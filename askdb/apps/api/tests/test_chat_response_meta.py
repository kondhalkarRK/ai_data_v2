"""Tests for honest chat response metadata helpers."""

from app.core.config import Industry
from app.services.chat.response_meta import (
    build_insights,
    detect_anomalies,
    extract_query_meta,
    resolve_grounded_on,
    semantic_followups,
    sql_diff_lines,
)


def test_extract_query_meta_tables_and_metrics() -> None:
    sql = """
    SELECT r.region_name, SUM(c.incurred_amount) AS claims_incurred
    FROM insurance.fact_claims c
    LEFT JOIN insurance.dim_region r ON r.region_id = c.region_id
    WHERE c.reported_date >= DATE '2024-01-01'
    GROUP BY 1
    """
    meta = extract_query_meta(sql)
    assert "insurance.fact_claims" in meta.tables_used
    assert "insurance.dim_region" in meta.tables_used
    assert "claims_incurred" in meta.metrics_used
    assert meta.date_range is not None


def test_grounded_on_only_lists_used_sources() -> None:
    assert resolve_grounded_on(
        path="template", glossary_matches=2, has_sql=True, dq_checked=False
    ) == ["Semantic Layer", "Business Glossary", "KPI Definition"]
    assert "Data Quality Check" not in resolve_grounded_on(
        path="fallback", glossary_matches=0, has_sql=False, dq_checked=False
    )


def test_semantic_followups_require_real_dimensions() -> None:
    items = semantic_followups(
        Industry.INSURANCE,
        dimensions=["region_name"],
        metrics=["claims_incurred"],
        tables=["insurance.fact_claims", "insurance.dim_region"],
        path="template",
    )
    assert any("region" in item.lower() for item in items)


def test_sql_diff_and_anomalies() -> None:
    diff = sql_diff_lines("SELECT 1", "SELECT 2")
    assert diff is not None
    assert any(line["op"] == "add" for line in diff)
    rows = [{"x": i, "y": 10 if i != 5 else 100} for i in range(10)]
    markers = detect_anomalies(["x", "y"], rows)
    assert markers
    insights = build_insights(
        narrative="Revenue rose.",
        columns=["x", "y"],
        rows=rows,
        path="template",
    )
    assert insights["executive"]
    assert "template" in insights["analyst"]
