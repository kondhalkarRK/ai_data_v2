"""
tools/golden_insurance_nlq_smoke.py

Lightweight golden-question smoke for insurance conversation routing
(no live warehouse / LLM required).

Usage:
  python tools/golden_insurance_nlq_smoke.py
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.question_normaliser import (
    detect_followup,
    is_standalone_analytical_question,
)
from core.sql_guardrails import sql_is_safe
from ui.tab_query import detect_destructive


STANDALONE = [
    "Show claims by region for 2025",
    "Show claim count by region for 2025",
    "just show GWP by product for 2025",
    "Show loss ratio by region for 2025",
    "Total sale of policy across type",
    "Earned premium by LOB",
]

ALLOW_ANALYTICAL = [
    "show drop in loss ratio by region",
    "status update on claims for 2025",
]

BLOCK_MUTATION = [
    "drop table fact_claims",
    "delete from insurance.fact_claims",
]

SAFE_SQL = [
    "SELECT 1",
    "WITH x AS (SELECT 1 AS n) SELECT n FROM x",
]

UNSAFE_SQL = [
    "WITH x AS (DELETE FROM t RETURNING *) SELECT * FROM x",
    "SELECT * INTO tmp FROM t",
    "SELECT * FROM t FOR UPDATE",
]


def main() -> int:
    failed = 0
    for q in STANDALONE:
        if not is_standalone_analytical_question(q):
            print(f"FAIL standalone: {q!r}")
            failed += 1
        elif detect_followup(q):
            print(f"FAIL not-followup: {q!r}")
            failed += 1
        else:
            print(f"OK standalone: {q!r}")

    for q in ALLOW_ANALYTICAL:
        if detect_destructive(q):
            print(f"FAIL allow analytical: {q!r}")
            failed += 1
        else:
            print(f"OK analytical: {q!r}")

    for q in BLOCK_MUTATION:
        if not detect_destructive(q):
            print(f"FAIL block mutation: {q!r}")
            failed += 1
        else:
            print(f"OK block: {q!r}")

    for sql in SAFE_SQL:
        if not sql_is_safe(sql)[0]:
            print(f"FAIL safe sql: {sql!r}")
            failed += 1
    for sql in UNSAFE_SQL:
        if sql_is_safe(sql)[0]:
            print(f"FAIL unsafe sql: {sql!r}")
            failed += 1

    if failed:
        print(f"\n{failed} check(s) failed")
        return 1
    print("\nAll golden smoke checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
