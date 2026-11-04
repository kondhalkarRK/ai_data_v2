"""Constrained automotive dashboard authoring, not model-authored SQL."""

from __future__ import annotations

from typing import Literal
from uuid import UUID

from pydantic import ConfigDict, Field

from app.schemas.analytics import AnalyticsRunResponse
from app.schemas.common import ApiModel

Metric = Literal["revenue", "units_sold", "orders", "average_selling_price", "active_salespeople"]
Dimension = Literal[
    "day", "month", "make", "model", "region", "state", "city", "dealer", "car_type", "engine_type"
]
Viz = Literal["bar", "line", "area", "pie", "table"]
Recipe = Literal["sales", "weekly", "models", "regions", "growth"]
Period = Literal["this_week", "last_week", "this_month", "last_month", "this_year", "custom"]


class StrictModel(ApiModel):
    model_config = ConfigDict(
        extra="forbid",
        populate_by_name=True,
        alias_generator=ApiModel.model_config["alias_generator"],
    )


class ChartDefinition(StrictModel):
    id: str = Field(max_length=80)
    title: str = Field(max_length=160)
    metric: Metric = "revenue"
    dimension: Dimension = "day"
    viz: Viz = "line"


class BoardDefinition(StrictModel):
    version: Literal[1] = 1
    recipe: Recipe = "sales"
    start: str
    end: str
    prior_start: str
    prior_end: str
    timezone: str
    filters: dict[str, list[str]] = Field(default_factory=dict)
    charts: list[ChartDefinition] = Field(min_length=1, max_length=6)


class CreateBoard(StrictModel):
    prompt: str = Field(default="", max_length=2000)
    recipe: Recipe | None = None


class BoardCommand(StrictModel):
    revision: int = Field(ge=1)
    prompt: str = Field(default="", max_length=2000)
    selected_chart_id: str | None = Field(default=None, max_length=80)
    action: Literal["edit", "undo", "save", "retry", "refresh"] = "edit"


class RevisionRequest(StrictModel):
    revision: int = Field(ge=1)


class Intent(StrictModel):
    operation: Literal["create", "update", "add", "remove", "explain", "clarify"] = "create"
    recipe: Recipe = "sales"
    period: Period | None = None
    start: str | None = None
    end: str | None = None
    count: int = Field(default=4, ge=1, le=6)
    chart_index: int | None = Field(default=None, ge=1, le=6)
    metric: Metric | None = None
    dimension: Dimension | None = None
    viz: Viz | None = None
    title: str | None = Field(default=None, max_length=160)
    filters: dict[str, list[str]] | None = None
    whole_board: bool = False
    clarification: str | None = Field(default=None, max_length=300)
    charts: list[ChartDefinition] | None = Field(default=None, min_length=1, max_length=6)


class BoardView(ApiModel):
    id: UUID
    title: str
    revision: int
    saved: bool
    definition: BoardDefinition
    can_undo: bool
    message: str = ""
    llm_calls: int = 0
    tokens: int = 0


class ChartResult(ApiModel):
    chart_id: str
    result: AnalyticsRunResponse | None = None
    error: str | None = None
    cache_hit: bool = False


class BoardResults(ApiModel):
    board_id: UUID
    revision: int
    charts: list[ChartResult]
    kpis: list[ChartResult]
    elapsed_ms: float
    query_count: int
    cache_hits: int
    computed_at: str


class BoardNarration(ApiModel):
    revision: int
    paragraphs: list[str]
    ai_used: bool
    llm_calls: int = 0
    tokens: int = 0
    limitation: str | None = None
