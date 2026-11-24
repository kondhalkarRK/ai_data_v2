"""
features/question_cache/cache_store.py
Persistent saved-question cache — stores question + SQL (+ optional result).
No LLM calls.
"""
import pickle
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd
import streamlit as st

_SESSION_KEY = "saved_questions"
_CACHE_DIR = Path("rag_storage") / "question_cache"


def _ensure_cache_dir() -> Path:
    _CACHE_DIR.mkdir(parents=True, exist_ok=True)
    return _CACHE_DIR


def _ensure_session_store() -> dict:
    if _SESSION_KEY not in st.session_state:
        st.session_state[_SESSION_KEY] = {}
    return st.session_state[_SESSION_KEY]


def _disk_path(key: str) -> Path:
    return _ensure_cache_dir() / f"{key}.pkl"


def _entry_is_fresh(entry: dict) -> bool:
    saved_at = entry["saved_at"]
    ttl = entry.get("ttl_minutes", 60)
    return datetime.utcnow() < saved_at + timedelta(minutes=ttl)


def _load_entry(key: str) -> dict | None:
    store = _ensure_session_store()
    if key in store:
        return store[key]
    path = _disk_path(key)
    if not path.exists():
        return None
    try:
        with open(path, "rb") as f:
            entry = pickle.load(f)
        store[key] = entry
        return entry
    except Exception:
        return None


def _remove_entry(key: str) -> None:
    store = _ensure_session_store()
    store.pop(key, None)
    path = _disk_path(key)
    if path.exists():
        path.unlink(missing_ok=True)


def save_entry(
    key: str,
    *,
    question: str,
    sql: str,
    result_df: pd.DataFrame | None = None,
    ttl_minutes: int = 60,
) -> None:
    """Persist a saved question under key in session state and on disk."""
    entry = {
        "question": question,
        "sql": sql,
        "result_df": result_df.copy() if result_df is not None else None,
        "saved_at": datetime.utcnow(),
        "ttl_minutes": ttl_minutes,
    }
    _ensure_session_store()[key] = entry
    with open(_disk_path(key), "wb") as f:
        pickle.dump(entry, f)


def get_entry(key: str) -> dict | None:
    """Return a fresh cache entry for key, or None if missing/expired."""
    entry = _load_entry(key)
    if entry is None or not _entry_is_fresh(entry):
        return None
    return entry


def clear_expired() -> int:
    store = _ensure_session_store()
    _ensure_cache_dir()
    all_keys = set(store.keys()) | {p.stem for p in _CACHE_DIR.glob("*.pkl")}
    removed = 0
    for key in all_keys:
        entry = _load_entry(key)
        if entry is None or not _entry_is_fresh(entry):
            _remove_entry(key)
            removed += 1
    return removed


def clear_all() -> int:
    store = _ensure_session_store()
    _ensure_cache_dir()
    all_keys = set(store.keys()) | {p.stem for p in _CACHE_DIR.glob("*.pkl")}
    count = len(all_keys)
    store.clear()
    for path in _CACHE_DIR.glob("*.pkl"):
        path.unlink(missing_ok=True)
    return count


def count_active() -> int:
    store = _ensure_session_store()
    _ensure_cache_dir()
    all_keys = set(store.keys()) | {p.stem for p in _CACHE_DIR.glob("*.pkl")}
    return sum(
        1 for key in all_keys
        if (entry := _load_entry(key)) is not None and _entry_is_fresh(entry)
    )


def list_recent(limit: int = 8) -> list[dict]:
    """Return recent saved questions for sidebar display."""
    _ensure_cache_dir()
    items: list[dict] = []
    for path in sorted(_CACHE_DIR.glob("*.pkl"), key=lambda p: p.stat().st_mtime, reverse=True):
        try:
            with open(path, "rb") as f:
                entry = pickle.load(f)
            if not _entry_is_fresh(entry):
                continue
            items.append({
                "question": entry.get("question") or "",
                "has_result": entry.get("result_df") is not None,
                "saved_at": entry.get("saved_at"),
            })
            if len(items) >= limit:
                break
        except Exception:
            continue
    return items
