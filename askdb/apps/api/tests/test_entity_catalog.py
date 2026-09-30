"""Entity Catalog: drift detection, readiness, refresh bookkeeping and cache hand-off."""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import Industry, Settings
from app.models.catalog import CatalogChange, CatalogColumn, CatalogRefresh, CatalogValue
from app.semantic.service import SemanticService
from app.services.catalog import service as catalog_service
from app.services.catalog.config import CatalogConfig, build_catalog_config
from app.services.catalog.drift import (
    ColumnInfo,
    diff_schema,
    diff_values,
    rename_confidence,
)
from app.services.catalog.introspect import CatalogObservation, DomainObservation
from app.services.catalog.readiness import assess_value
from app.services.catalog.service import EntityCatalogService
from app.services.chat.value_dictionary import (
    cached_value_dictionary,
    invalidate_value_dictionary,
)

CATALOG_TABLES = [
    model.__table__  # type: ignore[attr-defined]
    for model in (CatalogRefresh, CatalogValue, CatalogColumn, CatalogChange)
]


# ---------------------------------------------------------------- pure drift


def _col(table: str, column: str, data_type: str = "text", ordinal: int = 1) -> ColumnInfo:
    return ColumnInfo(table, column, data_type, ordinal)


def test_first_schema_refresh_is_a_baseline_except_missing_pack_columns() -> None:
    current = {c.key: c for c in [_col("s.t", "a"), _col("s.t", "b", ordinal=2)]}
    refs = {("s.t", "a"): ("Measure x",), ("s.t", "gone"): ("Dimension y",)}
    changes = diff_schema(None, current, references=refs, table_groups={})
    assert [(c.kind, c.column) for c in changes] == [("missing_in_database", "gone")]
    assert changes[0].severity == "high"


def test_new_removed_type_change_and_rename_are_detected() -> None:
    previous = {
        c.key: c
        for c in [
            _col("s.t", "city_name", "text", 1),
            _col("s.t", "amount", "integer", 2),
            _col("s.t", "legacy_flag", "boolean", 9),
        ]
    }
    current = {
        c.key: c
        for c in [
            _col("s.t", "city", "character varying", 1),
            _col("s.t", "amount", "numeric", 2),
            _col("s.t", "discount_pct", "numeric", 5),
        ]
    }
    refs = {("s.t", "city_name"): ("Dimension city",), ("s.t", "amount"): ("Measure revenue",)}
    changes = {c.kind: c for c in diff_schema(previous, current, references=refs, table_groups={})}
    rename = changes["possible_rename"]
    assert rename.detail["from"] == "city_name" and rename.detail["to"] == "city"
    assert rename.detail["autoApplied"] is False
    assert rename.confidence is not None and rename.confidence >= 0.6
    assert changes["type_change"].severity == "high"  # used by a measure
    assert changes["new_column"].column == "discount_pct"
    assert changes["new_column"].detail["suggestedDomain"]["role"] == "measure"
    removed = changes["removed_column"]
    assert removed.column == "legacy_flag" and removed.severity == "low"
    assert removed.impact["Semantic Layer"] == "No action"


def test_removed_referenced_column_is_high_impact() -> None:
    previous = {c.key: c for c in [_col("s.t", "region_id", "integer", 1)]}
    changes = diff_schema(
        previous,
        {c.key: c for c in [_col("s.t", "other", "integer", 1)]},  # keep schema visible
        references={("s.t", "region_id"): ("Join key t.region_id",)},
        table_groups={},
    )
    kinds = {c.kind for c in changes}
    # Same type, same position but unrelated name: may pair as a rename, never silently.
    assert kinds & {"removed_column", "possible_rename"}
    for change in changes:
        if change.kind in {"removed_column", "possible_rename"}:
            assert change.impact["SQL Generation"] == "High"


def test_rename_confidence_uses_value_overlap_when_available() -> None:
    old, new = _col("s.t", "cust_city", "text", 3), _col("s.t", "customer_town", "text", 7)
    without = rename_confidence(old, new)
    with_values = rename_confidence(
        old, new, removed_values={"Pune", "Delhi"}, added_values={"Pune", "Delhi"}
    )
    assert with_values > without


def test_value_growth_and_new_values() -> None:
    changes = diff_values(
        "city", "City", previous_distinct=50, current_distinct=75, new_values=["Surat", "Nagpur"]
    )
    growth = next(c for c in changes if c.kind == "distinct_growth")
    assert growth.summary == "City: 50 \u2192 75 (25 new)"
    fresh = next(c for c in changes if c.kind == "new_values")
    assert fresh.impact == {
        "AI Chat": "Low",
        "Knowledge Graph": "Medium",
        "Glossary": "Review recommended",
    }


# ------------------------------------------------------------------ readiness


