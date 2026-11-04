"""Semantic plans for the unified automotive analytics workspace.

Plans carry business specifications only. Execution must revalidate them against
the current catalog and authenticated scope; they never authorize SQL execution.
"""

from typing import Annotated, Literal
from uuid import UUID

from pydantic import ConfigDict, Field, model_validator

from app.schemas.analytics import AnalyticsFilterSpec, AnalyticsRunResponse, AnalyticsSpec
from app.schemas.askwiz import StrictModel


class WorkspaceFilter(AnalyticsFilterSpec):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)
    domain: str = Field(min_length=1, max_length=80)
    values: list[Annotated[str, Field(max_length=300)]] = Field(min_length=1, max_length=50)
    operator: Literal["=", "IN"] = "="


class WorkspaceSpec(AnalyticsSpec):
    model_config = ConfigDict(
        extra="forbid",
        populate_by_name=True,
        alias_generator=AnalyticsSpec.model_config["alias_generator"],
    )
    metrics: list[str] = Field(min_length=1, max_length=8)
    dimensions: list[str] = Field(default_factory=list, max_length=4)
    # Pydantic narrows nested input validation to AnalyticsFilterSpec subclasses.
    filters: list[WorkspaceFilter] = Field(default_factory=list, max_length=8)  # type: ignore[assignment]


class WorkspaceRequest(StrictModel):
    prompt: str = Field(min_length=1, max_length=2000)
    previous: "WorkspacePlan | None" = None
    selected_panel_id: str | None = Field(default=None, max_length=80)
    workspace_id: UUID | None = None
    revision: int | None = Field(default=None, ge=1)


class WorkspacePlanResponse(StrictModel):
    plan: "WorkspacePlan"
    llm_calls: int = 0
    tokens: int = 0
    elapsed_ms: float


class WorkspaceRunRequest(StrictModel):
    panel: "WorkspacePanel"


class WorkspaceRunResponse(StrictModel):
    result: AnalyticsRunResponse
    elapsed_ms: float
    query_count: int
    cache_hit: bool = False
    evidence: str = ""


class WorkspaceNarrationRequest(StrictModel):
    evidence: list[str] = Field(min_length=1, max_length=6)


class WorkspaceNarrationResponse(StrictModel):
    paragraphs: list[str]
    ai_used: bool = False
    llm_calls: int = 0
    tokens: int = 0
    limitation: str | None = None


class WorkspaceSaveRequest(StrictModel):
    plan: "WorkspacePlan"
    id: UUID | None = None
    revision: int | None = Field(default=None, ge=1)
    messages: list["WorkspaceMessage"] = Field(default_factory=list, max_length=50)


class WorkspaceMessage(StrictModel):
    question: str = Field(max_length=2000)
    answer: str = Field(max_length=1000)


class WorkspaceSaved(StrictModel):
    id: UUID
    revision: int
    plan: "WorkspacePlan"
    warning: str | None = None
    messages: list[WorkspaceMessage] = Field(default_factory=list)


class WorkspacePanel(StrictModel):
    id: str = Field(min_length=1, max_length=80)
    title: str = Field(min_length=1, max_length=160)
    kind: Literal["kpi", "chart", "table"]
    spec: WorkspaceSpec
    rationale: str = Field(default="", max_length=400)
    daily: bool = False

    @model_validator(mode="after")
    def validate_shape(self) -> "WorkspacePanel":
        if not self.spec.metrics:
            raise ValueError("Each data panel requires a governed metric.")
        if self.kind == "kpi" and self.spec.dimensions:
            raise ValueError("A KPI panel cannot group by dimensions.")
        if self.kind == "chart" and not self.spec.dimensions:
            raise ValueError("A chart requires a dimension; use a KPI for a single value.")
        return self


class WorkspacePlan(StrictModel):
    answer_kind: Literal["clarification", "single_value", "analysis", "report", "dashboard"]
    title: str = Field(min_length=1, max_length=160)
    panels: list[WorkspacePanel] = Field(default_factory=list, max_length=6)
    clarification: str | None = Field(default=None, max_length=500)
    assumptions: list[str] = Field(default_factory=list, max_length=6)

    @model_validator(mode="after")
    def validate_response(self) -> "WorkspacePlan":
        if self.answer_kind == "clarification":
            if not self.clarification or not self.clarification.strip() or self.panels:
                raise ValueError("Clarification requires a question and no executable panels.")
        elif not self.panels or self.clarification:
            raise ValueError("An answer requires panels and cannot also request clarification.")
        if len({panel.id for panel in self.panels}) != len(self.panels):
            raise ValueError("Panel IDs must be unique.")
        if self.answer_kind == "single_value" and (
            len(self.panels) != 1 or self.panels[0].kind != "kpi"
        ):
            raise ValueError("A single-value answer requires exactly one KPI panel.")
        return self
