"""
ui/tab_preview.py
Data Preview tab — DQ intelligence + controlled table preview.
"""
import pandas as pd
import streamlit as st

from core.data_quality_engine import render_data_quality


def _filter_columns_by_type(df: pd.DataFrame, kind: str) -> pd.DataFrame:
    if kind == "Numeric":
        cols = df.select_dtypes(include="number").columns.tolist()
    elif kind == "Text":
        cols = df.select_dtypes(include=["object", "string", "category"]).columns.tolist()
    elif kind == "Date":
        cols = df.select_dtypes(include=["datetime", "datetimetz"]).columns.tolist()
        if not cols:
            cols = [
                c for c in df.columns
                if any(x in str(c).lower() for x in ("date", "time", "year", "month"))
            ]
    else:
        return df
    return df[cols] if cols else df


def _preview_controls(prefix: str) -> tuple[int, str, str]:
    c1, c2, c3 = st.columns([2, 2, 3])
    with c1:
        n_rows = st.radio(
            "Rows",
            options=[25, 50, 100],
            index=1,
            horizontal=True,
            key=f"{prefix}_nrows",
            label_visibility="collapsed",
        )
        st.caption("Showing first N rows")
    with c2:
        col_kind = st.radio(
            "Types",
            options=["All", "Numeric", "Text", "Date"],
            index=0,
            horizontal=True,
            key=f"{prefix}_colkind",
            label_visibility="collapsed",
        )
        st.caption("Column type filter")
    with c3:
        search = st.text_input(
            "🔍 Search columns",
            "",
            key=f"{prefix}_search",
            placeholder="Filter by column name…",
        )
    return int(n_rows), col_kind, search


def render(working_df, tables, dfs):
    working_preview_df = working_df

    with st.expander("🔬 Data Quality Intelligence ▼", expanded=True):
        render_data_quality(working_preview_df, "working_dataset")

    if working_preview_df is not None:
        multi = len(dfs) > 1
        label = "🔗 Joined / Working Dataset" if multi else "📋 Working Dataset"
        st.markdown(f"#### {label}")
        st.markdown(
            f"""<div class="stat-row">
          <div class="stat-card"><div class="sv">{working_preview_df.shape[0]:,}</div><div class="sl">Rows</div></div>
          <div class="stat-card"><div class="sv">{working_preview_df.shape[1]}</div><div class="sl">Columns</div></div>
          <div class="stat-card"><div class="sv">{working_preview_df.select_dtypes(include='number').shape[1]}</div><div class="sl">Numeric Cols</div></div>
        </div>""",
            unsafe_allow_html=True,
        )

        n_rows, col_kind, search = _preview_controls("working")
        view = _filter_columns_by_type(working_preview_df, col_kind)
        if search:
            matched = [c for c in view.columns if search.lower() in c.lower()]
            view = view[matched] if matched else view
        st.dataframe(view.head(n_rows), use_container_width=True)

    st.markdown("---")
    st.markdown("#### 🗂️ Individual Table View")
    sel = st.selectbox("Select Table", tables, key="preview_table_sel")
    pdf = dfs[sel]
    n_rows, col_kind, search = _preview_controls("table")
    view = _filter_columns_by_type(pdf, col_kind)
    if search:
        matched = [c for c in view.columns if search.lower() in c.lower()]
        view = view[matched] if matched else view

    st.markdown(
        f"""<div class="stat-row">
      <div class="stat-card"><div class="sv">{pdf.shape[0]:,}</div><div class="sl">Rows</div></div>
      <div class="stat-card"><div class="sv">{pdf.shape[1]}</div><div class="sl">Columns</div></div>
      <div class="stat-card"><div class="sv">{pdf.select_dtypes(include='number').shape[1]}</div><div class="sl">Numeric Cols</div></div>
    </div>""",
        unsafe_allow_html=True,
    )
    st.dataframe(view.head(n_rows), use_container_width=True)

    with st.expander("📌 Column Details"):
        info = []
        for col in dfs[sel].columns:
            s = dfs[sel][col]
            info.append({
                "Column": col,
                "Type": str(s.dtype),
                "Non-Null": int(s.notna().sum()),
                "Null": int(s.isna().sum()),
                "Unique": int(s.nunique()),
                "Sample": str(s.dropna().iloc[0]) if s.notna().any() else "N/A",
            })
        st.dataframe(pd.DataFrame(info), use_container_width=True)
