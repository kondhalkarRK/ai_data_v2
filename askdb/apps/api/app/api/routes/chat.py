"""Chat SSE and activity routes."""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from typing import Annotated, Any

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from pydantic import Field
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncSession

from app.api.deps import (
    ActiveIndustry,
    RequireAnalyst,
    RequireViewer,
    get_app_session,
    get_app_settings,
    get_registry,
    get_semantic_service,
)
from app.core.config import Settings
from app.core.exceptions import NqlError
from app.db.session import DatabaseRegistry
from app.schemas.common import ApiModel
from app.semantic.service import SemanticService
from app.services.chat.profiler import PROFILER
from app.services.chat.query_cache import QUERY_CACHE
from app.services.chat.service import ChatService
from app.services.llm import circuit_stats, model_catalog

router = APIRouter(tags=["chat"])
_cancel_requested: set[uuid.UUID] = set()


class AskRequest(ApiModel):
    question: str = Field(min_length=1, max_length=4000)
    conversation_id: uuid.UUID | None = None
    web_retrieval: bool = False
    model: str | None = None
    temperature: float | None = Field(default=None, ge=0.0, le=1.5)
    top_p: float | None = Field(default=None, ge=0.0, le=1.0)
    top_k: int | None = Field(default=None, ge=1, le=200)


class SaveQuestionRequest(ApiModel):
    title: str = Field(min_length=1, max_length=240)
    question: str = Field(min_length=1, max_length=4000)
    sql_text: str | None = None


async def _analytics(
    industry: ActiveIndustry,
    registry: Annotated[DatabaseRegistry, Depends(get_registry)],
) -> AsyncIterator[AsyncConnection]:
    async with registry.analytics_connection(industry) as connection:
        yield connection


@router.post("/chat/ask")
async def chat_ask(
    body: AskRequest,
    user: RequireAnalyst,
    industry: ActiveIndustry,
    session: Annotated[AsyncSession, Depends(get_app_session)],
    settings: Annotated[Settings, Depends(get_app_settings)],
    analytics: Annotated[AsyncConnection, Depends(_analytics)],
    semantic_service: Annotated[SemanticService, Depends(get_semantic_service)],
) -> StreamingResponse:
    service = ChatService(
        app_session=session,
        analytics=analytics,
        settings=settings,
        user=user,
        industry=industry,
        semantic_service=semantic_service,
    )

    async def event_stream() -> AsyncIterator[bytes]:
        try:
            async for frame in service.ask_stream(
                body.question,
                body.conversation_id,
                cancel_requested=_cancel_requested,
                web_retrieval=body.web_retrieval,
                model_override=body.model,
                temperature=body.temperature,
                top_p=body.top_p,
                top_k=body.top_k,
            ):
                yield frame.encode("utf-8")
        except NqlError as exc:
            payload = (
                f"event: error\ndata: "
                f'{{"code":"{exc.code}","message":{json_quote(exc.message)}}}\n\n'
            )
            yield payload.encode("utf-8")

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


@router.post("/chat/cancel/{history_id}")
async def cancel_chat(
    history_id: uuid.UUID,
    user: RequireAnalyst,
    industry: ActiveIndustry,
    session: Annotated[AsyncSession, Depends(get_app_session)],
    settings: Annotated[Settings, Depends(get_app_settings)],
    analytics: Annotated[AsyncConnection, Depends(_analytics)],
) -> dict[str, Any]:
    _cancel_requested.add(history_id)
    service = ChatService(
        app_session=session,
        analytics=analytics,
        settings=settings,
        user=user,
        industry=industry,
    )
    updated = await service.cancel(history_id)
    return {"historyId": str(history_id), "status": "cancelled", "updated": updated}


def json_quote(value: str) -> str:
    import json

    return json.dumps(value)


