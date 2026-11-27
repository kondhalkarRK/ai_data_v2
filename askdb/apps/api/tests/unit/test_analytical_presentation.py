"""Visible local presentation/audit fixtures, not live gateway or human holdouts."""
# ruff: noqa: F811

import json
import uuid
from datetime import date
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from app.core.exceptions import AuthorizationError, NotFoundError
from app.services.chat.analytical_plan_audit import build_audit
from app.services.chat.analytical_plan_presentation import narrative, presentation, progress_payload
from app.services.chat.responses import check_access, owned_response
from app.services.security.region_scope import RegionScope
from tests.unit.test_analytical_execution import run, warehouse  # noqa: F401
from tests.unit.test_analytical_plan import (  # noqa: F401
    base_review,
    extreme_period_example,
    region_example,
)
from tests.unit.test_dependent_chat import proposal, reply, verdict
from tests.unit.test_request_compiler import fixture  # noqa: F401
from tests.unit.test_request_runtime import typed_chat  # noqa: F401

TODAY = date(2026, 11, 26)


def test_result_bound_narrative_covers_selection_baseline_and_contributors(warehouse):
    compiled, review, _, result = run(warehouse, extreme_period_example)
    with patch("app.services.llm.complete_text", side_effect=AssertionError("narration model")):
        view = presentation(compiled.plan, result, review.pack, today=TODAY, context=review.context)
        text = narrative(view)
    assert len(view["steps"]) == 4
    assert "2026-02-01" in text and "2026-01-01" in text
    assert "₹1,000" in text and "₹3,000" in text and "-₹2,000" in text
    assert "South" in text and "-₹1,500" in text
    assert "not proof of causation" in text
    assert view["checks"][0]["passed"]
    assert all(s["title"] != s["id"] for s in view["steps"])
    assert view["steps"][2]["comparisonPeriods"][0] == {
        "currentStart": "2026-02-01",
        "currentEnd": "2026-03-01",
        "baselineStart": "2026-01-01",
        "baselineEnd": "2026-02-01",
    }


def test_wrong_reconciliation_never_gets_contributor_narration(warehouse):
    compiled, review, _, result = run(warehouse, extreme_period_example)
    detail = next(s for s in result.steps if s.id == "contributors")
    detail.status, detail.verified = "partial", False
    detail.rows[0]["revenue_change"] = -987654321
    result.status = "partial"
    result.checks[0]["passed"] = False
    view = presentation(compiled.plan, result, review.pack, today=TODAY)
    text = narrative(view)
    assert view["status"] == "partial"
    assert "Contributing factors could not be verified" in text
    assert "98.77 Cr" not in text and "987654321" not in text


def test_zero_and_missing_values_are_different_in_text(warehouse):
    compiled, review, _, result = run(warehouse, extreme_period_example)
    head = next(s for s in result.steps if s.id == "headline")
    head.rows[0]["revenue_current"] = 0
    head.rows[0]["revenue_baseline"] = None
    view = presentation(compiled.plan, result, review.pack, today=TODAY)
    summary = next(s for s in view["steps"] if s["id"] == "headline")["summary"]
    assert "current: ₹0" in summary and "baseline: Unavailable" in summary


def test_display_snapshot_never_rebases_explicit_dates_on_replay(warehouse):
    compiled, review, _, result = run(warehouse, extreme_period_example)
    saved = presentation(compiled.plan, result, review.pack, today=TODAY)
    restored = json.loads(json.dumps(saved))
    assert restored == saved
    assert restored["steps"][2]["comparisonPeriods"][0]["currentStart"] == "2026-02-01"


def test_running_progress_claims_no_completed_database_steps(warehouse):
    compiled, review, _, result = run(warehouse, region_example)
    initial = progress_payload(compiled.plan, review.pack)
    assert initial["completed"] == 0 and initial["phase"] == "running"
    assert all(s["status"] == "pending" for s in initial["steps"])
    checked = progress_payload(compiled.plan, review.pack, completed=1, result=result)
    assert checked["message"] == "Reviewed step 1 of 3"
    assert checked["steps"][0]["status"] == "completed"
    assert checked["steps"][1]["status"] == "pending"


@pytest.mark.parametrize("status", ["denied", "cancelled", "failed"])
def test_terminal_failure_has_no_result_cards(warehouse, status):
    compiled, review, _, result = run(warehouse, region_example)
    result.status = status
    result.message = "No results can be published."
    view = presentation(compiled.plan, result, review.pack, today=TODAY)
    assert view["steps"] == [] and view["summary"] == result.message


def test_audit_is_structural_not_a_second_copy_of_customer_data(warehouse):
    compiled, review, _, result = run(warehouse, region_example)
    typed = SimpleNamespace(
        analysis_plan=compiled.plan,
        analysis_review=review,
        context=review.context,
        analysis_date=TODAY,
        analysis_issue_codes=[],
    )
    audit = build_audit(
        run_id="run-1",
        typed=typed,
        result=result,
        status=result.status,
        usage={
            "initialModelCalls": 1,
            "verificationModelCalls": 1,
            "inputTokens": 200,
            "outputTokens": 100,
        },
    )
    serialized = json.dumps(audit)
    assert audit["scopeFingerprint"] == compiled.plan.scope_fingerprint
    assert len(audit["coverage"]) == 3
    assert "South" not in serialized and "Toyota" not in serialized
    assert "SELECT " not in serialized and "WHERE " not in serialized
    assert "prompt" not in serialized and "system" not in serialized
    assert audit["sources"][0]["revisionFingerprint"] != review.completeness_sources[0].revision
    assert audit["usage"]["verificationModelCalls"] == 1


