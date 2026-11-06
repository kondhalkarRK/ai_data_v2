"""AskBI behavior, arithmetic and governance; no external database/provider."""

import json
import sqlite3
import uuid
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock
from zoneinfo import ZoneInfo

import pytest
import sqlglot
from pydantic import ValidationError as ContractError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api.routes.analytics import _permitted_region_values
from app.core.config import Industry, Settings
from app.core.exceptions import AuthorizationError, ConflictError, NotFoundError, ValidationError
from app.models import Base
from app.models.enums import Role
from app.models.user import User
from app.schemas.analytics import FilterValueItem, FilterValuesResponse
from app.schemas.analytics_workspace import WorkspaceSpec
from app.schemas.bi import (
    BiCreate,
    BiPanel,
    BiPending,
    BiPlan,
    BiReportFilter,
    BiState,
    BiTurnRequest,
)
from app.semantic.service import SemanticService
from app.services.analytics.bi import advanced, execution, planning, repository, service
from app.services.analytics.bi.llm import BiProviderError
from app.services.analytics.catalog import Catalog
from app.services.analytics.compiler import compile_builder_query
from app.services.security.region_scope import RegionScope

NOW = datetime(2026, 11, 5, tzinfo=ZoneInfo("Asia/Kolkata"))
SCOPE = RegionScope.all_regions()


@pytest.fixture
def catalog():
    return Catalog(Industry.AUTOMOTIVE, SemanticService(Settings())._load_pack(Industry.AUTOMOTIVE))


def panel(**kwargs):
    return BiPanel(
        id="p1",
        title="Revenue",
        kind="chart",
        spec=WorkspaceSpec(
            metrics=["revenue"],
            dimensions=["model"],
            date_preset="custom",
            date_from="2026-10-26",
            date_to="2026-11-01",
            viz="bar",
        ),
        **kwargs,
    )


@pytest.mark.parametrize(
    "question,kind,start,end",
    [
        ("Total revenue yesterday", "single_value", "2026-11-04", "2026-11-04"),
        ("Daily sales last week", "analysis", "2026-10-26", "2026-11-01"),
        ("Generate a report of last week on daily sales", "report", "2026-10-26", "2026-11-01"),
    ],
)
def test_exact_questions_have_no_fixed_chart_count(catalog, question, kind, start, end):
    proposal = planning.fast_plan(question, NOW, None)
    assert proposal.plan.answer_kind == kind
    assert len(proposal.plan.panels) == 1
    p = proposal.plan.panels[0]
    assert (p.spec.date_from, p.spec.date_to) == (start, end)
    planning.validate(proposal.plan, catalog, SCOPE)
    sql = compile_builder_query(p.spec, catalog, daily=p.daily, bi_grain=p.grain).sql
    assert sqlglot.parse_one(sql, read="postgres")


def test_unknown_qualifiers_never_use_template():
    assert planning.fast_plan("sales for unicorn last week", NOW, None) is None
    assert planning.fast_plan("daily profit last week", NOW, None) is None


@pytest.mark.parametrize("question", ["total sales by region", "Show me revenue by region?"])
def test_undated_region_sales_uses_disclosed_completed_month(catalog, question):
    proposal = planning.fast_plan(question, NOW, None)
    assert proposal is not None and proposal.kind == "answer" and proposal.plan is not None
    assert len(proposal.plan.panels) == 1
    panel = proposal.plan.panels[0]
    assert panel.spec.metrics == ["revenue"]
    assert panel.spec.dimensions == ["region"]
    assert (panel.spec.date_from, panel.spec.date_to) == ("2026-10-01", "2026-10-31")
    assert "last completed" in proposal.message
    assert "last completed" in proposal.plan.assumptions[0]
    planning.validate(proposal.plan, catalog, SCOPE)


def test_undated_fast_path_does_not_discard_qualifiers():
    assert planning.fast_plan("total sales by region for Tata", NOW, None) is None


