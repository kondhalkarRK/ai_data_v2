"""Compact per-conversation memory: analytical context, general chat, pending clarification.

Persisted on ``conversations.session_memory`` (JSONB), keyed by **user_id + conversation_id**
on the ``conversations`` row. There is no in-process or cross-user cache.

**Before migration 0010** (column missing): load/save no-op with ``session_memory_persisted=False``
on the service for that request. Each HTTP request starts with empty memory; analytical expiry,
pending clarification, and cross-turn context are **not** retained (fail closed). Follow-ups may
still use ``QueryHistory.trust_breakdown.queryState`` when present. Multi-worker behaviour matches
single-worker: nothing is shared except what is committed on ``conversations`` / ``query_history``.

Does not store raw SQL or result rows in memory.
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Literal

from app.core.config import Industry, Settings
from app.services.chat.conversation_context import (
    is_contextual_followup,
    plan_state,
    state_to_plan,
)
from app.services.chat.intents import is_followup
from app.services.chat.message_classifier import rule_route_interrupts_analytical_context
from app.services.chat.question_understanding import QuestionPlan
from app.services.security.region_scope import RegionScope, forbidden_zones

MEMORY_VERSION = 1

# Explicit refresh cues only — bare "latest" (e.g. "latest quarter") is not a cache bypass.
_REFRESH = re.compile(
    r"\b("
    r"refresh(?:\s+(?:that|this|it|the(?:\s+(?:data|numbers|query|report))?)?"
    r"|(?:\s+the\s+)?(?:data|numbers))?"
    r"|reload(?:\s+(?:that|this|it))?"
    r"|re-?run(?:\s+(?:that|this|it))?"
    r"|fresh\s+data"
    r"|update\s+the\s+numbers"
    r")\b",
    re.I,
)

_NON_DATA_PENDING = re.compile(
    r"\b(weather|forecast\s+temperature|who\s+won|bitcoin|cricket\s+match|"
    r"tell\s+me\s+a\s+joke|ignore\s+(?:all\s+)?(?:previous|prior)\s+instructions)\b",
    re.I,
)


@dataclass(slots=True)
class ResultMeta:
    row_count: int = 0
    column_names: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {"rowCount": self.row_count, "columnNames": list(self.column_names)}

    @classmethod
    def from_dict(cls, raw: dict[str, Any] | None) -> ResultMeta:
        if not raw:
            return cls()
        return cls(
            row_count=int(raw.get("rowCount") or 0),
            column_names=tuple(str(c) for c in (raw.get("columnNames") or [])),
        )


@dataclass(slots=True)
class AnalyticalContext:
    previous_intent: str
    previous_question: str
    metrics: tuple[str, ...]
    dimensions: tuple[str, ...]
    date_range: str | None
    time_grain: str | None
    filters: tuple[dict[str, Any], ...]
    validated_plan: dict[str, Any]
    result_meta: ResultMeta
    turn_counter: int = 0
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def to_dict(self) -> dict[str, Any]:
        return {
            "previousIntent": self.previous_intent,
            "previousQuestion": self.previous_question,
            "metrics": list(self.metrics),
            "dimensions": list(self.dimensions),
            "dateRange": self.date_range,
            "timeGrain": self.time_grain,
            "filters": list(self.filters),
            "validatedPlan": self.validated_plan,
            "resultMeta": self.result_meta.to_dict(),
            "turnCounter": self.turn_counter,
            "updatedAt": self.updated_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> AnalyticalContext:
        return cls(
            previous_intent=str(raw.get("previousIntent") or "aggregation"),
            previous_question=str(raw.get("previousQuestion") or ""),
            metrics=tuple(str(m) for m in (raw.get("metrics") or [])),
            dimensions=tuple(str(d) for d in (raw.get("dimensions") or [])),
            date_range=raw.get("dateRange"),
            time_grain=raw.get("timeGrain"),
            filters=tuple(dict(item) for item in (raw.get("filters") or [])),
            validated_plan=dict(raw.get("validatedPlan") or {}),
            result_meta=ResultMeta.from_dict(raw.get("resultMeta")),
            turn_counter=int(raw.get("turnCounter") or 0),
            updated_at=datetime.fromisoformat(raw["updatedAt"])
            if raw.get("updatedAt")
            else datetime.now(UTC),
        )


@dataclass(slots=True)
class PendingClarification:
    original_question: str
    clarifies: str
    options: tuple[str, ...] = ()
    asked_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def to_dict(self) -> dict[str, Any]:
        return {
            "originalQuestion": self.original_question,
            "clarifies": self.clarifies,
            "options": list(self.options),
            "askedAt": self.asked_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> PendingClarification:
        return cls(
            original_question=str(raw.get("originalQuestion") or ""),
            clarifies=str(raw.get("clarifies") or ""),
            options=tuple(str(o) for o in (raw.get("options") or [])),
            asked_at=datetime.fromisoformat(raw["askedAt"])
            if raw.get("askedAt")
            else datetime.now(UTC),
        )


@dataclass(slots=True)
class SessionMemory:
    version: int
    user_id: str
    conversation_id: str
    analytical: AnalyticalContext | None = None
    general_chat_turns: tuple[dict[str, str], ...] = ()
    recent_turns: tuple[dict[str, str], ...] = ()
    pending: PendingClarification | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "userId": self.user_id,
            "conversationId": self.conversation_id,
            "analytical": self.analytical.to_dict() if self.analytical else None,
            "generalChatTurns": list(self.general_chat_turns),
            "recentTurns": list(self.recent_turns),
            "pending": self.pending.to_dict() if self.pending else None,
        }

    @classmethod
    def from_dict(cls, raw: dict[str, Any] | None) -> SessionMemory | None:
        if not raw:
            return None
        return cls(
            version=int(raw.get("version") or MEMORY_VERSION),
            user_id=str(raw.get("userId") or ""),
            conversation_id=str(raw.get("conversationId") or ""),
            analytical=AnalyticalContext.from_dict(raw["analytical"])
            if raw.get("analytical")
            else None,
            general_chat_turns=tuple(dict(t) for t in (raw.get("generalChatTurns") or [])),
            recent_turns=tuple(dict(t) for t in (raw.get("recentTurns") or [])),
            pending=PendingClarification.from_dict(raw["pending"]) if raw.get("pending") else None,
        )


FollowUpContext = Literal["active", "expired", "none"]


def empty_memory(*, user_id: uuid.UUID, conversation_id: uuid.UUID) -> SessionMemory:
    return SessionMemory(
        version=MEMORY_VERSION,
        user_id=str(user_id),
        conversation_id=str(conversation_id),
    )


def assert_memory_scope(memory: SessionMemory, *, user_id: uuid.UUID, conversation_id: uuid.UUID) -> None:
    if memory.user_id != str(user_id) or memory.conversation_id != str(conversation_id):
        raise PermissionError("Conversation memory scope mismatch")


def is_refresh_request(question: str) -> bool:
    return bool(_REFRESH.search(question or ""))


def analytical_expired(
    memory: SessionMemory,
    settings: Settings,
    *,
    now: datetime | None = None,
) -> bool:
    ctx = memory.analytical
    if ctx is None:
        return True
    now = now or datetime.now(UTC)
    age = (now - ctx.updated_at).total_seconds()
    if age > settings.chat_analytical_context_ttl_seconds:
        return True
    return ctx.turn_counter >= settings.chat_analytical_context_max_turns


def follow_up_context_status(
    memory: SessionMemory,
    question: str,
    settings: Settings,
    *,
    industry: Industry,
    now: datetime | None = None,
) -> FollowUpContext:
    if memory.analytical is None:
        return "none"
    if rule_route_interrupts_analytical_context(question, industry):
        return "none"
    if not is_followup(question) and not is_contextual_followup(question):
        return "none"
    if analytical_expired(memory, settings, now=now):
        return "expired"
    return "active"


def plan_state_from_memory(memory: SessionMemory) -> dict[str, Any] | None:
    ctx = memory.analytical
    if ctx is None:
        return None
    return dict(ctx.validated_plan)


def build_analytical_context(
    *,
    plan: QuestionPlan,
    question: str,
    result_meta: ResultMeta,
    prior: AnalyticalContext | None,
) -> AnalyticalContext:
    filters = [
        {
            "column": item.column,
            "operator": item.operator,
            "values": list(item.all_values),
            "label": item.label,
        }
        for item in plan.filters
    ]
    period_label = plan.period.label if plan.period else None
    year_label = str(plan.year_filter) if plan.year_filter else None
    date_range = period_label or year_label
    turn = (prior.turn_counter if prior else 0) + 1
    return AnalyticalContext(
        previous_intent=plan.intent,
        previous_question=question.strip(),
        metrics=(plan.metric,) if plan.metric != "unknown" else (),
        dimensions=tuple(plan.dimensions),
        date_range=date_range,
        time_grain=plan.time_grain,
        filters=tuple(filters),
        validated_plan=plan_state(plan),
        result_meta=result_meta,
        turn_counter=turn,
        updated_at=datetime.now(UTC),
    )


def append_recent_turn(
    memory: SessionMemory,
    *,
    role: str,
    text: str,
    settings: Settings,
) -> None:
    entry = {"role": role, "text": text.strip()[:2000], "at": datetime.now(UTC).isoformat()}
    merged = (*memory.recent_turns, entry)
    window = settings.chat_recent_turns_window
    memory.recent_turns = merged[-window:]


def append_general_chat(memory: SessionMemory, *, role: str, text: str, settings: Settings) -> None:
    entry = {"role": role, "text": text.strip()[:500]}
    merged = (*memory.general_chat_turns, entry)
    memory.general_chat_turns = merged[-settings.chat_recent_turns_window :]


def set_pending_clarification(
    memory: SessionMemory,
    *,
    original_question: str,
    clarifies: str,
    options: list[str] | None = None,
) -> None:
    memory.pending = PendingClarification(
        original_question=original_question.strip(),
        clarifies=clarifies.strip(),
        options=tuple(options or ()),
    )


def clear_pending(memory: SessionMemory) -> None:
    memory.pending = None


def resolve_incoming_message(
    memory: SessionMemory,
    question: str,
) -> tuple[str, bool]:
    """Return (effective_question, completed_pending)."""
    pending = memory.pending
    if pending is None:
        return question.strip(), False
    if _pending_abandoned(question, pending):
        clear_pending(memory)
        return question.strip(), False
    combined = f"{pending.original_question} {question.strip()}".strip()
    clear_pending(memory)
    return combined, True


def _pending_abandoned(question: str, pending: PendingClarification) -> bool:
    """Abandon pending only on clearly non-data cues; otherwise complete the clarification."""
    q = (question or "").strip()
    ql = q.lower()
    if ql in {o.lower() for o in pending.options}:
        return False
    if _NON_DATA_PENDING.search(ql):
        return True
    try:
        from app.services.chat.intents import is_out_of_bounds

        if is_out_of_bounds(q, Industry.AUTOMOTIVE) or is_out_of_bounds(q, Industry.INSURANCE):
            return True
    except Exception:
        pass
    return False


def clear_analytical(memory: SessionMemory) -> None:
    memory.analytical = None


def revalidate_plan_for_scope(
    plan: QuestionPlan,
    question: str,
    scope: RegionScope,
) -> tuple[bool, str | None]:
    """Ensure question text and planned filter values respect region scope."""
    blocked = forbidden_zones(question, scope)
    if blocked:
        return False, f"Question references forbidden regions: {', '.join(blocked)}"
    probe_parts = [question]
    for item in plan.filters:
        probe_parts.extend(item.all_values)
    blocked = forbidden_zones(" ".join(probe_parts), scope)
    if blocked:
        return False, f"Plan filters reference forbidden regions: {', '.join(blocked)}"
    return True, None


def revalidate_stored_plan_for_scope(
    memory: SessionMemory,
    industry: Any,
    question: str,
    scope: RegionScope,
) -> tuple[bool, str | None]:
    state = plan_state_from_memory(memory)
    return revalidate_prior_state_for_scope(industry, state, question, scope)


def revalidate_prior_state_for_scope(
    industry: Any,
    state: dict[str, Any] | None,
    question: str,
    scope: RegionScope,
) -> tuple[bool, str | None]:
    if not state:
        return True, None
    plan = state_to_plan(industry, state)
    return revalidate_plan_for_scope(plan, question, scope)


def session_memory_storage_error(exc: BaseException) -> bool:
    """True when the DB cannot read/write ``conversations.session_memory`` (pre-migration)."""
    msg = str(exc).lower()
    return "session_memory" in msg or "no such column" in msg


def validated_plan_is_structured(plan_dict: dict[str, Any]) -> bool:
    """``validatedPlan`` holds governed plan fields only — no user free-text blob."""
    allowed_top = {
        "metric",
        "entity",
        "intent",
        "dimensions",
        "timeGrain",
        "analysis",
        "yearFilter",
        "period",
        "limit",
        "orderDirection",
        "partitionBy",
        "aggregation",
        "filters",
    }
    if not allowed_top.issuperset(plan_dict.keys()):
        return False
    for item in plan_dict.get("filters") or []:
        if not isinstance(item, dict):
            return False
        if not {"column", "operator", "value", "values", "label"}.issuperset(item.keys()):
            return False
    return True


def memory_for_response(meta: dict[str, Any]) -> dict[str, Any]:
    """Safe summary of what is persisted (for admin/debug)."""
    analytical = meta.get("analytical")
    pending = meta.get("pending")
    return {
        "hasAnalytical": bool(analytical),
        "analyticalTurnCounter": (analytical or {}).get("turnCounter"),
        "pendingClarification": bool(pending),
        "recentTurns": len(meta.get("recentTurns") or []),
        "generalChatTurns": len(meta.get("generalChatTurns") or []),
        "storesSql": False,
        "storesResultRows": False,
    }