async def test_progress_display_audit_and_snapshot_share_one_run(typed_chat, warehouse):
    from app.api.routes.chat import _save_response
    from tests.unit.test_analytical_execution import Connection

    service, conversation, _, _, catalog = typed_chat
    _, db = warehouse
    service._settings.chat_dependent_analysis_enabled = True
    service._analytics = Connection(db)
    decision = {
        **proposal(),
        "additional_outcomes": ["definition"],
        "definition_terms": ["revenue"],
    }
    provider = AsyncMock(side_effect=[reply(decision), reply(verdict())])
    with (
        patch(
            "app.services.chat.request_runtime.scoped_catalog",
            AsyncMock(return_value=(catalog, TODAY)),
        ),
        patch("app.services.chat.request_interpreter.llm_configured", return_value=True),
        patch("app.services.chat.request_interpreter.complete_text", provider),
    ):
        frames = [
            frame
            async for frame in service.ask_stream(
                "Define revenue and show highest revenue region then models Q1 2026",
                conversation.id,
            )
        ]
    progress = [
        json.loads(f.split("data: ")[1]) for f in frames if f.startswith("event: analysis_progress")
    ]
    assert [p["completed"] for p in progress] == [0, 1, 2, 3]
    await _save_response(service._app, service, service._user, frames)
    history = service.last_history
    audit = history.trust_breakdown["analyticalAudit"]
    meta = next(e["data"] for e in history.response_snapshot["events"] if e["event"] == "meta")
    assert audit == meta["analyticalAudit"]
    assert audit["runId"] == meta["runId"] == str(history.id)
    assert meta["analyticalPresentation"]["version"] == 1
    assert any(
        note.startswith("Approved glossary:") for note in meta["analyticalPresentation"]["notes"]
    )
    assert provider.await_count == 2
    assert not any(e["event"] == "analysis_progress" for e in history.response_snapshot["events"])
    row = await owned_response(service._app, history.id, service._user, service._industry)
    await check_access(
        service._app,
        row,
        service._user,
        service._industry,
        service._region_scope,
        service._settings,
    )
    with pytest.raises(AuthorizationError):
        await check_access(
            service._app,
            row,
            service._user,
            service._industry,
            RegionScope(False, ("West",)),
            service._settings,
        )
    with pytest.raises(NotFoundError):
        await owned_response(
            service._app, history.id, SimpleNamespace(id=uuid.uuid4()), service._industry
        )


async def test_explicit_cancel_retains_audit_without_results_or_second_call(typed_chat):
    from asyncio import Event

    from app.api.routes.chat import _save_response

    service, conversation, connection, _, catalog = typed_chat
    service._settings.chat_dependent_analysis_enabled = True
    stop = Event()

    async def interpretation(**kwargs):
        stop.set()
        return reply(proposal())

    provider = AsyncMock(side_effect=interpretation)
    with (
        patch(
            "app.services.chat.request_runtime.scoped_catalog",
            AsyncMock(return_value=(catalog, TODAY)),
        ),
        patch("app.services.chat.request_interpreter.llm_configured", return_value=True),
        patch("app.services.chat.request_interpreter.complete_text", provider),
    ):
        frames = [
            f
            async for f in service.ask_stream(
                "Highest revenue region then models Q1 2026", conversation.id, cancel_event=stop
            )
        ]
    await _save_response(service._app, service, service._user, frames)
    audit = service.last_history.trust_breakdown["analyticalAudit"]
    assert audit["status"] == "cancelled" and audit["published"] is False
    assert audit["results"] == []
    assert provider.await_count == 1
    assert not any("WITH " in str(call) for call in connection.execute.await_args_list)


async def test_relative_period_anchor_is_shared_by_execution_and_display(typed_chat, warehouse):
    from app.services.chat.analytical_plan_execution import execute_analysis
    from tests.unit.test_analytical_execution import Connection

    service, conversation, _, _, catalog = typed_chat
    _, db = warehouse
    service._settings.chat_dependent_analysis_enabled = True
    service._analytics = Connection(db)
    runner = AsyncMock(wraps=execute_analysis)
    decision = {**proposal(), "period": {"label": "Last month", "relative": "last_month"}}
    provider = AsyncMock(side_effect=[reply(decision), reply(verdict())])
    with (
        patch("app.services.chat.request_runtime.business_today", return_value=TODAY),
        patch("app.services.chat.request_dates.business_today", return_value=date(2026, 12, 1)),
        patch(
            "app.services.chat.request_runtime.scoped_catalog",
            AsyncMock(return_value=(catalog, TODAY)),
        ),
        patch("app.services.chat.request_interpreter.llm_configured", return_value=True),
        patch("app.services.chat.request_interpreter.complete_text", provider),
        patch("app.services.chat.analytical_plan_execution.execute_analysis", runner),
    ):
        frames = [
            f
            async for f in service.ask_stream(
                "Highest revenue region then models last month", conversation.id
            )
        ]
    assert runner.await_args.kwargs["today"] == TODAY
    meta = next(json.loads(f.split("data: ")[1]) for f in frames if f.startswith("event: meta"))
    assert meta["analyticalAudit"]["analysisDate"] == TODAY.isoformat()
    assert meta["analyticalPresentation"]["steps"][0]["searchPeriod"]["start"] == "2026-10-01"
    assert (
        meta["analyticalPresentation"]["steps"][0]["searchPeriod"]["endExclusive"] == "2026-11-01"
    )
