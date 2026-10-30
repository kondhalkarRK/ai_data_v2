"""Stage 0c baseline: replay the CURRENT chat planning stack on labeled messages.

Canonical FROZEN snapshot (do not overwrite — use --csv baseline_latest.csv for experiments):
  results/baseline_stage0.csv
  results/baseline_stage0_metrics.txt

Does not execute SQL or call LLMs.

ChatService order mirrored per message:
  region guard (forbidden_zones) -> message classifier (optional) -> memory expiry
  -> follow-up guard (optional) -> plan_turn
  Blocked messages never update ThreadState.

Predicted-label mapping (message + pipeline signals only; never reads case label):

  region_forbidden           -> UNSUPPORTED
  out_of_bounds + live cue   -> OUT_OF_SCOPE_LIVE  (_LIVE_EXTERNAL on message)
  out_of_bounds otherwise    -> UNSUPPORTED
  clarification              -> CLARIFICATION
  plan_validation_failed     -> CLARIFICATION
  knowledge_route / chat_route knowledge -> DOCUMENT_QUERY
  hybrid_route / chat_route hybrid     -> DATA_QUERY
  governed_sql + contextual  -> DATA_FOLLOW_UP
  governed_sql               -> DATA_QUERY
  no_governed_sql + analytic plan -> DATA_QUERY_NEEDS_LLM
  no_governed_sql otherwise  -> CLARIFICATION
  (anything else)            -> UNROUTED

DATA_QUERY_NEEDS_LLM and UNROUTED never count as label matches (always non-match).

Cases with expected_stage: 1 are excluded from Stage 0 accuracy / confusion matrix.

Usage (from apps/api):
    python tests/chat_routing_eval/run_baseline.py
    python tests/chat_routing_eval/run_baseline.py --csv results/scratch.csv
    python tests/chat_routing_eval/run_baseline.py --compare results/baseline_stage0.csv
    python tests/chat_routing_eval/run_baseline.py --fail-under 0.65
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

from app.core.config import Industry, Settings, get_settings  # noqa: E402
from app.semantic.service import SemanticService  # noqa: E402
from app.services.chat.conversation_context import is_contextual_followup, plan_state  # noqa: E402
from app.services.chat.conversation_memory import build_analytical_context, ResultMeta  # noqa: E402
from app.services.chat.decision_engine import decide_route  # noqa: E402
from app.services.chat.follow_up_guard import (  # noqa: E402
    data_vocabulary_hit,
    follow_up_guard_allows_sql,
)
from app.services.chat.pipeline import plan_turn  # noqa: E402
from app.services.chat.plan_coverage import coverage_gaps  # noqa: E402
from app.services.chat.pre_plan import (  # noqa: E402
    plan_with_rewrites,
    run_pre_plan,
    synthetic_memory,
)
from app.services.chat.query_router import route_question  # noqa: E402
from app.services.chat.semantic_context import build_allowed_schema  # noqa: E402
from app.services.chat.value_dictionary import ValueDictionarySnapshot  # noqa: E402
from app.services.security.region_scope import RegionScope  # noqa: E402
from seed_values import seed_values_for_industry  # noqa: E402

EVAL_FILE = EVAL_DIR / "chat_routing_eval.yaml"
STAGE0_CSV = EVAL_DIR / "results" / "baseline_stage0.csv"
STAGE0_METRICS = EVAL_DIR / "results" / "baseline_stage0_metrics.txt"
DEFAULT_CSV = EVAL_DIR / "results" / "baseline_latest.csv"
DEFAULT_METRICS = EVAL_DIR / "results" / "baseline_latest_metrics.txt"

NON_EVAL_PREDICTED = frozenset({"DATA_QUERY_NEEDS_LLM", "UNROUTED"})

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
    memory: Any = None  # SessionMemory, built lazily


@dataclass
class ReplayRow:
    id: str
    expected_label: str
    predicted_label: str
    match: str
    expected_stage: str
    plan_expect_match: str
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
    handling: str,
    chat_route: str,
    contextual: bool,
    message: str,
    plan: Any,
) -> str:
    """Map pipeline signals to eval vocabulary (see module docstring)."""
    if handling == "region_forbidden":
        return "UNSUPPORTED"
    if handling == "memory_expired":
        return "CLARIFICATION"
    if handling == "scope_denied":
        return "UNSUPPORTED"
    if handling == "general_chat":
        return "GENERAL_CHAT"
    if handling == "unsupported":
        return "UNSUPPORTED"
    if handling == "out_of_scope_live":
        return "OUT_OF_SCOPE_LIVE"
    if handling == "follow_up_guard":
        return "CLARIFICATION"
    if handling == "app_help":
        return "APP_HELP"
    if handling == "document_query":
        return "DOCUMENT_QUERY"
    if handling == "general_knowledge":
        return "GENERAL_KNOWLEDGE"
    if handling == "classifier_clarify":
        return "CLARIFICATION"
    if handling == "legacy_out_of_bounds":
        return "OUT_OF_SCOPE_LIVE" if _LIVE_EXTERNAL.search(message) else "UNSUPPORTED"
    if handling == "out_of_bounds":
        return "OUT_OF_SCOPE_LIVE" if _LIVE_EXTERNAL.search(message) else "UNSUPPORTED"
    if handling == "clarification":
        return "CLARIFICATION"
    if handling == "plan_validation_failed":
        return "CLARIFICATION"
    if handling in {"knowledge_route"} or chat_route == "knowledge":
        return "DOCUMENT_QUERY"
    if handling in {"hybrid_route"} or chat_route == "hybrid":
        return "DATA_QUERY"
    if handling == "governed_sql":
        return "DATA_FOLLOW_UP" if contextual else "DATA_QUERY"
    if handling == "no_governed_sql":
        return "DATA_QUERY_NEEDS_LLM" if _plan_looks_analytic(plan) else "CLARIFICATION"
    return "UNROUTED"


def _thread_memory(thread: ThreadState) -> Any:
    if thread.memory is None:
        thread.memory = synthetic_memory(prior_state=thread.prior_state)
    return thread.memory


def _scope(region_zones: list[str] | None) -> RegionScope:
    if region_zones:
        return RegionScope(unrestricted=False, zones=tuple(region_zones))
    return RegionScope.all_regions()


def _apply_pre_plan(
    industry: Industry,
    message: str,
    thread: ThreadState,
    *,
    region_zones: list[str] | None,
    settings: Settings,
    router_enabled: bool,
    guard_enabled: bool,
) -> tuple[str, str] | None:
    snapshot, pack, _allowed = _context(industry)
    memory = _thread_memory(thread)

    def _guard_check(**kwargs: Any) -> tuple[bool, str | None]:
        return follow_up_guard_allows_sql(
            question=kwargs["question"],
            session_memory=kwargs["session_memory"],
            settings=settings,
            prior_state=kwargs["prior_state"],
            snapshot=snapshot,
            pack=pack,
            industry=industry,
        )

    outcome = run_pre_plan(
        industry=industry,
        message=message,
        settings=settings,
        scope=_scope(region_zones),
        session_memory=memory,
        prior_state=thread.prior_state,
        router_enabled=router_enabled,
        data_vocabulary=lambda text: data_vocabulary_hit(text, snapshot, pack),
        follow_up_guard_check=_guard_check if guard_enabled else None,
    )
    if outcome.follow_up_guard_blocked:
        return "follow_up_guard", outcome.stop_detail or "no semantic anchor"
    if not outcome.proceed:
        return outcome.stop or "unsupported", outcome.stop_detail
    thread.prior_state = outcome.prior_state
    return None


def _run_plan_turn(
    industry: Industry,
    message: str,
    thread: ThreadState,
    *,
    region_zones: list[str] | None,
    settings: Settings,
    router_enabled: bool,
    guard_enabled: bool,
    rewrites_enabled: bool = False,
) -> tuple[Any | None, str, str]:
    blocked = _apply_pre_plan(
        industry,
        message,
        thread,
        region_zones=region_zones,
        settings=settings,
        router_enabled=router_enabled,
        guard_enabled=guard_enabled,
    )
    if blocked is not None:
        return None, blocked[0], blocked[1]

    snapshot, pack, allowed = _context(industry)
    planned = plan_with_rewrites(
        lambda text: plan_turn(
            industry,
            text,
            snapshot=snapshot,
            pack=pack,
            allowed_schema=allowed,
            prior_sql=thread.prior_sql,
            prior_state=thread.prior_state,
        ),
        message.strip(),
        enabled=rewrites_enabled,
    )
    turn = planned.turn
    if turn.clarification is not None:
        reason = turn.clarify_reason or "clarify"
        detail = reason
        if turn.clarification.message:
            detail = f"{reason}: {turn.clarification.message[:80]}"
        handling = "clarification"
    elif turn.validation_error:
        handling, detail = "plan_validation_failed", turn.validation_error[:120]
    elif turn.governed_sql:
        handling = "governed_sql"
        detail = turn.planned.path if turn.planned else "template"
        if planned.planned_question != message.strip():
            detail += f" | rewritten: {planned.planned_question[:60]}"
        if planned.definition_term:
            detail += f" | definition: {planned.definition_term}"
    else:
        handling, detail = "no_governed_sql", "would_need_llm_or_clarify"

    if turn.governed_sql and turn.plan:
        thread.prior_sql = turn.governed_sql
        thread.prior_state = plan_state(turn.plan)
        memory = _thread_memory(thread)
        memory.analytical = build_analytical_context(
            plan=turn.plan,
            question=message,
            result_meta=ResultMeta(row_count=1, column_names=()),
            prior=memory.analytical,
        )
    return turn, handling, detail


def _compare_plan_expect(plan: Any | None, expect: dict[str, Any] | None) -> str:
    if not expect:
        return "n/a"
    if plan is None:
        return "false"
    if "metric" in expect and plan.metric != expect["metric"]:
        return "false"
    if "entity" in expect and plan.entity != expect["entity"]:
        return "false"
    if "time_grain" in expect:
        expected_grain = expect["time_grain"]
        if plan.time_grain != expected_grain and not (
            expected_grain is None and plan.time_grain in {None, ""}
        ):
            return "false"
    if "dimensions" in expect:
        if list(plan.dimensions) != list(expect["dimensions"]):
            return "false"
    if "filters" in expect:
        actual = sorted(
            value for item in plan.filters for value in item.all_values
        )
        if actual != sorted(str(v) for v in expect["filters"]):
            return "false"
    return "true"


def _labels_match(expected: str, predicted: str) -> bool:
    if predicted in NON_EVAL_PREDICTED:
        return False
    return expected == predicted


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
        and handling
        not in {
            "region_forbidden",
            "memory_expired",
            "scope_denied",
            "general_chat",
            "unsupported",
            "out_of_scope_live",
            "follow_up_guard",
            "legacy_out_of_bounds",
            "out_of_bounds",
            "app_help",
            "document_query",
            "general_knowledge",
            "classifier_clarify",
        }
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
        handling=handling,
        chat_route=chat_route,
        contextual=bool(contextual),
        message=message,
        plan=plan,
    )
    stage = str(case.get("expected_stage") or "")
    return ReplayRow(
        id=str(case["id"]),
        expected_label=expected,
        predicted_label=predicted,
        match="true" if _labels_match(expected, predicted) else "false",
        expected_stage=stage,
        plan_expect_match=_compare_plan_expect(plan, case.get("expect")),
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


def replay_case(
    case: dict[str, Any],
    *,
    settings: Settings | None = None,
    router_enabled: bool | None = None,
    guard_enabled: bool | None = None,
    rewrites_enabled: bool | None = None,
) -> ReplayRow:
    settings = settings or get_settings()
    rewrites_enabled = (
        settings.chat_question_rewrites_enabled if rewrites_enabled is None else rewrites_enabled
    )
    router_enabled = (
        settings.chat_router_enabled if router_enabled is None else router_enabled
    )
    guard_enabled = (
        settings.chat_follow_up_guard_enabled if guard_enabled is None else guard_enabled
    )
    industry = Industry(case["industry"])
    has_documents = bool(case.get("has_documents", False))
    region_zones = case.get("simulate_region_zones")
    thread = ThreadState()

    for prior in case.get("prior_turns") or []:
        prior_msg = str(prior["message"])
        prior_zones = prior.get("simulate_region_zones", region_zones)
        blocked = _apply_pre_plan(
            industry,
            prior_msg,
            thread,
            region_zones=prior_zones,
            settings=settings,
            router_enabled=router_enabled,
            guard_enabled=guard_enabled,
        )
        if blocked is not None:
            continue
        _run_plan_turn(
            industry,
            prior_msg,
            thread,
            region_zones=prior_zones,
            settings=settings,
            router_enabled=router_enabled,
            guard_enabled=guard_enabled,
            rewrites_enabled=rewrites_enabled,
        )

    turn, handling, detail = _run_plan_turn(
        industry,
        str(case["message"]),
        thread,
        region_zones=region_zones,
        settings=settings,
        router_enabled=router_enabled,
        guard_enabled=guard_enabled,
        rewrites_enabled=rewrites_enabled,
    )
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


def stage0_rows(rows: list[ReplayRow]) -> list[ReplayRow]:
    return [row for row in rows if row.expected_stage != "1"]


def compute_metrics(rows: list[ReplayRow]) -> dict[str, Any]:
    total = len(rows)
    matches = sum(1 for r in rows if r.match == "true")
    by_expected: Counter[str] = Counter()
    tp_by_label: Counter[str] = Counter()
    predicted_counts: Counter[str] = Counter()
    confusion: dict[str, Counter[str]] = defaultdict(Counter)
    for row in rows:
        by_expected[row.expected_label] += 1
        predicted_counts[row.predicted_label] += 1
        confusion[row.expected_label][row.predicted_label] += 1
        if row.match == "true":
            tp_by_label[row.expected_label] += 1
    per_label: dict[str, dict[str, Any]] = {}
    all_labels = sorted(set(by_expected) | set(predicted_counts))
    for label in all_labels:
        support = by_expected[label]
        pred_n = predicted_counts[label]
        tp = tp_by_label[label]
        per_label[label] = {
            "support": support,
            "predicted_as": pred_n,
            "tp": tp,
            "recall": tp / support if support else None,
            "precision": tp / pred_n if pred_n else None,
        }
    return {
        "total": total,
        "correct": matches,
        "overall_accuracy": matches / total if total else 0.0,
        "per_label": per_label,
        "confusion": {k: dict(v) for k, v in sorted(confusion.items())},
    }


def format_metrics(metrics: dict[str, Any], *, title: str = "Stage 0 baseline") -> str:
    lines = [
        LIMITATIONS,
        "",
        f"=== {title} ===",
        f"Overall accuracy: {metrics['correct']}/{metrics['total']} "
        f"({metrics['overall_accuracy']:.1%})",
        "",
        "Per-label recall / precision (tp / support, tp / predicted_as):",
    ]
    for label, stats in sorted(metrics["per_label"].items()):
        if stats["support"] == 0 and stats["predicted_as"] == 0:
            continue
        recall = stats["recall"]
        precision = stats["precision"]
        recall_s = f"{recall:.1%}" if recall is not None else "n/a"
        precision_s = f"{precision:.1%}" if precision is not None else "n/a"
        lines.append(
            f"  {label}: recall {stats['tp']}/{stats['support']} ({recall_s}) | "
            f"precision {stats['tp']}/{stats['predicted_as']} ({precision_s})"
        )
    lines.extend(["", "Confusion matrix (expected -> predicted counts):"])
    all_predicted = sorted({p for row in metrics["confusion"].values() for p in row.keys()})
    header = "expected \\ predicted".ljust(22) + "".join(p.ljust(20) for p in all_predicted)
    lines.append(header)
    for expected, counts in metrics["confusion"].items():
        row = expected.ljust(22)
        for pred in all_predicted:
            row += str(counts.get(pred, 0)).ljust(20)
        lines.append(row)
    return "\n".join(lines)


def write_csv(rows: list[ReplayRow], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = list(ReplayRow.__dataclass_fields__.keys())
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow(row.__dict__)


def load_csv_rows(path: Path) -> dict[str, dict[str, str]]:
    with path.open(encoding="utf-8") as handle:
        return {row["id"]: row for row in csv.DictReader(handle)}


def compare_runs(
    current: list[ReplayRow],
    previous_path: Path,
    metrics: dict[str, Any],
    prev_metrics: dict[str, Any],
) -> str:
    prev = load_csv_rows(previous_path)
    lines = ["", "=== Compare to previous ===", f"Previous: {previous_path}", ""]
    fixed: list[str] = []
    regressed: list[str] = []
    for row in current:
        old = prev.get(row.id)
        if old is None:
            continue
        was = old.get("match") == "true"
        now = row.match == "true"
        if not was and now:
            fixed.append(row.id)
        elif was and not now:
            regressed.append(row.id)
    lines.append(f"Fixed ({len(fixed)}): {', '.join(fixed) or 'none'}")
    lines.append(f"Regressed ({len(regressed)}): {', '.join(regressed) or 'none'}")
    lines.append("")
    lines.append("Per-label recall delta (current - previous):")
    all_labels = set(metrics["per_label"]) | set(prev_metrics["per_label"])
    for label in sorted(all_labels):
        cur_r = metrics["per_label"].get(label, {}).get("recall")
        old_r = prev_metrics["per_label"].get(label, {}).get("recall")
        if cur_r is None and old_r is None:
            continue
        cur_s = f"{cur_r:.1%}" if cur_r is not None else "n/a"
        old_s = f"{old_r:.1%}" if old_r is not None else "n/a"
        delta = ""
        if cur_r is not None and old_r is not None:
            delta = f" ({cur_r - old_r:+.1%})"
        lines.append(f"  {label}: {old_s} -> {cur_s}{delta}")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Chat routing Stage 0c baseline")
    parser.add_argument("--suite", type=Path, default=EVAL_FILE)
    parser.add_argument(
        "--csv",
        type=Path,
        default=DEFAULT_CSV,
        help="Output CSV (default: baseline_latest.csv; frozen snapshot is baseline_stage0.csv)",
    )
    parser.add_argument("--metrics", type=Path, default=DEFAULT_METRICS)
    parser.add_argument("--compare", type=Path, default=None, help="Previous CSV for deltas")
    parser.add_argument(
        "--fail-under",
        type=float,
        default=None,
        help="Exit 1 if Stage 0 overall accuracy is below this fraction",
    )
    parser.add_argument(
        "--router-enabled",
        action="store_true",
        help="Enable message classifier in harness (default: settings.chat_router_enabled)",
    )
    parser.add_argument(
        "--follow-up-guard",
        action="store_true",
        help="Enable follow-up guard in harness",
    )
    parser.add_argument(
        "--question-rewrites",
        action="store_true",
        help="Enable compound split and why/explain strip retry (Stage E)",
    )
    args = parser.parse_args()

    settings = get_settings()
    router = args.router_enabled or settings.chat_router_enabled
    guard = args.follow_up_guard

    cases = load_cases(args.suite)
    rows = [
        replay_case(
            case,
            settings=settings,
            router_enabled=router,
            guard_enabled=guard,
            rewrites_enabled=args.question_rewrites,
        )
        for case in cases
    ]
    s0 = stage0_rows(rows)
    metrics = compute_metrics(s0)
    stage1_rows = [r for r in rows if r.expected_stage == "1"]

    write_csv(rows, args.csv)
    body = format_metrics(metrics, title="Stage 0 baseline (excludes expected_stage: 1)")
    if stage1_rows:
        body += "\n\n=== Deferred to Stage 1 (excluded from accuracy) ===\n"
        for row in stage1_rows:
            body += (
                f"  {row.id}: expected={row.expected_label} predicted={row.predicted_label} "
                f"match={row.match}\n"
            )
    compare_text = ""
    if args.compare and args.compare.is_file():
        prev_rows = list(load_csv_rows(args.compare).values())
        prev_s0 = [r for r in prev_rows if r.get("expected_stage") != "1"]
        prev_replay = [
            ReplayRow(
                id=r["id"],
                expected_label=r["expected_label"],
                predicted_label=r["predicted_label"],
                match=r["match"],
                expected_stage=r.get("expected_stage", ""),
                plan_expect_match=r.get("plan_expect_match", "n/a"),
                industry=r["industry"],
                message=r["message"],
                handling=r["handling"],
                detail=r["detail"],
                contextual=r["contextual"],
                plan_intent=r["plan_intent"],
                plan_entity=r["plan_entity"],
                plan_metric=r["plan_metric"],
                chat_route=r["chat_route"],
                decision_path=r["decision_path"],
                governed_sql=r["governed_sql"],
                has_documents=r.get("has_documents", "false"),
                coverage_gaps=r.get("coverage_gaps", ""),
            )
            for r in prev_s0
        ]
        prev_metrics = compute_metrics(prev_replay)
        compare_text = compare_runs(s0, args.compare, metrics, prev_metrics)
        body += compare_text

    args.metrics.write_text(body + "\n", encoding="utf-8")

    print(body)
    print(f"\nCSV: {args.csv}")
    print(f"Metrics: {args.metrics}")
    if args.csv == STAGE0_CSV:
        print(
            "\nWARNING: You are writing the FROZEN Stage 0 snapshot. "
            "Use --csv results/baseline_latest.csv for routine runs."
        )

    mismatches = [r for r in s0 if r.match == "false"]
    print(f"\nStage 0 mismatches ({len(mismatches)}):")
    for row in mismatches:
        print(
            f"  {row.id}: expected={row.expected_label} predicted={row.predicted_label} "
            f"handling={row.handling} msg={row.message[:50]!r}"
        )

    plan_fails = [r for r in rows if r.plan_expect_match == "false"]
    print(f"\nPlan expect failures ({len(plan_fails)}):")
    for row in plan_fails:
        print(
            f"  {row.id}: entity={row.plan_entity} metric={row.plan_metric} "
            f"intent={row.plan_intent} msg={row.message[:40]!r}"
        )

    if args.fail_under is not None and metrics["overall_accuracy"] < args.fail_under:
        print(f"\nFAIL: accuracy {metrics['overall_accuracy']:.1%} < {args.fail_under:.1%}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
