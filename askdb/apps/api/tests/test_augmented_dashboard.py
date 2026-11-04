"""Numerical, access-boundary and ASGI tests; no live warehouse or model calls."""

from __future__ import annotations

import time
import uuid
from datetime import date
from typing import cast
from unittest.mock import AsyncMock

import pytest
from httpx import ASGITransport, AsyncClient
from pydantic import ValidationError as PydanticError
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncSession

from app.api.deps import get_app_session, get_current_user, get_region_scope, get_scoped_analytics
from app.core.config import Industry, Settings
from app.core.exceptions import AuthorizationError, ValidationError
from app.main import create_app
from app.models.activity import Conversation, LlmUsage, QueryHistory
from app.models.enums import Role
from app.models.user import User
from app.schemas.dashboard import DashboardContributor, DashboardExplainRequest, DashboardMetric
from app.schemas.executive import BusinessHealth, DataQualityNotice, ExecutiveIntelligenceResponse
from app.schemas.executive_cockpit import CockpitPeriod, CockpitResponse
from app.schemas.kpi import KpiCard
from app.services.executive.cockpit import Agg, ExecutiveCockpitService, Grouped
from app.services.executive.dashboard import (
    SNAPSHOTS,
    DashboardRefreshRequiredError,
    QueryMeter,
    SnapshotStore,
    automotive_source,
    explain_dashboard,
    movement,
    question_intent,
    ratio_contributors,
    register_dashboard,
    residual_rows,
    resolve_snapshot,
    semantic_revision,
)
from app.services.llm import LlmResult
from app.services.security.region_scope import RegionScope


def person() -> User:
    return User(
        id=uuid.uuid4(),
        username="dashboard-test",
        email="dashboard@example.com",
        email_normalized="dashboard@example.com",
        full_name="Dashboard Test",
        password_hash="unused",
        role=Role.USER,
        default_industry=Industry.AUTOMOTIVE,
        is_active=True,
        weekly_call_limit=50,
        weekly_token_limit=60000,
    )


def automotive_result() -> CockpitResponse:
    grouped = Grouped(
        cur={
            "total": {(): Agg(120, 12, 10)},
            "zone": {("West",): Agg(120, 12, 10)},
            "make": {("Tata",): Agg(120, 12, 10)},
            "model": {("Tata", "Nexon"): Agg(120, 12, 10)},
        },
        pri={
            "total": {(): Agg(100, 10, 8)},
            "zone": {("West",): Agg(80, 8, 6), ("North",): Agg(20, 2, 2)},
            "make": {("Tata",): Agg(100, 10, 8)},
            "model": {("Tata", "Nexon"): Agg(100, 10, 8)},
        },
    )
    response = CockpitResponse.model_construct(
        period=CockpitPeriod(
            label="2026 YTD",
            start="2026-01-01",
            end="2026-09-15",
            prior_label="2025 YTD",
            prior_start="2025-01-01",
            prior_end="2025-09-15",
            data_as_of="2026-09-15",
        ),
        computed_at="2026-09-16T12:00:00Z",
    )
    response._dashboard_source = automotive_source(
        response,
        grouped,
        "SELECT SUM(f.total_sales) FROM automotive.fact_sales f "
        "WHERE f.sales_date BETWEEN :cs AND :ce",
        {"cs": date(2026, 1, 1), "ce": date(2026, 9, 15)},
    )
    return response


def insurance_result() -> ExecutiveIntelligenceResponse:
    def card(key: str, value: float) -> KpiCard:
        return KpiCard(
            id=key,
            label=key.replace("_", " "),
            value=value,
            formatted=str(value),
            format="percent"
            if key == "loss_ratio"
            else "integer"
            if key == "claim_count"
            else "currency",
            formula=key,
        )

    current = [
        card("written_premium", 120),
        card("earned_premium", 100),
        card("claims_incurred", 80),
        card("claim_count", 10),
        card("loss_ratio", 0.8),
    ]
    prior = [
        card("written_premium", 100),
        card("earned_premium", 80),
        card("claims_incurred", 72),
        card("claim_count", 8),
        card("loss_ratio", 0.9),
    ]
    response = ExecutiveIntelligenceResponse.model_construct(
        industry="insurance",
        window="ytd",
        window_label="YTD 2026",
        compare_label="Prior YTD 2025",
        start_date="2026-01-01",
        end_date="2026-09-15",
        data_as_of="2026-09-01",
        computed_at="2026-09-16T12:00:00Z",
        cards=current,
        data_quality=DataQualityNotice(
            label="Check freshness", notices=["Policy data is monthly."]
        ),
        health=BusinessHealth(label="Good", formula_note="test"),
    )
    response._dashboard_source = {
        "cards": current,
        "prior_cards": prior,
        "prior_start": "2025-01-01",
        "prior_end": "2025-09-15",
    }
    return response


