"""Tests for rule-based message classifier."""

from __future__ import annotations

from app.core.config import Industry
from app.services.chat.message_classifier import MessageRoute, classify_message


def test_greeting_is_general_chat_when_enabled() -> None:
    r = classify_message("Hello", Industry.AUTOMOTIVE, enabled=True)
    assert r.route is MessageRoute.GENERAL_CHAT


def test_thanks_after_data_context() -> None:
    r = classify_message("Thanks", Industry.AUTOMOTIVE, enabled=True)
    assert r.route is MessageRoute.GENERAL_CHAT


def test_unsupported_delete() -> None:
    r = classify_message("delete all orders", Industry.AUTOMOTIVE, enabled=True)
    assert r.route is MessageRoute.UNSUPPORTED


def test_live_weather_out_of_scope() -> None:
    r = classify_message("What is the weather in Mumbai today?", Industry.AUTOMOTIVE, enabled=True)
    assert r.route is MessageRoute.OUT_OF_SCOPE_LIVE


def test_disabled_is_passthrough() -> None:
    r = classify_message("Hello", Industry.AUTOMOTIVE, enabled=False)
    assert r.route is MessageRoute.PASSTHROUGH
    assert r.applied is False


def test_app_help_document_and_knowledge_routes() -> None:
    auto = Industry.AUTOMOTIVE
    assert classify_message("What tables can I query?", auto, enabled=True).route is (
        MessageRoute.APP_HELP
    )
    assert classify_message(
        "Summarize the uploaded report", Industry.INSURANCE, enabled=True
    ).route is MessageRoute.DOCUMENT_QUERY
    assert classify_message(
        "What is the capital of France?", auto, enabled=True, data_vocabulary=lambda _q: False
    ).route is MessageRoute.GENERAL_KNOWLEDGE


def test_data_vocabulary_keeps_data_questions_out_of_general_knowledge() -> None:
    r = classify_message(
        "What is our revenue in South?",
        Industry.AUTOMOTIVE,
        enabled=True,
        data_vocabulary=lambda _q: True,
    )
    assert r.route is MessageRoute.PASSTHROUGH


def test_classifier_exception_passes_through() -> None:
    def boom(_q: str) -> bool:
        raise RuntimeError("probe failed")

    r = classify_message(
        "What is the capital of France?", Industry.AUTOMOTIVE, enabled=True, data_vocabulary=boom
    )
    assert r.route is MessageRoute.PASSTHROUGH


def test_dinner_chitchat_not_data_follow_up() -> None:
    r = classify_message("What about dinner?", Industry.AUTOMOTIVE, enabled=True)
    assert r.route is MessageRoute.GENERAL_CHAT
