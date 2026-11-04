"""Additive, bounded dashboard explanation contracts. No client-authored SQL or values."""

from __future__ import annotations

import uuid
from typing import Literal

from pydantic import ConfigDict, Field

from app.schemas.common import ApiModel


class DashboardContext(ApiModel):
    result_id: str
    industry: str
    semantic_revision: str
    period_label: str
    compare_label: str
    start: str | None = None
    end: str | None = None
    prior_start: str | None = None
    prior_end: str | None = None
    filters: dict[str, str] = Field(default_factory=dict)
    data_as_of: str
    computed_at: str


class DashboardMetric(ApiModel):
    id: str
    label: str
    format: Literal["currency", "integer", "percent"]
    current: float | None = None
    prior: float | None = None
    definition: str
    dimensions: list[str] = Field(default_factory=list)
    supported: bool = True
    unavailable_reason: str | None = None


class DashboardHighlight(ApiModel):
    metric_id: str
    title: str
    body: str
    tone: Literal["positive", "negative", "neutral"] = "neutral"


class DashboardPerformance(ApiModel):
    elapsed_ms: float
    query_count: int
    warehouse_ms: float
    cache_hit: bool


class DashboardAugmentation(ApiModel):
    snapshot_token: str
    context: DashboardContext
    metrics: list[DashboardMetric]
    highlights: list[DashboardHighlight]
    caveats: list[str]
    performance: DashboardPerformance


class DashboardExplainRequest(ApiModel):
    model_config = ConfigDict(
        extra="forbid",
        populate_by_name=True,
        alias_generator=ApiModel.model_config["alias_generator"],
    )

    snapshot_token: str = Field(min_length=1, max_length=4096)
    metric_id: str = Field(min_length=1, max_length=80)
    dimension: str | None = Field(default=None, max_length=40)


class DashboardAskRequest(DashboardExplainRequest):
    question: str = Field(min_length=1, max_length=2000)
    conversation_id: uuid.UUID | None = None


class DashboardContributor(ApiModel):
    label: str
    current: float
    prior: float
    change: float
    filter_key: str | None = None
    filter_value: str | None = None
    filters: dict[str, str] = Field(default_factory=dict)
    residual: bool = False


class DashboardExplanation(ApiModel):
    context: DashboardContext
    metric: DashboardMetric
    dimension: str
    narrative: str
    contributors: list[DashboardContributor] = Field(default_factory=list)
    caveats: list[str] = Field(default_factory=list)
    source_tables: list[str] = Field(default_factory=list)
    sql: str | None = None
    sql_parameters: dict[str, str | int | float | list[int] | None] = Field(default_factory=dict)
    prior_sql_parameters: dict[str, str | int | float | list[int] | None] = Field(
        default_factory=dict
    )
    reconciled: bool = False
    evidence_changed: bool = False
    evidence_computed_at: str | None = None
    query_count: int = 0
    elapsed_ms: float = 0
    conversation_id: uuid.UUID | None = None
    suggested_questions: list[str] = Field(default_factory=list)
