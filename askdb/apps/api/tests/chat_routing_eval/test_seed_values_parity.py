"""Seed vocabulary parity with the NLQ benchmark dictionary."""

from __future__ import annotations

import sys
from pathlib import Path

API_ROOT = Path(__file__).resolve().parents[2]
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))

EVAL_DIR = Path(__file__).resolve().parent
if str(EVAL_DIR) not in sys.path:
    sys.path.insert(0, str(EVAL_DIR))

from app.core.config import Industry  # noqa: E402
from seed_values import seed_values_for_industry  # noqa: E402
from tests.benchmark.run_benchmark import _seed_values  # noqa: E402


def _triples(values: tuple) -> set[tuple[str, str, str]]:
    return {(v.domain, v.column, v.value) for v in values}


def test_seed_values_match_benchmark_vocabulary() -> None:
    for industry in (Industry.AUTOMOTIVE, Industry.INSURANCE):
        assert _triples(seed_values_for_industry(industry)) == _triples(
            _seed_values(industry)
        )