@pytest.mark.parametrize("question", list(planning.LEADERSHIP_PROMPTS))
def test_leadership_report_presets_are_governed_and_bounded(catalog, question):
    proposal = planning.fast_plan(question, NOW, None)
    assert proposal is not None and proposal.plan is not None
    assert proposal.kind == "answer" and proposal.plan.answer_kind == "report"
    assert len(proposal.plan.panels) == 6
    assert [p.kind for p in proposal.plan.panels].count("kpi") == 2
    assert [p.kind for p in proposal.plan.panels].count("chart") == 4
    assert all(p.spec.filters == [] for p in proposal.plan.panels)
    planning.validate(proposal.plan, catalog, SCOPE)
    for p in proposal.plan.panels:
        assert sqlglot.parse_one(
            compile_builder_query(p.spec, catalog, bi_grain=p.grain).sql, read="postgres"
        )


def test_leadership_prompt_with_extra_qualifier_is_not_a_preset():
    assert (
        planning.fast_plan(
            "Create a weekly sales and revenue briefing for the CFO for Tata", NOW, None
        )
        is None
    )


def test_report_filters_apply_same_dates_and_make_to_every_panel(catalog):
    plan = planning.fast_plan("Make & Model Comparison", NOW, None).plan
    selected = BiReportFilter(period="month", year=2025, month=4, make="Tata")
    filtered = planning.apply_report_filter(plan, selected)
    assert all(
        (p.spec.date_from, p.spec.date_to) == ("2025-04-01", "2025-04-30") for p in filtered.panels
    )
    assert all(
        len(p.spec.filters) == 1 and p.spec.filters[0].values == ["Tata"] for p in filtered.panels
    )
    assert all(not p.date_intent for p in filtered.panels)
    planning.validate(filtered, catalog, SCOPE)
    assert not plan.panels[0].spec.filters


def test_region_report_filters_dealers_and_models_within_permitted_zone(catalog):
    plan = planning.fast_plan("Region & Dealer Performance", NOW, None).plan
    west = RegionScope(unrestricted=False, zones=("West",))
    filtered = planning.apply_report_filter(
        plan, BiReportFilter(period="month", year=2026, month=10, region="Mumbai")
    )
    assert all(
        len(p.spec.filters) == 1
        and p.spec.filters[0].domain == "region"
        and p.spec.filters[0].values == ["Mumbai"]
        for p in filtered.panels
    )
    planning.validate(filtered, catalog, west)
    forbidden = planning.apply_report_filter(
        plan, BiReportFilter(period="month", year=2026, month=10, region="New Delhi")
    )
    with pytest.raises(AuthorizationError):
        planning.validate(forbidden, catalog, west)


def test_region_options_exclude_places_outside_user_scope():
    west = RegionScope(unrestricted=False, zones=("West",))
    values = FilterValuesResponse(
        domain="region",
        label="Region",
        values=[FilterValueItem(value="Mumbai"), FilterValueItem(value="New Delhi")],
    )
    result = _permitted_region_values(values, west)
    assert [item.value for item in result.values] == ["Mumbai"]


def test_week_filter_uses_monday_and_preserves_missing_values():
    from pydantic import ValidationError as PydanticError

    plan = planning.fast_plan("Sales Report for CEO", NOW, None).plan
    filtered = planning.apply_report_filter(
        plan, BiReportFilter(period="week", year=2026, week_start="2026-11-02")
    )
    assert all(
        (p.spec.date_from, p.spec.date_to) == ("2026-11-02", "2026-11-08") for p in filtered.panels
    )
    assert next(p for p in filtered.panels if p.title == "Revenue trend").grain == "day"
    with pytest.raises(PydanticError):
        BiReportFilter(period="week", year=2026, week_start="2026-11-03")


def test_context_preserves_original_and_pending_slot():
    state = BiState(
        pending=BiPending(question="Make a sales report", clarification="Which period and metric?")
    )
    question = planning.contextual_question(state, "Revenue last week")
    assert "Make a sales report" in question and "Revenue last week" in question


