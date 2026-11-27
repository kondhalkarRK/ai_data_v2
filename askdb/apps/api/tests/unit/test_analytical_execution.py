"""Visible development fixtures, not human-approved SQL or blind holdout acceptance.

Execute SQLGlot-adapted SQL in memory. PostgreSQL/office/provider acceptance remains
separate. The small reference totals below are independently calculated from rows.
"""

import asyncio
from dataclasses import replace
from datetime import date
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
import sqlglot
from sqlglot import exp

from app.core.config import Settings
from app.services.chat.analytical_plan_compiler import compile_analysis
from app.services.chat.analytical_plan_execution import check_results, execute_analysis
from app.services.chat.analytical_plan_validation import scope_fingerprint
from app.services.chat.request_context import build_request_context
from app.services.security.region_scope import RegionScope
from tests.unit.test_analytical_plan import (
    base_review,  # noqa: F401 -- imported pytest fixture
    changed,
    cohort_history_example,
    compare_example,
    extreme_period_example,
    opposite_changes_example,
    region_example,
)
from tests.unit.test_request_compiler import fixture  # noqa: F401 -- imported pytest fixture

TODAY = date(2026, 11, 26)
DATA = [
    (1, 1, 1, 1, "2026-01-05", 10, 1000),
    (2, 2, 2, 2, "2026-01-05", 20, 2000),
    (3, 1, 1, 1, "2026-02-05", 5, 500),
    (4, 2, 2, 2, "2026-02-05", 5, 500),
    (5, 1, 1, 1, "2026-03-05", 15, 1500),
    (6, 2, 2, 2, "2026-03-05", 25, 2500),
    (7, 1, 1, 1, "2025-01-05", 20, 1200),
    (8, 2, 2, 2, "2025-01-05", 10, 1800),
]


@pytest.fixture
def warehouse(fixture, base_review):  # noqa: F811 -- pytest fixture injection
    pack, principal, context, db = fixture
    db.execute("DELETE FROM automotive.fact_sales")
    db.executemany(
        "INSERT INTO automotive.fact_sales(order_id,carline_id,region_id,dealer_id,"
        "sales_date,order_qty,total_sales) VALUES (?,?,?,?,?,?,?)",
        DATA,
    )
    source = replace(
        base_review.completeness_sources[0], scope_fingerprint=scope_fingerprint(principal.binding)
    )
    review = replace(
        base_review, pack=pack, principal=principal, context=context, completeness_sources=(source,)
    )
    return review, db


def adapted(sql):
    def adapt(node):
        if isinstance(node, (exp.Add, exp.Sub)) and isinstance(node.expression, exp.Interval):
            interval = node.expression
            count = int(interval.this.this) * (-1 if isinstance(node, exp.Sub) else 1)
            return exp.Anonymous(
                this="DATE",
                expressions=[
                    node.this.copy(),
                    exp.Literal.string(f"{count} {interval.args['unit'].name.lower()}s"),
                ],
            )
        if isinstance(node, exp.TimestampTrunc):
            return exp.Anonymous(
                this="DATE_TRUNC",
                expressions=[exp.Literal.string(node.args["unit"].name.lower()), node.this.copy()],
            )
        return node

    return sqlglot.parse_one(sql, read="postgres").transform(adapt).sql(dialect="sqlite")


def run(warehouse, example):
    review, db = warehouse
    plan, review = example(review)
    compiled = compile_analysis(plan, review, today=TODAY)
    rows = [dict(row) for row in db.execute(adapted(compiled.sql))]
    return compiled, review, rows, check_results(compiled, rows)


def test_named_extreme_period_uses_selected_month_and_independent_baseline(warehouse):
    compiled, _, rows, result = run(warehouse, extreme_period_example)
    assert result.status == "completed", result.model_dump()
    selected = next(s for s in result.steps if s.id == "lowest_month")
    assert selected.rows == [
        {"revenue_value": 1000.0, "period_start": "2026-02-01", "period_end": "2026-03-01"}
    ]
    head = next(s for s in result.steps if s.id == "headline")
    assert head.rows == [
        {
            "revenue_current": 1000.0,
            "revenue_baseline": 3000.0,
            "revenue_change": -2000.0,
            "selected_period_start": "2026-02-01",
            "selected_period_end": "2026-03-01",
            "baseline_period_start": "2026-01-01",
            "baseline_period_end": "2026-02-01",
        }
    ]
    details = next(s for s in result.steps if s.id == "contributors")
    assert [r["region_name"] for r in details.rows] == ["South", "West"]
    assert [r["revenue_change"] for r in details.rows] == [-1500.0, -500.0]
    assert sum(r["revenue_change"] for r in details.rows) == head.rows[0]["revenue_change"]
    assert result.checks[0]["passed"]
    assert "FULL OUTER JOIN" in compiled.sql
    assert all(r["__check_0"] == 0 for r in rows)


