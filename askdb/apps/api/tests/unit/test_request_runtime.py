"""Gated shared Chat integration: mock provider/warehouse, real application persistence."""

import json
import uuid
from datetime import date
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.config import Industry, Settings
from app.models.activity import Conversation
from app.models.enums import Role
from app.models.region_access import UserRegionAccess
from app.models.user import User
from app.semantic.service import SemanticService
from app.services.chat.request_context import RequestPrincipal, ScopedCatalog
from app.services.chat.service import ChatService
from app.services.chat.value_dictionary import BusinessValue, ValueDictionarySnapshot
from app.services.llm import LlmResult
from app.services.security.region_scope import RegionScope


@pytest.fixture
async def typed_chat(db_session):
    user = User(
        id=uuid.uuid4(),
        username="typed-test",
        email="typed@example.com",
        email_normalized="typed@example.com",
        full_name="Rahul Test",
        password_hash="x" * 20,
        role=Role.ADMIN,
        default_industry=Industry.AUTOMOTIVE,
        is_active=True,
    )
    db_session.add(user)
    await db_session.flush()
    conv = Conversation(id=uuid.uuid4(), user_id=user.id, industry="automotive", title="Typed test")
    db_session.add(conv)
    await db_session.flush()
    settings = Settings(_env_file=None, chat_typed_execution_enabled=True)
    pack = SemanticService(settings)._load_pack(Industry.AUTOMOTIVE)
    semantic = MagicMock(get_pack=AsyncMock(return_value=pack))
    analytics = AsyncMock()
    result = MagicMock()
    result.mappings.return_value.all.return_value = [
        {"revenue": 5600, "units_sold": 36, "__total_groups": 1}
    ]
    result.keys.return_value = ["revenue", "units_sold", "__total_groups"]
    result.fetchall.return_value = [("Fixture explain",)]
    analytics.execute.return_value = result
    service = ChatService(
        app_session=db_session,
        analytics=analytics,
        settings=settings,
        user=user,
        industry=Industry.AUTOMOTIVE,
        semantic_service=semantic,
    )
    principal = RequestPrincipal(user.id, RegionScope.all_regions(), Industry.AUTOMOTIVE)
    values = (BusinessValue("Make", "automotive.dim_carline.make", "Toyota"),)
    catalog = ScopedCatalog(principal.binding, ValueDictionarySnapshot(Industry.AUTOMOTIVE, values))
    return service, conv, analytics, result, catalog


def proposal(**kwargs):
    return {
        "outcome": "analytics",
        "summary": "Revenue and units",
        "measures": [{"id": "revenue"}, {"id": "units_sold"}],
        "period": {"label": "Jan 2026", "start": "2026-01-01", "end_exclusive": "2026-02-01"},
        **kwargs,
    }


async def collect(typed_chat, question, decision, cancel_event=None):
    service, conv, _, _, catalog = typed_chat
    llm = AsyncMock(
        return_value=LlmResult(
            sql=None,
            narrative="",
            model="fixture-model",
            prompt_tokens=123,
            completion_tokens=87,
            content=json.dumps(decision),
        )
    )
    with (
        patch(
            "app.services.chat.request_runtime.scoped_catalog",
            AsyncMock(return_value=(catalog, date(2026, 11, 20))),
        ),
        patch("app.services.chat.request_interpreter.llm_configured", return_value=True),
        patch("app.services.chat.request_interpreter.complete_text", llm),
        patch("app.services.chat.service.plan_turn", side_effect=AssertionError("English reparse")),
        patch(
            "app.services.chat.service.generate_validated_sql",
            side_effect=AssertionError("LLM SQL rewrite"),
        ),
    ):
        frames = [
            frame
            async for frame in service.ask_stream(question, conv.id, cancel_event=cancel_event)
        ]
    events = []
    for frame in frames:
        kind = ""
        for line in frame.splitlines():
            if line.startswith("event: "):
                kind = line[7:]
            if line.startswith("data: "):
                events.append((kind, json.loads(line[6:])))
    return events, llm