def test_continuation_never_silently_drops_retained_filters():
    prior = BiPlan(title="Filtered", panels=[panel()])
    assert planning.fast_plan("Daily sales last week", NOW, prior) is None


def test_relative_date_labels_and_comparison_need_matching_evidence():
    p = panel(date_intent="this week")
    with pytest.raises(ValidationError, match="intent"):
        planning.validate_interpretation(
            BiPlan(title="wrong", panels=[p]), "Sales", None, None, NOW
        )
    p.date_intent = "last week"
    p.spec.date_to = "2026-10-29"
    with pytest.raises(ValidationError):
        planning.validate_interpretation(
            BiPlan(title="half", panels=[p]), "Compare this week with last week", None, None, NOW
        )


async def test_http_contract_and_csrf_are_enforced():
    from fastapi import FastAPI
    from httpx import ASGITransport, AsyncClient

    from app.api import deps
    from app.api.routes import analytics
    from app.core.exceptions import CsrfError

    app = FastAPI()
    app.include_router(analytics.router)
    app.dependency_overrides[deps.get_current_user] = lambda: SimpleNamespace(role=Role.ADMIN)
    app.dependency_overrides[deps.get_app_settings] = lambda: Settings(ask_me_askbi_enabled=True)
    app.dependency_overrides[deps.resolve_industry] = lambda: Industry.AUTOMOTIVE
    app.dependency_overrides[analytics._service] = lambda: SimpleNamespace()
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        caps = await client.get("/analytics/bi/capabilities")
        assert caps.status_code == 200 and caps.json()["schemaVersion"] == 2
        with pytest.raises(CsrfError):
            await client.post("/analytics/bi/reports", json={"id": str(uuid.uuid4())})
        app.dependency_overrides[deps.verify_csrf] = lambda: None
        rejected = await client.post(
            f"/analytics/bi/reports/{uuid.uuid4()}/turns",
            json={"requestId": str(uuid.uuid4()), "revision": 1, "sql": "SELECT 1"},
        )
        assert rejected.status_code == 422


async def test_llm_gets_clarification_and_keeps_original(catalog):
    state = BiState(
        pending=BiPending(question="Sales performance", clarification="Which breakdown?")
    )
    proposed = {
        "kind": "answer",
        "message": "Revenue by model for last week.",
        "plan": BiPlan(title="Sales", panels=[panel()]).model_dump(mode="json"),
    }
    llm = SimpleNamespace(call=AsyncMock(return_value=json.dumps(proposed)))
    answer = await planning.propose(
        state, "Revenue last week by model", None, NOW, catalog, SCOPE, llm
    )
    assert answer.kind == "answer"
    assert "Sales performance" in llm.call.call_args.args[1]
    assert "SUM(total_sales)" in llm.call.call_args.args[0]


async def test_invalid_response_has_one_correction(catalog):
    llm = SimpleNamespace(call=AsyncMock(return_value=""))
    with pytest.raises(BiProviderError, match="validated"):
        await planning.propose(
            BiState(), "Build an executive report", None, NOW, catalog, SCOPE, llm
        )
    assert llm.call.await_count == 2


def test_selected_edits_preserve_others(catalog):
    original = BiPlan(title="Report", panels=[panel(), panel().model_copy(update={"id": "p2"})])
    changed = original.model_copy(deep=True)
    changed.panels[1].title = "Unexpected change"
    with pytest.raises(ValidationError, match="selected"):
        planning.validate_interpretation(changed, "change this chart", original, "p1", NOW)
    edited, _ = service.local_visual("Make the second chart a line", original, None)
    assert edited.panels[1].spec.viz == "line"
    assert planning.data_key(edited.panels[1]) == planning.data_key(original.panels[1])


