"""Tests for evaluation integrity, without a login or network call."""

import importlib.util
import json
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location(
    "acceptance", Path(__file__).resolve().parents[4] / "scripts/chat_acceptance.py"
)
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)


def test_correct_route_with_wrong_numbers_fails():
    events = [
        {"event": "meta", "data": {"route": "sql", "executionMode": "typed"}},
        {"event": "columns", "data": {"columns": ["units"]}},
        {"event": "rows", "data": {"rows": [{"units": 9}]}},
    ]
    result = runner.inspect(
        events, {"route": "analytics", "columns": ["units"], "rows": [{"units": 10}]}
    )
    assert result["routeCorrect"] is True and result["answerCorrect"] is False
    assert result["review"] == "failed"
    assert '"units": 9' not in json.dumps(result)  # No raw result copied into capture.


def test_absent_gold_and_usage_are_not_fabricated_successes():
    result = runner.inspect([])
    assert result["review"] == "unreviewed" and result["answerCorrect"] is None
    assert result["usage"] is None


@pytest.mark.parametrize(
    "url",
    [
        "http://company.example",
        "https://user:secret@company.example",
        "https://company.example?key=secret",
    ],
)
def test_unsafe_capture_endpoints_are_rejected(url):
    with pytest.raises(ValueError):
        runner.validate_url(url)


def test_null_is_not_zero_and_rows_keep_ranking_order():
    assert not runner.equal(None, 0)
    assert not runner.equal([1, 2], [2, 1])
    assert runner.equal(1.0, 1)
    assert not runner.equal(True, 1)
    assert not runner.equal(1_000_000_000_000, 1_000_000_000_001)


def test_mismatched_runs_are_not_compared():
    with pytest.raises(ValueError):
        runner.compare({"datasetLabel": "old"}, {"datasetLabel": "new"})


def test_data_match_without_narrative_review_is_not_a_complete_pass():
    events = [
        {"event": "meta", "data": {"route": "sql", "responseKind": "data"}},
        {"event": "rows", "data": {"rows": [{"revenue": 100}]}},
        {"event": "columns", "data": {"columns": ["revenue"]}},
    ]
    scored = runner.inspect(
        events, {"route": "analytics", "columns": ["revenue"], "rows": [{"revenue": 100}]}
    )
    assert scored["resultCorrect"] is True
    assert scored["narrationCorrect"] is None and scored["answerCorrect"] is None
    assert scored["review"] == "incomplete_gold"


def test_same_model_with_different_principal_is_not_paired():
    common = {
        "caseHash": "same",
        "datasetLabel": "same",
        "expectedModel": "same",
        "goldHash": "same",
        "cases": [],
    }
    with pytest.raises(ValueError):
        runner.compare(
            {**common, "label": "legacy", "principalHash": "admin"},
            {**common, "label": "typed", "principalHash": "regional"},
        )
