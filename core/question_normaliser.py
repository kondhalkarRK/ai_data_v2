"""
core/question_normaliser.py
Stable cache-key normalisation + follow-up / OOB / scenario detectors.
"""
from __future__ import annotations

import hashlib
import re
from typing import Any

try:
    from config.constants import (
        FOLLOWUP_TRIGGER_TOKENS,
        MAX_FOLLOWUP_QUESTION_WORDS,
        OOB_PATTERNS,
    )
except ImportError:
    FOLLOWUP_TRIGGER_TOKENS = [
        "same", "now", "also", "but", "only",
        "filter", "instead", "what about",
        "how about", "additionally", "too",
        "and what", "show only", "just show",
    ]
    MAX_FOLLOWUP_QUESTION_WORDS = 8
    OOB_PATTERNS = [
        r"\bwrite\s+(me\s+)?code\b",
        r"\bdelete\s+(the\s+)?data\b",
        r"\bdrop\s+table\b",
        r"\binsert\s+into\b",
        r"\bpredict\s+future\b",
        r"\bml\s+model\b",
        r"\btrain\s+(a\s+)?model\b",
    ]

_STOP_WORDS = {
    "a", "an", "the", "me", "my", "please", "show", "give", "list",
    "display", "get", "find", "tell", "of", "to", "for", "in", "on",
    "at", "from", "with", "and", "or", "is", "are", "was", "were",
    "what", "which", "who", "how", "many", "much",
}

_SCENARIO_PATTERNS = [
    r"\bwhat\s+if\b",
    r"\bif\s+.*\bchange[sd]?\b",
    r"\bsuppose\b",
    r"\bassume\b",
    r"\b\d+\s*%\s*(increase|decrease|change)\b",
    r"\b(increase|decrease)\s+by\s+\d+\b",
]

_OOB_EXTRA = [
    r"\bupdate\s+.*set\b",
    r"\bforecast\s+next\b",
    r"\bpersonal\s+data\b",
    r"\bpassword\b",
    r"\bcredit\s+card\b",
]

_FOLLOWUP_EXTRA = [
    "same", "now", "also", "but", "only",
    "filter", "instead", "what about",
    "how about", "additionally", "too",
    "and what", "show only", "just show",
]


def normalise_question(question: str) -> str:
    """
    Lowercase, strip punctuation, drop stop words, sort tokens → stable key text.
    """
    if not question:
        return ""
    q = question.lower().strip()
    q = re.sub(r"[^\w\s%]", " ", q)
    tokens = [t for t in q.split() if t and t not in _STOP_WORDS]
    tokens.sort()
    return " ".join(tokens)


def fingerprint_question(question: str) -> str:
    """SHA-256 fingerprint of the normalised question (16 hex chars)."""
    norm = normalise_question(question)
    return hashlib.sha256(norm.encode("utf-8")).hexdigest()[:16]


def detect_followup(question: str) -> bool:
    """
    Follow-up signal detection.
    Rules: short question (≤8 words) + token OR explicit reference tokens.
    """
    if not question or not isinstance(question, str):
        return False
    q = question.strip().lower()
    if not q:
        return False

    tokens = list(FOLLOWUP_TRIGGER_TOKENS) + _FOLLOWUP_EXTRA
    # de-dupe
    seen = set()
    uniq = []
    for t in tokens:
        if t not in seen:
            seen.add(t)
            uniq.append(t)

    explicit = [t for t in uniq if " " in t]
    if any(tok in q for tok in explicit):
        return True

    words = q.split()
    has_token = any(
        re.search(rf"\b{re.escape(tok)}\b", q)
        for tok in uniq
        if " " not in tok
    )
    if has_token and len(words) <= MAX_FOLLOWUP_QUESTION_WORDS:
        return True
    return False


def detect_oob(question: str) -> bool:
    """Out-of-scope detection for CSV analytics domain."""
    if not question:
        return False
    q = question.lower()
    patterns = list(OOB_PATTERNS) + _OOB_EXTRA
    return any(re.search(p, q, flags=re.IGNORECASE) for p in patterns)


def detect_scenario(question: str) -> bool:
    """Scenario / what-if signal detection."""
    if not question:
        return False
    q = question.lower()
    return any(re.search(p, q, flags=re.IGNORECASE) for p in _SCENARIO_PATTERNS)


def extract_followup_tokens(question: str) -> dict[str, Any]:
    """
    Extract what changed in a follow-up question.
    """
    result = {
        "dimension_change": None,
        "filter_change": None,
        "metric_change": None,
        "time_change": None,
    }
    if not question:
        return result

    q = question.strip().lower()

    # Dimension: "by X", "now show by X"
    m = re.search(r"\bby\s+([a-z0-9_ ]+?)(?:\s+(?:for|in|only|with)|$)", q)
    if m:
        result["dimension_change"] = m.group(1).strip()

    # Filter: "for X", "only for X", "same but for X"
    m = re.search(
        r"\b(?:only\s+for|but\s+for|just\s+for|for)\s+([a-z0-9_ ]+?)(?:\s+by|$)",
        q,
    )
    if m:
        result["filter_change"] = m.group(1).strip()

    # Metric: "instead show revenue", "now revenue"
    m = re.search(
        r"\b(?:instead|now|also)\s+(?:show\s+)?([a-z_ ]+?)(?:\s+by|\s+for|$)",
        q,
    )
    if m and "by" not in m.group(1):
        candidate = m.group(1).strip()
        if candidate and candidate not in ("show", "me", "the"):
            result["metric_change"] = candidate

    # Time: year or month mentions
    m = re.search(r"\b(20\d{2}|19\d{2})\b", q)
    if m:
        result["time_change"] = m.group(1)
    else:
        m = re.search(
            r"\b(january|february|march|april|may|june|july|august|"
            r"september|october|november|december|q[1-4])\b",
            q,
        )
        if m:
            result["time_change"] = m.group(1)

    return result
