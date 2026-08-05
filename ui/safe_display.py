"""
ui/safe_display.py
Display helpers — PII-safe dataframes.
"""
from __future__ import annotations

import streamlit as st

from core.pii_mask import mask_pii_for_display, pii_columns_found


def safe_dataframe(df, **kwargs) -> None:
    """st.dataframe wrapper that masks PII before render."""
    if df is None:
        st.dataframe(df, **kwargs)
        return
    masked = mask_pii_for_display(df)
    pii_cols = pii_columns_found(df)
    if pii_cols:
        st.caption(f"PII masked in display: {', '.join(pii_cols[:5])}{'…' if len(pii_cols) > 5 else ''}")
    st.dataframe(masked, **kwargs)
