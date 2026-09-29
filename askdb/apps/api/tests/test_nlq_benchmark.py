"""NLQ accuracy floor: the governed planner must keep answering the benchmark suites."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

_RUNNER = Path(__file__).with_name("benchmark") / "run_benchmark.py"
_spec = importlib.util.spec_from_file_location("nlq_benchmark_runner", _RUNNER)
assert _spec is not None and _spec.loader is not None
runner = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = runner
_spec.loader.exec_module(runner)

ACCURACY_FLOOR = 95.0


@pytest.mark.parametrize("suite", ["nlq_benchmark.yaml", "nlq_holdout.yaml"])
def test_nlq_accuracy_floor(suite: str) -> None:
    results = runner.run(_RUNNER.with_name(suite))
    summary = runner.summarise(results)
    misses = [
        f"{r['id']} [{r['verdict']}] {r['question']}: {'; '.join(r['checks_failed'])[:120]}"
        for r in results
        if r["verdict"] != "correct"
    ]
    assert summary["accuracy"] >= ACCURACY_FLOOR, "\n".join(misses)


def test_no_benchmark_question_needs_the_llm() -> None:
    results = runner.run(_RUNNER.with_name("nlq_benchmark.yaml"))
    needs_llm = [r["id"] for r in results if "no_compiled_sql" in " ".join(r["checks_failed"])]
    assert not needs_llm
