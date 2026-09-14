"""Compatibility wrappers over question_understanding.

Prefer `understand_question` for new code. These helpers keep older call sites
and tests working while the chat path uses QuestionPlan end-to-end.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.core.config import Industry
from app.services.chat.question_understanding import understand_question


@dataclass(frozen=True, slots=True)
class EntityMatch:
    entity: str
    metric_hint: str | None
    synonyms_hit: list[str]
    ambiguity_options: list[str]


def match_entities(industry: Industry, question: str) -> EntityMatch | None:
    plan = understand_question(industry, question)
    if plan.entity == "unknown" and not plan.is_ambiguous:
        return None
    metric = None if plan.metric == "unknown" else plan.metric
    if plan.is_ambiguous and plan.entity == "vehicle":
        metric = None
    return EntityMatch(
        entity=plan.entity if plan.entity != "unknown" else "vehicle",
        metric_hint=metric,
        synonyms_hit=list(plan.glossary_hits),
        ambiguity_options=list(plan.ambiguity_options),
    )


def resolve_with_entity_match(industry: Industry, question: str) -> tuple[str | None, list[str]]:
    """Return (clarification_message_or_None, alternate_options)."""
    plan = understand_question(industry, question)
    if plan.is_ambiguous and plan.ambiguity_options:
        return (
            "Your question is ambiguous. Did you mean one of these?",
            list(plan.ambiguity_options),
        )
    return None, []
