"""Versioned automotive BI contracts. No client SQL or permission fields."""

from datetime import date
from typing import Literal
from uuid import UUID

from pydantic import Field, model_validator

from app.schemas.analytics_workspace import WorkspacePanel
from app.schemas.askwiz import StrictModel


class BiPanel(WorkspacePanel):
    grain: Literal["day", "week", "month", "quarter", "year"] | None = None
    section: str = Field(default="Analysis", max_length=80)
    date_intent: (
        Literal["yesterday", "last week", "this week", "last month", "this month", "last quarter"]
        | None
    ) = None
    calculation: Literal["z_score", "index_to_average"] | None = None

    @model_validator(mode="after")
    def single_metric(self) -> "BiPanel":
        if len(self.spec.metrics) != 1:
            raise ValueError("Each query has one governed metric; add a panel for another metric.")
        return self


class BiPlan(StrictModel):
    version: Literal[2] = 2
    title: str = Field(min_length=1, max_length=160)
    answer_kind: Literal["single_value", "analysis", "report", "dashboard"] = "analysis"
    panels: list[BiPanel] = Field(min_length=1, max_length=6)
    assumptions: list[str] = Field(default_factory=list, max_length=6)
    report_filter: "BiReportFilter | None" = None

    @model_validator(mode="after")
    def shape(self) -> "BiPlan":
        if len({p.id for p in self.panels}) != len(self.panels):
            raise ValueError("Panel IDs must be unique.")
        if self.answer_kind == "single_value" and (
            len(self.panels) != 1 or self.panels[0].kind != "kpi"
        ):
            raise ValueError("A single-value answer must contain one KPI.")
        return self


class BiProposal(StrictModel):
    kind: Literal["answer", "clarification", "unsupported"]
    message: str = Field(min_length=1, max_length=1200)
    plan: BiPlan | None = None

    @model_validator(mode="after")
    def shape(self) -> "BiProposal":
        if (self.kind == "answer") != (self.plan is not None):
            raise ValueError("Only an answer must contain a report plan.")
        return self


class BiTurn(StrictModel):
    id: UUID
    question: str
    answer: str
    kind: Literal["answer", "clarification", "unsupported", "error", "edit"]
    code: str | None = None
    changed_panel_ids: list[str] = Field(default_factory=list)


class BiUsage(StrictModel):
    llm_calls: int = 0
    tokens: int = 0
    usage_complete: bool = True
    elapsed_ms: float = 0
    validation_queries: int = 0


class BiPending(StrictModel):
    question: str
    clarification: str
    selected_panel_id: str | None = None


class BiState(StrictModel):
    plan: BiPlan | None = None
    previous: BiPlan | None = None
    pending: BiPending | None = None
    turns: list[BiTurn] = Field(default_factory=list)
    usage: BiUsage = Field(default_factory=BiUsage)
    advanced_sql: dict[str, str] = Field(default_factory=dict)


class BiReport(StrictModel):
    id: UUID
    revision: int
    title: str
    saved: bool
    state: BiState
    warning: str | None = None


class BiCreate(StrictModel):
    id: UUID
    source: Literal["analysis", "board", "workspace"] | None = None
    source_id: UUID | None = None

    @model_validator(mode="after")
    def paired_source(self) -> "BiCreate":
        if bool(self.source) != bool(self.source_id):
            raise ValueError("Import requires both source and sourceId.")
        return self


class BiTurnRequest(StrictModel):
    request_id: UUID
    revision: int = Field(ge=1)
    question: str = Field(default="", max_length=2000)
    selected_panel_id: str | None = Field(default=None, max_length=80)
    action: Literal[
        "ask",
        "save",
        "undo",
        "refresh",
        "remove",
        "move_up",
        "move_down",
        "visualize",
        "rename",
        "filter",
    ] = "ask"
    value: str | None = Field(default=None, max_length=160)
    report_filter: "BiReportFilter | None" = None


class BiReportFilter(StrictModel):
    period: Literal["year", "month", "week"]
    year: int = Field(ge=2000, le=2100)
    month: int | None = Field(default=None, ge=1, le=12)
    week_start: date | None = None
    make: str | None = Field(default=None, max_length=100)
    region: str | None = Field(default=None, max_length=100)

    @model_validator(mode="after")
    def period_fields(self) -> "BiReportFilter":
        if self.period == "month" and self.month is None:
            raise ValueError("Select a month.")
        if self.period == "week" and (
            self.week_start is None
            or self.week_start.weekday() != 0
            or self.week_start.year != self.year
        ):
            raise ValueError("Select a Monday in the chosen year.")
        if self.make is not None and not self.make.strip():
            self.make = None
        if self.region is not None and not self.region.strip():
            self.region = None
        return self


class BiRunRequest(StrictModel):
    revision: int = Field(ge=1)
    panel_id: str = Field(min_length=1, max_length=80)


class BiNarrationRequest(StrictModel):
    revision: int = Field(ge=1)
    evidence: list[str] = Field(min_length=1, max_length=6)


class BiNarration(StrictModel):
    paragraphs: list[str]
    ai_used: bool
    usage: BiUsage
    limitation: str | None = None
