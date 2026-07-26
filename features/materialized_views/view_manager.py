"""
features/materialized_views/view_manager.py
Key generation and lookup/materialization for cached query results.
No LLM calls — pure cache orchestration.
"""
import hashlib

import pandas as pd

from features.materialized_views import view_store


def build_view_key(question: str, df: pd.DataFrame) -> str:
    """Build a stable cache key from normalized question text and df fingerprint."""
    q_norm = " ".join(question.lower().strip().split())
    cols = ",".join(sorted(str(c) for c in df.columns))
    fingerprint = f"{df.shape[0]}x{df.shape[1]}:{cols}"
    raw = f"{q_norm}|{fingerprint}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def get_or_none(question: str, df: pd.DataFrame) -> pd.DataFrame | None:
    """Return a fresh cached result for this question/dataset pair, else None."""
    key = build_view_key(question, df)
    return view_store.get_view(key)


def materialize(question: str, df: pd.DataFrame, result_df: pd.DataFrame) -> None:
    """Save a successful query result into the materialized view store."""
    key = build_view_key(question, df)
    view_store.save_view(key, result_df)