def event(events, name):
    return next(value for kind, value in events if kind == name)


@pytest.mark.asyncio
async def test_report_handoff_persists_revision_and_retains_partial_panels(typed_chat):
    service, conv, _, _, _ = typed_chat
    service._settings.ask_me_askbi_enabled = True
    result = SimpleNamespace(model_dump=lambda **kwargs: {"result": {"rows": [{"revenue": 100}]}})
    with patch(
        "app.services.analytics.bi.execution.run",
        AsyncMock(
            side_effect=[RuntimeError("panel failed"), result, result, result, result, result]
        ),
    ):
        events, _ = await collect(
            typed_chat, "Create revenue and units report January 2026", proposal(outcome="report")
        )
    report = event(events, "report")
    assert report["partial"] and len(report["panels"]) == 6
    assert sum(p["status"] == "verified" for p in report["panels"]) == 5
    assert report["revision"] == 2
    assert conv.session_memory["typedRequest"]["report"]["id"] == report["reportId"]
    with patch("app.services.analytics.bi.execution.run", AsyncMock(return_value=result)):
        followup, _ = await collect(
            typed_chat,
            "Now February 2026",
            {
                "outcome": "report",
                "summary": "Same report February 2026",
                "followup": True,
                "changed_fields": ["period"],
                "period": {
                    "label": "Feb 2026",
                    "start": "2026-02-01",
                    "end_exclusive": "2026-03-01",
                },
            },
        )
    revised = event(followup, "report")
    assert revised["reportId"] == report["reportId"] and revised["revision"] == 3


@pytest.mark.asyncio
async def test_implications_use_saved_scoped_evidence_without_new_query(typed_chat):
    _, _, analytics, _, _ = typed_chat
    await collect(typed_chat, "Revenue January 2026", proposal())
    analytics.execute.reset_mock()
    events, _ = await collect(
        typed_chat,
        "So what?",
        {"outcome": "implications", "summary": "Interpret previous result", "followup": True},
    )
    text = "".join(v["token"] for k, v in events if k == "token")
    assert "Observations:" in text and "Suggested actions:" in text
    assert analytics.execute.await_count == 0


@pytest.mark.asyncio
async def test_investigation_executes_once_and_labels_contributions(typed_chat):
    _, _, _, result, _ = typed_chat
    result.mappings.return_value.all.return_value = [
        {
            "region_name": "West",
            "current_revenue": 120,
            "baseline_revenue": 100,
            "change_revenue": 20,
            "revenue_change_pct": 20,
            "__headline_current_revenue": 120,
            "__headline_baseline_revenue": 100,
            "__missing_revenue": 0,
            "__total_groups": 1,
        }
    ]
    events, llm = await collect(
        typed_chat,
        "Why did revenue change in January 2026?",
        proposal(
            outcome="investigation",
            measures=[{"id": "revenue"}],
            group_by=["dim_region.region_name"],
        ),
    )
    text = "".join(value["token"] for kind, value in events if kind == "token")
    assert "Contributing factors" in text and "reconcile" in text
    assert "West" in text and llm.await_count == 1


@pytest.mark.asyncio
async def test_missing_report_period_is_pending_not_query(typed_chat):
    service, conv, analytics, _, _ = typed_chat
    service._settings.ask_me_askbi_enabled = True
    events, _ = await collect(
        typed_chat, "Create a report", proposal(outcome="report", period=None)
    )
    assert event(events, "clarification")["message"] == "Which date range should the report use?"
    assert conv.session_memory["typedRequest"]["pending"]
    assert analytics.execute.await_count == 0


