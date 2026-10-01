"""Executive KPI cockpit (automotive) response schemas."""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from app.schemas.common import ApiModel


class CockpitPeriod(ApiModel):
    label: str
    start: str
    end: str
    prior_label: str
    prior_start: str
    prior_end: str
    data_as_of: str
    plan_months_label: str | None = None


class MetricKpi(ApiModel):
    value: float
    prior: float
    growth: float | None = None


class LeaderKpi(ApiModel):
    name: str
    make: str | None = None
    revenue: float
    share: float
    share_change: float | None = None
    growth: float | None = None


class CockpitKpis(ApiModel):
    revenue: MetricKpi
    units: MetricKpi
    orders: MetricKpi
    avg_price: MetricKpi
    top_model: LeaderKpi | None = None
    top_make: LeaderKpi | None = None


class TrendPoint(ApiModel):
    month: str
    revenue: float | None = None
    units: float | None = None
    prior_revenue: float | None = None
    forecast_revenue: float | None = None
    forecast_units: float | None = None
    in_period: bool = False
    partial: bool = False
    peak: bool = False
    growth_period: bool = False


class TrendEvent(ApiModel):
    month: str
    label: str
    kind: Literal["festive", "shock"] = "festive"


class RankedItem(ApiModel):
    key: str
    name: str
    detail: str | None = None
    group: str | None = None
    revenue: float
    units: float
    prior_revenue: float = 0.0
    growth: float | None = None
    share: float = 0.0
    prior_share: float | None = None


class SunburstNode(ApiModel):
    name: str
    dimension: Literal["make", "model", "engine_type"]
    revenue: float
    units: float
    children: list[SunburstNode] = Field(default_factory=list)


class HeatCell(ApiModel):
    row: str
    col: str
    revenue: float
    share: float
    growth: float | None = None


class HeatMatrix(ApiModel):
    rows: list[str]
    cols: list[str]
    cells: list[HeatCell]


class BulletMetric(ApiModel):
    label: str
    actual: float
    target: float | None = None
    achievement: float | None = None
    format: Literal["currency", "integer"] = "integer"


class MakeAchievement(ApiModel):
    make: str
    actual_units: float
    target_units: float
    achievement: float


class CockpitPlan(ApiModel):
    months_label: str | None = None
    revenue: BulletMetric
    units: BulletMetric
    forecast_revenue: BulletMetric
    forecast_units: BulletMetric
    target_note: str | None = None
    forecast_note: str | None = None
    by_make: list[MakeAchievement] = Field(default_factory=list)


class CockpitInsight(ApiModel):
    id: str
    tone: Literal["positive", "negative", "neutral"]
    headline: str
    detail: str
    metric: str | None = None
    filter_dimension: str | None = None
    filter_value: str | None = None


class CockpitResponse(ApiModel):
    period: CockpitPeriod
    applied_filters: dict[str, str] = Field(default_factory=dict)
    empty: bool = False
    kpis: CockpitKpis
    trend: list[TrendPoint]
    events: list[TrendEvent]
    zones: list[RankedItem]
    states: list[RankedItem]
    cities: list[RankedItem]
    dealers: list[RankedItem]
    sunburst: list[SunburstNode]
    top_models_by_revenue: list[RankedItem]
    top_models_by_units: list[RankedItem]
    fuel_mix: list[RankedItem]
    body_mix: list[RankedItem]
    heat: HeatMatrix
    plan: CockpitPlan
    insights: list[CockpitInsight]
    computed_at: str


class OptionItem(ApiModel):
    value: str
    label: str
    group: str | None = None


class CockpitOptions(ApiModel):
    years: list[int]
    makes: list[OptionItem]
    models: list[OptionItem]
    engine_types: list[OptionItem]
    car_types: list[OptionItem]
    zones: list[OptionItem]
    states: list[OptionItem]
    dealers: list[OptionItem]
    salespeople: list[OptionItem] = Field(default_factory=list)
