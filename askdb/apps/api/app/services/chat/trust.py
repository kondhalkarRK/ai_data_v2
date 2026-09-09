"""Legacy four-component trust score (0-100)."""

from __future__ import annotations

from typing import Any


def compute_trust_score(
    *,
    glossary_matches: int,
    glossary_hints_are_sql: bool,
    resolution_path: str,
    row_count: int,
) -> tuple[int, dict[str, Any]]:
    """Port of ``ui.tab_query.compute_trust_score`` components.

    Components are 0-25 each. Empty results are capped at 45.
    """
    if glossary_matches >= 2:
        semantic = 25
    elif glossary_matches == 1:
        semantic = 12
    else:
        semantic = 0

    if glossary_hints_are_sql:
        glossary = 25
    elif glossary_matches > 0:
        glossary = 12
    else:
        glossary = 0

    path = resolution_path.lower()
    if path in {"retry", "error"}:
        sql_validation = 5
    elif path in {"semantic", "semantic_llm", "template"}:
        sql_validation = 25
    elif path in {"cache", "saved"}:
        sql_validation = 20
    elif path == "fallback":
        sql_validation = 10
    else:
        sql_validation = 5

    if path in {"semantic", "semantic_llm", "template"}:
        join_quality = 25
    elif path in {"cache", "saved"}:
        join_quality = 20
    elif path == "fallback":
        join_quality = 10
    else:
        join_quality = 5

    score = semantic + glossary + sql_validation + join_quality
    breakdown: dict[str, Any] = {
        "semantic": semantic,
        "glossary": glossary,
        "sql_validation": sql_validation,
        "join_quality": join_quality,
        "resolution_path": resolution_path,
    }
    if row_count == 0:
        score = min(score, 45)
        breakdown["empty_cap"] = True
    return score, breakdown
