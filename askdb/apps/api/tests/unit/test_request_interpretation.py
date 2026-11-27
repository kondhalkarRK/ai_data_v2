"""Batch 1: contract/routing tests. Provider responses are fixtures, not accuracy claims."""

from __future__ import annotations

import asyncio
import json
import uuid
from dataclasses import replace
from datetime import date
from unittest.mock import AsyncMock, patch

import pytest
from pydantic import ValidationError

from app.core.config import Industry, Settings
from app.core.exceptions import AuthorizationError
from app.semantic.service import SemanticService
from app.services.chat.request_context import (
    ContextBudgetError,
    PreviousRequest,
    RequestPrincipal,
    ScopedCatalog,
    build_request_context,
)
from app.services.chat.request_contract import InterpretedRequest
from app.services.chat.request_interpreter import InterpretationInput, preview_request
from app.services.chat.value_dictionary import BusinessValue, ValueDictionarySnapshot
from app.services.llm import LlmResult
from app.services.security.region_scope import RegionScope


@pytest.fixture(scope="module")
def pack():
    return SemanticService(Settings())._load_pack(Industry.AUTOMOTIVE)


@pytest.fixture
def principal():
    return RequestPrincipal(uuid.uuid4(), RegionScope.all_regions(), Industry.AUTOMOTIVE)


def catalog_for(principal):
    values = [
        BusinessValue("Make", "automotive.dim_carline.make", "Toyota"),
        BusinessValue("Make", "automotive.dim_carline.make", "Tata"),
        BusinessValue("Model", "automotive.dim_carline.model", "Orion Plus"),
        BusinessValue("Model", "automotive.dim_carline.model", "Comet Trail"),
        BusinessValue("Model", "automotive.dim_carline.model", "Venue"),
        BusinessValue("Region", "automotive.dim_region.region_name", "West"),
        BusinessValue("Region", "automotive.dim_region.region_name", "South"),
    ]
    return ScopedCatalog(
        principal.binding, ValueDictionarySnapshot(principal.industry, tuple(values))
    )


def context_for(pack, principal, question, **kwargs):
    return build_request_context(
        question,
        pack=pack,
        principal=principal,
        catalog=catalog_for(principal),
        current_date=date(2026, 11, 26),
        **kwargs,
    )


async def interpret(
    pack, principal, question, proposal, *, settings=None, context=None, result=None
):
    context = context or context_for(pack, principal, question)
    response = result or LlmResult(
        sql=None,
        narrative="",
        model="fixture-model",
        prompt_tokens=123,
        completion_tokens=87,
        content=json.dumps(proposal),
    )
    llm = AsyncMock(return_value=response)
    # Tripwires prove routing-only never plans, retrieves, or creates a report.
    with (
        patch("app.services.chat.request_interpreter.llm_configured", return_value=True),
        patch("app.services.chat.request_interpreter.complete_text", llm),
        patch("app.services.chat.pipeline.plan_turn", side_effect=AssertionError("SQL planning")),
        patch(
            "app.services.knowledge.KnowledgeService.search_authorized",
            side_effect=AssertionError("retrieval"),
        ),
        patch(
            "app.services.analytics.bi.service.turn", side_effect=AssertionError("report creation")
        ),
    ):
        output = await preview_request(
            settings=settings
            or Settings(
                chat_request_preview_enabled=True,
                ask_me_askbi_enabled=False,
                chat_general_knowledge_enabled=False,
            ),
            incoming=InterpretationInput(question, principal, context, "Rahul Kondhalkar"),
        )
    return output, llm


def test_context_searches_every_measure_and_includes_models(pack, principal):
    ctx = context_for(pack, principal, "Compare Orion Plus and Comet Trail units and ASP by region")
    assert {m["id"] for m in ctx.payload["measures"]} >= {"units_sold", "average_selling_price"}
    assert {e["value"] for e in ctx.payload["entities"]} >= {"Orion Plus", "Comet Trail"}
    assert "dim_carline.model" in ctx.payload["fields"]


def test_sensitive_fields_excluded_and_question_coverage_is_independent(pack, principal):
    from app.services.chat.request_interpreter import validate_question_coverage

    ctx = context_for(pack, principal, "revenue and units")
    assert "dim_salesman.email" not in ctx.payload["fields"]
    incomplete = InterpretedRequest(
        outcome="analytics", summary="Revenue only", measures=[{"id": "revenue"}]
    )
    with pytest.raises(ValueError, match="omitted"):
        validate_question_coverage("Revenue and units sold", incomplete, ctx)