@router.get("/history")
async def query_history(
    user: RequireViewer,
    industry: ActiveIndustry,
    session: Annotated[AsyncSession, Depends(get_app_session)],
    settings: Annotated[Settings, Depends(get_app_settings)],
    analytics: Annotated[AsyncConnection, Depends(_analytics)],
) -> list[dict[str, Any]]:
    service = ChatService(
        app_session=session,
        analytics=analytics,
        settings=settings,
        user=user,
        industry=industry,
    )
    rows = await service.list_history()
    return [
        {
            "id": str(row.id),
            "question": row.question,
            "sqlText": row.sql_text,
            "status": row.status,
            "rowCount": row.row_count,
            "trustScore": row.trust_score,
            "latencyMs": row.latency_ms,
            "createdAt": row.created_at.isoformat(),
        }
        for row in rows
    ]


@router.get("/questions")
async def list_saved_questions(
    user: RequireViewer,
    industry: ActiveIndustry,
    session: Annotated[AsyncSession, Depends(get_app_session)],
    settings: Annotated[Settings, Depends(get_app_settings)],
    analytics: Annotated[AsyncConnection, Depends(_analytics)],
) -> list[dict[str, Any]]:
    service = ChatService(
        app_session=session,
        analytics=analytics,
        settings=settings,
        user=user,
        industry=industry,
    )
    rows = await service.list_saved()
    return [
        {
            "id": str(row.id),
            "title": row.title,
            "question": row.question,
            "sqlText": row.sql_text,
            "isShared": row.is_shared,
            "createdAt": row.created_at.isoformat(),
        }
        for row in rows
    ]


@router.post("/questions")
async def save_question(
    body: SaveQuestionRequest,
    user: RequireViewer,
    industry: ActiveIndustry,
    session: Annotated[AsyncSession, Depends(get_app_session)],
    settings: Annotated[Settings, Depends(get_app_settings)],
    analytics: Annotated[AsyncConnection, Depends(_analytics)],
) -> dict[str, Any]:
    service = ChatService(
        app_session=session,
        analytics=analytics,
        settings=settings,
        user=user,
        industry=industry,
    )
    row = await service.save_question(
        title=body.title, question=body.question, sql_text=body.sql_text
    )
    return {"id": str(row.id), "title": row.title}


@router.get("/chat/profiler")
async def chat_profiler(
    user: RequireAnalyst,
    limit: int = 50,
) -> dict[str, Any]:
    """Last N NLQ executions + stage percentiles (POC ring buffer)."""
    del user
    return {
        "recent": PROFILER.recent(limit=min(limit, 100)),
        "stagePercentiles": PROFILER.stage_percentiles(),
        "errorRates": PROFILER.error_rates(),
        "queryCache": QUERY_CACHE.stats(),
        "llmCircuit": circuit_stats(),
        "note": (
            "Process-local POC store. Production should export p50/p95/p99 "
            "and error rates to a durable metrics backend."
        ),
    }


@router.get("/llm/controls")
async def llm_controls(
    user: RequireAnalyst,
    settings: Annotated[Settings, Depends(get_app_settings)],
) -> dict[str, Any]:
    del user
    catalog = model_catalog(settings)
    return {
        "defaultModel": settings.llm_default_model,
        "fallbackModel": (settings.llm_fallback_model or "").strip() or None,
        "defaultTemperature": settings.llm_temperature,
        "monthlyBudgetUsd": settings.llm_monthly_budget_usd,
        "models": catalog,
        "parameterHelp": {
            "temperature": (
                "Controls how predictable vs. varied the model's answers are. "
                "Lower values (e.g. 0.1–0.3) make answers more consistent and literal — "
                "recommended for SQL generation."
            ),
            "topP": (
                "Limits how many possible next words the model considers, based on "
                "cumulative probability. Most providers recommend adjusting either "
                "Temperature or Top-P — not both at once."
            ),
            "topK": (
                "Limits the model to choosing from only its K most likely next words. "
                "Not all models support this parameter — it is disabled when unsupported."
            ),
        },
    }


@router.get("/cost")
async def cost_analytics(
    user: RequireAnalyst,
    industry: ActiveIndustry,
    session: Annotated[AsyncSession, Depends(get_app_session)],
    settings: Annotated[Settings, Depends(get_app_settings)],
    analytics: Annotated[AsyncConnection, Depends(_analytics)],
) -> dict[str, Any]:
    service = ChatService(
        app_session=session,
        analytics=analytics,
        settings=settings,
        user=user,
        industry=industry,
    )
    return await service.cost_summary()
