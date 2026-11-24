"""
features/question_cache/cache_triggers.py
Heuristics for when to store a result snapshot alongside saved SQL.
No LLM calls.
"""
import pandas as pd

_TIME_SENSITIVE_WORDS = ("today", "now", "current")


def should_cache_result(question: str, df: pd.DataFrame, result_df: pd.DataFrame) -> bool:
    """Return True when the result is small enough and not time-sensitive."""
    if result_df is None or result_df.empty:
        return False
    if len(result_df) > 5000:
        return False
    q_lower = (question or "").lower()
    if any(word in q_lower for word in _TIME_SENSITIVE_WORDS):
        return False
    return True
