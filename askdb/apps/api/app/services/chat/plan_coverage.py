"""Check that a QuestionPlan and generated SQL still reflect the user's question.

This is a lightweight intent-preservation layer on top of existing planning and
``validate_sql_against_plan`` — it does not replace SQL safety or schema checks.
"""

from __future__ import annotations

import re

from app.services.chat.question_understanding import QuestionPlan

_STABLE_WORDS = re.compile(
    r"\b(stable|steady|flat|unchanged|consistent|holding\s+steady)\b", re.I
)
_DECLINING = re.compile(r"\b(declin\w*|decreas\w*|falling|dropping|shrinking)\b", re.I)
_GROWING = re.compile(r"\b(increas\w*|growing|rising|improving)\b", re.I)
_BY_MONTH = re.compile(r"\bby\s+month\b|\bmonthly\b|\bper\s+month\b", re.I)
_MODELS = re.compile(r"\bmodels?\b", re.I)
_VEHICLE_LIST = re.compile(
    r"\b(?:which|what)\s+(?:all\s+)?(?:the\s+)?(?:car|cars|vehicle|vehicles|model|models)\b|"
    r"\b(?:car|cars)\s+(?:has|have|with)\b",
    re.I,
)
_METRIC_ALIASES: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\bunits?\b|\bvolume\b", re.I), "units"),
    (re.compile(r"\baverage\s+selling\s+price\b|\basp\b", re.I), "average_selling_price"),
    (re.compile(r"\brevenue\b|\bsales\s+value\b", re.I), "revenue"),
    (re.compile(r"\borders?\b", re.I), "orders"),
    (re.compile(r"\bpremium\b|\bgwp\b", re.I), "premium"),
    (re.compile(r"\bclaims?\s+incurred\b", re.I), "claims_incurred"),
)


def _mentioned_metrics(question: str) -> set[str]:
    found: set[str] = set()
    for pattern, key in _METRIC_ALIASES:
        if pattern.search(question):
            found.add(key)
    return found


def coverage_gaps(question: str, plan: QuestionPlan) -> list[str]:
    """Human-readable gaps between the question and the structured plan."""
    gaps: list[str] = []
    q = question or ""
    metrics = _mentioned_metrics(q)

    if _MODELS.search(q) and "model" not in plan.dimensions and plan.entity != "vehicle":
        if plan.analysis != "divergence" or "model" not in plan.dimensions:
            gaps.append("Question asks about models but the plan has no model grouping.")

    if _VEHICLE_LIST.search(q) and not _BY_MONTH.search(q):
        if plan.intent != "lookup":
            gaps.append(
                "Question asks which cars match criteria but the plan is not a vehicle lookup."
            )
        elif plan.time_grain or any(d in plan.dimensions for d in ("month", "quarter", "year")):
            gaps.append("Vehicle list questions should not include a time breakdown.")

    if _BY_MONTH.search(q) and not any(d in plan.dimensions for d in ("month", "quarter", "year")):
        if plan.time_grain not in {"month", "quarter", "half", "year"}:
            gaps.append("Question asks for a monthly (time) breakdown but no time grain is planned.")

    if len(metrics) >= 2:
        planned_metrics = {m for m, _ in plan.divergence} if plan.divergence else {plan.metric}
        planned_metrics.discard("unknown")
        missing = metrics - planned_metrics
        if missing and plan.analysis != "divergence":
            gaps.append(
                "Question mentions multiple metrics "
                f"({', '.join(sorted(metrics))}) but the plan only targets {plan.metric}."
            )
        elif missing and plan.analysis == "divergence":
            missing_div = metrics - {m for m, _ in plan.divergence}
            if missing_div:
                gaps.append(
                    "Divergence plan is missing metrics: " + ", ".join(sorted(missing_div)) + "."
                )

    if _DECLINING.search(q) and _STABLE_WORDS.search(q):
        if plan.analysis != "divergence":
            gaps.append(
                "Question contrasts a declining metric with a stable metric but analysis is not divergence."
            )
        else:
            dirs = {direction for _, direction in plan.divergence}
            if "down" not in dirs:
                gaps.append("Question implies a declining metric but no metric is marked down.")
            if "flat" not in dirs:
                gaps.append(
                    "Question implies a stable metric; stable trends use a documented ±5% band."
                )

    return gaps


def sql_covers_plan_metrics(plan: QuestionPlan, sql: str) -> tuple[bool, str | None]:
    """Ensure multi-metric plans appear in SQL (syntax match only)."""
    if not sql:
        return False, "Empty SQL"
    lowered = sql.lower()
    if plan.analysis == "divergence" and plan.divergence:
        for metric, _direction in plan.divergence:
            token = metric.replace("_", "")
            if metric not in lowered and token not in lowered.replace("_", ""):
                return False, f"SQL does not reference metric '{metric}' required by divergence plan."
        return True, None
    return True, None
