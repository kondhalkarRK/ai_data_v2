"""Data Reliability Center: rule compilation, scoring, monitors, store and response assembly."""

from __future__ import annotations

import re
from collections.abc import AsyncIterator
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import Industry
from app.models import Base
from app.models.reliability import DqRuleRun, DqRuleSetting, DqScoreSnapshot
from app.schemas.reliability import (
    BulkMonitorRequest,
    CatalogColumn,
    CreateMonitorRequest,
    EntityChanges,
    SchemaDrift,
)
from app.services.reliability.defaults import (
    AUTOMOTIVE_DATASETS,
    AUTOMOTIVE_RULES,
    INSURANCE_DATASETS,
    INSURANCE_RULES,
)
from app.services.reliability.engine import (
    ROW_KINDS,
    RuleDefinitionError,
    compile_condition,
    finish_population,
    freshness_score,
    period_end,
)
from app.services.reliability.model import (
    DIMENSION_INFO,
    DatasetSpec,
    RuleResult,
    RuleSpec,
    band_for,
)
from app.services.reliability.scoring import (
    dimension_scores,
    effective_weights,
    impact_text,
    overall_score,
    quality_drops,
    record_date_trend,
    window_delta,
)
from app.services.reliability.service import (
    MonitorValidationError,
    RunOutcome,
    _snapshot_payload,
    build_response,
    bulk_change,
    rescore,
    validate_monitor,
)
from app.services.reliability.store import _MEMORY, ReliabilityStore, Setting

NOW = datetime(2026, 10, 1, 9, 0, tzinfo=UTC)


def rule(rule_id: str, **overrides: object) -> RuleSpec:
    base = RuleSpec(
        id=rule_id,
        name=rule_id.title(),
        dimension="accuracy",
        dataset="sales",
        severity="medium",
        kind="row_check",
        description="",
        owner="Owner",
        condition="TRUE",
        unit="orders",
        assets=("Revenue dashboard",),
    )
    return replace(base, **overrides)  # type: ignore[arg-type]


def passing(rule_id: str, score: float = 100.0, **extra: object) -> RuleResult:
    return RuleResult(
        rule_id, "passing", total=100, failed=0, pass_rate=score, score=score, **extra
    )  # type: ignore[arg-type]


def failing(rule_id: str, failed: int, total: int = 1000, **extra: object) -> RuleResult:
    rate = 100 * (1 - failed / total)
    return RuleResult(
        rule_id,
        "failing",
        total=total,
        failed=failed,
        pass_rate=rate,
        score=rate,
        **extra,  # type: ignore[arg-type]
    )


# --------------------------------------------------------------------------- engine helpers


def test_population_result_respects_threshold_and_empty_population() -> None:
    strict = rule("r", threshold=100)
    assert finish_population(strict, 1000, 0, None).status == "passing"
    result = finish_population(strict, 1000, 1, 5_000.0)
    assert result.status == "failing"
    assert result.pass_rate == pytest.approx(99.9)
    assert result.value_at_risk == 5_000.0
    assert result.observed == "1 of 1,000 orders failed"
    lenient = rule("r", threshold=99.5)
    assert finish_population(lenient, 1000, 5, None).status == "passing"
    assert finish_population(lenient, 1000, 6, None).status == "failing"
    assert finish_population(strict, 0, 0, None).status == "no_data"


def test_freshness_score_and_period_end() -> None:
    assert freshness_score(10, 36) == 100
    assert freshness_score(72, 36) == 50
    assert freshness_score(200, 36) == 0
    assert period_end(date(2026, 9, 30), "daily") == datetime(2026, 10, 1, tzinfo=UTC)
    assert period_end(date(2026, 12, 1), "monthly") == datetime(2027, 1, 1, tzinfo=UTC)


def test_conditions_bind_user_values_and_reject_unsafe_columns() -> None:
    compiled = compile_condition(
        rule("r", kind="range", column="price", min_value=1, max_value=9, condition=None), 3
    )
    assert compiled.params == {"lo_3": 1, "hi_3": 9}
    assert "t.price IS NULL OR" in compiled.condition
    allowed = compile_condition(
        rule("r", kind="allowed_values", column="grade", allowed=("A", "B"), condition=None), 0
    )
    assert allowed.expanding == ("vals_0",) and allowed.params["vals_0"] == ["A", "B"]
    pattern = compile_condition(
        rule("r", kind="pattern", column="email", pattern="^x';--", condition=None), 1
    )
    assert "';--" not in pattern.condition and pattern.params["re_1"] == "^x';--"
    with pytest.raises(RuleDefinitionError):
        compile_condition(rule("r", kind="not_null", column="a; DROP TABLE x", condition=None), 0)


