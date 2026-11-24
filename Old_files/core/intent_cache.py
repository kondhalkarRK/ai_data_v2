"""
core/intent_cache.py
Two-layer intent cache: session (Layer 1) + disk JSON (Layer 2).
"""
from __future__ import annotations

import json
import os
from typing import Any

import streamlit as st

_DIR = os.path.dirname(os.path.abspath(__file__))
_CACHE_DIR = os.path.join(os.path.dirname(_DIR), "rag_storage", "intent_cache")
_CACHE_FILE = os.path.join(_CACHE_DIR, "intents.json")


def _ensure_disk() -> dict[str, Any]:
    os.makedirs(_CACHE_DIR, exist_ok=True)
    if not os.path.exists(_CACHE_FILE):
        return {}
    try:
        with open(_CACHE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def _write_disk(data: dict[str, Any]) -> None:
    os.makedirs(_CACHE_DIR, exist_ok=True)
    try:
        with open(_CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, default=str)
    except OSError:
        pass


def _session_store() -> dict[str, Any]:
    if "intent_session_cache" not in st.session_state:
        st.session_state.intent_session_cache = {}
    return st.session_state.intent_session_cache


def get_cached_intent(fingerprint: str) -> dict | None:
    """Look up intent by question fingerprint (session then disk)."""
    if not fingerprint:
        return None
    session = _session_store()
    if fingerprint in session:
        hit = session[fingerprint]
        if isinstance(hit, dict):
            hit = dict(hit)
            hit["_cache_layer"] = "session"
            return hit
    disk = _ensure_disk()
    if fingerprint in disk and isinstance(disk[fingerprint], dict):
        hit = dict(disk[fingerprint])
        session[fingerprint] = hit
        hit["_cache_layer"] = "disk"
        return hit
    return None


def store_intent(fingerprint: str, intent: dict) -> None:
    """Store intent in both session and disk caches."""
    if not fingerprint or not isinstance(intent, dict):
        return
    clean = {k: v for k, v in intent.items() if not str(k).startswith("_")}
    session = _session_store()
    session[fingerprint] = clean
    disk = _ensure_disk()
    disk[fingerprint] = clean
    _write_disk(disk)


def clear_intent_cache() -> None:
    """Clear session + disk intent caches."""
    st.session_state.intent_session_cache = {}
    _write_disk({})
