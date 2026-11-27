"""Dependent-analysis proposals, not execution authority.

This contract contains no execution or provider dispatch. A separately gated
compiler/runner consumes reviewed plans. A plan never contains SQL or credentials.
Server-owned review context lives in analytical_plan_validation.
"""

from typing import Literal

from pydantic import Field, model_validator

from app.services.chat.request_contract import ContractModel, InterpretedRequest

Operation = Literal[
    "aggregate", "select_extreme", "select_ranked", "compare", "contributors", "history"
]
OutputRole = Literal[
    "value",
    "current",
    "baseline",
    "change",
    "percent_change",
    "dimension",
    "period_start",
    "period_end",
    "rank",
    "group_count",
]


class PlanOutput(ContractModel):
    name: str = Field(pattern=r"^[a-z][a-z0-9_]{0,62}$")
    role: OutputRole
    semantic_id: str = Field(min_length=1, max_length=160)
    value_type: Literal["decimal", "integer", "string", "date", "boolean"]
    nullable: bool = True


class ResultBinding(ContractModel):
    """Bind canonical field values or a half-open period, never SQL fragments.

    These are REFERENCES only. This batch does not read, serialize, or substitute
    any intermediate values. A future executor must validate actual values again.
    """

    source_step: str = Field(pattern=r"^[a-z][a-z0-9_]{0,39}$")
    kind: Literal["entity_set", "period"]
    source_columns: list[str] = Field(min_length=1, max_length=2)
    target_field: str = Field(min_length=1, max_length=160)
    max_items: int = Field(default=50, ge=1, le=50)
    on_empty: Literal["skip_dependents"] = "skip_dependents"
    on_overflow: Literal["clarify"] = "clarify"

    @model_validator(mode="after")
    def binding_shape(self) -> "ResultBinding":
        if len(set(self.source_columns)) != len(self.source_columns):
            raise ValueError("Binding columns must be distinct")
        if len(self.source_columns) != (2 if self.kind == "period" else 1):
            raise ValueError("Period bindings need start/end; entity bindings need one column")
        return self


class PeriodEligibility(ContractModel):
    mode: Literal["closed_only", "include_partial_labelled"] = "closed_only"
    evidence: Literal["unverified", "semantic_calendar", "load_status", "combined"] = "unverified"
    source_ref: str | None = Field(default=None, min_length=1, max_length=120)

    @model_validator(mode="after")
    def source_required(self) -> "PeriodEligibility":
        if (self.evidence == "unverified") != (self.source_ref is None):
            raise ValueError("Completeness claims need a source; unverified has no source")
        return self


class SelectionPolicy(ContractModel):
    ties: Literal["all"] = "all"
    cohort_cap: int = Field(default=50, ge=1, le=50)
    on_overflow: Literal["clarify"] = "clarify"
    on_empty: Literal["skip_dependents"] = "skip_dependents"
    before_display_limit: Literal[True] = True


class BaselineProvenance(ContractModel):
    kind: Literal["previous_period", "same_period_last_year", "explicit"]
    source: Literal["user", "approved_default"]
    rule_ref: str | None = Field(default=None, min_length=1, max_length=120)

    @model_validator(mode="after")
    def default_requires_rule(self) -> "BaselineProvenance":
        if (self.source == "approved_default") != (self.rule_ref is not None):
            raise ValueError("Only approved defaults have a required rule reference")
        return self


class ChangeCondition(ContractModel):
    measure_id: str = Field(min_length=1, max_length=120)
    basis: Literal["change", "percent_change"] = "change"
    operator: Literal["gt", "gte", "lt", "lte", "eq", "ne"]
    value: int | float = 0


