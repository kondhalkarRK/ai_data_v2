"""Backend selection for Streamlit and non-UI callers."""
from __future__ import annotations

import pandas as pd
import streamlit as st

from config.settings import get_data_config
from core.data_backend.base import DataBackend
from core.data_backend.csv_duckdb import CsvDuckDbBackend
from core.data_backend.postgres import PostgresBackend


@st.cache_resource(show_spinner=False)
def _postgres_backend(config_items: tuple[tuple[str, object], ...]) -> PostgresBackend:
    return PostgresBackend(dict(config_items))


def get_active_backend_id() -> str:
    configured = get_data_config()["backend"]
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
