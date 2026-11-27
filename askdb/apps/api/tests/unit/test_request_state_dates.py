"""Date boundaries, persisted scope and scoped catalog reuse for the Batch 2 bridge."""

import json
import uuid
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.config import Industry, Settings
from app.core.exceptions import AuthorizationError
from app.schemas.semantic import SemanticQueryPolicy
from app.semantic.service import SemanticService
from app.services.chat.conversation_memory import SessionMemory, empty_memory
from app.services.chat.request_context import (
    RequestPrincipal,
    build_request_context,
)
from app.services.chat.request_contract import (
    InterpretedRequest,
    RequestedComparison,
    RequestedPeriod,
)
from app.services.chat.request_dates import comparison_ranges, resolve_period
from app.services.chat.request_runtime import _CATALOGS, scoped_catalog
from app.services.chat.request_state import merge_proposal, previous_request, save_request
from app.services.chat.value_dictionary import ValueDictionarySnapshot
from app.services.security.region_scope import RegionScope, for_current_scope


def req(**kwargs):
    return InterpretedRequest.model_validate_json(
        json.dumps(
            {
                "outcome": "analytics",
                "summary": "Revenue and units by model",
                "measures": [{"id": "revenue"}, {"id": "units_sold"}],
                "group_by": ["dim_carline.model"],
                "period": {"label": "2026", "relative": "this_year"},
                **kwargs,
            }
        )
    )


@pytest.fixture
def context():
    principal = RequestPrincipal(uuid.uuid4(), RegionScope.all_regions(), Industry.AUTOMOTIVE)
    pack = SemanticService(Settings(_env_file=None))._load_pack(Industry.AUTOMOTIVE)
    return (
        pack,
        principal,
        build_request_context("revenue units model Toyota Tata", pack=pack, principal=principal),
    )


@pytest.mark.parametrize(
    "relative,start,end",
    [
        ("last_month", date(2026, 10, 1), date(2026, 11, 1)),
        ("last_quarter", date(2026, 7, 1), date(2026, 10, 1)),
        ("this_year", date(2026, 1, 1), date(2026, 11, 27)),
        ("fytd", date(2026, 4, 1), date(2026, 11, 27)),
        ("last_n_months", date(2026, 9, 1), date(2026, 11, 27)),
    ],
)
def test_relative_dates_use_business_calendar_not_data_max(relative, start, end):
    period = RequestedPeriod(
        label=relative, relative=relative, count=3 if relative.startswith("last_n_") else None
    )
    resolved = resolve_period(
        period,
        date(2026, 11, 26),
        SemanticQueryPolicy(
            utc_offset_minutes=330,
            fiscal_year_start_month=4,
            comparison_alignment="same_elapsed",
            undated_ranking="available_history",
            undated_aggregation="clarify",
        ),
    )
    assert (resolved.start, resolved.end) == (start, end)


@pytest.mark.parametrize(
    "alignment,end", [("full_period", date(2026, 10, 1)), ("same_elapsed", date(2026, 8, 27))]
)
def test_previous_quarter_full_and_partial_alignment(alignment, end):
    current, baseline = comparison_ranges(
        RequestedComparison(
            kind="period", baseline_reference="previous_period", alignment=alignment
        ),
        RequestedPeriod(label="QTD", relative="this_quarter"),
        date(2026, 11, 26),
        SemanticQueryPolicy(
            utc_offset_minutes=330,
            fiscal_year_start_month=4,
            comparison_alignment="same_elapsed",
            undated_ranking="available_history",
            undated_aggregation="clarify",
        ),
    )
    assert current.partial and current.end == date(2026, 11, 27)
    assert baseline.start == date(2026, 7, 1) and baseline.end == end


@pytest.mark.parametrize(
    "today,end", [(date(2024, 2, 29), date(2023, 3, 1)), (date(2025, 2, 28), date(2024, 2, 29))]
)
def test_last_year_corresponds_to_inclusive_calendar_date(today, end):
    _, baseline = comparison_ranges(
        RequestedComparison(kind="period", baseline_reference="same_period_last_year"),
        RequestedPeriod(label="YTD", relative="ytd"),
        today,
        SemanticQueryPolicy(
            utc_offset_minutes=330,
            fiscal_year_start_month=4,
            comparison_alignment="same_elapsed",
            undated_ranking="available_history",
            undated_aggregation="clarify",
        ),
    )
    assert baseline.end == end


