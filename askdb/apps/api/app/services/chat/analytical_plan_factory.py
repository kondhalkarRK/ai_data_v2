"""Materialize checked interpretation clauses into a deterministic reviewed plan.

The inventory is the validated interpretation, independently checked against the
original question before this function is called. Outputs and reconciliation are
server-built. This does not prove arbitrary English coverage; human benchmarks
and office acceptance remain required before rollout.
"""

from __future__ import annotations

import uuid
from dataclasses import replace
from datetime import date

from app.services.chat.analytical_plan import (
    AnalyticalPlan,
    AnalyticalStep,
    BaselineProvenance,
    ChangeCondition,
    PeriodEligibility,
    PlanOutput,
    ReconciliationCheck,
    RequirementCoverage,
    ResultBinding,
    SelectionPolicy,
)
from app.services.chat.analytical_plan_validation import (
    ExpectedRequirement,
    PlanReviewContext,
    RequiredBinding,
    RequiredOutput,
    scope_fingerprint,
)
from app.services.chat.request_capabilities import TypedCompileError
from app.services.chat.request_contract import (
    RequestedComparison,
    RequestedMeasure,
    RequestedPeriod,
)
from app.services.chat.request_dates import RequestClarificationError, add_months, resolve_period


def _closed_period(period, grain, today, policy):
    months = {"month": 1, "quarter": 3, "year": 12}.get(grain)
    if not months:
        raise TypedCompileError("Closed-period selection currently supports month, quarter or year")
    anchor = date(today.year, ((today.month - 1) // months) * months + 1, 1)
    relative = {"month": "last_n_months", "quarter": "last_n_quarters", "year": "last_n_years"}[
        grain
    ]
    if period.relative == relative:
        start, end = add_months(anchor, -months * period.count), anchor
    else:
        resolved = resolve_period(period, today, policy)
        if not resolved.start or not resolved.end:
            raise RequestClarificationError("Which bounded period should I investigate?")
        start = date(resolved.start.year, ((resolved.start.month - 1) // months) * months + 1, 1)
        if start != resolved.start:
            start = add_months(start, months)
        end = min(anchor, resolved.end)
        end = date(end.year, ((end.month - 1) // months) * months + 1, 1)
    if start >= end:
        raise RequestClarificationError(
            "There is no closed eligible period in that selection. Which earlier period should I use?"
        )
    return RequestedPeriod(
        label=f"Closed periods: {start} to {end} (exclusive)", start=start, end_exclusive=end
    )


def materialize_plan(request, review: PlanReviewContext, *, today: date):
    if not request.analysis_tasks:
        raise TypedCompileError("No dependent interpretation inventory was supplied")
    if not any(
        t.source or (t.operation == "compare" and t.change_conditions)
        for t in request.analysis_tasks
    ):
        raise TypedCompileError("Independent analytics should use the existing request compiler")
    if request.period is None:
        raise RequestClarificationError("Which period should I analyze?")
    if any(c.kind != "period" for c in request.comparisons) or len(request.comparisons) > 1:
        raise TypedCompileError("This dependent comparison needs one approved period baseline")
    period = request.period
    for task in request.analysis_tasks:
        if task.operation in {"select_extreme", "select_ranked"}:
            source = next(t for t in request.analysis_tasks if t.id == task.source)
            if source.time_grain:
                period = _closed_period(
                    period, source.time_grain, today, review.pack.model.query_policy
                )
    # The defaults below are the seven approved business decisions, not arbitrary
    # formulas or dimension allocations. Explicit comparisons always take priority.
    comparisons = request.comparisons or [
        RequestedComparison(
            kind="period", baseline_reference="previous_period", alignment="full_period"
        )
    ]
    comparison = comparisons[0]
    baseline = BaselineProvenance(
        kind="explicit" if comparison.baseline else comparison.baseline_reference,
        source="user" if request.comparisons else "approved_default",
        rule_ref=None if request.comparisons else review.approved_baseline_rule,
    )
    fields = review.context.payload["fields"]
    date_field = next(
        (f for f, s in fields.items() if s["type"] == "date" and f.startswith("fact_")), None
    )
    if date_field is None:
        raise TypedCompileError("No approved analytical date field")
    built, requirements = {}, []
    for task in request.analysis_tasks:
        selection = task.operation in {"select_extreme", "select_ranked"}
        comparing = task.operation in {"compare", "contributors", "history"}
        if selection:
            source = built[task.source]
            scoped = source.request.model_copy(deep=True, update={"ranking": task.ranking})
            if task.measures and set(task.measures) != {m.id for m in scoped.measures}:
                raise TypedCompileError("Selection cannot change its input measures")
            if task.group_by and task.group_by != scoped.group_by:
                raise TypedCompileError("Selection cannot change its input grouping")
            if task.time_grain and task.time_grain != scoped.time_grain:
                raise TypedCompileError("Selection cannot change its input time grain")
            outputs = [o.model_copy(deep=True) for o in source.outputs]
        else:
            scoped = request.model_copy(
                deep=True,
                update={
                    "outcome": "analytics",
                    "additional_outcomes": [],
                    "analysis_tasks": [],
                    "summary": task.id.replace("_", " "),
                    "period": period,
                    "measures": [RequestedMeasure(id=m) for m in task.measures]
                    if task.measures
                    else request.measures,
                    "group_by": task.group_by,
                    "time_grain": task.time_grain,
                    "ranking": task.ranking,
                    "comparisons": comparisons if comparing else [],
                    "definition_terms": [],
                    "evidence": [],
                    "reply": None,
                    "followup": False,
                    "changed_fields": [],
                    "clear_filters": [],
                },
            )
            outputs = []
            for mid in scoped.measures:
                for role in (
                    ("current", "baseline", "change", "percent_change") if comparing else ("value",)
                ):
                    outputs.append(
                        PlanOutput(
                            name=f"{mid.id}_{role}",
                            role=role,
                            semantic_id=mid.id,
                            value_type="decimal",
                        )
                    )
            for field in scoped.group_by:
                kind = fields.get(field, {}).get("type")
                kind = {"text": "string", "float": "decimal", "int": "integer"}.get(kind, kind)
                if kind not in {"decimal", "integer", "string", "date", "boolean"}:
                    raise TypedCompileError("Unknown approved grouping type")
                outputs.append(
                    PlanOutput(
                        name=field.replace(".", "_"),
                        role="dimension",
                        semantic_id=field,
                        value_type=kind,
                    )
                )
            if scoped.time_grain:
                for role in ("period_start", "period_end"):
                    outputs.append(
                        PlanOutput(name=role, role=role, semantic_id=date_field, value_type="date")
                    )
        bindings = []
        if task.binding_kind:
            source = built[task.source]
            columns = [
                o.name
                for o in source.outputs
                if o.semantic_id == task.binding_field
                and o.role
                in (
                    {"period_start", "period_end"}
                    if task.binding_kind == "period"
                    else {"dimension"}
                )
            ]
            if task.binding_kind == "period":
                columns = [
                    next(
                        (
                            o.name
                            for o in source.outputs
                            if o.semantic_id == task.binding_field and o.role == role
                        ),
                        "",
                    )
                    for role in ("period_start", "period_end")
                ]
            if not columns or any(not c for c in columns):
                raise TypedCompileError(
                    "Selected result does not expose the required binding field"
                )
            bindings = [
                ResultBinding(
                    source_step=task.source,
                    kind=task.binding_kind,
                    target_field=task.binding_field,
                    source_columns=columns,
                )
            ]
        eligibility = None
        if scoped.time_grain:
            source = next(
                (
                    s
                    for s in review.completeness_sources
                    if s.loaded_data_verified and s.kind in {"load_status", "combined"}
                ),
                None,
            )
            eligibility = PeriodEligibility(
                mode="closed_only",
                evidence=source.kind if source else "unverified",
                source_ref=source.reference if source else None,
            )
        step = AnalyticalStep(
            id=task.id,
            operation=task.operation,
            label=task.id.replace("_", " "),
            request=scoped,
            depends_on=[task.source] if task.source else [],
            input_step=task.source if selection else None,
            bindings=bindings,
            outputs=outputs,
            baseline=baseline if comparing else None,
            selection=SelectionPolicy() if selection else None,
            eligibility=eligibility,
            change_conditions=[
                ChangeCondition.model_validate(c.model_dump()) for c in task.change_conditions
            ],
        )
        built[step.id] = step
        requirements.append(
            ExpectedRequirement(
                id=task.id,
                operation=task.operation,
                request=scoped.model_copy(deep=True),
                outputs=tuple(RequiredOutput(o.role, o.semantic_id) for o in outputs),
                depends_on=tuple(step.depends_on),
                change_conditions=tuple(step.change_conditions),
                bindings=tuple(
                    RequiredBinding(b.source_step, b.kind, b.target_field) for b in bindings
                ),
            )
        )
    reconciliations = []
    for step in built.values():
        if step.operation != "contributors":
            continue
        head = next(
            (
                h
                for h in built.values()
                if h.operation == "compare"
                and not h.request.group_by
                and h.bindings == step.bindings
                and h.request.filters == step.request.filters
                and h.request.period == step.request.period
                and h.baseline == step.baseline
            ),
            None,
        )
        if head is None:
            raise TypedCompileError("Contributors require an independent ungrouped headline task")
        for measure in step.request.measures:
            reconciliations.append(
                ReconciliationCheck(
                    headline_step=head.id, contributor_step=step.id, measure_id=measure.id
                )
            )
    requested_measures = {m.id for m in request.measures}
    planned_measures = {m.id for s in built.values() for m in s.request.measures}
    planned_groups = {f for s in built.values() for f in s.request.group_by}
    if any(s.request.time_grain for s in built.values()):
        planned_groups.add(date_field)
    if not requested_measures <= planned_measures:
        raise TypedCompileError("The task inventory dropped a requested measure")
    if not set(request.group_by) <= planned_groups:
        raise TypedCompileError("The task inventory dropped a requested grouping")
    if request.time_grain and not any(
        s.request.time_grain == request.time_grain for s in built.values()
    ):
        raise TypedCompileError("The task inventory dropped a requested time grain")
    if request.comparisons and not any(
        s.request.comparisons == request.comparisons for s in built.values()
    ):
        raise TypedCompileError("The task inventory dropped an explicit comparison")
    if request.ranking and not any(s.request.ranking == request.ranking for s in built.values()):
        raise TypedCompileError("The task inventory dropped a requested ranking")
    plan = AnalyticalPlan(
        plan_id=str(uuid.uuid4()),
        source_request_id=review.request_id,
        semantic_version=review.context.semantic_version,
        scope_fingerprint=scope_fingerprint(review.principal.binding),
        steps=list(built.values()),
        total_model_calls=max(1, review.model_calls_used),
        coverage=[
            RequirementCoverage(
                requirement_id=r.id,
                step_id=r.id,
                output_columns=[o.name for o in built[r.id].outputs],
            )
            for r in requirements
        ],
        reconciliations=reconciliations,
    )
    return plan, replace(review, requirements=tuple(requirements))