def test_new_brand_without_synonyms_needs_review() -> None:
    result = assess_value(
        "BYD",
        domain_key="make",
        domain_ai_known=True,
        in_dictionary=True,
        is_new=True,
        phrases={"exact": ["byd"]},
    )
    assert result.status == "needs_review"
    assert "No synonyms configured" in result.notes


@pytest.mark.parametrize(
    ("kwargs", "expected"),
    [
        ({"domain_ai_known": False}, "needs_review"),
        ({"in_dictionary": False}, "needs_review"),
        ({"shadowed_by": "Make"}, "low_confidence"),
        ({"ambiguous_with": ["City"]}, "low_confidence"),
        ({"generic_word": True}, "low_confidence"),
        ({}, "missing_synonyms"),
        ({"phrases": {"alias": ["vitara"]}}, "ai_ready"),
    ],
)
def test_readiness_rules(kwargs: dict[str, Any], expected: str) -> None:
    params: dict[str, Any] = {
        "domain_key": "model",
        "domain_ai_known": True,
        "in_dictionary": True,
        "is_new": False,
        "phrases": {},
    }
    params.update(kwargs)
    assert assess_value("Grand Vitara", **params).status == expected


# -------------------------------------------------------------------- config


def test_automotive_config_tracks_value_domains_and_watched_columns(settings: Settings) -> None:
    import asyncio

    pack = asyncio.run(SemanticService(settings).get_pack(Industry.AUTOMOTIVE))
    config = build_catalog_config(Industry.AUTOMOTIVE, pack)
    make = config.domain("make")
    assert make is not None and make.ai_known and make.group == "Vehicle"
    dealer = config.domain("dealer_name")
    assert dealer is not None and not dealer.ai_known and dealer.group == "Dealer"
    assert config.fact_tables
    assert (make.table, make.column) in config.references


# ------------------------------------------------------------------- service


@pytest.fixture
async def catalog_session() -> AsyncIterator[AsyncSession]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
    async with engine.begin() as connection:
        await connection.run_sync(
            lambda sync: CatalogRefresh.metadata.create_all(sync, tables=CATALOG_TABLES)
        )
    factory = async_sessionmaker(engine, expire_on_commit=False, autoflush=False)
    async with factory() as session:
        yield session
    await engine.dispose()


@pytest.fixture(autouse=True)
def _reset_catalog_state() -> None:
    invalidate_value_dictionary()
    catalog_service._LOOKUPS.clear()


class FakeWarehouse:
    """Plays the analytics side: schema columns plus distinct values per domain."""

    def __init__(self, config: CatalogConfig) -> None:
        self.columns = {
            key: ColumnInfo(key[0], key[1], "text", index)
            for index, key in enumerate(sorted(config.references))
        }
        self.values: dict[str, list[tuple[str, int]]] = {
            domain.key: [(f"{domain.key}-{i}", 100 - i) for i in range(3)]
            for domain in config.domains
        }
        self.values["make"] = [("Maruti Suzuki", 500), ("Tata", 300), ("Hyundai", 200)]
        self.fail = False

    async def observe(
        self, connection: object, config: CatalogConfig, *, include_schema: bool = True
    ) -> CatalogObservation:
        if self.fail:
            raise ConnectionError("connection refused")
        return CatalogObservation(
            columns=dict(self.columns) if include_schema else None,
            domains={
                key: DomainObservation(list(values), len(values))
                for key, values in self.values.items()
            },
            fact_rows=dict.fromkeys(config.fact_tables, 1000),
        )


async def _service(
    session: AsyncSession, settings: Settings, warehouse: FakeWarehouse | None = None, **kw: Any
) -> EntityCatalogService:
    return EntityCatalogService(
        session,
        SemanticService(settings),
        Industry.AUTOMOTIVE,
        analytics=object(),  # type: ignore[arg-type]
        observer=warehouse.observe if warehouse else catalog_service.observe,
        **kw,
    )


async def _config(settings: Settings) -> CatalogConfig:
    pack = await SemanticService(settings).get_pack(Industry.AUTOMOTIVE)
    return build_catalog_config(Industry.AUTOMOTIVE, pack)


async def test_refresh_detects_new_brand_and_feeds_ai_chat(
    catalog_session: AsyncSession, settings: Settings
) -> None:
    warehouse = FakeWarehouse(await _config(settings))
    service = await _service(catalog_session, settings, warehouse)

    first = await service.refresh(trigger="startup", load_id="load-1")
    assert first.status == "completed" and first.version == 1
    assert first.new_value_count == 0  # baseline
    assert first.rows_processed and first.rows_processed > 0

    unchanged = await service.refresh(load_id="load-2")
    assert unchanged.version == 1  # nothing changed, version holds

    warehouse.values["make"].append(("VinFast", 40))
    warehouse.columns[("automotive.dim_carline", "launch_year")] = ColumnInfo(
        "automotive.dim_carline", "launch_year", "integer", 99
    )
    third = await service.refresh(trigger="data_load", load_id="load-3")
    assert third.version == 2 and third.new_value_count == 1

    kinds = {c.kind for c in await service.changes()}
    assert {"new_values", "distinct_growth", "new_column"} <= kinds

    make = (await service.entity_views(domain_key="make"))[0]
    byd = next(v for v in make.values if v.value == "VinFast")
    assert byd.is_new and byd.first_seen_load == "load-3"
    assert byd.readiness.status == "needs_review"
    assert "No synonyms configured" in byd.readiness.notes

    snapshot = cached_value_dictionary(Industry.AUTOMOTIVE)
    assert snapshot is not None
    assert any(v.value == "VinFast" for v in snapshot.values)
    assert snapshot.resolve("VinFast sales last year").filters()

    summary = await service.summary()
    assert summary["catalogVersion"] == 2
    assert summary["lastLoadId"] == "load-3"
    assert summary["newValues"] == 1
    assert summary["schemaDrift"]["status"] == "changes_detected"
    assert 0 < summary["aiCoverage"] <= 1


