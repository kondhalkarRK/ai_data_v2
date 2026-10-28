"""Stage 0b baseline: replay the CURRENT chat planning stack on labeled messages.

Does not execute SQL or call LLMs. Approximates ChatService through:
  region text guard (optional simulate_region_zones) -> is_out_of_bounds ->
  plan_turn (threaded prior_turns) -> query_router.route_question(has_documents) ->
  decision_engine.decide_route (for logging only; does not change predicted class).

Harness limitations (printed on every run):
  * Value dictionary built from seed generators (seed_values.py), not live warehouse.
  * No LLM interpret/reasoning, no SQL execution, no KnowledgeService search.
  * Region simulation uses forbidden_zones text guard only (not SQL RLS rewrite).
  * predicted_label is a heuristic map of TODAY's pipeline behavior, not the target router.

Predicted-label mapping (expected labels in the eval YAML):
  region_forbidden     -> UNSUPPORTED
  out_of_bounds        -> OUT_OF_SCOPE_LIVE if live/external cue else UNSUPPORTED
  clarification        -> CLARIFICATION
  knowledge_route        -> DOCUMENT_QUERY  (chat_route == knowledge, plan did not clarify)
  hybrid_route           -> DATA_QUERY       (chat_route == hybrid, before SQL execution)
  governed_sql+context -> DATA_FOLLOW_UP
  governed_sql         -> DATA_QUERY
  no_governed_sql      -> DATA_QUERY if plan looks analytic else CLARIFICATION
  plan_validation_failed -> CLARIFICATION

Usage (from apps/api):
    python tests/chat_routing_eval/run_baseline.py
"""

from __future__ import annotations

import argparse
import csv
import re
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass
from functools import cache
from pathlib import Path
from typing import Any

import yaml

EVAL_DIR = Path(__file__).resolve().parent
API_ROOT = EVAL_DIR.parents[1]
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))
if str(EVAL_DIR) not in sys.path:
    sys.path.insert(0, str(EVAL_DIR))

from app.core.config import Industry, get_settings  # noqa: E402
from app.semantic.service import SemanticService  # noqa: E402
from app.services.chat.conversation_context import plan_state  # noqa: E402
from app.services.chat.decision_engine import decide_route  # noqa: E402
from app.services.chat.intents import is_out_of_bounds  # noqa: E402
from app.services.chat.pipeline import plan_turn  # noqa: E402
from app.services.chat.plan_coverage import coverage_gaps  # noqa: E402
from app.services.chat.query_router import route_question  # noqa: E402
from app.services.chat.semantic_context import build_allowed_schema  # noqa: E402
from app.services.chat.value_dictionary import ValueDictionarySnapshot  # noqa: E402
from app.services.security.region_scope import RegionScope, forbidden_zones  # noqa: E402
from seed_values import seed_values_for_industry  # noqa: E402

EVAL_FILE = EVAL_DIR / "chat_routing_eval.yaml"
DEFAULT_OUT = EVAL_DIR / "results" / "baseline_latest.csv"

_LIVE_EXTERNAL = re.compile(
    r"\b(weather|forecast|temperature|cricket|football|soccer|basketball|"
    r"election|bitcoin|ethereum|crypto(?:currency)?|stock\s+price|"
    r"match\s+yesterday|won the\s+\w+\s+match)\b",
    re.I,
)

LIMITATIONS = """
HARNESS LIMITATIONS
-------------------
- Seed value dictionary only (not live catalog/warehouse distinct values).
- No LLM calls (interpret_question, generate_validated_sql) and no SQL execution.
- No KnowledgeService document search; has_documents only affects route_question().
- Region cases use forbidden_zones() text guard; full RBAC/RLS apply at execution time.
- predicted_label reflects current planner + router heuristics, not Stage 1+ behavior.
""".strip()


@dataclass
class ThreadState:
    prior_sql: str | None = None
    prior_state: dict[str, Any] | None = None


@dataclass
class ReplayRow:
    id: str
    expected_label: str
    predicted_label: str
    match: str
    industry: str
    message: str
    handling: str
    detail: str
    contextual: str
    plan_intent: str
    plan_entity: str
    plan_metric: str
    chat_route: str
    decision_path: str
    governed_sql: str
    has_documents: str
    coverage_gaps: str


@cache
def _context(industry: Industry) -> tuple[ValueDictionarySnapshot, Any, dict[str, set[str]]]:
    pack = SemanticService(get_settings())._load_pack(industry)
    snapshot = ValueDictionarySnapshot(industry, seed_values_for_industry(industry))
    return snapshot, pack, build_allowed_schema(pack)


def _plan_looks_analytic(plan: Any) -> bool:
    if plan is None:
        return False
    if plan.metric not in {"unknown", ""}:
        return True
    if plan.entity not in {"unknown", ""}:
        return True
    if plan.filters or plan.dimensions:
        return True
    if plan.intent not in {"unknown", "ambiguous"}:
        return True
    return False


