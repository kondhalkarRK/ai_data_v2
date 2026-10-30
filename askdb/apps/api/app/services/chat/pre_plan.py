"""Shared pre-plan path for ChatService and the routing eval harness.

Order: region guard -> rule classifier (early, before any schema load) ->
general-knowledge probe (needs the value dictionary) -> memory expiry ->
scope revalidation -> follow-up guard -> plan_turn.
"""

from __future__ import annotations

import re
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Literal

from app.core.config import Industry, Settings
from app.services.chat.conversation_context import is_contextual_followup
from app.services.chat.conversation_memory import (
    AnalyticalContext,
    SessionMemory,
    empty_memory,
    follow_up_context_status,
    plan_state_from_memory,
    revalidate_prior_state_for_scope,
    revalidate_stored_plan_for_scope,
)
from app.services.chat.intents import is_out_of_bounds
from app.services.chat.message_classifier import (
    MessageClassification,
    MessageRoute,
    classify_message,
)
from app.services.security.region_scope import RegionScope, forbidden_zones

PrePlanStop = Literal[
    "region_forbidden",
    "legacy_out_of_bounds",
    "general_chat",
    "unsupported",
    "out_of_scope_live",
    "app_help",
    "document_query",
    "general_knowledge",
    "memory_expired",
    "scope_denied",
]

_ROUTE_STOP: dict[MessageRoute, PrePlanStop] = {
    MessageRoute.GENERAL_CHAT: "general_chat",
    MessageRoute.UNSUPPORTED: "unsupported",
    MessageRoute.OUT_OF_SCOPE_LIVE: "out_of_scope_live",
    MessageRoute.APP_HELP: "app_help",
    MessageRoute.DOCUMENT_QUERY: "document_query",
    MessageRoute.GENERAL_KNOWLEDGE: "general_knowledge",
}


@dataclass(slots=True)
class PrePlanOutcome:
    proceed: bool
    stop: PrePlanStop | None = None
    stop_detail: str = ""
    question: str = ""
    prior_state: dict[str, Any] | None = None
    classification: MessageClassification | None = None
    follow_up_guard_blocked: bool = False
    interpretation: str | None = None


def region_guard(message: str, scope: RegionScope) -> tuple[str, str] | None:
    blocked = forbidden_zones(message, scope)
    if blocked:
        return "region_forbidden", f"blocked zones: {', '.join(blocked)}"
    return None


def early_route(
    *,
    industry: Industry,
    message: str,
    scope: RegionScope,
    router_enabled: bool,
) -> PrePlanOutcome | None:
    """Region guard and rule classifier. Needs no schema, pack or value dictionary."""
    question = message.strip()
    guard = region_guard(question, scope)
    if guard is not None:
        return PrePlanOutcome(
            proceed=False, stop="region_forbidden", stop_detail=guard[1], question=question
        )
    if not router_enabled and is_out_of_bounds(question, industry):
        return PrePlanOutcome(
            proceed=False,
            stop="legacy_out_of_bounds",
            stop_detail="intents.is_out_of_bounds",
            question=question,
        )
    classification = classify_message(question, industry, enabled=router_enabled)
    if classification.applied and classification.route in _ROUTE_STOP:
        return PrePlanOutcome(
            proceed=False,
            stop=_ROUTE_STOP[classification.route],
            stop_detail=classification.reason,
            question=question,
            classification=classification,
        )
    return None


