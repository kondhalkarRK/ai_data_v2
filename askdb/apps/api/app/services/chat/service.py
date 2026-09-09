"""Chat orchestration with SSE events."""

from __future__ import annotations

import json
import time
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncSession

from app.analytics.sql_guardrails import sql_is_safe
from app.core.config import Industry, Settings
from app.core.exceptions import GuardrailViolationError, ValidationError
from app.models.activity import Conversation, LlmUsage, QueryHistory, SavedQuestion
from app.models.user import User
from app.services.chat.templates import resolve_template
from app.services.chat.trust import compute_trust_score
from app.services.llm import complete_chat


def _jsonable(value: Any) -> Any:
    if isinstance(value, Decimal):
        return float(value)
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return value


def _sse(event: str, data: dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(data, default=str)}\n\n"


class ChatService:
    def __init__(
        self,
        *,
        app_session: AsyncSession,
        analytics: AsyncConnection,
        settings: Settings,
        user: User,
        industry: Industry,
    ) -> None:
        self._app = app_session
        self._analytics = analytics
        self._settings = settings
        self._user = user
        self._industry = industry

    async def ask_stream(
        self, question: str, conversation_id: uuid.UUID | None
    ) -> AsyncIterator[str]:
        started = time.perf_counter()
        question = (question or "").strip()
        if not question:
            raise ValidationError("Question is required.")

        history_id = uuid.uuid4()
        yield _sse("stage", {"stage": "accepted", "historyId": str(history_id)})

        conversation = await self._ensure_conversation(conversation_id, question)
        yield _sse(
            "stage",
            {
                "stage": "planning",
                "conversationId": str(conversation.id),
            },
        )

        hit = resolve_template(self._industry, question)
        sql_text: str | None = None
        path = "fallback"
        glossary_matches = 0
        narrative = ""

        if hit is not None:
            sql_text = hit.sql
            path = hit.path
            glossary_matches = hit.glossary_matches
            narrative = f"Answered with governed template: {hit.title}."
            yield _sse("stage", {"stage": "template", "title": hit.title})
        else:
            yield _sse("stage", {"stage": "llm"})
            llm = await complete_chat(
                settings=self._settings,
                industry=self._industry,
                question=question,
            )
            if llm.sql:
                sql_text = llm.sql
                path = "semantic_llm"
                glossary_matches = 1
                narrative = llm.narrative or "Generated with the configured language model."
                await self._record_usage(llm.model, llm.prompt_tokens, llm.completion_tokens)
            else:
                narrative = llm.narrative or (
                    "No matching governed template and no LLM key is configured. "
                    "Try questions like 'loss ratio', 'claims by status', "
                    "'revenue by month', or 'top models'."
                )
                path = "fallback"

        if sql_text:
            ok, reason = sql_is_safe(sql_text)
            if not ok:
                raise GuardrailViolationError(reason)
            yield _sse("sql", {"sql": sql_text, "path": path})

            result = await self._analytics.execute(text(sql_text))
            mappings = result.mappings().all()
            capped = mappings[: self._settings.sql_max_result_rows]
            columns = list(capped[0].keys()) if capped else list(result.keys())
            rows = [{key: _jsonable(value) for key, value in row.items()} for row in capped]
            yield _sse("columns", {"columns": columns})
            yield _sse(
                "rows",
                {
                    "rows": rows,
                    "rowCount": len(rows),
                    "truncated": len(mappings) > len(rows),
                },
            )
            if rows and len(columns) >= 2:
                yield _sse(
                    "chart",
                    {
                        "type": "bar",
                        "x": columns[0],
                        "y": columns[1],
                        "points": rows[:20],
                    },
                )
            score, breakdown = compute_trust_score(
                glossary_matches=glossary_matches,
                glossary_hints_are_sql=True,
                resolution_path=path,
                row_count=len(rows),
            )
        else:
            rows = []
            score, breakdown = compute_trust_score(
                glossary_matches=0,
                glossary_hints_are_sql=False,
                resolution_path=path,
                row_count=0,
            )

        for token in narrative.split(" "):
            yield _sse("token", {"token": token + " "})

        yield _sse("trust", {"score": score, "breakdown": breakdown})
        latency_ms = int((time.perf_counter() - started) * 1000)
        await self._persist_history(
            history_id=history_id,
            conversation_id=conversation.id,
            question=question,
            sql_text=sql_text,
            row_count=len(rows),
            trust_score=score,
            trust_breakdown=breakdown,
            latency_ms=latency_ms,
            status="completed",
        )
        yield _sse(
            "done",
            {
                "historyId": str(history_id),
                "conversationId": str(conversation.id),
                "latencyMs": latency_ms,
                "trustScore": score,
            },
        )

    async def list_history(self, *, limit: int = 50) -> list[QueryHistory]:
        result = await self._app.execute(
            select(QueryHistory)
            .where(QueryHistory.user_id == self._user.id)
            .where(QueryHistory.industry == self._industry.value)
            .order_by(QueryHistory.created_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def list_saved(self) -> list[SavedQuestion]:
        result = await self._app.execute(
            select(SavedQuestion)
            .where(SavedQuestion.user_id == self._user.id)
            .where(SavedQuestion.industry == self._industry.value)
            .order_by(SavedQuestion.created_at.desc())
        )
        return list(result.scalars().all())

    async def save_question(
        self, *, title: str, question: str, sql_text: str | None
    ) -> SavedQuestion:
        row = SavedQuestion(
            id=uuid.uuid4(),
            user_id=self._user.id,
            industry=self._industry.value,
            title=title[:240],
            question=question,
            sql_text=sql_text,
        )
        self._app.add(row)
        await self._app.flush()
        return row

    async def cost_summary(self) -> dict[str, Any]:
        result = await self._app.execute(
            select(LlmUsage)
            .where(LlmUsage.user_id == self._user.id)
            .order_by(LlmUsage.created_at.desc())
            .limit(200)
        )
        rows = list(result.scalars().all())
        total_tokens = sum(row.total_tokens for row in rows)
        total_cost = float(sum(float(row.estimated_cost_usd) for row in rows))
        return {
            "calls": len(rows),
            "totalTokens": total_tokens,
            "estimatedCostUsd": round(total_cost, 6),
            "recent": [
                {
                    "id": str(row.id),
                    "model": row.model,
                    "purpose": row.purpose,
                    "totalTokens": row.total_tokens,
                    "estimatedCostUsd": float(row.estimated_cost_usd),
                    "createdAt": row.created_at.isoformat(),
                }
                for row in rows[:20]
            ],
        }

    async def _ensure_conversation(
        self, conversation_id: uuid.UUID | None, question: str
    ) -> Conversation:
        if conversation_id is not None:
            existing = await self._app.get(Conversation, conversation_id)
            if existing and existing.user_id == self._user.id:
                existing.updated_at = datetime.now(UTC)
                return existing
        conversation = Conversation(
            id=uuid.uuid4(),
            user_id=self._user.id,
            industry=self._industry.value,
            title=question[:80],
        )
        self._app.add(conversation)
        await self._app.flush()
        return conversation

    async def _persist_history(self, **kwargs: Any) -> None:
        row = QueryHistory(
            id=kwargs["history_id"],
            user_id=self._user.id,
            conversation_id=kwargs["conversation_id"],
            industry=self._industry.value,
            question=kwargs["question"],
            sql_text=kwargs["sql_text"],
            status=kwargs["status"],
            row_count=kwargs["row_count"],
            trust_score=kwargs["trust_score"],
            trust_breakdown=kwargs["trust_breakdown"],
            latency_ms=kwargs["latency_ms"],
        )
        self._app.add(row)
        await self._app.flush()

    async def _record_usage(self, model: str, prompt_tokens: int, completion_tokens: int) -> None:
        total = prompt_tokens + completion_tokens
        # Rough placeholder pricing for analytics; replaced when provider billing is wired.
        cost = total * 0.000002
        self._app.add(
            LlmUsage(
                id=uuid.uuid4(),
                user_id=self._user.id,
                industry=self._industry.value,
                model=model,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                total_tokens=total,
                estimated_cost_usd=cost,
                purpose="chat",
            )
        )
        await self._app.flush()