@pytest.mark.parametrize("grain", ["day", "week"])
def test_calendar_rolling_compiles_spine_and_missing_guard(catalog, grain):
    p = panel(grain=grain)
    p.spec.dimensions = ["month"]
    p.spec.analysis = "moving_average"
    p.spec.window = 7
    planning.validate(BiPlan(title="Rolling", panels=[p]), catalog, SCOPE)
    query = compile_builder_query(p.spec, catalog, bi_grain=grain)
    assert "generate_series" in query.sql
    assert "COUNT(revenue) OVER w = 7" in query.sql
    assert "COALESCE" not in query.sql
    assert query.time_grain == grain
    sqlglot.parse_one(query.sql, read="postgres")


def test_weighted_asp_and_zero_denominator_execute_on_fixture(catalog):
    spec = WorkspaceSpec(metrics=["average_selling_price"], dimensions=[], viz="kpi")
    query = compile_builder_query(spec, catalog)
    sql = sqlglot.transpile(query.sql, read="postgres", write="sqlite")[0]
    db = sqlite3.connect(":memory:")
    try:
        db.execute("ATTACH DATABASE ':memory:' AS automotive")
        db.execute("CREATE TABLE automotive.fact_sales(total_sales REAL, order_qty INTEGER)")
        db.executemany("INSERT INTO automotive.fact_sales VALUES (?,?)", [(100, 1), (900, 3)])
        assert db.execute(sql).fetchone()[0] == 250
        db.execute("DELETE FROM automotive.fact_sales")
        db.execute("INSERT INTO automotive.fact_sales VALUES (100,0)")
        assert db.execute(sql).fetchone()[0] is None
    finally:
        db.close()


def test_benchmark_denominator_before_limit_and_formula(catalog):
    p = panel(calculation="index_to_average")
    source, expected, _ = advanced.shape(p, catalog)
    assert "LIMIT" not in source.sql.upper()
    assert advanced.validate_sql(expected, expected)
    db = sqlite3.connect(":memory:")
    try:
        db.execute("CREATE TABLE bi_input(model TEXT, revenue REAL)")
        db.executemany("INSERT INTO bi_input VALUES (?,?)", [("A", 100), ("B", 300)])
        query = sqlglot.transpile(expected, read="postgres", write="sqlite")[0]
        values = {row[0]: row[2] for row in db.execute(query)}
        assert values == {"A": 50, "B": 150}
    finally:
        db.close()


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT pg_sleep(5) FROM bi_input",
        "DELETE FROM bi_input",
        "SELECT * FROM automotive.fact_sales",
        "SELECT * FROM bi_input; SELECT * FROM auth_users",
        "WITH x AS (DELETE FROM bi_input RETURNING *) SELECT * FROM x",
        "SELECT *, 123 AS bi_value FROM bi_input",
        "SELECT * INTO stolen FROM bi_input",
    ],
)
def test_advanced_structural_gate_rejects_escape(catalog, sql):
    _, expected, _ = advanced.shape(panel(calculation="z_score"), catalog)
    with pytest.raises(ValidationError):
        advanced.validate_sql(sql, expected)


def test_contract_rejects_sql_and_duplicate_ids():
    with pytest.raises(ContractError):
        BiTurnRequest(request_id=uuid.uuid4(), revision=1, sql="SELECT 1")
    with pytest.raises(ContractError):
        BiPlan(title="bad", panels=[panel(), panel()])


def test_narration_cannot_smuggle_numbers_or_causality():
    facts = [{"id": "p1:value", "text": "Revenue is INR 120."}]
    assert execution.render_story('["Performance overview: {{p1:value}}"]', facts) == [
        "Performance overview: Revenue is INR 120."
    ]
    for raw in [
        '["Revenue is 999 {{p1:value}}"]',
        '["Advertising caused growth {{p1:value}}"]',
        '["{{other:value}}"]',
    ]:
        with pytest.raises(ValueError):
            execution.render_story(raw, facts)


