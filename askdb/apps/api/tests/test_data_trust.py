"""Unit tests for Data Trust scoring helpers."""

from app.services.trust.scoring import (
    aggregate_trust_score,
    build_incidents_for_table,
    build_rules_for_table,
    dimension_scores,
    label_for_score,
)


def test_dimension_scores_from_dq_report() -> None:
    report = {
        "total_null_pct": 2.0,
        "duplicate_pct": 0.0,
        "type_issues": [],
        "outliers": {},
        "cardinality_flags": [],
        "date_gaps": [],
    }
    dims = dimension_scores(report, freshness_hours=2.0, sla_hours=12.0)
    assert dims["freshness"] == 100.0
    assert dims["completeness"] > 90
    score, components = aggregate_trust_score(dims)
    assert score is not None
    assert len(components) == 7
    assert label_for_score(score) in {"Healthy", "Watch", "At risk", "Critical"}


def test_incidents_require_sla_for_freshness() -> None:
    report = {"total_null_pct": 1.0, "duplicate_pct": 0, "type_issues": [], "date_gaps": [], "outliers": {}}
    dims = dimension_scores(report, freshness_hours=20.0, sla_hours=6.0)
    incidents = build_incidents_for_table(
        table_name="fact_sales",
        display_name="Fact Sales",
        dimensions=dims,
        report=report,
        freshness_hours=20.0,
        sla_hours=6.0,
        impacted_assets=["kpi:revenue", "dashboard:executive-intelligence"],
    )
    assert any(i["id"].startswith("freshness-") for i in incidents)
    assert all(i.get("rootCauseHint") is None for i in incidents)


def test_rules_reflect_pass_fail() -> None:
    report = {
        "total_null_pct": 8.0,
        "duplicate_pct": 0.2,
        "type_issues": [{"column": "x", "issue": "bad"}],
        "date_gaps": [],
    }
    dims = dimension_scores(report, freshness_hours=1.0, sla_hours=24.0)
    rules = build_rules_for_table("fact_claims", report, dims)
    null_rule = next(r for r in rules if r["id"].endswith("null-pct"))
    assert null_rule["passing"] is False
