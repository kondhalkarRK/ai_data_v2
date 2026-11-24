"""
core/schema_builder.py
"""
import pandas as pd
import streamlit as st

# ─────────────────────────────────────────────────────────────────
# SCHEMA BUILDER
# ─────────────────────────────────────────────────────────────────
@st.cache_data(show_spinner=False)
def build_rich_schema(df: pd.DataFrame, columns_subset: list[str] | None = None) -> str:
    lines = []
    cols_to_use = columns_subset if columns_subset else df.columns
    for col in cols_to_use:
        if col not in df.columns:
            continue
        s = df[col]; nn = s.notna().sum(); uniq = s.nunique()
        if pd.api.types.is_numeric_dtype(s):
            mn = round(float(s.min()),2) if nn else "N/A"
            mx = round(float(s.max()),2) if nn else "N/A"
            lines.append(f"  {col} ({s.dtype}): range=[{mn},{mx}]")
        elif pd.api.types.is_datetime64_any_dtype(s):
            mn = str(s.min())[:10] if nn else "N/A"
            mx = str(s.max())[:10] if nn else "N/A"
            lines.append(f"  {col} (date): range=[{mn},{mx}]")
        else:
            top = s.dropna().value_counts().head(5).index.tolist()
            lines.append(f"  {col} (text,{uniq} unique): top_values={top}")
    return "COLUMNS:\n" + "\n".join(lines)
