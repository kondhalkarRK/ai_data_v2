"""Gated Chat integration with fixture model replies and in-memory warehouse.

No office endpoint or human holdout is exercised by these tests.
"""
# ruff: noqa: F811
# Imported pytest fixtures intentionally share dependency-injection parameter names.

import json
from datetime import date
from unittest.mock import AsyncMock, patch

import pytest

from app.core.config import Settings
from app.services.chat.request_interpreter import InterpretationInput, preview_request
from app.services.llm import LlmResult
from tests.unit.test_analytical_execution import Connection, warehouse  # noqa: F401
from tests.unit.test_analytical_plan import base_review  # noqa: F401
from tests.unit.test_request_compiler import fixture  # noqa: F401
from tests.unit.test_request_runtime import typed_chat  # noqa: F401

REGION = "dim_region.region_name"
MODEL = "dim_carline.model"


def proposal():
    return {
        "outcome": "analytics",
        "summary": "Find the leading region, then its models",
        "measures": [{"id": "revenue"}],
        "group_by": [REGION, MODEL],
        "period": {"label": "Q1 2026", "start": "2026-01-01", "end_exclusive": "2026-04-01"},
        "analysis_tasks": [
            {"id": "regions", "operation": "aggregate", "group_by": [REGION]},
            {
                "id": "leader",
                "operation": "select_extreme",
                "source": "regions",
                "ranking": {
                    "measure_id": "revenue",
                    "basis": "value",
                    "direction": "desc",
                    "limit": 1,
                    "ties": "include",
                },
            },
            {
                "id": "models",
                "operation": "aggregate",
                "group_by": [MODEL],
                "source": "leader",
                "binding_kind": "entity_set",
                "binding_field": REGION,
                "ranking": {
                    "measure_id": "revenue",
                    "basis": "value",
                    "direction": "desc",
                    "limit": 10,
                    "ties": "include",
                },
            },
        ],
    }


def verdict(**updates):
    return {
        "coverage_complete": True,
        "task_ids": ["regions", "leader", "models"],
        "reason": "All requested operations and scope retained.",
        **updates,
    }


def reply(payload, **updates):
    return LlmResult(
        sql=None,
        narrative="",
        model="fixture-model",
        prompt_tokens=100,
        completion_tokens=50,
        content=json.dumps(payload),
        **updates,
    )


@pytest.fixture
def incoming(base_review):
    return InterpretationInput(
        "Find the highest revenue region, then rank models inside it in Q1 2026",
        base_review.principal,
        base_review.context,
        "Rahul",
    )


def settings(**updates):
    return Settings(
        _env_file=None,
        chat_request_preview_enabled=True,
        chat_dependent_analysis_enabled=True,
        chat_typed_execution_enabled=True,
        **updates,
    )


async def preview(incoming, outputs):
    provider = AsyncMock(side_effect=outputs)
    with (
        patch("app.services.chat.request_interpreter.llm_configured", return_value=True),
        patch("app.services.chat.request_interpreter.complete_text", provider),
    ):
        result = await preview_request(settings=settings(), incoming=incoming)
    return result, provider


async def test_compound_inventory_checked_in_two_calls_without_specialist_work(incoming):
    with patch(
        "app.services.chat.analytical_plan_compiler.compile_analysis",
        side_effect=AssertionError("SQL"),
    ):
        result, provider = await preview(incoming, [reply(proposal()), reply(verdict())])
    assert result.status == "ready"
    assert provider.await_count == result.usage.calls == 2
    assert result.usage.verification_calls == 1
    assert result.usage.input_tokens == 200 and result.usage.output_tokens == 100
    assert not result.usage.tokens_estimated
    payloads = [json.loads(call.kwargs["user"]) for call in provider.await_args_list]
    assert set(payloads[0]) == {"question", "approved_context"}
    assert set(payloads[1]) == {"question", "authorized_interpretation", "approved_context"}
    assert all("rows" not in payload and "results" not in payload for payload in payloads)


async def test_disagreed_inventory_clarifies_without_third_call(incoming):
    result, provider = await preview(
        incoming,
        [
            reply(proposal()),
            reply(
                verdict(
                    coverage_complete=False,
                    reason="The metric is ambiguous.",
                    clarification="Which measure should define the leading region?",
                )
            ),
        ],
    )
    assert result.status == "clarification"
    assert result.request.clarification.startswith("Which measure")
    assert provider.await_count == 2


