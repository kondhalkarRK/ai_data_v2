"""
core/question_normaliser.py
Follow-up / OOB detectors and SQL-anchor intent classification.
"""
from __future__ import annotations

import re

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
    "drill down", "drill into", "break down", "break that down",
    "deeper", "more detail", "zoom in", "dig into", "slice by", "split by",
]


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


# ── Follow-up intent classification (SQL-anchor routing) ─────────

ADDITIVE_PATTERNS = [
    r"\badd\s+\w+",
    r"\binclude\s+\w+",
    r"\balso\s+show\s+\w+",
    r"\bwith\s+\w+",
    r"\bshow\s+\w+\s+as\s+well\b",
    r"\bplus\s+\w+",
    r"\bcan\s+you\s+add\s+\w+",
    r"\band\s+\w+\s+column\b",
    r"\bshow\s+me\s+\w+\s+too\b",
    r"\balso\s+(?:show\s+)?\w+",
]

SUBTRACTIVE_PATTERNS = [
    r"\bremove\s+\w+",
    r"\bhide\s+\w+",
    r"\bwithout\s+\w+",
    r"\bdrop\s+\w+",
    r"\bdon'?t\s+show\s+\w+",
    r"\bexclude\s+\w+",
    r"\bonly\s+\w+\s+and\s+\w+",
]

FILTER_CHANGE_PATTERNS = [
    r"\bonly\s+for\s+\w+",
    r"\bfilter\s+by\s+\w+",
    r"\bjust\s+\w+",
    r"\bfor\s+(?:20\d{2}|19\d{2})\b",
    r"\bin\s+(?:20\d{2}|january|february|march|april|may|june|july|august|september|october|november|december)\b",
    r"\bwhere\s+\w+",
    r"\bsame\s+but\s+for\s+\w+",
    r"\bsame\s+for\s+\w+",
    r"\b(20\d{2}|19\d{2})\s+only\b",
    r"\blast\s+month\b",
    r"\bthis\s+year\b",
    r"\bfor\s+[A-Za-z][\w\s-]{1,30}$",
    r"\bwhat\s+about\s+\w+",
    r"\bhow\s+about\s+\w+",
    r"\band\s+for\s+\w+",
    r"\bnow\s+for\s+\w+",
    r"\bsame\s+but\s+\w+",
    r"\bonly\s+[A-Za-z][\w-]*$",
]

SORT_CHANGE_PATTERNS = [
    r"\btop\s+\d+\b",
    r"\bbottom\s+\d+\b",
    r"\border\s+by\s+\w+",
    r"\bsort\s+by\s+\w+",
    r"\bhighest\s+\w+",
    r"\blowest\s+\w+",
    r"\branked\s+by\s+\w+",
    r"\bshow\s+\d+\b",
    r"\btop\s+\d+\s+only\b",
    r"\blimit\s+\d+\b",
]

DRILL_DOWN_PATTERNS = [
    r"\bdrill\s+down\b",
    r"\bdrill\s+into\b",
    r"\bbreak\s+(?:that\s+)?down\b",
    r"\bmore\s+detail\b",
    r"\bzoom\s+in\b",
    r"\bdig\s+(?:deeper|into)\b",
    r"\bslice\s+by\b",
    r"\bsplit\s+by\b",
]

NEW_TOPIC_SIGNALS = [
    "new question", "start over", "forget that", "different question",
    "instead show me",
]


def classify_followup_intent(question: str, anchor: dict | None) -> str:
    """
    Classify a chat message into: additive | subtractive | filter_change |
    sort_change | new_question.
    """
    if not question:
        return "new_question"
    q = question.strip().lower()
    if not anchor or not anchor.get("sql_anchor"):
        return "new_question"

    # Explicit new-topic first
    if any(sig in q for sig in NEW_TOPIC_SIGNALS):
        return "new_question"

    for p in ADDITIVE_PATTERNS:
        if re.search(p, q, re.I):
            return "additive"
    for p in DRILL_DOWN_PATTERNS:
        if re.search(p, q, re.I):
            return "additive"
    for p in SUBTRACTIVE_PATTERNS:
        if re.search(p, q, re.I):
            return "subtractive"
    for p in SORT_CHANGE_PATTERNS:
        if re.search(p, q, re.I):
            return "sort_change"
    for p in FILTER_CHANGE_PATTERNS:
        if re.search(p, q, re.I):
            return "filter_change"

    if detect_followup(question):
        return "filter_change"

    # Short relative utterances while an anchor exists → treat as filter/refine
    words = q.split()
    if len(words) <= 6 and not any(
        q.startswith(p) for p in ("show me revenue", "show me units", "how many", "what is the")
    ):
        # Single make/year/region-like token after a prior query
        if re.search(r"\b(20\d{2}|19\d{2})\b", q):
            return "filter_change"
        if re.search(
            r"\b(ford|tata|maruti|mahindra|hyundai|toyota|kia|honda|mg|skoda|"
            r"north|south|east|west|central|suv|petrol|diesel|electric|ev)\b",
            q,
            re.I,
        ):
            return "filter_change"

    # Long standalone analytical question → new
    if len(words) > 10 and any(
        q.startswith(p) for p in ("show ", "what ", "how ", "which ", "list ", "compare ")
    ):
        return "new_question"
    if any(q.startswith(p) for p in ("show me ", "how many ", "what is ", "compare ")):
        return "new_question"
    return "new_question"