@pytest.mark.asyncio
async def test_unapproved_ratio_investigation_has_explicit_limitation(typed_chat):
    _, _, analytics, _, _ = typed_chat
    events, _ = await collect(
        typed_chat,
        "Why did ASP change?",
        proposal(outcome="investigation", measures=[{"id": "average_selling_price"}]),
    )
    text = "".join(value["token"] for kind, value in events if kind == "token")
    assert "approved additive decomposition" in text
    assert analytics.execute.await_count == 0


@pytest.mark.asyncio
async def test_shared_execution_keeps_measures_sql_and_usage(typed_chat):
    service, conv, analytics, _, _ = typed_chat
    events, llm = await collect(typed_chat, "Revenue and units in January 2026", proposal())
    assert not any(kind == "error" for kind, _ in events), events
    assert event(events, "rows")["rows"] == [{"revenue": 5600, "units_sold": 36}]
    assert "SUM(f.total_sales)" in event(events, "sql")["sql"]
    assert event(events, "meta")["totalGroups"] == 1
    assert event(events, "meta")["typedRequest"]["measures"] == [
        {"id": "revenue", "aggregation": None},
        {"id": "units_sold", "aggregation": None},
    ]
    assert not any(kind == "chart" for kind, _ in events)  # Two totals are not chart axes.
    assert llm.await_count == service.usage_llm_steps == 1
    assert service.usage_prompt_tokens == 123 and service.usage_completion_tokens == 87
    assert analytics.execute.await_count >= 3
    stored = conv.session_memory["typedRequest"]["confirmed"]["request"]
    assert len(stored["measures"]) == 2


@pytest.mark.asyncio
async def test_empty_query_still_emits_sql_without_fabricated_zero(typed_chat):
    _, _, _, result, _ = typed_chat
    result.mappings.return_value.all.return_value = []
    events, _ = await collect(typed_chat, "Revenue and units in Jan 2026", proposal())
    assert event(events, "sql")["sql"]
    assert event(events, "rows")["rows"] == []
    assert event(events, "meta")["totalGroups"] == 0


@pytest.mark.asyncio
async def test_missing_period_pending_then_date_only_reply(typed_chat):
    service, conv, analytics, result, _ = typed_chat
    events, _ = await collect(
        typed_chat,
        "Revenue and units by model",
        proposal(period=None, group_by=["dim_carline.model"]),
    )
    assert event(events, "clarification")["message"] == "Which date range should I use?"
    assert analytics.execute.await_count == 0
    assert conv.session_memory["typedRequest"]["pending"]
    result.mappings.return_value.all.return_value = [
        {"model": "A", "revenue": 5600, "units_sold": 36, "__total_groups": 1}
    ]
    events, _ = await collect(
        typed_chat,
        "January 2026",
        {
            "outcome": "analytics",
            "summary": "Same request for January 2026",
            "followup": True,
            "changed_fields": ["period"],
            "period": proposal()["period"],
        },
    )
    assert not any(kind == "clarification" for kind, _ in events), events
    req = event(events, "meta")["typedRequest"]
    assert len(req["measures"]) == 2 and req["group_by"] == ["dim_carline.model"]
    assert conv.session_memory["typedRequest"]["pending"] is None
    assert service.usage_llm_steps == 1


@pytest.mark.asyncio
async def test_new_definition_does_not_inherit_analytics(typed_chat):
    _, _, analytics, _, _ = typed_chat
    await collect(typed_chat, "Revenue and units January 2026", proposal())
    analytics.execute.reset_mock()
    events, _ = await collect(
        typed_chat,
        "What is revenue?",
        {
            "outcome": "definition",
            "summary": "Approved revenue definition",
            "definition_terms": ["revenue"],
        },
    )
    assert not any(kind in {"sql", "rows", "chart"} for kind, _ in events)
    assert analytics.execute.await_count == 0
    assert "revenue" in "".join(value["token"] for kind, value in events if kind == "token").lower()


@pytest.mark.asyncio
async def test_greeting_uses_profile_without_provider_or_analytics(typed_chat):
    _, _, analytics, _, _ = typed_chat
    events, llm = await collect(typed_chat, "Hello", {})
    assert "Rahul" in "".join(value["token"] for kind, value in events if kind == "token")
    assert llm.await_count == analytics.execute.await_count == 0


