"""Chat SSE and activity routes."""

from __future__ import annotations

import json
import logging
import time
import uuid
from collections.abc import AsyncIterator
from typing import Annotated, Any

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from pydantic import Field
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncSession

from app.api.deps import (
    ActiveIndustry,
    RequireAdmin,
    RequireUser,
    get_app_session,
    get_app_settings,
    get_registry,
    get_semantic_service,
)
from app.core.config import Industry, Settings
from app.core.exceptions import NqlError
from app.db.session import DatabaseRegistry
from app.models.user import User
from app.schemas.common import ApiModel
from app.semantic.service import SemanticService
from app.services.chat.profiler import PROFILER
from app.services.chat.query_cache import QUERY_CACHE
from app.services.chat.service import ChatService, recovery_frames
from app.services.governance import (
    active_llm,
    enforce_quota,
    execution_mode,
    record_question_usage,
    sync_llm_config,
)
from app.services.llm import circuit_stats, model_catalog

logger = logging.getLogger(__name__)
router = APIRouter(tags=["chat"])
_cancel_requested: set[uuid.UUID] = set()


class AskRequest(ApiModel):
    """Model, temperature and token limits are governed by the admin, not the client."""

    question: str = Field(min_length=1, max_length=4000)
    conversation_id: uuid.UUID | None = None
    web_retrieval: bool = False


async def _prepare_question(session: AsyncSession, settings: Settings, user: User) -> None:
    await sync_llm_config(session, settings)
    await enforce_quota(session, user)


async def _record_question(
    session: AsyncSession,
    settings: Settings,
    service: ChatService,
    *,
    user: User,
    question: str,
    industry: Industry,
    started: float,
) -> None:
    """Store one ``llm_usage`` row per question; never fails the answer."""
    profile = service.last_profile
    if profile is None:
        return
    tokens = service.usage_prompt_tokens + service.usage_completion_tokens
    llm_used = service.usage_llm_steps > 0 or profile.llm_calls > 0 or tokens > 0
    mode = execution_mode(cache_hit=profile.cache_hit, llm_used=llm_used, path=profile.path)
    history = service.last_history
    try:
        await record_question_usage(
            session,
            user_id=user.id,
            question=question,
            industry=industry.value,
            mode=mode,
            model_name=(service.usage_model or active_llm(settings).model) if llm_used else "none",
            prompt_tokens=service.usage_prompt_tokens,
            completion_tokens=service.usage_completion_tokens,
            response_time_ms=int((time.perf_counter() - started) * 1000),
            query_history_id=history.id if history is not None else None,
        )
        await session.commit()
    except Exception:
        logger.warning("could not record llm usage", exc_info=True)
        await session.rollback()


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
    user: RequireUser,
    industry: ActiveIndustry,
    session: Annotated[AsyncSession, Depends(get_app_session)],
    settings: Annotated[Settings, Depends(get_app_settings)],
    analytics: Annotated[AsyncConnection, Depends(_analytics)],
    semantic_service: Annotated[SemanticService, Depends(get_semantic_service)],
) -> StreamingResponse:
    await _prepare_question(session, settings, user)
    service = ChatService(
        app_session=session,
        analytics=analytics,
        settings=settings,
        user=user,
        industry=industry,
        semantic_service=semantic_service,
    )
    started = time.perf_counter()

    async def event_stream() -> AsyncIterator[bytes]:
        try:
            async for frame in service.ask_stream(
                body.question,
                body.conversation_id,
                cancel_requested=_cancel_requested,
                web_retrieval=body.web_retrieval,
            ):
                yield frame.encode("utf-8")
        except NqlError as exc:
            payload = (
                f"event: error\ndata: "
                f'{{"code":"{exc.code}","message":{json_quote(exc.message)}}}\n\n'
            )
            yield payload.encode("utf-8")
        except Exception:
            logger.exception("chat_ask failed unexpectedly")
            for frame in recovery_frames(industry):
                yield frame.encode("utf-8")
        finally:
            await _record_question(
                session,
                settings,
                service,
                user=user,
                question=body.question,
                industry=industry,
                started=started,
            )

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


def _sse_events_from_frames(frames: list[str]) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for frame in frames:
        event_name = "message"
        data_line = ""
        for line in frame.splitlines():
            if line.startswith("event:"):
                event_name = line[6:].strip()
            elif line.startswith("data:"):
                data_line += line[5:].strip()
        if not data_line:
            continue
        try:
            events.append({"event": event_name, "data": json.loads(data_line)})
        except json.JSONDecodeError:
            continue
    return events


@router.post("/chat/ask-sync")
async def chat_ask_sync(
    body: AskRequest,
    user: RequireUser,
    industry: ActiveIndustry,
    session: Annotated[AsyncSession, Depends(get_app_session)],
    settings: Annotated[Settings, Depends(get_app_settings)],
    analytics: Annotated[AsyncConnection, Depends(_analytics)],
    semantic_service: Annotated[SemanticService, Depends(get_semantic_service)],
) -> dict[str, Any]:
    """One JSON response for hosts (Vercel) that buffer SSE and never paint tokens."""
    await _prepare_question(session, settings, user)
    service = ChatService(
        app_session=session,
        analytics=analytics,
        settings=settings,
        user=user,
        industry=industry,
        semantic_service=semantic_service,
    )
    started = time.perf_counter()
    frames: list[str] = []
    try:
        async for frame in service.ask_stream(
            body.question,
            body.conversation_id,
            cancel_requested=_cancel_requested,
            web_retrieval=body.web_retrieval,
        ):
            frames.append(frame)
    except NqlError as exc:
        return {
            "events": [
                {"event": "error", "data": {"code": exc.code, "message": exc.message}},
                {"event": "done", "data": {"failed": True}},
            ]
        }
    except Exception:
        logger.exception("chat_ask_sync failed unexpectedly")
        return {"events": _sse_events_from_frames([*frames, *recovery_frames(industry)])}
    finally:
        await _record_question(
            session,
            settings,
            service,
            user=user,
            question=body.question,
            industry=industry,
            started=started,
        )
    return {"events": _sse_events_from_frames(frames)}


@router.post("/chat/cancel/{history_id}")
async def cancel_chat(
    history_id: uuid.UUID,
    user: RequireUser,
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
    user: RequireUser,
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
    user: RequireUser,
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
    user: RequireUser,
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
    user: RequireAdmin,
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
    user: RequireAdmin,
    settings: Annotated[Settings, Depends(get_app_settings)],
) -> dict[str, Any]:
    del user
    catalog = model_catalog(settings)
    return {
        "defaultModel": active_llm(settings).model,
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
    user: RequireUser,
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
