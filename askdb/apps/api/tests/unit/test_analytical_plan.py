"""Non-executing contract examples, NOT human holdouts or SQL-result acceptance.

The independent inventory is kept fixed while proposals are damaged. This proves
structural/typed coverage validation, not an LLM's ability to understand English.
"""

from __future__ import annotations

import ast
import json
import uuid
from dataclasses import replace
from datetime import date
from pathlib import Path
from unittest.mock import patch

import pytest
from pydantic import ValidationError

from app.core.config import Industry, Settings
from app.semantic.service import SemanticService
from app.services.chat.analytical_plan import AnalyticalPlan, AnalyticalStep
from app.services.chat.analytical_plan_validation import (
    CompletenessSource,
    ExpectedRequirement,
    PlanReviewContext,
    RequiredBinding,
    RequiredOutput,
    review_plan,
    scope_fingerprint,
)
from app.services.chat.request_context import RequestPrincipal, build_request_context
from app.services.chat.request_contract import InterpretedRequest
from app.services.security.region_scope import RegionScope

REGION = "dim_region.region_name"
MODEL = "dim_carline.model"
MAKE = "dim_carline.make"
DATE = "fact_sales.sales_date"
PERIOD = {
    "label": "Last 12 closed calendar months",
    "start": "2025-11-01",
    "end_exclusive": "2026-11-01",
}
ELIGIBILITY = {
    "mode": "closed_only",
    "evidence": "combined",
    "source_ref": "fixture_load_revision_1",
}
BASELINE = {
    "kind": "previous_period",
    "source": "approved_default",
    "rule_ref": "previous_equivalent_period_v1",
}
COMPARISON = {"kind": "period", "baseline_reference": "previous_period", "alignment": "full_period"}


def typed(model, value):
    return model.model_validate_json(json.dumps(value))


def request(*, measures=("revenue",), groups=(), grain=None, comparison=False, **changes):
    result = {
        "outcome": "analytics",
        "summary": "Controlled contract example",
        "measures": [{"id": m} for m in measures],
        "group_by": list(groups),
        "period": PERIOD,
        "time_grain": grain,
    }
    if comparison:
        result["comparisons"] = [COMPARISON]
    return result | changes


def metric_outputs(measures=("revenue",), *, comparison=False):
    return [
        {"name": f"{mid}_{role}", "role": role, "semantic_id": mid, "value_type": "decimal"}
        for mid in measures
        for role in (("current", "baseline", "change") if comparison else ("value",))
    ]


def dimension_output(field):
    return {
        "name": field.split(".")[-1],
        "role": "dimension",
        "semantic_id": field,
        "value_type": "string",
    }


def period_outputs():
    return [
        {"name": name, "role": name, "semantic_id": DATE, "value_type": "date"}
        for name in ("period_start", "period_end")
    ]


def step(sid, op, req, outputs, **changes):
    return {
        "id": sid,
        "operation": op,
        "label": sid.replace("_", " "),
        "request": req,
        "outputs": outputs,
    } | changes


def binding(source, kind="period", field=DATE):
    return {
        "source_step": source,
        "kind": kind,
        "source_columns": ["period_start", "period_end"]
        if kind == "period"
        else [field.split(".")[-1]],
        "target_field": field,
    }


def ranking(measure="revenue", *, basis="value", direction="asc", limit=1):
    return {
        "measure_id": measure,
        "basis": basis,
        "direction": direction,
        "limit": limit,
        "ties": "include",
    }


@pytest.fixture(scope="module")
def base_review():
    pack = SemanticService(Settings(_env_file=None))._load_pack(Industry.AUTOMOTIVE)
    principal = RequestPrincipal(uuid.uuid4(), RegionScope.all_regions(), Industry.AUTOMOTIVE)
    context = build_request_context(
        "revenue units ASP orders regions models",
        pack=pack,
        principal=principal,
        current_date=date(2026, 11, 26),
        max_chars=16000,
    )
    return PlanReviewContext(
        request_id="reviewed_request_1",
        principal=principal,
        context=context,
        pack=pack,
        requirements=(),
        completeness_sources=(
            CompletenessSource(
                reference="fixture_load_revision_1",
                kind="combined",
                scope_fingerprint=scope_fingerprint(principal.binding),
                revision="fixture_revision_1",
                start=date(2025, 11, 1),
                end_exclusive=date(2026, 11, 1),
                loaded_data_verified=True,
            ),
        ),
    )


