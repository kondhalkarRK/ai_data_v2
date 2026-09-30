"""One planning pass, shared by the chat service and the benchmark.

Spell correction -> query rewrite -> semantic resolver (values, glossary,
aliases) -> entity resolution -> intent -> planner -> governed SQL -> plan
validation. Pure: no database or LLM calls, so the benchmark measures exactly
what the chat service does before execution.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from app.core.config import Industry
from app.services.chat.clarification import Clarification, assess_resolution, plan_suggestions
from app.services.chat.conversation_context import is_contextual_followup
from app.services.chat.entity_resolver import Resolution
from app.services.chat.intents import needs_clarification
from app.services.chat.question_understanding import QuestionPlan, understand_question
from app.services.chat.semantic_context import validate_sql_against_plan
from app.services.chat.semantic_query_planner import (
    SemanticQuery,
    plan_semantic_query,
    rewrite_question,
)
from app.services.chat.spell import correct_question
from app.services.chat.value_dictionary import ValueDictionarySnapshot, resolver_for

ClarifyReason = Literal[
    "needs_clarification", "ambiguous", "unsupported", "unresolved", "planner_ambiguous"
]


@dataclass(slots=True)
class TurnPlan:
    original: str
    question: str
    corrections: list[tuple[str, str]] = field(default_factory=list)
    resolution: Resolution = field(default_factory=Resolution)
    plan: QuestionPlan | None = None
    planned: SemanticQuery | None = None
    clarification: Clarification | None = None
    clarify_reason: ClarifyReason | None = None
    contextual: bool = False
    governed_sql: str | None = None
    validation_error: str | None = None

    @property
    def spelling_notes(self) -> list[str]:
        return [f"Read \u201c{wrong}\u201d as \u201c{right}\u201d." for wrong, right in self.corrections]


def plan_turn(
    industry: Industry,
    question: str,
    *,
    snapshot: ValueDictionarySnapshot,
    pack: Any | None,
    allowed_schema: dict[str, set[str]] | None,
    prior_sql: str | None = None,
    prior_state: dict[str, Any] | None = None,
    surprise_sql: tuple[str, str, int] | None = None,
) -> TurnPlan:
    resolver = resolver_for(snapshot, pack)
    spelled = correct_question(question, protected=resolver.protected_words())
    text = spelled.text
    turn = TurnPlan(original=question, question=text, corrections=spelled.corrections)
    followup_words = is_contextual_followup(text)
    has_prior = bool(prior_state or prior_sql)
    turn.contextual = has_prior and followup_words

    turn.resolution = snapshot.resolve(text, pack=pack)
    value_filters = turn.resolution.filters()
    if not turn.resolution.matches and not turn.contextual:
        message = needs_clarification(text)
        if message is not None:
            turn.clarify_reason = "needs_clarification"
            turn.clarification = Clarification(
                kind="clarify",
                title="What should I analyze?",
                message=message,
                options=plan_suggestions(None, industry=industry, question=text),
            )
            return turn

    plan = understand_question(industry, rewrite_question(text), value_filters=value_filters)
    turn.plan = plan
    if plan.is_ambiguous and plan.ambiguity_options and not turn.contextual:
        turn.clarify_reason = "ambiguous"
        turn.clarification = _ambiguity(plan)
        return turn

    if not followup_words:
        gate = assess_resolution(
            text,
            plan,
            turn.resolution,
            industry=industry,
            brands=resolver.canonical_values("make"),
        )
        if gate is not None:
            turn.clarify_reason = "unsupported" if gate.kind == "unsupported" else "unresolved"
            turn.clarification = gate
            return turn

    planned = plan_semantic_query(
        industry,
        text,
        value_filters=value_filters,
        prior_sql=prior_sql if turn.contextual else None,
        pack=pack,
        surprise_sql=surprise_sql,
        prior_state=prior_state if turn.contextual else None,
        resolved=turn.resolution.trace(),
    )
    turn.planned = planned
    turn.plan = planned.plan
    if planned.path == "clarification":
        turn.clarify_reason = "planner_ambiguous"
        turn.clarification = _ambiguity(planned.plan)
        return turn
    if planned.sql:
        if surprise_sql is not None:
            turn.governed_sql = planned.sql
        else:
            ok, reason = validate_sql_against_plan(
                planned.sql, planned.plan, allowed_schema=allowed_schema
            )
            if ok:
                turn.governed_sql = planned.sql
            else:
                turn.validation_error = reason or "SQL did not match the question plan"
    return turn


def _ambiguity(plan: QuestionPlan) -> Clarification:
    message = (plan.notes[0] if plan.notes else "This question can be read several ways.")
    return Clarification(
        kind="clarify",
        title="Did you mean\u2026",
        message=f"{message} Did you mean one of these?",
        options=list(plan.ambiguity_options),
    )
