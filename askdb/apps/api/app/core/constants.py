"""Business constants carried over from the legacy ``config/constants.py``.

Values that governed query behaviour in the Streamlit app are preserved verbatim so the
new backend produces the same bounded results. Streamlit-specific constants are dropped.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Final

# --- conversation ----------------------------------------------------------
MAX_CONVERSATION_TURNS: Final = 10
MAX_FOLLOWUP_QUESTION_WORDS: Final = 8
FOLLOWUP_TRIGGER_TOKENS: Final[frozenset[str]] = frozenset(
    {
        "also",
        "and",
        "instead",
        "what about",
        "how about",
        "that",
        "those",
        "these",
        "it",
        "them",
        "same",
        "add",
        "remove",
        "drop",
        "exclude",
        "include",
        "sort",
        "order",
        "top",
        "bottom",
        "filter",
        "only",
        "break",
        "split",
        "by",
    }
)

# --- query bounds (legacy config/constants.py:35-37) -----------------------
MAX_QUERY_ROWS: Final = 1000
MAX_QUERY_TIMEOUT_SECONDS: Final = 30
MAX_RESULT_DISPLAY_ROWS: Final = 500
CHAT_PREVIEW_ROWS: Final = 5

# --- evidence --------------------------------------------------------------
MAX_EVIDENCE_HISTORY: Final = 20


class ExecutionPath(StrEnum):
    """How a result was produced. Surfaced to the user as a provenance badge."""

    DETERMINISTIC = "deterministic"
    LLM_FALLBACK = "llm_fallback"
    CACHED = "cached"
    OUT_OF_BOUNDS = "out_of_bounds"


EXECUTION_BADGES: Final[dict[ExecutionPath, dict[str, str]]] = {
    ExecutionPath.DETERMINISTIC: {
        "label": "Semantic",
        "tone": "success",
        "description": "Compiled from the semantic layer and validated before execution.",
    },
    ExecutionPath.LLM_FALLBACK: {
        "label": "Semantic + AI",
        "tone": "info",
        "description": "Generated with model assistance, then validated by SQL guardrails.",
    },
    ExecutionPath.CACHED: {
        "label": "Cached",
        "tone": "neutral",
        "description": "Served from a previous identical question on unchanged data.",
    },
    ExecutionPath.OUT_OF_BOUNDS: {
        "label": "Out of scope",
        "tone": "warning",
        "description": "The question falls outside the governed data scope.",
    },
}


# --- narration -------------------------------------------------------------
NARRATION_USE_LLM: Final = False
NARRATION_MAX_ROWS: Final = 15
NARRATION_MAX_TOKENS: Final = 400

# --- rotating loading messages (spec section 8) ----------------------------
LOADING_MESSAGES: Final[tuple[str, ...]] = (
    "Analyzing your question...",
    "Understanding business context...",
    "Loading data...",
    "Building semantic relationships...",
    "Exploring ontology...",
    "Generating insights...",
    "Retrieving relevant information...",
    "Preparing dashboard...",
    "Finalizing response...",
)
