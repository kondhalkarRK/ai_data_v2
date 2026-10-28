"""ChatService integration tests for session memory (mocked NLQ execution)."""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy import select

from app.core.config import Industry, Settings
from app.models.activity import Conversation, QueryHistory
from app.models.enums import Role
from app.models.region_access import UserRegionAccess
from app.models.user import User
from app.services.chat.clarification import Clarification
from app.services.chat.conversation_context import plan_state
from app.services.chat.conversation_memory import (
    ResultMeta,
    build_analytical_context,
    empty_memory,
    set_pending_clarification,
)
from app.services.chat.pipeline import TurnPlan
from app.services.chat.question_understanding import ExtractedFilter, QuestionPlan
from app.services.chat.query_cache import CachedAnswer, QUERY_CACHE
from app.services.chat.service import ChatService
from app.services.chat.value_dictionary import ValueDictionarySnapshot


def _parse_sse(chunks: list[str]) -> list[tuple[str, dict]]:
    events: list[tuple[str, dict]] = []
    event_name = ""
    for chunk in chunks:
        for line in chunk.splitlines():
            if line.startswith("event: "):
                event_name = line[7:].strip()
            elif line.startswith("data: "):
                events.append((event_name, json.loads(line[6:])))
    return events


async def _collect_stream(service: ChatService, question: str, conv_id: uuid.UUID) -> list[tuple[str, dict]]:
    chunks: list[str] = []
    async for frame in service.ask_stream(question, conv_id):
        chunks.append(frame)
    return _parse_sse(chunks)


def _automotive_user() -> User:
    uid = uuid.uuid4()
    return User(
        id=uid,
        username=f"mem_{uid.hex[:8]}",
        email=f"{uid.hex[:8]}@example.com",
        email_normalized=f"{uid.hex[:8]}@example.com",
        full_name="Memory Test",
        password_hash="x" * 20,
        role=Role.USER,
        default_industry=Industry.AUTOMOTIVE,
        is_active=True,
    )


def _north_plan_state() -> dict:
    plan = QuestionPlan(
        industry=Industry.AUTOMOTIVE,
        metric="revenue",
        entity="metric_only",
        intent="aggregation",
        dimensions=("region",),
        filters=(
            ExtractedFilter(
                column="region_name",
                operator="=",
                value="North",
                values=("North",),
                label="North",
            ),
        ),
    )
    return plan_state(plan)


@pytest.fixture
async def memory_chat(db_session):
    user = _automotive_user()
    db_session.add(user)
    await db_session.flush()
    conv = Conversation(
        id=uuid.uuid4(),
        user_id=user.id,
        industry=Industry.AUTOMOTIVE.value,
        title="Memory test",
    )
    db_session.add(conv)
    await db_session.flush()

    analytics = AsyncMock()
    analytics.execute = AsyncMock()
    analytics.rollback = AsyncMock()

    semantic = MagicMock()
    semantic.get_pack = AsyncMock(return_value=None)

    settings = Settings()

    service = ChatService(
        app_session=db_session,
        analytics=analytics,
        settings=settings,
        user=user,
        industry=Industry.AUTOMOTIVE,
        semantic_service=semantic,
    )
    return service, conv, user


@pytest.fixture
async def scoped_memory_chat(memory_chat):
    service, conv, user = memory_chat
    service._app.add(UserRegionAccess(user_id=user.id, region_id="North"))
    await service._app.flush()
    await service._app.commit()
    return service, conv, user


def _stub_turn(*, question: str = "", prior_state: dict | None = None) -> TurnPlan:
    plan = QuestionPlan(
        industry=Industry.AUTOMOTIVE,
        metric="revenue",
        entity="metric_only",
        intent="aggregation",
        dimensions=("region",),
    )
    return TurnPlan(
        original=question,
        question=question or "stub",
        plan=plan,
        clarification=Clarification(kind="clarify", title="Need detail", message="Pick one"),
        contextual=bool(prior_state),
    )


