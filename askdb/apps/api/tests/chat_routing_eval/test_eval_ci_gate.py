"""Stage F: CI gate on the routing eval.

Fails when DATA_QUERY / DATA_FOLLOW_UP recall drops below the frozen Stage 0 baseline, when
any label falls below its floor, or when a case that matched in the baseline stops matching.
Runs in-process with no LLM calls and writes no result files.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

EVAL_DIR = Path(__file__).resolve().parent
API_ROOT = EVAL_DIR.parents[1]
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))

from app.core.config import Settings  # noqa: E402
from tests.chat_routing_eval.run_baseline import (  # noqa: E402
    EVAL_FILE,
    STAGE0_CSV,
    ReplayRow,
    compute_metrics,
    load_cases,
    load_csv_rows,
    replay_case,
    stage0_rows,
)

DATA_LABELS = ("DATA_QUERY", "DATA_FOLLOW_UP")

# Set from the final Stage E run (router + follow-up guard + question rewrites).
RECALL_FLOORS = {
    "APP_HELP": 1.0,
    "CLARIFICATION": 1.0,
    "DATA_FOLLOW_UP": 1.0,
    "DATA_QUERY": 30 / 31,
    "DOCUMENT_QUERY": 1.0,
    "GENERAL_CHAT": 1.0,
    "GENERAL_KNOWLEDGE": 1.0,
    "OUT_OF_SCOPE_LIVE": 1.0,
    "UNSUPPORTED": 1.0,
}
# Anything predicted as a data label runs SQL, so data precision must stay perfect.
PRECISION_FLOORS = {"DATA_QUERY": 1.0, "DATA_FOLLOW_UP": 1.0}


@pytest.fixture(scope="module")
def current() -> tuple[list[ReplayRow], dict]:
    settings = Settings(chat_router_enabled=True, chat_follow_up_guard_enabled=True)
    rows = [
        replay_case(
            case,
            settings=settings,
            router_enabled=True,
            guard_enabled=True,
            rewrites_enabled=True,
        )
        for case in load_cases(EVAL_FILE)
    ]
    return rows, compute_metrics(stage0_rows(rows))


@pytest.fixture(scope="module")
def baseline() -> tuple[dict[str, dict[str, str]], dict]:
    frozen = load_csv_rows(STAGE0_CSV)
    rows = [
        ReplayRow(**{name: r.get(name, "") for name in ReplayRow.__dataclass_fields__})
        for r in frozen.values()
        if r.get("expected_stage") != "1"
    ]
    return frozen, compute_metrics(rows)


@pytest.mark.parametrize("label", DATA_LABELS)
def test_data_recall_not_below_frozen_baseline(label: str, current, baseline) -> None:
    now = current[1]["per_label"][label]["recall"]
    before = baseline[1]["per_label"][label]["recall"]
    assert now >= before, f"{label} recall {now:.1%} < baseline {before:.1%}"


@pytest.mark.parametrize(("label", "floor"), sorted(RECALL_FLOORS.items()))
def test_recall_floor(label: str, floor: float, current) -> None:
    stats = current[1]["per_label"][label]
    assert stats["recall"] + 1e-9 >= floor, (
        f"{label} recall {stats['tp']}/{stats['support']} below floor {floor:.1%}"
    )


@pytest.mark.parametrize(("label", "floor"), sorted(PRECISION_FLOORS.items()))
def test_data_precision_floor(label: str, floor: float, current) -> None:
    stats = current[1]["per_label"][label]
    assert stats["precision"] + 1e-9 >= floor, (
        f"{label} precision {stats['tp']}/{stats['predicted_as']} below floor {floor:.1%}"
    )


def test_no_case_regresses_from_frozen_baseline(current, baseline) -> None:
    frozen = baseline[0]
    regressed = [
        row.id
        for row in stage0_rows(current[0])
        if frozen.get(row.id, {}).get("match") == "true" and row.match != "true"
    ]
    assert regressed == []


def test_plan_expectations_hold(current) -> None:
    failures = [row.id for row in current[0] if row.plan_expect_match == "false"]
    assert failures == []