async def test_new_badge_expires_after_seven_days(
    catalog_session: AsyncSession, settings: Settings
) -> None:
    warehouse = FakeWarehouse(await _config(settings))
    now = datetime(2026, 9, 1, tzinfo=UTC)
    service = await _service(catalog_session, settings, warehouse, clock=lambda: now)
    await service.refresh()
    warehouse.values["make"].append(("VinFast", 40))
    await service.refresh()
    later = await _service(
        catalog_session, settings, warehouse, clock=lambda: now + timedelta(days=8)
    )
    make = (await later.entity_views(domain_key="make"))[0]
    assert not next(v for v in make.values if v.value == "VinFast").is_new


async def test_failed_refresh_keeps_previous_figures(
    catalog_session: AsyncSession, settings: Settings
) -> None:
    warehouse = FakeWarehouse(await _config(settings))
    service = await _service(catalog_session, settings, warehouse)
    good = await service.refresh()
    warehouse.fail = True
    failed = await service.refresh()
    assert failed.status == "failed"
    assert failed.error and "previous catalog" in failed.error
    assert "refused" not in failed.error  # no technical detail
    assert failed.rows_processed == good.rows_processed
    summary = await service.summary()
    assert summary["lastRefresh"]["status"] == "failed"
    assert summary["catalogVersion"] == good.version


async def test_refresh_without_warehouse_fails_softly(
    catalog_session: AsyncSession, settings: Settings
) -> None:
    service = EntityCatalogService(catalog_session, SemanticService(settings), Industry.AUTOMOTIVE)
    run = await service.refresh()
    assert run.status == "failed"
    assert "could not be reached" in (run.error or "")


async def test_removed_referenced_column_requires_action(
    catalog_session: AsyncSession, settings: Settings
) -> None:
    warehouse = FakeWarehouse(await _config(settings))
    service = await _service(catalog_session, settings, warehouse)
    await service.refresh()
    assert (await service.summary())["schemaDrift"]["status"] == "stable"
    removed_key = ("automotive.dim_carline", "engine_type")
    warehouse.columns.pop(removed_key)
    await service.refresh()
    change = next(
        c for c in await service.changes() if (c.table_name, c.column_name) == removed_key
    )
    assert change.kind in {"removed_column", "possible_rename"}
    assert change.severity == "high"
    assert (await service.summary())["schemaDrift"]["status"] == "action_required"


async def test_targeted_lookup_adds_unknown_value_once(
    catalog_session: AsyncSession, settings: Settings
) -> None:
    warehouse = FakeWarehouse(await _config(settings))
    calls: list[list[str]] = []

    async def lookup(connection: object, config: CatalogConfig, terms: list[str]) -> list[Any]:
        calls.append(list(terms))
        return [("model", "Seal", 12)] if "seal" in terms else []

    service = await _service(catalog_session, settings, warehouse, lookup=lookup)
    await service.refresh()
    found = await service.targeted_lookup(["Seal"])
    assert found == [("model", "Seal")]
    snapshot = cached_value_dictionary(Industry.AUTOMOTIVE)
    assert snapshot is not None and any(v.value == "Seal" for v in snapshot.values)
    changes = await service.changes()
    assert any(c.detail.get("trigger") == "unknown_entity" for c in changes)

    assert await service.targeted_lookup(["seal"]) == []  # throttled
    assert len(calls) == 1


async def test_semantic_cache_rebuild_needs_no_warehouse(
    catalog_session: AsyncSession, settings: Settings
) -> None:
    warehouse = FakeWarehouse(await _config(settings))
    service = await _service(catalog_session, settings, warehouse)
    await service.refresh()
    offline = EntityCatalogService(catalog_session, SemanticService(settings), Industry.AUTOMOTIVE)
    run = await offline.refresh(scope="semantic_cache")
    assert run.status == "completed"
    snapshot = cached_value_dictionary(Industry.AUTOMOTIVE)
    assert snapshot is not None and any(v.value == "Tata" for v in snapshot.values)