def test_extreme_region_binds_only_selected_region(warehouse):
    _, _, _, result = run(warehouse, region_example)
    chosen = next(s for s in result.steps if s.id == "selected_region")
    assert chosen.rows == [{"revenue_value": 5000.0, "region_name": "South"}]
    models = next(s for s in result.steps if s.id == "models")
    assert models.rows == [{"revenue_value": 5000.0, "model": "B"}]


def test_requested_model_ranking_is_applied_after_region_selection(warehouse):
    review, db = warehouse
    db.execute(
        "INSERT INTO automotive.fact_sales(order_id,carline_id,region_id,sales_date,"
        "order_qty,total_sales) VALUES (30,3,2,'2026-02-10',1,2000)"
    )
    plan, review = region_example(review)
    plan = changed(plan, lambda p: p["steps"][2]["request"]["ranking"].update(limit=1))
    review = replace(
        review,
        requirements=tuple(
            replace(r, request=plan.steps[2].request) if r.id == "req_models" else r
            for r in review.requirements
        ),
    )
    compiled = compile_analysis(plan, review, today=TODAY)
    result = check_results(compiled, [dict(row) for row in db.execute(adapted(compiled.sql))])
    models = next(s for s in result.steps if s.id == "models")
    assert models.rows == [{"revenue_value": 5000, "model": "B"}]
    assert models.total_groups == 2 and models.selected_groups == 1


def test_explicit_periods_rank_changes_not_total_values(warehouse):
    def example(review):
        plan, review = compare_example(review)
        # This is visible fixture setup; the explicit scope is fixed independently
        # before damaging proposals in the separate coverage tests.
        period = {"label": "Feb 2026", "start": "2026-02-01", "end_exclusive": "2026-03-01"}
        plan = changed(plan, lambda p: p["steps"][0]["request"].update(period=period))
        req = plan.steps[0].request
        review = replace(review, requirements=(replace(review.requirements[0], request=req),))
        return plan, review

    _, _, _, result = run(warehouse, example)
    rows = result.steps[0].rows
    assert [r["model"] for r in rows] == ["B", "A"]
    assert [r["revenue_change"] for r in rows] == [-1500, -500]


def test_opposite_measure_changes_keep_both_predicates(warehouse):
    review, db = warehouse
    db.execute("UPDATE automotive.fact_sales SET total_sales=1500, order_qty=5 WHERE order_id=3")

    def example(review):
        plan, review = opposite_changes_example(review)
        period = {"label": "Feb", "start": "2026-02-01", "end_exclusive": "2026-03-01"}
        plan = changed(plan, lambda p: p["steps"][0]["request"].update(period=period))
        return plan, replace(
            review, requirements=(replace(review.requirements[0], request=plan.steps[0].request),)
        )

    _, _, _, result = run((review, db), example)
    assert len(result.steps[0].rows) == 1
    assert result.steps[0].rows[0]["model"] == "A"
    assert result.steps[0].rows[0]["revenue_change"] == 500
    assert result.steps[0].rows[0]["units_sold_change"] == -5


def test_fixed_cohort_compares_each_member_with_own_history(warehouse):
    _, _, _, result = run(warehouse, cohort_history_example)
    cohort = next(s for s in result.steps if s.id == "top_cohort")
    history = next(s for s in result.steps if s.id == "own_history")
    assert {r["model"] for r in cohort.rows} == {r["model"] for r in history.rows} == {"A", "B"}
    assert {r["model"]: r["revenue_baseline"] for r in history.rows} == {"A": 1200, "B": 1800}


class Connection:
    def __init__(self, db, delay=0):
        self.db, self.delay, self.statements = db, delay, []

    async def execute(self, statement, *args, **kwargs):
        sql = str(statement)
        self.statements.append(sql)
        if sql == "SHOW transaction_read_only":
            return SimpleNamespace(scalar_one=lambda: "on")
        if sql.startswith(("SET ", "EXPLAIN ")):
            return None
        if self.delay:
            await asyncio.sleep(self.delay)
        rows = [dict(row) for row in self.db.execute(adapted(sql))]
        return SimpleNamespace(mappings=lambda: SimpleNamespace(all=lambda: rows))


async def execute(warehouse, *, enabled=True, authorize=None, cancelled=None, delay=0):
    review, db = warehouse
    plan, review = region_example(review)
    connection = Connection(db, delay=delay)
    result = await execute_analysis(
        plan,
        review,
        connection=connection,
        settings=Settings(
            _env_file=None,
            chat_typed_execution_enabled=True,
            chat_dependent_analysis_enabled=enabled,
        ),
        today=TODAY,
        authorize=authorize or AsyncMock(return_value=True),
        cancelled=cancelled or AsyncMock(return_value=False),
    )
    return result, connection