def extract_intent_subject(
    question: str,
    intent_type: str,
    df=None,
) -> str | None:
    """Extract the subject of a follow-up (column name, year, N, etc.)."""
    if not question:
        return None
    ql = question.strip().lower()

    patterns = {
        "additive": [
            r"\badd\s+(?:the\s+)?([A-Za-z_][\w ]+?)(?:\s+column)?(?:\s+too)?$",
            r"\balso\s+show\s+(?:the\s+)?([A-Za-z_][\w ]+)",
            r"\binclude\s+(?:the\s+)?([A-Za-z_][\w ]+)",
            r"\bwith\s+([A-Za-z_][\w ]+)$",
            r"\bplus\s+([A-Za-z_][\w ]+)",
            r"\bshow\s+(?:me\s+)?([A-Za-z_][\w ]+)\s+too\b",
            r"\balso\s+([A-Za-z_][\w ]+)$",
        ],
        "subtractive": [
            r"\bremove\s+(?:the\s+)?([A-Za-z_][\w ]+)",
            r"\bhide\s+(?:the\s+)?([A-Za-z_][\w ]+)",
            r"\bwithout\s+(?:the\s+)?([A-Za-z_][\w ]+)",
            r"\bdrop\s+(?:the\s+)?([A-Za-z_][\w ]+)",
            r"\bexclude\s+(?:the\s+)?([A-Za-z_][\w ]+)",
            r"\bdon'?t\s+show\s+(?:the\s+)?([A-Za-z_][\w ]+)",
        ],
        "filter_change": [
            r"\bonly\s+for\s+(.+)$",
            r"\bsame\s+(?:but\s+)?for\s+(.+)$",
            r"\bfilter\s+by\s+(.+)$",
            r"\bwhat\s+about\s+(.+)$",
            r"\bhow\s+about\s+(.+)$",
            r"\band\s+for\s+(.+)$",
            r"\bnow\s+for\s+(.+)$",
            r"\bfor\s+(.+)$",
            r"\bin\s+(20\d{2}|19\d{2})\b",
            r"\b(20\d{2}|19\d{2})\b",
            r"\blast\s+month\b",
            r"\bthis\s+year\b",
            r"\bonly\s+([A-Za-z][\w-]*)$",
        ],
        "sort_change": [
            r"\btop\s+(\d+)",
            r"\bbottom\s+(\d+)",
            r"\bshow\s+(\d+)",
            r"\border\s+by\s+([A-Za-z_][\w ]+)",
            r"\bsort\s+by\s+([A-Za-z_][\w ]+)",
        ],
    }
    subject = None
    for pat in patterns.get(intent_type, []):
        m = re.search(pat, ql, re.I)
        if m:
            subject = (m.group(1) if m.lastindex else m.group(0)).strip()
            break

    if not subject:
        return None

    subject = re.sub(r"\b(column|please|too|as well)\b", "", subject, flags=re.I).strip()

    if df is not None and intent_type in ("additive", "subtractive", "sort_change"):
        resolved = _resolve_column_name(subject, df)
        if resolved:
            return resolved
    return subject


def _resolve_column_name(subject: str, df) -> str | None:
    if df is None or subject is None:
        return None
    s = re.sub(r"\s+", "_", str(subject).strip().lower())
    s2 = str(subject).strip().lower().replace(" ", "")
    cols = list(df.columns)
    for c in cols:
        if str(c).lower() == s or str(c).lower() == s2:
            return str(c)
    aliases = {
        "colour": "colour_name", "color": "colour_name", "color_name": "colour_name",
        "brand": "make", "salesperson": "first_name", "person": "first_name",
        "region": "region_name", "city": "city", "type": "car_type",
        "engine": "engine_type",
    }
    alias = aliases.get(s) or aliases.get(s2)
    if alias:
        for c in cols:
            if str(c).lower() == alias:
                return str(c)
    matches = [
        c for c in cols
        if s in str(c).lower() or s2 in str(c).lower().replace("_", "")
    ]
    if len(matches) == 1:
        return str(matches[0])
    return None