class AnalyticalStep(ContractModel):
    id: str = Field(pattern=r"^[a-z][a-z0-9_]{0,39}$")
    operation: Operation
    label: str = Field(min_length=1, max_length=200)
    request: InterpretedRequest
    depends_on: list[str] = Field(default_factory=list, max_length=3)
    input_step: str | None = Field(default=None, pattern=r"^[a-z][a-z0-9_]{0,39}$")
    bindings: list[ResultBinding] = Field(default_factory=list, max_length=4)
    outputs: list[PlanOutput] = Field(min_length=1, max_length=32)
    baseline: BaselineProvenance | None = None
    eligibility: PeriodEligibility | None = None
    selection: SelectionPolicy | None = None
    change_conditions: list[ChangeCondition] = Field(default_factory=list, max_length=8)

    @model_validator(mode="after")
    def shape(self) -> "AnalyticalStep":
        if len({o.name for o in self.outputs}) != len(self.outputs):
            raise ValueError("Step output names must be unique")
        if len(set(self.depends_on)) != len(self.depends_on):
            raise ValueError("Step dependencies must be unique")
        if self.operation in {"select_extreme", "select_ranked"} and not (
            self.input_step and self.selection and self.request.ranking
        ):
            raise ValueError("Extreme selection needs input, ranking and safe tie policy")
        if self.operation not in {"select_extreme", "select_ranked"} and self.input_step:
            raise ValueError("Only selection transforms an existing step output")
        if self.operation not in {"select_extreme", "select_ranked"} and self.selection:
            raise ValueError("Only selection can declare a cohort selection policy")
        if self.operation in {"compare", "contributors", "history"} and not self.baseline:
            raise ValueError("Change analysis needs an explicit baseline provenance")
        if self.operation in {"aggregate", "select_extreme", "select_ranked"} and self.baseline:
            raise ValueError("A level is not a change; use an explicit comparison step")
        return self


class RequirementCoverage(ContractModel):
    requirement_id: str = Field(min_length=1, max_length=80)
    step_id: str = Field(min_length=1, max_length=40)
    output_columns: list[str] = Field(min_length=1, max_length=32)


class UnansweredRequirement(ContractModel):
    requirement_id: str = Field(min_length=1, max_length=80)
    status: Literal["clarification", "unsupported", "source_unavailable"]
    reason: str = Field(min_length=1, max_length=240)
    question: str | None = Field(default=None, min_length=1, max_length=240)

    @model_validator(mode="after")
    def focused_question(self) -> "UnansweredRequirement":
        if (self.status == "clarification") != (self.question is not None):
            raise ValueError("Only clarification requires a focused question")
        return self


class ReconciliationCheck(ContractModel):
    """An independent headline, not SUM of the same grouped result again."""

    headline_step: str
    contributor_step: str
    measure_id: str
    before_display_limit: Literal[True] = True
    signed_changes: Literal[True] = True


class AnalyticalPlan(ContractModel):
    version: Literal[1] = 1
    plan_id: str = Field(min_length=1, max_length=80)
    source_request_id: str = Field(min_length=1, max_length=80)
    semantic_version: str = Field(min_length=1, max_length=100)
    scope_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    steps: list[AnalyticalStep] = Field(default_factory=list, max_length=4)
    coverage: list[RequirementCoverage] = Field(default_factory=list, max_length=32)
    unanswered: list[UnansweredRequirement] = Field(default_factory=list, max_length=32)
    reconciliations: list[ReconciliationCheck] = Field(default_factory=list, max_length=8)
    # Entire request, including the initial interpretation. Never a per-step budget.
    total_model_calls: int = Field(default=1, ge=1, le=2)

    @model_validator(mode="after")
    def dependency_order(self) -> "AnalyticalPlan":
        seen: set[str] = set()
        for step in self.steps:
            if step.id in seen or not set(step.depends_on) <= seen:
                raise ValueError("Steps need unique IDs in acyclic dependency order")
            references = {b.source_step for b in step.bindings}
            if step.input_step:
                references.add(step.input_step)
            if references != set(step.depends_on):
                raise ValueError("Each dependency needs an explicit input or result binding")
            seen.add(step.id)
        covered = [c.requirement_id for c in self.coverage]
        unanswered = [u.requirement_id for u in self.unanswered]
        if len(covered + unanswered) != len(set(covered + unanswered)):
            raise ValueError("Each requirement must be covered OR explicitly unanswered once")
        if not covered and not unanswered:
            raise ValueError("Plan must account for at least one requirement")
        return self
