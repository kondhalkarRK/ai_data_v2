"""
core/conversation_state.py
Conversation-aware state for follow-up NLQ turns.
"""
from __future__ import annotations

import re
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
    "pending_clarification": None,
    # SQL anchor — last successful query for surgical follow-up edits
    "sql_anchor": None,
    "sql_anchor_question": None,
    "sql_anchor_columns": [],
    "sql_anchor_filters": [],
    "sql_anchor_metric": None,
    "sql_anchor_order": None,
    "sql_anchor_limit": None,
    "sql_anchor_group_by": None,
    "anchor_turn": 0,
    "modification_depth": 0,
    "last_followup_intent": None,
    "last_followup_subject": None,
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
    st.session_state[_STATE_KEY]["pending_clarification"] = None
    clear_sql_anchor()


def set_sql_anchor(sql: str, question: str, df=None) -> None:
    """Parse successful SQL and store as surgical-edit anchor."""
    state = _ensure_state()
    sql = (sql or "").strip()
    if not sql or sql.startswith("--"):
        return

    select_m = re.search(
        r"\bSELECT\b\s+(.*?)\s+\bFROM\b",
        sql,
        flags=re.IGNORECASE | re.DOTALL,
    )
    select_body = select_m.group(1).strip() if select_m else ""

    # Column-ish tokens from SELECT (aliases + bare names)
    cols: list[str] = []
    for part in re.split(r",(?![^()]*\))", select_body):
        part = part.strip()
        if not part:
            continue
        as_m = re.search(r"\bAS\s+([A-Za-z_][\w]*)\s*$", part, flags=re.IGNORECASE)
        if as_m:
            cols.append(as_m.group(1))
            continue
        bare = re.findall(r"[A-Za-z_][\w]*", part)
        if bare:
            cols.append(bare[-1])

    where_m = re.search(
        r"\bWHERE\b\s+(.*?)(?=\b(?:GROUP\s+BY|ORDER\s+BY|LIMIT|HAVING)\b|$)",
        sql,
        flags=re.IGNORECASE | re.DOTALL,
    )
    filters = [where_m.group(1).strip().rstrip(";")] if where_m else []

    metric_m = re.search(
        r"\b((?:SUM|COUNT|AVG|MIN|MAX)\s*\([^)]+\))",
        select_body,
        flags=re.IGNORECASE,
    )
    order_m = re.search(
        r"\bORDER\s+BY\b\s+(.*?)(?=\bLIMIT\b|$)",
        sql,
        flags=re.IGNORECASE | re.DOTALL,
    )
    limit_m = re.search(r"\bLIMIT\s+(\d+)", sql, flags=re.IGNORECASE)
    group_m = re.search(
        r"\bGROUP\s+BY\b\s+(.*?)(?=\b(?:ORDER\s+BY|LIMIT|HAVING)\b|$)",
        sql,
        flags=re.IGNORECASE | re.DOTALL,
    )

    state["sql_anchor"] = sql
    state["sql_anchor_question"] = question
    state["sql_anchor_columns"] = cols
    state["sql_anchor_filters"] = filters
    state["sql_anchor_metric"] = metric_m.group(1) if metric_m else None
    state["sql_anchor_order"] = order_m.group(1).strip().rstrip(";") if order_m else None
    state["sql_anchor_limit"] = int(limit_m.group(1)) if limit_m else None
    state["sql_anchor_group_by"] = (
        group_m.group(1).strip().rstrip(";") if group_m else None
    )
    state["anchor_turn"] = int(state.get("anchor_turn") or 0) + 1