@pytest.mark.asyncio
async def test_expired_memory_follow_up_clarifies(memory_chat) -> None:
    service, conv, _user = memory_chat
    mem = empty_memory(user_id=conv.user_id, conversation_id=conv.id)
    mem.analytical = build_analytical_context(
        plan=QuestionPlan(
            industry=Industry.AUTOMOTIVE,
            metric="revenue",
            entity="metric_only",
            intent="aggregation",
            dimensions=("region",),
        ),
        question="Revenue by region",
        result_meta=ResultMeta(),
        prior=None,
    )
    mem.analytical.turn_counter = 99
    conv.session_memory = mem.to_dict()
    await service._save_session_memory(conv, mem)
    await service._app.commit()

    with patch("app.services.chat.service.get_value_dictionary", new_callable=AsyncMock) as gv:
        gv.return_value = ValueDictionarySnapshot(Industry.AUTOMOTIVE, ())
        with patch("app.services.chat.service.plan_turn", return_value=_stub_turn()):
            events = await _collect_stream(service, "Break it down by month", conv.id)

    kinds = [data.get("kind") for _ev, data in events if _ev == "clarification"]
    assert "clarify" in kinds
    titles = [data.get("title") for _ev, data in events if _ev == "clarification"]
    assert "Context expired" in titles


@pytest.mark.asyncio
async def test_active_memory_passes_prior_state_to_planner(memory_chat) -> None:
    service, conv, _user = memory_chat
    mem = empty_memory(user_id=conv.user_id, conversation_id=conv.id)
    mem.analytical = build_analytical_context(
        plan=QuestionPlan(
            industry=Industry.AUTOMOTIVE,
            metric="revenue",
            entity="metric_only",
            intent="aggregation",
            dimensions=("region",),
        ),
        question="Revenue by region",
        result_meta=ResultMeta(),
        prior=None,
    )
    conv.session_memory = mem.to_dict()
    await service._save_session_memory(conv, mem)
    await service._app.commit()

    captured: dict = {}

    def _capture_plan_turn(*args, **kwargs):
        captured["prior_state"] = kwargs.get("prior_state")
        return _stub_turn(prior_state=kwargs.get("prior_state"))

    with patch("app.services.chat.service.get_value_dictionary", new_callable=AsyncMock) as gv:
        gv.return_value = ValueDictionarySnapshot(Industry.AUTOMOTIVE, ())
        with patch("app.services.chat.service.plan_turn", side_effect=_capture_plan_turn):
            await _collect_stream(service, "Break it down by month", conv.id)

    assert captured.get("prior_state") is not None
    assert captured["prior_state"].get("metric") == "revenue"


@pytest.mark.asyncio
async def test_pending_clarification_completes_cl_comp(memory_chat) -> None:
    service, conv, _user = memory_chat
    mem = empty_memory(user_id=conv.user_id, conversation_id=conv.id)
    set_pending_clarification(
        mem,
        original_question="Show sales",
        clarifies="Which metric?",
        options=["Revenue", "Units"],
    )
    conv.session_memory = mem.to_dict()
    await service._save_session_memory(conv, mem)
    await service._app.commit()

    seen_questions: list[str] = []

    def _plan(industry, question, **kwargs):
        seen_questions.append(question)
        return _stub_turn(question=question)

    with patch("app.services.chat.service.get_value_dictionary", new_callable=AsyncMock) as gv:
        gv.return_value = ValueDictionarySnapshot(Industry.AUTOMOTIVE, ())
        with patch("app.services.chat.service.plan_turn", side_effect=_plan):
            await _collect_stream(service, "Revenue", conv.id)

    assert seen_questions == ["Show sales Revenue"]


@pytest.mark.asyncio
async def test_forbidden_region_follow_up_denied_rbac(scoped_memory_chat) -> None:
    service, conv, _user = scoped_memory_chat
    mem = empty_memory(user_id=conv.user_id, conversation_id=conv.id)
    plan = QuestionPlan(
        industry=Industry.AUTOMOTIVE,
        metric="revenue",
        entity="metric_only",
        intent="aggregation",
        dimensions=("region",),
        filters=(
            ExtractedFilter(
                column="region_name",
                operator="=",
                value="North",
                values=("North",),
                label="North",
            ),
        ),
    )
    mem.analytical = build_analytical_context(
        plan=plan,
        question="Revenue in North",
        result_meta=ResultMeta(),
        prior=None,
    )
    conv.session_memory = mem.to_dict()
    await service._save_session_memory(conv, mem)
    await service._app.commit()

    with patch("app.services.chat.service.get_value_dictionary", new_callable=AsyncMock) as gv:
        gv.return_value = ValueDictionarySnapshot(Industry.AUTOMOTIVE, ())
        with patch("app.services.chat.service.plan_turn", return_value=_stub_turn()):
            events = await _collect_stream(service, "What about South?", conv.id)

    denied = [
        data
        for ev, data in events
        if ev == "clarification" and data.get("kind") == "denied"
    ]
    assert denied, "expected region scope denial via forbidden_zones on follow-up"
    assert service.last_history is not None


