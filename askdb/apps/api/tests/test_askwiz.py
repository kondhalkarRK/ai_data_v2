"""Automotive Auto authoring contracts and persistence; SQLite/mocked warehouse/model."""

from __future__ import annotations

import uuid
from datetime import date
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Industry, Settings
from app.core.exceptions import AuthorizationError, ConflictError, ValidationError
from app.models.enums import Role
from app.models.user import User
from app.schemas.analytics import AnalyticsInsights, AnalyticsRunResponse, AnalyticsSpec
from app.schemas.askwiz import Intent
from app.semantic.service import SemanticService
from app.services.analytics.askwiz import (
    CACHE,
    NARRATIONS,
    AskWizService,
    deterministic_intent,
    resolve_period,
    validate_definition,
)
from app.services.analytics.catalog import Catalog
from app.services.analytics.compiler import compile_builder_query
from app.services.analytics.runner import AnalyticsService
from app.services.llm import LlmResult
from app.services.security.region_scope import RegionScope


@pytest.fixture
async def api(
    settings: Settings, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> AskWizService:
    user = User(
        id=uuid.uuid4(),
        username=str(uuid.uuid4()),
        email="auto@example.com",
        email_normalized="auto@example.com",
        full_name="Auto",
        password_hash="unused",
        role=Role.ADMIN,
        default_industry=Industry.AUTOMOTIVE,
        is_active=True,
    )
    db_session.add(user)
    await db_session.flush()
    connection = MagicMock()
    connection.execute = AsyncMock()
    connection.begin_nested.return_value.__aenter__ = AsyncMock()
    connection.begin_nested.return_value.__aexit__ = AsyncMock(return_value=False)
    base = AnalyticsService(
        app_session=db_session,
        analytics=connection,
        settings=settings,
        user=user,
        industry=Industry.AUTOMOTIVE,
        semantic_service=SemanticService(settings),
    )
    monkeypatch.setattr(
        "app.services.analytics.askwiz.load_region_scope",
        AsyncMock(return_value=RegionScope.all_regions()),
    )
    monkeypatch.setattr("app.services.analytics.askwiz.sync_llm_config", AsyncMock())
    monkeypatch.setattr("app.services.analytics.askwiz.llm_configured", lambda _: False)
    base._prepare = AsyncMock()
    CACHE.clear()
    NARRATIONS.clear()
    return AskWizService(base)


@pytest.mark.parametrize(
    "today,period,expected",
    [
        (date(2026, 11, 4), "last_week", ("2026-10-26", "2026-11-01", "2026-10-19", "2026-10-25")),
        (date(2026, 11, 4), "this_week", ("2026-11-02", "2026-11-04", "2026-10-26", "2026-10-28")),
        (date(2024, 2, 29), "this_year", ("2024-01-01", "2024-02-29", "2023-01-01", "2023-02-28")),
        (date(2026, 1, 1), "last_month", ("2025-12-01", "2025-12-31", "2025-11-01", "2025-11-30")),
    ],
)
def test_calendar_dates(today: date, period: str, expected: tuple[str, ...]) -> None:
    assert tuple(map(str, resolve_period(period, today))) == expected


def test_ambiguous_week_and_oversized_requests() -> None:
    assert deterministic_intent("Report for second week").operation == "clarify"
    assert deterministic_intent("Generate 9 charts on sales").operation == "clarify"
    assert deterministic_intent("Generate report last week on daily sales").period == "last_week"


async def test_daily_compiler_is_auto_only(api: AskWizService) -> None:
    catalog, _ = await api.context()
    spec = AnalyticsSpec(
        metrics=["revenue"],
        dimensions=["month"],
        analysis="trend",
        date_preset="custom",
        date_from="2026-10-26",
        date_to="2026-11-01",
    )
    daily = compile_builder_query(spec, catalog, daily=True)
    normal = compile_builder_query(spec, catalog)
    assert "sales_day" in daily.sql and "sales_date::date" in daily.sql
    assert "'2026-10-26'" in daily.sql and "'2026-11-01'" in daily.sql
    assert normal.time_grain == "month" and daily.time_grain == "day"
    assert all(d.id != "day" for d in catalog.dimensions)
    insurance = Catalog(
        Industry.INSURANCE, SemanticService(api.base._settings)._load_pack(Industry.INSURANCE)
    )
    from app.services.analytics.compiler import BuilderCompileError

    with pytest.raises(BuilderCompileError):
        compile_builder_query(
            AnalyticsSpec(metrics=["gross_written_premium"], dimensions=["month"]),
            insurance,
            daily=True,
        )


async def test_automotive_flag_and_domain_guard(api: AskWizService) -> None:
    api.base._industry = Industry.INSURANCE
    with pytest.raises(AuthorizationError):
        await api.create("sales", "sales")
    api.base._industry = Industry.AUTOMOTIVE
    old = api.base._settings.ask_me_askwiz_enabled
    api.base._settings.ask_me_askwiz_enabled = False
    try:
        from app.core.exceptions import NotFoundError

        with pytest.raises(NotFoundError):
            await api.list_saved()
    finally:
        api.base._settings.ask_me_askwiz_enabled = old


async def test_recipe_edit_undo_save_and_revision(api: AskWizService) -> None:
    board = await api.create("", "weekly")
    assert len(board.definition.charts) == 4 and board.llm_calls == 0
    assert not await api.list_saved()
    ids = [c.id for c in board.definition.charts]
    edited = await api.command(board.id, 1, "Make chart two a bar chart", None, "edit")
    assert edited.revision == 2 and edited.definition.charts[1].viz == "bar"
    assert [c.id for c in edited.definition.charts] == ids
    assert edited.llm_calls == 0
    with pytest.raises(ConflictError):
        await api.command(board.id, 1, "remove chart two", None, "edit")
    restored = await api.command(board.id, 2, "", None, "undo")
    assert restored.definition.charts[1].viz == "line" and restored.revision == 3
    await api.command(board.id, 3, "", None, "save")
    assert len(await api.list_saved()) == 1
    with pytest.raises(ValidationError, match="Select a chart"):
        await api.command(board.id, 3, "Change it to area", None, "edit")


async def test_cross_user_and_scope_change(
    api: AskWizService, monkeypatch: pytest.MonkeyPatch
) -> None:
    board = await api.create("", "sales")
    from app.core.exceptions import NotFoundError

    original = api.base._user.id
    api.base._user.id = uuid.uuid4()
    with pytest.raises(NotFoundError):
        await api.get(board.id)
    api.base._user.id = original
    # Different canonical permission scope cannot reopen an earlier board.
    scope = MagicMock(spec=RegionScope)
    scope.cache_key.return_value = "revoked"
    monkeypatch.setattr(
        "app.services.analytics.askwiz.load_region_scope", AsyncMock(return_value=scope)
    )
    with pytest.raises(AuthorizationError, match="access changed"):
        await api.get(board.id)


async def test_freeform_uses_bounded_llm(
    api: AskWizService, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("app.services.analytics.askwiz.llm_configured", lambda _: True)
    complete = AsyncMock(
        return_value=LlmResult(
            sql=None,
            narrative="",
            model="mock",
            content=Intent(recipe="weekly", period="last_week").model_dump_json(),
            prompt_tokens=20,
            completion_tokens=10,
        )
    )
    monkeypatch.setattr("app.services.analytics.askwiz.complete_text", complete)
    board = await api.create("Generate report of last week on daily sales")
    assert board.llm_calls == 1 and board.tokens == 30 and len(board.definition.charts) == 4
    assert complete.await_count == 1
    assert all(c.metric in {"revenue", "units_sold"} for c in board.definition.charts)
    repeated = await AskWizService(api.base).create("Generate report of last week on daily sales")
    assert repeated.llm_calls == 0 and complete.await_count == 1


@pytest.mark.parametrize(
    "content", ["bad json", '{"operation":"create","sql":"DROP TABLE x"}', '{"metric":"profit"}']
)
async def test_invalid_llm_never_executes(
    api: AskWizService, monkeypatch: pytest.MonkeyPatch, content: str
) -> None:
    monkeypatch.setattr("app.services.analytics.askwiz.llm_configured", lambda _: True)
    monkeypatch.setattr(
        "app.services.analytics.askwiz.complete_text",
        AsyncMock(return_value=LlmResult(sql=None, narrative="", model="mock", content=content)),
    )
    with pytest.raises(ValidationError):
        await api.create("Show profit only for West")
    api.base._analytics.execute.assert_not_awaited()


async def test_query_dedup_cache_and_selective_edit(api: AskWizService) -> None:
    board = await api.create("", "sales")

    async def run(spec: AnalyticsSpec, **kwargs) -> AnalyticsRunResponse:
        assert kwargs == {
            "daily": bool(spec.dimensions == ["month"]),
            "include_drivers": False,
            "prepare": False,
        }
        return AnalyticsRunResponse(
            title="Fixture",
            columns=["revenue"],
            rows=[{"revenue": 20}],
            sql="SELECT 20",
            recommended_viz="bar",
            insights=AnalyticsInsights(executive="Revenue is ₹20.", analyst="Fixture evidence"),
        )

    api.base.run = AsyncMock(side_effect=run)
    first = await api.run(board.id, 1)
    assert api.base.run.await_count == 6 and len(first.charts) == 4 and len(first.kpis) == 2
    api.base.run.reset_mock()
    api.base._prepare.reset_mock()
    cached = await api.run(board.id, 1)
    assert cached.cache_hits == 6 and cached.query_count == 0
    api.base.run.assert_not_awaited()
    api.base._prepare.assert_not_awaited()
    edited = await api.command(board.id, 1, "Make chart two a bar chart", None, "edit")
    await api.run(board.id, edited.revision)
    api.base.run.assert_not_awaited()
    # Data-changing edit of a single chart invalidates only that specification.
    changed = edited.definition.model_copy(deep=True)
    changed.charts[0].metric = "orders"
    from app.models.askwiz import AutoDashboard

    row = await api.base._app.get(AutoDashboard, board.id)
    row.definition = changed.model_dump(mode="json")
    await api.base._app.flush()
    await api.run(board.id, 2)
    assert api.base.run.await_count == 1


async def test_narration_is_cache_only_and_fact_bound(
    api: AskWizService, monkeypatch: pytest.MonkeyPatch
) -> None:
    board = await api.create("", "weekly")
    absent = await api.narrate(board.id, 1)
    assert not absent.paragraphs
    from app.services.analytics.askwiz import chart_spec

    scope = RegionScope.all_regions()
    import time

    for chart in board.definition.charts:
        key = api.key(chart_spec(chart, board.definition), chart.dimension == "day", scope)
        CACHE[key] = (
            time.monotonic(),
            AnalyticsRunResponse(
                title="Fixture",
                columns=[],
                rows=[{"v": 20}],
                sql="",
                recommended_viz="bar",
                insights=AnalyticsInsights(executive="Revenue is ₹20.", analyst=""),
            ),
        )
    monkeypatch.setattr("app.services.analytics.askwiz.llm_configured", lambda _: True)
    complete = AsyncMock(
        return_value=LlmResult(sql=None, narrative="", model="mock", content='{"factIds":[2,0]}')
    )
    monkeypatch.setattr("app.services.analytics.askwiz.complete_text", complete)
    story = await api.narrate(board.id, 1)
    assert story.ai_used and len(story.paragraphs) == 2
    assert all("₹20" in text for text in story.paragraphs)
    again = await api.narrate(board.id, 1)
    assert again.llm_calls == 0 and complete.await_count == 1
    changed = await api.command(board.id, 1, "Make chart two a bar chart", None, "edit")
    styled = await AskWizService(api.base).narrate(board.id, changed.revision)
    assert styled.llm_calls == 0 and complete.await_count == 1
    api.base._analytics.execute.assert_not_awaited()


async def test_invalid_chart_shapes_and_filters(api: AskWizService) -> None:
    board = await api.create("", "sales")
    catalog, scope = await api.context()
    definition = board.definition.model_copy(deep=True)
    definition.charts[0].viz = "pie"
    with pytest.raises(ValidationError, match="pie"):
        validate_definition(definition, catalog, scope)
    definition = board.definition.model_copy(deep=True)
    definition.filters = {"raw_sql": ["anything"]}
    with pytest.raises(ValidationError, match="Unsupported filter"):
        validate_definition(definition, catalog, scope)


async def test_http_auth_csrf_domain_and_forged_fields(api: AskWizService) -> None:
    from httpx import ASGITransport, AsyncClient

    from app.api.deps import (
        get_app_session,
        get_current_user,
        get_scoped_analytics,
        get_semantic_service,
    )
    from app.main import create_app

    app = create_app(api.base._settings)
    app.dependency_overrides[get_app_session] = lambda: api.base._app
    app.dependency_overrides[get_scoped_analytics] = lambda: api.base._analytics
    app.dependency_overrides[get_semantic_service] = lambda: api.base._semantic
    async with AsyncClient(transport=ASGITransport(app), base_url="http://testserver") as client:
        assert (await client.get("/api/v1/analytics/auto/boards")).status_code == 401
        app.dependency_overrides[get_current_user] = lambda: api.base._user
        assert (
            await client.post("/api/v1/analytics/auto/boards", json={"recipe": "sales"})
        ).status_code == 403
        headers = {"authorization": "Bearer fixture", "x-industry": "insurance"}
        assert (
            await client.post(
                "/api/v1/analytics/auto/boards", json={"recipe": "sales"}, headers=headers
            )
        ).status_code == 403
        headers["x-industry"] = "automotive"
        assert (
            await client.post(
                "/api/v1/analytics/auto/boards",
                json={"recipe": "sales", "sql": "SELECT anything"},
                headers=headers,
            )
        ).status_code == 422
        created = await client.post(
            "/api/v1/analytics/auto/boards", json={"recipe": "sales"}, headers=headers
        )
        assert created.status_code == 200, created.text


async def test_provider_failure_never_drops_unrecognized_filter(
    api: AskWizService, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("app.services.analytics.askwiz.llm_configured", lambda _: True)
    complete = AsyncMock(
        return_value=LlmResult(
            sql=None, narrative="", model="mock", error="timeout", timed_out=True
        )
    )
    monkeypatch.setattr("app.services.analytics.askwiz.complete_text", complete)
    with pytest.raises(ValidationError):
        await api.create("Generate sales report in Chennai")
    api.base._analytics.execute.assert_not_awaited()
    board = await api.create("Generate report last week on daily sales")
    assert len(board.definition.charts) == 4 and "could not complete" in board.message


async def test_real_runner_daily_and_aggregate_query_budget(api: AskWizService) -> None:
    """Actual compiler/runner, synthetic DB cursor responses; not PostgreSQL validation."""
    import time

    board = await api.create("", "weekly")
    statements = []

    async def execute(statement, parameters=None, **kwargs):
        sql = str(statement)
        statements.append(sql)
        result = MagicMock()
        if "SELECT MAX(" in sql:
            result.scalar.return_value = date(2026, 11, 1)
            return result
        if "sales_day" in sql:
            value = "units" if "SUM(f.order_qty)" in sql else "revenue"
            rows = [
                {"sales_day": date(2026, 10, 26), value: 100},
                {"sales_day": date(2026, 10, 27), value: 120},
            ]
        elif "AS region" in sql:
            rows = [{"region": "West", "revenue": 220}]
        elif "AS model" in sql:
            rows = [{"model": "Nexon", "revenue": 220}]
        else:
            rows = [{"revenue": 220, "units": 22, "orders": 20}]
        result.keys.return_value = list(rows[0])
        result.mappings.return_value.fetchmany.return_value = rows
        return result

    api.base._analytics.execute = AsyncMock(side_effect=execute)
    cold = await api.run(board.id, 1)
    assert not any(c.error for c in [*cold.charts, *cold.kpis]), cold
    assert cold.query_count == 12  # six result SELECTs plus six freshness SELECTs
    assert sum("SELECT MAX(" in sql for sql in statements) == 6
    assert not any("WITH totals" in sql for sql in statements)  # no optional driver query
    assert cold.kpis[0].result.rows[0] == {"revenue": 220, "units": 22, "orders": 20}
    assert cold.charts[0].result.chart.x == "sales_day"
    samples = []
    for _ in range(20):
        start = time.perf_counter()
        warm = await api.run(board.id, 1)
        samples.append((time.perf_counter() - start) * 1000)
        assert warm.query_count == 0 and warm.cache_hits == 6
    print(
        f"\nASKWIZ synthetic runner: cold={cold.elapsed_ms:.3f}ms/12 execute calls; "
        f"warm p50={sorted(samples)[9]:.3f}ms p95={sorted(samples)[18]:.3f}ms/0 warehouse calls; "
        "no live DB or model."
    )