async def test_one_read_only_statement_with_scoped_sql_provenance(warehouse):
    result, conn = await execute(warehouse)
    assert result.status == "completed", result.model_dump()
    assert result.analytical_queries == 1
    assert sum(s.startswith("WITH ") for s in conn.statements) == 1
    assert conn.statements[0] == "SHOW transaction_read_only"
    assert result.sql_fingerprint


async def test_disabled_and_denied_run_no_warehouse_statements(warehouse):
    result, conn = await execute(warehouse, enabled=False)
    assert result.status == "disabled" and not conn.statements
    result, conn = await execute(warehouse, authorize=AsyncMock(return_value=False))
    assert result.status == "denied" and not conn.statements


async def test_revoked_scope_discards_all_results(warehouse):
    result, _conn = await execute(warehouse, authorize=AsyncMock(side_effect=[True, True, False]))
    assert result.status == "denied"
    assert result.steps == [] and result.sql is None
    assert result.analytical_queries == 1


async def test_cancel_during_query_returns_no_results(warehouse):
    checks = 0

    async def cancelled():
        nonlocal checks
        checks += 1
        return checks >= 3

    result, _ = await execute(warehouse, cancelled=cancelled, delay=10)
    assert result.status == "cancelled"
    assert not result.steps


def test_missing_outputs_and_corrupt_reconciliation_are_rejected(warehouse):
    compiled, _, rows, _ = run(warehouse, extreme_period_example)
    corrupted = [r.copy() for r in rows]
    corrupted[0].pop("s0_revenue_value")
    with pytest.raises(ValueError, match="columns"):
        check_results(compiled, corrupted)
    corrupted = [r | {"__check_0": 1} for r in rows]
    result = check_results(compiled, corrupted)
    detail = next(s for s in result.steps if s.id == "contributors")
    assert result.status == "partial" and not detail.verified


def test_missing_member_is_not_synthesized_as_zero(warehouse):
    review, db = warehouse
    db.execute("DELETE FROM automotive.fact_sales WHERE order_id=2")
    _, _, _, result = run((review, db), extreme_period_example)
    assert not result.checks[0]["passed"]
    detail = next(s for s in result.steps if s.id == "contributors")
    assert detail.status == "partial"
    assert any(r["revenue_baseline"] is None for r in detail.rows)


def test_empty_source_skips_dependent_tasks(warehouse):
    review, db = warehouse
    db.execute("DELETE FROM automotive.fact_sales")
    _, _, _, result = run((review, db), region_example)
    assert result.steps[0].status == "empty"
    assert all(s.status == "skipped" and not s.rows for s in result.steps[1:])


async def test_regional_scope_is_applied_to_every_branch(warehouse):
    review, db = warehouse
    principal = replace(review.principal, scope=RegionScope(False, ("West",)))
    context = build_request_context(
        "revenue regions models", pack=review.pack, principal=principal, max_chars=16000
    )
    review = replace(review, principal=principal, context=context, completeness_sources=())
    result, _ = await execute((review, db))
    assert result.status == "completed", result.model_dump()
    selected = next(s for s in result.steps if s.id == "selected_region")
    assert selected.rows == [{"revenue_value": 3000, "region_name": "West"}]
    assert "/*rls*/" in result.sql
    assert "South" not in str(result.steps)


def test_all_tied_periods_are_bound_separately_not_combined(warehouse):
    review, db = warehouse
    db.execute("UPDATE automotive.fact_sales SET total_sales=500 WHERE order_id IN (5,6)")
    _, _, _, result = run((review, db), extreme_period_example)
    selected = next(s for s in result.steps if s.id == "lowest_month")
    head = next(s for s in result.steps if s.id == "headline")
    assert len(selected.rows) == len(head.rows) == 2
    assert {r["selected_period_start"]: r["revenue_change"] for r in head.rows} == {
        "2026-02-01": -2000,
        "2026-03-01": 0,
    }
    detail = next(s for s in result.steps if s.id == "contributors")
    assert detail.status == "partial"  # March is not a dip against February.
    assert "did not decline" in " ".join(detail.notes)


def test_cohort_overflow_asks_to_narrow_and_skips_dependents(warehouse):
    review, db = warehouse
    db.execute("DELETE FROM automotive.fact_sales")
    db.executemany(
        "INSERT INTO automotive.dim_region(region_id,region_name,state_code) VALUES (?,?,?)",
        [(i, f"Region {i}", "MH") for i in range(10, 61)],
    )
    db.executemany(
        "INSERT INTO automotive.fact_sales(order_id,carline_id,region_id,sales_date,"
        "order_qty,total_sales) VALUES (?,?,?,'2026-02-05',1,100)",
        [(i, 1, i) for i in range(10, 61)],
    )
    _, _, _, result = run((review, db), region_example)
    selected = next(s for s in result.steps if s.id == "selected_region")
    dependent = next(s for s in result.steps if s.id == "models")
    assert result.status == "clarification"
    assert selected.total_groups == 51 and selected.status == "clarification" and not selected.rows
    assert dependent.status == "skipped" and not dependent.rows