def test_explicit_period_and_stale_data_are_separate(context):
    pack, principal, _ = context
    ctx = build_request_context(
        "revenue this year",
        pack=pack,
        principal=principal,
        current_date=date(2026, 11, 26),
        data_as_of=date(2025, 8, 31),
    )
    assert (
        ctx.payload["calendar_date"] == "2026-11-26" and ctx.payload["data_as_of"] == "2025-08-31"
    )
    assert ctx.payload["query_policy"]["utc_offset_minutes"] == 330


def test_date_patch_only_changes_period_and_never_mutates_old_state():
    old = req(
        filters=[{"field": "dim_carline.make", "operator": "in", "entity_ids": ["toyota"]}]
    ).model_dump(mode="json")
    snapshot = json.dumps(old)
    updated = merge_proposal(
        json.dumps(
            {
                "outcome": "analytics",
                "summary": "Last quarter",
                "followup": True,
                "changed_fields": ["period"],
                "period": {"label": "Q3", "relative": "last_quarter"},
                "measures": [{"id": "orders"}],
            }
        ),
        {"request": old},
    )
    assert updated.measures == req().measures and updated.filters[0].entity_ids == ["toyota"]
    assert updated.group_by == ["dim_carline.model"] and updated.period.relative == "last_quarter"
    assert json.dumps(old) == snapshot


def test_region_patch_preserves_exclusions_and_other_scope():
    old = req(
        filters=[
            {"field": "dim_carline.make", "operator": "ne", "entity_ids": ["tata"]},
            {"field": "dim_region.region_name", "operator": "eq", "entity_ids": ["north"]},
        ]
    )
    updated = merge_proposal(
        json.dumps(
            {
                "outcome": "analytics",
                "summary": "Now West",
                "followup": True,
                "changed_fields": ["filters"],
                "filters": [
                    {"field": "dim_region.region_name", "operator": "eq", "entity_ids": ["west"]}
                ],
            }
        ),
        {"request": old.model_dump(mode="json")},
    )
    assert updated.filters[0].operator == "ne" and updated.filters[0].entity_ids == ["tata"]
    assert (
        updated.filters[1].entity_ids == ["west"]
        and updated.measures == old.measures
        and updated.period == old.period
    )


def test_changing_member_filter_removes_stale_comparison():
    old = req(comparisons=[{"kind": "members", "member_ids": ["a", "b"]}])
    updated = merge_proposal(
        json.dumps(
            {
                "outcome": "analytics",
                "summary": "Only C",
                "followup": True,
                "changed_fields": ["filters"],
                "filters": [{"field": "dim_carline.model", "operator": "eq", "entity_ids": ["c"]}],
            }
        ),
        {"request": old.model_dump(mode="json")},
        entity_fields={
            "a": "dim_carline.model",
            "b": "dim_carline.model",
            "c": "dim_carline.model",
        },
    )
    assert updated.comparisons == [] and updated.filters[0].entity_ids == ["c"]


def test_new_topic_never_inherits_previous_measures():
    updated = merge_proposal(
        json.dumps(
            {
                "outcome": "definition",
                "summary": "Revenue definition",
                "definition_terms": ["revenue"],
            }
        ),
        {"request": req().model_dump(mode="json")},
    )
    assert updated.measures == [] and updated.period is None


def test_unrelated_followup_preserves_both_ends_of_filter_ranges():
    old = req(
        filters=[
            {"field": "dim_carline.engine_capacity", "operator": "gte", "values": [1000]},
            {"field": "dim_carline.engine_capacity", "operator": "lte", "values": [2000]},
        ],
        measure_filters=[
            {"measure_id": "revenue", "operator": "gt", "value": 10},
            {"measure_id": "revenue", "operator": "lt", "value": 10000},
        ],
    )
    updated = merge_proposal(
        json.dumps(
            {
                "outcome": "analytics",
                "summary": "Only West",
                "followup": True,
                "changed_fields": ["filters"],
                "filters": [
                    {"field": "dim_region.region_name", "operator": "eq", "entity_ids": ["west"]}
                ],
            }
        ),
        {"request": old.model_dump(mode="json")},
    )
    assert [f.operator for f in updated.filters[:2]] == ["gte", "lte"]
    assert updated.measure_filters == old.measure_filters