@pytest.mark.parametrize(
    ("datasets", "rules"),
    [(AUTOMOTIVE_DATASETS, AUTOMOTIVE_RULES), (INSURANCE_DATASETS, INSURANCE_RULES)],
)
def test_default_catalog_is_consistent(
    datasets: tuple[DatasetSpec, ...], rules: tuple[RuleSpec, ...]
) -> None:
    names = {d.name for d in datasets}
    ids = [r.id for r in rules]
    assert len(ids) == len(set(ids))
    assert {r.dimension for r in rules} == set(DIMENSION_INFO)
    for item in rules:
        assert item.dataset in names, item.id
        if item.kind in ROW_KINDS:
            compile_condition(item, 0)
        if item.kind == "metric":
            assert item.sql and "SELECT" in item.sql
        if item.kind == "reference":
            assert item.ref_dataset in names
        assert item.impact, item.id
        impact_text(item, failing(item.id, 3))
    assert sum(info.weight for info in DIMENSION_INFO.values()) == 100


# --------------------------------------------------------------------------- scoring


def test_dimension_and_trust_scores_weight_severity_and_skip_unscored_rules() -> None:
    rules = [
        rule("crit", severity="critical"),
        rule("low", severity="low"),
        rule("broken", severity="critical"),
        rule("off", severity="critical", enabled=False),
        rule("fresh", dimension="timeliness", kind="freshness"),
    ]
    results = {
        "crit": passing("crit", 100.0),
        "low": failing("low", 500),  # 50
        "broken": RuleResult("broken", "error"),
        "off": failing("off", 1000),
        "fresh": passing("fresh", 80.0),
    }
    dims = dimension_scores(rules, results)
    assert dims["accuracy"].score == pytest.approx((100 * 4 + 50 * 1) / 5)
    assert dims["accuracy"].errored == 1 and dims["accuracy"].failing == 1
    assert dims["completeness"].score is None
    weights = effective_weights(dims)
    assert weights == {"accuracy": 62.5, "timeliness": 37.5}
    assert overall_score(dims) == pytest.approx((90 * 25 + 80 * 15) / 40, abs=0.05)
    assert band_for(96)[0] == "excellent" and band_for(85)[0] == "good"
    assert band_for(70)[0] == "fair" and band_for(69.9)[0] == "risk"

    snapshot = _snapshot_payload(overall_score(dims), dims, RunOutcome(NOW, results))
    shares = {c["id"]: c["weight"] for c in snapshot["components"]}
    assert shares == {"accuracy": 0.625, "timeliness": 0.375}


def test_record_date_trend_flags_a_bad_day_and_uses_monthly_results() -> None:
    end = date(2026, 9, 30)
    daily = {end - timedelta(days=i): (100, 0) for i in range(30)}
    daily[end - timedelta(days=5)] = (100, 40)
    monthly = {date(2026, 9, 1): (10, 5), date(2026, 8, 1): (10, 0)}
    rules = [
        rule("orders", severity="critical"),
        rule("forecast", dimension="completeness", kind="metric", threshold=85),
    ]
    results = {
        "orders": passing("orders", 99.9, trend=daily),
        "forecast": passing("forecast", 90.0, trend=monthly),
    }
    points = record_date_trend(rules, results, end=end, days=40)
    assert len(points) == 40 and points[-1].day == end
    by_day = {p.day: p for p in points}
    bad = by_day[end - timedelta(days=5)]
    assert "orders" in bad.failing_rules
    assert bad.dimensions["accuracy"] == pytest.approx(60.0)
    assert by_day[date(2026, 8, 31)].dimensions["completeness"] == pytest.approx(100.0)
    assert by_day[date(2026, 9, 2)].dimensions["completeness"] == pytest.approx(50.0)
    assert bad in quality_drops(points)
    assert window_delta([1.0] * 7 + [2.0] * 7) == pytest.approx(1.0)
    assert window_delta([1.0] * 5) is None


def test_impact_text_speaks_business_language() -> None:
    item = rule(
        "rev",
        impact="{failed} orders mismatch; revenue misstated by {value}.",
    )
    text = impact_text(item, failing("rev", 2500, total=100_000, value_at_risk=3.2e7))
    assert text == "2,500 orders mismatch; revenue misstated by \u20b93.20 Cr."
    gap = rule("fc", threshold=85, impact="about {gap} points below {threshold}%")
    assert impact_text(gap, failing("fc", 19, total=100)) == "about 4.0 points below 85%"


