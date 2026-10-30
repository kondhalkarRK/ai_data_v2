"""Stage D: non-data routes never plan or run SQL; LLM calls are mocked and metered."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.config import Industry, Settings
from app.models.region_access import UserRegionAccess
from app.semantic.service import SemanticService
from app.services.chat.non_data_handlers import app_help_reply, lookup_definition
from app.services.llm import LlmResult
from app.services.security.region_scope import RegionScope
from app.services.chat.semantic_context import build_allowed_schema
from tests.unit.test_chat_service_memory import _collect_stream, memory_chat  # noqa: F401


def _llm(content: str, *, prompt: int = 40, completion: int = 12, error: str | None = None):
    return AsyncMock(
        return_value=LlmResult(
            sql=None,
            narrative="",
            model="mock-model",
            prompt_tokens=prompt,
            completion_tokens=completion,
            error=error,
            content=content,
        )
    )


def _narrative(events) -> str:
    return "".join(d["token"] for ev, d in events if ev == "token").strip()


def _router_on(service) -> None:
    service._settings = Settings(chat_router_enabled=True)


@pytest.fixture(scope="module")
def auto_pack():
    return SemanticService(Settings())._load_pack(Industry.AUTOMOTIVE)


@pytest.fixture(scope="module")
def ins_pack():
    return SemanticService(Settings())._load_pack(Industry.INSURANCE)


# ── service level ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_greeting_uses_template_without_schema_sql_or_llm(memory_chat) -> None:
    service, conv, _ = memory_chat
    assert service._settings.chat_router_enabled is True
    llm = _llm("should not be called")
    with (
        patch("app.services.chat.non_data_handlers.complete_text", llm),
        patch("app.services.chat.service.get_value_dictionary", new_callable=AsyncMock) as gv,
        patch("app.services.chat.service.plan_turn") as plan,
    ):
        events = await _collect_stream(service, "Hello", conv.id)

    assert "governed analytics question" in _narrative(events).lower()
    plan.assert_not_called()
    gv.assert_not_called()
    service._semantic.get_pack.assert_not_called()
    llm.assert_not_called()
    assert service.usage_llm_steps == 0
    assert service.last_profile.route == "general_chat"
    assert service.last_profile.route_source == "rules"


@pytest.mark.asyncio
async def test_reply_kept_despite_client_empty_sql_flag(memory_chat) -> None:
    service, conv, _ = memory_chat
    _router_on(service)
    llm = _llm("Why did the KPI cross the road?", error="Invalid model response (empty SQL)")
    with patch("app.services.chat.non_data_handlers.complete_text", llm):
        events = await _collect_stream(service, "Tell me a joke", conv.id)
    assert _narrative(events) == "Why did the KPI cross the road?"


@pytest.mark.asyncio
async def test_greeting_falls_back_to_template_when_llm_fails(memory_chat) -> None:
    service, conv, _ = memory_chat
    _router_on(service)
    llm = _llm("", prompt=0, completion=0, error="timeout")
    with (
        patch("app.services.chat.non_data_handlers.complete_text", llm),
        patch("app.services.chat.service.plan_turn") as plan,
    ):
        events = await _collect_stream(service, "Hello", conv.id)
    assert _narrative(events)
    plan.assert_not_called()
    assert service.usage_llm_steps == 0


@pytest.mark.asyncio
async def test_no_joke_after_failed_turn(memory_chat) -> None:
    from app.models.activity import QueryHistory

    service, conv, user = memory_chat
    _router_on(service)
    service._app.add(
        QueryHistory(
            id=uuid.uuid4(),
            user_id=user.id,
            conversation_id=conv.id,
            industry=Industry.AUTOMOTIVE.value,
            question="Revenue for Atlantis",
            status="failed",
        )
    )
    await service._app.commit()
    llm = _llm("Why did the car ...")
    with patch("app.services.chat.non_data_handlers.complete_text", llm):
        events = await _collect_stream(service, "Tell me a joke", conv.id)
    llm.assert_not_called()
    assert "data question" in _narrative(events)


@pytest.mark.asyncio
async def test_general_knowledge_prompt_forbids_data_claims(memory_chat) -> None:
    service, conv, _ = memory_chat
    service._settings = Settings(chat_router_enabled=True, chat_general_knowledge_enabled=True)
    llm = _llm("Paris is the capital of France.")
    with (
        patch("app.services.chat.non_data_handlers.complete_text", llm),
        patch("app.services.chat.service.plan_turn") as plan,
    ):
        events = await _collect_stream(service, "What is the capital of France?", conv.id)
    plan.assert_not_called()
    system = llm.await_args.kwargs["system"]
    assert "Never state or imply facts about the user's" in system
    assert "NOT checked any database" in system
    assert _narrative(events).startswith("Paris is the capital of France.")
    assert "not from your data" in _narrative(events)
    assert service.usage_llm_steps == 1


@pytest.mark.asyncio
async def test_app_help_answers_from_pack_without_llm_or_sql(memory_chat, auto_pack) -> None:
    service, conv, _ = memory_chat
    _router_on(service)
    service._semantic.get_pack = AsyncMock(return_value=auto_pack)
    llm = _llm("should not be used")
    with (
        patch("app.services.chat.non_data_handlers.complete_text", llm),
        patch("app.services.chat.service.plan_turn") as plan,
    ):
        events = await _collect_stream(service, "What metrics are available in Ask DB?", conv.id)
    plan.assert_not_called()
    llm.assert_not_called()
    text = _narrative(events)
    for measure in auto_pack.model.measures.values():
        assert measure.display_name.split()[0] in text


@pytest.mark.asyncio
async def test_how_do_i_ask_runs_no_sql(memory_chat, auto_pack) -> None:
    service, conv, _ = memory_chat
    _router_on(service)
    service._semantic.get_pack = AsyncMock(return_value=auto_pack)
    with patch("app.services.chat.service.plan_turn") as plan:
        events = await _collect_stream(service, "How do I ask about revenue?", conv.id)
    plan.assert_not_called()
    assert service.last_history.sql_text is None
    assert _narrative(events)


@pytest.fixture
async def north_only(memory_chat):
    service, conv, user = memory_chat
    service._app.add(UserRegionAccess(user_id=user.id, region_id="North"))
    await service._app.commit()
    return service, conv, user


@pytest.mark.asyncio
async def test_app_help_regions_respect_rbac(north_only, auto_pack) -> None:
    service, conv, _ = north_only
    _router_on(service)
    service._semantic.get_pack = AsyncMock(return_value=auto_pack)
    events = await _collect_stream(service, "Which regions are in the semantic layer?", conv.id)
    text = _narrative(events)
    assert "North" in text
    for other in ("South", "East", "West"):
        assert other not in text


@pytest.mark.asyncio
async def test_document_query_without_documents(memory_chat) -> None:
    service, conv, _ = memory_chat
    _router_on(service)
    knowledge = MagicMock()
    knowledge.list_documents.return_value = []
    with (
        patch("app.services.chat.service.KnowledgeService", return_value=knowledge),
        patch("app.services.chat.service.plan_turn") as plan,
    ):
        events = await _collect_stream(
            service, "Summarize key findings from the uploaded report on claims", conv.id
        )
    plan.assert_not_called()
    knowledge.search.assert_not_called()
    assert "No documents have been uploaded" in _narrative(events)


@pytest.mark.asyncio
async def test_document_query_with_documents_uses_knowledge_search(memory_chat) -> None:
    service, conv, _ = memory_chat
    _router_on(service)
    knowledge = MagicMock()
    knowledge.list_documents.return_value = [{"id": "d1", "suggestedQuestions": []}]
    knowledge.search.return_value = []
    with (
        patch("app.services.chat.service.KnowledgeService", return_value=knowledge),
        patch("app.services.chat.service.plan_turn") as plan,
    ):
        await _collect_stream(
            service, "What does the policy document say about fraud exclusions?", conv.id
        )
    plan.assert_not_called()
    knowledge.search.assert_called_once()


# ── Stage C at the service level ─────────────────────────────────────────────


async def _seed_revenue_by_region(service, conv) -> None:
    from app.services.chat.conversation_memory import (
        ResultMeta,
        build_analytical_context,
        empty_memory,
    )
    from app.services.chat.question_understanding import QuestionPlan

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
        result_meta=ResultMeta(row_count=4),
        prior=None,
    )
    await service._save_session_memory(conv, mem)
    await service._app.commit()


@pytest.mark.asyncio
async def test_unanchored_follow_up_runs_no_sql(memory_chat, auto_pack) -> None:
    service, conv, _ = memory_chat
    service._semantic.get_pack = AsyncMock(return_value=auto_pack)
    await _seed_revenue_by_region(service, conv)
    with (
        patch("app.services.chat.service.get_value_dictionary", new_callable=AsyncMock) as gv,
        patch("app.services.chat.service.plan_turn") as plan,
    ):
        from app.services.chat.value_dictionary import ValueDictionarySnapshot

        gv.return_value = ValueDictionarySnapshot(Industry.AUTOMOTIVE, ())
        events = await _collect_stream(service, "What about it then?", conv.id)
    plan.assert_not_called()
    assert any(ev == "clarification" for ev, _ in events)


@pytest.mark.asyncio
async def test_anchored_follow_up_emits_interpretation(memory_chat, auto_pack) -> None:
    import sys
    from pathlib import Path

    from app.services.chat.value_dictionary import ValueDictionarySnapshot
    from tests.unit.test_chat_service_memory import _stub_turn

    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "chat_routing_eval"))
    from seed_values import seed_values_for_industry

    service, conv, _ = memory_chat
    service._semantic.get_pack = AsyncMock(return_value=auto_pack)
    await _seed_revenue_by_region(service, conv)
    with (
        patch("app.services.chat.service.get_value_dictionary", new_callable=AsyncMock) as gv,
        patch("app.services.chat.service.plan_turn", return_value=_stub_turn()) as plan,
    ):
        gv.return_value = ValueDictionarySnapshot(
            Industry.AUTOMOTIVE, seed_values_for_industry(Industry.AUTOMOTIVE)
        )
        events = await _collect_stream(service, "What about South?", conv.id)
    plan.assert_called()
    stages = [d for ev, d in events if ev == "stage" and d.get("stage") == "interpretation"]
    assert stages and stages[0]["message"] == "Showing revenue for South"


# ── handler units ────────────────────────────────────────────────────────────


def test_missing_definition_is_reported_not_invented(ins_pack) -> None:
    text = app_help_reply(
        "What does churn mean in this app?",
        industry=Industry.INSURANCE,
        pack=ins_pack,
        allowed_schema=build_allowed_schema(ins_pack),
        scope=RegionScope.all_regions(),
    )
    assert "no approved definition" in text
    assert "churn" in text


def test_loss_ratio_definition_comes_from_glossary(ins_pack) -> None:
    found = lookup_definition("loss ratio", ins_pack)
    assert found is not None
    text = app_help_reply(
        "What does loss ratio mean in this app?",
        industry=Industry.INSURANCE,
        pack=ins_pack,
        allowed_schema=build_allowed_schema(ins_pack),
        scope=RegionScope.all_regions(),
    )
    assert found[1] in text


def test_tables_listed_only_from_allowed_schema(auto_pack) -> None:
    allowed = build_allowed_schema(auto_pack)
    text = app_help_reply(
        "What tables can I query?",
        industry=Industry.AUTOMOTIVE,
        pack=auto_pack,
        allowed_schema=allowed,
        scope=RegionScope.all_regions(),
    )
    for table in auto_pack.model.tables.values():
        assert table.display_name in text