def make_example(base, steps, *, reconciliations=()):
    # These are visible implementation examples. A production inventory must be
    # supplied separately; copying a model's proposal is NOT coverage validation.
    requirements = tuple(
        ExpectedRequirement(
            id="req_" + s["id"],
            operation=s["operation"],
            request=typed(InterpretedRequest, s["request"]),
            outputs=tuple(RequiredOutput(o["role"], o["semantic_id"]) for o in s["outputs"]),
            depends_on=tuple("req_" + dep for dep in s.get("depends_on", [])),
            bindings=tuple(
                RequiredBinding("req_" + b["source_step"], b["kind"], b["target_field"])
                for b in s.get("bindings", [])
            ),
            change_conditions=tuple(typed(AnalyticalStep, s).change_conditions),
        )
        for s in steps
    )
    context = replace(base, requirements=requirements)
    proposal = {
        "plan_id": "controlled_plan_1",
        "source_request_id": context.request_id,
        "semantic_version": context.context.semantic_version,
        "scope_fingerprint": scope_fingerprint(context.principal.binding),
        "steps": steps,
        "coverage": [
            {
                "requirement_id": r.id,
                "step_id": s["id"],
                "output_columns": [o["name"] for o in s["outputs"]],
            }
            for r, s in zip(requirements, steps, strict=True)
        ],
        "reconciliations": list(reconciliations),
    }
    return typed(AnalyticalPlan, proposal), context


def extreme_period_example(base):
    """Named regression: lowest month, baseline, combined region-model changes.

    Full-period prior-month baseline and combined dimensions are explicit HERE;
    they are not global defaults or proof that production interpretation knows them.
    """
    totals = request(grain="month")
    periods = metric_outputs() + period_outputs()
    comparison = request(comparison=True)
    steps = [
        step("month_totals", "aggregate", totals, periods, eligibility=ELIGIBILITY),
        step(
            "lowest_month",
            "select_extreme",
            totals | {"ranking": ranking()},
            periods,
            input_step="month_totals",
            depends_on=["month_totals"],
            selection={},
            eligibility=ELIGIBILITY,
        ),
        step(
            "headline",
            "compare",
            comparison,
            metric_outputs(comparison=True),
            depends_on=["lowest_month"],
            bindings=[binding("lowest_month")],
            baseline=BASELINE,
        ),
        step(
            "contributors",
            "contributors",
            comparison
            | {"group_by": [REGION, MODEL], "ranking": ranking(basis="absolute_change", limit=10)},
            [*metric_outputs(comparison=True), dimension_output(REGION), dimension_output(MODEL)],
            depends_on=["lowest_month"],
            bindings=[binding("lowest_month")],
            baseline=BASELINE,
        ),
    ]
    checks = [
        {"headline_step": "headline", "contributor_step": "contributors", "measure_id": "revenue"}
    ]
    return make_example(base, steps, reconciliations=checks)


def region_example(base):
    totals = request(groups=[REGION])
    outputs = [*metric_outputs(), dimension_output(REGION)]
    steps = [
        step("regions", "aggregate", totals, outputs),
        step(
            "selected_region",
            "select_extreme",
            totals | {"ranking": ranking(direction="desc")},
            outputs,
            input_step="regions",
            depends_on=["regions"],
            selection={},
        ),
        step(
            "models",
            "aggregate",
            request(groups=[MODEL], ranking=ranking(direction="desc", limit=10)),
            [*metric_outputs(), dimension_output(MODEL)],
            depends_on=["selected_region"],
            bindings=[binding("selected_region", "entity_set", REGION)],
        ),
    ]
    return make_example(base, steps)


