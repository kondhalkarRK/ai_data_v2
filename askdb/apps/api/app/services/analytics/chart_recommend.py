"""Chart type recommendation for Analytics Builder."""

from __future__ import annotations

from app.schemas.analytics import AnalyticsSpec, AnalyticsVizKind

_TIME = {"month", "quarter", "year", "date"}


def recommend_viz(spec: AnalyticsSpec) -> AnalyticsVizKind:
    if spec.viz != "auto":
        return spec.viz

    metrics = len(spec.metrics)
    dims = [d.casefold() for d in spec.dimensions]
    dim_count = len(dims)
    has_time = any(d in _TIME or "month" in d or "date" in d for d in dims)

    if spec.analysis == "contribution":
        return "donut"
    if spec.analysis in {"top_n", "bottom_n", "ranking"}:
        return "bar"
    if spec.analysis in {"trend", "running_total", "moving_average", "period_growth"}:
        return "line"
    if metrics == 1 and dim_count == 0:
        return "kpi"
    if metrics >= 2 and dim_count == 1:
        return "scatter"
    if has_time and dim_count <= 2:
        return "area" if spec.analysis == "running_total" else "line"
    if dim_count == 1:
        return "bar"
    if dim_count >= 2:
        return "table"
    return "bar"
