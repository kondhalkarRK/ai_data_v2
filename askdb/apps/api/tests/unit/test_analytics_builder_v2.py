"""Analytics Builder: validation, governed SQL, charts and business insight."""

from __future__ import annotations

from functools import lru_cache
from typing import Any

import pytest

from app.core.config import Industry, get_settings
from app.schemas.analytics import AnalyticsSpec
from app.semantic.service import SemanticService
from app.services.analytics.catalog import Catalog
from app.services.analytics.compiler import compile_builder_query, date_window, driver_sql
from app.services.analytics.insights import InsightContext, build_narration
from app.services.analytics.runner import _partial_period, assist_spec, build_chart
from app.services.chat.question_understanding import understand_question


@lru_cache(maxsize=2)
def _catalog(industry: Industry) -> Catalog:
    return Catalog(industry, SemanticService(get_settings())._load_pack(industry))


def auto() -> Catalog:
    return _catalog(Industry.AUTOMOTIVE)


def ins() -> Catalog:
    return _catalog(Industry.INSURANCE)


def spec(**kwargs: Any) -> AnalyticsSpec:
    return AnalyticsSpec(**kwargs)


def codes(catalog: Catalog, s: AnalyticsSpec) -> list[str]:
    return [i.code for i in catalog.inspect(s).issues if i.severity == "error"]


# -- validation ------------------------------------------------------------------------


def test_salesperson_as_metric_is_explained_with_fixes() -> None:
    report = auto().inspect(spec(metrics=["salesperson"], dimensions=["month"], analysis="moving_average"))
    assert not report.valid
    issue = report.issues[0]
    assert issue.code == "metric_is_dimension"
    assert "dimension, not a metric" in issue.message
    actions = {(f.action, f.value) for f in issue.fixes}
    assert ("add_dimension", "salesperson") in actions
    assert ("set_metric", "active_salespeople") in actions


@pytest.mark.parametrize(
    "analysis",
    ["moving_average", "running_total", "period_growth", "yoy_growth", "trend"],
)
def test_time_analyses_need_a_time_dimension(analysis: str) -> None:
    report = auto().inspect(spec(metrics=["revenue"], dimensions=["salesperson"], analysis=analysis))
    assert [i.code for i in report.issues] == ["time_required"]
    assert {f.value for f in report.issues[0].fixes} == {"month", "quarter", "year"}


@pytest.mark.parametrize("analysis", ["top_n", "bottom_n", "ranking", "contribution"])
def test_ranking_needs_a_business_dimension(analysis: str) -> None:
    assert codes(auto(), spec(metrics=["revenue"], dimensions=["month"], analysis=analysis)) == ["category_required"]


def test_top_n_with_time_offers_top_n_within_group() -> None:
    report = auto().inspect(spec(metrics=["revenue"], dimensions=["model", "month"], analysis="top_n"))
    issue = report.issues[0]
    assert issue.code == "time_not_allowed"
    assert any(f.value == "top_n_per_group" for f in issue.fixes)


def test_comparison_needs_two_values() -> None:
    one = spec(metrics=["revenue"], dimensions=["make"], analysis="comparison",
               filters=[{"domain": "Make", "values": ["Tata"]}])
    two = spec(metrics=["revenue"], dimensions=["make"], analysis="comparison",
               filters=[{"domain": "Make", "values": ["Tata", "Mahindra"]}])
    assert codes(auto(), one) == ["compare_values_required"]
    assert codes(auto(), two) == []


def test_running_total_rejects_ratio_metrics() -> None:
    report = auto().inspect(spec(metrics=["average_selling_price"], dimensions=["month"], analysis="running_total"))
    assert report.issues[0].code == "metric_not_additive"
    assert report.issues[0].fixes[0].value == "moving_average"


def test_actual_vs_target_rules() -> None:
    assert codes(auto(), spec(metrics=["orders"], dimensions=["make"], analysis="actual_vs_target")) == ["target_metric"]
    assert codes(auto(), spec(metrics=["revenue"], dimensions=["region"], analysis="actual_vs_target")) == [
        "target_dimension"
    ]
    region = spec(metrics=["revenue"], dimensions=["make"], analysis="actual_vs_target",
                  filters=[{"domain": "Region", "values": ["North"]}])
    assert codes(auto(), region) == ["target_filter"]
    assert codes(auto(), spec(metrics=["revenue"], dimensions=["make", "month"], analysis="actual_vs_target")) == []


