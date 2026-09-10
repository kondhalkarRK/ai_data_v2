"""KPI / dashboard response schemas."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import Field

from app.schemas.common import ApiModel

WindowId = Literal["ytd", "rolling_12m", "full", "fy_current", "fy_previous"]


class KpiCard(ApiModel):
    id: str
    label: str
    value: float | None = None
    formatted: str
    format: str = "number"
    formula: str | None = None
    delta: float | None = None
    meta: dict[str, Any] = Field(default_factory=dict)


class KpiSeriesPoint(ApiModel):
    period: str
    values: dict[str, float | None]


class NamedValue(ApiModel):
    name: str
    value: float
    formatted: str


class KpiFilterOptions(ApiModel):
    windows: list[dict[str, str]]
    lobs: list[str] = Field(default_factory=list)
    regions: list[str] = Field(default_factory=list)
    makes: list[str] = Field(default_factory=list)
    scenario_available: bool = False


class KpiSummaryResponse(ApiModel):
    industry: str
    window: WindowId
    window_label: str
    start_date: str | None = None
    end_date: str | None = None
    filters: dict[str, str | None]
    cards: list[KpiCard]
    series: list[KpiSeriesPoint]
    breakdowns: dict[str, list[NamedValue]]
    scenario_available: bool = False
    compare_enabled: bool = True


class ScenarioRequest(ApiModel):
    metric: str = "revenue"
    change_type: Literal["percent", "absolute"] = "percent"
    change_value: float = 10.0
    direction: Literal["up", "down"] = "up"


class ScenarioResponse(ApiModel):
    available: bool
    message: str
    actual: float | None = None
    scenario: float | None = None
    delta: float | None = None
    narrative: str | None = None
