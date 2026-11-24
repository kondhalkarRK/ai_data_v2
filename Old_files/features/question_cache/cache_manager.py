"""
features/question_cache/cache_manager.py
Lookup and save question → SQL (+ optional result) pairs.
No LLM calls.
"""
import hashlib

import pandas as pd

from features.question_cache import cache_store

_SAVED_SQL_PREFIX = "-- served from saved question --"


def normalize_question(question: str) -> str:
    return " ".join((question or "").lower().strip().split())


def build_dataset_fingerprint(df: pd.DataFrame) -> str:
    cols = ",".join(sorted(str(c) for c in df.columns))
    return f"{df.shape[0]}x{df.shape[1]}:{cols}"


def build_cache_key(question: str, df: pd.DataFrame) -> str:
    raw = f"{normalize_question(question)}|{build_dataset_fingerprint(df)}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def lookup(question: str, df: pd.DataFrame) -> dict | None:
    """
    Return a fresh saved entry: {question, sql, result_df}.
    result_df may be None when only SQL was stored.
    """
    key = build_cache_key(question, df)
    entry = cache_store.get_entry(key)
    if not entry or not entry.get("sql"):
        return None
    sql = str(entry["sql"]).strip()
    if not sql or sql.startswith(_SAVED_SQL_PREFIX):
        return None
    result_df = entry.get("result_df")
    return {
        "question": entry.get("question") or question,
        "sql": sql,
        "result_df": result_df.copy() if isinstance(result_df, pd.DataFrame) else None,
    }


def save(
    question: str,
    df: pd.DataFrame,
    sql: str,
    result_df: pd.DataFrame | None = None,
    *,
    ttl_minutes: int = 60,
) -> None:
    """Store question + SQL; optionally include a small result snapshot."""
    if not question or not sql:
        return
    sql = sql.strip()
    if sql.startswith(_SAVED_SQL_PREFIX):
        return
    key = build_cache_key(question, df)
    cache_store.save_entry(
        key,
        question=normalize_question(question),
        sql=sql,
        result_df=result_df,
        ttl_minutes=ttl_minutes,
    )


def saved_sql_marker() -> str:
    return _SAVED_SQL_PREFIX