def compare_example(base):
    req = request(
        groups=[MODEL], comparison=True, ranking=ranking(basis="absolute_change", limit=10)
    )
    return make_example(
        base,
        [
            step(
                "decliners",
                "compare",
                req,
                [*metric_outputs(comparison=True), dimension_output(MODEL)],
                baseline=BASELINE,
            )
        ],
    )


def opposite_changes_example(base):
    req = request(measures=["revenue", "units_sold"], groups=[MODEL], comparison=True)
    return make_example(
        base,
        [
            step(
                "opposite_changes",
                "compare",
                req,
                [
                    *metric_outputs(["revenue", "units_sold"], comparison=True),
                    dimension_output(MODEL),
                ],
                baseline=BASELINE,
                change_conditions=[
                    {"measure_id": "revenue", "operator": "gt"},
                    {"measure_id": "units_sold", "operator": "lt"},
                ],
            )
        ],
    )


def cohort_history_example(base):
    req = request(groups=[MODEL])
    outputs = [*metric_outputs(), dimension_output(MODEL)]
    steps = [
        step("model_totals", "aggregate", req, outputs),
        step(
            "top_cohort",
            "select_ranked",
            req | {"ranking": ranking(direction="desc", limit=5)},
            outputs,
            input_step="model_totals",
            depends_on=["model_totals"],
            selection={},
        ),
        step(
            "own_history",
            "history",
            request(groups=[MODEL], comparison=True),
            [*metric_outputs(comparison=True), dimension_output(MODEL)],
            depends_on=["top_cohort"],
            bindings=[binding("top_cohort", "entity_set", MODEL)],
            baseline=BASELINE,
        ),
    ]
    return make_example(base, steps)


def changed(plan, mutate):
    value = plan.model_dump(mode="json")
    mutate(value)
    return typed(AnalyticalPlan, value)


def codes(plan, context):
    return {i.code for i in review_plan(plan, context).issues}


@pytest.mark.parametrize(
    "example,path",
    [
        (extreme_period_example, "dependent"),
        (region_example, "dependent"),
        (compare_example, "existing"),
        (opposite_changes_example, "existing"),
        (cohort_history_example, "dependent"),
    ],
)
def test_five_general_shapes(base_review, example, path):
    plan, context = example(base_review)
    result = review_plan(plan, context)
    assert result.status == "valid", result.model_dump()
    assert result.proposed_path == path
    assert result.execution_enabled is False
    assert len(result.covered_requirements) == len(context.requirements)


@pytest.mark.parametrize(
    "measures,groups,windows",
    [
        (["units_sold"], [REGION], []),
        (["revenue", "units_sold", "average_selling_price"], [MAKE, MODEL, REGION], []),
        (
            ["revenue"],
            [REGION],
            [
                {
                    "operation": "running_total",
                    "measure_ids": ["revenue"],
                    "partition_by": [REGION],
                    "order_by": DATE,
                }
            ],
        ),
    ],
)
def test_multiple_measures_joins_or_windows_do_not_imply_dependency(
    base_review, measures, groups, windows
):
    plan, context = make_example(
        base_review,
        [
            step(
                "direct",
                "aggregate",
                request(measures=measures, groups=groups, windows=windows),
                metric_outputs(measures) + [dimension_output(g) for g in groups],
            )
        ],
    )
    assert review_plan(plan, context).proposed_path == "existing"


