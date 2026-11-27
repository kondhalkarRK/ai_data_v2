"""Visible synthetic scorer fixtures, not human references or unseen questions."""

import copy
import json

import pytest

from tests.unit.test_chat_acceptance_runner import runner


@pytest.fixture
def sample():
    steps = [
        {
            "id": "totals",
            "operation": "aggregate",
            "depends_on": [],
            "request": {"measures": [{"id": "revenue"}], "group_by": ["dim_region.region_name"]},
            "outputs": [
                {"name": "region", "value_type": "string"},
                {"name": "revenue", "value_type": "decimal"},
            ],
        },
        {
            "id": "winner",
            "operation": "select_extreme",
            "depends_on": ["totals"],
            "request": {"measures": [{"id": "revenue"}], "group_by": ["dim_region.region_name"]},
            "outputs": [
                {"name": "region", "value_type": "string"},
                {"name": "revenue", "value_type": "decimal"},
            ],
        },
    ]
    meta = {
        "executionMode": "typed",
        "responseKind": "data",
        "typedRequest": {"outcome": "analytics"},
        "analyticalPlan": {"steps": steps},
        "analyticalExecution": {
            "status": "completed",
            "scope_labels": ["West"],
            "checks": [],
            "steps": [
                {
                    "id": "totals",
                    "status": "completed",
                    "verified": True,
                    "columns": ["region", "revenue"],
                    "rows": [{"region": "West", "revenue": "100.01"}],
                    "total_groups": 1,
                    "selected_groups": 1,
                },
                {
                    "id": "winner",
                    "status": "completed",
                    "verified": True,
                    "columns": ["region", "revenue"],
                    "rows": [{"region": "West", "revenue": "100.01"}],
                    "total_groups": 1,
                    "selected_groups": 1,
                },
            ],
        },
        "analyticalPresentation": {
            "version": 1,
            "scope": ["West"],
            "unanswered": [],
            "steps": [
                {
                    "id": "totals",
                    "searchPeriod": {"start": "2026-01-01", "endExclusive": "2026-02-01"},
                    "filters": [],
                    "comparisonPeriods": [],
                    "baseline": None,
                },
                {
                    "id": "winner",
                    "searchPeriod": {"start": "2026-01-01", "endExclusive": "2026-02-01"},
                    "filters": [],
                    "comparisonPeriods": [],
                    "baseline": None,
                },
            ],
        },
        "runUsage": {
            "initialModelCalls": 1,
            "verificationModelCalls": 1,
            "correctionModelCalls": 0,
            "inputTokens": 250,
            "outputTokens": 150,
            "tokensEstimated": False,
            "modelsUsed": ["same", "same"],
            "modelUsageComplete": True,
        },
    }
    # Independently specified reference values. Never build gold from the projection.
    ref_steps = [
        {
            "operation": "aggregate",
            "dependsOn": [],
            "measures": ["revenue"],
            "grouping": ["dim_region.region_name"],
            "filters": [],
            "period": {"start": "2026-01-01", "endExclusive": "2026-02-01"},
            "comparisonPeriods": [],
            "baseline": None,
            "status": "completed",
            "verified": True,
            "columns": ["region", "revenue"],
            "rows": [{"region": "West", "revenue": 100.01}],
            "totalGroups": 1,
            "selectedGroups": 1,
            "rowOrder": "ordered",
        },
        {
            "operation": "select_extreme",
            "dependsOn": [0],
            "measures": ["revenue"],
            "grouping": ["dim_region.region_name"],
            "filters": [],
            "period": {"start": "2026-01-01", "endExclusive": "2026-02-01"},
            "comparisonPeriods": [],
            "baseline": None,
            "status": "completed",
            "verified": True,
            "columns": ["region", "revenue"],
            "rows": [{"region": "West", "revenue": 100.01}],
            "totalGroups": 1,
            "selectedGroups": 1,
            "rowOrder": "ordered",
        },
    ]
    gold = {
        "route": "analytics",
        "text": "West leads.",
        "reference": {
            "kind": "human_reference",
            "reviewer": "Synthetic reviewer fixture",
            "sqlSha256": "a" * 64,
            "datasetRevision": "synthetic-v1",
            "reviewedAt": "2026-11-27",
            "holdout": False,
        },
        "analysis": {
            "status": "completed",
            "scope": ["West"],
            "steps": ref_steps,
            "checks": [],
            "unanswered": [],
        },
    }
    meta["analyticalPresentation"]["status"] = "completed"
    meta["analyticalPresentation"]["summary"] = "West leads."
    for step in meta["analyticalPresentation"]["steps"]:
        step.update(
            status="completed",
            verified=True,
            displayedRows=1,
            columns=[{"key": "region"}, {"key": "revenue"}],
        )
    return [
        {"event": "meta", "data": meta},
        {"event": "token", "data": {"token": "West leads."}},
    ], gold


