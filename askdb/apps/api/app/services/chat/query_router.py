"""Deterministic Chat routing: SQL, knowledge, or hybrid. No extra LLM."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Literal

from app.services.chat.question_understanding import QuestionPlan

ChatRoute = Literal["sql", "knowledge", "hybrid"]

DOCUMENT_CUES = (
    "summarize",
    "summary of",
    "report say",
    "report says",
    "key findings",
    "key finding",
    "concerns",
    "recommendations",
    "catalog",
    "policy",
    "policies",
    "what does the document",
    "what does the report",
    "in the document",
    "from the document",
    "from the report",
    "uploaded document",
    "knowledge base",
)

HYBRID_CUES = (
    "why",
    "reason",
    "reasons",
    "factors",
    "insights",
    "insight",
    "what contributed",
    "behind the",
    "explain the increase",
    "explain the decrease",
    "explain increase",
    "explain decrease",
    "why did",
    "why is",
    "why are",
    "drivers of",
)

DOCUMENT_LIKE = (
    "document",
    "report",
    "pdf",
    "memo",
    "brief",
    "findings",
    "recommendation",
    "policy",
)


@dataclass(frozen=True)
class RouteDecision:
    route: ChatRoute
    reason: str


def route_question(
    question: str,
    plan: QuestionPlan | None,
    *,
    has_documents: bool = True,
) -> RouteDecision:
    """First-match heuristics. Default is governed SQL, never RAG."""
    q = (question or "").strip().casefold()
    if not q:
        return RouteDecision("sql", "empty question defaults to analytics")

    if any(cue in q for cue in DOCUMENT_CUES):
        return RouteDecision("knowledge", "document-oriented phrasing")

    if _looks_hybrid(q):
        return RouteDecision("hybrid", "explanation/insight phrasing")

    if plan is not None and _plan_is_metric(plan):
        return RouteDecision("sql", "known metric, entity, or dimension")

    if has_documents and any(token in q for token in DOCUMENT_LIKE):
        return RouteDecision("knowledge", "document-like question with corpus present")

    return RouteDecision("sql", "default governed analytics")


def _looks_hybrid(q: str) -> bool:
    if any(cue in q for cue in HYBRID_CUES):
        return True
    if re.search(r"\bexplain\b.+\b(increase|decrease|drop|growth|spike)\b", q):
        return True
    return False


def _plan_is_metric(plan: QuestionPlan) -> bool:
    if plan.intent in {"ranking", "aggregation", "trend", "lookup"}:
        return True
    if plan.metric != "unknown":
        return True
    if plan.entity not in {"unknown"}:
        return True
    if plan.analysis != "basic":
        return True
    if plan.dimensions or plan.filters:
        return True
    return False


def plan_entities(plan: QuestionPlan | None) -> list[str]:
    """Values used to pre-filter knowledge chunks on the hybrid path."""
    if plan is None:
        return []
    values: list[str] = []
    for item in plan.filters:
        raw = getattr(item, "value", None)
        if raw is None:
            continue
        text = str(raw).strip()
        if text:
            values.append(text)
    for dim in plan.dimensions:
        if dim:
            values.append(str(dim))
    entity = getattr(plan, "entity", None)
    if entity and str(entity) not in {"unknown", "none"}:
        values.append(str(entity).replace("_", " "))
    seen: set[str] = set()
    out: list[str] = []
    for value in values:
        key = value.casefold()
        if key not in seen:
            seen.add(key)
            out.append(value)
    return out


def knowledge_narrative(hits: list[Any], *, max_chars: int = 900) -> str:
    if not hits:
        return (
            "No matching passages were found in the knowledge base. "
            "Upload a report or try a more specific document question."
        )
    parts: list[str] = []
    for hit in hits[:3]:
        snippet = str(getattr(hit, "snippet", "") or "").strip()
        title = str(getattr(hit, "title", "") or "Document").strip()
        if snippet:
            parts.append(f"{title}: {snippet}")
    text = " ".join(parts).strip()
    if len(text) > max_chars:
        text = text[: max_chars - 1].rsplit(" ", 1)[0] + "…"
    return text or "Retrieved document passages, but they were empty."