def register(
    settings: Settings, user: User, scope: RegionScope, industry: Industry = Industry.AUTOMOTIVE
):
    response = automotive_result() if industry is Industry.AUTOMOTIVE else insurance_result()
    return register_dashboard(
        response,
        settings=settings,
        user=user,
        scope=scope,
        industry=industry,
        meter=QueryMeter(cast(AsyncConnection, AsyncMock())),
        started=time.perf_counter(),
        filters={"zone": "West"} if industry is Industry.AUTOMOTIVE else {"window": "ytd"},
        revision=semantic_revision(settings, industry),
    )


def snapshot(
    settings: Settings, user: User, scope: RegionScope, industry: Industry = Industry.AUTOMOTIVE
):
    augmentation = register(settings, user, scope, industry)
    return resolve_snapshot(
        augmentation.snapshot_token, settings=settings, user=user, scope=scope, industry=industry
    )


def test_snapshot_binding_and_expiration(
    settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    user, scope = person(), RegionScope.all_regions()
    aug = register(settings, user, scope)
    args = {"settings": settings, "user": user, "scope": scope, "industry": Industry.AUTOMOTIVE}
    item = resolve_snapshot(aug.snapshot_token, **args)
    with pytest.raises(AuthorizationError):
        resolve_snapshot(aug.snapshot_token, **(args | {"user": person()}))
    with pytest.raises(AuthorizationError):
        resolve_snapshot(aug.snapshot_token, **(args | {"scope": RegionScope(False, ("West",))}))
    with pytest.raises(AuthorizationError):
        resolve_snapshot(aug.snapshot_token, **(args | {"industry": Industry.INSURANCE}))
    with pytest.raises(DashboardRefreshRequiredError):
        resolve_snapshot(aug.snapshot_token + "tampered", **args)
    monkeypatch.setattr(
        "app.services.executive.dashboard.semantic_revision", lambda *_: "new-revision"
    )
    with pytest.raises(DashboardRefreshRequiredError):
        resolve_snapshot(aug.snapshot_token, **args)
    monkeypatch.undo()
    item.expires = 0
    with pytest.raises(DashboardRefreshRequiredError):
        resolve_snapshot(aug.snapshot_token, **args)


def test_disabled_feature_and_forged_values(settings: Settings) -> None:
    user, scope = person(), RegionScope.all_regions()
    aug = register(settings, user, scope)
    with pytest.raises(AuthorizationError):
        resolve_snapshot(
            aug.snapshot_token,
            settings=settings.model_copy(update={"ask_me_augmented_dashboard_enabled": False}),
            user=user,
            scope=scope,
            industry=Industry.AUTOMOTIVE,
        )
    with pytest.raises(PydanticError):
        DashboardExplainRequest.model_validate(
            {
                "snapshotToken": aug.snapshot_token,
                "metricId": "revenue",
                "current": 999999,
                "filters": {"zone": "North"},
            }
        )


def test_store_is_bounded_and_removes_expired(settings: Settings) -> None:
    store = SnapshotStore(max_entries=2)
    item = snapshot(settings, person(), RegionScope.all_regions())
    first = store.put(item)
    store.put(item)
    store.put(item)
    assert len(store.entries) == 2 and first not in store.entries


@pytest.mark.parametrize(("before", "after"), [(0, 0), (0, 10), (-100, -50), (100, 0)])
def test_zero_negative_missing_and_percent_changes(before: float, after: float) -> None:
    metric = DashboardMetric(
        id="x", label="Revenue", format="currency", current=after, prior=before, definition="test"
    )
    assert "nan" not in movement(metric).lower()
    if before == 0 and after:
        assert "percentage change is undefined" in movement(metric)
    metric.current = None
    assert "unavailable" in movement(metric)
    metric.current, metric.prior, metric.format = 0.8, 0.9, "percent"
    assert "10.00 percentage points" in movement(metric)


@pytest.mark.parametrize(
    ("c1", "c0", "e1", "e0"), [(80, 72, 100, 80), (0, 0, 100, 80), (-20, -30, 50, 60)]
)
def test_loss_ratio_effects_reconcile(c1: float, c0: float, e1: float, e0: float) -> None:
    rows = ratio_contributors(
        {"current_claims": c1, "prior_claims": c0, "current_premium": e1, "prior_premium": e0}
    )
    assert sum(r.change for r in rows) == pytest.approx(c1 / e1 - c0 / e0)
    assert (
        ratio_contributors(
            {"current_claims": c1, "prior_claims": c0, "current_premium": 0, "prior_premium": e0}
        )
        == []
    )


def test_top_contributors_include_residual_and_exits() -> None:
    rows = [DashboardContributor(label=str(i), current=i * 2, prior=i, change=i) for i in range(12)]
    ranked = residual_rows(rows, sum(r.current for r in rows), sum(r.prior for r in rows))
    assert ranked[-1].residual
    assert sum(r.change for r in ranked) == pytest.approx(sum(r.change for r in rows))


async def test_automotive_explanation_reuses_scan_and_includes_prior_only_group(
    settings: Settings,
) -> None:
    item = snapshot(settings, person(), RegionScope.all_regions())
    connection = AsyncMock()
    result = await explain_dashboard(
        item, "revenue", "zone", connection, settings, RegionScope.all_regions()
    )
    assert result.reconciled and result.query_count == 0
    assert next(r for r in result.contributors if r.label == "North").change == -20
    assert sum(r.change for r in result.contributors) == pytest.approx(20)
    connection.execute.assert_not_awaited()
    with pytest.raises(ValidationError):
        await explain_dashboard(
            item, "revenue", "untrusted_column", connection, settings, RegionScope.all_regions()
        )
    with pytest.raises(ValidationError):
        await explain_dashboard(
            item, "unknown", None, connection, settings, RegionScope.all_regions()
        )


async def test_ratio_explanation_uses_existing_totals(settings: Settings) -> None:
    item = snapshot(settings, person(), RegionScope.all_regions(), Industry.INSURANCE)
    connection = AsyncMock()
    result = await explain_dashboard(
        item, "loss_ratio", None, connection, settings, RegionScope.all_regions()
    )
    assert result.reconciled and "percentage points" in result.narrative
    assert result.prior_sql_parameters["start_date"] == "2025-01-01"
    connection.execute.assert_not_awaited()


@pytest.mark.parametrize("newer", [False, True])
async def test_insurance_driver_query_scope_and_changed_data(
    settings: Settings, newer: bool
) -> None:
    scope = RegionScope(False, ("West",))
    item = snapshot(settings, person(), scope, Industry.INSURANCE)
    connection = AsyncMock()
    rows = [
        {
            "label": "West",
            "current": 125 if newer else 120,
            "prior": 100,
            "total_current": 125 if newer else 120,
            "total_prior": 100,
        }
    ]
    result_proxy = type("Rows", (), {"mappings": lambda self: self, "all": lambda self: rows})()
    connection.execute.return_value = result_proxy
    result = await explain_dashboard(item, "written_premium", "region", connection, settings, scope)
    assert result.reconciled and result.evidence_changed is newer
    assert connection.execute.await_count == 2
    assert "/*rls*/" in (result.sql or "")
    assert result.sql_parameters["cs"] == item.context.start
    if newer:
        assert "newer totals" in " ".join(result.caveats)


def test_contextual_intent_does_not_change_scope(settings: Settings) -> None:
    item = snapshot(settings, person(), RegionScope.all_regions())
    assert question_intent("Which models contributed most?", item, "units", "zone") == (
        "units",
        "model",
        "explain",
    )
    assert question_intent("What is revenue?", item, "units", "zone") == (
        "revenue",
        "zone",
        "definition",
    )
    assert (
        question_intent("Compare North and South last year", item, "revenue", "zone")[2] == "scope"
    )
    assert question_intent("Break down by product", item, "revenue", "zone")[2] == "unsupported"


async def test_dimension_cache_is_separate_per_access_scope(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import app.services.executive.cockpit as module

    monkeypatch.setattr(module, "_DIM_CACHE", {})
    for zone in ("West", "North"):
        service = ExecutiveCockpitService(cast(AsyncConnection, AsyncMock()))
        service._scope_key = zone
        query = AsyncMock(
            side_effect=[
                [
                    {
                        "carline_id": 1,
                        "make": "Tata",
                        "model": "Nexon",
                        "engine_type": "Petrol",
                        "car_type": "SUV",
                    }
                ],
                [{"region_id": 1, "zone": zone, "state": "MH", "city": zone}],
            ]
        )
        monkeypatch.setattr(service, "_rows", query)
        dimensions = await service._dimensions()
        assert dimensions.regions[1]["zone"] == zone
        assert query.await_count == 2
    assert len(module._DIM_CACHE) == 2


async def test_dashboard_api_conversation_audit_scope_and_quota(
    settings: Settings, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    user, scope = person(), RegionScope.all_regions()
    db_session.add(user)
    await db_session.flush()
    aug = register(settings, user, scope)
    app = create_app(settings)
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_region_scope] = lambda: scope
    app.dependency_overrides[get_scoped_analytics] = lambda: AsyncMock()
    app.dependency_overrides[get_app_session] = lambda: db_session
    monkeypatch.setattr("app.api.routes.dashboard.llm_configured", lambda _: False)
    async with AsyncClient(transport=ASGITransport(app), base_url="http://testserver") as client:
        headers = {"authorization": "Bearer test", "x-industry": "automotive"}
        payload = {"snapshotToken": aug.snapshot_token, "metricId": "revenue", "dimension": "zone"}
        result = await client.post("/api/v1/executive/explain", json=payload, headers=headers)
        assert result.status_code == 200 and result.json()["reconciled"]
        forged = await client.post(
            "/api/v1/executive/explain", json=payload | {"current": 999}, headers=headers
        )
        assert forged.status_code == 422
        asked = await client.post(
            "/api/v1/executive/ask",
            json=payload | {"question": "Which models contributed most?"},
            headers=headers,
        )
        assert asked.status_code == 200, asked.text
        cid = asked.json()["conversationId"]
        assert cid and asked.json()["dimension"] == "model"
        assert await db_session.scalar(select(func.count()).select_from(LlmUsage)) == 1
        assert await db_session.scalar(select(func.count()).select_from(QueryHistory)) == 1
        conversation = await db_session.get(Conversation, uuid.UUID(cid))
        assert (
            conversation and conversation.session_memory["dashboard"]["scope"] == scope.cache_key()
        )
        # An expired result never falls back to executing a client question without context.
        SNAPSHOTS.entries.clear()
        stale = await client.post(
            "/api/v1/executive/ask", json=payload | {"question": "Explain revenue"}, headers=headers
        )
        assert stale.status_code == 409
        fresh = register(settings, user, scope)
        payload["snapshotToken"] = fresh.snapshot_token
        user.weekly_call_limit = 0
        quota = await client.post(
            "/api/v1/executive/ask", json=payload | {"question": "Explain revenue"}, headers=headers
        )
        assert quota.status_code == 429
        assert (
            await client.post("/api/v1/executive/explain", json=payload, headers=headers)
        ).status_code == 200
        # CSRF remains enforced for cookie-authenticated mutations.
        assert (await client.post("/api/v1/executive/explain", json=payload)).status_code == 403


@pytest.mark.parametrize("content", ["not-json", '{"metricId":"forged","operation":"explain"}', ""])
async def test_bounded_classifier_failure_keeps_evidence_available(
    content: str, settings: Settings, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    user, scope = person(), RegionScope.all_regions()
    db_session.add(user)
    await db_session.flush()
    aug = register(settings, user, scope)
    app = create_app(settings)
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_region_scope] = lambda: scope
    analytics = AsyncMock()
    app.dependency_overrides[get_scoped_analytics] = lambda: analytics
    app.dependency_overrides[get_app_session] = lambda: db_session
    monkeypatch.setattr("app.api.routes.dashboard.sync_llm_config", AsyncMock())
    monkeypatch.setattr("app.api.routes.dashboard.llm_configured", lambda _: True)
    complete = AsyncMock(
        return_value=LlmResult(
            sql=None,
            narrative="",
            model="fixture",
            content=content,
            error="timeout" if not content else None,
            timed_out=not bool(content),
        )
    )
    monkeypatch.setattr("app.api.routes.dashboard.complete_text", complete)
    async with AsyncClient(transport=ASGITransport(app), base_url="http://testserver") as client:
        payload = {"snapshotToken": aug.snapshot_token, "metricId": "revenue", "dimension": "zone"}
        headers = {"authorization": "Bearer test", "x-industry": "automotive"}
        result = await client.post(
            "/api/v1/executive/ask", json=payload | {"question": "Illuminate this"}, headers=headers
        )
        assert result.status_code == 200, result.text
        assert "Try one of the suggestions" in result.json()["narrative"]
        complete.assert_awaited_once()
        analytics.execute.assert_not_awaited()
        evidence = await client.post("/api/v1/executive/explain", json=payload, headers=headers)
        assert evidence.status_code == 200 and evidence.json()["reconciled"]
