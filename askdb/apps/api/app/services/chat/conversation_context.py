"""Carry metric, filters, and grain from the previous turn into a follow-up."""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any

from app.core.config import Industry
from app.services.chat.intents import is_followup
from app.services.chat.question_understanding import ExtractedFilter, QuestionPlan

_LAST_YEAR = re.compile(r"\b(last|previous|prior)\s+year\b", re.I)
_COMPARE_YEAR = re.compile(r"\bcompare\b[\s\S]{0,40}\b(previous|last|prior)\s+year\b", re.I)


def is_contextual_followup(question: str) -> bool:
    """True when the utterance should modify the previous plan instead of starting over."""
    if is_followup(question):
        return True
    text = (question or "").lower()
    return bool(_LAST_YEAR.search(text) or _COMPARE_YEAR.search(text))


def plan_state(plan: QuestionPlan) -> dict[str, Any]:
    return {
        "metric": plan.metric,
        "entity": plan.entity,
        "intent": plan.intent,
        "dimensions": list(plan.dimensions),
        "timeGrain": plan.time_grain,
        "analysis": plan.analysis,
        "yearFilter": plan.year_filter,
        "filters": [
            {
                "column": item.column,
                "operator": item.operator,
                "value": item.value,
                "label": item.label,
            }
            for item in plan.filters
        ],
    }


def state_to_plan(industry: Industry, state: dict[str, Any]) -> QuestionPlan:
    filters = [
        ExtractedFilter(
            column=str(item["column"]),
            operator=str(item.get("operator") or "="),
            value=str(item["value"]),
            label=str(item.get("label") or item["value"]),
        )
        for item in (state.get("filters") or [])
        if item.get("column") and item.get("value")
    ]
    return QuestionPlan(
        industry=industry,
        intent=state.get("intent") or "aggregation",
        entity=state.get("entity") or "metric_only",
        metric=state.get("metric") or "revenue",
        filters=filters,
        dimensions=list(state.get("dimensions") or []),
        time_grain=state.get("timeGrain"),
        analysis=state.get("analysis") or "breakdown",
        year_filter=state.get("yearFilter"),
        glossary_hits=["prior turn"],
    )


def apply_followup(prior: QuestionPlan, question: str) -> QuestionPlan:
    """Keep the previous metric and grain, then apply the new constraint."""
    text = (question or "").lower()
    plan = state_to_plan(prior.industry, plan_state(prior))
    plan.notes.append("Continued from the previous question.")

    if "mumbai" in text:
        city = ExtractedFilter(
            column="automotive.dim_region.city",
            operator="=",
            value="Mumbai",
            label="City = Mumbai",
        )
        if not any(item.column == city.column and item.value == city.value for item in plan.filters):
            plan.filters.append(city)

    if _COMPARE_YEAR.search(text):
        plan.analysis = "period_growth"
        plan.intent = "comparison"
        plan.time_grain = "year"
        plan.year_filter = None
        if "year" not in plan.dimensions:
            plan.dimensions = ["year", *plan.dimensions]
        return plan

    if _LAST_YEAR.search(text):
        plan.year_filter = datetime.now().year - 1
        plan.time_grain = plan.time_grain or "year"
        if "year" not in plan.dimensions:
            plan.dimensions = ["year", *plan.dimensions]
    return plan
