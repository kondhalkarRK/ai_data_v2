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
    "breakdown",
    "ranking",
    "top_n",
    "bottom_n",
    "contribution",
    "running_total",
    "moving_average",
    "period_growth",
    "trend",
    "variance",
]


class AnalyticsFilterSpec(ApiModel):
    domain: str = Field(description="Value-domain or dimension key, e.g. region, car_type")
    values: list[str] = Field(default_factory=list)
    operator: str = "="


class AnalyticsSpec(ApiModel):
    """Business-facing analysis definition — never exposes physical tables."""

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


class AnalyticsRunRequest(ApiModel):
    spec: AnalyticsSpec


class AnalyticsChartPayload(ApiModel):
    type: str
    x: str
    y: str
    points: list[dict[str, Any]] = Field(default_factory=list)


class AnalyticsInsights(ApiModel):
    executive: str
    analyst: str


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
