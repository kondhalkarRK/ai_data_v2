"""Reference-result acceptance using SQLite + SQLGlot dialect adaptation, not PostgreSQL.

Expected values are independently calculated from fixture rows. Office PostgreSQL
acceptance is still required; no live provider or warehouse is used here.
"""

import json
import math
import sqlite3
import uuid
from datetime import date

import pytest
import sqlglot
from sqlglot import exp

from app.core.config import Industry, Settings
from app.semantic.service import SemanticService
from app.services.chat.request_compiler import (
    TypedCompileError,
    compile_request,
    measure_capabilities,
)
from app.services.chat.request_context import RequestPrincipal, ScopedCatalog, build_request_context
from app.services.chat.request_contract import InterpretedRequest
from app.services.chat.request_dates import (
    RequestClarificationError,
)
from app.services.chat.value_dictionary import BusinessValue, ValueDictionarySnapshot
from app.services.security.region_scope import RegionScope

FACTS = [
    (1, 1, 1, 1, "2026-01-05", 10, 1000.0),
    (2, 2, 2, 2, "2026-01-10", 20, 4000.0),
    (3, 1, 1, 1, "2026-02-05", 5, 1000.0),
    (4, 1, 1, 1, "2026-04-05", 15, 3000.0),
    (5, 1, 1, 1, "2026-07-05", 30, 3000.0),
    (6, 2, 2, 2, "2026-08-05", 10, 2000.0),
    (7, 1, 1, 1, "2026-10-05", 40, 5000.0),
    (8, 2, 2, 2, "2026-11-05", 15, 3000.0),
    (9, 1, 1, 1, "2025-12-05", 4, 400.0),
    (10, 2, 2, 2, "2026-03-05", 0, 0.0),
    (11, 1, 1, 1, "2026-01-20", 6, 600.0),
]


