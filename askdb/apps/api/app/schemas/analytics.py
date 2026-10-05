"""Analytics Builder request/response contracts."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import Field

from app.schemas.common import ApiModel

AnalyticsVizKind = Literal[
    "table",
    "bar",
    "line",
    "area",
    "pie",
    "donut",
    "scatter",
    "kpi",
    "heatmap",
    "treemap",
    "auto",
]

AnalyticsAnalysisKind = Literal[
    "basic",
    "trend",
    "comparison",
    "top_n",
    "bottom_n",
    "top_n_per_group",
    "ranking",
    "contribution",
    "running_total",
    "moving_average",
    "period_growth",
    "yoy_growth",
    "growth_contribution",
    "actual_vs_target",
    "above_average",
    # Saved before the redesign: "breakdown" is Standard, "variance" is Above average.
    "breakdown",
    "variance",
]

RankMethod = Literal["rank", "dense_rank", "row_number"]


class AnalyticsFilterSpec(ApiModel):
    domain: str = Field(description="Value-domain or dimension key, e.g. region, car_type")
    values: list[str] = Field(default_factory=list)
    operator: str = "="


class AnalyticsSpec(ApiModel):
    """Business-facing analysis definition; never exposes physical tables."""

    metrics: list[str] = Field(
        default_factory=list,
        description="Semantic measure ids from the pack (first is primary).",
    )
    dimensions: list[str] = Field(
        default_factory=list,
        description="Compiler dimension keys or pack dimension attribute keys.",
    )
    filters: list[AnalyticsFilterSpec] = Field(default_factory=list)
    analysis: AnalyticsAnalysisKind = "basic"
    limit: int = Field(default=25, ge=1, le=500)
    order_direction: Literal["asc", "desc"] = "desc"
    time_grain: str | None = None
    viz: AnalyticsVizKind = "auto"
    date_preset: str | None = None
    date_from: str | None = None
    date_to: str | None = None
    rank_method: RankMethod = "rank"
    window: int = Field(default=3, ge=2, le=24, description="Moving-average periods")


class AnalyticsRunRequest(ApiModel):
    spec: AnalyticsSpec


class AnalyticsChartPayload(ApiModel):
    type: str
    x: str
    y: str
    series: list[str] = Field(default_factory=list)
    points: list[dict[str, Any]] = Field(default_factory=list)
    note: str | None = None


class AnalyticsInsights(ApiModel):
    executive: str
    analyst: str
    narration: dict[str, Any] | None = None


class AnalyticsRunResponse(ApiModel):
    title: str
    columns: list[str]
    rows: list[dict[str, Any]]
    sql: str
    chart: AnalyticsChartPayload | None = None
    recommended_viz: AnalyticsVizKind
    insights: AnalyticsInsights | None = None
    meta: dict[str, Any] = Field(default_factory=dict)


class AnalyticsAssistRequest(ApiModel):
    prompt: str = Field(min_length=1, max_length=2000)


class AnalyticsAssistResponse(ApiModel):
    spec: AnalyticsSpec
    explanation: str
    glossary_hits: list[str] = Field(default_factory=list)


class FilterValueItem(ApiModel):
    value: str
    frequency: int = 0
    label: str | None = None


class FilterValuesResponse(ApiModel):
    domain: str
    label: str
    values: list[FilterValueItem]


class SavedAnalysisCreate(ApiModel):
    title: str = Field(min_length=1, max_length=240)
    spec: AnalyticsSpec
    sql_snapshot: str | None = None
    viz: AnalyticsVizKind = "auto"


class SavedAnalysisUpdate(ApiModel):
    title: str | None = Field(default=None, min_length=1, max_length=240)
    spec: AnalyticsSpec | None = None
    sql_snapshot: str | None = None
    viz: AnalyticsVizKind | None = None


class SavedAnalysisResponse(ApiModel):
    id: UUID
    title: str
    industry: str
    spec: dict[str, Any]
    viz: str
    sql_snapshot: str | None = None
    created_at: datetime
    updated_at: datetime


# --- guided building ---------------------------------------------------------

FixAction = Literal[
    "add_dimension",
    "remove_dimension",
    "set_analysis",
    "set_metric",
    "open_filters",
    "remove_filter",
    "clear_date",
]


class AnalyticsFix(ApiModel):
    """One click that turns an invalid selection into a valid one."""

    label: str
    action: FixAction
    value: str | None = None


class AnalyticsIssue(ApiModel):
    code: str
    severity: Literal["error", "warning"] = "error"
    message: str
    fixes: list[AnalyticsFix] = Field(default_factory=list)


class AnalyticsOption(ApiModel):
    id: str
    label: str
    available: bool = True
    reason: str | None = None


class AnalyticsSuggestion(ApiModel):
    label: str
    description: str
    spec: AnalyticsSpec


class AnalyticsInspection(ApiModel):
    valid: bool
    issues: list[AnalyticsIssue] = Field(default_factory=list)
    analyses: list[AnalyticsOption] = Field(default_factory=list)
    metrics: list[AnalyticsOption] = Field(default_factory=list)
    dimensions: list[AnalyticsOption] = Field(default_factory=list)
    suggestions: list[AnalyticsSuggestion] = Field(default_factory=list)


class AnalyticsInspectRequest(ApiModel):
    spec: AnalyticsSpec


class MetricCapability(ApiModel):
    id: str
    label: str
    description: str | None = None
    format: str
    additive: bool
    supported: bool = True
    reason: str | None = None


class DimensionCapability(ApiModel):
    id: str
    label: str
    group: str
    time: bool = False
    filter_domain: str | None = None


class AnalysisCapability(ApiModel):
    id: str
    label: str
    group: str
    description: str
    requirement: str


class FilterDomainCapability(ApiModel):
    id: str
    label: str


class DatePresetCapability(ApiModel):
    id: str
    label: str


class AnalyticsCapabilities(ApiModel):
    metrics: list[MetricCapability]
    dimensions: list[DimensionCapability]
    analyses: list[AnalysisCapability]
    filter_domains: list[FilterDomainCapability]
    date_presets: list[DatePresetCapability]
    data_as_of: str | None = None