def test_rescore_applies_new_threshold_without_rerun() -> None:
    result = failing("r", 3, total=1000)
    assert rescore(rule("r", threshold=99.5), result).status == "passing"
    assert rescore(rule("r", threshold=100), result).status == "failing"


# --------------------------------------------------------------------------- monitors

DATASETS = {
    "sales": DatasetSpec(
        "sales", "automotive.fact_sales", "Sales", "fact", "Sales", date_column="sales_date"
    ),
    "dealers": DatasetSpec("dealers", "automotive.dim_dealer", "Dealers", "dimension", "Dealer"),
}
COLUMNS = {
    "sales": [
        CatalogColumn(name="sales_date", label="Date", type="date"),
        CatalogColumn(name="price", label="Price", type="decimal"),
        CatalogColumn(name="dealer_id", label="Dealer", type="integer"),
    ],
    "dealers": [CatalogColumn(name="dealer_id", label="Dealer", type="integer")],
}


def monitor(**fields: object) -> CreateMonitorRequest:
    base: dict[str, object] = {
        "name": "Price floor",
        "dimension": "validity",
        "dataset": "sales",
        "severity": "high",
        "kind": "range",
        "column": "price",
        "minValue": 1,
        "tags": ["Pricing", " pricing ", "kpi"],
    }
    base.update(fields)
    return CreateMonitorRequest.model_validate(base)


def test_monitor_validation_accepts_known_columns_only() -> None:
    definition = validate_monitor(monitor(), DATASETS, COLUMNS)
    assert definition["column"] == "price" and definition["min_value"] == 1
    assert definition["tags"] == ["pricing", "kpi"]
    with pytest.raises(MonitorValidationError):
        validate_monitor(monitor(column="unknown"), DATASETS, COLUMNS)
    with pytest.raises(MonitorValidationError):
        validate_monitor(monitor(dataset="nope"), DATASETS, COLUMNS)
    with pytest.raises(MonitorValidationError):
        validate_monitor(
            monitor(kind="freshness", column="price", maxAgeHours=24), DATASETS, COLUMNS
        )
    with pytest.raises(MonitorValidationError):
        validate_monitor(monitor(kind="pattern", pattern="(unclosed"), DATASETS, COLUMNS)
    ref = validate_monitor(
        monitor(kind="reference", column="dealer_id", refDataset="dealers", refColumn="dealer_id"),
        DATASETS,
        COLUMNS,
    )
    assert ref["ref_dataset"] == "dealers"


def test_bulk_changes() -> None:
    item = rule("r", tags=("a",))

    def change(action: str, **kw: object) -> object:
        return bulk_change(
            item, BulkMonitorRequest.model_validate({"ruleIds": ["r"], "action": action, **kw})
        )

    assert change("assign_dimension", value="timeliness") == {"dimension": "timeliness"}
    assert change("assign_dimension", value="bogus") is None
    assert change("set_severity", value="critical") == {"severity": "critical"}
    assert change("add_tags", tags=["B"]) == {"tags": ["a", "b"]}
    assert change("remove_tags", tags=["a"]) == {"tags": []}
    assert change("disable") == {"enabled": False}
    assert change("enable") == {"enabled": True}


# --------------------------------------------------------------------------- store


@pytest.fixture
async def reliability_session() -> AsyncIterator[AsyncSession]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    tables = [DqRuleSetting.__table__, DqRuleRun.__table__, DqScoreSnapshot.__table__]
    async with engine.begin() as connection:
        await connection.run_sync(lambda sync: Base.metadata.create_all(sync, tables=tables))
    async with async_sessionmaker(engine, expire_on_commit=False)() as session:
        yield session
    await engine.dispose()


async def test_store_persists_settings_and_failure_history(
    reliability_session: AsyncSession,
) -> None:
    store = ReliabilityStore(reliability_session, Industry.AUTOMOTIVE)
    await store.save_setting(Setting(rule_id="auto.x", custom=False, overrides={"owner": "A"}))
    await store.save_setting(Setting(rule_id="auto.x", custom=False, overrides={"owner": "B"}))
    settings = await store.settings()
    assert store.mode == "database"
    assert settings["auto.x"].overrides == {"owner": "B"}

    first, second, third = NOW - timedelta(days=2), NOW - timedelta(days=1), NOW
    await store.record_run(
        ran_at=first,
        results={"r": failing("r", 3)},
        score=90.0,
        dimensions={},
        datasets={},
        duration_ms=10,
        triggered_by=None,
    )
    await store.record_run(
        ran_at=second,
        results={"r": passing("r")},
        score=99.0,
        dimensions={},
        datasets={},
        duration_ms=10,
        triggered_by=None,
    )
    await store.record_run(
        ran_at=third,
        results={"r": failing("r", 5)},
        score=95.0,
        dimensions={},
        datasets={},
        duration_ms=10,
        triggered_by=None,
    )
    history = (await store.history(now=NOW))["r"]
    assert history.runs == 3
    assert history.last_failure_at == third
    assert history.failing_since == third
    assert len(await store.snapshots(now=NOW)) == 3
    await store.delete_setting("auto.x")
    assert "auto.x" not in await store.settings()