def predict_label(
    *,
    case: dict[str, Any],
    handling: str,
    chat_route: str,
    contextual: bool,
    message: str,
    plan: Any,
) -> str:
    """Map observed pipeline signals to the eval label vocabulary."""
    if handling == "region_forbidden":
        return "UNSUPPORTED"
    if handling == "out_of_bounds":
        if _LIVE_EXTERNAL.search(message) or case.get("label") == "OUT_OF_SCOPE_LIVE":
            return "OUT_OF_SCOPE_LIVE"
        return "UNSUPPORTED"
    if handling == "clarification":
        return "CLARIFICATION"
    if chat_route == "knowledge":
        return "DOCUMENT_QUERY"
    if chat_route == "hybrid":
        return "DATA_QUERY"
    if handling == "governed_sql":
        return "DATA_FOLLOW_UP" if contextual else "DATA_QUERY"
    if handling == "no_governed_sql":
        return "DATA_QUERY" if _plan_looks_analytic(plan) else "CLARIFICATION"
    if handling == "plan_validation_failed":
        return "CLARIFICATION"
    return "CLARIFICATION"


def _handling_from_turn(
    turn: Any,
    *,
    message: str,
    industry: Industry,
) -> tuple[str, str]:
    if is_out_of_bounds(message, industry):
        return "out_of_bounds", "intents.is_out_of_bounds"
    if turn.clarification is not None:
        reason = turn.clarify_reason or "clarify"
        detail = reason
        if turn.clarification.message:
            detail = f"{reason}: {turn.clarification.message[:80]}"
        return "clarification", detail
    if turn.validation_error:
        return "plan_validation_failed", turn.validation_error[:120]
    if turn.governed_sql:
        path = turn.planned.path if turn.planned else "template"
        return "governed_sql", path
    return "no_governed_sql", "would_need_llm_or_clarify"


def _run_plan_turn(
    industry: Industry,
    message: str,
    thread: ThreadState,
    *,
    region_zones: list[str] | None,
) -> tuple[Any | None, str, str]:
    scope = (
        RegionScope(unrestricted=False, zones=tuple(region_zones))
        if region_zones
        else RegionScope.all_regions()
    )
    blocked = forbidden_zones(message, scope)
    if blocked:
        return None, "region_forbidden", f"blocked zones: {', '.join(blocked)}"

    snapshot, pack, allowed = _context(industry)
    turn = plan_turn(
        industry,
        message,
        snapshot=snapshot,
        pack=pack,
        allowed_schema=allowed,
        prior_sql=thread.prior_sql,
        prior_state=thread.prior_state,
    )
    handling, detail = _handling_from_turn(turn, message=message, industry=industry)
    if turn.governed_sql and turn.plan:
        thread.prior_sql = turn.governed_sql
        thread.prior_state = plan_state(turn.plan)
    return turn, handling, detail


def _row_from_turn(
    *,
    case: dict[str, Any],
    turn: Any | None,
    handling: str,
    detail: str,
    has_documents: bool,
) -> ReplayRow:
    message = str(case["message"])
    plan = turn.plan if turn is not None else None
    contextual = turn.contextual if turn is not None else False

    chat_route = "n/a"
    decision_path = "n/a"
    if (
        turn is not None
        and turn.clarification is None
        and handling not in {"region_forbidden", "out_of_bounds"}
    ):
        chat = route_question(message, plan, has_documents=has_documents)
        chat_route = chat.route
        if handling == "governed_sql" and chat_route in {"knowledge", "hybrid"}:
            handling = f"{chat_route}_route"
        if plan is not None:
            decision = decide_route(
                plan,
                has_governed_sql=bool(turn.governed_sql),
                llm_available=True,
                mode="llm_first",
            )
            decision_path = decision.path

    gaps = coverage_gaps(message, plan) if plan else []
    expected = str(case["label"])
    predicted = predict_label(
        case=case,
        handling=handling,
        chat_route=chat_route,
        contextual=bool(contextual),
        message=message,
        plan=plan,
    )
    return ReplayRow(
        id=str(case["id"]),
        expected_label=expected,
        predicted_label=predicted,
        match="true" if expected == predicted else "false",
        industry=str(case["industry"]),
        message=message,
        handling=handling,
        detail=detail,
        contextual="yes" if contextual else "no",
        plan_intent=getattr(plan, "intent", "") or "",
        plan_entity=getattr(plan, "entity", "") or "",
        plan_metric=getattr(plan, "metric", "") or "",
        chat_route=chat_route,
        decision_path=decision_path,
        governed_sql="yes" if turn and turn.governed_sql else "no",
        has_documents="true" if has_documents else "false",
        coverage_gaps="; ".join(gaps) if gaps else "",
    )