@pytest.mark.parametrize(
    "mutation,code",
    [
        (lambda p: p.update(semantic_version="changed"), "authority_mismatch"),
        (lambda p: p.update(source_request_id="another"), "authority_mismatch"),
        (lambda p: p.update(scope_fingerprint="0" * 64), "authority_mismatch"),
        (
            lambda p: p["steps"][0]["request"]["measures"].append({"id": "invented_profit"}),
            "measure_reference",
        ),
        (
            lambda p: p["steps"][0]["request"]["measures"][0].update(aggregation="avg"),
            "formula_override",
        ),
        (lambda p: p["steps"][2]["request"].update(group_by=[MAKE]), "requirement_scope"),
        (
            lambda p: p["steps"][2]["request"].update(
                filters=[{"field": "dim_salesman.active", "operator": "eq", "values": [True]}]
            ),
            "requirement_scope",
        ),
        (
            lambda p: p["steps"][2]["request"]["period"].update(start="2026-01-01"),
            "requirement_scope",
        ),
        (
            lambda p: p["steps"][2]["request"]["ranking"].update(direction="asc"),
            "requirement_scope",
        ),
        (lambda p: p["coverage"].pop(), "requirement_coverage"),
        (lambda p: p["coverage"][2].update(output_columns=["model"]), "coverage_output"),
        (
            lambda p: p["steps"][2]["bindings"][0].update(source_columns=["unknown"]),
            "binding_output",
        ),
        (lambda p: p["steps"][2]["bindings"][0].update(target_field=MODEL), "binding_type"),
    ],
)
def test_rejects_silent_simplification_and_wrong_references(base_review, mutation, code):
    plan, context = region_example(base_review)
    assert code in codes(changed(plan, mutation), context)


@pytest.mark.parametrize(
    "mutation",
    [
        lambda p: p["steps"][1].update(depends_on=["selected_region"]),
        lambda p: p["steps"][1].update(depends_on=["models"], input_step="models"),
        lambda p: p["steps"][1].update(id="regions"),
        lambda p: p["steps"][2].update(depends_on=[]),
        lambda p: p["steps"][2]["bindings"][0].update(max_items=51),
        lambda p: p["steps"][1]["selection"].update(ties="first"),
        lambda p: p["steps"][1]["selection"].update(on_overflow="truncate"),
        lambda p: p.update(total_model_calls=3),
        lambda p: p["steps"][0].update(sql="SELECT * FROM private_table"),
        lambda p: p.update(credentials="not_allowed"),
        lambda p: p["coverage"].append(p["coverage"][0]),
    ],
)
def test_structural_guards(base_review, mutation):
    plan, _ = region_example(base_review)
    with pytest.raises(ValidationError):
        changed(plan, mutation)


@pytest.mark.parametrize(
    "mutate,code",
    [
        (
            lambda p: p["steps"][1].update(
                eligibility={"mode": "closed_only", "evidence": "unverified"}
            ),
            "loaded_completeness",
        ),
        (
            lambda p: p["steps"][1]["eligibility"].update(source_ref="max_date_is_not_load_status"),
            "completeness_source",
        ),
        (
            lambda p: p["steps"][1]["eligibility"].update(mode="include_partial_labelled"),
            "period_eligibility",
        ),
        (lambda p: p.update(reconciliations=[]), "reconciliation_missing"),
        (
            lambda p: p["reconciliations"][0].update(headline_step="contributors"),
            "independent_reconciliation",
        ),
        (
            lambda p: p["steps"][2]["request"]["period"].update(start="2026-01-01"),
            "independent_reconciliation",
        ),
        (
            lambda p: p["steps"][3]["request"]["ranking"].update(basis="value"),
            "contribution_ranking",
        ),
        (
            lambda p: p["steps"][3]["request"]["ranking"].update(direction="desc"),
            "contribution_ranking",
        ),
        (lambda p: p["steps"][3]["baseline"].update(rule_ref="invented"), "baseline_rule"),
        (
            lambda p: p["steps"][2]["request"]["comparisons"][0].update(
                baseline_reference="same_period_last_year"
            ),
            "baseline",
        ),
    ],
)
def test_named_regression_rejects_false_dip_and_false_proof(base_review, mutate, code):
    plan, context = extreme_period_example(base_review)
    assert code in codes(changed(plan, mutate), context)


def test_calendar_closure_does_not_prove_loaded_completeness(base_review):
    plan, context = extreme_period_example(base_review)
    plan = changed(
        plan,
        lambda p: p["steps"][1].update(
            eligibility={
                "mode": "closed_only",
                "evidence": "semantic_calendar",
                "source_ref": "calendar_v1",
            }
        ),
    )
    context = replace(
        context,
        completeness_sources=(
            CompletenessSource(
                "calendar_v1", "semantic_calendar", plan.scope_fingerprint, "calendar_revision_1"
            ),
            *context.completeness_sources,
        ),
    )
    result = review_plan(plan, context)
    assert result.status == "clarification"
    assert result.proposed_path == "none"