def test_verified_zero_remains_a_real_value(warehouse):
    review, db = warehouse
    db.execute("UPDATE automotive.fact_sales SET total_sales=0 WHERE order_id IN (3,4)")
    _, _, _, result = run((review, db), extreme_period_example)
    selected = next(s for s in result.steps if s.id == "lowest_month")
    assert selected.rows[0]["revenue_value"] == 0
    assert selected.status == "completed" and selected.verified
    assert result.checks[0]["passed"]


def test_positive_offsets_remain_in_independent_reconciliation(warehouse):
    review, db = warehouse
    db.execute("UPDATE automotive.fact_sales SET total_sales=1500 WHERE order_id=3")
    db.execute("UPDATE automotive.fact_sales SET total_sales=-500 WHERE order_id=4")
    _, _, _, result = run((review, db), extreme_period_example)
    detail = next(s for s in result.steps if s.id == "contributors")
    assert [r["revenue_change"] for r in detail.rows] == [-2500, 500]
    assert result.checks[0]["passed"]


def test_binding_period_corruption_is_rejected(warehouse):
    compiled, _, rows, _ = run(warehouse, extreme_period_example)
    corrupted = [
        r | {"__period_start": "2026-04-01", "__period_end": "2026-05-01"}
        if r["__step"] == "headline"
        else r
        for r in rows
    ]
    with pytest.raises(ValueError, match="not a selected"):
        check_results(compiled, corrupted)


async def test_read_only_setup_failure_does_not_run_select(warehouse):
    review, _db = warehouse
    plan, review = region_example(review)
    connection = SimpleNamespace(
        execute=AsyncMock(side_effect=RuntimeError("private driver details"))
    )
    result = await execute_analysis(
        plan,
        review,
        connection=connection,
        settings=Settings(
            _env_file=None, chat_typed_execution_enabled=True, chat_dependent_analysis_enabled=True
        ),
        today=TODAY,
        authorize=AsyncMock(return_value=True),
        cancelled=AsyncMock(return_value=False),
    )
    assert result.status == "failed" and result.analytical_queries == 0
    assert connection.execute.await_count == 1
    assert "private driver" not in result.model_dump_json()


async def test_read_write_connection_is_rejected_before_explain_or_query(warehouse):
    review, _db = warehouse
    plan, review = region_example(review)
    connection = SimpleNamespace(
        execute=AsyncMock(return_value=SimpleNamespace(scalar_one=lambda: "off"))
    )
    result = await execute_analysis(
        plan,
        review,
        connection=connection,
        settings=Settings(
            _env_file=None, chat_typed_execution_enabled=True, chat_dependent_analysis_enabled=True
        ),
        today=TODAY,
        authorize=AsyncMock(return_value=True),
        cancelled=AsyncMock(return_value=False),
    )
    assert result.status == "failed" and result.analytical_queries == 0
    assert connection.execute.await_count == 1


def test_observed_baseline_is_not_proof_of_loaded_completeness(warehouse):
    review, db = warehouse
    db.execute("UPDATE automotive.fact_sales SET total_sales=250 WHERE order_id IN (1,2)")
    db.executemany(
        "INSERT INTO automotive.fact_sales(order_id,carline_id,region_id,sales_date,"
        "order_qty,total_sales) VALUES (?,?,?,'2025-12-05',10,1000)",
        [(20, 1, 1), (21, 2, 2)],
    )
    plan, review = extreme_period_example(review)

    def scope(p):
        for step in p["steps"]:
            step["request"]["period"] = {
                "label": "Q1",
                "start": "2026-01-01",
                "end_exclusive": "2026-04-01",
            }

    plan = changed(plan, scope)
    review = replace(
        review,
        requirements=tuple(
            replace(
                r, request=next(s.request for s in plan.steps if s.id == r.id.removeprefix("req_"))
            )
            for r in review.requirements
        ),
        completeness_sources=(
            replace(
                review.completeness_sources[0],
                start=date(2026, 1, 1),
                end_exclusive=date(2026, 4, 1),
            ),
        ),
    )
    compiled = compile_analysis(plan, review, today=TODAY)
    result = check_results(compiled, [dict(r) for r in db.execute(adapted(compiled.sql))])
    head = next(s for s in result.steps if s.id == "headline")
    detail = next(s for s in result.steps if s.id == "contributors")
    assert result.checks[0]["passed"]  # Arithmetic is correct, loading proof is absent.
    assert head.completeness_verified is False
    assert detail.status == "partial" and not detail.verified