@pytest.fixture
def fixture():
    pack = SemanticService(Settings(_env_file=None))._load_pack(Industry.AUTOMOTIVE)
    principal = RequestPrincipal(uuid.uuid4(), RegionScope.all_regions(), Industry.AUTOMOTIVE)
    entries = tuple(
        BusinessValue(domain, "automotive." + field, value)
        for domain, field, value in [
            ("Make", "dim_carline.make", "Toyota"),
            ("Make", "dim_carline.make", "Tata"),
            ("Model", "dim_carline.model", "A"),
            ("Model", "dim_carline.model", "B"),
            ("Model", "dim_carline.model", "C"),
            ("Region", "dim_region.region_name", "West"),
            ("Region", "dim_region.region_name", "South"),
        ]
    )
    catalog = ScopedCatalog(
        principal.binding, ValueDictionarySnapshot(Industry.AUTOMOTIVE, entries)
    )
    context = build_request_context(
        "Toyota Tata A B C West South revenue units orders ASP active salespeople targets",
        pack=pack,
        principal=principal,
        catalog=catalog,
        max_chars=16000,
    )
    db = sqlite3.connect(":memory:")
    db.row_factory = sqlite3.Row
    db.execute("ATTACH DATABASE ':memory:' AS automotive")
    for name, table in pack.model.tables.items():
        columns = [
            f"{key} "
            + (
                "REAL"
                if spec.type == "decimal"
                else "TEXT"
                if spec.type in {"string", "date"}
                else "INTEGER"
            )
            + (" PRIMARY KEY" if key == table.primary_key else "")
            for key, spec in table.columns.items()
        ]
        db.execute(f"CREATE TABLE automotive.{name} ({', '.join(columns)})")
    db.executemany(
        "INSERT INTO automotive.dim_carline(carline_id,make,model) VALUES (?,?,?)",
        [(1, "Toyota", "A"), (2, "Tata", "B"), (3, "Toyota", "C")],
    )
    db.executemany(
        "INSERT INTO automotive.dim_region(region_id,region_name,state_code) VALUES (?,?,?)",
        [(1, "West", "MH"), (2, "South", "TN")],
    )
    db.executemany(
        "INSERT INTO automotive.dim_dealer(dealer_id,dealer_name,region_id) VALUES (?,?,?)",
        [(1, "D1", 1), (2, "D2", 2)],
    )
    db.executemany(
        "INSERT INTO automotive.fact_sales(order_id,carline_id,region_id,dealer_id,"
        "sales_date,order_qty,total_sales) VALUES (?,?,?,?,?,?,?)",
        FACTS,
    )
    db.executemany(
        "INSERT INTO automotive.dim_targets(target_id,make,year_month,target_units,"
        "target_revenue) VALUES (?,?,?,?,?)",
        [(1, "Toyota", "2026-01-01", 100, 10000), (2, "Tata", "2026-01-01", 200, 30000)],
    )
    db.executemany(
        "INSERT INTO automotive.dim_salesman(sales_person_id,first_name,last_name,active) "
        "VALUES (?,?,?,?)",
        [(1, "Asha", "Patel", True), (2, "Ravi", "Rao", False)],
    )
    db.execute("UPDATE automotive.fact_sales SET sales_person_id=carline_id")
    db.create_function("FLOOR", 1, math.floor)

    def truncate(unit, value):
        parsed = date.fromisoformat(value[:10])
        if unit == "month":
            return parsed.replace(day=1).isoformat()
        if unit == "quarter":
            return date(parsed.year, ((parsed.month - 1) // 3) * 3 + 1, 1).isoformat()
        if unit == "year":
            return date(parsed.year, 1, 1).isoformat()
        return parsed.isoformat()

    db.create_function("DATE_TRUNC", 2, truncate)
    yield pack, principal, context, db
    db.close()


def request(**kwargs):
    return InterpretedRequest.model_validate_json(
        json.dumps(
            {
                "outcome": "analytics",
                "summary": "Fixture analysis",
                "measures": [{"id": "revenue"}],
                "period": {"label": "2026", "start": "2026-01-01", "end_exclusive": "2027-01-01"},
                **kwargs,
            }
        )
    )


def run(fixture, req, cap=200):
    pack, principal, context, db = fixture
    compiled = compile_request(
        req,
        pack=pack,
        principal=principal,
        context=context,
        today=date(2026, 11, 26),
        row_limit=cap,
    )

    def adapt(node):
        if isinstance(node, exp.Extract):
            unit = node.this.name.lower()
            fmt = {"year": "%Y", "month": "%m", "epoch": "%s"}[unit]
            return exp.Cast(
                this=exp.Anonymous(
                    this="STRFTIME", expressions=[exp.Literal.string(fmt), node.expression.copy()]
                ),
                to=exp.DataType.build("INT"),
            )
        if isinstance(node, exp.TimestampTrunc):
            return exp.Anonymous(
                this="DATE_TRUNC",
                expressions=[exp.Literal.string(node.args["unit"].name.lower()), node.this.copy()],
            )
        return node

    sqlite_sql = (
        sqlglot.parse_one(compiled.sql, read="postgres").transform(adapt).sql(dialect="sqlite")
    )
    return compiled, [dict(row) for row in db.execute(sqlite_sql)]


def test_multiple_totals_and_weighted_asp_match_reference(fixture):
    _, rows = run(
        fixture,
        request(
            measures=[
                {"id": m} for m in ["revenue", "units_sold", "orders", "average_selling_price"]
            ]
        ),
    )
    source = [f for f in FACTS if f[4].startswith("2026")]
    assert rows[0]["revenue"] == sum(f[6] for f in source)
    assert rows[0]["units_sold"] == sum(f[5] for f in source)
    assert rows[0]["orders"] == len({f[0] for f in source})
    assert rows[0]["average_selling_price"] == pytest.approx(
        sum(f[6] for f in source) / sum(f[5] for f in source)
    )
    assert rows[0]["__selected_fact_sales_start"] == "2026-01-05"
    assert rows[0]["__selected_fact_sales_through"] == "2026-11-05"


def test_multiple_joins_and_groupings_do_not_duplicate_totals(fixture):
    compiled, rows = run(
        fixture,
        request(group_by=["dim_dealer.dealer_name", "dim_region.region_name", "dim_carline.model"]),
    )
    assert sum(r["revenue"] for r in rows) == sum(f[6] for f in FACTS if f[4].startswith("2026"))
    assert compiled.sql.count("dim_carline v ON") == 1
    assert compiled.sql.count("dim_region r ON") == 1


def test_salesperson_counts_names_and_explicit_active_filter(fixture):
    _, rows = run(
        fixture,
        request(
            measures=[{"id": "active_salespeople"}],
            group_by=["dim_salesman.first_name", "dim_salesman.last_name"],
            filters=[{"field": "dim_salesman.active", "operator": "eq", "values": [True]}],
        ),
    )
    assert len(rows) == 1 and rows[0]["first_name"] == "Asha" and rows[0]["last_name"] == "Patel"
    assert rows[0]["active_salespeople"] == 1


def test_asp_zero_denominator_is_unavailable_not_zero(fixture):
    _, rows = run(
        fixture,
        request(
            measures=[{"id": "average_selling_price"}, {"id": "orders"}],
            period={"label": "March", "start": "2026-03-01", "end_exclusive": "2026-04-01"},
        ),
    )
    assert rows[0]["average_selling_price"] is None and rows[0]["orders"] == 1


def test_actual_target_aggregates_separately_before_combining(fixture):
    _, rows = run(
        fixture,
        request(
            measures=[{"id": "revenue"}, {"id": "target_revenue"}],
            group_by=["dim_carline.make"],
            period={"label": "Jan", "start": "2026-01-01", "end_exclusive": "2026-02-01"},
        ),
    )
    assert sum(r["target_revenue"] for r in rows) == 40000
    assert sum(r["revenue"] for r in rows) == 5600


def test_unknown_target_grain_returns_explicit_partial(fixture):
    compiled, rows = run(
        fixture,
        request(
            measures=[{"id": "revenue"}, {"id": "target_revenue"}], group_by=["dim_carline.model"]
        ),
    )
    assert "target_revenue" in compiled.unsupported
    assert all("target_revenue" not in row for row in rows)


def test_period_comparison_preserves_both_aligned_periods(fixture):
    compiled, rows = run(
        fixture,
        request(
            period=None,
            comparisons=[
                {
                    "kind": "period",
                    "current": {"label": "QTD", "relative": "this_quarter"},
                    "baseline": {"label": "Last quarter", "relative": "last_quarter"},
                }
            ],
        ),
    )
    assert rows[0]["current_revenue"] == 8000
    assert rows[0]["baseline_revenue"] == 5000
    assert rows[0]["change_revenue"] == 3000
    assert rows[0]["revenue_change_pct"] == 60
    assert compiled.periods["baseline"].end == date(2026, 8, 27)


def test_window_running_total_and_calendar_moving_average(fixture):
    windows = [
        {
            "operation": "running_total",
            "measure_ids": ["revenue"],
            "order_by": "fact_sales.sales_date",
            "partition_by": ["dim_carline.model"],
            "reset": "calendar_year",
        },
        {
            "operation": "moving_average",
            "measure_ids": ["revenue"],
            "order_by": "fact_sales.sales_date",
            "partition_by": ["dim_carline.model"],
            "size": 3,
        },
    ]
    _, rows = run(
        fixture, request(group_by=["dim_carline.model"], time_grain="month", windows=windows)
    )
    april = next(row for row in rows if row["model"] == "A" and row["month"] == "2026-04")
    assert april["running_total_revenue"] == 5600
    assert april["moving_average_revenue"] == 2000  # Feb + Apr; March absent, not zero.


def test_missing_member_is_null_and_verified_zero_is_zero(fixture):
    context = fixture[2]
    entities = [
        e["id"]
        for e in context.payload["entities"]
        if e["value"] in {"B", "C"} and e["field"] == "dim_carline.model"
    ]
    _, rows = run(
        fixture,
        request(
            comparisons=[{"kind": "members", "member_ids": entities}],
            period={"label": "March", "start": "2026-03-01", "end_exclusive": "2026-04-01"},
        ),
    )
    assert {r["model"]: r["revenue"] for r in rows} == {"B": 0, "C": None}


def test_empty_total_is_not_a_fabricated_zero(fixture):
    _, rows = run(
        fixture,
        request(
            measures=[{"id": "orders"}],
            period={"label": "Future", "start": "2030-01-01", "end_exclusive": "2031-01-01"},
        ),
    )
    assert rows == []


def test_top_per_region_and_verified_group_count(fixture):
    _, rows = run(
        fixture,
        request(
            group_by=["dim_region.region_name", "dim_carline.model"],
            ranking={
                "measure_id": "revenue",
                "limit": 1,
                "partition_by": ["dim_region.region_name"],
            },
        ),
        cap=1,
    )
    assert len(rows) == 1 and rows[0]["__total_groups"] == 2


def test_no_period_requires_focused_detail_except_ranking(fixture):
    with pytest.raises(RequestClarificationError):
        run(fixture, request(period=None))
    compiled, _ = run(fixture, request(period=None, ranking={"measure_id": "revenue", "limit": 5}))
    assert compiled.notes and compiled.periods["selection"].start is None


def test_declared_unsafe_cardinality_is_not_executed(fixture):
    pack = fixture[0]
    pack.model.relationships[0].type = "many_to_many"
    fixture = refresh(fixture)
    with pytest.raises(TypedCompileError, match="cardinality"):
        run(fixture, request(group_by=["dim_carline.model"]))


def test_pack_formula_is_authoritative(fixture):
    pack = fixture[0]
    assert set(measure_capabilities(pack)) == set(pack.model.measures)
    pack.model.measures["revenue"].expression = "SUM(total_sales) * 2"
    with pytest.raises(TypedCompileError, match="metadata changed"):
        run(fixture, request())
    fixture = refresh(fixture)
    _, rows = run(fixture, request())
    assert rows[0]["revenue"] == 2 * sum(f[6] for f in FACTS if f[4].startswith("2026"))


def refresh(fixture):
    pack, principal, old, db = fixture
    values = tuple(
        BusinessValue(e["domain"], "automotive." + e["field"], e["value"])
        for e in old.payload["entities"]
    )
    context = build_request_context(
        "Toyota Tata A B C West South revenue units orders ASP active salespeople targets",
        pack=pack,
        principal=principal,
        catalog=ScopedCatalog(
            principal.binding, ValueDictionarySnapshot(Industry.AUTOMOTIVE, values)
        ),
        max_chars=16000,
    )
    return pack, principal, context, db


def test_actual_target_variance_and_attainment_are_verified(fixture):
    _, rows = run(
        fixture,
        request(
            measures=[{"id": "revenue"}, {"id": "target_revenue"}],
            comparisons=[{"kind": "actual_target"}],
            period={"label": "Jan", "start": "2026-01-01", "end_exclusive": "2026-02-01"},
        ),
    )
    assert rows[0]["revenue"] == 5600 and rows[0]["target_revenue"] == 40000
    assert rows[0]["revenue_target_variance"] == -34400
    assert rows[0]["revenue_attainment_pct"] == 14


def test_target_without_records_keeps_actual_with_null_target(fixture):
    _, rows = run(
        fixture,
        request(
            measures=[{"id": "revenue"}, {"id": "target_revenue"}],
            comparisons=[{"kind": "actual_target"}],
            period={"label": "Oct", "relative": "last_month"},
        ),
    )
    assert rows[0]["revenue"] == 5000 and rows[0]["target_revenue"] is None
    assert rows[0]["revenue_attainment_pct"] is None


def test_exclusions_measure_filter_and_contribution(fixture):
    context = fixture[2]
    make = next(e["id"] for e in context.payload["entities"] if e["value"] == "Toyota")
    _, rows = run(
        fixture,
        request(
            group_by=["dim_carline.model"],
            filters=[{"field": "dim_carline.make", "operator": "ne", "entity_ids": [make]}],
            measure_filters=[{"measure_id": "revenue", "operator": "gt", "value": 0}],
            windows=[
                {
                    "operation": "contribution",
                    "measure_ids": ["revenue"],
                    "order_by": "dim_carline.model",
                }
            ],
        ),
    )
    assert len(rows) == 1 and rows[0]["model"] == "B"
    assert rows[0]["revenue"] == 9000 and rows[0]["contribution_revenue"] == 100


def test_nested_average_is_average_of_grouped_totals(fixture):
    _, rows = run(
        fixture,
        request(
            group_by=["dim_carline.make"],
            operations=[{"operation": "avg", "measure_ids": ["revenue"], "group_by": []}],
        ),
    )
    assert rows[0]["avg_revenue"] == 11300


def test_post_aggregation_does_not_drop_other_measures(fixture):
    with pytest.raises(TypedCompileError, match="every requested measure"):
        run(
            fixture,
            request(
                measures=[{"id": "revenue"}, {"id": "units_sold"}],
                group_by=["dim_carline.make"],
                operations=[{"operation": "avg", "measure_ids": ["revenue"]}],
            ),
        )


@pytest.mark.parametrize(
    "bad",
    [
        "SUM(total_sales); SELECT 1",
        "pg_sleep(1)",
        "SUM(secret_column)",
        "(SELECT SUM(total_sales) FROM other_table)",
    ],
)
def test_unexecutable_formula_returns_verified_partial_not_invented_values(fixture, bad):
    fixture[0].model.measures["revenue"].expression = bad
    fixture = refresh(fixture)
    compiled, rows = run(fixture, request(measures=[{"id": "revenue"}, {"id": "units_sold"}]))
    assert "revenue" in compiled.unsupported and "revenue" not in rows[0]
    assert rows[0]["units_sold"] == 151


def test_growth_does_not_skip_missing_calendar_month(fixture):
    _, rows = run(
        fixture,
        request(
            group_by=["dim_carline.model"],
            time_grain="month",
            windows=[
                {
                    "operation": "period_growth",
                    "measure_ids": ["revenue"],
                    "order_by": "fact_sales.sales_date",
                }
            ],
        ),
    )
    by_month = {r["month"]: r for r in rows if r["model"] == "A"}
    assert by_month["2026-02"]["period_growth_revenue"] == pytest.approx(-37.5)
    assert by_month["2026-04"]["period_growth_revenue"] is None


def test_running_total_resets_at_fiscal_year_boundary(fixture):
    _, rows = run(
        fixture,
        request(
            group_by=["dim_carline.model"],
            time_grain="month",
            windows=[
                {
                    "operation": "running_total",
                    "measure_ids": ["revenue"],
                    "order_by": "fact_sales.sales_date",
                    "reset": "fiscal_year",
                }
            ],
        ),
    )
    april = next(r for r in rows if r["month"] == "2026-04" and r["model"] == "A")
    assert april["running_total_revenue"] == 3000


@pytest.mark.parametrize("baseline,expected", [(0, None), (-100, 200)])
def test_zero_and_negative_baseline_percentages(fixture, baseline, expected):
    fixture[3].execute(
        "UPDATE automotive.fact_sales SET total_sales=? WHERE order_id=9", (baseline,)
    )
    fixture[3].execute("UPDATE automotive.fact_sales SET total_sales=100 WHERE order_id=1")
    _, rows = run(
        fixture,
        request(
            period={"label": "Jan5", "start": "2026-01-05", "end_exclusive": "2026-01-06"},
            comparisons=[
                {
                    "kind": "period",
                    "baseline": {
                        "label": "Dec5",
                        "start": "2025-12-05",
                        "end_exclusive": "2025-12-06",
                    },
                }
            ],
        ),
    )
    assert rows[0]["revenue_change_pct"] == expected


def test_best_and_worst_preserve_all_ties(fixture):
    fixture[3].execute(
        "UPDATE automotive.fact_sales SET total_sales=total_sales+4600 WHERE order_id=2"
    )
    _, rows = run(
        fixture,
        request(
            group_by=["dim_carline.make"],
            ranking={"measure_id": "revenue", "include_both_ends": True, "ties": "include"},
        ),
    )
    assert len(rows) == 2 and {r["revenue"] for r in rows} == {13600}


def test_unsafe_dealer_region_special_path_is_blocked(fixture):
    rel = next(r for r in fixture[0].model.relationships if r.name == "dealer_to_region")
    rel.type = "many_to_many"
    with pytest.raises(TypedCompileError, match="cardinality"):
        run(
            refresh(fixture), request(group_by=["dim_dealer.dealer_name", "dim_region.region_name"])
        )


def test_legacy_metric_formulas_do_not_silently_drift_from_pack(fixture):
    from app.services.chat.question_understanding import QuestionPlan
    from app.services.chat.semantic_analytics import _metric_spec

    pack = fixture[0]
    for legacy, semantic in [
        ("revenue", "revenue"),
        ("units", "units_sold"),
        ("orders", "orders"),
        ("average_selling_price", "average_selling_price"),
        ("active_salespeople", "active_salespeople"),
    ]:
        spec = _metric_spec(
            QuestionPlan(
                industry=Industry.AUTOMOTIVE,
                metric=legacy,
                intent="aggregation",
                entity="metric_only",
            )
        )
        normalized = sqlglot.parse_one(spec.expression.format(alias="fact_sales"), read="postgres")
        for column in normalized.find_all(exp.Column):
            column.set("table", None)
        assert (
            normalized.sql()
            == sqlglot.parse_one(pack.model.measures[semantic].expression, read="postgres").sql()
        )


def test_investigation_reconciles_capped_groups_and_missing_side(fixture):
    from app.services.chat.request_evidence import render

    req = request(
        group_by=["dim_region.region_name"],
        period={"label": "QTD", "relative": "this_quarter"},
        comparisons=[{"kind": "period", "baseline_reference": "previous_period"}],
    )
    _, rows = run(fixture, req, cap=1)
    text = render(req, fixture[0], rows, rows[0], investigation=True, total=2)
    assert "Contributing factors" in text and "Other / remaining groups" in text
    assert "reconcile" in text and "proof of causation" in text
    missing = dict(rows[0], __missing_revenue=1)
    assert "unverified" in render(req, fixture[0], rows, missing, investigation=True)


def test_report_plan_preserves_typed_scope_without_model(fixture):
    from app.services.analytics.catalog import Catalog
    from app.services.chat.request_report import report_plan
    from app.services.analytics.bi.planning import validate

    pack, principal, context, _ = fixture
    req = request(outcome="report", measures=[{"id": "revenue"}, {"id": "units_sold"}])
    catalog = Catalog(Industry.AUTOMOTIVE, pack)
    plan = report_plan(req, pack, context, catalog, date(2026, 11, 26))
    validate(plan, catalog, principal.scope)
    assert len(plan.panels) == 6
    assert sum(panel.kind == "kpi" for panel in plan.panels) == 2
    assert all(
        panel.spec.date_from == "2026-01-01" and panel.spec.date_to == "2026-12-31"
        for panel in plan.panels
    )
    previous = plan.model_copy(deep=True)
    previous.panels[-1].title = "My retained choice"
    updated = report_plan(req, pack, context, catalog, date(2026, 11, 26), previous)
    assert updated.panels[-1].title == "My retained choice"


@pytest.mark.parametrize(
    "basis,model", [("absolute_change", "B"), ("percent_change", "A"), ("unspecified", "B")]
)
def test_independent_decline_order_differs_for_amount_and_percentage(fixture, basis, model):
    db = fixture[3]
    db.execute("DELETE FROM automotive.fact_sales")
    db.executemany(
        "INSERT INTO automotive.fact_sales(order_id,carline_id,sales_date,order_qty,total_sales) VALUES (?,?,?,?,?)",
        [
            (1, 1, "2026-01-05", 10, 100),
            (2, 2, "2026-01-05", 100, 1000),
            (3, 1, "2026-02-05", 9, 90),
            (4, 2, "2026-02-05", 95, 950),
        ],
    )
    _, rows = run(
        fixture,
        request(
            group_by=["dim_carline.model"],
            period={"label": "Feb", "start": "2026-02-01", "end_exclusive": "2026-03-01"},
            comparisons=[
                {
                    "kind": "period",
                    "baseline": {
                        "label": "Jan",
                        "start": "2026-01-01",
                        "end_exclusive": "2026-02-01",
                    },
                }
            ],
            ranking={"measure_id": "revenue", "basis": basis, "direction": "asc", "limit": 1},
        ),
    )
    assert rows[0]["model"] == model


def test_reference_sql_checks_multi_join_asp_independently(fixture):
    _, rows = run(
        fixture,
        request(
            measures=[{"id": "revenue"}, {"id": "units_sold"}, {"id": "average_selling_price"}],
            group_by=["dim_carline.make", "dim_region.region_name"],
        ),
    )
    reference = (
        fixture[3]
        .execute("""SELECT v.make,r.region_name,SUM(f.total_sales) revenue,
        SUM(f.order_qty) units_sold,1.0*SUM(f.total_sales)/NULLIF(SUM(f.order_qty),0) average_selling_price
        FROM automotive.fact_sales f LEFT JOIN automotive.dim_carline v ON v.carline_id=f.carline_id
        LEFT JOIN automotive.dim_region r ON r.region_id=f.region_id
        WHERE f.sales_date>='2026-01-01' AND f.sales_date<'2027-01-01'
        GROUP BY v.make,r.region_name ORDER BY v.make,r.region_name""")
        .fetchall()
    )
    public = [{k: v for k, v in row.items() if not k.startswith("__")} for row in rows]
    assert public == [dict(row) for row in reference]


@pytest.mark.parametrize(
    "question,overrides,column,total",
    [
        (
            "Total revenue and units sold last quarter",
            {
                "measures": [{"id": "revenue"}, {"id": "units_sold"}],
                "period": {"label": "Q3", "relative": "last_quarter"},
            },
            "revenue",
            5000,
        ),
        (
            "Top five models by revenue this year",
            {
                "group_by": ["dim_carline.model"],
                "period": {"label": "YTD", "relative": "this_year"},
                "ranking": {"measure_id": "revenue", "limit": 5},
            },
            "revenue",
            22600,
        ),
        (
            "Total revenue this month so far",
            {"period": {"label": "MTD", "relative": "this_month"}},
            "revenue",
            3000,
        ),
        (
            "Revenue this quarter versus last quarter",
            {
                "period": {"label": "QTD", "relative": "this_quarter"},
                "comparisons": [{"kind": "period", "baseline_reference": "previous_period"}],
            },
            "change_revenue",
            3000,
        ),
        (
            "Units sold this year versus same period last year",
            {
                "measures": [{"id": "units_sold"}],
                "period": {"label": "YTD", "relative": "this_year"},
                "comparisons": [{"kind": "period", "baseline_reference": "same_period_last_year"}],
            },
            "current_units_sold",
            151,
        ),
        (
            "Best and worst region last quarter",
            {
                "group_by": ["dim_region.region_name"],
                "period": {"label": "Q3", "relative": "last_quarter"},
                "ranking": {"measure_id": "revenue", "include_both_ends": True},
            },
            "revenue",
            5000,
        ),
        (
            "Revenue by region last quarter",
            {
                "group_by": ["dim_region.region_name"],
                "period": {"label": "Q3", "relative": "last_quarter"},
            },
            "revenue",
            5000,
        ),
        (
            "Top dealers this year",
            {
                "group_by": ["dim_dealer.dealer_name"],
                "ranking": {"measure_id": "revenue", "limit": 5},
            },
            "revenue",
            22600,
        ),
        (
            "Models declining most versus last quarter",
            {
                "group_by": ["dim_carline.model"],
                "period": {"label": "QTD", "relative": "this_quarter"},
                "comparisons": [{"kind": "period", "baseline_reference": "previous_period"}],
                "ranking": {"measure_id": "revenue", "direction": "asc", "limit": 5},
            },
            "change_revenue",
            3000,
        ),
        (
            "Monthly revenue last twelve months",
            {
                "time_grain": "month",
                "period": {"label": "12 months", "relative": "last_n_months", "count": 12},
            },
            "revenue",
            23000,
        ),
        (
            "Sales trend by model last four quarters",
            {
                "time_grain": "quarter",
                "group_by": ["dim_carline.model"],
                "period": {"label": "4 quarters", "relative": "last_n_quarters", "count": 4},
            },
            "revenue",
            22600,
        ),
        (
            "How are we doing?",
            {
                "measures": [{"id": "revenue"}, {"id": "units_sold"}],
                "period": {"label": "Approved QTD summary", "relative": "this_quarter"},
            },
            "revenue",
            8000,
        ),
        (
            "Turnover and volume in 2026",
            {"measures": [{"id": "revenue"}, {"id": "units_sold"}]},
            "units_sold",
            151,
        ),
    ],
)
def test_executive_reference_requests(question, overrides, column, total, fixture):
    """English labels describe fixture requests, not a live-model accuracy benchmark."""
    compiled, rows = run(fixture, request(**overrides))
    assert question and compiled.sql
    assert sum(row[column] for row in rows if row.get(column) is not None) == total
