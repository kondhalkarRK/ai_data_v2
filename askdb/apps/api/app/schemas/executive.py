"""Executive Intelligence response schemas."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import Field

from app.schemas.common import ApiModel
from app.schemas.kpi import KpiCard, KpiSeriesPoint, NamedValue, WindowId


class HealthComponent(ApiModel):
    kpi_id: str
    label: str
    value: float | None = None
    formatted: str
    weight: float
    contribution: float
    direction: Literal["higher_better", "lower_better"] = "higher_better"


class BusinessHealth(ApiModel):
    score: float | None = None
    label: str
    components: list[HealthComponent] = Field(default_factory=list)
    formula_note: str
    available: bool = False
    unavailable_reason: str | None = None


class AiInsightCard(ApiModel):
    id: str
    category: Literal["risk", "opportunity", "insight", "recommendation"]
    title: str
    body: str
    grounded_on: list[str] = Field(default_factory=list)
    metric_ids: list[str] = Field(default_factory=list)
    explore_focus: list[str] = Field(default_factory=list)


class DataQualityNotice(ApiModel):
    healthy_pct: float | None = None
    label: str
    notices: list[str] = Field(default_factory=list)
    affected_kpi_ids: list[str] = Field(default_factory=list)


class WhatIfPreset(ApiModel):
    id: str
    label: str
    metric: str
    change_value: float
    direction: Literal["up", "down"] = "up"
    supported: bool = True
    unsupported_reason: str | None = None


class SuggestedQuestion(ApiModel):
    id: str
    text: str
    supported: bool = True


class ExecutiveIntelligenceResponse(ApiModel):
    industry: str
    title: str
    tagline: str
    window: WindowId
    window_label: str
    compare_label: str
    start_date: str | None = None
    end_date: str | None = None
    data_as_of: str
    computed_at: str
    cache_ttl_seconds: int = 300
    cards: list[KpiCard]
    series: list[KpiSeriesPoint]
    breakdowns: dict[str, list[NamedValue]]
    health: BusinessHealth
    insights: list[AiInsightCard]
    data_quality: DataQualityNotice
    suggested_questions: list[SuggestedQuestion]
    what_if_presets: list[WhatIfPreset]
    chart_metrics: list[str]
    explore_base_path: str = "/semantic/ontology"


class InsightFeedbackRequest(ApiModel):
    insight_id: str
    vote: Literal["up", "down"]
    grounded_on: list[str] = Field(default_factory=list)
    category: str | None = None
    body_preview: str | None = None


class InsightFeedbackResponse(ApiModel):
    ok: bool
    id: str
