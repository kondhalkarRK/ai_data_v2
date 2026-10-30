"""Regression sequences A–H: general chat routing and follow-up context."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.config import Industry, Settings
from app.semantic.service import SemanticService
from app.services.chat.conversation_memory import (
    ResultMeta,
    build_analytical_context,
    empty_memory,
    follow_up_context_status,
)
from app.services.chat.follow_up_guard import follow_up_guard_allows_sql
from app.services.chat.pre_plan import early_route
from app.services.chat.question_understanding import QuestionPlan
from app.services.chat.semantic_query_planner import plan_semantic_query
from app.services.chat.value_dictionary import ValueDictionarySnapshot
from app.services.llm import LlmResult
from tests.unit.test_chat_service_memory import _collect_stream, memory_chat  # noqa: F401

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "chat_routing_eval"))
from seed_values import seed_values_for_industry  # noqa: E402


def _revenue_memory():
    mem = empty_memory(user_id=uuid.uuid4(), conversation_id=uuid.uuid4())
    mem.analytical = build_analytical_context(
        plan=QuestionPlan(
            industry=Industry.AUTOMOTIVE,
            metric="revenue",
            entity="metric_only",
            intent="aggregation",
            dimensions=("region",),
        ),
        question="Show revenue for North",
        result_meta=ResultMeta(row_count=3),
        prior=None,
    )
    return mem


def _llm(content: str) -> AsyncMock:
    return AsyncMock(
        return_value=LlmResult(
            sql=None,
            narrative="",
            model="mock",
            prompt_tokens=30,
            completion_tokens=10,
            content=content,
        )
    )


def _narrative(events) -> str:
    return "".join(d["token"] for ev, d in events if ev == "token").strip()


def test_runtime_default_router_enabled() -> None:
    assert Settings().chat_router_enabled is True


# ── A: Greeting ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_sequence_a_hey_there_no_sql(memory_chat) -> None:
    service, conv, _ = memory_chat
    with (
        patch("app.services.chat.service.plan_turn") as plan,
        patch("app.services.chat.service.get_value_dictionary", new_callable=AsyncMock),
    ):
        events = await _collect_stream(service, "Hey there!", conv.id)
    assert _narrative(events)
    plan.assert_not_called()
    assert service.last_profile.route == "general_chat"


# ── B: Casual dinner ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_sequence_b_dinner_uses_llm_not_sql(memory_chat) -> None:
    service, conv, _ = memory_chat
    llm = _llm("Maybe pasta — and I can help with revenue or units whenever you like.")
    with (
        patch("app.services.chat.non_data_handlers.complete_text", llm),
        patch("app.services.chat.service.plan_turn") as plan,
    ):
        events = await _collect_stream(service, "What's for dinner?", conv.id)
    assert _narrative(events)
    plan.assert_not_called()
    assert service.last_profile.route == "general_chat"
    llm.assert_awaited_once()


# ── C / G: Follow-up vs dinner (memory rules) ───────────────────────────────


def test_sequence_c_south_follow_up_active() -> None:
    settings = Settings()
    mem = _revenue_memory()
    assert (
        follow_up_context_status(mem, "What about South?", settings, industry=Industry.AUTOMOTIVE)
        == "active"
    )


def test_sequence_g_dinner_not_follow_up_context() -> None:
    settings = Settings()
    mem = _revenue_memory()
    assert (
        follow_up_context_status(mem, "What about dinner?", settings, industry=Industry.AUTOMOTIVE)
        == "none"
    )


# ── D: New analytical topic (planner does not inherit prior when self-contained) ──


def test_sequence_d_new_topic_not_contextual() -> None:
    prior = {"metric": "revenue", "entity": "metric_only", "intent": "aggregation", "dimensions": ["region"]}
    query = plan_semantic_query(
        Industry.AUTOMOTIVE,
        "How many employees work in West?",
        prior_state=prior,
    )
    assert query.contextual is False


# ── E: Greeting after revenue thread ────────────────────────────────────────


@pytest.mark.asyncio
async def test_sequence_e_greeting_after_revenue_no_follow_up_clarification(memory_chat) -> None:
    service, conv, _ = memory_chat
    mem = empty_memory(user_id=conv.user_id, conversation_id=conv.id)
    mem.analytical = _revenue_memory().analytical
    await service._save_session_memory(conv, mem)
    await service._app.commit()

    with patch("app.services.chat.service.plan_turn") as plan:
        events = await _collect_stream(service, "Hey there!", conv.id)
    clarifications = [d for ev, d in events if ev == "clarification"]
    assert not clarifications
    assert service.last_profile.route == "general_chat"
    plan.assert_not_called()


# ── F: Joke then compare (analytical memory preserved) ────────────────────────


@pytest.mark.asyncio
async def test_sequence_f_joke_then_compare_still_follows_revenue(memory_chat) -> None:
    service, conv, _ = memory_chat
    mem = empty_memory(user_id=conv.user_id, conversation_id=conv.id)
    mem.analytical = _revenue_memory().analytical
    await service._save_session_memory(conv, mem)
    await service._app.commit()

    joke_llm = _llm("Why did the metric cross the road? To join the dashboard.")
    with patch("app.services.chat.non_data_handlers.complete_text", joke_llm):
        await _collect_stream(service, "Tell me a joke", conv.id)

    loaded = await service._load_session_memory(conv.id)
    assert loaded.analytical is not None
    assert loaded.analytical.validated_plan.get("metric") == "revenue"

    snapshot = ValueDictionarySnapshot(
        Industry.AUTOMOTIVE, seed_values_for_industry(Industry.AUTOMOTIVE)
    )
    pack = SemanticService(Settings())._load_pack(Industry.AUTOMOTIVE)
    prior = dict(loaded.analytical.validated_plan)
    allowed, interp = follow_up_guard_allows_sql(
        question="What about South?",
        session_memory=loaded,
        settings=Settings(),
        prior_state=prior,
        snapshot=snapshot,
        pack=pack,
        industry=Industry.AUTOMOTIVE,
    )
    assert allowed
    assert interp


# ── H: Expired context ──────────────────────────────────────────────────────


def test_sequence_h_expired_south() -> None:
    settings = Settings(chat_analytical_context_ttl_seconds=60)
    mem = _revenue_memory()
    mem.analytical.updated_at = datetime.now(UTC) - timedelta(seconds=120)
    assert (
        follow_up_context_status(mem, "What about South?", settings, industry=Industry.AUTOMOTIVE)
        == "expired"
    )


def test_early_route_good_morning_is_general_chat() -> None:
    from app.services.security.region_scope import RegionScope

    scope = RegionScope.all_regions(MagicMock())
    outcome = early_route(
        industry=Industry.AUTOMOTIVE,
        message="Good morning",
        scope=scope,
        router_enabled=True,
    )
    assert outcome is not None
    assert outcome.stop == "general_chat"
    assert outcome.stop_detail == "greeting"