def test_missing_loaded_proof_does_not_affect_ordinary_questions(base_review):
    plan, context = region_example(base_review)
    assert review_plan(plan, replace(context, completeness_sources=())).status == "valid"


def test_effective_period_binding_cannot_conflict_with_explicit_comparison_dates(base_review):
    plan, context = extreme_period_example(base_review)
    plan = changed(
        plan, lambda p: p["steps"][2]["request"]["comparisons"][0].update(current=PERIOD)
    )
    assert "binding_target" in codes(plan, context)


def test_lost_dependency_rejected_even_when_model_rewrites_its_coverage(base_review):
    plan, context = region_example(base_review)
    plan = changed(plan, lambda p: p["steps"][2].update(bindings=[], depends_on=[]))
    assert {"requirement_dependency", "requirement_binding"} <= codes(plan, context)


def test_every_comparison_member_and_exclusion_is_preserved(base_review):
    original = request(
        groups=[MAKE, MODEL],
        filters=[{"field": "dim_salesman.active", "operator": "ne", "values": [False]}],
    )
    plan, context = make_example(
        base_review,
        [
            step(
                "grouped",
                "aggregate",
                original,
                [*metric_outputs(), dimension_output(MAKE), dimension_output(MODEL)],
            )
        ],
    )
    bad = changed(plan, lambda p: p["steps"][0]["request"].update(filters=[]))
    assert "requirement_scope" in codes(bad, context)


def test_two_measures_opposite_conditions_cannot_be_dropped(base_review):
    plan, context = opposite_changes_example(base_review)
    bad = changed(plan, lambda p: p["steps"][0]["change_conditions"].pop())
    assert "requirement_scope" in codes(bad, context)


def test_no_independent_inventory_no_coverage_claim(base_review):
    plan, context = region_example(base_review)
    result = review_plan(plan, replace(context, requirements=()))
    assert result.status == "invalid"
    assert result.covered_requirements == []


def test_same_plan_cannot_be_reused_by_another_user(base_review):
    plan, context = region_example(base_review)
    other = replace(context.principal, user_id=uuid.uuid4())
    assert "authority_mismatch" in codes(plan, replace(context, principal=other))


@pytest.mark.parametrize("max_steps,max_calls,used", [(2, 2, 1), (4, 1, 2), (5, 2, 1), (4, 3, 1)])
def test_shared_budget_cannot_be_broadened(base_review, max_steps, max_calls, used):
    plan, context = region_example(base_review)
    assert "budget" in codes(
        plan,
        replace(
            context, max_steps=max_steps, max_total_model_calls=max_calls, model_calls_used=used
        ),
    )


def test_all_calls_include_initial_interpretation(base_review):
    plan, context = region_example(base_review)
    assert "budget" in codes(plan, replace(context, model_calls_used=2))
    plan = changed(plan, lambda p: p.update(total_model_calls=2))
    assert review_plan(plan, replace(context, model_calls_used=2)).status == "valid"


@pytest.mark.parametrize(
    "unanswered_status,question,status",
    [
        ("unsupported", None, "partial"),
        ("source_unavailable", None, "partial"),
        ("clarification", "Which comparison period should I use?", "clarification"),
    ],
)
def test_partial_answers_account_for_missing_parts(
    base_review, unanswered_status, question, status
):
    plan, context = opposite_changes_example(base_review)
    missing = replace(context.requirements[0], id="req_unavailable")
    context = replace(context, requirements=(*context.requirements, missing))
    value = {
        "requirement_id": missing.id,
        "status": unanswered_status,
        "reason": "Approved evidence is missing.",
    }
    if question:
        value["question"] = question
    plan = changed(plan, lambda p: p.update(unanswered=[value]))
    result = review_plan(plan, context)
    assert result.status == status
    assert result.unanswered_requirements == [missing.id]
    assert result.proposed_path == "none"
    assert not result.execution_enabled


