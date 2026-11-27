"""Opt-in native syntax/math checks on the existing EMPTY disposable test DB.

Visible development fixture; not human-approved reference SQL or blind holdouts.
Never uses the application/office warehouse URL or commits test setup.
"""

from dataclasses import replace
from datetime import date

import pytest
from sqlalchemy import text

from app.services.chat.analytical_plan_compiler import compile_analysis
from app.services.chat.analytical_plan_execution import check_results
from app.services.chat.analytical_plan_validation import scope_fingerprint
from app.services.chat.request_context import build_request_context
from tests.test_chat_postgres_acceptance import native_database  # noqa: F401
from tests.unit.test_analytical_execution import DATA
from tests.unit.test_analytical_plan import (  # noqa: F401
    base_review,
    cohort_history_example,
    compare_example,
    extreme_period_example,
    opposite_changes_example,
    region_example,
)


def test_native_dependent_period_binding_and_reconciliation(native_database, base_review):  # noqa: F811
    pack, connection = native_database
    principal = base_review.principal
    context = build_request_context(
        "revenue by region model month", pack=pack, principal=principal, max_chars=16000
    )
    review = replace(
        base_review,
        pack=pack,
        context=context,
        completeness_sources=(
            replace(
                base_review.completeness_sources[0],
                scope_fingerprint=scope_fingerprint(principal.binding),
            ),
        ),
    )
    connection.execute(text("DELETE FROM automotive.fact_sales"))
    connection.execute(
        text(
            "INSERT INTO automotive.dim_region(region_id,region_name,state_code) "
            "VALUES (1,'West','MH'),(2,'South','TN')"
        )
    )
    # Only the test fixture transaction is modified, after its empty-DB guard.
    connection.execute(
        text(
            "INSERT INTO automotive.fact_sales(order_id,carline_id,region_id,dealer_id,"
            "sales_date,order_qty,total_sales) "
            "VALUES (:id,:car,:region,:dealer,:day,:units,:revenue)"
        ),
        [
            dict(
                zip(["id", "car", "region", "dealer", "day", "units", "revenue"], row, strict=True)
            )
            for row in DATA
        ],
    )
    plan, review = extreme_period_example(review)
    compiled = compile_analysis(plan, review, today=date(2026, 11, 26))
    rows = [dict(r) for r in connection.execute(text(compiled.sql)).mappings().all()]
    result = check_results(compiled, rows)
    assert result.status == "completed"
    head = next(s for s in result.steps if s.id == "headline")
    assert head.rows[0]["revenue_current"] == 1000
    assert head.rows[0]["revenue_baseline"] == 3000
    assert head.rows[0]["revenue_change"] == -2000
    assert head.rows[0]["selected_period_start"] == "2026-02-01"
    assert result.checks[0]["passed"]


# Independent visible reference SQL, not generated from compiler SQL or user holdouts.
REFERENCE_COMPARISON = """
WITH current_values AS (
  SELECT v.model, SUM(f.total_sales) revenue, SUM(f.order_qty) units
  FROM automotive.fact_sales f JOIN automotive.dim_carline v USING (carline_id)
  WHERE f.sales_date >= DATE '2025-11-01' AND f.sales_date < DATE '2026-11-01'
  GROUP BY v.model
), baseline_values AS (
  SELECT v.model, SUM(f.total_sales) revenue, SUM(f.order_qty) units
  FROM automotive.fact_sales f JOIN automotive.dim_carline v USING (carline_id)
  WHERE f.sales_date >= DATE '2024-11-01' AND f.sales_date < DATE '2025-11-01'
  GROUP BY v.model
), compared AS (
  SELECT COALESCE(c.model,b.model) model, c.revenue revenue_current,
    b.revenue revenue_baseline, c.revenue-b.revenue revenue_change,
    c.units units_sold_current, b.units units_sold_baseline,
    c.units-b.units units_sold_change
  FROM current_values c FULL OUTER JOIN baseline_values b ON c.model=b.model
)
"""


