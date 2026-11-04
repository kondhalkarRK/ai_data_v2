"""Semantic, scope, failure and persistence checks without an external warehouse."""

import uuid
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.config import Industry, Settings
from app.core.exceptions import AuthorizationError, ConflictError, NotFoundError, ValidationError
from app.models import Base
from app.models.enums import Role
from app.models.user import User
from app.schemas.analytics_workspace import (
    WorkspaceNarrationRequest,
    WorkspaceRequest,
    WorkspaceSaveRequest,
)
from app.semantic.service import SemanticService
from app.services.analytics import workspace as service
from app.services.analytics.catalog import Catalog
from app.services.analytics.compiler import compile_builder_query
from app.services.security.region_scope import RegionScope

NOW = datetime(2026, 11, 5, tzinfo=ZoneInfo("Asia/Kolkata"))


@pytest.mark.parametrize(
    "question,kind,dimension,start,end",
    [
        ("What were total sales yesterday?", "single_value", [], "2026-11-04", "2026-11-04"),
        ("Show daily sales for last week", "analysis", ["month"], "2026-10-26", "2026-11-01"),
        ("Sales by model last month", "analysis", ["model"], "2026-10-01", "2026-10-31"),
        ("Total revenue this week", "single_value", [], "2026-11-02", "2026-11-05"),
        ("Total sales last quarter", "single_value", [], "2026-07-01", "2026-09-30"),
    ],
)
async def test_common_questions_compile(question, kind, dimension, start, end):
    plan = service.local_plan(WorkspaceRequest(prompt=question), NOW)
    assert plan.answer_kind == kind
    panel = plan.panels[0]
    assert panel.spec.dimensions == dimension
    assert (panel.spec.date_from, panel.spec.date_to) == (start, end)
    settings = Settings()
    catalog = Catalog(
        Industry.AUTOMOTIVE, await SemanticService(settings).get_pack(Industry.AUTOMOTIVE)
    )
    service.validate_plan(plan, catalog, RegionScope.all_regions())
    query = compile_builder_query(panel.spec, catalog, daily=panel.daily)
    assert "SELECT" in query.sql
    if panel.daily:
        assert "sales_day" in query.sql


def test_unknown_filters_and_metrics_are_not_dropped():
    for question in [
        "sales for unicorn last week",
        "daily discount last week",
        "sales north last week",
        "report for second week",
    ]:
        assert service.local_plan(WorkspaceRequest(prompt=question), NOW) is None
    assert (
        service.local_plan(WorkspaceRequest(prompt="Show performance"), NOW).answer_kind
        == "clarification"
    )


def test_visual_edit_preserves_query_and_context():
    plan = service.local_plan(WorkspaceRequest(prompt="Sales by model last month"), NOW)
    edited = service.local_plan(
        WorkspaceRequest(
            prompt="Change this chart to a line chart", previous=plan, selected_panel_id="primary"
        ),
        NOW,
    )
    assert edited.panels[0].spec.viz == "line"
    assert edited.panels[0].spec.model_dump(exclude={"viz"}) == plan.panels[0].spec.model_dump(
        exclude={"viz"}
    )


async def test_flags_and_industry(monkeypatch):
    base = SimpleNamespace(
        _settings=Settings(ask_me_analytics_workspace_enabled=False), _industry=Industry.AUTOMOTIVE
    )
    with pytest.raises(NotFoundError):
        await service.context(base)
    base._settings.ask_me_analytics_workspace_enabled = True
    base._industry = Industry.INSURANCE
    with pytest.raises(AuthorizationError):
        await service.context(base)


async def test_no_llm_for_common_question_and_provider_failure(monkeypatch):
    settings = Settings(ask_me_analytics_workspace_enabled=True)
    catalog = Catalog(
        Industry.AUTOMOTIVE, await SemanticService(settings).get_pack(Industry.AUTOMOTIVE)
    )
    scope = RegionScope.all_regions()
    monkeypatch.setattr(service, "context", AsyncMock(return_value=(catalog, scope)))
    completion = AsyncMock(side_effect=RuntimeError("provider timeout"))
    monkeypatch.setattr(service.AskWizService, "completion", completion)
    base = SimpleNamespace(_settings=settings, _user=SimpleNamespace(id=uuid.uuid4()))
    answer = await service.plan_workspace(base, WorkspaceRequest(prompt="Total sales yesterday"))
    assert answer.llm_calls == 0
    completion.assert_not_called()
    answer = await service.plan_workspace(
        base, WorkspaceRequest(prompt="Create an executive sales dashboard")
    )
    assert answer.plan.answer_kind == "clarification"
    assert completion.await_count == 1


