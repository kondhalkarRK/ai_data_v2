"""Pure review of a dependent-plan proposal. No execution or provider calls.

Coverage is checked against a SEPARATELY supplied requirement inventory. Comparing
a model's plan with its own coverage declarations cannot prove question coverage.
This batch does not extract that inventory from English or wire it into Chat.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import date
from typing import Literal

from pydantic import Field, ValidationError

from app.core.config import Industry
from app.schemas.semantic import SemanticPackResponse
from app.services.chat.analytical_plan import (
    AnalyticalPlan,
    ChangeCondition,
    Operation,
    OutputRole,
    PlanOutput,
)
from app.services.chat.request_capabilities import measure_capabilities
from app.services.chat.request_context import RequestContext, RequestPrincipal, pack_fingerprint
from app.services.chat.request_contract import ContractModel, InterpretedRequest


@dataclass(frozen=True)
class RequiredOutput:
    role: OutputRole
    semantic_id: str


@dataclass(frozen=True)
class RequiredBinding:
    source_requirement: str
    kind: Literal["entity_set", "period"]
    target_field: str


@dataclass(frozen=True)
class ExpectedRequirement:
    """Server-supplied acceptance clause, not an LLM self-certification."""

    id: str
    operation: Operation
    request: InterpretedRequest
    outputs: tuple[RequiredOutput, ...]
    depends_on: tuple[str, ...] = ()  # Requirement IDs, not proposed step IDs.
    change_conditions: tuple[ChangeCondition, ...] = ()
    bindings: tuple[RequiredBinding, ...] = ()


@dataclass(frozen=True)
class CompletenessSource:
    """Pre-authorized evidence descriptor, not a model's completeness assertion.

    Future code must obtain/recheck it from an authoritative scoped source. No
    source is discovered, queried or inferred from MAX(date) in this module.
    """

    reference: str
    kind: Literal["semantic_calendar", "load_status", "combined"]
    scope_fingerprint: str
    revision: str
    start: date | None = None
    end_exclusive: date | None = None
    loaded_data_verified: bool = False


@dataclass(frozen=True)
class PlanReviewContext:
    request_id: str
    principal: RequestPrincipal
    context: RequestContext
    pack: SemanticPackResponse
    requirements: tuple[ExpectedRequirement, ...]
    completeness_sources: tuple[CompletenessSource, ...] = ()
    approved_baseline_rule: str = "previous_equivalent_period_v1"
    max_steps: int = 4
    max_total_model_calls: int = 2
    # Already spent on interpretation/correction for this SAME request.
    model_calls_used: int = 1


class PlanIssue(ContractModel):
    code: str
    severity: Literal["invalid", "clarification", "unsupported"]
    requirement_id: str | None = None
    step_id: str | None = None
    message: str


class PlanReview(ContractModel):
    execution_enabled: Literal[False] = False
    status: Literal["valid", "partial", "clarification", "unsupported", "invalid"]
    proposed_path: Literal["existing", "dependent", "none"]
    issues: list[PlanIssue] = Field(default_factory=list)
    covered_requirements: list[str] = Field(default_factory=list)
    unanswered_requirements: list[str] = Field(default_factory=list)


def scope_fingerprint(binding: str) -> str:
    return hashlib.sha256(binding.encode()).hexdigest()


def _covers_scope(
    actual: InterpretedRequest, expected: InterpretedRequest, *, selection: bool = False
) -> bool:
    # Extra approved measures can share a query. Extra groupings/filters can change
    # the answer and are NOT harmless additions. The independent inventory must
    # already contain any approved comparison defaults. Only a selection transform
    # may introduce ranking relative to its input; coverage still checks it exactly.
    if not {m.id for m in expected.measures} <= {m.id for m in actual.measures}:
        return False
    for field in (
        "filters",
        "group_by",
        "time_grain",
        "period",
        "windows",
        "operations",
        "measure_filters",
        "entity_ids",
        "comparisons",
    ):
        if getattr(actual, field) != getattr(expected, field):
            return False
    return selection or actual.ranking == expected.ranking


def _output_signature(output: PlanOutput) -> tuple[str, str]:
    return output.role, output.semantic_id


def review_plan(plan: AnalyticalPlan, review: PlanReviewContext) -> PlanReview:
    """Validate a proposal; never route, compile, query, retrieve or create a report."""
    issues: list[PlanIssue] = []

    def issue(code, message, *, step=None, requirement=None, severity="invalid"):
        issues.append(
            PlanIssue(
                code=code,
                message=message,
                step_id=step,
                requirement_id=requirement,
                severity=severity,
            )
        )

    # Pydantic objects are mutable; never trust model_copy(update=...) or a mutated
    # instance to have gone through dependency and identifier validation.
    try:
        plan = AnalyticalPlan.model_validate_json(plan.model_dump_json())
    except ValidationError:
        issue("plan_shape", "Plan structure failed validation.")
        return PlanReview(status="invalid", proposed_path="none", issues=issues)

    if (
        review.principal.industry != Industry.AUTOMOTIVE
        or review.pack.summary.industry != Industry.AUTOMOTIVE
        or review.context.binding != review.principal.binding
        or review.context.semantic_version != pack_fingerprint(review.pack)
        or plan.semantic_version != review.context.semantic_version
        or plan.scope_fingerprint != scope_fingerprint(review.principal.binding)
        or plan.source_request_id != review.request_id
        or review.principal.scope.user_id not in {None, review.principal.user_id}
        or (not review.principal.scope.unrestricted and not review.principal.scope.zones)
    ):
        issue(
            "authority_mismatch",
            "Plan does not belong to the current request, scope and semantic version.",
        )
        return PlanReview(status="invalid", proposed_path="none", issues=issues)
    if (
        not 1 <= review.max_steps <= 4
        or not 1 <= review.max_total_model_calls <= 2
        or not 0 <= review.model_calls_used <= review.max_total_model_calls
        or len(plan.steps) > review.max_steps
        or not review.model_calls_used <= plan.total_model_calls <= review.max_total_model_calls
    ):
        issue("budget", "Plan exceeds the shared request budget or understates calls already used.")

    expected = {r.id: r for r in review.requirements}
    if not expected or len(expected) != len(review.requirements):
        issue(
            "requirement_inventory",
            "A separate nonempty, uniquely identified requirement inventory is required.",
        )
    if any(not r.outputs for r in review.requirements):
        issue(
            "requirement_inventory", "Each expected requirement needs verifiable output signatures."
        )
    for req in review.requirements:
        if not set(req.depends_on) <= set(expected) or req.id in req.depends_on:
            issue(
                "requirement_inventory",
                "Expected dependency references are invalid.",
                requirement=req.id,
            )
        if any(b.source_requirement not in req.depends_on for b in req.bindings):
            issue(
                "requirement_inventory",
                "Expected bindings must name expected dependencies.",
                requirement=req.id,
            )
    sources = {s.reference: s for s in review.completeness_sources}
    if len(sources) != len(review.completeness_sources):
        issue("completeness_inventory", "Completeness source references must be unique.")
    steps = {s.id: s for s in plan.steps}
    measures = {m["id"]: m for m in review.context.payload["measures"]}
    fields = review.context.payload["fields"]
    entities = {e["id"]: e for e in review.context.payload["entities"]}
    capabilities = measure_capabilities(review.pack)

    for step in plan.steps:
        request = step.request
        ids = {m.id for m in request.measures}
        if (
            request.outcome not in {"analytics", "investigation"}
            or request.additional_outcomes
            or request.clarification
            or request.unresolved
            or request.reply
            or request.followup
            or request.changed_fields
            or request.clear_filters
            or request.evidence
            or request.definition_terms
            or request.analysis_tasks
        ):
            issue(
                "step_outcome",
                "An analytical step must contain resolved analytical scope only.",
                step=step.id,
            )
        if not ids <= set(measures) or not ids:
            issue(
                "measure_reference", "Step contains an unapproved or missing measure.", step=step.id
            )
        if any(
            m.aggregation and m.aggregation != measures.get(m.id, {}).get("aggregation")
            for m in request.measures
        ):
            issue(
                "formula_override", "Approved measure aggregation cannot be changed.", step=step.id
            )
        for mid in ids & set(measures):
            if capabilities[mid]["status"] != "executable":
                issue(
                    "measure_capability",
                    "This measure needs another registered execution capability.",
                    step=step.id,
                    severity="unsupported",
                )
        referenced_fields = [*request.group_by, *(f.field for f in request.filters)]
        for window in request.windows:
            referenced_fields += [window.order_by, *window.partition_by]
        for operation in request.operations:
            referenced_fields += operation.group_by
        if request.ranking:
            referenced_fields += request.ranking.partition_by
        if not set(referenced_fields) <= set(fields):
            issue("field_reference", "Step references an unapproved field.", step=step.id)
        if not set(request.entity_ids) <= set(entities):
            issue("entity_reference", "Step references an unapproved scoped entity.", step=step.id)
        for comparison in request.comparisons:
            if not set(comparison.member_ids) <= set(entities):
                issue(
                    "entity_reference", "Comparison references an unapproved entity.", step=step.id
                )
        for filt in request.filters:
            if any(
                e not in entities or entities[e]["field"] != filt.field for e in filt.entity_ids
            ):
                issue(
                    "entity_reference",
                    "Filter values do not belong to the scoped field catalog.",
                    step=step.id,
                )
            field_type = fields.get(filt.field, {}).get("type")
            if filt.values and field_type in {"string", "text"}:
                allowed = {e["value"] for e in entities.values() if e["field"] == filt.field}
                if any(v not in allowed for v in filt.values):
                    issue(
                        "entity_reference",
                        "Categorical values are absent from the scoped catalog.",
                        step=step.id,
                    )

        for output in step.outputs:
            metric = output.role in {"value", "current", "baseline", "change", "percent_change"}
            if metric and (
                output.semantic_id not in ids or output.value_type not in {"decimal", "integer"}
            ):
                issue(
                    "output_reference",
                    "Metric output must name a requested measure and numeric type.",
                    step=step.id,
                )
            if output.role == "dimension" and (
                output.semantic_id not in request.group_by
                or output.value_type != _field_type(fields.get(output.semantic_id, {}).get("type"))
            ):
                issue(
                    "output_reference",
                    "Dimension output must retain an approved grouping and its type.",
                    step=step.id,
                )
            if output.role in {"period_start", "period_end"} and (
                output.value_type != "date"
                or fields.get(output.semantic_id, {}).get("type") != "date"
                or not request.time_grain
            ):
                issue(
                    "output_reference",
                    "Period outputs require an approved date field and grain.",
                    step=step.id,
                )
            if output.role in {"rank", "group_count"} and (
                output.value_type != "integer" or output.semantic_id not in ids
            ):
                issue(
                    "output_reference",
                    "Rank/count outputs require a requested measure and integer type.",
                    step=step.id,
                )
        signatures = {_output_signature(o) for o in step.outputs}
        source_comparison = step.input_step and steps[step.input_step].baseline
        required_roles = (
            ("current", "baseline", "change") if step.baseline or source_comparison else ("value",)
        )
        if any((role, mid) not in signatures for mid in ids for role in required_roles):
            issue(
                "measure_output",
                "Every requested measure needs outputs for the operation, including both comparison sides.",
                step=step.id,
            )
        if any(("dimension", field) not in signatures for field in request.group_by):
            issue("grouping_output", "Every grouping must appear in step outputs.", step=step.id)
        if request.ranking:
            role = {
                "value": "value",
                "absolute_change": "change",
                "percent_change": "percent_change",
            }.get(request.ranking.basis)
            if not role or (role, request.ranking.measure_id) not in signatures:
                issue(
                    "ranking_basis",
                    "Ranking must use an explicit basis retained in the output.",
                    step=step.id,
                )

        _review_bindings(step, steps, fields, issue)
        if step.operation == "aggregate" and request.comparisons:
            issue(
                "operation_shape",
                "An aggregate must not silently substitute a comparison.",
                step=step.id,
            )
        if step.change_conditions:
            if step.operation != "compare" or any(
                c.measure_id not in ids for c in step.change_conditions
            ):
                issue(
                    "change_condition",
                    "Change conditions require an explicit comparison and requested measures.",
                    step=step.id,
                )
            if any((c.basis, c.measure_id) not in signatures for c in step.change_conditions):
                issue(
                    "change_condition",
                    "Change predicates must retain the compared values in output.",
                    step=step.id,
                )
        if step.operation in {"select_extreme", "select_ranked"}:
            source = steps[step.input_step]
            if (
                source.operation not in {"aggregate", "compare"}
                or source.request.ranking
                or not _covers_scope(request, source.request, selection=True)
                or request.ranking.basis
                not in (
                    {"value"}
                    if source.operation == "aggregate"
                    else {"absolute_change", "percent_change"}
                )
                or request.ranking.ties != "include"
                or request.ranking.limit > step.selection.cohort_cap
                or (
                    step.operation == "select_extreme"
                    and (source.operation != "aggregate" or request.ranking.limit != 1)
                )
                or request.ranking.include_both_ends
                or request.ranking.partition_by
                or request.windows
                or request.operations
                or step.change_conditions != source.change_conditions
            ):
                issue(
                    "selection_semantics",
                    "Selection must preserve its input scope, rank the requested basis and retain all ties within the safe cohort cap.",
                    step=step.id,
                )
            source_outputs = {_output_signature(o) for o in source.outputs}
            if not signatures <= source_outputs | {("rank", request.ranking.measure_id)}:
                issue(
                    "selection_output",
                    "Selection cannot invent outputs absent from its input.",
                    step=step.id,
                )
            if request.time_grain:
                eligible = step.eligibility
                if not eligible or eligible.mode != "closed_only":
                    issue(
                        "period_eligibility",
                        "Extreme periods must exclude incomplete periods.",
                        step=step.id,
                    )
                elif eligible.evidence in {"unverified", "semantic_calendar"}:
                    issue(
                        "loaded_completeness",
                        "Calendar closure alone does not prove the selected period was fully loaded.",
                        step=step.id,
                        severity="clarification",
                    )

        if step.eligibility and step.eligibility.source_ref:
            source = sources.get(step.eligibility.source_ref)
            if (
                source is None
                or source.kind != step.eligibility.evidence
                or source.scope_fingerprint != plan.scope_fingerprint
                or not source.revision
            ):
                issue(
                    "completeness_source",
                    "Completeness source is not approved for this scoped review.",
                    step=step.id,
                )
            elif (
                step.operation in {"select_extreme", "select_ranked"}
                and request.time_grain
                and not source.loaded_data_verified
            ):
                issue(
                    "loaded_completeness",
                    "Loaded-period completeness is not verified.",
                    step=step.id,
                    severity="clarification",
                )
            elif step.operation in {"select_extreme", "select_ranked"} and request.time_grain:
                period = request.period
                if (
                    not period
                    or not period.start
                    or not period.end_exclusive
                    or not source.start
                    or not source.end_exclusive
                    or not source.start
                    <= period.start
                    < period.end_exclusive
                    <= source.end_exclusive
                ):
                    issue(
                        "completeness_coverage",
                        "Completeness evidence must cover the resolved selection period; resolve relative windows before this check.",
                        step=step.id,
                        severity="clarification",
                    )

        if step.baseline:
            comparisons = request.comparisons
            if len(comparisons) != 1 or comparisons[0].kind != "period":
                issue(
                    "baseline",
                    "This bounded operation needs one explicit period comparison.",
                    step=step.id,
                )
            else:
                comparison = comparisons[0]
                kind = "explicit" if comparison.baseline else comparison.baseline_reference
                if kind != step.baseline.kind:
                    issue(
                        "baseline",
                        "Baseline provenance disagrees with the requested comparison.",
                        step=step.id,
                    )
            if step.baseline.source == "approved_default" and (
                step.baseline.rule_ref != review.approved_baseline_rule
                or step.baseline.kind != "previous_period"
            ):
                issue(
                    "baseline_rule",
                    "Only the approved previous-equivalent-period default is available.",
                    step=step.id,
                )
            if step.operation == "contributors":
                if not request.group_by or any(
                    measures.get(mid, {}).get("aggregation") != "sum" for mid in ids
                ):
                    issue(
                        "contribution_capability",
                        "Initial contribution decomposition requires additive sums and explicit dimensions.",
                        step=step.id,
                        severity="unsupported",
                    )
                if (
                    not request.ranking
                    or request.ranking.basis != "absolute_change"
                    or request.ranking.direction != "asc"
                    or request.measure_filters
                    or request.windows
                    or request.operations
                ):
                    issue(
                        "contribution_ranking",
                        "Decline contributors rank signed change ascending over all groups before display limits; offsets remain available.",
                        step=step.id,
                    )
            if step.operation == "history" and not any(
                b.kind == "entity_set"
                and steps[b.source_step].operation in {"select_extreme", "select_ranked"}
                and b.target_field in request.group_by
                for b in step.bindings
            ):
                issue(
                    "history_cohort",
                    "History must use a previously selected fixed cohort.",
                    step=step.id,
                )

    covered = {c.requirement_id: c for c in plan.coverage}
    unanswered = {u.requirement_id: u for u in plan.unanswered}
    if set(covered) | set(unanswered) != set(expected):
        issue(
            "requirement_coverage",
            "Every expected requirement must be covered or explicitly unanswered; invented requirements are rejected.",
        )
    for rid, coverage in covered.items():
        requirement = expected.get(rid)
        step = steps.get(coverage.step_id)
        if requirement is None or step is None:
            issue(
                "coverage_reference",
                "Coverage refers to a missing requirement or step.",
                requirement=rid,
            )
            continue
        if (
            step.operation != requirement.operation
            or not _covers_scope(step.request, requirement.request)
            or tuple(step.change_conditions) != requirement.change_conditions
        ):
            issue(
                "requirement_scope",
                "Step changed or omitted required operations, measures, filters, periods, grouping or comparisons.",
                step=step.id,
                requirement=rid,
            )
        declared = {o.name: o for o in step.outputs}
        if len(set(coverage.output_columns)) != len(coverage.output_columns) or not set(
            coverage.output_columns
        ) <= set(declared):
            issue(
                "coverage_output",
                "Coverage names missing or duplicate output columns.",
                step=step.id,
                requirement=rid,
            )
            continue
        signatures = {_output_signature(declared[name]) for name in coverage.output_columns}
        if not {(o.role, o.semantic_id) for o in requirement.outputs} <= signatures:
            issue(
                "coverage_output",
                "Required output roles are missing from the answer mapping.",
                step=step.id,
                requirement=rid,
            )
        for dependency in requirement.depends_on:
            source = covered.get(dependency)
            if source is None or source.step_id not in step.depends_on:
                issue(
                    "requirement_dependency",
                    "A required dependency was dropped or its prerequisite is unanswered.",
                    step=step.id,
                    requirement=rid,
                )
        expected_bindings = {
            (covered[b.source_requirement].step_id, b.kind, b.target_field)
            for b in requirement.bindings
            if b.source_requirement in covered
        }
        actual_bindings = {(b.source_step, b.kind, b.target_field) for b in step.bindings}
        if actual_bindings != expected_bindings:
            issue(
                "requirement_binding",
                "A required intermediate result was omitted or bound to a different target.",
                step=step.id,
                requirement=rid,
            )
    if set(steps) - {c.step_id for c in plan.coverage}:
        issue("unjustified_step", "Every analytical step must serve a declared requirement.")

    _review_reconciliation(plan, steps, issue)
    if any(i.severity == "invalid" for i in issues):
        status = "invalid"
    elif any(i.severity == "clarification" for i in issues) or any(
        u.status == "clarification" for u in plan.unanswered
    ):
        status = "clarification"
    elif any(i.severity == "unsupported" for i in issues):
        status = "unsupported"
    elif plan.unanswered:
        status = "partial" if plan.coverage else "unsupported"
    else:
        status = "valid"
    path = "dependent" if any(s.depends_on for s in plan.steps) else "existing"
    if status != "valid":
        path = "none"  # Partial execution policy belongs to a later batch.
    return PlanReview(
        status=status,
        proposed_path=path,
        issues=issues,
        covered_requirements=list(covered) if status in {"valid", "partial"} else [],
        unanswered_requirements=list(unanswered),
    )


def _field_type(kind: str | None) -> str | None:
    return {
        "string": "string",
        "text": "string",
        "integer": "integer",
        "int": "integer",
        "decimal": "decimal",
        "float": "decimal",
        "date": "date",
        "boolean": "boolean",
    }.get(kind)


def _review_bindings(step, steps, fields, issue):
    targets: set[tuple[str, str]] = set()
    for binding in step.bindings:
        target = (binding.kind, binding.target_field)
        if target in targets:
            issue("binding_target", "A target cannot receive conflicting bindings.", step=step.id)
        targets.add(target)
        source = steps[binding.source_step]
        outputs = {o.name: o for o in source.outputs}
        if not set(binding.source_columns) <= set(outputs):
            issue("binding_output", "Binding refers to missing source outputs.", step=step.id)
            continue
        selected = [outputs[name] for name in binding.source_columns]
        if binding.kind == "entity_set":
            output = selected[0]
            if (
                output.role != "dimension"
                or output.semantic_id != binding.target_field
                or output.value_type
                != _field_type(fields.get(binding.target_field, {}).get("type"))
            ):
                issue(
                    "binding_type",
                    "Entity binding must preserve its approved field and value type.",
                    step=step.id,
                )
            if any(f.field == binding.target_field for f in step.request.filters):
                issue(
                    "binding_target",
                    "A bound entity field cannot also have a static filter.",
                    step=step.id,
                )
        else:
            if (
                [o.role for o in selected] != ["period_start", "period_end"]
                or any(
                    o.value_type != "date" or o.semantic_id != binding.target_field
                    for o in selected
                )
                or fields.get(binding.target_field, {}).get("type") != "date"
                or not source.request.time_grain
            ):
                issue(
                    "binding_type",
                    "Period binding must preserve ordered half-open date boundaries.",
                    step=step.id,
                )
            if any(c.current or c.baseline for c in step.request.comparisons):
                issue(
                    "binding_target",
                    "An effective bound period cannot also have explicit comparison periods.",
                    step=step.id,
                )


def _review_reconciliation(plan, steps, issue):
    checked: set[tuple[str, str]] = set()
    for check in plan.reconciliations:
        head, detail = steps.get(check.headline_step), steps.get(check.contributor_step)
        if head is None or detail is None:
            issue("reconciliation_reference", "Reconciliation references an unknown step.")
            continue
        key = (detail.id, check.measure_id)
        if key in checked:
            issue(
                "reconciliation_reference", "Reconciliation checks must be unique.", step=detail.id
            )
        checked.add(key)
        if (
            head.id == detail.id
            or head.operation != "compare"
            or detail.operation != "contributors"
            or head.request.group_by
            or head.depends_on != detail.depends_on
            or head.bindings != detail.bindings
            or head.baseline != detail.baseline
            or head.eligibility != detail.eligibility
            or head.request.period != detail.request.period
            or head.request.comparisons != detail.request.comparisons
            or head.request.filters != detail.request.filters
            or head.request.entity_ids != detail.request.entity_ids
            or head.request.time_grain != detail.request.time_grain
            or head.request.windows
            or head.request.operations
            or head.request.measure_filters
            or detail.request.windows
            or detail.request.operations
            or detail.request.measure_filters
            or head.request.ranking
            or head.change_conditions
            or detail.change_conditions
        ):
            issue(
                "independent_reconciliation",
                "Require an independent ungrouped headline with the same period, filters, bindings and baseline; no capped or derived substitute.",
                step=detail.id,
            )
        for step in (head, detail):
            signatures = {_output_signature(o) for o in step.outputs}
            if any(
                (role, check.measure_id) not in signatures
                for role in ("current", "baseline", "change")
            ):
                issue(
                    "reconciliation_output",
                    "Reconciliation needs current, baseline and signed change on both independent sides.",
                    step=step.id,
                )
    for step in plan.steps:
        if step.operation == "contributors":
            for measure in step.request.measures:
                if (step.id, measure.id) not in checked:
                    issue(
                        "reconciliation_missing",
                        "Every contribution measure needs an independent headline reconciliation before limits.",
                        step=step.id,
                    )