def test_json_memory_roundtrip_preserves_owner_and_complete_request(context):
    _, principal, ctx = context
    memory = empty_memory(user_id=principal.user_id, conversation_id=uuid.uuid4())
    memory.typed_request = save_request(None, req(), ctx, "run-1", pending=False, sql="SELECT 1")
    restored = SessionMemory.from_dict(json.loads(json.dumps(memory.to_dict())))
    previous = previous_request(
        restored.typed_request, principal, ctx.semantic_version, ttl_seconds=3600
    )
    assert previous.request == req()
    assert restored.typed_request["confirmed"]["sql"] == "SELECT 1"


@pytest.mark.parametrize("change", ["owner", "scope", "version", "expired", "turns"])
def test_old_state_cannot_survive_scope_version_or_lifetime_changes(context, change):
    _, principal, ctx = context
    state = save_request(None, req(), ctx, "run-1", pending=False)
    version = ctx.semantic_version
    if change == "owner":
        principal = replace(principal, user_id=uuid.uuid4())
    if change == "scope":
        principal = replace(
            principal,
            scope=RegionScope(
                unrestricted=False, zones=("West",), user_id=principal.user_id, username="test"
            ),
        )
    if change == "version":
        version = "changed"
    if change == "expired":
        state["confirmed"]["updated_at"] = (datetime.now(UTC) - timedelta(hours=2)).isoformat()
    if change == "turns":
        state["confirmed"]["turn_count"] = 8
    if change in {"owner", "scope", "version"}:
        with pytest.raises(AuthorizationError):
            previous_request(state, principal, version, ttl_seconds=3600)
    else:
        assert previous_request(state, principal, version, ttl_seconds=3600) is None


@pytest.mark.asyncio
async def test_catalog_cache_is_partitioned_by_user_scope_and_pack(context):
    pack, principal, _ = context
    connection = AsyncMock()
    result = MagicMock()
    result.__iter__.return_value = iter([])
    result.scalar.return_value = date(2026, 11, 20)
    connection.execute.return_value = result
    snapshot = ValueDictionarySnapshot(Industry.AUTOMOTIVE, ())
    _CATALOGS.clear()
    with patch(
        "app.services.chat.request_runtime.load_value_dictionary", AsyncMock(return_value=snapshot)
    ) as load:
        await scoped_catalog(connection, pack, principal)
        await scoped_catalog(connection, pack, principal)
        assert load.await_count == 1
        await scoped_catalog(connection, pack, replace(principal, user_id=uuid.uuid4()))
        assert load.await_count == 2
        west = replace(
            principal,
            scope=RegionScope(
                unrestricted=False, zones=("West",), user_id=principal.user_id, username="test"
            ),
        )
        await scoped_catalog(connection, pack, west)
        assert load.await_count == 3
        pack.model.description += " Updated"
        await scoped_catalog(connection, pack, west)
        assert load.await_count == 4
    assert any("/*rls*/" in str(call.args[0]) for call in connection.execute.await_args_list)
    _CATALOGS.clear()


@pytest.mark.asyncio
async def test_fresh_scope_replaces_wrapper_instead_of_nesting(context):
    _, principal, _ = context
    connection = AsyncMock()
    old = RegionScope(
        unrestricted=False, zones=("North",), user_id=principal.user_id, username="test"
    )
    new = RegionScope(
        unrestricted=False, zones=("West",), user_id=principal.user_id, username="test"
    )
    scoped = for_current_scope(
        for_current_scope(connection, Industry.AUTOMOTIVE, old), Industry.AUTOMOTIVE, new
    )
    await scoped.execute("SELECT * FROM automotive.fact_sales f")
    sql = str(connection.execute.await_args.args[0])
    assert sql == new.apply_sql("SELECT * FROM automotive.fact_sales f", Industry.AUTOMOTIVE)
    assert sql.count("/*rls*/") == 1