def test_insurance_blocks_fan_out_combinations() -> None:
    assert codes(ins(), spec(metrics=["gross_written_premium"], dimensions=["claim_status"])) == ["dimension_incompatible"]
    assert codes(ins(), spec(metrics=["loss_ratio"], dimensions=["region"])) == ["metric_unsupported"]
    assert codes(ins(), spec(metrics=["claims_paid"], dimensions=["agent"])) == []


def test_unavailable_options_carry_reasons() -> None:
    report = auto().inspect(spec(metrics=["revenue"], dimensions=["salesperson"]))
    moving = next(o for o in report.analyses if o.id == "moving_average")
    assert not moving.available and "time dimension" in (moving.reason or "")
    ranking = next(o for o in report.analyses if o.id == "ranking")
    assert ranking.available


def test_suggestions_are_valid_and_role_aware() -> None:
    catalog = auto()
    suggestions = catalog.suggestions(spec(metrics=["revenue"], dimensions=["dealer"]))
    labels = [s.label for s in suggestions]
    assert "Dealer ranking" not in labels or labels.index("Dealer ranking") == 0
    assert any("dealer" in label.lower() for label in labels)
    for suggestion in suggestions:
        assert catalog.inspect(suggestion.spec).valid, suggestion.label
    assert len(labels) == len(set(labels))


def test_custom_date_validation() -> None:
    bad = spec(metrics=["revenue"], date_preset="custom", date_from="2025-05-01", date_to="2025-01-01")
    assert codes(auto(), bad) == ["date_order"]


# -- SQL -------------------------------------------------------------------------------


def test_last_12_months_is_bounded_and_anchored_with_lookback() -> None:
    q = compile_builder_query(
        spec(metrics=["revenue"], dimensions=["month"], analysis="moving_average", window=3,
             date_preset="last_12_months"),
        auto(),
    )
    assert "MAX(fact_sales_latest.sales_date)" in q.sql
    assert "INTERVAL '11 months') - INTERVAL '2 months'" in q.sql
    assert "ROWS BETWEEN 2 PRECEDING AND CURRENT ROW" in q.sql
    assert "WHERE month >= date_trunc('month'" in q.sql
    assert q.date_label == "Last 12 months"


@pytest.mark.parametrize(
    "analysis",
    ["basic", "trend", "running_total", "period_growth", "yoy_growth", "moving_average"],
)
def test_every_time_analysis_respects_the_date_filter(analysis: str) -> None:
    q = compile_builder_query(
        spec(metrics=["units_sold"], dimensions=["month"], analysis=analysis, date_preset="last_12_months"),
        auto(),
    )
    assert "f.sales_date >=" in q.sql and "f.sales_date <" in q.sql


def test_top_n_per_group_and_dense_rank() -> None:
    per_group = compile_builder_query(
        spec(metrics=["revenue"], dimensions=["make", "model"], analysis="top_n_per_group", limit=3), auto()
    )
    assert "ROW_NUMBER() OVER (PARTITION BY make ORDER BY revenue DESC" in per_group.sql
    assert "row_number <= 3" in per_group.sql
    dense = compile_builder_query(
        spec(metrics=["revenue"], dimensions=["dealer"], analysis="ranking", rank_method="dense_rank"), auto()
    )
    assert "DENSE_RANK() OVER (ORDER BY revenue DESC" in dense.sql


def test_yoy_uses_calendar_exact_self_join() -> None:
    q = compile_builder_query(
        spec(metrics=["units_sold"], dimensions=["month", "make"], analysis="yoy_growth"), auto()
    )
    assert "prev.month = (cur.month - INTERVAL '12 months')::date" in q.sql
    assert "prev.make IS NOT DISTINCT FROM cur.make" in q.sql
    assert q.value_column == "yoy_growth_pct"


def test_contribution_has_share_and_cumulative() -> None:
    q = compile_builder_query(spec(metrics=["claims_paid"], dimensions=["line_of_business"],
                                   analysis="contribution"), ins())
    assert "claims_paid_share_pct" in q.sql and "cumulative_share_pct" in q.sql


def test_actual_vs_target_uses_complete_months_and_full_join() -> None:
    q = compile_builder_query(
        spec(metrics=["units_sold"], dimensions=["make"], analysis="actual_vs_target",
             filters=[{"domain": "Make", "values": ["Tata"]}]),
        auto(),
    )
    assert "SUM(t.target_units)" in q.sql
    assert "FULL OUTER JOIN target USING (make)" in q.sql
    assert "v.make = 'Tata'" in q.sql and "t.make = 'Tata'" in q.sql