@pytest.mark.parametrize(
    "question",
    ["Units sold without revenue", "Show units sold; exclude revenue", "Units sold, not revenue"],
)
def test_measure_exclusion_does_not_require_that_output(pack, principal, question):
    from app.services.chat.request_interpreter import validate_question_coverage

    ctx = context_for(pack, principal, question)
    req = InterpretedRequest(
        outcome="analytics", summary="Units only", measures=[{"id": "units_sold"}]
    )
    validate_question_coverage(question, req, ctx)
    assert ctx.payload["relationships"] and ctx.payload["facts"]
    assert ctx.payload["calendar_date"] == "2026-11-26"
    assert ctx.payload["data_as_of"] is None


def test_measure_name_does_not_become_a_fuzzy_entity(pack, principal):
    ctx = context_for(pack, principal, "How is revenue defined?")
    assert "Venue" not in {e["value"] for e in ctx.payload["entities"]}
    assert any(g["id"] == "Revenue" for g in ctx.payload["glossary"])


@pytest.mark.parametrize(
    "question",
    [
        "Compare Orion Plus and Comet Trail units sold",
        "How many units were sold for ORION PLUS versus COMET TRAIL?",
        "Orion Plus vs Comet Trail sales volume",
        "Compare Orion Pluss and Comet Trail cars sold",
    ],
)
def test_context_candidates_cover_paraphrases_and_spelling_variants(pack, principal, question):
    context = context_for(pack, principal, question)
    assert {e["value"] for e in context.payload["entities"]} >= {"Orion Plus", "Comet Trail"}
    assert "units_sold" in {m["id"] for m in context.payload["measures"]}


def test_late_pack_measure_is_not_excluded_by_static_vocabulary(pack, principal):
    changed = pack.model_copy(deep=True)
    changed.model.measures["demo_adjusted_revenue"] = changed.model.measures["revenue"].model_copy(
        update={"display_name": "Adjusted proceeds", "synonyms": ["adjusted turnover"]}
    )
    ctx = context_for(changed, principal, "Adjusted turnover by region")
    assert "demo_adjusted_revenue" in {m["id"] for m in ctx.payload["measures"]}


def test_context_is_bound_to_owner_scope_industry_and_pack(pack, principal):
    question = "Revenue by region"
    with pytest.raises(AuthorizationError):
        build_request_context(
            question,
            pack=pack,
            principal=principal,
            catalog=catalog_for(replace(principal, user_id=uuid.uuid4())),
        )
    previous = PreviousRequest(
        principal.binding,
        "stale",
        "prior",
        InterpretedRequest(
            outcome="analytics",
            summary="Revenue",
            measures=[{"id": "revenue"}],
        ),
    )
    with pytest.raises(AuthorizationError):
        context_for(pack, principal, question, previous=previous)
    with pytest.raises(AuthorizationError):
        context_for(pack, replace(principal, industry=Industry.INSURANCE), question)


def test_scoped_catalog_cannot_add_global_values(pack, principal):
    restricted = replace(principal, scope=RegionScope(False, ("West",), principal.user_id))
    ctx = context_for(pack, restricted, "West and South")
    assert "South" not in {e["value"] for e in ctx.payload["entities"]}
    ctx_without_catalog = build_request_context("Tata", pack=pack, principal=restricted)
    assert not ctx_without_catalog.payload["entities"]
    assert ctx_without_catalog.payload["catalog_available"] is False


def test_budget_fails_explicitly_instead_of_truncating_requested_context(pack, principal):
    with pytest.raises(ContextBudgetError):
        context_for(pack, principal, "Toyota Tata units revenue ASP", max_chars=100)


