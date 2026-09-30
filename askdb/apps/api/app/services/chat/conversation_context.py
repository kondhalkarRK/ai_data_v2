"""Carry metric, filters, and grain from the previous turn into a follow-up."""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any

from app.core.config import Industry
from app.services.chat.intents import is_followup
from app.services.chat.question_understanding import (
    FILTER_DIMENSION,
    ExtractedFilter,
    QuestionPlan,
    understand_question,
)
from app.services.chat.time_periods import Period, parse_period

_LAST_YEAR = re.compile(r"\b(last|previous|prior)\s+year\b", re.I)
_COMPARE_YEAR = re.compile(r"\bcompare\b[\s\S]{0,40}\b(previous|last|prior)\s+year\b", re.I)
_YEAR = re.compile(r"\b(20[12]\d)\b")
# "Add Tata" / "also Kia" widens the named values instead of replacing them.
_ADD_VALUES = re.compile(r"^\s*(?:and\s+)?(?:add|also|include|plus|along\s+with)\b|\balso\b", re.I)
_METRIC_WORDS = re.compile(
    r"\b(units?|volume|quantity|revenue|value|turnover|orders?|asp|average\s+selling\s+price|"
    r"premium|gwp|claims?|loss\s+ratio|severity|frequency|approval|renewal|incurred|paid)\b",
    re.I,
)
_TIME_DIMS = ("month", "quarter", "year")
_SCOPE_ONLY = re.compile(
    r"^(?:for|in|during|over|within|from|since|only|just|excluding|without|by|per|"
    r"top|bottom|lowest|highest)\b"
)
_RANKING = re.compile(r"\b(top|bottom|lowest|highest|best|worst|least)\b", re.I)
_TOP_N = re.compile(r"\b(?:top|bottom|first|last)\s+(\d{1,3})\b", re.I)


def is_contextual_followup(question: str) -> bool:
    """True when the utterance should modify the previous plan instead of starting over."""
    if is_followup(question):
        return True
    text = (question or "").lower().strip(" ?.!")
    if _LAST_YEAR.search(text) or _COMPARE_YEAR.search(text):
        return True
    # A bare scope or period with no metric ("for 2024", "in Q1", "by quarter", "bottom 5").
    if len(text.split()) <= 6 and not _METRIC_WORDS.search(text):
        if _SCOPE_ONLY.match(text) or _YEAR.fullmatch(text):
            return True
        return len(text.split()) <= 4 and parse_period(text) is not None
    return False


def plan_state(plan: QuestionPlan) -> dict[str, Any]:
    return {
        "metric": plan.metric,
        "entity": plan.entity,
        "intent": plan.intent,
        "dimensions": list(plan.dimensions),
        "timeGrain": plan.time_grain,
        "analysis": plan.analysis,
        "yearFilter": plan.year_filter,
        "period": plan.period.to_state() if plan.period else None,
        "limit": plan.limit,
        "orderDirection": plan.order_direction,
        "partitionBy": list(plan.partition_by),
        "aggregation": plan.aggregation,
        "filters": [
            {
                "column": item.column,
                "operator": item.operator,
                "value": item.value,
                "values": list(item.values),
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
            values=tuple(str(value) for value in (item.get("values") or [])),
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
        period=Period.from_state(state.get("period")),
        limit=int(state.get("limit") or 10),
        order_direction=state.get("orderDirection") or "desc",
        partition_by=list(state.get("partitionBy") or []),
        aggregation=state.get("aggregation") or "sum",
        glossary_hits=["prior turn"],
    )


def _widen(existing: ExtractedFilter, extra: ExtractedFilter) -> ExtractedFilter:
    values = tuple(dict.fromkeys((*existing.all_values, *extra.all_values)))
    domain = existing.label.split(" = ", 1)[0].split(" in (", 1)[0]
    return ExtractedFilter(
        column=existing.column,
        operator="IN",
        value=values[0],
        label=f"{domain} in ({', '.join(values)})",
        source=extra.source,
        values=values,
        match_type=extra.match_type,
        matched_text=extra.matched_text,
        confidence=min(existing.confidence, extra.confidence),
    )


def apply_followup(
    prior: QuestionPlan,
    question: str,
    *,
    value_filters: list[ExtractedFilter] | None = None,
) -> QuestionPlan:
    """Keep the previous metric, scope and grain, then apply the new constraint."""
    text = (question or "").lower()
    plan = state_to_plan(prior.industry, plan_state(prior))
    plan.notes.append("Continued from the previous question.")
    # Read the follow-up on its own for the parts it names (metric, grain, period).
    reading = understand_question(prior.industry, question, value_filters=value_filters)

    extra = list(value_filters or [])
    if not extra and "mumbai" in text:
        extra.append(
            ExtractedFilter(
                column="automotive.dim_region.city",
                operator="=",
                value="Mumbai",
                label="City = Mumbai",
            )
        )
    widen = bool(_ADD_VALUES.search(text))
    for filt in extra:
        existing = next((item for item in plan.filters if item.column == filt.column), None)
        plan.filters = [item for item in plan.filters if item.column != filt.column]
        # A newly named value replaces the previous value of the same column
        # ("what about Pune?" after a Mumbai question) unless the user adds it.
        plan.filters.append(_widen(existing, filt) if widen and existing else filt)
    for filt in plan.filters:
        key = FILTER_DIMENSION.get(filt.column.rsplit(".", 1)[-1])
        if len(filt.all_values) > 1 and key and key not in plan.dimensions:
            plan.dimensions.append(key)

    if _METRIC_WORDS.search(text) and reading.metric not in {"unknown", plan.metric}:
        plan.metric = reading.metric
        plan.aggregation = reading.aggregation

    asked = [d for d in reading.dimensions if d != reading.default_dimension]
    new_time = [d for d in asked if d in _TIME_DIMS]
    if new_time:
        plan.dimensions = [d for d in plan.dimensions if d not in _TIME_DIMS]
        plan.dimensions = [*plan.dimensions, new_time[0]] if plan.dimensions else [new_time[0]]
    for dimension in asked:
        if dimension not in _TIME_DIMS and dimension not in plan.dimensions:
            plan.dimensions.append(dimension)
    if plan.analysis == "basic" and plan.dimensions:
        plan.analysis = "breakdown"
    if _RANKING.search(text) and plan.dimensions:
        plan.order_direction = reading.order_direction
        if plan.intent != "ranking" and plan.analysis in {"basic", "breakdown", "ranking"}:
            plan.intent, plan.analysis = "ranking", "ranking"
        if top_n := _TOP_N.search(text):
            plan.limit = int(top_n.group(1))

    if _COMPARE_YEAR.search(text):
        plan.analysis = "period_growth"
        plan.intent = "comparison"
        plan.time_grain = "year"
        plan.year_filter = None
        plan.period = None
        if "year" not in plan.dimensions:
            plan.dimensions = ["year", *plan.dimensions]
        return plan

    period = parse_period(question)
    years = sorted({int(year) for year in _YEAR.findall(text)})
    if period is not None and not years and not period.relative and prior.year_filter:
        # "in Q1" after a 2024 answer means Q1 2024.
        period = parse_period(f"{question} {prior.year_filter}") or period
    if period is not None:
        plan.period, plan.year_filter = period, None
    elif len(years) == 1:
        plan.year_filter, plan.period = years[0], None
    elif _LAST_YEAR.search(text):
        plan.year_filter, plan.period = datetime.now().year - 1, None
        if "year" not in plan.dimensions:
            plan.dimensions = ["year", *plan.dimensions]
    plan.time_grain = next((g for g in _TIME_DIMS if g in plan.dimensions), None)
    return plan