def test_evidence_binds_owner_report_revision_and_scope():
    base = SimpleNamespace(
        _settings=Settings(),
        _industry=Industry.AUTOMOTIVE,
        _user=SimpleNamespace(id=uuid.uuid4(), role="admin"),
    )
    report_id = uuid.uuid4()
    p = panel()
    state = BiState(plan=BiPlan(title="Evidence", panels=[p]))
    token = execution.sign(
        base, SCOPE, report_id, 1, p, [{"id": "p1:value", "text": "Revenue 120"}]
    )
    assert execution.verify(base, SCOPE, report_id, 1, state, [token])
    for target, revision in [(uuid.uuid4(), 1), (report_id, 2)]:
        with pytest.raises(ValidationError):
            execution.verify(base, SCOPE, target, revision, state, [token])
    base._user.id = uuid.uuid4()
    with pytest.raises(ValidationError):
        execution.verify(base, SCOPE, report_id, 1, state, [token])


async def test_feature_gate_and_insurance_exclusion():
    base = SimpleNamespace(
        _industry=Industry.INSURANCE, _settings=Settings(ask_me_askbi_enabled=True)
    )
    with pytest.raises(AuthorizationError):
        await repository.context(base)
    base._industry = Industry.AUTOMOTIVE
    base._settings.ask_me_askbi_enabled = False
    with pytest.raises(NotFoundError):
        await repository.context(base)


async def test_persistence_idempotency_undo_conflicts_and_owner(catalog, monkeypatch):
    context = AsyncMock(return_value=(catalog, SCOPE))
    monkeypatch.setattr(repository, "context", context)
    monkeypatch.setattr(service, "context", context)
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with async_sessionmaker(engine, expire_on_commit=False)() as session:
        user = User(
            id=uuid.uuid4(),
            username="askbi",
            email="bi@example.com",
            email_normalized="bi@example.com",
            full_name="BI",
            password_hash="unused",
            role=Role.ADMIN,
            default_industry=Industry.AUTOMOTIVE,
            is_active=True,
        )
        session.add(user)
        await session.flush()
        base = SimpleNamespace(
            _settings=Settings(ask_me_askbi_enabled=True),
            _industry=Industry.AUTOMOTIVE,
            _user=user,
            _app=session,
        )
        created = await repository.create(base, BiCreate(id=uuid.uuid4()))
        req = BiTurnRequest(request_id=uuid.uuid4(), revision=1, question="Daily sales last week")
        report = await service.turn(base, created.id, req)
        assert report.revision == 2 and report.state.plan
        again = await service.turn(base, created.id, req)
        assert again.revision == 2 and len(again.state.turns) == 1
        with pytest.raises(ConflictError):
            await service.turn(
                base, created.id, BiTurnRequest(request_id=uuid.uuid4(), revision=1, action="save")
            )
        edited = await service.turn(
            base,
            created.id,
            BiTurnRequest(
                request_id=uuid.uuid4(),
                revision=2,
                action="visualize",
                selected_panel_id="primary",
                value="bar",
            ),
        )
        assert edited.state.plan.panels[0].spec.viz == "bar"
        undone = await service.turn(
            base, created.id, BiTurnRequest(request_id=uuid.uuid4(), revision=3, action="undo")
        )
        assert undone.state.plan.panels[0].spec.viz == "line"
        monkeypatch.setattr(
            service, "propose", AsyncMock(side_effect=BiProviderError("quota", "Quota exhausted"))
        )
        error = await service.turn(
            base,
            created.id,
            BiTurnRequest(request_id=uuid.uuid4(), revision=4, question="Build a report"),
        )
        assert error.state.turns[-1].kind == "error" and error.state.plan == undone.state.plan
        base._user = SimpleNamespace(id=uuid.uuid4(), role=Role.ADMIN)
        with pytest.raises(NotFoundError):
            await repository.owned(base, created.id, SCOPE)
    await engine.dispose()