@pytest.mark.asyncio
async def test_multi_measure_comparison_filters_grouping_and_windows_survive(pack, principal):
    question = "Compare Toyota and Tata revenue and units by region this quarter vs last quarter"
    ctx = context_for(pack, principal, question)
    ids = [e["id"] for e in ctx.payload["entities"] if e["value"] in {"Toyota", "Tata"}]
    proposal = {
        "outcome": "analytics",
        "summary": question,
        "measures": [{"id": "revenue"}, {"id": "units_sold"}],
        "entity_ids": ids,
        "filters": [{"field": "dim_carline.make", "operator": "in", "entity_ids": ids}],
        "group_by": ["dim_region.region_name", "dim_carline.make"],
        "time_grain": "month",
        "comparisons": [
            {
                "kind": "period",
                "current": {"label": "This quarter", "relative": "this_quarter"},
                "baseline": {"label": "Last quarter", "relative": "last_quarter"},
            }
        ],
        "windows": [
            {
                "operation": "running_total",
                "measure_ids": ["units_sold"],
                "order_by": "fact_sales.sales_date",
                "partition_by": ["dim_region.region_name"],
                "reset": "calendar_year",
            }
        ],
    }
    result, llm = await interpret(pack, principal, question, proposal, context=ctx)
    assert result.status == "ready" and result.routes == ["askme"]
    assert result.request.model_dump(mode="json", exclude_defaults=True) == proposal
    assert result.original_question == question
    assert result.execution_enabled is False
    assert result.usage.input_tokens == 123 and result.usage.output_tokens == 87
    assert result.usage.tokens_estimated is False
    assert result.usage.calls == llm.await_count == 1
    assert llm.await_args.kwargs["max_tokens"] <= 600


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("question", "proposal", "route", "status"),
    [
        (
            "How is revenue defined?",
            {
                "outcome": "definition",
                "summary": "Revenue definition",
                "definition_terms": ["revenue"],
            },
            "glossary",
            "ready",
        ),
        (
            "Is any region's data incomplete?",
            {"outcome": "data_quality", "summary": "Regional data quality"},
            "data_trust",
            "ready",
        ),
        (
            "Why did revenue decline?",
            {
                "outcome": "investigation",
                "summary": "Revenue contributors",
                "measures": [{"id": "revenue"}],
            },
            "askme_investigation",
            "ready",
        ),
        (
            "Create a sales report last month",
            {
                "outcome": "report",
                "summary": "Monthly sales report",
                "measures": [{"id": "revenue"}],
            },
            "askbi",
            "unavailable",
        ),
        (
            "Show me sales",
            {
                "outcome": "clarification",
                "summary": "Ambiguous measure",
                "unresolved": ["measure"],
                "clarification": "Revenue, units or orders?",
            },
            None,
            "clarification",
        ),
        (
            "What does the delivery policy say?",
            {"outcome": "documents", "summary": "Delivery policy"},
            "documents_gated",
            "unavailable",
        ),
        (
            "Revenue and applicable delivery policy",
            {
                "outcome": "analytics",
                "additional_outcomes": ["documents"],
                "summary": "Sales and policy",
                "measures": [{"id": "revenue"}],
            },
            "askme",
            "partial",
        ),
        (
            "Explain a rainbow",
            {
                "outcome": "general_knowledge",
                "summary": "Ordinary question",
                "reply": "A rainbow forms through light interacting with water droplets.",
            },
            None,
            "unsupported",
        ),
        (
            "So what should we do?",
            {
                "outcome": "clarification",
                "summary": "Missing prior evidence",
                "clarification": "Which result should I explain?",
            },
            None,
            "clarification",
        ),
    ],
)
async def test_routing_only_outcomes(pack, principal, question, proposal, route, status):
    result, _ = await interpret(pack, principal, question, proposal)
    assert result.status == status
    assert (route in result.routes) if route else not result.routes
    assert result.execution_enabled is False


@pytest.mark.asyncio
async def test_greeting_personalization_and_default_off_make_no_model_call(pack, principal):
    greeting, llm = await interpret(pack, principal, "Hello", {})
    assert greeting.request.reply.startswith("Hello, Rahul!")
    llm.assert_not_called()
    disabled, llm = await interpret(pack, principal, "Revenue", {}, settings=Settings())
    assert disabled.status == "disabled"
    llm.assert_not_called()


@pytest.mark.asyncio
async def test_greeting_prefix_does_not_swallow_business_question(pack, principal):
    result, llm = await interpret(
        pack,
        principal,
        "Hi show revenue",
        {
            "outcome": "analytics",
            "summary": "Revenue",
            "measures": [{"id": "revenue"}],
        },
    )
    assert result.routes == ["askme"]
    llm.assert_awaited_once()


