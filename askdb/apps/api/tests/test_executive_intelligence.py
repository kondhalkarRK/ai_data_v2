"""Unit tests for Executive Intelligence helpers."""

from app.schemas.kpi import KpiCard
from app.services.executive.domain_config import get_domain_config
from app.services.executive.insights import build_grounded_insights, compute_business_health


def test_domain_config_automotive_and_insurance() -> None:
    auto = get_domain_config("automotive")
    ins = get_domain_config("insurance")
    assert auto["title"] == "Automotive Intelligence"
    assert "written_premium" in ins["primaryKpis"]
    assert "revenue" in auto["healthScoreWeights"]


def test_health_score_exposes_components() -> None:
    cards = [
        KpiCard(id="revenue", label="Revenue", value=100.0, formatted="₹100", format="currency", delta=0.1),
        KpiCard(id="units_sold", label="Units", value=10.0, formatted="10", format="integer", delta=0.05),
    ]
    result = compute_business_health(
        cards=cards,
        weights={"revenue": 0.6, "units_sold": 0.4},
    )
    assert result["available"] is True
    assert result["score"] is not None
    assert len(result["components"]) == 2


def test_insights_require_grounding_and_real_metrics() -> None:
    cards = [
        KpiCard(
            id="written_premium",
            label="GWP",
            value=1_000_000,
            formatted="₹10 L",
            format="currency",
            delta=0.11,
        ),
        KpiCard(
            id="loss_ratio",
            label="Loss Ratio",
            value=0.7,
            formatted="70.0%",
            format="percent",
            delta=0.04,
        ),
    ]
    insights = build_grounded_insights(
        industry="insurance",
        cards=cards,
        compare_label="vs prior YTD",
        glossary_terms=["premium"],
        dq_notices=[],
    )
    assert insights
    assert all(item.grounded_on for item in insights)
    # Missing inventory metric must not invent an inventory insight for automotive
    auto = build_grounded_insights(
        industry="automotive",
        cards=[],
        compare_label="vs prior",
        glossary_terms=[],
        dq_notices=[],
    )
    assert auto == []
