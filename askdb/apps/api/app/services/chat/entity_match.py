"""Semantic entity / synonym matching to reduce LLM dependency."""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.core.config import Industry


@dataclass(frozen=True, slots=True)
class EntityMatch:
    entity: str
    metric_hint: str | None
    synonyms_hit: list[str]
    ambiguity_options: list[str]


_VEHICLE = re.compile(
    r"\b(car|cars|vehicle|vehicles|model|models|automobile|automobiles|carline)\b",
    re.IGNORECASE,
)
_TOP = re.compile(r"\b(top|best|highest|leading|most)\b", re.IGNORECASE)
_REVENUE = re.compile(r"\b(revenue|sales\s+value|dollar|amount)\b", re.IGNORECASE)
_REGION = re.compile(r"\b(region|regions|geo|geography|market)\b", re.IGNORECASE)


def match_entities(industry: Industry, question: str) -> EntityMatch | None:
    q = question or ""
    if industry is Industry.AUTOMOTIVE and _VEHICLE.search(q) and _TOP.search(q):
        hits = [m.group(0).lower() for m in _VEHICLE.finditer(q)]
        options = [
            "Top selling car by units",
            "Top selling car by revenue",
            "Top selling car by region",
        ]
        if _REVENUE.search(q):
            return EntityMatch("vehicle", "revenue", hits, [])
        if _REGION.search(q):
            return EntityMatch("vehicle", "region", hits, [])
        # Explicit unit/volume wording resolves; bare "top selling car" is ambiguous.
        if re.search(r"\b(unit|units|volume|qty|quantity)\b", q, re.I):
            return EntityMatch("vehicle", "units", hits, [])
        # Bare "top/best selling car|vehicle|model" needs metric clarification.
        if re.search(
            r"(top|best|highest)\s+selling\s+(car|cars|vehicle|vehicles|model|models)\b",
            q,
            re.I,
        ):
            return EntityMatch("vehicle", None, hits, options)
        return EntityMatch("vehicle", "units", hits, [])

    if industry is Industry.INSURANCE:
        if re.search(r"\bloss\s*ratio\b", q, re.I):
            return EntityMatch("loss_ratio", "loss_ratio", ["loss ratio"], [])
        if re.search(r"\b(claim|claims)\b", q, re.I) and re.search(r"\b(status|count|volume)\b", q, re.I):
            return EntityMatch("claims", "claim_count", ["claims"], [])
    return None


def resolve_with_entity_match(industry: Industry, question: str) -> tuple[str | None, list[str]]:
    """Return (clarification_message_or_None, alternate_options)."""
    match = match_entities(industry, question)
    if match is None:
        return None, []
    if match.ambiguity_options and match.metric_hint is None:
        return (
            "Your question is ambiguous. Did you mean one of these?",
            match.ambiguity_options,
        )
    return None, []