@pytest.mark.asyncio
async def test_normal_knowledge_uses_initial_reply_and_respects_feature_setting(pack, principal):
    result, llm = await interpret(
        pack,
        principal,
        "Explain a rainbow",
        {
            "outcome": "general_knowledge",
            "summary": "Ordinary question",
            "reply": "Light interacting with water droplets produces a rainbow.",
        },
        settings=Settings(chat_request_preview_enabled=True, chat_general_knowledge_enabled=True),
    )
    assert result.routes == ["general_knowledge"]
    assert result.request.reply.startswith("Light")
    llm.assert_awaited_once()


def test_post_aggregation_and_having_do_not_replace_approved_formulas(pack, principal):
    context = context_for(pack, principal, "Average revenue by region")
    request = InterpretedRequest(
        outcome="analytics",
        summary="Average regional revenue",
        measures=[{"id": "revenue"}],
        operations=[
            {"operation": "avg", "measure_ids": ["revenue"], "group_by": ["dim_region.region_name"]}
        ],
        measure_filters=[{"measure_id": "revenue", "operator": "gt", "value": 1000000}],
        ranking={"measure_id": "revenue", "include_both_ends": True},
    )
    from app.services.chat.request_interpreter import validate_proposal

    validate_proposal(request, context)
    assert request.measures[0].aggregation is None
    assert request.operations[0].operation == "avg"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "extra",
    [
        {"sql": "SELECT 1"},
        {"user_id": "admin"},
        {"outcome": "RUN_SQL"},
        {"measures": [{"id": "net_profit"}]},
        {"group_by": ["secret.password"]},
        {"entity_ids": ["invented-model"]},
        {
            "filters": [
                {"field": "dim_region.region_name", "operator": "eq", "values": ["Invented"]}
            ]
        },
    ],
)
async def test_unapproved_or_authority_fields_are_rejected(pack, principal, extra):
    payload = {
        "outcome": "analytics",
        "summary": "Revenue",
        "measures": [{"id": "revenue"}],
        **extra,
    }
    result, llm = await interpret(pack, principal, "Revenue", payload)
    assert result.status == "unavailable" and result.request is None
    assert "validation" in result.reason
    llm.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize("content", ["not json", "```json\n{}\n```", '{"outcome":"analytics"}'])
async def test_invalid_provider_output_never_becomes_analytical_execution(pack, principal, content):
    result, llm = await interpret(
        pack,
        principal,
        "Revenue",
        {},
        result=LlmResult(
            sql=None,
            narrative="",
            model="fixture",
            content=content,
        ),
    )
    assert result.status == "unavailable"
    assert result.usage.tokens_estimated
    llm.assert_awaited_once()


@pytest.mark.asyncio
async def test_provider_timeout_is_unavailable_not_user_ambiguity(pack, principal):
    result, llm = await interpret(
        pack,
        principal,
        "Revenue",
        {},
        result=LlmResult(
            sql=None,
            narrative="",
            model="fixture",
            timed_out=True,
        ),
    )
    assert result.status == "unavailable" and result.request is None
    assert result.usage.calls == 1
    llm.assert_awaited_once()


@pytest.mark.asyncio
async def test_open_circuit_does_not_charge_invented_provider_tokens(pack, principal):
    result, _ = await interpret(
        pack,
        principal,
        "Revenue",
        {},
        result=LlmResult(
            sql=None,
            narrative="",
            model="fixture",
            circuit_open=True,
        ),
    )
    assert result.status == "unavailable"
    assert result.usage.calls == result.usage.input_tokens == result.usage.output_tokens == 0
    assert result.usage.tokens_estimated is False


@pytest.mark.asyncio
@pytest.mark.parametrize("enabled", [False, True])
async def test_report_route_respects_existing_askbi_gate_without_creating_report(
    pack, principal, enabled
):
    result, llm = await interpret(
        pack,
        principal,
        "Create a revenue report",
        {
            "outcome": "report",
            "summary": "Revenue report",
            "measures": [{"id": "revenue"}],
        },
        settings=Settings(chat_request_preview_enabled=True, ask_me_askbi_enabled=enabled),
    )
    assert result.routes == ["askbi"]
    assert result.status == ("ready" if enabled else "unavailable")
    assert not result.execution_enabled
    llm.assert_awaited_once()


