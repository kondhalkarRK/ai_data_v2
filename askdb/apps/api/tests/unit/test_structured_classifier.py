"""Stage E: one validated classify-and-resolve call; failures clarify; clear turns make no call."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import pytest

from app.core.config import Industry, Settings
from app.services.chat.clarification import Clarification
from app.services.chat.llm_assist import ClassifierOutcome, ClassifierVerdict, classify_and_resolve
from app.services.chat.pipeline import TurnPlan
from app.services.chat.pre_plan import plan_with_rewrites, split_compound, strip_question_words
from app.services.chat.question_understanding import QuestionPlan
from app.services.chat.value_dictionary import ValueDictionarySnapshot
from app.services.llm import LlmResult
from tests.unit.test_chat_service_memory import _collect_stream, memory_chat  # noqa: F401


def _result(content: str = "", *, timed_out: bool = False, error: str | None = None):
    return LlmResult(
        sql=None,
        narrative="",
        model="mock",
        prompt_tokens=30,
        completion_tokens=20,
        timed_out=timed_out,
        error=error,
        content=content,
    )


async def _classify(result: LlmResult) -> ClassifierOutcome:
    with patch(
        "app.services.chat.llm_assist.complete_text", AsyncMock(return_value=result)
    ) as llm:
        outcome = await classify_and_resolve(
            settings=Settings(chat_classifier_model="small-model"),
            industry=Industry.AUTOMOTIVE,
            question="sales of the red ones up north",
            vocabulary="Metrics: revenue, units",
        )
    assert llm.await_count == 1
    assert llm.await_args.kwargs["model_override"] == "small-model"
    return outcome


@pytest.mark.asyncio
async def test_valid_json_is_validated() -> None:
    payload = {
        "intent": "DATA_QUERY",
        "resolved_question": "Units by colour in North",
        "needs_clarification": False,
        "clarification_question": None,
    }
    outcome = await _classify(_result(json.dumps(payload)))
    assert outcome.failure is None
    assert outcome.verdict == ClassifierVerdict(**payload)
    assert (outcome.prompt_tokens, outcome.completion_tokens) == (30, 20)


@pytest.mark.asyncio
async def test_real_client_empty_sql_flag_does_not_discard_verdict() -> None:
    payload = {"intent": "APP_HELP", "needs_clarification": False}
    result = _result(json.dumps(payload), error="Invalid model response (empty SQL)")
    outcome = await _classify(result)
    assert outcome.failure is None
    assert outcome.verdict is not None and outcome.verdict.intent == "APP_HELP"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("result", "failure"),
    [
        (_result(timed_out=True, error="timeout"), "timeout"),
        (_result(error="502 bad gateway"), "error"),
        (_result("not json at all"), "invalid_json"),
        (_result('{"intent": "SELL_CARS", "needs_clarification": false}'), "invalid_json"),
        (_result('{"intent": "DATA_QUERY", "needs_clarification": false}'), "invalid_json"),
        (_result('{"intent": "CLARIFICATION", "needs_clarification": true}'), "invalid_json"),
    ],
)
async def test_failures_return_no_verdict(result: LlmResult, failure: str) -> None:
    outcome = await _classify(result)
    assert outcome.verdict is None
    assert outcome.failure == failure


def test_strip_and_compound_helpers() -> None:
    assert strip_question_words("Why did revenue drop in the West region?") == (
        "revenue drop in the West region?"
    )
    assert strip_question_words("What drove the increase in SUV sales?") == (
        "increase in SUV sales?"
    )
    assert strip_question_words("Revenue by region") is None
    assert split_compound("Explain churn and show it for last quarter") == (
        "churn",
        "show churn for last quarter",
    )


def _turn(question: str, *, clarify: bool) -> TurnPlan:
    return TurnPlan(
        original=question,
        question=question,
        plan=QuestionPlan(
            industry=Industry.AUTOMOTIVE,
            metric="revenue",
            entity="metric_only",
            intent="aggregation",
        ),
        clarification=(
            Clarification(kind="clarify", title="t", message="m") if clarify else None
        ),
        clarify_reason="unresolved" if clarify else None,
        governed_sql=None if clarify else "SELECT 1",
    )


def test_rewrite_only_after_original_would_clarify() -> None:
    seen: list[str] = []

    def plan(text: str) -> TurnPlan:
        seen.append(text)
        return _turn(text, clarify=text.lower().startswith("why"))

    out = plan_with_rewrites(plan, "Why did revenue drop in the West region?", enabled=True)
    assert seen == ["Why did revenue drop in the West region?", "revenue drop in the West region?"]
    assert out.planned_question == "revenue drop in the West region?"

    seen.clear()
    out = plan_with_rewrites(plan, "Revenue by region", enabled=True)
    assert seen == ["Revenue by region"]


def test_compound_plans_data_half_and_keeps_definition_separate() -> None:
    from app.semantic.service import SemanticService
    from app.services.chat.non_data_handlers import definition_from_metadata

    seen: list[str] = []

    def plan(text: str) -> TurnPlan:
        seen.append(text)
        return _turn(text, clarify=False)

    out = plan_with_rewrites(plan, "Explain loss ratio and show it by month", enabled=True)
    assert seen == ["show loss ratio by month"]
    assert out.definition_term == "loss ratio"

    pack = SemanticService(Settings())._load_pack(Industry.INSURANCE)
    assert "Loss Ratio" in definition_from_metadata("loss ratio", pack, Industry.INSURANCE)
    missing = definition_from_metadata("churn", pack, Industry.INSURANCE)
    assert "no approved definition" in missing


# ── service level ────────────────────────────────────────────────────────────


def _clarifying_turn(question: str = "q", **_kw) -> TurnPlan:
    return _turn(question, clarify=True)


def _enable(service) -> None:
    service._settings = Settings(
        chat_router_enabled=True, chat_structured_classifier_enabled=True
    )


@pytest.mark.asyncio
async def test_classifier_failure_routes_to_clarification(memory_chat) -> None:
    service, conv, _ = memory_chat
    _enable(service)
    outcome = ClassifierOutcome(None, "mock", 25, 0, failure="timeout")
    with (
        patch("app.services.chat.service.llm_configured", return_value=True),
        patch("app.services.chat.service.get_value_dictionary", new_callable=AsyncMock) as gv,
        patch("app.services.chat.service.plan_turn", side_effect=lambda i, q, **k: _clarifying_turn(q)),
        patch("app.services.chat.service.classify_and_resolve", AsyncMock(return_value=outcome)) as cls,
        patch("app.services.chat.service.interpret_question", AsyncMock()) as legacy,
    ):
        gv.return_value = ValueDictionarySnapshot(Industry.AUTOMOTIVE, ())
        events = await _collect_stream(service, "sales of the shiny ones", conv.id)
    assert cls.await_count == 1
    legacy.assert_not_called()
    assert any(ev == "clarification" for ev, _ in events)
    assert service.usage_llm_steps == 1
    assert service.usage_prompt_tokens == 25
    assert service.last_profile.route_source == "llm_classifier"


@pytest.mark.asyncio
async def test_valid_verdict_plans_resolved_question(memory_chat) -> None:
    service, conv, _ = memory_chat
    _enable(service)
    verdict = ClassifierVerdict(
        intent="DATA_QUERY",
        resolved_question="Revenue by colour",
        needs_clarification=False,
    )
    seen: list[str] = []

    def plan(_industry, question, **_kw):
        seen.append(question)
        return _clarifying_turn(question)

    with (
        patch("app.services.chat.service.llm_configured", return_value=True),
        patch("app.services.chat.service.get_value_dictionary", new_callable=AsyncMock) as gv,
        patch("app.services.chat.service.plan_turn", side_effect=plan),
        patch(
            "app.services.chat.service.classify_and_resolve",
            AsyncMock(return_value=ClassifierOutcome(verdict, "mock", 10, 10)),
        ),
    ):
        gv.return_value = ValueDictionarySnapshot(Industry.AUTOMOTIVE, ())
        events = await _collect_stream(service, "money from the shiny ones", conv.id)
    assert "Revenue by colour" in seen
    # The resolved question still clarified in the planner, so no SQL and a clarification.
    assert any(ev == "clarification" for ev, _ in events)


@pytest.mark.asyncio
async def test_non_data_verdict_answers_without_sql(memory_chat) -> None:
    service, conv, _ = memory_chat
    _enable(service)
    verdict = ClassifierVerdict(intent="OUT_OF_SCOPE_LIVE", needs_clarification=False)
    with (
        patch("app.services.chat.service.llm_configured", return_value=True),
        patch("app.services.chat.service.get_value_dictionary", new_callable=AsyncMock) as gv,
        patch("app.services.chat.service.plan_turn", side_effect=lambda i, q, **k: _clarifying_turn(q)),
        patch(
            "app.services.chat.service.classify_and_resolve",
            AsyncMock(return_value=ClassifierOutcome(verdict, "mock", 10, 10)),
        ),
    ):
        gv.return_value = ValueDictionarySnapshot(Industry.AUTOMOTIVE, ())
        await _collect_stream(service, "how are the markets doing", conv.id)
    assert service.last_history.sql_text is None
    assert service.last_profile.route == "out_of_scope_live"


@pytest.mark.asyncio
async def test_greeting_makes_no_classifier_call(memory_chat) -> None:
    service, conv, _ = memory_chat
    _enable(service)
    with (
        patch("app.services.chat.service.llm_configured", return_value=True),
        patch("app.services.chat.service.classify_and_resolve", AsyncMock()) as cls,
        patch(
            "app.services.chat.non_data_handlers.complete_text",
            AsyncMock(return_value=_result("Hello!")),
        ) as chat_llm,
    ):
        await _collect_stream(service, "Hello", conv.id)
    cls.assert_not_called()
    chat_llm.assert_not_called()


@pytest.mark.asyncio
async def test_clear_data_question_makes_no_classifier_call(memory_chat) -> None:
    service, conv, _ = memory_chat
    _enable(service)
    with (
        patch("app.services.chat.service.llm_configured", return_value=True),
        patch("app.services.chat.service.get_value_dictionary", new_callable=AsyncMock) as gv,
        patch(
            "app.services.chat.service.plan_turn",
            side_effect=lambda i, q, **k: _turn(q, clarify=False),
        ) as plan,
        patch("app.services.chat.service.classify_and_resolve", AsyncMock()) as cls,
        patch("app.services.chat.service.interpret_question", AsyncMock()) as legacy,
    ):
        gv.return_value = ValueDictionarySnapshot(Industry.AUTOMOTIVE, ())
        try:
            await _collect_stream(service, "Revenue by region", conv.id)
        except Exception:
            pass  # warehouse execution is mocked out; only the routing calls matter here
    assert plan.call_count == 1
    cls.assert_not_called()
    legacy.assert_not_called()
