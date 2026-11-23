"""Chat SSE and activity routes."""

from __future__ import annotations

import json
import logging
import time
import uuid
from collections.abc import AsyncIterator
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from pydantic import ConfigDict, Field
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncSession

from app.api.deps import (
    ActiveIndustry,
    RegionScopeDep,
    RequireAdmin,
    RequireUser,
    get_app_session,
    get_app_settings,
    get_optional_scoped_analytics,
    get_semantic_service,
)
from app.core.config import Industry, Settings
from app.core.exceptions import AuthorizationError, NotFoundError, NqlError
from app.models import ChatRating, Conversation, QueryHistory
from app.models.enums import Role
from app.models.user import User
from app.schemas.common import ApiModel
from app.semantic.service import SemanticService
from app.services.chat.profiler import PROFILER
from app.services.chat.query_cache import QUERY_CACHE
from app.services.chat.responses import (
    check_access,
    owned_response,
    rating_payload,
    save_rating,
    scope_key,
)
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
    use_documents: bool = False
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


async def _save_response(session, service, user, frames):
    """Persist the rendered answer once, tied to its existing query-history ID."""
    row = service.last_history
    if row is None:
        return
    events = _sse_events_from_frames(frames)
    # Progress frames are transient. Fold tokens to avoid thousands of JSON objects.
    text = "".join(str(e["data"].get("token", "")) for e in events if e["event"] == "token")
    stored = [e for e in events if e["event"] not in {"token", "progress", "stage"}]
    if text:
        stored.insert(0, {"event": "token", "data": {"token": text}})
    documents = sorted(
        {
            str(e["data"]["documentId"])
            for e in events
            if e["event"] == "citation" and e["data"].get("documentId")
        }
    )
    row.response_snapshot = {
        "version": 1,
        "scope": scope_key(user, service._region_scope),
        "events": stored,
        "documents": documents,
    }
    conversation = await session.get(Conversation, row.conversation_id)
    if conversation:
        conversation.updated_at = func.now()
    await session.commit()


class SaveQuestionRequest(ApiModel):
    title: str = Field(min_length=1, max_length=240)
    question: str = Field(min_length=1, max_length=4000)
    sql_text: str | None = None


OptionalAnalyticsConnection = Annotated[AsyncConnection | None, Depends(get_optional_scoped_analytics)]


@router.post("/chat/ask")
async def chat_ask(
    body: AskRequest,
    user: RequireUser,
    industry: ActiveIndustry,
    session: Annotated[AsyncSession, Depends(get_app_session)],
    settings: Annotated[Settings, Depends(get_app_settings)],
    analytics: OptionalAnalyticsConnection,
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
        frames: list[str] = []
        try:
            async for frame in service.ask_stream(
                body.question,
                body.conversation_id,
                cancel_requested=_cancel_requested,
                web_retrieval=body.web_retrieval,
                use_documents=body.use_documents,
            ):
                frames.append(frame)
                yield frame.encode("utf-8")
        except NqlError as exc:
            payload = (
                f"event: error\ndata: "
                f'{{"code":"{exc.code}","message":{json_quote(exc.message)}}}\n\n'
            )
            frames.append(payload)
            yield payload.encode("utf-8")
        except Exception:
            logger.exception("chat_ask failed unexpectedly")
            for frame in recovery_frames(industry):
                frames.append(frame)
                yield frame.encode("utf-8")
        finally:
            await _save_response(session, service, user, frames)
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
    analytics: OptionalAnalyticsConnection,
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
            use_documents=body.use_documents,
        ):
            frames.append(frame)
    except NqlError as exc:
        frames.extend(
            [
                f"event: error\ndata: {json.dumps({'code': exc.code, 'message': exc.message})}\n\n",
                'event: done\ndata: {"failed":true}\n\n',
            ]
        )
    except Exception:
        logger.exception("chat_ask_sync failed unexpectedly")
        frames.extend(recovery_frames(industry))
    finally:
        await _save_response(session, service, user, frames)
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


class RatingRequest(ApiModel):
    model_config = ConfigDict(extra="forbid")
    rating: Literal["up", "down"]
    reason: Literal["incorrect", "misunderstood", "incomplete", "unclear", "other"] | None = None
    note: str | None = Field(default=None, max_length=2000)


@router.get("/chat/conversations")
async def conversations(
    user: RequireUser,
    industry: ActiveIndustry,
    session: Annotated[AsyncSession, Depends(get_app_session)],
):
    rows = (
        await session.scalars(
            select(Conversation)
            .where(
                Conversation.user_id == user.id,
                Conversation.industry == industry.value,
            )
            .order_by(Conversation.updated_at.desc(), Conversation.id.desc())
            .limit(201)
        )
    ).all()
    return {
        "items": [
            {"id": str(r.id), "title": r.title, "updatedAt": r.updated_at.isoformat()}
            for r in rows[:200]
        ],
        "hasMore": len(rows) > 200,
    }