@pytest.mark.asyncio
async def test_real_deadline_and_cancellation_propagation(pack, principal):
    context = context_for(pack, principal, "Revenue")
    settings = Settings(chat_request_preview_enabled=True).model_copy(
        update={"nlq_llm_timeout_seconds": 0.01}
    )

    async def slow(**kwargs):
        await asyncio.sleep(1)

    with (
        patch("app.services.chat.request_interpreter.llm_configured", return_value=True),
        patch("app.services.chat.request_interpreter.complete_text", side_effect=slow) as llm,
    ):
        result = await preview_request(
            settings=settings,
            incoming=InterpretationInput(
                "Revenue",
                principal,
                context,
            ),
        )
    assert result.status == "unavailable" and "timed out" in result.reason
    llm.assert_awaited_once()
    with (
        patch("app.services.chat.request_interpreter.llm_configured", return_value=True),
        patch(
            "app.services.chat.request_interpreter.complete_text",
            side_effect=asyncio.CancelledError,
        ),
        pytest.raises(asyncio.CancelledError),
    ):
        await preview_request(
            settings=settings,
            incoming=InterpretationInput(
                "Revenue",
                principal,
                context,
            ),
        )


@pytest.mark.asyncio
async def test_previous_implications_use_authorized_request_and_preserve_scope(pack, principal):
    old = context_for(pack, principal, "Toyota revenue in 2025")
    request = InterpretedRequest(
        outcome="analytics",
        summary="Toyota revenue in 2025",
        measures=[{"id": "revenue"}],
        group_by=["dim_region.region_name"],
    )
    prior = PreviousRequest(principal.binding, old.semantic_version, "run-1", request)
    prior.request.summary = "The confirmed selection"
    context = context_for(pack, principal, "So what should we do?", previous=prior)
    result, _ = await interpret(
        pack,
        principal,
        "So what should we do?",
        {
            "outcome": "implications",
            "summary": "Implications of the previous result",
            "followup": True,
            "measures": [{"id": "revenue"}],
            "evidence": [{"id": "prior", "source": "previous_result"}],
        },
        context=context,
    )
    assert result.routes == ["previous_result"]
    assert result.status == "ready" and not result.execution_enabled


@pytest.mark.asyncio
async def test_denied_scope_or_unsafe_request_does_not_reach_model(pack, principal):
    restricted = replace(principal, scope=RegionScope(False, ("West",), principal.user_id))
    result, llm = await interpret(pack, restricted, "Revenue in South", {})
    assert result.status == "denied"
    llm.assert_not_called()
    result, llm = await interpret(pack, principal, "Drop table fact_sales", {})
    assert result.status == "unsupported"
    llm.assert_not_called()


def test_previous_typed_request_retains_context_and_is_owner_bound(pack, principal):
    old = context_for(pack, principal, "Toyota revenue in 2025")
    entity_ids = [e["id"] for e in old.payload["entities"] if e["value"] == "Toyota"]
    request = InterpretedRequest(
        outcome="analytics",
        summary="Toyota revenue in 2025",
        measures=[{"id": "revenue"}],
        entity_ids=entity_ids,
        filters=[{"field": "dim_carline.make", "operator": "in", "entity_ids": entity_ids}],
        group_by=["dim_region.region_name"],
    )
    prior = PreviousRequest(principal.binding, old.semantic_version, "run-1", request)
    new = context_for(pack, principal, "Last quarter", previous=prior)
    assert (
        new.payload["previous"]["request"]["filters"]
        == request.model_dump(exclude_defaults=True)["filters"]
    )
    assert "revenue" in {m["id"] for m in new.payload["measures"]}


@pytest.mark.parametrize(
    "payload",
    [
        {
            "comparisons": [
                {"kind": "period", "current": {"label": "Q1", "relative": "last_quarter"}}
            ]
        },
        {
            "windows": [
                {
                    "operation": "running_total",
                    "measure_ids": ["units_sold"],
                    "order_by": "fact_sales.sales_date",
                }
            ]
        },
        {"evidence": [{"id": "b", "source": "database", "depends_on": ["a"]}]},
    ],
)
def test_contract_rejects_lost_baseline_unknown_window_measure_and_cyclic_dependencies(payload):
    with pytest.raises(ValidationError):
        InterpretedRequest.model_validate(
            {
                "outcome": "analytics",
                "summary": "Revenue",
                "measures": [{"id": "revenue"}],
                **payload,
            }
        )