def get_sql_anchor() -> dict | None:
    """Return full SQL anchor dict, or None if unset."""
    state = _ensure_state()
    if not state.get("sql_anchor"):
        return None
    return {
        "sql_anchor": state.get("sql_anchor"),
        "sql_anchor_question": state.get("sql_anchor_question"),
        "sql_anchor_columns": list(state.get("sql_anchor_columns") or []),
        "sql_anchor_filters": list(state.get("sql_anchor_filters") or []),
        "sql_anchor_metric": state.get("sql_anchor_metric"),
        "sql_anchor_order": state.get("sql_anchor_order"),
        "sql_anchor_limit": state.get("sql_anchor_limit"),
        "sql_anchor_group_by": state.get("sql_anchor_group_by"),
        "anchor_turn": state.get("anchor_turn", 0),
        "modification_depth": state.get("modification_depth", 0),
        "last_followup_intent": state.get("last_followup_intent"),
        "last_followup_subject": state.get("last_followup_subject"),
    }


def clear_sql_anchor() -> None:
    """Reset all sql_anchor_* fields."""
    state = _ensure_state()
    state["sql_anchor"] = None
    state["sql_anchor_question"] = None
    state["sql_anchor_columns"] = []
    state["sql_anchor_filters"] = []
    state["sql_anchor_metric"] = None
    state["sql_anchor_order"] = None
    state["sql_anchor_limit"] = None
    state["sql_anchor_group_by"] = None
    state["anchor_turn"] = 0
    state["modification_depth"] = 0
    state["last_followup_intent"] = None
    state["last_followup_subject"] = None


def should_use_anchor(question: str) -> bool:
    """True when follow-up should surgically modify the SQL anchor."""
    anchor = get_sql_anchor()
    if not anchor or not question:
        return False
    q = question.strip().lower()
    new_topic = (
        "new question", "start over", "forget that", "different question",
        "instead show me",
    )
    if any(sig in q for sig in new_topic):
        return False

    try:
        from core.question_normaliser import classify_followup_intent
        intent = classify_followup_intent(question, anchor)
        return intent != "new_question"
    except Exception:
        return detect_followup(question)


def is_awaiting_clarification() -> bool:
    """True when a clarifying question is pending a user A/B/C reply."""
    try:
        state = get_state()
        return bool(state.get("pending_clarification"))
    except Exception:
        return False


def set_pending_clarification(question: str, options: dict | None = None) -> None:
    """Store ambiguous question awaiting A/B/C clarification."""
    state = _ensure_state()
    state["pending_clarification"] = {
        "question": question,
        "options": options or {
            "a": "Revenue",
            "b": "Units Sold",
            "c": "Order count",
        },
    }


