"""
ui/tab_preview.py
Data Preview tab — DQ intelligence + controlled table preview.
"""
import pandas as pd
import streamlit as st

from core.data_quality_engine import render_data_quality
from core.data_backend.factory import get_backend, postgres_mode_enabled
from ui.safe_display import safe_dataframe


def _render_postgres_preview():
    backend = get_backend()
    healthy, message = backend.health_check()
    if not healthy:
        st.error(message)
        return

    tables = backend.list_tables()
    counts = backend.table_row_counts()
    total_loaded = int(sum(counts.values())) if counts else 0
    claim_rows = int(counts.get("fact_claims") or 0)
    st.caption(f"PostgreSQL · {message}")
    st.markdown(
        f"""<div class="stat-row">
      <div class="stat-card"><div class="sv">{claim_rows:,}</div><div class="sl">Claims loaded</div></div>
      <div class="stat-card"><div class="sv">{total_loaded:,}</div><div class="sl">All table rows</div></div>
      <div class="stat-card"><div class="sv">{len(tables)}</div><div class="sl">Tables / views</div></div>
    </div>""",
        unsafe_allow_html=True,
    )

    with st.expander("🔬 Data Quality Intelligence ▼", expanded=True):
        from core.postgres_dq_engine import render_postgres_data_quality

        render_postgres_data_quality()

    if not tables:
        st.info("No readable tables or views were found in the configured schema.")
        return

    st.markdown("---")
    st.markdown("#### 🗂️ Individual Table View")
    selected = st.selectbox(
        "Select PostgreSQL table or view",
        tables,
        key="postgres_preview_table",
    )
    preview_limit = 100
    preview = backend.get_preview(selected, limit=preview_limit)
    full_n = int(counts.get(selected) or len(preview))
    st.markdown(f"#### 📋 {selected}")
    st.markdown(
        f"""<div class="stat-row">
      <div class="stat-card"><div class="sv">{full_n:,}</div><div class="sl">Loaded rows</div></div>
      <div class="stat-card"><div class="sv">{preview.shape[1]}</div><div class="sl">Columns</div></div>
      <div class="stat-card"><div class="sv">{preview.select_dtypes(include='number').shape[1]}</div><div class="sl">Numeric Cols</div></div>
    </div>""",
        unsafe_allow_html=True,
    )
    safe_dataframe(preview, use_container_width=True)
    st.caption(
        f"Showing first {min(preview_limit, len(preview)):,} of {full_n:,} rows "
        "(server-side LIMIT). ASK-DB does not load the full PostgreSQL table into Streamlit."
    )

    with st.expander("📌 Column Details"):
        info = [
            {
                "Column": column,
                "Type": str(preview[column].dtype),
                "Non-Null in preview": int(preview[column].notna().sum()),
                "Null in preview": int(preview[column].isna().sum()),
                "Unique in preview": int(preview[column].nunique()),
            }
            for column in preview.columns
        ]
        st.dataframe(pd.DataFrame(info), use_container_width=True)


def render(working_df, tables, dfs):
    if postgres_mode_enabled():
        _render_postgres_preview()
        return

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
        safe_dataframe(working_preview_df.head(100), use_container_width=True)
        if len(working_preview_df) > 100:
            st.caption(f"Showing first 100 of {len(working_preview_df):,} rows")

    st.markdown("---")
    st.markdown("#### 🗂️ Individual Table View")
    sel = st.selectbox("Select Table", tables, key="preview_table_sel")
    pdf = dfs[sel]
    st.markdown(
        f"""<div class="stat-row">
      <div class="stat-card"><div class="sv">{pdf.shape[0]:,}</div><div class="sl">Rows</div></div>
      <div class="stat-card"><div class="sv">{pdf.shape[1]}</div><div class="sl">Columns</div></div>
      <div class="stat-card"><div class="sv">{pdf.select_dtypes(include='number').shape[1]}</div><div class="sl">Numeric Cols</div></div>
    </div>""",
        unsafe_allow_html=True,
    )
    safe_dataframe(pdf.head(100), use_container_width=True)
    if len(pdf) > 100:
        st.caption(f"Showing first 100 of {len(pdf):,} rows")

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
