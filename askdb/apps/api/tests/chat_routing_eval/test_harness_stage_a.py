"""Stage A: harness pre-plan path matches frozen baseline when router/guard off."""

from __future__ import annotations

from pathlib import Path

EVAL_DIR = Path(__file__).resolve().parent
API_ROOT = EVAL_DIR.parents[1]
import sys

if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))

from app.core.config import Settings  # noqa: E402
from tests.chat_routing_eval.run_baseline import (  # noqa: E402
    STAGE0_CSV,
    compute_metrics,
    load_cases,
    load_csv_rows,
    replay_case,
    stage0_rows,
)


def test_harness_preplan_matches_frozen_baseline_with_classifier_disabled() -> None:
    settings = Settings(chat_router_enabled=False)
    cases = load_cases(EVAL_DIR / "chat_routing_eval.yaml")
    rows = [
        replay_case(
            c,
            settings=settings,
            router_enabled=False,
            guard_enabled=False,
            rewrites_enabled=False,
        )
        for c in cases
    ]
    frozen = load_csv_rows(STAGE0_CSV)
    for row in stage0_rows(rows):
        old = frozen.get(row.id)
        assert old is not None, row.id
        assert old["predicted_label"] == row.predicted_label, (
            f"{row.id}: was {old['predicted_label']} now {row.predicted_label}"
        )
        assert old["match"] == row.match
        assert old.get("plan_expect_match", "n/a") == row.plan_expect_match

    metrics = compute_metrics(stage0_rows(rows))
    assert metrics["correct"] == 53
    assert metrics["total"] == 79
