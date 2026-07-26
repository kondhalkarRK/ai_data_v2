"""
ui/tab_preview.py
"""
import pandas as pd
# from ai_data.app import get_working_df
import streamlit as st

from core.data_quality_engine import render_data_quality

# ─────────────────────────────────────────────────────────────────
# TAB 2 — DATA PREVIEW
# ─────────────────────────────────────────────────────────────────
def render(working_df, tables, dfs):
    # st.markdown('<div class="hero-card glass-card"><div class="hero-left"><div class="hero-title">Data Observatory</div><div class="hero-sub">Explore & monitor table health with semantic profiling</div></div></div>', unsafe_allow_html=True)
    # working_preview_df = get_working_df()
    working_preview_df = working_df
    with st.expander("🔬 Data Quality Intelligence ▼", expanded=True):
            render_data_quality(working_preview_df, "working_dataset")
    st.dataframe(working_preview_df.head(200), use_container_width=True)

    if working_preview_df is not None:
        multi = len(dfs) > 1
        label = "🔗 Joined / Working Dataset" if multi else "📋 Working Dataset"
        st.markdown(f"#### {label}")
        st.markdown(f"""<div class="stat-row">
          <div class="stat-card"><div class="sv">{working_preview_df.shape[0]:,}</div><div class="sl">Rows</div></div>
          <div class="stat-card"><div class="sv">{working_preview_df.shape[1]}</div><div class="sl">Columns</div></div>
          <div class="stat-card"><div class="sv">{working_preview_df.select_dtypes(include='number').shape[1]}</div><div class="sl">Numeric Cols</div></div>
        </div>""", unsafe_allow_html=True)


    st.markdown("---")
    st.markdown("#### 🗂️ Individual Table View")
    sel    = st.selectbox("Select Table", tables, key="preview_table_sel")
    search = st.text_input("🔍 Search columns", "")
    pdf    = dfs[sel]
    if search:
        matched = [c for c in pdf.columns if search.lower() in c.lower()]
        pdf = pdf[matched] if matched else pdf
    st.markdown(f"""<div class="stat-row">
      <div class="stat-card"><div class="sv">{pdf.shape[0]:,}</div><div class="sl">Rows</div></div>
      <div class="stat-card"><div class="sv">{pdf.shape[1]}</div><div class="sl">Columns</div></div>
      <div class="stat-card"><div class="sv">{pdf.select_dtypes(include='number').shape[1]}</div><div class="sl">Numeric Cols</div></div>
    </div>""", unsafe_allow_html=True)
    st.dataframe(pdf.head(200), use_container_width=True)
    with st.expander("📌 Column Details"):
        info = []
        for col in dfs[sel].columns:
            s = dfs[sel][col]
            info.append({"Column": col, "Type": str(s.dtype), "Non-Null": int(s.notna().sum()), "Null": int(s.isna().sum()), "Unique": int(s.nunique()), "Sample": str(s.dropna().iloc[0]) if s.notna().any() else "N/A"})
        st.dataframe(pd.DataFrame(info), use_container_width=True)