async def test_missing_inventory_can_be_vetoed_not_silently_simplified(incoming):
    simple = proposal()
    simple.pop("analysis_tasks")
    result, provider = await preview(
        incoming,
        [
            reply(simple),
            reply(
                verdict(
                    task_ids=[],
                    coverage_complete=False,
                    reason="The selected-region dependency was omitted.",
                )
            ),
        ],
    )
    assert result.status == "unsupported"
    assert provider.await_count == 2


async def test_simple_question_keeps_one_call(incoming):
    simple = proposal()
    simple.pop("analysis_tasks")
    simple["group_by"] = [REGION]
    incoming = InterpretationInput(
        "Revenue by region in Q1 2026", incoming.principal, incoming.context
    )
    result, provider = await preview(incoming, [reply(simple)])
    assert result.status == "ready" and result.usage.calls == 1
    assert provider.await_count == 1


async def test_greeting_uses_no_provider_call(incoming):
    incoming = InterpretationInput("Hello", incoming.principal, incoming.context, "Rahul")
    result, provider = await preview(incoming, [])
    assert "Rahul" in result.request.reply
    assert not provider.await_count


async def test_provider_failure_is_not_a_business_clarification(incoming):
    result, provider = await preview(
        incoming, [reply(proposal()), RuntimeError("secret endpoint details")]
    )
    assert result.status == "unavailable"
    assert provider.await_count == 2 and result.usage.calls == 2
    assert "secret" not in result.model_dump_json()


async def test_cancel_after_interpretation_skips_verification(incoming):
    from dataclasses import replace

    stop = False

    async def provider_reply(**kwargs):
        nonlocal stop
        stop = True
        return reply(proposal())

    provider = AsyncMock(side_effect=provider_reply)
    incoming = replace(incoming, cancel_requested=lambda: stop)
    with (
        patch("app.services.chat.request_interpreter.llm_configured", return_value=True),
        patch("app.services.chat.request_interpreter.complete_text", provider),
    ):
        result = await preview_request(settings=settings(), incoming=incoming)
    assert provider.await_count == 1 and result.usage.verification_calls == 0
    assert result.reason == "Request cancelled."


async def test_checker_cannot_approve_missing_dependent_inventory(incoming):
    simple = proposal()
    simple.pop("analysis_tasks")
    result, provider = await preview(
        incoming, [reply(simple), reply(verdict(task_ids=[], requires_dependencies=True))]
    )
    assert result.status == "unsupported"
    assert "omitted" in result.reason and provider.await_count == 2


def test_date_followup_retains_dependent_inventory():
    from app.services.chat.request_state import merge_proposal

    original = proposal()
    changed = merge_proposal(
        json.dumps(
            {
                "outcome": "analytics",
                "summary": "Change only period",
                "followup": True,
                "changed_fields": ["period"],
                "period": {"label": "Q2", "start": "2026-04-01", "end_exclusive": "2026-07-01"},
            }
        ),
        {"request": original},
    )
    assert [t.id for t in changed.analysis_tasks] == [t["id"] for t in original["analysis_tasks"]]
    assert changed.group_by == original["group_by"]
    assert changed.period.start == date(2026, 4, 1)


def test_factory_and_ordinary_compiler_reject_silent_measure_loss(base_review):
    from app.services.chat.analytical_plan_factory import materialize_plan
    from app.services.chat.request_compiler import TypedCompileError, compile_request
    from app.services.chat.request_contract import InterpretedRequest

    data = proposal()
    data["measures"].append({"id": "units_sold"})
    for task in data["analysis_tasks"]:
        task["measures"] = ["revenue"]
    request = InterpretedRequest.model_validate_json(json.dumps(data))
    with pytest.raises(TypedCompileError, match="dropped a requested measure"):
        materialize_plan(request, base_review, today=date(2026, 11, 26))
    with pytest.raises(TypedCompileError, match="cannot be simplified"):
        compile_request(
            request,
            pack=base_review.pack,
            context=base_review.context,
            principal=base_review.principal,
            today=date(2026, 11, 26),
        )