def test_checks_every_step_not_only_the_flat_rows_event(sample):
    events, gold = sample
    result = runner.inspect(events, gold)
    assert result["review"] == "passed"
    assert result["resultCorrect"] is result["coverageCorrect"] is True
    assert result["stepCount"] == 2 and result["budgetCorrect"] is True
    assert "West" not in json.dumps(result) and "100.01" not in json.dumps(result)


@pytest.mark.parametrize(
    "damage", ["measure", "grouping", "dependency", "period", "baseline", "filter"]
)
def test_numerically_right_but_different_question_fails(sample, damage):
    events, gold = sample
    meta = events[0]["data"]
    if damage == "measure":
        meta["analyticalPlan"]["steps"][1]["request"]["measures"] = [{"id": "units_sold"}]
    elif damage == "grouping":
        meta["analyticalPlan"]["steps"][1]["request"]["group_by"] = ["dim_carline.model"]
    elif damage == "dependency":
        meta["analyticalPlan"]["steps"][1]["depends_on"] = []
    elif damage == "period":
        meta["analyticalPresentation"]["steps"][1]["searchPeriod"]["start"] = "2026-02-01"
    elif damage == "baseline":
        meta["analyticalPresentation"]["steps"][1]["baseline"] = {"kind": "same_period_last_year"}
    else:
        meta["analyticalPresentation"]["steps"][1]["filters"] = [
            {"field": "dim_carline.model", "operator": "ne", "values": ["Hidden exclusion"]}
        ]
    result = runner.inspect(events, gold)
    assert result["resultCorrect"] is True
    assert result["coverageCorrect"] is False and result["review"] == "failed"


@pytest.mark.parametrize(
    "damage", ["missing_step", "extra_step", "wrong_value", "null", "extra_column"]
)
def test_omitted_or_corrupted_results_cannot_pass(sample, damage):
    events, gold = sample
    steps = events[0]["data"]["analyticalExecution"]["steps"]
    if damage == "missing_step":
        steps.pop()
    elif damage == "extra_step":
        steps.append(copy.deepcopy(steps[-1]))
    elif damage == "wrong_value":
        steps[-1]["rows"][0]["revenue"] = "999"
    elif damage == "null":
        steps[-1]["rows"][0]["revenue"] = None
    else:
        steps[-1]["rows"][0]["uncheckedMetric"] = 7
    assert runner.inspect(events, gold)["review"] == "failed"


def test_absent_reference_and_unreviewed_narration_do_not_pass(sample):
    events, gold = sample
    assert runner.inspect(events)["review"] == "incomplete_gold"
    gold.pop("reference")
    assert runner.inspect(events, gold)["review"] == "incomplete_gold"
    gold.pop("text")
    assert runner.inspect(events, gold)["narrationCorrect"] is None


def test_missing_coverage_field_is_incomplete_not_success(sample):
    events, gold = sample
    gold["analysis"]["steps"][1].pop("filters")
    result = runner.inspect(events, gold)
    assert result["coverageCorrect"] is None and result["review"] == "incomplete_gold"


@pytest.mark.parametrize("damage", ["status", "columns", "displayedRows", "summary"])
def test_visible_answer_must_match_the_executed_evidence(sample, damage):
    events, gold = sample
    shown = events[0]["data"]["analyticalPresentation"]["steps"][1]
    shown[damage] = {
        "status": "partial",
        "columns": [],
        "displayedRows": 0,
        "summary": "Unverified numerical story",
    }[damage]
    assert runner.inspect(events, gold)["review"] == "failed"


def test_actual_model_call_cap_and_missing_usage(sample):
    events, gold = sample
    events[0]["data"]["runUsage"]["correctionModelCalls"] = 1
    assert runner.inspect(events, gold)["review"] == "failed"
    events[0]["data"].pop("runUsage")
    assert runner.inspect(events, gold)["review"] == "incomplete_usage"


def test_narrative_failure_and_privacy_allowlist(sample):
    events, gold = sample
    events[-1]["data"]["token"] = "An unsupported causal claim."
    events[0]["data"]["runUsage"]["privateProviderPayload"] = "secret"
    result = runner.inspect(events, gold)
    assert result["resultCorrect"] is True and result["narrationCorrect"] is False
    assert result["review"] == "failed" and "secret" not in json.dumps(result)