async def test_store_falls_back_to_memory_without_a_session() -> None:
    _MEMORY.clear()
    store = ReliabilityStore(None, Industry.INSURANCE)
    await store.save_setting(Setting(rule_id="ins.x", custom=True, definition={"name": "x"}))
    assert store.mode == "memory"
    assert (await store.settings())["ins.x"].definition == {"name": "x"}
    _MEMORY.clear()


# --------------------------------------------------------------------------- response


def test_build_response_assembles_executive_view() -> None:
    datasets = {
        "sales": DatasetSpec(
            "sales",
            "automotive.fact_sales",
            "Sales Transactions",
            "fact",
            "Sales",
            date_column="sales_date",
            cadence="daily",
            sla_hours=36,
            value_column="total_sales",
        ),
        "dealers": DatasetSpec(
            "dealers", "automotive.dim_dealer", "Dealer Network", "dimension", "Dealer"
        ),
    }
    rules = [
        rule(
            "auto.rev",
            name="Revenue Validation",
            severity="critical",
            impact="{failed} orders mismatch ({value}).",
        ),
        rule(
            "auto.fresh",
            name="Sales Freshness",
            dimension="timeliness",
            kind="freshness",
            severity="critical",
            max_age_hours=36,
        ),
        rule(
            "auto.dealer",
            name="Dealer Uniqueness",
            dimension="uniqueness",
            dataset="dealers",
            kind="unique",
            severity="high",
        ),
        rule("auto.broken", name="Broken", dimension="consistency", severity="low"),
    ]
    results = {
        "auto.rev": failing("auto.rev", 25, total=10_000, value_at_risk=1.5e6),
        "auto.fresh": passing("auto.fresh"),
        "auto.dealer": passing("auto.dealer"),
        "auto.broken": RuleResult("auto.broken", "error", error="boom"),
    }
    outcome = RunOutcome(
        ran_at=NOW,
        results=results,
        latest={"sales": date(2026, 9, 30)},
        estimates={"automotive.fact_sales": 10_000},
    )
    response = build_response(
        industry=Industry.AUTOMOTIVE,
        rules=rules,
        results=results,
        outcome=outcome,
        datasets=datasets,
        history={},
        snapshots=[],
        drift=SchemaDrift(status="stable", label="Stable"),
        entities=EntityChanges(available=False),
        columns={},
        storage="memory",
    )
    hero = response.hero
    assert hero.available and hero.rules_failing == 1 and hero.critical_issues == 1
    assert hero.rules_errored == 1 and hero.datasets_monitored == 2
    assert [a.rule_id for a in response.alerts] == ["auto.rev", "auto.broken"]
    assert response.alerts[0].impact == "25 orders mismatch (\u20b915.0 L)."
    assert "boom" not in response.model_dump_json()
    assert response.impact.records_affected == 25
    assert response.freshness[0].status == "on_time"
    assert response.datasets[0].rank == 1
    texts = [s.text for s in response.summary.statements]
    assert "No freshness issues" in texts and "Schema stable" in texts
    assert {d.key for d in response.dimensions} == set(DIMENSION_INFO)
    assert response.methodology.bands[0].min == 95
    assert re.search(r"Trust = ", response.methodology.formula)

    empty = {r.id: RuleResult(r.id, "no_data") for r in rules}
    unmeasured = build_response(
        industry=Industry.AUTOMOTIVE,
        rules=rules,
        results=empty,
        outcome=RunOutcome(ran_at=NOW, results=empty),
        datasets=datasets,
        history={},
        snapshots=[],
        drift=SchemaDrift(status="stable", label="Stable"),
        entities=EntityChanges(available=False),
        columns={},
        storage="memory",
    )
    assert not unmeasured.hero.available
    assert "no rows yet" in (unmeasured.hero.unavailable_reason or "")