@pytest.mark.asyncio
async def test_refresh_skips_cache_but_keeps_analytical_context(memory_chat) -> None:
    service, conv, _user = memory_chat
    mem = empty_memory(user_id=conv.user_id, conversation_id=conv.id)
    mem.analytical = build_analytical_context(
        plan=QuestionPlan(
            industry=Industry.AUTOMOTIVE,
            metric="revenue",
            entity="metric_only",
            intent="aggregation",
            dimensions=("region",),
        ),
        question="Revenue by region",
        result_meta=ResultMeta(),
        prior=None,
    )
    conv.session_memory = mem.to_dict()
    await service._save_session_memory(conv, mem)
    await service._app.commit()

    cached = CachedAnswer(
        sql="SELECT 1",
        columns=["x"],
        rows=[{"x": 1}],
        chart=None,
        meta={},
        narrative="cached",
        followups=[],
        path="template",
        data_as_of=None,
        created_at=__import__("time").time(),
        tables=[],
    )
    QUERY_CACHE.put(
        industry=Industry.AUTOMOTIVE.value,
        question="refresh that",
        scope=service._cache_scope(),
        answer=cached,
    )

    cache_get = MagicMock(wraps=QUERY_CACHE.get)
    with patch.object(QUERY_CACHE, "get", cache_get):
        with patch("app.services.chat.service.get_value_dictionary", new_callable=AsyncMock) as gv:
            gv.return_value = ValueDictionarySnapshot(Industry.AUTOMOTIVE, ())
            with patch("app.services.chat.service.plan_turn", return_value=_stub_turn()):
                await _collect_stream(service, "refresh that", conv.id)

    cache_get.assert_not_called()
    reloaded = await service._load_session_memory(conv.id)
    assert reloaded.analytical is not None


@pytest.mark.asyncio
async def test_concurrent_session_memory_save_last_write_wins(memory_chat) -> None:
    """Two interleaved saves on one conversation row: last flush wins (no merge)."""
    service, conv, user = memory_chat
    mem_a = empty_memory(user_id=user.id, conversation_id=conv.id)
    set_pending_clarification(mem_a, original_question="A", clarifies="?", options=[])
    mem_b = empty_memory(user_id=user.id, conversation_id=conv.id)
    mem_b.analytical = build_analytical_context(
        plan=QuestionPlan(
            industry=Industry.AUTOMOTIVE,
            metric="units",
            entity="metric_only",
            intent="aggregation",
            dimensions=(),
        ),
        question="Units",
        result_meta=ResultMeta(),
        prior=None,
    )

    await service._save_session_memory(conv, mem_a)
    await service._save_session_memory(conv, mem_b)

    result = await service._app.execute(
        select(Conversation.session_memory).where(Conversation.id == conv.id)
    )
    raw = result.scalar_one()
    assert raw.get("pending") is None
    assert raw["analytical"]["previousQuestion"] == "Units"


@pytest.mark.asyncio
async def test_history_fallback_prior_state_rbac_before_plan(scoped_memory_chat) -> None:
    service, conv, user = scoped_memory_chat
    hist = QueryHistory(
        id=uuid.uuid4(),
        user_id=user.id,
        conversation_id=conv.id,
        industry=Industry.AUTOMOTIVE.value,
        question="Revenue in North",
        status="completed",
        trust_breakdown={"queryState": _north_plan_state()},
    )
    service._app.add(hist)
    await service._app.flush()
    await service._app.commit()

    plan_calls: list[str] = []

    def _plan(industry, question, **kwargs):
        plan_calls.append(question)
        return _stub_turn()

    with patch("app.services.chat.service.get_value_dictionary", new_callable=AsyncMock) as gv:
        gv.return_value = ValueDictionarySnapshot(Industry.AUTOMOTIVE, ())
        with patch("app.services.chat.service.plan_turn", side_effect=_plan):
            events = await _collect_stream(service, "What about South?", conv.id)

    assert plan_calls == []
    denied = [d for ev, d in events if ev == "clarification" and d.get("kind") == "denied"]
    assert denied
