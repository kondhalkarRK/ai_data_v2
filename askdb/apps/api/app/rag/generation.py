"""Grounded LLM answers from authorized document passages only."""

from __future__ import annotations

import logging
from typing import Any, Sequence

from app.core.config import Settings
from app.services.chat.non_data_handlers import LlmReply, estimate_tokens
from app.services.llm import active_llm, complete_text

logger = logging.getLogger(__name__)

_SYSTEM = (
    "You are Ask Me's document assistant. Answer ONLY using the provided evidence "
    "passages. If the evidence does not contain the answer, say clearly that the "
    "documents do not contain enough information. Do not invent facts, numbers, or "
    "citations. Prefer concise business language."
)


def _passage_fields(hit: Any) -> tuple[str, str, str]:
    if isinstance(hit, dict):
        title = str(hit.get("title") or "Document")
        locator = str(hit.get("locator") or "")
        snippet = str(hit.get("snippet") or hit.get("text") or "").strip()
        return title, locator, snippet
    title = str(getattr(hit, "title", None) or "Document")
    locator = str(getattr(hit, "locator", None) or "")
    snippet = str(
        getattr(hit, "snippet", None) or getattr(hit, "text", None) or ""
    ).strip()
    return title, locator, snippet


def extractive_fallback(passages: Sequence[Any], *, max_chars: int = 900) -> str:
    parts: list[str] = []
    for hit in passages[:3]:
        title, _, snippet = _passage_fields(hit)
        if snippet:
            parts.append(f"{title}: {snippet}")
    text = " ".join(parts).strip()
    if len(text) > max_chars:
        text = text[: max_chars - 1].rsplit(" ", 1)[0] + "…"
    return text or "Retrieved passages were empty."


async def grounded_document_reply(
    settings: Settings,
    *,
    question: str,
    passages: Sequence[Any],
    conversation_context: str | None = None,
) -> LlmReply:
    """One grounded LLM call. Passages must already be ACL-authorized."""
    if not passages:
        return LlmReply(
            "No relevant passages were found in documents you are allowed to access. "
            "Try a more specific question or ask an administrator to grant access."
        )
    evidence_lines: list[str] = []
    for index, hit in enumerate(passages[:8], start=1):
        title, locator, snippet = _passage_fields(hit)
        evidence_lines.append(f"[{index}] {title} ({locator})\n{snippet}")
    evidence = "\n\n".join(evidence_lines)
    user_parts = [f"Question: {question.strip()}"]
    if conversation_context:
        user_parts.append(f"Recent document context:\n{conversation_context[:1200]}")
    user_parts.append(f"Evidence passages:\n{evidence}")
    model = active_llm(settings).model
    try:
        result = await complete_text(
            settings=settings,
            system=_SYSTEM,
            user="\n\n".join(user_parts),
            max_tokens=min(500, settings.llm_max_completion_tokens),
            temperature=0.1,
        )
        text = (result.content or "").strip()
        if text and not result.timed_out and not result.circuit_open:
            return LlmReply(
                text,
                model=model,
                prompt_tokens=result.prompt_tokens or estimate_tokens("\n\n".join(user_parts)),
                completion_tokens=result.completion_tokens or estimate_tokens(text),
                tokens_estimated=not (result.prompt_tokens or result.completion_tokens),
                used_llm=True,
            )
    except Exception:
        logger.debug(
            "Grounded document LLM failed; falling back to extractive summary",
            exc_info=True,
        )
    return LlmReply(extractive_fallback(passages), model=model)
