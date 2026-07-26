"""
features/materialized_views.py
"""
from __future__ import annotations
import pandas as pd
import duckdb
import streamlit as st


class ViewStore:
    """
    In-memory store for materialized views and named semantic views.
    """

    def __init__(self):
        # existing materialized views
        self._views: dict[str, pd.DataFrame] = {}
        # CHANGED: named semantic views store — holds SQL + resulting df
        self._named_views: dict[str, dict] = {}

    # ── Existing materialized view methods (unchanged) ───────────

    def save_view(self, name: str, df: pd.DataFrame) -> None:
        self._views[name] = df

    def get_view(self, name: str) -> pd.DataFrame | None:
        return self._views.get(name)

    def list_views(self) -> list[str]:
        return list(self._views.keys())

    def count_active_views(self) -> int:
        return len(self._views)

    def clear_all_views(self) -> int:
        count = len(self._views)
        self._views.clear()
        return count

    def delete_view(self, name: str) -> bool:
        if name in self._views:
            del self._views[name]
            return True
        return False

    # ── CHANGED: Named semantic view methods (new) ───────────────

    def save_named_view(
        self,
        name:    str,
        sql:     str,
        df:      pd.DataFrame,
        source:  str = "semantic_join",
    ) -> None:
        """
        Save an edited semantic join SQL as a named view.
        Stores both the SQL definition and the resulting DataFrame.

        Args:
            name:   View name (e.g. 'semantic_join_view')
            sql:    The SQL used to produce this view
            df:     Resulting DataFrame from executing the SQL
            source: Origin tag — 'semantic_join' or 'manual'
        """
        self._named_views[name] = {
            "sql":    sql,
            "df":     df,
            "source": source,
        }
        # CHANGED: also store in session_state so all tabs can access it
        st.session_state[f"named_view_{name}"] = {
            "sql": sql,
            "df":  df,
        }

    def get_named_view(self, name: str) -> dict | None:
        """
        Returns dict with keys: sql, df, source
        or None if not found.
        """
        # CHANGED: check session_state first (survives reruns)
        ss_key = f"named_view_{name}"
        if ss_key in st.session_state:
            return st.session_state[ss_key]
        return self._named_views.get(name)

    def list_named_views(self) -> list[str]:
        return list(self._named_views.keys())

    def count_named_views(self) -> int:
        return len(self._named_views)

    def delete_named_view(self, name: str) -> bool:
        ss_key = f"named_view_{name}"
        if ss_key in st.session_state:
            del st.session_state[ss_key]
        if name in self._named_views:
            del self._named_views[name]
            return True
        return False

    def clear_all_named_views(self) -> int:
        count = len(self._named_views)
        # CHANGED: clean session_state keys too
        keys_to_del = [
            k for k in st.session_state
            if k.startswith("named_view_")
        ]
        for k in keys_to_del:
            del st.session_state[k]
        self._named_views.clear()
        return count


# ── Singleton ────────────────────────────────────────────────────
view_store = ViewStore()