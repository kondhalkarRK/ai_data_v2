"""
features/materialized_views/view_store.py
In-memory materialized view cache with optional disk persistence.
Pure Pandas caching — no LLM calls.
"""
import pickle
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd
import streamlit as st

_SESSION_KEY = "materialized_views"
_CACHE_DIR = Path("rag_storage") / "materialized_cache"


def _ensure_cache_dir() -> Path:
    """Create the disk cache directory if it does not exist."""
    _CACHE_DIR.mkdir(parents=True, exist_ok=True)
    return _CACHE_DIR


def _ensure_session_store() -> dict:
    """Lazy-init the in-memory view store inside st.session_state."""
    if _SESSION_KEY not in st.session_state:
        st.session_state[_SESSION_KEY] = {}
    return st.session_state[_SESSION_KEY]


def _disk_path(key: str) -> Path:
    """Resolve the pickle file path for a given view key."""
    return _ensure_cache_dir() / f"{key}.pkl"


def _entry_is_fresh(entry: dict) -> bool:
    """Return True when a cache entry is still within its TTL window."""
    saved_at = entry["saved_at"]
    ttl = entry.get("ttl_minutes", 60)
    return datetime.utcnow() < saved_at + timedelta(minutes=ttl)


def _load_entry(key: str) -> dict | None:
    """Load a cache entry from session state or disk."""
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
    """Delete a cache entry from session state and disk."""
    store = _ensure_session_store()
    store.pop(key, None)
    path = _disk_path(key)
    if path.exists():
        path.unlink(missing_ok=True)


def save_view(key: str, df: pd.DataFrame, ttl_minutes: int = 60) -> None:
    """Persist a result DataFrame under key in session state and on disk."""
    entry = {
        "df": df.copy(),
        "saved_at": datetime.utcnow(),
        "ttl_minutes": ttl_minutes,
    }
    _ensure_session_store()[key] = entry
    with open(_disk_path(key), "wb") as f:
        pickle.dump(entry, f)


def get_view(key: str) -> pd.DataFrame | None:
    """Return a fresh cached DataFrame for key, or None if missing/expired."""
    entry = _load_entry(key)
    if entry is None or not _entry_is_fresh(entry):
        return None
    return entry["df"].copy()


def is_view_fresh(key: str) -> bool:
    """Check whether a cached view exists and has not expired."""
    entry = _load_entry(key)
    return entry is not None and _entry_is_fresh(entry)


def clear_expired_views() -> int:
    """Remove expired views from session state and disk. Returns count removed."""
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


def clear_all_views() -> int:
    """Remove every materialized view from memory and disk. Returns count removed."""
    store = _ensure_session_store()
    _ensure_cache_dir()
    all_keys = set(store.keys()) | {p.stem for p in _CACHE_DIR.glob("*.pkl")}
    count = len(all_keys)
    store.clear()
    for path in _CACHE_DIR.glob("*.pkl"):
        path.unlink(missing_ok=True)
    return count


def count_active_views() -> int:
    """Return the number of non-expired materialized views."""
    store = _ensure_session_store()
    _ensure_cache_dir()
    all_keys = set(store.keys()) | {p.stem for p in _CACHE_DIR.glob("*.pkl")}
    return sum(1 for key in all_keys if is_view_fresh(key))
