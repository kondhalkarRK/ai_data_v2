"""Unit tests for SQL guardrails and legacy data-quality scoring."""

from __future__ import annotations

from datetime import date

from app.analytics.data_quality import compute_data_quality
from app.analytics.sql_guardrails import sql_is_safe


def test_sql_is_safe_allows_select_and_blocks_delete() -> None:
    assert sql_is_safe("SELECT 1 FROM automotive.fact_sales")[0] is True
    ok, reason = sql_is_safe("DELETE FROM automotive.fact_sales")
    assert ok is False
    assert "SELECT" in reason.upper()
    assert sql_is_safe("WITH x AS (DELETE FROM t) SELECT 1")[0] is False
    assert sql_is_safe("SELECT * FROM t; DROP TABLE t")[0] is False


def test_data_quality_score_matches_legacy_formula_on_fixture() -> None:
    rows = [
        {
            "order_id": i,
            "sales_date": date(2024, 1 + (i % 6), 1),
            # Repeated prices keep unique-ratio below the ID heuristic.
            "total_sales": float(10_000 + (i % 8) * 250),
            "notes": "ok",
        }
        for i in range(1, 41)
    ]
    # Inject controlled defects.
    rows[0]["notes"] = None
    rows[1]["notes"] = None
    rows.append(dict(rows[2]))  # duplicate
    rows[5]["total_sales"] = 1_000_000.0  # outlier

    report = compute_data_quality(rows)
    total_rows = len(rows)
    total_cols = 4
    total_null_cells = 2
    total_null_pct = round(total_null_cells / (total_rows * total_cols) * 100, 2)
    duplicate_pct = round(1 / total_rows * 100, 2)

    expected = 100.0
    expected -= min(total_null_pct * 1.5, 25)
    expected -= min(duplicate_pct * 2.0, 20)
    expected -= min(len(report["outliers"]) * 3, 15)
    expected -= min(len(report["type_issues"]) * 4, 16)
    expected -= min(len(report["cardinality_flags"]) * 2, 10)
    expected -= min(len(report["date_gaps"]) * 1, 10)
    expected = max(round(expected, 1), 0.0)

    assert report["total_null_pct"] == total_null_pct
    assert report["duplicate_count"] == 1
    assert report["health_score"] == expected
    assert "total_sales" in report["outliers"]


def test_insurance_dimensions_are_deterministic() -> None:
    from app.analytics.insurance_seed import build_dimensions, iter_claims

    a = build_dimensions(policy_count=100)
    b = build_dimensions(policy_count=100)
    assert a.products == b.products
    assert len(list(iter_claims(a, row_count=500))) == 500