async def test_signed_evidence_rejects_forgery_and_other_user(monkeypatch):
    settings = Settings(ask_me_analytics_workspace_enabled=True)
    scope = RegionScope.all_regions()
    base = SimpleNamespace(_settings=settings, _user=SimpleNamespace(id=uuid.uuid4()))
    monkeypatch.setattr(service, "context", AsyncMock(return_value=(None, scope)))
    token = service.sign_evidence(base, scope, "Revenue is 120.")
    base._user.id = uuid.uuid4()
    with pytest.raises(ValidationError):
        await service.narrate_workspace(base, WorkspaceNarrationRequest(evidence=[token]))
    with pytest.raises(ValidationError):
        await service.narrate_workspace(base, WorkspaceNarrationRequest(evidence=[token + "x"]))


async def test_owner_persistence_and_optimistic_revision(monkeypatch):
    settings = Settings(ask_me_analytics_workspace_enabled=True)
    catalog = Catalog(
        Industry.AUTOMOTIVE, await SemanticService(settings).get_pack(Industry.AUTOMOTIVE)
    )
    scope = RegionScope.all_regions()
    monkeypatch.setattr(service, "context", AsyncMock(return_value=(catalog, scope)))
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    async with async_sessionmaker(engine, expire_on_commit=False)() as session:
        user = User(
            id=uuid.uuid4(),
            username="workspace-test",
            email="workspace@example.com",
            email_normalized="workspace@example.com",
            full_name="Test",
            password_hash="unused",
            role=Role.ADMIN,
            default_industry=Industry.AUTOMOTIVE,
            is_active=True,
        )
        session.add(user)
        await session.flush()
        base = SimpleNamespace(_settings=settings, _user=user, _app=session)
        plan = service.local_plan(WorkspaceRequest(prompt="Total sales yesterday"), NOW)
        saved = await service.save_workspace(base, WorkspaceSaveRequest(plan=plan))
        reopened = await service.get_workspace(base, saved.id)
        assert reopened.plan == plan
        changed = await service.save_workspace(
            base, WorkspaceSaveRequest(id=saved.id, revision=1, plan=plan)
        )
        assert changed.revision == 2
        with pytest.raises(ConflictError):
            await service.save_workspace(
                base, WorkspaceSaveRequest(id=saved.id, revision=1, plan=plan)
            )
        base._user = SimpleNamespace(id=uuid.uuid4())
        with pytest.raises(NotFoundError):
            await service.get_workspace(base, saved.id)
    await engine.dispose()


async def test_bounded_llm_plan_repair_and_explicit_count(monkeypatch):
    settings = Settings(ask_me_analytics_workspace_enabled=True)
    catalog = Catalog(
        Industry.AUTOMOTIVE, await SemanticService(settings).get_pack(Industry.AUTOMOTIVE)
    )
    monkeypatch.setattr(
        service, "context", AsyncMock(return_value=(catalog, RegionScope.all_regions()))
    )
    plan = service.local_plan(WorkspaceRequest(prompt="Sales by model last month"), NOW)
    completion = AsyncMock(side_effect=["not JSON", plan.model_dump_json()])
    monkeypatch.setattr(service.AskWizService, "completion", completion)
    base = SimpleNamespace(_settings=settings, _user=SimpleNamespace(id=uuid.uuid4()))
    answer = await service.plan_workspace(
        base, WorkspaceRequest(prompt="Please analyze models for the previous calendar month")
    )
    assert answer.plan.panels[0].spec.metrics == ["revenue"]
    assert completion.await_count == 2
    completion.reset_mock()
    completion.side_effect = [plan.model_dump_json(), plan.model_dump_json()]
    answer = await service.plan_workspace(
        base, WorkspaceRequest(prompt="Create four charts for sales")
    )
    assert answer.plan.answer_kind == "clarification"
    assert completion.await_count == 2


async def test_scope_forgery_and_invalid_dates_rejected():
    settings = Settings()
    catalog = Catalog(
        Industry.AUTOMOTIVE, await SemanticService(settings).get_pack(Industry.AUTOMOTIVE)
    )
    plan = service.local_plan(WorkspaceRequest(prompt="Total sales yesterday"), NOW)
    plan.panels[0].spec.date_from = "invalid"
    with pytest.raises(ValidationError):
        service.validate_plan(plan, catalog, RegionScope.all_regions())
    plan.panels[0].spec.date_from = "2026-11-04"
    from app.schemas.analytics import AnalyticsFilterSpec

    plan.panels[0].spec.filters = [AnalyticsFilterSpec(domain="region", values=["North"])]
    with pytest.raises(AuthorizationError):
        service.validate_plan(plan, catalog, RegionScope(unrestricted=False, zones=("West",)))


async def test_unknown_value_clarifies_instead_of_silent_filter_drop():
    plan = service.local_plan(WorkspaceRequest(prompt="Sales by model last month"), NOW)
    from app.schemas.analytics import AnalyticsFilterSpec, FilterValuesResponse

    plan.panels[0].spec.filters = [AnalyticsFilterSpec(domain="model", values=["Not a real model"])]
    base = SimpleNamespace(
        filter_values=AsyncMock(
            return_value=FilterValuesResponse(domain="model", label="Model", values=[])
        )
    )
    with pytest.raises(ValidationError):
        await service.validate_values(base, plan)
