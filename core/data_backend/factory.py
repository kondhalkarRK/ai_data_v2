"""Backend selection for Streamlit and non-UI callers."""
from __future__ import annotations

import logging

import pandas as pd
import streamlit as st

from config.settings import (
    get_data_config,
    is_loopback_host,
    is_streamlit_cloud,
)
from core.data_backend.base import DataBackend
from core.data_backend.csv_duckdb import CsvDuckDbBackend
from core.data_backend.postgres import PostgresBackend

logger = logging.getLogger(__name__)


@st.cache_resource(show_spinner=False)
def _postgres_backend(config_items: tuple[tuple[str, object], ...]) -> PostgresBackend:
    return PostgresBackend(dict(config_items))


def get_configured_backend_id() -> str:
    configured = get_data_config()["backend"]
    return configured if configured in {"csv_duckdb", "postgres"} else "csv_duckdb"


def get_active_backend_id() -> str:
    configured = get_configured_backend_id()
    try:
        selected = st.session_state.get("data_backend", configured)
    except Exception:
        selected = configured
    return selected if selected in {"csv_duckdb", "postgres"} else configured


def get_backend(
    working_df: pd.DataFrame | None = None,
    extra_tables: dict[str, pd.DataFrame] | None = None,
) -> DataBackend:
    config = get_data_config()
    if get_active_backend_id() == "postgres":
        items = tuple(sorted(config["postgres"].items()))
        return _postgres_backend(items)
    return CsvDuckDbBackend(working_df, extra_tables)


def postgres_mode_enabled() -> bool:
    return get_active_backend_id() == "postgres"


def is_postgres_fallback_active() -> bool:
    """True when secrets want Postgres but this session is on CSV fallback."""
    try:
        reason = st.session_state.get("_postgres_fallback_reason")
    except Exception:
        reason = None
    return (
        get_configured_backend_id() == "postgres"
        and get_active_backend_id() != "postgres"
        and bool(reason)
    )


def _clear_postgres_health_caches() -> None:
    try:
        backend = get_backend()
        clear = getattr(backend, "clear_runtime_caches", None)
        if callable(clear):
            clear()
            return
        for attr in (
            "_health_cache",
            "_health_cache_ts",
            "_catalog_cache",
            "_relations_cache",
            "_counts_cache",
            "_fingerprint_cache",
            "_schema_text_cache",
        ):
            if hasattr(backend, attr):
                setattr(backend, attr, None if not attr.endswith("_ts") else 0.0)
    except Exception:
        pass


def _switch_to_csv(reason: str) -> str:
    """Session-scoped fallback to CSV/DuckDB; returns the human-readable reason."""
    try:
        st.session_state.data_backend = "csv_duckdb"
        st.session_state["_postgres_fallback_reason"] = reason
    except Exception:
        pass
    logger.warning("Falling back to csv_duckdb: %s", reason)
    return reason


def retry_postgres_backend() -> tuple[bool, str]:
    """
    Clear sticky CSV fallback and re-probe Postgres when secrets request it.

    Returns (ok_to_continue, status_message) same as ensure_data_backend_ready.
    """
    if get_configured_backend_id() != "postgres":
        return False, "DATA_BACKEND is not set to postgres in secrets."

    try:
        st.session_state.data_backend = "postgres"
        st.session_state.pop("_postgres_fallback_reason", None)
        st.session_state.pop("_postgres_fallback_shown", None)
    except Exception:
        pass

    _clear_postgres_health_caches()
    return ensure_data_backend_ready()


def ensure_data_backend_ready() -> tuple[bool, str]:
    """
    Validate Postgres when configured; soft-fallback to CSV/DuckDB when needed.

    Returns (ok_to_continue, status_message).
    - ok_to_continue True means the app can proceed (Postgres healthy OR
      successfully switched to csv_duckdb).
    - When Postgres is required and unreachable with fallback disabled,
      ok_to_continue is False.
    """
    config = get_data_config()
    if get_active_backend_id() != "postgres":
        return True, ""

    pg = config.get("postgres") or {}
    host = str(pg.get("host") or "localhost")
    url = str(pg.get("connection_url") or "").strip()
    allow_fallback = bool(config.get("postgres_fallback_csv", True))

    # Streamlit Cloud cannot reach the developer's laptop Postgres.
    if not url and is_streamlit_cloud() and is_loopback_host(host):
        reason = (
            "DATA_BACKEND=postgres with host=localhost cannot work on "
            "Streamlit Cloud (localhost is the cloud container, not your PC). "
            "Set [postgres] host (or connection_url) to a reachable managed "
            "Postgres, or set DATA_BACKEND=csv_duckdb in Cloud secrets."
        )
        if allow_fallback:
            return True, _switch_to_csv(reason)
        return False, reason

    backend = get_backend()
    ok, message = backend.health_check()
    if ok:
        try:
            st.session_state.pop("_postgres_fallback_reason", None)
            st.session_state.pop("_postgres_fallback_shown", None)
        except Exception:
            pass
        return True, message

    detail = (
        f"{message} "
        f"(host={host!r}; on Streamlit Cloud use a public/managed Postgres "
        f"host or connection_url, not localhost.)"
    )
    if allow_fallback:
        return True, _switch_to_csv(detail)
    return False, detail