@pytest.mark.asyncio
async def test_bad_model_decision_fails_closed_without_sql(typed_chat):
    _, _, analytics, _, _ = typed_chat
    events, llm = await collect(
        typed_chat, "Revenue January 2026", proposal(measures=[{"id": "invented_profit"}])
    )
    assert not any(kind in {"sql", "rows"} for kind, _ in events)
    assert llm.await_count == 1 and analytics.execute.await_count == 0
    assert "validation" in "".join(value["token"] for kind, value in events if kind == "token")


@pytest.mark.asyncio
async def test_scope_revoked_during_interpretation_runs_no_query(typed_chat):
    service, _, analytics, _, _ = typed_chat
    scopes = [
        RegionScope.all_regions(),
        RegionScope(unrestricted=False, zones=("West",), user_id=service._user.id),
    ]
    with patch("app.services.chat.service.load_region_scope", AsyncMock(side_effect=scopes)):
        events, _ = await collect(typed_chat, "Revenue January 2026", proposal())
    assert analytics.execute.await_count == 0
    assert not any(kind in {"sql", "rows"} for kind, _ in events)
    assert "access changed" in "".join(value["token"] for kind, value in events if kind == "token")


@pytest.mark.asyncio
async def test_failed_explain_does_not_repair_or_confirm_state(typed_chat):
    _, conv, analytics, _, _ = typed_chat
    analytics.execute.side_effect = RuntimeError("column does not exist")
    events, llm = await collect(typed_chat, "Revenue January 2026", proposal())
    assert llm.await_count == 1
    assert (
        sum(str(c.args[0]).startswith("EXPLAIN ") for c in analytics.execute.await_args_list) == 1
    )
    assert not any(str(c.args[0]).startswith("WITH ") for c in analytics.execute.await_args_list)
    assert not any(kind == "rows" for kind, _ in events)
    assert not (conv.session_memory or {}).get("typedRequest")


@pytest.mark.asyncio
async def test_truncation_count_is_visible_in_response_and_rows(typed_chat):
    _, _, _, result, _ = typed_chat
    result.mappings.return_value.all.return_value = [
        {"model": "A", "revenue": 5600, "units_sold": 36, "__total_groups": 91}
    ]
    events, _ = await collect(
        typed_chat, "Revenue units by model 2026", proposal(group_by=["dim_carline.model"])
    )
    assert event(events, "rows")["truncated"] is True
    assert event(events, "meta")["totalGroups"] == 91
    assert "Showing 1 of 91 groups" in "".join(
        value["token"] for kind, value in events if kind == "token"
    )


@pytest.mark.asyncio
async def test_greeting_survives_unavailable_catalog_and_prior_entities(typed_chat):
    service, conv, analytics, _, _ = typed_chat
    with patch(
        "app.services.chat.request_runtime.scoped_catalog",
        AsyncMock(side_effect=RuntimeError("unavailable")),
    ) as catalog:
        frames = [frame async for frame in service.ask_stream("Hello", conv.id)]
    assert "Rahul" in "".join(frames)
    assert catalog.await_count == analytics.execute.await_count == 0


@pytest.mark.asyncio
async def test_safety_rejection_does_not_load_metadata_or_call_provider(typed_chat):
    service, conv, analytics, _, _ = typed_chat
    with (
        patch(
            "app.services.chat.request_runtime.scoped_catalog",
            AsyncMock(side_effect=AssertionError("metadata read")),
        ) as catalog,
        patch(
            "app.services.chat.request_interpreter.complete_text",
            AsyncMock(side_effect=AssertionError("model call")),
        ) as llm,
    ):
        frames = [
            frame async for frame in service.ask_stream("DROP TABLE automotive.fact_sales", conv.id)
        ]
    assert "blocked" in "".join(frames).lower()
    assert catalog.await_count == llm.await_count == analytics.execute.await_count == 0