def test_conditional_comparison_inventory_reaches_executable_plan(warehouse):
    from app.services.chat.analytical_plan_compiler import compile_analysis
    from app.services.chat.analytical_plan_execution import check_results
    from app.services.chat.analytical_plan_factory import materialize_plan
    from app.services.chat.request_contract import InterpretedRequest
    from tests.unit.test_analytical_execution import adapted

    review, db = warehouse
    db.execute("UPDATE automotive.fact_sales SET total_sales=1500 WHERE order_id=3")
    request = InterpretedRequest.model_validate_json(
        json.dumps(
            {
                "outcome": "analytics",
                "summary": "Revenue up but units down",
                "measures": [{"id": "revenue"}, {"id": "units_sold"}],
                "group_by": [MODEL],
                "period": {
                    "label": "February",
                    "start": "2026-02-01",
                    "end_exclusive": "2026-03-01",
                },
                "analysis_tasks": [
                    {
                        "id": "opposite",
                        "operation": "compare",
                        "group_by": [MODEL],
                        "change_conditions": [
                            {"measure_id": "revenue", "operator": "gt"},
                            {"measure_id": "units_sold", "operator": "lt"},
                        ],
                    }
                ],
            }
        )
    )
    plan, review = materialize_plan(request, review, today=date(2026, 11, 26))
    compiled = compile_analysis(plan, review, today=date(2026, 11, 26))
    result = check_results(compiled, [dict(row) for row in db.execute(adapted(compiled.sql))])
    assert len(result.steps[0].rows) == 1
    assert result.steps[0].rows[0]["revenue_change"] == 500
    assert result.steps[0].rows[0]["units_sold_change"] == -5


async def test_common_chat_backend_executes_one_compound_query_and_persists_events(
    typed_chat, warehouse
):
    service, conversation, _, _, catalog = typed_chat
    _, db = warehouse
    service._settings.chat_dependent_analysis_enabled = True
    connection = Connection(db)
    service._analytics = connection
    provider = AsyncMock(side_effect=[reply(proposal()), reply(verdict())])
    with (
        patch(
            "app.services.chat.request_runtime.scoped_catalog",
            AsyncMock(return_value=(catalog, date(2026, 11, 20))),
        ),
        patch("app.services.chat.request_interpreter.llm_configured", return_value=True),
        patch("app.services.chat.request_interpreter.complete_text", provider),
        patch("app.services.chat.service.plan_turn", side_effect=AssertionError("legacy reparse")),
    ):
        frames = [
            frame
            async for frame in service.ask_stream(
                "Find the highest revenue region, then rank models inside it in Q1 2026",
                conversation.id,
            )
        ]
    events = [
        (
            frame.splitlines()[0][7:],
            json.loads(next(line[6:] for line in frame.splitlines() if line.startswith("data: "))),
        )
        for frame in frames
    ]
    meta = next(payload for kind, payload in events if kind == "meta")
    assert meta["analyticalExecution"]["status"] == "completed", events
    assert len(meta["analyticalExecution"]["steps"]) == 3
    assert meta["runUsage"]["initialModelCalls"] == 1
    assert meta["runUsage"]["verificationModelCalls"] == 1
    assert meta["runUsage"]["analyticalQueries"] == 1
    assert provider.await_count == service.usage_llm_steps == 2
    assert any(kind == "sql" for kind, _ in events)
    assert "South" in "".join(payload["token"] for kind, payload in events if kind == "token")
    assert sum(sql.startswith("WITH ") for sql in connection.statements) == 1


async def test_missing_completeness_is_unavailable_without_analytical_sql(typed_chat):
    service, conversation, connection, _, catalog = typed_chat
    service._settings.chat_dependent_analysis_enabled = True
    data = proposal()
    data["group_by"] = []
    data["analysis_tasks"] = [
        {"id": "months", "operation": "aggregate", "time_grain": "month"},
        {
            "id": "lowest",
            "operation": "select_extreme",
            "source": "months",
            "ranking": {
                "measure_id": "revenue",
                "basis": "value",
                "direction": "asc",
                "limit": 1,
                "ties": "include",
            },
        },
    ]
    provider = AsyncMock(side_effect=[reply(data), reply(verdict(task_ids=["months", "lowest"]))])
    with (
        patch(
            "app.services.chat.request_runtime.scoped_catalog",
            AsyncMock(return_value=(catalog, date(2026, 11, 20))),
        ),
        patch("app.services.chat.request_interpreter.llm_configured", return_value=True),
        patch("app.services.chat.request_interpreter.complete_text", provider),
    ):
        frames = [
            f
            async for f in service.ask_stream(
                "Find the lowest revenue month in Q1 2026", conversation.id
            )
        ]
    assert "An administrator needs to connect approved load-status evidence" in "".join(frames)
    assert '"responseKind": "unavailable"' in "".join(frames)
    assert not any("WITH " in str(call) for call in connection.execute.await_args_list)
    assert not any(frame.startswith("event: sql\n") for frame in frames)