def test_growth_contribution_compares_equal_windows() -> None:
    q = compile_builder_query(spec(metrics=["revenue"], dimensions=["model"], analysis="growth_contribution",
                                   date_preset="last_3_months"), auto())
    assert "contribution_to_change_pct" in q.sql
    assert "period_bucket" in q.sql


def test_custom_window_end_is_inclusive() -> None:
    window = date_window("custom", "2025-01-01", "2025-03-31", "ANCHOR")
    assert window is not None
    assert window.start == "DATE '2025-01-01'"
    assert window.end == "(DATE '2025-03-31' + INTERVAL '1 day')"


def test_filter_values_are_escaped() -> None:
    q = compile_builder_query(
        spec(metrics=["revenue"], dimensions=["model"], filters=[{"domain": "Make", "values": ["O'Brien"]}]),
        auto(),
    )
    assert "'O''Brien'" in q.sql


def test_driver_query_compares_complete_periods() -> None:
    compiled = driver_sql(spec(metrics=["revenue"], dimensions=["month"]), auto(), grain="month", dimension="model")
    assert compiled is not None
    assert "period_start" in compiled[0]


# -- charts and insight ------------------------------------------------------------------


def _rows_trend() -> list[dict[str, Any]]:
    return [{"month": f"2026-0{i}-01", "revenue": 100.0 + 10 * i} for i in range(1, 7)]


def test_time_by_category_chart_is_pivoted() -> None:
    q = compile_builder_query(spec(metrics=["revenue"], dimensions=["month", "make"], analysis="trend"), auto())
    rows = [
        {"month": "2026-01-01", "make": "Tata", "revenue": 10.0},
        {"month": "2026-01-01", "make": "Kia", "revenue": 5.0},
        {"month": "2026-02-01", "make": "Tata", "revenue": 12.0},
    ]
    chart, viz = build_chart(q, ["month", "make", "revenue"], rows, "auto")
    assert chart is not None and viz == "line"
    assert chart.series == ["Tata", "Kia"]
    assert chart.points[0] == {"month": "2026-01-01", "Tata": 10.0, "Kia": 5.0}


def test_moving_average_chart_overlays_actual_and_average() -> None:
    q = compile_builder_query(spec(metrics=["revenue"], dimensions=["month"], analysis="moving_average"), auto())
    rows = [{"month": "2026-01-01", "revenue": 1.0, "moving_avg_revenue": None}]
    chart, _ = build_chart(q, ["month", "revenue", "moving_avg_revenue"], rows, "auto")
    assert chart is not None and chart.series == ["revenue", "moving_avg_revenue"]


def test_trend_insight_names_change_and_skips_partial_month() -> None:
    q = compile_builder_query(spec(metrics=["revenue"], dimensions=["month"], analysis="trend"), auto())
    rows = _rows_trend()
    narration = build_narration(
        InsightContext(query=q, columns=["month", "revenue"], rows=rows, metric_label="Revenue",
                       partial_period="Jun 2026")
    )
    assert narration is not None
    assert narration.summary.startswith("Revenue increased")
    assert "May 2026" in narration.summary
    assert any("still in progress" in h for h in narration.highlights)


def test_actual_vs_target_insight() -> None:
    q = compile_builder_query(spec(metrics=["revenue"], dimensions=["make"], analysis="actual_vs_target"), auto())
    rows = [
        {"make": "Tata", "actual": 90.0, "target": 100.0, "variance": -10.0, "achievement_pct": 90.0},
        {"make": "Kia", "actual": 120.0, "target": 100.0, "variance": 20.0, "achievement_pct": 120.0},
    ]
    narration = build_narration(
        InsightContext(query=q, columns=list(rows[0]), rows=rows, metric_label="Revenue")
    )
    assert narration is not None
    assert "105.0% of target" in narration.summary
    assert any("1 of 2 brands" in h for h in narration.highlights)


def test_partial_period_detection() -> None:
    from datetime import date

    q = compile_builder_query(spec(metrics=["revenue"], dimensions=["month"]), auto())
    rows = [{"month": "2026-08-01"}, {"month": "2026-09-01"}]
    assert _partial_period(q, date(2026, 9, 12), rows) == "Sep 2026"
    assert _partial_period(q, date(2026, 9, 30), rows) is None


def test_assist_maps_prompt_to_valid_builder_spec() -> None:
    catalog = auto()
    plan = understand_question(Industry.AUTOMOTIVE, "monthly revenue trend for the last 12 months")
    result = assist_spec(plan, catalog)
    assert result.metrics == ["revenue"]
    assert "month" in result.dimensions
    assert result.date_preset == "last_12_months"
    assert catalog.inspect(result).valid