@pytest.mark.asyncio
async def test_sql_event_matches_scoped_statement_and_persists_after_reload(typed_chat):
    service, conv, analytics, result, _ = typed_chat
    service._user.role = Role.USER
    service._app.add(UserRegionAccess(user_id=service._user.id, region_id="West"))
    await service._app.flush()
    scope = RegionScope(unrestricted=False, zones=("West",), user_id=service._user.id)
    principal = RequestPrincipal(service._user.id, scope, Industry.AUTOMOTIVE)
    catalog = ScopedCatalog(principal.binding, ValueDictionarySnapshot(Industry.AUTOMOTIVE, ()))
    events, _ = await collect(
        (service, conv, analytics, result, catalog), "Revenue and units January 2026", proposal()
    )
    shown_sql = event(events, "sql")["sql"]
    executed = [
        str(call.args[0])
        for call in analytics.execute.await_args_list
        if str(call.args[0]).startswith("WITH ")
    ]
    assert executed == [shown_sql] and shown_sql.count("/*rls*/") == 1
    await service._app.commit()
    await service._app.refresh(conv)
    assert conv.session_memory["typedRequest"]["confirmed"]["sql"] == shown_sql
    assert event(events, "meta")["appliedScope"]["zones"] == ["West"]


@pytest.mark.asyncio
async def test_previous_sql_uses_authorized_state_without_new_query(typed_chat):
    _, _, analytics, _, _ = typed_chat
    first, _ = await collect(typed_chat, "Revenue and units January 2026", proposal())
    sql = event(first, "sql")["sql"]
    analytics.execute.reset_mock()
    events, _ = await collect(
        typed_chat,
        "Show the SQL",
        {"outcome": "previous_sql", "summary": "Previous authorized SQL", "followup": True},
    )
    assert event(events, "sql")["sql"] == sql
    assert analytics.execute.await_count == 0
    assert event(events, "meta")["responseKind"] == "conversation"


@pytest.mark.asyncio
async def test_typed_usage_is_reported_without_a_verifier_call(typed_chat):
    events, llm = await collect(typed_chat, "Revenue and units January 2026", proposal())
    meta = event(events, "meta")
    assert meta["responseKind"] == "data" and meta["runId"]
    assert meta["runUsage"]["initialModelCalls"] == llm.await_count == 1
    assert meta["runUsage"]["correctionModelCalls"] == 0
    assert meta["runUsage"]["analyticalQueries"] == 1
    assert meta["runUsage"]["tokensEstimated"] is False


@pytest.mark.asyncio
async def test_document_first_hybrid_keeps_verified_database_part(typed_chat):
    events, _ = await collect(
        typed_chat,
        "Using the delivery policy, show revenue January 2026",
        proposal(outcome="documents", additional_outcomes=["analytics"]),
    )
    assert event(events, "rows")["rows"]
    text = "".join(value["token"] for kind, value in events if kind == "token")
    assert "compliance is unverified" in text
    assert event(events, "meta")["responseKind"] == "partial"


@pytest.mark.asyncio
async def test_report_cancellation_stops_before_the_next_panel(typed_chat):
    import asyncio

    service, _, _, _, _ = typed_chat
    service._settings.ask_me_askbi_enabled = True
    cancel = asyncio.Event()

    async def panel(*args, **kwargs):
        cancel.set()
        return SimpleNamespace(model_dump=lambda **kw: {"result": {"columns": [], "rows": []}})

    with patch("app.services.analytics.bi.execution.run", AsyncMock(side_effect=panel)) as run:
        events, _ = await collect(
            typed_chat, "Create report for January 2026", proposal(outcome="report"), cancel
        )
    assert run.await_count == 1
    assert any(kind == "cancelled" for kind, _ in events)
    assert not any(kind == "report" for kind, _ in events)