@router.get("/chat/conversations/{conversation_id}")
async def conversation_response(
    conversation_id: uuid.UUID,
    user: RequireUser,
    industry: ActiveIndustry,
    scope: RegionScopeDep,
    session: Annotated[AsyncSession, Depends(get_app_session)],
    settings: Annotated[Settings, Depends(get_app_settings)],
):
    conversation = await session.scalar(
        select(Conversation).where(
            Conversation.id == conversation_id,
            Conversation.user_id == user.id,
            Conversation.industry == industry.value,
        )
    )
    if conversation is None:
        raise NotFoundError("This conversation is not available.")
    rows = (
        await session.scalars(
            select(QueryHistory)
            .where(
                QueryHistory.conversation_id == conversation_id,
                QueryHistory.user_id == user.id,
                QueryHistory.industry == industry.value,
            )
            .order_by(QueryHistory.created_at.desc(), QueryHistory.id.desc())
            .limit(201)
        )
    ).all()
    ratings = {
        r.response_id: rating_payload(r)
        for r in (
            await session.scalars(
                select(ChatRating).where(
                    ChatRating.user_id == user.id,
                    ChatRating.response_id.in_([r.id for r in rows[:200]]),
                )
            )
        ).all()
    }
    turns = []
    for row in reversed(rows[:200]):
        unavailable = None
        try:
            await check_access(session, row, user, industry, scope, settings)
        except AuthorizationError as exc:
            unavailable = exc.message
        events = (row.response_snapshot or {}).get("events") if not unavailable else None
        if events is None:
            events = [
                {
                    "event": "token",
                    "data": {
                        "token": unavailable
                        or "This earlier response has no saved answer content. "
                        "Ask again to get a current answer."
                    },
                },
                {"event": "meta", "data": {"rowCount": 0}},
            ]
        turns.append(
            {
                "responseId": str(row.id),
                "question": row.question,
                "events": events,
                "rating": ratings.get(row.id) if not unavailable else None,
                "canRate": row.status != "running" and not unavailable,
            }
        )
    return {"id": str(conversation.id), "turns": turns, "hasMore": len(rows) > 200}


@router.get("/chat/responses/{response_id}/rating")
async def response_rating(
    response_id: uuid.UUID,
    user: RequireUser,
    industry: ActiveIndustry,
    scope: RegionScopeDep,
    session: Annotated[AsyncSession, Depends(get_app_session)],
    settings: Annotated[Settings, Depends(get_app_settings)],
):
    row = await owned_response(session, response_id, user, industry)
    await check_access(session, row, user, industry, scope, settings)
    return {
        "responseId": str(row.id),
        "feedback": rating_payload(await session.get(ChatRating, (row.id, user.id))),
    }


@router.put("/chat/responses/{response_id}/rating")
async def update_response_rating(
    response_id: uuid.UUID,
    body: RatingRequest,
    user: RequireUser,
    industry: ActiveIndustry,
    scope: RegionScopeDep,
    session: Annotated[AsyncSession, Depends(get_app_session)],
    settings: Annotated[Settings, Depends(get_app_settings)],
):
    row = await owned_response(session, response_id, user, industry)
    await check_access(session, row, user, industry, scope, settings)
    return {"responseId": str(row.id), "feedback": await save_rating(session, row, user, body)}


@router.delete("/chat/responses/{response_id}/rating")
async def delete_response_rating(
    response_id: uuid.UUID,
    user: RequireUser,
    industry: ActiveIndustry,
    scope: RegionScopeDep,
    session: Annotated[AsyncSession, Depends(get_app_session)],
    settings: Annotated[Settings, Depends(get_app_settings)],
):
    row = await owned_response(session, response_id, user, industry)
    await check_access(session, row, user, industry, scope, settings)
    await session.execute(
        delete(ChatRating).where(ChatRating.response_id == row.id, ChatRating.user_id == user.id)
    )
    await session.commit()
    return {"responseId": str(row.id), "feedback": None}


@router.post("/chat/cancel/{history_id}")
async def cancel_chat(
    history_id: uuid.UUID,
    user: RequireUser,
    industry: ActiveIndustry,
    session: Annotated[AsyncSession, Depends(get_app_session)],
    settings: Annotated[Settings, Depends(get_app_settings)],
    analytics: AnalyticsConnection,
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
    analytics: AnalyticsConnection,
) -> list[dict[str, Any]]:
    service = ChatService(
        app_session=session,
        analytics=analytics,
        settings=settings,
        user=user,
        industry=industry,
    )
    rows = await service.list_history()
    usernames: dict[uuid.UUID, str] = {}
    if user.role == Role.ADMIN and rows:
        user_ids = {row.user_id for row in rows}
        result = await session.execute(select(User.id, User.username).where(User.id.in_(user_ids)))
        usernames = {uid: name for uid, name in result.all()}
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
            **(
                {"userId": str(row.user_id), "username": usernames.get(row.user_id, "—")}
                if user.role == Role.ADMIN
                else {}
            ),
        }
        for row in rows
    ]


@router.get("/questions")
async def list_saved_questions(
    user: RequireUser,
    industry: ActiveIndustry,
    session: Annotated[AsyncSession, Depends(get_app_session)],
    settings: Annotated[Settings, Depends(get_app_settings)],
    analytics: AnalyticsConnection,
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
    analytics: AnalyticsConnection,
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
    governed = active_llm(settings)
    return {
        "defaultProvider": governed.provider,
        "defaultModel": governed.model,
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
    analytics: AnalyticsConnection,
) -> dict[str, Any]:
    service = ChatService(
        app_session=session,
        analytics=analytics,
        settings=settings,
        user=user,
        industry=industry,
    )
    return await service.cost_summary()
