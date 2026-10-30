"""Scope: business analytics only. Casual chat allowed; programming/trivia declined, no SQL."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from app.core.config import Industry, Settings
from app.services.chat.message_classifier import MessageRoute, classify_message
from app.services.llm import LlmResult
from tests.unit.test_chat_service_memory import _collect_stream, memory_chat  # noqa: F401


def _narrative(events) -> str:
    return "".join(d["token"] for ev, d in events if ev == "token").strip()


@pytest.mark.parametrize(
    "question",
    [
        "What's the difference between a Python list and tuple?",
        "How do I reverse a linked list in Java?",
        "Write me a function to parse JSON",
        "debug my code please",
    ],
)
def test_programming_questions_classified_out_of_scope(question: str) -> None:
    result = classify_message(question, Industry.AUTOMOTIVE, enabled=True)
    assert result.route is MessageRoute.GENERAL_KNOWLEDGE
    assert result.reason == "off_topic_programming"


@pytest.mark.parametrize(
    "question",
    [
        "Show revenue by month",
        "Top 3 selling Tata cars",
        "Hey there!",
        "Show me claims by status as sql",
        "What about South?",
    ],
)
def test_business_and_casual_messages_not_declined(question: str) -> None:
    result = classify_message(question, Industry.AUTOMOTIVE, enabled=True)
    assert result.reason != "off_topic_programming"
    assert result.route is not MessageRoute.GENERAL_KNOWLEDGE


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "question",
    [
        "What's the difference between a Python list and tuple?",
        "What is the capital of France?",
    ],
)
async def test_out_of_scope_declined_without_sql_or_llm(memory_chat, question: str) -> None:
    service, conv, _ = memory_chat
    llm = AsyncMock(return_value=LlmResult(sql=None, narrative="", model="m", content="Paris"))
    with (
        patch("app.services.chat.non_data_handlers.complete_text", llm),
        patch("app.services.chat.service.plan_turn") as plan,
    ):
        events = await _collect_stream(service, question, conv.id)
    text = _narrative(events)
    assert "business data and analytics" in text
    plan.assert_not_called()
    llm.assert_not_called()
    assert service.last_history.sql_text is None
    assert service.usage_llm_steps == 0
    assert not any(ev == "sql" for ev, _ in events)


@pytest.mark.asyncio
async def test_general_knowledge_can_be_enabled_explicitly(memory_chat) -> None:
    service, conv, _ = memory_chat
    service._settings = Settings(chat_router_enabled=True, chat_general_knowledge_enabled=True)
    llm = AsyncMock(
        return_value=LlmResult(
            sql=None, narrative="", model="m", prompt_tokens=5, completion_tokens=5,
            content="Paris is the capital of France.",
        )
    )
    with patch("app.services.chat.non_data_handlers.complete_text", llm):
        events = await _collect_stream(service, "What is the capital of France?", conv.id)
    assert "Paris" in _narrative(events)
    assert service.usage_llm_steps == 1


@pytest.mark.asyncio
async def test_casual_chat_still_allowed(memory_chat) -> None:
    service, conv, _ = memory_chat
    with patch("app.services.chat.service.plan_turn") as plan:
        events = await _collect_stream(service, "Hey there!", conv.id)
    assert _narrative(events)
    plan.assert_not_called()
    assert service.last_profile.route == "general_chat"