def test_unanswered_prerequisite_cannot_feed_a_claimed_answer(base_review):
    plan, context = region_example(base_review)

    def mutate(p):
        p["steps"] = [p["steps"][2] | {"depends_on": [], "bindings": []}]
        p["coverage"] = [p["coverage"][2]]
        p["unanswered"] = [
            {
                "requirement_id": c.id,
                "status": "source_unavailable",
                "reason": "No eligible source rows.",
            }
            for c in context.requirements[:2]
        ]

    assert "requirement_dependency" in codes(changed(plan, mutate), context)


def test_contributions_do_not_support_ratio_decomposition(base_review):
    plan, context = extreme_period_example(base_review)

    def mutate(p):
        s = p["steps"][3]
        s["request"]["measures"] = [{"id": "average_selling_price"}]
        s["request"]["ranking"]["measure_id"] = "average_selling_price"
        for out in s["outputs"][:3]:
            out["semantic_id"] = "average_selling_price"

    assert "contribution_capability" in codes(changed(plan, mutate), context)


def test_history_must_use_entity_cohort_not_only_period(base_review):
    plan, context = extreme_period_example(base_review)
    plan = changed(plan, lambda p: p["steps"][2].update(operation="history"))
    assert "history_cohort" in codes(plan, context)


def test_round_trip_preserves_plan_and_outputs(base_review):
    plan, context = extreme_period_example(base_review)
    restored = AnalyticalPlan.model_validate_json(plan.model_dump_json())
    assert restored == plan
    assert review_plan(restored, context).status == "valid"


def test_review_is_pure_and_never_executes_specialists(base_review):
    plan, context = extreme_period_example(base_review)
    before = plan.model_dump_json()
    with (
        patch("app.services.llm.complete_text", side_effect=AssertionError("model call")),
        patch(
            "app.services.chat.request_compiler.compile_request",
            side_effect=AssertionError("compile"),
        ),
        patch("app.services.chat.pipeline.plan_turn", side_effect=AssertionError("planning")),
        patch(
            "app.services.knowledge.KnowledgeService.search_authorized",
            side_effect=AssertionError("retrieval"),
        ),
        patch("app.services.analytics.bi.service.turn", side_effect=AssertionError("report")),
        patch(
            "sqlalchemy.ext.asyncio.AsyncConnection.execute",
            side_effect=AssertionError("warehouse"),
        ),
        patch(
            "sqlalchemy.ext.asyncio.AsyncSession.execute",
            side_effect=AssertionError("app database"),
        ),
    ):
        assert review_plan(plan, context).status == "valid"
    assert plan.model_dump_json() == before


def test_model_cannot_add_an_unrequested_ranking(base_review):
    plan, context = opposite_changes_example(base_review)
    plan = changed(
        plan,
        lambda p: p["steps"][0]["request"].update(
            ranking=ranking(basis="absolute_change", limit=5)
        ),
    )
    assert "requirement_scope" in codes(plan, context)


def test_model_cannot_add_an_unrequested_comparison(base_review):
    plan, context = region_example(base_review)
    plan = changed(plan, lambda p: p["steps"][0]["request"].update(comparisons=[COMPARISON]))
    assert {"requirement_scope", "operation_shape"} <= codes(plan, context)


def test_selection_cannot_take_extreme_from_an_already_capped_ranking(base_review):
    plan, context = region_example(base_review)
    plan = changed(plan, lambda p: p["steps"][0]["request"].update(ranking=ranking(limit=10)))
    assert "selection_semantics" in codes(plan, context)


def test_mutated_model_is_revalidated_before_reference_lookup(base_review):
    plan, context = region_example(base_review)
    plan.steps[2].depends_on = ["does_not_exist"]
    result = review_plan(plan, context)
    assert result.status == "invalid"
    assert result.issues[0].code == "plan_shape"


def test_no_access_scope_fails_closed(base_review):
    plan, context = region_example(base_review)
    principal = replace(context.principal, scope=RegionScope(False, ()))
    context = replace(
        context, principal=principal, context=replace(context.context, binding=principal.binding)
    )
    plan = changed(plan, lambda p: p.update(scope_fingerprint=scope_fingerprint(principal.binding)))
    assert "authority_mismatch" in codes(plan, context)