def test_numeric_precision_ties_and_duplicate_rows_are_explicit():
    compare = runner._reference_rows
    assert not compare([{"n": "1.0000001"}], [{"n": 1}], ["n"], {"n": "integer"}, "ordered")
    assert compare(
        [{"n": "1000000000000.000001"}], [{"n": "1000000000000"}], ["n"], {"n"}, "ordered"
    )
    assert not compare([{"n": "1000000000001"}], [{"n": "1000000000000"}], ["n"], {"n"}, "ordered")
    assert not compare([{"n": "NaN"}], [{"n": 0}], ["n"], {"n"}, "ordered")
    assert compare([{"n": 1}, {"n": 2}], [{"n": 2}, {"n": 1}], ["n"], {"n"}, "unordered")
    assert not compare([{"n": 1}, {"n": 1}], [{"n": 1}, {"n": 2}], ["n"], {"n"}, "unordered")
    assert not compare([{"name": "1"}], [{"name": 1}], ["name"], set(), "ordered")


def test_terminal_denial_cannot_hide_data_in_step_metadata(sample):
    events, _ = sample
    events[0]["data"]["responseKind"] = "denied"
    events[0]["data"]["analyticalExecution"]["status"] = "denied"
    result = runner.inspect(events, {"responseKind": "denied", "text": "West leads."})
    assert result["review"] == "failed"
    assert result["failureCode"] == "terminal_response_exposed_evidence"


def test_display_scope_must_match_execution_scope(sample):
    events, gold = sample
    events[0]["data"]["analyticalExecution"]["scope_labels"] = ["South"]
    assert runner.inspect(events, gold)["review"] == "failed"


def test_summary_does_not_count_unknown_as_correct():
    result = runner.summarize(
        [
            {"routeCorrect": True, "resultCorrect": False, "latencyMs": 10},
            {"routeCorrect": None, "latencyMs": 50},
        ]
    )
    assert result["checks"]["routeCorrect"] == {"passed": 1, "failed": 0, "unknown": 1}
    assert result["checks"]["resultCorrect"] == {"passed": 0, "failed": 1, "unknown": 1}
    assert result["fullyPassed"] == 0 and result["rolloutApproved"] is False


def test_offline_preflight_requires_reviewed_full_references(sample):
    _, gold = sample
    cases = [{"id": "SYNTHETIC", "question": "Visible synthetic fixture only"}]
    report = runner.validate_inputs(cases, {"SYNTHETIC": gold}, "synthetic-v1")
    assert report["dependentReferences"] == 1 and report["holdoutsDeclaredByReviewer"] == 0
    assert report["rolloutApproved"] is False
    with pytest.raises(ValueError, match="revision"):
        runner.validate_inputs(cases, {"SYNTHETIC": gold}, "wrong")
    gold["analysis"]["steps"][0].pop("rows")
    with pytest.raises(ValueError, match="every structural"):
        runner.validate_inputs(cases, {"SYNTHETIC": gold}, "synthetic-v1")


def test_preflight_rejects_incomplete_inputs_before_login(sample, tmp_path, monkeypatch):
    from types import SimpleNamespace

    _, gold = sample
    gold["analysis"]["steps"][0].pop("rows")
    cases = tmp_path / "cases.json"
    references = tmp_path / "gold.json"
    cases.write_text(json.dumps([{"id": "S", "question": "Visible synthetic fixture"}]))
    references.write_text(json.dumps({"S": gold}))
    monkeypatch.setattr(runner.getpass, "getpass", lambda *args: pytest.fail("login prompt"))
    monkeypatch.setattr(runner.request, "build_opener", lambda *args: pytest.fail("network"))
    with pytest.raises(ValueError, match="every structural"):
        runner.capture(
            SimpleNamespace(
                base_url="http://localhost:8000",
                cases=str(cases),
                gold=str(references),
                warehouse_revision="synthetic-v1",
            )
        )


def test_dependent_matched_comparison_requires_revision_account_and_correct_modes(sample):
    events, gold = sample
    result = runner.inspect(events, gold)
    result.update(id="synthetic", mode="typed", configuredModel="same", cacheHit=False)
    common = {
        "caseHash": "same",
        "datasetLabel": "same",
        "expectedModel": "same",
        "goldHash": "same",
        "principalHash": "same",
        "warehouseRevision": "v1",
    }
    before = {
        **common,
        "label": "typed-baseline",
        "cases": [{**result, "dependentObserved": False}],
    }
    after = {**common, "label": "dependent", "cases": [result]}
    assert runner.compare(before, after)["pairs"][0]["comparable"]
    assert runner.compare(before, after)["rolloutApproved"] is False
    after["cases"][0]["usage"]["modelsUsed"] = ["same", "fallback"]
    assert not runner.compare(before, after)["pairs"][0]["comparable"]
    after["cases"][0]["usage"]["modelsUsed"] = ["same", "same"]
    before["warehouseRevision"] = "v2"
    with pytest.raises(ValueError, match="revision"):
        runner.compare(before, after)
