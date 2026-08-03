"""
ui/tab_preview.py
Data Preview tab — DQ intelligence + controlled table preview.
"""
import pandas as pd
import streamlit as st

from core.data_quality_engine import render_data_quality


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
        st.dataframe(working_preview_df.head(100), use_container_width=True)
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
    st.dataframe(pdf.head(100), use_container_width=True)
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
