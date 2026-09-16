"""Unit tests for Analytics Builder spec mapping and chart recommend."""

from __future__ import annotations

from app.core.config import Industry
from app.schemas.analytics import AnalyticsSpec
from app.services.analytics.chart_recommend import recommend_viz
from app.services.analytics.spec_to_plan import (
    map_dimension_key,
    map_measure_to_metric,
    spec_to_plan,
)


def test_map_measure_aliases() -> None:
    assert map_measure_to_metric("revenue") == "revenue"
    assert map_measure_to_metric("units_sold") == "units"
    assert map_measure_to_metric("claims_incurred") == "claims_incurred"


def test_map_dimension_aliases() -> None:
    assert map_dimension_key("Region") == "region"
    assert map_dimension_key("car_type") == "car_type"
    assert map_dimension_key("Vehicle Type") == "car_type"
    assert map_dimension_key("month") == "month"


def test_spec_to_plan_top_n() -> None:
    spec = AnalyticsSpec(
        metrics=["revenue"],
        dimensions=["dealer"],
        filters=[],
        analysis="top_n",
        limit=10,
        order_direction="desc",
        viz="auto",
    )
    plan = spec_to_plan(spec, Industry.AUTOMOTIVE, None)
    assert plan.metric == "revenue"
    assert plan.dimensions == ["dealer"]
    assert plan.analysis == "ranking"
    assert plan.order_direction == "desc"
    assert plan.intent == "ranking"
    assert plan.limit == 10


def test_recommend_viz_kpi_and_line() -> None:
    kpi = AnalyticsSpec(metrics=["revenue"], dimensions=[], filters=[], analysis="basic", viz="auto")
    assert recommend_viz(kpi) == "kpi"
    trend = AnalyticsSpec(
        metrics=["revenue"],
        dimensions=["month"],
        filters=[],
        analysis="trend",
        viz="auto",
    )
    assert recommend_viz(trend) == "line"
    contrib = AnalyticsSpec(
        metrics=["revenue"],
        dimensions=["region"],
        filters=[],
        analysis="contribution",
        viz="auto",
    )
    assert recommend_viz(contrib) == "donut"
