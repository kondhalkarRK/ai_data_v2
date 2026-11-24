"""
ui/tab_kpi.py
"""
from core.kpi_engine import render_kpi_tab
from core.data_backend.factory import postgres_mode_enabled


def render(working_df, tables, dfs):
    if postgres_mode_enabled():
        from core.insurance_kpi_engine import render_insurance_kpi_tab

        render_insurance_kpi_tab()
        return
    render_kpi_tab(working_df)