def run_pre_plan(
    *,
    industry: Industry,
    message: str,
    settings: Settings,
    scope: RegionScope,
    session_memory: SessionMemory,
    prior_state: dict[str, Any] | None,
    router_enabled: bool,
    data_vocabulary: Callable[[str], bool] | None = None,
    follow_up_guard_check: Callable[..., tuple[bool, str | None]] | None = None,
    skip_early: bool = False,
) -> PrePlanOutcome:
    """Everything ChatService does before plan_turn, in the same order."""
    question = message.strip()
    if not skip_early:
        early = early_route(
            industry=industry, message=question, scope=scope, router_enabled=router_enabled
        )
        if early is not None:
            return early

    classification: MessageClassification | None = None
    if router_enabled and data_vocabulary is not None:
        classification = classify_message(
            question, industry, enabled=True, data_vocabulary=data_vocabulary
        )
        if classification.route is MessageRoute.GENERAL_KNOWLEDGE:
            return PrePlanOutcome(
                proceed=False,
                stop="general_knowledge",
                stop_detail=classification.reason,
                question=question,
                classification=classification,
            )

    follow_status = follow_up_context_status(
        session_memory, question, settings, industry=industry
    )
    if follow_status == "expired" and is_contextual_followup(question):
        return PrePlanOutcome(
            proceed=False,
            stop="memory_expired",
            stop_detail="analytical context expired",
            question=question,
            classification=classification,
        )

    effective_prior = prior_state
    if follow_status == "active":
        ok, reason = revalidate_stored_plan_for_scope(session_memory, industry, question, scope)
        if not ok:
            return PrePlanOutcome(
                proceed=False,
                stop="scope_denied",
                stop_detail=reason or "region scope",
                question=question,
                classification=classification,
            )
        effective_prior = plan_state_from_memory(session_memory)
    elif not session_memory.analytical and prior_state and is_contextual_followup(question):
        ok, reason = revalidate_prior_state_for_scope(industry, prior_state, question, scope)
        if not ok:
            return PrePlanOutcome(
                proceed=False,
                stop="scope_denied",
                stop_detail=reason or "region scope",
                question=question,
                classification=classification,
            )

    interpretation: str | None = None
    if follow_up_guard_check is not None and effective_prior:
        allowed, interpretation = follow_up_guard_check(
            question=question,
            session_memory=session_memory,
            prior_state=effective_prior,
        )
        if not allowed:
            return PrePlanOutcome(
                proceed=False,
                stop_detail="follow_up_guard",
                question=question,
                classification=classification,
                follow_up_guard_blocked=True,
            )

    return PrePlanOutcome(
        proceed=True,
        question=question,
        prior_state=effective_prior,
        classification=classification,
        interpretation=interpretation,
    )


_QUESTION_WORDS = re.compile(
    r"^\s*(?:why\s+(?:did|does|is|are|was|were|has|have)|explain(?:\s+why)?|"
    r"what\s+drove(?:\s+the)?|what\s+caused(?:\s+the)?)\s+",
    re.I,
)
_COMPOUND = re.compile(
    r"^\s*(?:explain|define|what\s+is)\s+(?P<term>[\w\s-]{2,40}?)\s+and\s+(?P<rest>(?:show|list|give|plot|chart)\b.+)$",
    re.I,
)


def strip_question_words(question: str) -> str | None:
    """Drop a leading "why did / explain / what drove" so the gate sees only data words."""
    stripped = _QUESTION_WORDS.sub("", question or "", count=1).strip()
    if not stripped or stripped == (question or "").strip():
        return None
    return stripped


def split_compound(question: str) -> tuple[str, str] | None:
    """"Explain churn and show it for last quarter" -> ("churn", "show churn for last quarter")."""
    match = _COMPOUND.match(question or "")
    if match is None:
        return None
    term = match.group("term").strip()
    rest = re.sub(r"\b(it|them|that)\b", term, match.group("rest"), count=1, flags=re.I)
    return term, rest.strip()


@dataclass(slots=True)
class PlannedTurn:
    turn: Any
    planned_question: str
    definition_term: str | None = None


def plan_with_rewrites(plan: Callable[[str], Any], question: str, *, enabled: bool) -> PlannedTurn:
    """plan_turn on the original text first; rewrites are only tried when it would clarify.

    Compound "explain X and show ..." plans the data half and returns X for a separate,
    metadata-only definition. A leading "why/explain/what drove" is retried without it.
    """
    term: str | None = None
    if enabled:
        compound = split_compound(question)
        if compound is not None:
            term, data_part = compound
            turn = plan(data_part)
            if turn.clarification is None:
                return PlannedTurn(turn, data_part, definition_term=term)
    turn = plan(question)
    if not enabled or turn.clarification is None:
        return PlannedTurn(turn, question, definition_term=term)
    stripped = strip_question_words(question)
    if stripped:
        retry = plan(stripped)
        if retry.clarification is None and retry.governed_sql:
            return PlannedTurn(retry, stripped)
    return PlannedTurn(turn, question, definition_term=term)


def synthetic_memory(*, prior_state: dict[str, Any] | None) -> SessionMemory:
    mem = empty_memory(user_id=uuid.uuid4(), conversation_id=uuid.uuid4())
    if prior_state:
        mem.analytical = AnalyticalContext.from_dict(
            {
                "previousIntent": prior_state.get("intent", "aggregation"),
                "previousQuestion": "",
                "metrics": [prior_state.get("metric", "unknown")],
                "dimensions": list(prior_state.get("dimensions") or []),
                "dateRange": None,
                "timeGrain": prior_state.get("timeGrain"),
                "filters": prior_state.get("filters") or [],
                "validatedPlan": prior_state,
                "resultMeta": {"rowCount": 0, "columnNames": []},
                "turnCounter": 0,
                "updatedAt": datetime.now(UTC).isoformat(),
            }
        )
    return mem
