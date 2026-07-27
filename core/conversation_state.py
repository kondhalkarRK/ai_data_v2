"""
core/conversation_state.py
Conversation-aware state for follow-up NLQ turns.
"""
from __future__ import annotations

from typing import Any

import streamlit as st

try:
    from config.constants import (
        FOLLOWUP_TRIGGER_TOKENS,
        MAX_FOLLOWUP_QUESTION_WORDS,
        MAX_CONVERSATION_TURNS,
    )
except ImportError:
    FOLLOWUP_TRIGGER_TOKENS = [
        "same", "now", "also", "but", "only",
        "filter", "instead", "what about",
        "how about", "additionally", "too",
        "and what", "show only", "just",
    ]
    MAX_FOLLOWUP_QUESTION_WORDS = 8
    MAX_CONVERSATION_TURNS = 10

_STATE_KEY = "conversation_state"

_EMPTY_STATE: dict[str, Any] = {
    "active_intent": None,
    "last_resolved": {
        "metric": None,
        "dimensions": [],
        "filters": {},
        "time_grain": None,
        "sql": None,
    },
    "prior_metric": None,
    "prior_dimensions": [],
    "prior_filters": {},
    "prior_time_grain": None,
    "turn_count": 0,
    "last_question": None,
    "continued_from": None,
    "is_followup": False,
    "inherited_context": {},
    "chat_history": [],
}


def _ensure_state() -> dict[str, Any]:
    if _STATE_KEY not in st.session_state or not isinstance(
        st.session_state.get(_STATE_KEY), dict
    ):
        st.session_state[_STATE_KEY] = dict(_EMPTY_STATE)
        st.session_state[_STATE_KEY]["last_resolved"] = dict(
            _EMPTY_STATE["last_resolved"]
        )
        st.session_state[_STATE_KEY]["prior_dimensions"] = []
        st.session_state[_STATE_KEY]["prior_filters"] = {}
        st.session_state[_STATE_KEY]["inherited_context"] = {}
    return st.session_state[_STATE_KEY]


def get_state() -> dict[str, Any]:
    """Return current conversation state dict."""
    return _ensure_state()


def clear_state() -> None:
    """Reset conversation state to empty."""
    st.session_state[_STATE_KEY] = dict(_EMPTY_STATE)
    st.session_state[_STATE_KEY]["last_resolved"] = {
        "metric": None,
        "dimensions": [],
        "filters": {},
        "time_grain": None,
        "sql": None,
    }
    st.session_state[_STATE_KEY]["prior_dimensions"] = []
    st.session_state[_STATE_KEY]["prior_filters"] = {}
    st.session_state[_STATE_KEY]["inherited_context"] = {}
    st.session_state[_STATE_KEY]["continued_from"] = None
    st.session_state[_STATE_KEY]["chat_history"] = []


def detect_followup(question: str) -> bool:
    """
    Detect follow-up questions using ISANA-style rules:
    - Short question (≤ MAX words) + trigger token → follow-up
    - Explicit multi-word reference tokens always count
    """
    if not question or not isinstance(question, str):
        return False
    q = question.strip().lower()
    if not q:
        return False

    state = get_state()
    if not state.get("last_question") and not state.get("prior_metric"):
        return False

    words = q.split()
    explicit = [
        "what about", "how about", "same but", "and what",
        "show only", "instead of",
    ]
    if any(tok in q for tok in explicit):
        return True

    has_token = any(
        (f" {tok} " in f" {q} " or q.startswith(tok + " ") or q.endswith(" " + tok))
        for tok in FOLLOWUP_TRIGGER_TOKENS
        if " " not in tok
    ) or any(tok in q for tok in FOLLOWUP_TRIGGER_TOKENS if " " in tok)

    if has_token and len(words) <= MAX_FOLLOWUP_QUESTION_WORDS:
        return True
    return False


