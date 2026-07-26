"""
ui/tab_kpi.py
"""
from core.kpi_engine import render_kpi_tab
import streamlit as st


# TAB 3 — Executive KPI Cockpit
def render(working_df, tables, dfs):
    # st.markdown('<div class="hero-card glass-card"><div class="hero-left"><div class="hero-title">Executive KPI Dashboard</div><div class="hero-sub">Monitor business performance in real time</div></div></div>', unsafe_allow_html=True)
    render_kpi_tab(working_df)