def test_changed_region_permissions_invalidate_plan(base_review):
    plan, context = region_example(base_review)
    principal = replace(context.principal, scope=RegionScope(False, ("West",)))
    assert "authority_mismatch" in codes(plan, replace(context, principal=principal))


@pytest.mark.parametrize(
    "mutation,code",
    [
        ({"scope_fingerprint": "0" * 64}, "completeness_source"),
        ({"revision": ""}, "completeness_source"),
        ({"end_exclusive": date(2026, 10, 1)}, "completeness_coverage"),
        ({"start": date(2026, 1, 1)}, "completeness_coverage"),
        ({"loaded_data_verified": False}, "loaded_completeness"),
    ],
)
def test_completeness_requires_scoped_revision_and_covered_dates(base_review, mutation, code):
    plan, context = extreme_period_example(base_review)
    context = replace(
        context, completeness_sources=(replace(context.completeness_sources[0], **mutation),)
    )
    assert code in codes(plan, context)


def test_relative_selection_window_is_not_mistaken_for_resolved_load_proof(base_review):
    plan, context = extreme_period_example(base_review)

    def mutate(p):
        for s in p["steps"][:2]:
            s["request"]["period"] = {
                "label": "Last 12 months",
                "relative": "last_n_months",
                "count": 12,
            }

    assert "completeness_coverage" in codes(changed(plan, mutate), context)


def test_runtime_cannot_skip_safe_tie_policy(base_review):
    plan, _ = region_example(base_review)
    with pytest.raises(ValidationError):
        changed(plan, lambda p: p["steps"][1]["selection"].update(before_display_limit=False))


def test_history_cannot_regroup_away_the_selected_cohort(base_review):
    plan, context = cohort_history_example(base_review)
    plan = changed(plan, lambda p: p["steps"][2]["request"].update(group_by=[]))
    assert "history_cohort" in codes(plan, context)


def test_cannot_drop_one_measure_from_multi_measure_request(base_review):
    plan, context = opposite_changes_example(base_review)

    def mutate(p):
        s = p["steps"][0]
        s["request"]["measures"] = [{"id": "revenue"}]
        s["outputs"] = [o for o in s["outputs"] if o["semantic_id"] != "units_sold"]
        s["change_conditions"] = s["change_conditions"][:1]
        p["coverage"][0]["output_columns"] = [o["name"] for o in s["outputs"]]

    assert "requirement_scope" in codes(changed(plan, mutate), context)


def test_specialized_target_is_not_promoted_to_general_execution(base_review):
    req = request(measures=["target_revenue"])
    plan, context = make_example(
        base_review, [step("target", "aggregate", req, metric_outputs(["target_revenue"]))]
    )
    result = review_plan(plan, context)
    assert result.status == "unsupported"
    assert "measure_capability" in {i.code for i in result.issues}


@pytest.mark.parametrize(
    "outcome,extras",
    [
        ("conversation", {"reply": "Hello"}),
        ("report", {}),
        ("documents", {}),
        ("definition", {"definition_terms": ["revenue"]}),
        ("clarification", {"clarification": "Which period?"}),
    ],
)
def test_analytical_step_cannot_execute_other_routes(base_review, outcome, extras):
    plan, context = region_example(base_review)
    plan = changed(plan, lambda p: p["steps"][0]["request"].update(outcome=outcome, **extras))
    assert "step_outcome" in codes(plan, context)


def test_dependent_runtime_remains_default_off():
    settings = Settings(_env_file=None)
    assert not settings.chat_dependent_analysis_enabled
    assert not settings.chat_typed_execution_enabled


@pytest.mark.parametrize("module", ["analytical_plan.py", "analytical_plan_validation.py"])
def test_no_executor_or_provider_imports(module):
    folder = Path(__file__).parents[2] / "app" / "services" / "chat"
    tree = ast.parse((folder / module).read_text(encoding="utf-8"))
    imports = [node.module or "" for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)]
    assert not any(
        name.startswith(("app.services.llm", "app.services.analytics", "app.services.knowledge"))
        for name in imports
    )
