"""Versioned language-understanding contract. It contains intent, never executable SQL.

Batch 1 produces routing previews only. Authority and capability to execute are separate.
"""

from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

Outcome = Literal[
    "conversation",
    "general_knowledge",
    "app_help",
    "data_quality",
    "previous_sql",
    "definition",
    "analytics",
    "investigation",
    "implications",
    "report",
    "documents",
    "clarification",
    "unsupported",
]
Aggregation = Literal["sum", "count", "count_distinct", "avg", "min", "max", "ratio"]
Grain = Literal["day", "week", "month", "quarter", "half", "year"]


class ContractModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid", strict=True, allow_inf_nan=False, str_strip_whitespace=True
    )


class RequestedMeasure(ContractModel):
    id: str = Field(min_length=1, max_length=120)
    aggregation: Aggregation | None = None


class RequestedFilter(ContractModel):
    field: str = Field(min_length=1, max_length=160)
    operator: Literal["eq", "ne", "in", "not_in", "gt", "gte", "lt", "lte", "is_null", "not_null"]
    values: list[str | int | float | bool] = Field(default_factory=list, max_length=32)
    entity_ids: list[str] = Field(default_factory=list, max_length=32)

    @model_validator(mode="after")
    def operands(self) -> RequestedFilter:
        if self.operator in {"is_null", "not_null"}:
            if self.values or self.entity_ids:
                raise ValueError("Null filters cannot have operands")
        elif not self.values and not self.entity_ids:
            raise ValueError("Filter requires values or approved entity IDs")
        elif self.values and self.entity_ids:
            raise ValueError("Use either typed values or entity IDs, not both")
        elif self.operator not in {"in", "not_in"} and len(self.values or self.entity_ids) != 1:
            raise ValueError("Scalar filter requires one operand")
        return self


class RequestedPeriod(ContractModel):
    label: str = Field(min_length=1, max_length=100)
    start: date | None = None
    end_exclusive: date | None = None
    relative: (
        Literal[
            "this_month",
            "last_month",
            "this_quarter",
            "last_quarter",
            "this_year",
            "last_year",
            "ytd",
            "fytd",
            "last_n_days",
            "last_n_months",
            "last_n_quarters",
            "last_n_years",
            "available_history",
        ]
        | None
    ) = None
    count: int | None = Field(default=None, ge=1, le=120)

    @model_validator(mode="after")
    def boundaries(self) -> RequestedPeriod:
        if bool(self.start) != bool(self.end_exclusive):
            raise ValueError("Both explicit boundaries are required")
        if self.start and self.end_exclusive and self.start >= self.end_exclusive:
            raise ValueError("Period must have positive length")
        if self.relative and self.start:
            raise ValueError("Use relative or explicit period, not both")
        if not self.relative and not self.start:
            raise ValueError("Period needs boundaries or a relative reference")
        if self.relative and self.relative.startswith("last_n_") and self.count is None:
            raise ValueError("Relative window requires a count")
        return self


class RequestedComparison(ContractModel):
    kind: Literal["period", "members", "actual_target", "benchmark"]
    current: RequestedPeriod | None = None
    baseline: RequestedPeriod | None = None
    baseline_reference: (
        Literal["previous_period", "same_period_last_year", "approved_target"] | None
    ) = None
    member_ids: list[str] = Field(default_factory=list, max_length=32)
    alignment: Literal["full_period", "same_elapsed", "unspecified"] = "unspecified"


class RequestedWindow(ContractModel):
    operation: Literal["running_total", "moving_average", "period_growth", "contribution"]
    measure_ids: list[str] = Field(min_length=1, max_length=16)
    partition_by: list[str] = Field(default_factory=list, max_length=12)
    order_by: str = Field(min_length=1, max_length=160)
    size: int | None = Field(default=None, ge=1, le=120)
    reset: Literal["none", "calendar_year", "fiscal_year", "quarter", "unspecified"] = "unspecified"


class RequestedRanking(ContractModel):
    measure_id: str
    basis: Literal["value", "absolute_change", "percent_change", "unspecified"] = "unspecified"
    direction: Literal["asc", "desc"] = "desc"
    limit: int = Field(default=10, ge=1, le=200)
    ties: Literal["include", "limit", "unspecified"] = "unspecified"
    include_both_ends: bool = False
    partition_by: list[str] = Field(default_factory=list, max_length=12)


class MeasureOperation(ContractModel):
    """Post-aggregation operation; never overrides an approved base formula."""

    operation: Aggregation
    measure_ids: list[str] = Field(min_length=1, max_length=16)
    group_by: list[str] = Field(default_factory=list, max_length=12)


class MeasureFilter(ContractModel):
    measure_id: str
    operator: Literal["eq", "ne", "gt", "gte", "lt", "lte"]
    value: int | float


class EvidenceTask(ContractModel):
    id: str = Field(min_length=1, max_length=40)
    source: Literal["database", "glossary", "documents", "previous_result", "data_quality"]
    depends_on: list[str] = Field(default_factory=list, max_length=8)


class RequestedChangeCondition(ContractModel):
    measure_id: str = Field(min_length=1, max_length=120)
    basis: Literal["change", "percent_change"] = "change"
    operator: Literal["gt", "gte", "lt", "lte", "eq", "ne"]
    value: int | float = 0


