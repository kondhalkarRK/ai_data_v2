"""Run the NLQ benchmark offline against the current planner.

The run replays the AI Chat pipeline in ``ChatService.ask`` up to (not including)
database execution: scope guard, value resolution, clarification gates, planning,
SQL compilation and plan validation. Questions that would need the LLM are
reported as failures, because the benchmark measures governed answers.

The value dictionary is built from the seed generators, i.e. the same distinct
values the live dictionary loads from the analytics database.

Usage (from apps/api):
    python tests/benchmark/run_benchmark.py --label baseline
    python tests/benchmark/run_benchmark.py --label after --compare baseline \
        --report ../../docs/nlq-benchmark-report.md
    python tests/benchmark/run_benchmark.py --suite tests/benchmark/nlq_holdout.yaml
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass, field
from datetime import date, timedelta
from functools import cache
from pathlib import Path
from typing import Any

import yaml

API_ROOT = Path(__file__).resolve().parents[2]
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))

from app.analytics import automotive_seed, insurance_seed  # noqa: E402
from app.analytics.sql_guardrails import sql_is_safe  # noqa: E402
from app.core.config import Industry, get_settings  # noqa: E402
from app.semantic.service import SemanticService  # noqa: E402
from app.services.chat.clarification import assess_resolution  # noqa: E402
from app.services.chat.conversation_context import is_contextual_followup, plan_state  # noqa: E402
from app.services.chat.intents import is_out_of_bounds, needs_clarification  # noqa: E402
from app.services.chat.question_understanding import understand_question  # noqa: E402
from app.services.chat.semantic_context import (  # noqa: E402
    build_allowed_schema,
    validate_sql_against_plan,
)
from app.services.chat.semantic_query_planner import (  # noqa: E402
    plan_semantic_query,
    rewrite_question,
)
from app.services.chat.value_dictionary import (  # noqa: E402
    BusinessValue,
    ValueDictionarySnapshot,
    resolver_for,
)

BENCHMARK = Path(__file__).with_name("nlq_benchmark.yaml")
RESULTS_DIR = Path(__file__).with_name("results")

A = r"(?:\w+\.)?"  # optional table alias, written as "@" in the benchmark

METRIC_PATTERNS: dict[str, list[str]] = {
    "revenue": [r"sum\(@total_sales\)"],
    "units": [r"sum\(@order_qty\)"],
    "orders": [r"count\(distinct @order_id\)"],
    "asp": [r"sum\(@total_sales\)\s*/\s*nullif\(sum\(@order_qty\)"],
    "gwp": [r"sum\(@written_premium\)"],
    "earned": [r"sum\(@earned_premium\)"],
    "incurred": [r"sum\(@incurred_amount\)"],
    "paid": [r"sum\(@paid_amount\)"],
    "claim_count": [r"count\((?:distinct )?(?:@claim_id|\*)\)"],
    "loss_ratio": [r"@incurred_amount", r"@earned_premium"],
    "severity": [r"@incurred_amount", r"count\(distinct @claim_id\)"],
    "frequency": [r"@claim_id", r"@exposure_units"],
    "approval_rate": [r"approved_flag"],
    "renewal_rate": [r"renewed_flag"],
}

GROUP_PATTERNS: dict[str, str] = {
    "year": r"extract\(year from|date_trunc\('year'",
    "quarter": r"date_trunc\('quarter'|extract\(quarter from",
    "month": r"date_trunc\('month'|to_char\([^)]*'yyyy-mm'",
    "make": r"@make\b",
    "model": r"@model\b",
    "colour": r"@colour_name\b",
    "car_type": r"@car_type\b",
    "engine_type": r"@engine_type\b",
    "city": r"@city\b",
    "region": r"@region_name\b",
    "state": r"@state_code\b|@state_name\b",
    "dealer": r"@dealer_name\b",
    "salesperson": r"first_name",
    "product": r"@product_name\b",
    "lob": r"@line_of_business\b",
    "channel": r"@channel_name\b",
    "agent": r"@agent_name\b",
    "tier": r"@coverage_tier\b",
    "claim_type": r"@claim_type\b",
}


def _rx(pattern: str) -> re.Pattern[str]:
    return re.compile(pattern.replace("@", A), re.I)


def _normalise(sql: str) -> str:
    return re.sub(r"\s+", " ", sql or "").strip().lower()


# ─────────────────────────── value dictionary ───────────────────────────


@cache
def _seed_values(industry: Industry) -> tuple[BusinessValue, ...]:
    rows: list[tuple[str, str, list[str]]] = []
    if industry is Industry.AUTOMOTIVE:
        d = automotive_seed.build_dimensions()
        rows = [
            ("Car Type", "automotive.dim_carline.car_type", [c.car_type for c in d.carlines]),
            ("Make", "automotive.dim_carline.make", [c.make for c in d.carlines]),
            ("Model", "automotive.dim_carline.model", [c.model for c in d.carlines]),
            (
                "Engine Type",
                "automotive.dim_carline.engine_type",
                [c.engine_type for c in d.carlines],
            ),
            ("Colour", "automotive.dim_color.colour_name", [c.colour_name for c in d.colours]),
            ("City", "automotive.dim_region.city", [r.city for r in d.regions]),
            ("Region", "automotive.dim_region.region_name", [r.region_name for r in d.regions]),
            ("State", "automotive.dim_region.state_code", [r.state_code for r in d.regions]),
            (
                "Dealer Grade",
                "automotive.dim_dealer.dealer_grade",
                [x.dealer_grade for x in d.dealers],
            ),
        ]
    else:
        d = insurance_seed.build_dimensions(policy_count=2_000)
        rows = [
            (
                "Claim Status",
                "insurance.fact_claims.claim_status",
                list(insurance_seed.CLAIM_STATUSES),
            ),
            ("Claim Type", "insurance.fact_claims.claim_type", list(insurance_seed.CLAIM_TYPES)),
            (
                "Policy Status",
                "insurance.dim_policy.policy_status",
                [p.policy_status for p in d.policies],
            ),
            (
                "Coverage Tier",
                "insurance.dim_policy.coverage_tier",
                [p.coverage_tier for p in d.policies],
            ),
            ("Product", "insurance.dim_product.product_name", [p.product_name for p in d.products]),
            (
                "Line of Business",
                "insurance.dim_product.line_of_business",
                [p.line_of_business for p in d.products],
            ),
            (
                "Product Family",
                "insurance.dim_product.product_family",
                [p.product_family for p in d.products],
            ),
            (
                "Coverage Type",
                "insurance.dim_product.coverage_type",
                [p.coverage_type for p in d.products],
            ),
            ("Channel", "insurance.dim_agent.channel_name", [a.channel_name for a in d.agents]),
            ("Branch", "insurance.dim_agent.branch_name", [a.branch_name for a in d.agents]),
            ("Region", "insurance.dim_region.region_name", [r.region_name for r in d.regions]),
            ("State", "insurance.dim_region.state_name", [r.state_name for r in d.regions]),
        ]
    values: list[BusinessValue] = []
    for domain, column, items in rows:
        for value, count in Counter(items).items():
            values.append(BusinessValue(domain, column, str(value), count))
    return tuple(values)


@cache
def _context(industry: Industry) -> tuple[ValueDictionarySnapshot, Any, dict[str, set[str]]]:
    pack = SemanticService(get_settings())._load_pack(industry)
    snapshot = ValueDictionarySnapshot(industry, _seed_values(industry))
    return snapshot, pack, build_allowed_schema(pack)


# ───────────────────────────── pipeline replay ─────────────────────────────


@dataclass
class Turn:
    outcome: str  # sql | clarify | failure
    detail: str = ""
    sql: str = ""
    path: str = ""
    plan: Any = None
    resolved: list[str] = field(default_factory=list)
    unresolved: list[str] = field(default_factory=list)


def ask(industry: Industry, question: str, prior: Turn | None = None) -> Turn:
    """Mirror ChatService.ask from the scope guard to plan validation."""
    snapshot, pack, allowed = _context(industry)
    if is_out_of_bounds(question, industry):
        return Turn("failure", "out_of_scope")
    resolution = snapshot.resolve(question, pack=pack)
    turn = Turn(
        "failure",
        resolved=[f"{m.text}->{m.entry.canonical} ({m.method})" for m in resolution.matches],
        unresolved=[u.text for u in resolution.unresolved],
    )
    value_filters = resolution.filters()
    if not resolution.matches and (message := needs_clarification(question)):
        turn.outcome, turn.detail = "clarify", f"needs_clarification: {message[:90]}"
        return turn
    plan = understand_question(industry, rewrite_question(question), value_filters=value_filters)
    turn.plan = plan
    if plan.is_ambiguous and plan.ambiguity_options:
        turn.outcome, turn.detail = "clarify", f"ambiguous: {(plan.notes or [''])[0][:90]}"
        return turn
    followup = is_contextual_followup(question)
    gate = assess_resolution(
        question,
        plan,
        resolution,
        industry=industry,
        brands=resolver_for(snapshot, pack).canonical_values("make"),
    )
    if gate is not None and not followup:
        turn.outcome, turn.detail = "clarify", f"{gate.kind}: {gate.message[:90]}"
        return turn
    prior_sql = prior_state = None
    if followup and prior is not None and prior.plan is not None:
        prior_sql, prior_state = prior.sql, plan_state(prior.plan)
    planned = plan_semantic_query(
        industry,
        question,
        value_filters=value_filters,
        prior_sql=prior_sql,
        pack=pack,
        prior_state=prior_state,
        resolved=resolution.trace(),
    )
    turn.plan, turn.path = planned.plan, planned.path
    if planned.path == "clarification":
        turn.outcome, turn.detail = "clarify", "planner_ambiguous"
        return turn
    if not planned.sql:
        turn.detail = "no_compiled_sql (would need the LLM)"
        return turn
    ok, reason = sql_is_safe(planned.sql)
    if ok:
        ok, reason = validate_sql_against_plan(planned.sql, planned.plan, allowed_schema=allowed)
    turn.sql = planned.sql
    if not ok:
        turn.detail = f"validation_rejected: {reason}"
        return turn
    turn.outcome = "sql"
    return turn


# ─────────────────────────────── grading ───────────────────────────────


def _period_patterns(start: str, end: str) -> list[str]:
    last = (date.fromisoformat(end) - timedelta(days=1)).isoformat()
    return [f"'{start}'", f"('{end}'|'{last}')"]


def grade(case: dict[str, Any], turn: Turn) -> tuple[str, list[str]]:
    """Return (verdict, failed checks). Verdicts: correct | wrong | clarification | failure."""
    expected = case.get("outcome", "sql")
    if expected == "clarify":
        if turn.outcome == "clarify":
            return "correct", []
        if turn.outcome == "sql":
            return "wrong", ["expected a clarification, got SQL"]
        return "failure", [turn.detail]
    if turn.outcome == "clarify":
        return "clarification", [turn.detail]
    if turn.outcome == "failure":
        return "failure", [turn.detail]

    sql = _normalise(turn.sql)
    failed: list[str] = []

    def need(pattern: str, label: str) -> None:
        if not _rx(pattern).search(sql):
            failed.append(label)

    for pattern in METRIC_PATTERNS.get(case.get("metric", ""), []):
        need(pattern, f"metric:{case['metric']}")
    for column, values in (case.get("filters") or {}).items():
        for value in values:
            literal = re.escape(str(value).lower().replace("'", "''"))
            need(
                rf"@{column}\s*(?:=|in\s*\()\s*(?:'[^']*'\s*,\s*)*'{literal}'",
                f"filter:{column}={value}",
            )
    for dim in case.get("group") or []:
        need(GROUP_PATTERNS[dim], f"group:{dim}")
    if year := case.get("year"):
        need(
            rf"extract\(year from @\w+\)(?:::int)? = {year}|'{year}-01-01'",
            f"period:year={year}",
        )
    if period := case.get("period"):
        for pattern in _period_patterns(*period):
            need(pattern, f"period:{period[0]}..{period[1]}")
    if order := case.get("order"):
        need(rf"order by [^;]*\b{order}\b", f"order:{order}")
    if limit := case.get("limit"):
        need(rf"\blimit {limit}\b", f"limit:{limit}")
    for pattern in case.get("must") or []:
        need(pattern, f"must:{pattern}")
    for pattern in case.get("must_not") or []:
        if _rx(pattern).search(sql):
            failed.append(f"must_not:{pattern}")
    return ("wrong" if failed else "correct"), failed


# ─────────────────────────── failure patterns ───────────────────────────


_WINDOW_CHECK = (
    "lag\\(",
    "partition by",
    "over\\s",
    'over"',
    "preceding",
    "<= ",
    "sum\\(.*\\) over",
)
_TIME_WORD = re.compile(
    r"(q[1-4]|h[12]|fy\S*|ytd|quarter|past|jan\w*|feb\w*|mar\w*|apr\w*|may|jun\w*|jul\w*|"
    r"aug\w*|sep\w*|oct\w*|nov\w*|dec\w*)"
)
_VALUE_WORD_HINT = {"black", "maharashtra", "karnataka", "red", "grey"}


def pattern_of(
    verdict: str, checks: list[str], unresolved: list[str], category: str = ""
) -> str | None:
    """Group a non-correct result under one root-cause pattern."""
    if verdict == "correct":
        return None
    text = " ".join(checks)
    if category == "followup" and verdict == "wrong":
        return "Follow-up lost or misapplied the previous turn's context"
    if verdict == "clarification":
        if unresolved:
            if any(_TIME_WORD.fullmatch(u) for u in unresolved):
                return "Time phrase rejected as an unknown name (Q1 / FY / H1 / month)"
            if any(u in _VALUE_WORD_HINT for u in unresolved):
                return "Value dictionary gap: colour family or state name not recognised"
            return "Business word rejected as an unknown name (vocabulary gap)"
        if "needs_clarification" in text:
            return "Question rejected as too vague (no value resolved)"
        return "Planner asked for clarification on an answerable question"
    if verdict == "failure":
        if "no_compiled_sql" in text:
            return "No governed SQL for the shape (running total, moving average, cross-fact ratio)"
        if "validation_rejected" in text:
            return "Template dropped a filter; validator blocked the query (safe failure)"
        return f"Pipeline failure ({text[:60]})"
    kinds = {c.split(":", 1)[0] for c in checks}
    musts = [c for c in checks if c.startswith("must:")]
    if (
        "period" in kinds
        or any("interval" in c or "date_trunc" in c for c in musts)
        or any(re.fullmatch(r"must:20\d\d", c) for c in musts)
    ):
        return "Time period not applied (year / quarter / FY / relative range)"
    if any(any(k in c for k in _WINDOW_CHECK) for c in musts) or any(
        "partition by" in c for c in checks
    ):
        return "Ranking / window logic wrong (partition, growth axis)"
    if any(c.startswith("filter:") for c in checks) or musts:
        return "Named value or business condition not filtered"
    if "must_not" in kinds or "group" in kinds:
        return "Wrong or extra grouping dimension"
    if "metric" in kinds:
        return "Wrong metric chosen"
    if "order" in kinds or "limit" in kinds:
        return "Ranking direction or Top-N limit wrong"
    return "Other wrong answer"


# ─────────────────────────────── runner ───────────────────────────────


def run(suite: Path = BENCHMARK) -> list[dict[str, Any]]:
    cases = yaml.safe_load(suite.read_text(encoding="utf-8"))["cases"]
    results: list[dict[str, Any]] = []
    for case in cases:
        industry = Industry(case["industry"])
        prior_turn = ask(industry, case["prior"]) if case.get("prior") else None
        try:
            turn = ask(industry, case["question"], prior_turn)
        except Exception as exc:  # a crash is a failure, not a harness error
            turn = Turn("failure", f"exception: {type(exc).__name__}: {exc}"[:160])
        verdict, checks = grade(case, turn)
        results.append(
            {
                "id": case["id"],
                "category": case["category"],
                "industry": case["industry"],
                "question": case["question"],
                "prior": case.get("prior"),
                "verdict": verdict,
                "checks_failed": checks,
                "pattern": pattern_of(verdict, checks, turn.unresolved, case["category"]),
                "turn": {k: v for k, v in asdict(turn).items() if k != "plan"},
            }
        )
    return results


def load_run(label: str) -> list[dict[str, Any]]:
    """A saved run with patterns re-derived, so older runs use the current taxonomy."""
    results = json.loads((RESULTS_DIR / f"{label}.json").read_text(encoding="utf-8"))
    for r in results:
        r["pattern"] = pattern_of(
            r["verdict"], r["checks_failed"], r["turn"].get("unresolved") or [], r["category"]
        )
    return results


def summarise(results: list[dict[str, Any]]) -> dict[str, Any]:
    verdicts = Counter(r["verdict"] for r in results)
    by_category: dict[str, Counter[str]] = defaultdict(Counter)
    for r in results:
        by_category[r["category"]][r["verdict"]] += 1
    patterns = Counter(r["pattern"] for r in results if r["pattern"])
    return {
        "total": len(results),
        "verdicts": dict(verdicts),
        "accuracy": round(100 * verdicts["correct"] / max(len(results), 1), 1),
        "by_category": {k: dict(v) for k, v in by_category.items()},
        "patterns": patterns.most_common(),
    }


CATEGORY_ORDER = [
    "aggregation",
    "trend",
    "ranking",
    "comparison",
    "time_intelligence",
    "geography",
    "vehicle_attributes",
    "insurance_metrics",
    "followup",
]


def render_report(
    label: str, results: list[dict[str, Any]], baseline: list[dict[str, Any]] | None
) -> str:
    s = summarise(results)
    v = s["verdicts"]
    lines = [
        "# NLQ Benchmark Report",
        "",
        f"Run: `{label}` · {s['total']} questions · "
        "generated by `tests/benchmark/run_benchmark.py`.",
        "",
        "Offline replay of the AI Chat pipeline (scope guard → value resolution → clarification "
        "gates → planner → SQL validation) with the value dictionary built from the seed data. "
        "SQL is graded against business expectations in `tests/benchmark/nlq_benchmark.yaml`; "
        "it is not executed. A question that would need the LLM counts as a failure.",
        "",
        "## Summary",
        "",
    ]
    if baseline:
        b = summarise(baseline)
        bv = b["verdicts"]
        lines += [
            "| | Baseline | Now |",
            "|---|---|---|",
            f"| Accuracy | {b['accuracy']}% | **{s['accuracy']}%** |",
        ]
        for key in ("correct", "wrong", "clarification", "failure"):
            lines.append(f"| {key.title()} | {bv.get(key, 0)} | {v.get(key, 0)} |")
    else:
        lines += [f"Accuracy **{s['accuracy']}%**", ""]
        lines += ["| Correct | Wrong | Clarification | Failure |", "|---|---|---|---|"]
        lines.append(
            " | ".join(
                str(v.get(k, 0)) for k in ("correct", "wrong", "clarification", "failure")
            ).join(["| ", " |"])
        )
    before_cats = summarise(baseline)["by_category"] if baseline else {}
    lines += [
        "",
        "## By category",
        "",
        "| Category | Total | Baseline correct | Correct | Wrong | Clarification | Failure |",
        "|---|---|---|---|---|---|---|",
    ]
    for cat in CATEGORY_ORDER:
        c = s["by_category"].get(cat, {})
        b = before_cats.get(cat, {})
        base = f"{b.get('correct', 0)}/{sum(b.values())}" if baseline else "-"
        lines.append(
            f"| {cat} | {sum(c.values())} | {base} | {c.get('correct', 0)} | "
            f"{c.get('wrong', 0)} | {c.get('clarification', 0)} | {c.get('failure', 0)} |"
        )
    if baseline:
        lines += [
            "",
            "## Baseline failure patterns (by frequency)",
            "",
            "| # | Pattern | Questions |",
            "|---|---|---|",
        ]
        for i, (pattern, count) in enumerate(summarise(baseline)["patterns"], 1):
            lines.append(f"| {i} | {pattern} | {count} |")
    lines += [
        "",
        "## Remaining failure patterns (by frequency)",
        "",
        "| # | Pattern | Questions |",
        "|---|---|---|",
    ]
    for i, (pattern, count) in enumerate(s["patterns"], 1):
        lines.append(f"| {i} | {pattern} | {count} |")
    lines += [
        "",
        "## Questions not answered correctly",
        "",
        "| ID | Question | Verdict | Why |",
        "|---|---|---|---|",
    ]
    for r in results:
        if r["verdict"] != "correct":
            why = "; ".join(r["checks_failed"])[:140].replace("|", "\\|")
            q = r["question"] if not r["prior"] else f"{r['prior']} → {r['question']}"
            lines.append(f"| {r['id']} | {q} | {r['verdict']} | {why} |")
    if baseline:
        before = {r["id"]: r["verdict"] for r in baseline}
        now = {r["id"]: r["verdict"] for r in results}
        fixed = [r for r in baseline if r["verdict"] != "correct" and now.get(r["id"]) == "correct"]
        regressed = [
            r for r in results if r["verdict"] != "correct" and before.get(r["id"]) == "correct"
        ]
        added = [r["id"] for r in results if r["id"] not in before]
        lines += [
            "",
            f"## Baseline misses: {len(fixed)} fixed, {len(regressed)} regressed",
            "",
            "| ID | Question | Pattern | Baseline | Now |",
            "|---|---|---|---|---|",
        ]
        for r in baseline:
            if r["verdict"] != "correct":
                q = r["question"] if not r["prior"] else f"{r['prior']} → {r['question']}"
                lines.append(
                    f"| {r['id']} | {q} | {r['pattern']} | {r['verdict']} | "
                    f"{now.get(r['id'], 'removed')} |"
                )
        for r in regressed:
            lines.append(f"- REGRESSED {r['id']}: {r['question']}")
        if added:
            lines += ["", f"Cases added after the baseline run: {', '.join(added)}."]
    return "\n".join(lines) + "\n"


def render_holdout(before: list[dict[str, Any]], after: list[dict[str, Any]]) -> str:
    """Hold-out suite: first run (unseen) and after fixing what it exposed."""
    b, a = summarise(before), summarise(after)
    lines = [
        "",
        "## Hold-out suite (`tests/benchmark/nlq_holdout.yaml`)",
        "",
        f"{a['total']} questions written after the fixes with different phrasing. The first "
        "run is the honest estimate on unseen questions; the misses it exposed were then "
        "fixed generically, so the second number is no longer an unseen score.",
        "",
        "| | First run (unseen) | After fixes |",
        "|---|---|---|",
        f"| Accuracy | {b['accuracy']}% | {a['accuracy']}% |",
    ]
    for key in ("correct", "wrong", "clarification", "failure"):
        lines.append(
            f"| {key.title()} | {b['verdicts'].get(key, 0)} | {a['verdicts'].get(key, 0)} |"
        )
    lines += ["", "| ID | Question | First run | Pattern |", "|---|---|---|---|"]
    for r in before:
        if r["verdict"] != "correct":
            lines.append(f"| {r['id']} | {r['question']} | {r['verdict']} | {r['pattern']} |")
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--label", default="latest")
    parser.add_argument("--suite", default=str(BENCHMARK), help="benchmark YAML to run")
    parser.add_argument("--compare", help="label of a saved run to compare against")
    parser.add_argument("--report", help="write a markdown report to this path")
    parser.add_argument(
        "--holdout", help="BEFORE,AFTER labels of saved hold-out runs to add to the report"
    )
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    results = run(Path(args.suite))
    RESULTS_DIR.mkdir(exist_ok=True)
    (RESULTS_DIR / f"{args.label}.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
    baseline = load_run(args.compare) if args.compare else None

    s = summarise(results)
    print(f"{s['total']} questions · accuracy {s['accuracy']}% · {s['verdicts']}")
    for cat in CATEGORY_ORDER:
        print(f"  {cat:20} {s['by_category'].get(cat, {})}")
    print("Failure patterns:")
    for pattern, count in s["patterns"]:
        print(f"  {count:3}  {pattern}")
    if args.verbose:
        for r in results:
            if r["verdict"] != "correct":
                why = "; ".join(r["checks_failed"])[:150]
                print(f"- {r['id']} [{r['verdict']}] {r['question']} :: {why}")
                if r["turn"]["sql"]:
                    print("     " + _normalise(r["turn"]["sql"])[:330])
    if args.report:
        report = render_report(args.label, results, baseline)
        if args.holdout:
            first, second = (load_run(label) for label in args.holdout.split(",", 1))
            report += render_holdout(first, second)
        Path(args.report).write_text(report, encoding="utf-8")
        print(f"Report written to {args.report}")


if __name__ == "__main__":
    main()