def replay_case(case: dict[str, Any]) -> ReplayRow:
    industry = Industry(case["industry"])
    has_documents = bool(case.get("has_documents", False))
    region_zones = case.get("simulate_region_zones")
    thread = ThreadState()

    for prior in case.get("prior_turns") or []:
        prior_msg = str(prior["message"])
        prior_zones = prior.get("simulate_region_zones", region_zones)
        _run_plan_turn(industry, prior_msg, thread, region_zones=prior_zones)

    turn, handling, detail = _run_plan_turn(
        industry,
        str(case["message"]),
        thread,
        region_zones=region_zones,
    )
    if handling == "region_forbidden":
        return _row_from_turn(
            case=case,
            turn=None,
            handling=handling,
            detail=detail,
            has_documents=has_documents,
        )
    assert turn is not None
    return _row_from_turn(
        case=case,
        turn=turn,
        handling=handling,
        detail=detail,
        has_documents=has_documents,
    )


def load_cases(path: Path) -> list[dict[str, Any]]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    return list(data.get("cases") or [])


def write_csv(rows: list[ReplayRow], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = list(ReplayRow.__dataclass_fields__.keys())
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow(row.__dict__)


def compute_metrics(rows: list[ReplayRow]) -> dict[str, Any]:
    total = len(rows)
    matches = sum(1 for r in rows if r.match == "true")
    by_expected: Counter[str] = Counter()
    correct_by_expected: Counter[str] = Counter()
    confusion: dict[str, Counter[str]] = defaultdict(Counter)
    for row in rows:
        by_expected[row.expected_label] += 1
        if row.match == "true":
            correct_by_expected[row.expected_label] += 1
        confusion[row.expected_label][row.predicted_label] += 1
    per_label = {
        label: {
            "total": by_expected[label],
            "correct": correct_by_expected[label],
            "accuracy": correct_by_expected[label] / by_expected[label]
            if by_expected[label]
            else 0.0,
        }
        for label in sorted(by_expected)
    }
    return {
        "total": total,
        "correct": matches,
        "overall_accuracy": matches / total if total else 0.0,
        "per_label": per_label,
        "confusion": {k: dict(v) for k, v in sorted(confusion.items())},
    }


def format_metrics(metrics: dict[str, Any]) -> str:
    lines = [
        LIMITATIONS,
        "",
        f"Overall accuracy: {metrics['correct']}/{metrics['total']} "
        f"({metrics['overall_accuracy']:.1%})",
        "",
        "Per-label accuracy:",
    ]
    for label, stats in metrics["per_label"].items():
        lines.append(
            f"  {label}: {stats['correct']}/{stats['total']} ({stats['accuracy']:.1%})"
        )
    lines.extend(["", "Confusion matrix (expected -> predicted counts):"])
    all_predicted = sorted({p for row in metrics["confusion"].values() for p in row.keys()})
    header = "expected \\ predicted".ljust(22) + "".join(p.ljust(18) for p in all_predicted)
    lines.append(header)
    for expected, counts in metrics["confusion"].items():
        row = expected.ljust(22)
        for pred in all_predicted:
            row += str(counts.get(pred, 0)).ljust(18)
        lines.append(row)
    return "\n".join(lines)


def write_markdown(rows: list[ReplayRow], metrics: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Chat routing baseline (Stage 0b)",
        "",
        "```",
        format_metrics(metrics),
        "```",
        "",
        "## Mismatches",
        "",
        "| id | expected | predicted | handling | message |",
        "| --- | --- | --- | --- | --- |",
    ]
    for row in rows:
        if row.match == "true":
            continue
        msg = row.message.replace("|", "\\|")[:40]
        lines.append(
            f"| {row.id} | {row.expected_label} | {row.predicted_label} | "
            f"{row.handling} | {msg} |"
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Chat routing Stage 0b baseline")
    parser.add_argument("--suite", type=Path, default=EVAL_FILE)
    parser.add_argument("--csv", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--markdown", type=Path, default=None)
    parser.add_argument("--metrics", type=Path, default=None)
    args = parser.parse_args()

    cases = load_cases(args.suite)
    rows = [replay_case(case) for case in cases]
    metrics = compute_metrics(rows)

    write_csv(rows, args.csv)
    md_path = args.markdown or args.csv.with_suffix(".md")
    write_markdown(rows, metrics, md_path)
    metrics_path = args.metrics or args.csv.with_name("baseline_metrics.txt")
    metrics_text = format_metrics(metrics)
    metrics_path.write_text(metrics_text + "\n", encoding="utf-8")

    print(metrics_text)
    print(f"\nCSV: {args.csv}")
    print(f"Markdown: {md_path}")
    print(f"Metrics: {metrics_path}")
    mismatches = [r for r in rows if r.match == "false"]
    print(f"\nMismatches ({len(mismatches)}):")
    for row in mismatches:
        print(
            f"  {row.id}: expected={row.expected_label} predicted={row.predicted_label} "
            f"handling={row.handling} msg={row.message[:50]!r}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
