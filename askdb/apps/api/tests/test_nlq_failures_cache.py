"""Unit tests for failure classification and query cache freshness."""

from __future__ import annotations

import time

from app.services.chat.failures import (
    classify_database,
    classify_llm_failure,
    classify_sql_validation,
)
from app.services.chat.query_cache import QUERY_CACHE, CachedAnswer, normalize_question


def test_classify_llm_timeout() -> None:
    info = classify_llm_failure("Timeout")
    assert info.category == "llm"
    assert "Timeout" in info.reason


def test_classify_db_timeout() -> None:
    info = classify_database("canceling statement due to statement_timeout")
    assert info.category == "database"
    assert "timeout" in info.reason.lower()


def test_classify_sql_validation() -> None:
    info = classify_sql_validation("Unknown column vehicle_type")
    assert info.category == "sql_generation"


def test_query_cache_freshness_invalidation() -> None:
    industry = "automotive"
    question = "revenue by month unique " + str(time.time())
    answer = CachedAnswer(
        sql="SELECT 1",
        columns=["x"],
        rows=[{"x": 1}],
        chart=None,
        meta={},
        narrative="ok",
        followups=[],
        path="template",
        data_as_of="2024-01-01",
        created_at=time.time(),
        tables=["automotive.fact_sales"],
    )
    QUERY_CACHE.put(industry=industry, question=question, answer=answer)
    hit = QUERY_CACHE.get(
        industry=industry, question=question, current_data_as_of="2024-01-01"
    )
    assert hit is not None
    miss = QUERY_CACHE.get(
        industry=industry, question=question, current_data_as_of="2024-06-01"
    )
    assert miss is None


def test_normalize_question() -> None:
    assert normalize_question("  Top Selling Car? ") == "top selling car"
