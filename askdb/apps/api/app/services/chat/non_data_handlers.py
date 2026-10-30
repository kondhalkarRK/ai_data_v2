"""Answers for messages that never run SQL: chat, general knowledge, app help, documents.

LLM replies go through ``complete_text`` (circuit breaker, timeout) and return token
counts so the caller can record usage. APP_HELP is deterministic: it only repeats the
approved semantic pack and glossary for the active industry.
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass
from typing import Any

from app.core.config import Industry, Settings
from app.services.chat.message_classifier import template_general_chat
from app.services.llm import active_llm, complete_text
from app.services.security.region_scope import RegionScope


@dataclass(slots=True)
class LlmReply:
    text: str
    model: str = ""
    prompt_tokens: int = 0
    completion_tokens: int = 0
    tokens_estimated: bool = False
    latency_ms: int = 0
    used_llm: bool = False


def estimate_tokens(text: str) -> int:
    return max(1, (len(text or "") + 3) // 4)


_GENERAL_CHAT_SYSTEM = (
    "You are Ask DB, a governed {industry} analytics assistant. Reply to small talk in one "
    "or two short, friendly sentences. Never state, guess or imply anything about the "
    "user's data, numbers or business. If asked for a joke, tell one short, clean, "
    "work-appropriate joke. You may invite the user to ask a {industry} data question."
)
_GENERAL_KNOWLEDGE_SYSTEM = (
    "Answer the general-knowledge question briefly and accurately in at most four "
    "sentences. You have NOT checked any database. Never state or imply facts about the "
    "user's company, data, metrics or results, and never say or suggest that you looked "
    "anything up in their data. If the question needs current or live information, say "
    "you don't have live data."
)
_KNOWLEDGE_FALLBACK = (
    "I can't answer general questions right now. I can still help with governed "
    "{industry} data questions."
)


async def _llm(
    settings: Settings,
    *,
    system: str,
    user: str,
    max_tokens: int,
    temperature: float,
) -> LlmReply | None:
    model = (settings.chat_classifier_model or "").strip() or active_llm(settings).model
    t0 = time.perf_counter()
    result = await complete_text(
        settings=settings,
        system=system,
        user=user,
        max_tokens=max_tokens,
        model_override=model,
        temperature=temperature,
    )
    latency = int((time.perf_counter() - t0) * 1000)
    text = (result.content or "").strip()
    # complete_text flags every non-SQL reply with an "empty SQL" error; content is what counts.
    if result.timed_out or result.circuit_open or not text:
        if result.prompt_tokens or result.completion_tokens:
            return LlmReply("", model, result.prompt_tokens, result.completion_tokens,
                            latency_ms=latency, used_llm=True)
        return None
    estimated = not (result.prompt_tokens or result.completion_tokens)
    return LlmReply(
        text=text,
        model=model,
        prompt_tokens=result.prompt_tokens or estimate_tokens(system + user),
        completion_tokens=result.completion_tokens or estimate_tokens(text),
        tokens_estimated=estimated,
        latency_ms=latency,
        used_llm=True,
    )


async def general_chat_reply(
    settings: Settings,
    *,
    industry: Industry,
    question: str,
    reason: str,
    last_turn_failed: bool,
) -> LlmReply:
    """Short LLM small-talk reply; templates when the LLM is unavailable or after a failure."""
    if reason == "joke_request" and last_turn_failed:
        return LlmReply(
            "Let's get your data question sorted first. Try rephrasing it or pick a "
            "suggested question."
        )
    if reason in {"greeting", "thanks"}:
        return LlmReply(template_general_chat(reason))
    reply = await _llm(
        settings,
        system=_GENERAL_CHAT_SYSTEM.format(industry=industry.value),
        user=question,
        max_tokens=settings.chat_general_max_completion_tokens,
        temperature=0.7 if reason == "joke_request" else 0.3,
    )
    if reply is None or not reply.text:
        fallback = LlmReply(template_general_chat(reason))
        if reply is not None:
            fallback.model, fallback.used_llm = reply.model, True
            fallback.prompt_tokens, fallback.completion_tokens = (
                reply.prompt_tokens, reply.completion_tokens,
            )
        return fallback
    return reply


async def general_knowledge_reply(
    settings: Settings, *, industry: Industry, question: str
) -> LlmReply:
    reply = await _llm(
        settings,
        system=_GENERAL_KNOWLEDGE_SYSTEM,
        user=question,
        max_tokens=max(settings.chat_general_max_completion_tokens, 200),
        temperature=0.2,
    )
    if reply is None or not reply.text:
        fallback = LlmReply(_KNOWLEDGE_FALLBACK.format(industry=industry.value))
        if reply is not None:
            fallback.model, fallback.used_llm = reply.model, True
            fallback.prompt_tokens, fallback.completion_tokens = (
                reply.prompt_tokens, reply.completion_tokens,
            )
        return fallback
    reply.text += "\n\n(General knowledge, not from your data.)"
    return reply


def no_documents_reply() -> str:
    return (
        "No documents have been uploaded for this workspace, so there's nothing to "
        "summarise yet. Upload a document in Knowledge, or ask a question about your data."
    )


# ── APP_HELP (deterministic, metadata only) ──────────────────────────────────

_TERM_PATTERNS = (
    re.compile(r"what\s+does\s+(?P<a>.+?)\s+mean", re.I),
    re.compile(r"how\s+is\s+(?P<a>.+?)\s+(?:calculated|computed|defined|measured)", re.I),
    re.compile(r"difference\s+between\s+(?P<a>.+?)\s+and\s+(?P<b>.+?)(?:\s+here|\s+in\b|\?|$)", re.I),
    re.compile(r"how\s+do\s+i\s+ask\s+about\s+(?P<a>.+?)(?:\s+vs\.?\s+|\s+versus\s+|\s+and\s+)(?P<b>.+?)(?:\?|$)", re.I),
    re.compile(r"how\s+do\s+i\s+ask\s+about\s+(?P<a>.+?)(?:\?|$)", re.I),
    re.compile(r"^\s*(?:define|explain)\s+(?P<a>.+?)(?:\?|$)", re.I),
)
_TRAILING = re.compile(r"\b(?:in\s+this\s+(?:app|product|tool)|here|in\s+ask\s*db)\b.*$", re.I)


def _norm(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (text or "").lower()).strip()


def lookup_definition(term: str, pack: Any | None) -> tuple[str, str, list[str], list[str]] | None:
    """(label, definition, calculation rules, example questions) from the approved pack."""
    if pack is None or not term:
        return None
    wanted = _norm(_TRAILING.sub("", term))
    if not wanted:
        return None
    glossary = getattr(getattr(pack, "glossary", None), "terms", None) or {}
    for name, entry in glossary.items():
        names = {_norm(name), _norm(entry.display_label or ""), *(_norm(s) for s in entry.synonyms)}
        if wanted in names:
            return (
                entry.display_label or name,
                entry.definition,
                list(entry.calculation_rules),
                list(entry.example_questions),
            )
    measures = getattr(getattr(pack, "model", None), "measures", None) or {}
    for name, measure in measures.items():
        names = {_norm(name), _norm(measure.display_name), *(_norm(s) for s in measure.synonyms)}
        if wanted in names and measure.description:
            return measure.display_name, measure.description, [], []
    return None


def _definition_block(term: str, pack: Any | None, industry: Industry) -> str:
    found = lookup_definition(term, pack)
    clean = _TRAILING.sub("", term).strip(" ?.\"'")
    if found is None:
        return (
            f"There's no approved definition for \u201c{clean}\u201d in the "
            f"{industry.value} semantic layer, so I won't guess one."
        )
    label, definition, rules, examples = found
    lines = [f"**{label}**: {definition}"]
    if rules:
        lines.append("How it's calculated: " + "; ".join(rules[:3]))
    if examples:
        lines.append("Try asking: " + " | ".join(f"\u201c{q}\u201d" for q in examples[:2]))
    return "\n".join(lines)


def definition_from_metadata(term: str, pack: Any | None, industry: Industry) -> str:
    return _definition_block(term, pack, industry)


def _measure_labels(pack: Any | None) -> list[str]:
    measures = getattr(getattr(pack, "model", None), "measures", None) or {}
    return [m.display_name for m in measures.values()]


def _table_labels(pack: Any | None, allowed: dict[str, set[str]]) -> list[str]:
    tables = getattr(getattr(pack, "model", None), "tables", None) or {}
    labels = [
        t.display_name for t in tables.values() if str(t.physical_name).lower() in allowed
    ]
    return labels


def _region_dimensions(pack: Any | None) -> list[str]:
    dims = getattr(getattr(pack, "model", None), "dimensions", None) or {}
    return [
        d.display_name for name, d in dims.items()
        if re.search(r"region|zone|state|city|territor", name + " " + d.display_name, re.I)
    ]


def app_help_reply(
    question: str,
    *,
    industry: Industry,
    pack: Any | None,
    allowed_schema: dict[str, set[str]],
    scope: RegionScope,
) -> str:
    q = (question or "").strip()
    if pack is None:
        return (
            f"The {industry.value} semantic layer isn't available right now, so I can't "
            "describe its metrics. Please try again shortly."
        )
    low = q.lower()

    if re.search(r"\bregions?\b|\bzones?\b|\bterritor", low):
        dims = _region_dimensions(pack)
        if scope.unrestricted:
            access = "You can see all regions."
        else:
            access = "Your access is limited to: " + ", ".join(scope.zones) + "."
        geo = ", ".join(dims) if dims else "no geographic dimensions"
        return f"The {industry.value} semantic layer has these geographic dimensions: {geo}. {access}"

    if re.search(r"\btables?\b|\bdatasets?\b", low):
        labels = _table_labels(pack, allowed_schema)
        return (
            f"You can ask about these {industry.value} tables: " + ", ".join(labels) + ". "
            "Ask in plain language; I'll pick the tables for you."
        )

    for pattern in _TERM_PATTERNS:
        match = pattern.search(q)
        if match is None:
            continue
        parts = [match.group("a")]
        if "b" in match.groupdict() and match.group("b"):
            parts.append(match.group("b"))
        blocks = [_definition_block(part, pack, industry) for part in parts]
        if pattern.pattern.startswith("how\\s+do\\s+i\\s+ask"):
            blocks.append(
                "Ask about each one by name with a period, for example "
                f"\u201c{parts[0].strip()} by month this year\u201d."
            )
        return "\n\n".join(blocks)

    measures = _measure_labels(pack)
    intro = (
        "In Ask DB, KPIs are the governed measures defined in the semantic layer."
        if re.search(r"\bkpis?\b", low)
        else f"These metrics are available for {industry.value}:"
    )
    return f"{intro} " + ", ".join(measures) + "."
