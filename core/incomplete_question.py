"""
core/incomplete_question.py
Detect incomplete NL questions and build two suggestion alternatives (no LLM).
"""
from __future__ import annotations

import re

import pandas as pd

_METRIC_WORDS = {
    "revenue": "revenue", "sales": "revenue", "amount": "revenue",
    "units": "units", "unit": "units", "volume": "units", "qty": "units",
    "orders": "orders", "order": "orders",
}
_DIM_WORDS = ("make", "model", "region", "zone", "city", "colour", "color", "car", "dealer")
_TIME_WORDS = ("year", "month", "quarter", "trend", "monthly", "yearly", "2020", "2021", "2022", "2023", "2024", "2025", "2026")
_EV_WORDS = ("ev", "electric", "bev", "powertrain")


def _cols_lower(df: pd.DataFrame) -> set[str]:
    return {str(c).lower() for c in df.columns}


def _detect_metric(q: str) -> str | None:
    low = q.lower()
    if any(w in low for w in ("unit", "volume", "qty", "sold", "selling")):
        return "units"
    if any(w in low for w in ("revenue", "sales amount", "money", "inr", "rupee")):
        return "revenue"
    if "order" in low and "unit" not in low:
        return "orders"
    return None


def _detect_dim(q: str, df: pd.DataFrame | None) -> str | None:
    low = q.lower()
    cols = _cols_lower(df) if df is not None and not df.empty else set()
    for d in _DIM_WORDS:
        if d in low:
            if d == "car" and "carline" in cols:
                return "carline"
            if d == "color" and "colour" in cols:
                return "colour"
            if d in cols or d == "make":
                return "colour" if d == "color" else d
    return None


def _has_time(q: str) -> bool:
    low = q.lower()
    if any(t in low for t in _TIME_WORDS):
        return True
    return bool(re.search(r"\b20\d{2}\b", low))


def _extract_entity(q: str) -> str | None:
    """Rough entity after 'about' / 'for' phrases."""
    low = q.lower().strip()
    for prefix in ("tell me about ", "about ", "for ", "show ", "how is "):
        if low.startswith(prefix):
            rest = low[len(prefix):].strip(" ?.")
            words = rest.split()
            if words and words[0] not in _METRIC_WORDS and words[0] not in _DIM_WORDS:
                return " ".join(words[:3])
    return None


def build_suggestions(question: str, df: pd.DataFrame | None) -> list[str]:
    """Return exactly two complete question suggestions."""
    q = (question or "").strip()
    low = q.lower()
    metric = _detect_metric(q) or "units"
    dim = _detect_dim(q, df) or "make"
    entity = _extract_entity(q)
    year = "2025"
    m = re.search(r"\b(20\d{2})\b", q)
    if m:
        year = m.group(1)

    if any(w in low for w in _EV_WORDS):
        return [
            f"Show EV unit share by year",
            f"Top makes by electric vehicle units sold in {year}",
        ]

    if "between" in low and re.search(r"20\d{2}", low):
        years = re.findall(r"20\d{2}", low)
        if len(years) >= 2:
            y1, y2 = years[0], years[-1]
            return [
                f"Which {dim} gained the most units between {y1} and {y2}?",
                f"Compare total {metric} by {dim} for {y1} versus {y2}",
            ]

    if entity:
        ent = entity.title()
        return [
            f"Show {metric} for {ent} by region in {year}",
            f"Monthly {metric} trend for {ent} in {year}",
        ]

    if not _has_time(q):
        return [
            f"Show total {metric} by {dim} for {year}",
            f"Monthly {metric} trend by {dim} in {year}",
        ]

    if not _detect_metric(q):
        return [
            f"Show total revenue by {dim} for {year}",
            f"Show units sold by {dim} for {year}",
        ]

    if "by" not in low and dim:
        return [
            f"Show {metric} by {dim} for {year}",
            f"Top 10 {dim} by {metric} in {year}",
        ]

    return [
        f"Show {metric} by {dim} for {year}",
        f"Compare {metric} by region for {year}",
    ]


def assess_question_completeness(question: str, df: pd.DataFrame | None) -> dict:
    """
    Returns {incomplete: bool, suggestions: [str, str], reason: str}
    """
    q = (question or "").strip()
    low = q.lower().rstrip("?.!")
    if not q or len(low) < 3:
        return {"incomplete": True, "suggestions": build_suggestions(q, df)[:2], "reason": "too_short"}

    words = low.split()

    # Clearly complete patterns — do not interrupt
    complete_signals = (
        " by ", " between ", " versus ", " vs ", " top ", " trend",
        "monthly", "yearly", "quarterly", "share", "gained", "compare",
    )
    if any(s in f" {low} " for s in complete_signals) and len(words) >= 5:
        return {"incomplete": False, "suggestions": [], "reason": "complete"}

    if re.search(r"which .+ (gained|lost|sold|lead)", low) and _has_time(q):
        return {"incomplete": False, "suggestions": [], "reason": "complete"}

    vague_exact = {
        "show me sales", "show sales", "ev sales", "electric sales",
        "tell me about ev", "how is performance", "show me the best",
        "compare them", "what about sales", "sales last year",
        "last year sales", "performance", "show me revenue",
    }
    if low in vague_exact or low.rstrip("?.!") in vague_exact:
        return {"incomplete": True, "suggestions": build_suggestions(q, df)[:2], "reason": "vague"}

    if low.startswith("tell me about ") and len(words) <= 5:
        rest = low.replace("tell me about ", "")
        if rest and not any(m in rest for m in ("revenue", "sales", "units", "trend")):
            return {"incomplete": True, "suggestions": build_suggestions(q, df)[:2], "reason": "entity_only"}

    if len(words) <= 4 and not _detect_metric(q) and not _has_time(q):
        return {"incomplete": True, "suggestions": build_suggestions(q, df)[:2], "reason": "short_vague"}

    if _detect_metric(q) and not _has_time(q) and "by" not in low and len(words) <= 6:
        return {"incomplete": True, "suggestions": build_suggestions(q, df)[:2], "reason": "missing_time_or_dim"}

    return {"incomplete": False, "suggestions": [], "reason": "ok"}