def resolve_clarification(choice: str) -> str | None:
    """
    Map A/B/C (or 1/2/3) to a reconstructed data question.
    Clears pending_clarification. Returns None if nothing pending.
    """
    state = _ensure_state()
    pending = state.get("pending_clarification")
    if not pending:
        return None
    opts = pending.get("options") or {
        "a": "Revenue", "b": "Units Sold", "c": "Order count",
    }
    key = str(choice or "").strip().lower()
    digit_map = {"1": "a", "2": "b", "3": "c"}
    key = digit_map.get(key, key)
    metric = opts.get(key) or opts.get(key[:1])
    original = pending.get("question") or ""
    state["pending_clarification"] = None
    if not metric:
        return original
    # Reconstruct: prefer "show {metric} by colour" style
    return f"show {metric} by colour"


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

    # Keep SQL anchor in sync after successful data queries
    if sql and not str(sql).startswith("--"):
        try:
            set_sql_anchor(sql, question or "")
        except Exception:
            pass

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
    """Build conversation history + SQL anchor summary for LLM injection."""
    state = get_state()
    hist = list(state.get("chat_history") or [])[-n_turns:]
    lines: list[str] = []

    anchor = None
    try:
        anchor = get_sql_anchor()
    except Exception:
        anchor = None

    if anchor and anchor.get("sql_anchor"):
        lines.append("ACTIVE SQL ANCHOR (preserve unless user starts a new topic):")
        lines.append(f"  Prior question: {anchor.get('sql_anchor_question') or '—'}")
        if anchor.get("sql_anchor_metric"):
            lines.append(f"  Metric: {anchor['sql_anchor_metric']}")
        cols = anchor.get("sql_anchor_columns") or []
        if cols:
            lines.append(f"  Columns: {', '.join(map(str, cols))}")
        filt = anchor.get("sql_anchor_filters") or []
        if filt:
            lines.append(f"  Filters: {'; '.join(filt)}")
        if anchor.get("sql_anchor_order"):
            lines.append(f"  Order: {anchor['sql_anchor_order']}")
        if anchor.get("sql_anchor_limit") is not None:
            lines.append(f"  Limit: {anchor['sql_anchor_limit']}")
        lines.append(f"  SQL:\n{anchor['sql_anchor']}")

    # Also pull from session chat_messages if richer
    msgs = st.session_state.get("chat_messages") or []
    if msgs and not hist:
        lines.append(f"CONVERSATION HISTORY (last {n_turns} turns):")
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
        return "\n".join(lines) if lines else ""

    if hist:
        lines.append(f"CONVERSATION HISTORY (last {len(hist)} turns):")
        for ex in hist:
            lines.append(f"User: {ex.get('user_question', '')}")
            if ex.get("result_summary"):
                lines.append(f"Result: {ex['result_summary']}")
            if ex.get("metric_used"):
                lines.append(f"Metric used: {ex['metric_used']}")

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

    # Lifestyle / off-topic → never treat as data (polite redirect via OOB)
    lifestyle = (
        "dinner", "lunch", "breakfast", "recipe", "weather", "joke",
        "movie", "song", "football", "cricket", "restaurant", "cook",
    )
    if any(w in q for w in lifestyle) and not any(
        w in q for w in ("revenue", "sales", "units", "colour", "make", "region", "order")
    ):
        return False

    general = [
        "what can you do", "who are you", "how does this work", "help",
        "what are you", "introduce yourself",
    ]
    if any(g in q for g in general) and not any(
        w in q for w in ("show", "revenue", "sales", "colour", "make")
    ):
        return False

    # Follow-ups / clarifications about prior results → treat as data
    followup_phrases = [
        "same but", "same for", "and for", "now for", "tell me more",
        "why is", "why are", "what about", "break that down", "drill",
        "previous", "that again", "those results", "the result",
    ]
    if any(p in q for p in followup_phrases):
        return True

    # What-if always data
    if any(p in q for p in ("what if", "suppose", "simulate", "scenario")):
        return True

    data_terms = (
        "revenue", "sales", "units", "orders", "colour", "color", "make",
        "model", "salesperson", "region", "quarter", "month", "year",
        "trend", "top", "bottom", "compare", "average", "total",
        "car type", "vehicle", "ev", "electric",
    )
    has_data_term = any(t in q for t in data_terms)

    # Column names (only meaningful if also looks analytical, or exact col mention)
    if df is not None:
        try:
            for c in df.columns:
                cl = str(c).lower()
                if len(cl) >= 4 and cl in q:
                    return True
        except Exception:
            pass

    # Glossary synonyms — skip ultra-short tokens to avoid false positives
    try:
        from semantic.semantic_loader import get_semantic_loader
        syn_map = get_semantic_loader().get_synonym_map()
        for syn in syn_map:
            if syn and len(syn) >= 3 and syn in q:
                return True
    except Exception:
        pass

    triggers = [
        "show", "display", "list", "find", "top", "bottom",
        "average", "compare", "trend", " by ", "group",
        "how many", "revenue", "sales", "units", "orders",
        "colour", "color", "make", "model", "salesperson", "year",
        "month", "quarter", "filter", "same but", "region",
    ]
    # "which" / "what is" only count when paired with a data term
    if any(t in q for t in ("which ", "what is ", "what's ")):
        return has_data_term or any(t in q for t in triggers)

    return any(t in q for t in triggers) or has_data_term


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