def inherit_context(question: str) -> dict[str, Any]:
    """
    Return what to inherit from the prior turn based on follow-up patterns.
    """
    state = get_state()
    prior_metric = state.get("prior_metric")
    prior_dims = list(state.get("prior_dimensions") or [])
    prior_filters = dict(state.get("prior_filters") or {})
    prior_grain = state.get("prior_time_grain")

    inherited: dict[str, Any] = {
        "metric": prior_metric,
        "dimensions": list(prior_dims),
        "filters": dict(prior_filters),
        "time_grain": prior_grain,
        "mode": "inherit_all",
    }

    q = (question or "").strip().lower()

    # "same but for X" / "only for Z" → inherit all, add/change filter
    if "only for" in q or "same but" in q or "but for" in q or "just for" in q:
        inherited["mode"] = "inherit_all_add_filter"
        return inherited

    # "now show by Y" → inherit metric+filters, change dimension
    if ("now" in q and "by " in q) or q.startswith("by ") or "show by" in q:
        inherited["mode"] = "inherit_metric_filters_change_dim"
        return inherited

    # "what about W" / "how about W" → inherit metric, change dim/filter
    if "what about" in q or "how about" in q:
        inherited["mode"] = "inherit_metric_change_scope"
        return inherited

    return inherited


def update_state(
    intent: dict | None,
    resolved: dict | None,
    question: str | None,
) -> None:
    """Update conversation state after a successful query."""
    state = _ensure_state()
    intent = intent or {}
    resolved = resolved or {}

    metric = (
        resolved.get("metric_name")
        or intent.get("metric_name")
        or intent.get("metric")
    )
    if not metric and isinstance(intent.get("measures"), list) and intent["measures"]:
        metric = intent["measures"][0].get("name")

    dimensions = resolved.get("dimensions")
    if dimensions is None:
        dimensions = intent.get("dimensions") or []
    if dimensions and isinstance(dimensions, list) and dimensions and isinstance(dimensions[0], dict):
        dimensions = [
            d.get("column") or d.get("alias") or str(d)
            for d in dimensions
        ]

    filters = resolved.get("filters")
    if filters is None:
        filters = intent.get("filters") or {}
    if isinstance(filters, list):
        filt_dict: dict[str, Any] = {}
        for f in filters:
            if isinstance(f, dict) and f.get("column") is not None:
                filt_dict[str(f["column"])] = f.get("value")
        filters = filt_dict

    time_grain = resolved.get("time_grain") or intent.get("time_grain")
    sql = resolved.get("sql") or intent.get("sql")

    is_fu = detect_followup(question or "")
    previous_question = state.get("last_question")
    state["is_followup"] = is_fu
    state["continued_from"] = previous_question if is_fu else None
    state["inherited_context"] = inherit_context(question or "") if is_fu else {}
    state["active_intent"] = intent.get("intent_type")
    state["prior_metric"] = metric
    state["prior_dimensions"] = list(dimensions or [])
    state["prior_filters"] = dict(filters or {})
    state["prior_time_grain"] = time_grain
    state["last_resolved"] = {
        "metric": metric,
        "dimensions": list(dimensions or []),
        "filters": dict(filters or {}),
        "time_grain": time_grain,
        "sql": sql,
    }
    state["last_question"] = question
    state["turn_count"] = min(
        int(state.get("turn_count") or 0) + 1,
        MAX_CONVERSATION_TURNS * 10,
    )

    # Chat history (last 5 exchanges)
    hist = list(state.get("chat_history") or [])
    hist.append({
        "user_question": question,
        "result_summary": resolved.get("result_summary"),
        "metric_used": metric,
        "dimensions_used": list(dimensions or []),
        "was_data_query": True,
    })
    state["chat_history"] = hist[-5:]


def append_chat_exchange(
    user_question: str,
    result_summary: str | None = None,
    metric_used: str | None = None,
    dimensions_used: list | None = None,
    was_data_query: bool = True,
) -> None:
    """Append a chat exchange for conversation memory."""
    state = _ensure_state()
    hist = list(state.get("chat_history") or [])
    hist.append({
        "user_question": user_question,
        "result_summary": result_summary,
        "metric_used": metric_used,
        "dimensions_used": list(dimensions_used or []),
        "was_data_query": was_data_query,
    })
    state["chat_history"] = hist[-5:]
    state["last_question"] = user_question
    state["turn_count"] = int(state.get("turn_count") or 0) + 1


