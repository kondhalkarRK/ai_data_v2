"""
core/incomplete_question.py
Detect incomplete NL questions and build two suggestion alternatives (no LLM).
Insurance (Postgres) and automotive (CSV/DuckDB) packs use different suggestions.
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
_TIME_WORDS = (
    "year", "month", "quarter", "trend", "monthly", "yearly",
    "2020", "2021", "2022", "2023", "2024", "2025", "2026",
    "ytd", "last 12", "rolling",
)
_EV_WORDS = ("ev", "electric", "bev", "powertrain")

_INS_METRIC_WORDS = {
    "claims": "claims incurred",
    "claim": "claims incurred",
    "incurred": "claims incurred",
    "premium": "earned premium",
    "gwp": "gross written premium",
    "written": "gross written premium",
    "earned": "earned premium",
    "loss ratio": "loss ratio",
    "severity": "average claim severity",
    "frequency": "claim frequency",
    "approval": "approval rate",
    "renewal": "renewal rate",
    "reserve": "reserve",
    "payout": "claims paid",
    "paid": "claims paid",
}
_INS_DIM_WORDS = (
    "region", "territory", "product", "lob", "line of business",
    "agent", "broker", "customer", "policyholder", "policy", "status",
)
_INS_ENTITY_HINTS = {
    "east": "East region",
    "west": "West region",
    "north": "North region",
    "south": "South region",
    "motor": "Motor",
    "health": "Health",
    "property": "Property",
}


def _insurance_mode() -> bool:
    try:
        from core.data_backend.factory import postgres_mode_enabled
        if postgres_mode_enabled():
            return True
    except Exception:
        pass
    try:
        import streamlit as st
        pack = str(st.session_state.get("industry_pack_id") or "").lower()
        if pack == "insurance":
            return True
    except Exception:
        pass
    try:
        from config.settings import get_data_config
        if str(get_data_config().get("industry_pack") or "").lower() == "insurance":
            return True
    except Exception:
        pass
    return False


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


def _detect_ins_metric(q: str) -> str | None:
    low = q.lower()
    # Longer phrases first
    for phrase, label in (
        ("loss ratio", "loss ratio"),
        ("written premium", "gross written premium"),
        ("earned premium", "earned premium"),
        ("claims paid", "claims paid"),
        ("claims incurred", "claims incurred"),
        ("claim count", "claim count"),
        ("approval rate", "approval rate"),
        ("renewal rate", "renewal rate"),
        ("average severity", "average claim severity"),
        ("severity", "average claim severity"),
        ("gwp", "gross written premium"),
    ):
        if phrase in low:
            return label
    if any(w in low for w in ("claim", "incurred", "payout", "loss")):
        return "claims incurred"
    if any(w in low for w in ("premium", "gwp", "written", "earned")):
        return "earned premium"
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


def _detect_ins_dim(q: str) -> str | None:
    low = q.lower()
    if any(w in low for w in ("region", "territory", "east", "west", "north", "south")):
        return "region"
    if any(w in low for w in ("product", "lob", "line of business", "motor", "health", "property")):
        return "product"
    if any(w in low for w in ("agent", "broker", "intermediary")):
        return "agent"
    if any(w in low for w in ("customer", "policyholder", "insured")):
        return "customer"
    if "policy" in low:
        return "policy"
    if "status" in low:
        return "claim status"
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
            if not words:
                return None
            first = words[0]
            if first in _METRIC_WORDS or first in _DIM_WORDS:
                return None
            if first in _INS_METRIC_WORDS or first in {
                "claims", "premium", "loss", "region", "product",
            }:
                return None
            return " ".join(words[:3])
    return None


def _ins_entity_label(q: str) -> str | None:
    low = q.lower()
    for key, label in _INS_ENTITY_HINTS.items():
        if re.search(rf"\b{re.escape(key)}\b", low):
            return label
    ent = _extract_entity(q)
    return ent.title() if ent else None


def build_suggestions_insurance(question: str) -> list[str]:
    """Exactly two complete insurance-domain question suggestions."""
    q = (question or "").strip()
    low = q.lower()
    metric = _detect_ins_metric(q) or "claims incurred"
    dim = _detect_ins_dim(q) or "region"
    entity = _ins_entity_label(q)
    year = "2025"
    m = re.search(r"\b(20\d{2})\b", q)
    if m:
        year = m.group(1)

    if entity and any(k in low for k in _INS_ENTITY_HINTS):
        # Region / LOB named without metric or grain
        if dim == "region" or entity.endswith("region"):
            return [
                f"Show claim count and claims incurred for {entity} by product in {year}",
                f"Loss ratio for {entity} by month in {year}",
            ]
        return [
            f"Show claim count and claims incurred for {entity} by region in {year}",
            f"Earned premium and GWP for {entity} by month in {year}",
        ]

    if entity:
        return [
            f"Show {metric} for {entity} by region in {year}",
            f"Monthly {metric} trend for {entity} in {year}",
        ]

    if "loss ratio" in low or low in {"lr", "loss ratio?"}:
        return [
            f"Loss ratio by region for {year} (with incurred and earned premium)",
            f"Loss ratio by product (LOB) for {year}",
        ]

    if not _has_time(q):
        return [
            f"Show {metric} by {dim} for {year}",
            f"Monthly {metric} trend by {dim} in {year}",
        ]

    if not _detect_ins_metric(q):
        return [
            f"Show claims incurred and claim count by {dim} for {year}",
            f"Show earned premium and GWP by {dim} for {year}",
        ]

    if "by" not in low:
        return [
            f"Show {metric} by {dim} for {year}",
            f"Top 10 {dim} by {metric} in {year}",
        ]

    return [
        f"Show {metric} by {dim} for {year}",
        f"Compare {metric} by region and product for {year}",
    ]


def build_suggestions(question: str, df: pd.DataFrame | None) -> list[str]:
    """Return exactly two complete question suggestions."""
    if _insurance_mode():
        return build_suggestions_insurance(question)[:2]

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
    suggestions_fn = (
        (lambda: build_suggestions_insurance(q)[:2])
        if _insurance_mode()
        else (lambda: build_suggestions(q, df)[:2])
    )

    if not q or len(low) < 3:
        return {"incomplete": True, "suggestions": suggestions_fn(), "reason": "too_short"}

    words = low.split()

    # Clearly complete patterns — do not interrupt
    if "loss ratio" in low and ("by" in low or _has_time(q)):
        return {"incomplete": False, "suggestions": [], "reason": "complete"}

    complete_signals = (
        " by ", " between ", " versus ", " vs ", " top ", " trend",
        "monthly", "yearly", "quarterly", "share", "gained", "compare",
    )
    if any(s in f" {low} " for s in complete_signals) and len(words) >= 5:
        return {"incomplete": False, "suggestions": [], "reason": "complete"}

    if re.search(r"which .+ (gained|lost|sold|lead)", low) and _has_time(q):
        return {"incomplete": False, "suggestions": [], "reason": "complete"}

    if _insurance_mode():
        vague_exact = {
            "show me claims", "show claims", "show premium", "show premiums",
            "tell me about east", "tell me about west", "how is performance",
            "show me the best", "compare them", "what about claims",
            "claims last year", "last year claims", "performance",
            "show me loss ratio", "loss ratio", "show gwp", "show severity",
            "east", "west", "north", "south", "motor", "health", "property",
            "claims", "premium", "customers", "policies",
        }
        if low in vague_exact or low.rstrip("?.!") in vague_exact:
            return {"incomplete": True, "suggestions": suggestions_fn(), "reason": "vague"}

        if low.startswith("tell me about ") and len(words) <= 5:
            rest = low.replace("tell me about ", "")
            if rest and not _detect_ins_metric(rest) and "trend" not in rest:
                return {"incomplete": True, "suggestions": suggestions_fn(), "reason": "entity_only"}

        # Bare region / LOB name
        if low in _INS_ENTITY_HINTS and len(words) <= 2:
            return {"incomplete": True, "suggestions": suggestions_fn(), "reason": "entity_only"}

        if len(words) <= 4 and not _detect_ins_metric(q) and not _has_time(q):
            return {"incomplete": True, "suggestions": suggestions_fn(), "reason": "short_vague"}

        if _detect_ins_metric(q) and not _has_time(q) and "by" not in low and len(words) <= 6:
            return {"incomplete": True, "suggestions": suggestions_fn(), "reason": "missing_time_or_dim"}

        return {"incomplete": False, "suggestions": [], "reason": "ok"}

    vague_exact = {
        "show me sales", "show sales", "ev sales", "electric sales",
        "tell me about ev", "how is performance", "show me the best",
        "compare them", "what about sales", "sales last year",
        "last year sales", "performance", "show me revenue",
    }
    if low in vague_exact or low.rstrip("?.!") in vague_exact:
        return {"incomplete": True, "suggestions": suggestions_fn(), "reason": "vague"}

    if low.startswith("tell me about ") and len(words) <= 5:
        rest = low.replace("tell me about ", "")
        if rest and not any(m in rest for m in ("revenue", "sales", "units", "trend")):
            return {"incomplete": True, "suggestions": suggestions_fn(), "reason": "entity_only"}

    if len(words) <= 4 and not _detect_metric(q) and not _has_time(q):
        return {"incomplete": True, "suggestions": suggestions_fn(), "reason": "short_vague"}

    if _detect_metric(q) and not _has_time(q) and "by" not in low and len(words) <= 6:
        return {"incomplete": True, "suggestions": suggestions_fn(), "reason": "missing_time_or_dim"}

    return {"incomplete": False, "suggestions": [], "reason": "ok"}