class RequestedAnalysisTask(ContractModel):
    """Compact interpretation inventory; server constructs outputs and SQL later."""

    id: str = Field(pattern=r"^[a-z][a-z0-9_]{0,39}$")
    operation: Literal[
        "aggregate", "select_extreme", "select_ranked", "compare", "contributors", "history"
    ]
    measures: list[str] = Field(default_factory=list, max_length=16)
    group_by: list[str] = Field(default_factory=list, max_length=12)
    time_grain: Grain | None = None
    source: str | None = Field(default=None, pattern=r"^[a-z][a-z0-9_]{0,39}$")
    binding_kind: Literal["entity_set", "period"] | None = None
    binding_field: str | None = Field(default=None, max_length=160)
    ranking: RequestedRanking | None = None
    change_conditions: list[RequestedChangeCondition] = Field(default_factory=list, max_length=8)

    @model_validator(mode="after")
    def references(self) -> RequestedAnalysisTask:
        if bool(self.binding_kind) != bool(self.binding_field):
            raise ValueError("A binding requires both its kind and approved field")
        if self.binding_kind and not self.source:
            raise ValueError("A binding requires a preceding source task")
        if self.operation in {"select_extreme", "select_ranked"} and (
            not self.source or self.binding_kind or not self.ranking
        ):
            raise ValueError("Selection requires an input and explicit ranking")
        if (
            self.source
            and not self.binding_kind
            and self.operation not in {"select_extreme", "select_ranked"}
        ):
            raise ValueError("A dependency must declare how its result is used")
        return self


class InterpretedRequest(ContractModel):
    version: Literal[1] = 1
    outcome: Outcome
    additional_outcomes: list[Outcome] = Field(default_factory=list, max_length=4)
    summary: str = Field(min_length=1, max_length=300)
    measures: list[RequestedMeasure] = Field(default_factory=list, max_length=16)
    entity_ids: list[str] = Field(default_factory=list, max_length=32)
    filters: list[RequestedFilter] = Field(default_factory=list, max_length=24)
    group_by: list[str] = Field(default_factory=list, max_length=12)
    time_grain: Grain | None = None
    period: RequestedPeriod | None = None
    comparisons: list[RequestedComparison] = Field(default_factory=list, max_length=8)
    windows: list[RequestedWindow] = Field(default_factory=list, max_length=8)
    operations: list[MeasureOperation] = Field(default_factory=list, max_length=8)
    measure_filters: list[MeasureFilter] = Field(default_factory=list, max_length=8)
    ranking: RequestedRanking | None = None
    definition_terms: list[str] = Field(default_factory=list, max_length=8)
    followup: bool = False
    changed_fields: list[
        Literal[
            "measures",
            "entity_ids",
            "filters",
            "group_by",
            "time_grain",
            "period",
            "comparisons",
            "windows",
            "operations",
            "measure_filters",
            "ranking",
            "analysis_tasks",
        ]
    ] = Field(default_factory=list, max_length=12)
    clear_filters: list[str] = Field(default_factory=list, max_length=12)
    unresolved: list[str] = Field(default_factory=list, max_length=12)
    clarification: str | None = Field(default=None, min_length=1, max_length=240)
    assumptions: list[str] = Field(default_factory=list, max_length=8)
    evidence: list[EvidenceTask] = Field(default_factory=list, max_length=12)
    reply: str | None = Field(default=None, max_length=1400)
    analysis_tasks: list[RequestedAnalysisTask] = Field(default_factory=list, max_length=4)

    @model_validator(mode="after")
    def consistent(self) -> InterpretedRequest:
        ids = [measure.id for measure in self.measures]
        if len(ids) != len(set(ids)):
            raise ValueError("Measures must be unique by semantic identity")
        if (self.unresolved or self.outcome == "clarification") and not self.clarification:
            raise ValueError("Unresolved requests require a focused clarification")
        outcomes = {self.outcome, *self.additional_outcomes}
        if outcomes & {"analytics", "investigation"} and not ids and not self.clarification:
            raise ValueError("Analytical outcome requires approved measures")
        if "definition" in [self.outcome, *self.additional_outcomes] and not self.definition_terms:
            raise ValueError("Definition outcome requires approved terms")
        for window in self.windows:
            if not set(window.measure_ids) <= set(ids):
                raise ValueError("Window refers to an unrequested measure")
        if self.ranking and self.ranking.measure_id not in ids:
            raise ValueError("Ranking refers to an unrequested measure")
        if any(not set(op.measure_ids) <= set(ids) for op in self.operations):
            raise ValueError("Operation refers to an unrequested measure")
        if any(f.measure_id not in ids for f in self.measure_filters):
            raise ValueError("Measure filter refers to an unrequested measure")
        if not self.clarification:
            for comparison in self.comparisons:
                if comparison.kind == "period" and (
                    not (comparison.current or self.period)
                    or not (comparison.baseline or comparison.baseline_reference)
                ):
                    raise ValueError("Period comparison must retain current and baseline")
                if comparison.kind == "members" and len(set(comparison.member_ids)) < 2:
                    raise ValueError("Member comparison needs every comparison member")
        completed: set[str] = set()
        for task in self.evidence:
            if task.id in completed or not set(task.depends_on) <= completed:
                raise ValueError("Evidence tasks must have unique IDs in dependency order")
            completed.add(task.id)
        completed = set()
        for task in self.analysis_tasks:
            if task.id in completed or (task.source and task.source not in completed):
                raise ValueError("Analytical inventory needs ordered unique task IDs")
            if task.measures and not set(task.measures) <= set(ids):
                raise ValueError("Analytical tasks cannot invent unrequested measures")
            completed.add(task.id)
        if self.analysis_tasks and self.outcome not in {"analytics", "investigation"}:
            raise ValueError("Dependent analysis is only available for database questions")
        return self