def build_chat_context_string(n_turns: int = 5) -> str:
    """Build conversation history string for LLM injection."""
    state = get_state()
    hist = list(state.get("chat_history") or [])[-n_turns:]

    # Also pull from session chat_messages if richer
    msgs = st.session_state.get("chat_messages") or []
    if msgs and not hist:
        lines = [f"CONVERSATION HISTORY (last {n_turns} turns):"]
        for msg in msgs[-n_turns * 2:]:
            role = "User" if msg.get("role") == "user" else "Assistant"
            content = msg.get("content") or ""
            lines.append(f"{role}: {content}")
            data = msg.get("data") or {}
            if data.get("result_summary"):
                lines.append(f"[Result: {data['result_summary']}]")
            narr = data.get("narration") or {}
            if narr.get("result_summary"):
                lines.append(f"[Result: {narr['result_summary']}]")
        return "\n".join(lines) if len(lines) > 1 else ""

    if not hist:
        return ""

    lines = [f"CONVERSATION HISTORY (last {len(hist)} turns):"]
    for ex in hist:
        lines.append(f"User: {ex.get('user_question', '')}")
        if ex.get("result_summary"):
            lines.append(f"Result: {ex['result_summary']}")
    return "\n".join(lines)


def is_data_question(question: str, df=None) -> bool:
    """
    True if question is data-related; False → treat as conversational.
    """
    if not question or not str(question).strip():
        return False
    q = question.strip().lower()

    greetings = {
        "hi", "hello", "hey", "thanks", "thank you", "bye", "ok", "okay",
        "good morning", "good evening", "howdy",
    }
    if q in greetings:
        return False

    general = [
        "what can you do", "who are you", "how does this work", "help",
        "what are you", "introduce yourself",
    ]
    if any(g in q for g in general) and not any(
        w in q for w in ("show", "revenue", "sales", "colour", "make")
    ):
        return False

    # What-if always data
    if any(p in q for p in ("what if", "suppose", "simulate", "scenario")):
        return True

    # Column names
    if df is not None:
        try:
            for c in df.columns:
                if str(c).lower() in q:
                    return True
        except Exception:
            pass

    # Glossary synonyms
    try:
        from semantic.semantic_loader import get_semantic_loader
        syn_map = get_semantic_loader().get_synonym_map()
        for syn in syn_map:
            if syn and syn in q:
                return True
    except Exception:
        pass

    triggers = [
        "show", "display", "list", "find", "top", "bottom", "total",
        "average", "compare", "trend", " by ", "group", "which",
        "how many", "what is", "revenue", "sales", "units", "orders",
        "colour", "color", "make", "model", "salesperson", "year",
        "month", "quarter", "filter", "same but",
    ]
    return any(t in q for t in triggers)


def to_context_string() -> str:
    """Format state for LLM prompt injection."""
    state = get_state()
    if not state.get("prior_metric") and not state.get("last_question"):
        return ""

    parts = ["PRIOR CONTEXT:"]
    if state.get("last_question"):
        parts.append(f"  Prior question: {state['last_question']}")
    if state.get("prior_metric"):
        parts.append(f"  Prior metric: {state['prior_metric']}")
    if state.get("prior_dimensions"):
        parts.append(
            f"  Prior dimensions: {', '.join(map(str, state['prior_dimensions']))}"
        )
    if state.get("prior_filters"):
        filt = ", ".join(f"{k}={v}" for k, v in state["prior_filters"].items())
        parts.append(f"  Prior filters: {filt}")
    if state.get("prior_time_grain"):
        parts.append(f"  Prior time grain: {state['prior_time_grain']}")
    if state.get("is_followup"):
        parts.append("  This appears to be a follow-up query.")
    return "\n".join(parts)


def get_badge_info() -> dict[str, Any]:
    """Return display badge info for UI."""
    state = get_state()
    if state.get("is_followup"):
        return {
            "icon": "↩",
            "label": "Follow-up",
            "colour": "indigo",
            "prior_question": state.get("continued_from") or state.get("last_question"),
            "turn_count": state.get("turn_count", 0),
        }
    return {
        "icon": "💬",
        "label": "New query",
        "colour": "slate",
        "prior_question": None,
        "turn_count": state.get("turn_count", 0),
    }