@pytest.mark.parametrize("shape", ["region", "decliners", "opposite", "cohort"])
def test_native_other_shapes_against_independent_sql(native_database, base_review, shape):  # noqa: F811
    pack, connection = native_database
    principal = base_review.principal
    context = build_request_context(
        "revenue units region model", pack=pack, principal=principal, max_chars=16000
    )
    review = replace(base_review, pack=pack, context=context, completeness_sources=())
    connection.execute(text("DELETE FROM automotive.fact_sales"))
    connection.execute(
        text(
            "INSERT INTO automotive.dim_region(region_id,region_name,state_code) "
            "VALUES (1,'West','MH'),(2,'South','TN')"
        )
    )
    connection.execute(
        text(
            "INSERT INTO automotive.fact_sales(order_id,carline_id,region_id,dealer_id,"
            "sales_date,order_qty,total_sales) "
            "VALUES (:id,:car,:region,:dealer,:day,:units,:revenue)"
        ),
        [
            dict(
                zip(["id", "car", "region", "dealer", "day", "units", "revenue"], row, strict=True)
            )
            for row in DATA
        ],
    )
    if shape == "opposite":
        connection.execute(
            text(
                "UPDATE automotive.fact_sales SET order_qty=5 "
                "WHERE carline_id=1 AND sales_date >= DATE '2026-01-01'"
            )
        )
    example = {
        "region": region_example,
        "decliners": compare_example,
        "opposite": opposite_changes_example,
        "cohort": cohort_history_example,
    }[shape]
    plan, review = example(review)
    compiled = compile_analysis(plan, review, today=date(2026, 11, 26))
    observed = check_results(
        compiled, [dict(r) for r in connection.execute(text(compiled.sql)).mappings()]
    )
    final = observed.steps[-1]
    assert observed.status == "completed"
    if shape == "region":
        reference = """
        WITH region_totals AS (
          SELECT r.region_name, SUM(f.total_sales) revenue
          FROM automotive.fact_sales f JOIN automotive.dim_region r USING (region_id)
          WHERE f.sales_date >= DATE '2025-11-01' AND f.sales_date < DATE '2026-11-01'
          GROUP BY r.region_name
        ), winners AS (
          SELECT region_name FROM region_totals
          WHERE revenue=(SELECT MAX(revenue) FROM region_totals)
        )
        SELECT v.model, SUM(f.total_sales) revenue_value
        FROM automotive.fact_sales f JOIN automotive.dim_region r USING (region_id)
        JOIN automotive.dim_carline v USING (carline_id)
        WHERE r.region_name IN (SELECT region_name FROM winners)
          AND f.sales_date >= DATE '2025-11-01' AND f.sales_date < DATE '2026-11-01'
        GROUP BY v.model ORDER BY revenue_value DESC, v.model LIMIT 10
        """
    else:
        reference = (
            REFERENCE_COMPARISON + "SELECT model,revenue_current,revenue_baseline,revenue_change"
        )
        if shape == "opposite":
            reference += ",units_sold_current,units_sold_baseline,units_sold_change"
        reference += " FROM compared"
        if shape == "opposite":
            reference += " WHERE revenue_change > 0 AND units_sold_change < 0"
        elif shape == "cohort":
            reference += (
                " WHERE model IN (SELECT model FROM (SELECT model, "
                "RANK() OVER (ORDER BY revenue DESC) position FROM current_values) "
                "ranked WHERE position<=5)"
            )
        reference += (
            " ORDER BY revenue_change ASC,model" if shape == "decliners" else " ORDER BY model"
        )
    expected = [dict(r) for r in connection.execute(text(reference)).mappings()]
    assert sorted(final.rows, key=lambda r: r["model"]) == sorted(
        expected, key=lambda r: r["model"]
    )
    if shape == "decliners":
        assert [r["model"] for r in final.rows] == [r["model"] for r in expected]
