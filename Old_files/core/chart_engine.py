"""
core/chart_engine.py
"""
import pandas as pd
import plotly.express as px
import streamlit as st

# ─────────────────────────────────────────────────────────────────
# CHART BUILDER
# ─────────────────────────────────────────────────────────────────
def auto_chart_type(result: pd.DataFrame, question: str) -> str:
    q = question.lower()
    n = len(result)
    num_cols = result.select_dtypes(include="number").columns.tolist()
    str_cols = result.select_dtypes(exclude="number").columns.tolist()
    if any(w in q for w in ["trend","monthly","yearly","over time","growth"]): return "Line"
    if any(w in q for w in ["share","proportion","percent","breakdown","distribution"]) and n<=10: return "Pie"
    if any(w in q for w in ["compare","vs","versus"]): return "Bar"
    if len(num_cols)>=2 and len(str_cols)==0: return "Scatter"
    if n>30: return "Line"
    return "Bar"


def build_chart(result: pd.DataFrame, chart_type: str, x_col: str, y_col: str):
    try:
        if not isinstance(x_col, str) or not isinstance(y_col, str):
            st.warning("⚠️ Invalid axis selection.")
            return
        all_cols = list(result.columns)
        if x_col not in all_cols:
            st.warning(f"⚠️ X-axis column '{x_col}' not found in result.")
            return
        if y_col not in all_cols:
            st.warning(f"⚠️ Y-axis column '{y_col}' not found in result.")
            return
        if x_col == y_col:
            st.warning("⚠️ X and Y axes must be different columns.")
            return
        df_plot = result[[x_col, y_col]].copy()
        df_plot[y_col] = pd.to_numeric(df_plot[y_col], errors="coerce")
        if df_plot[y_col].isna().all():
            st.warning(f"⚠️ Column '{y_col}' has no numeric values to plot.")
            return
        colors = px.colors.qualitative.Plotly
        layout = dict(
            plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
            margin=dict(l=10,r=10,t=30,b=10), font=dict(size=12)
        )
        if chart_type == "Bar":
            fig = px.bar(df_plot, x=x_col, y=y_col, text_auto=True,
                         color=x_col if df_plot[x_col].nunique() <= 20 else None,
                         color_discrete_sequence=colors)
        elif chart_type == "Line":
            fig = px.line(df_plot, x=x_col, y=y_col, markers=True)
        elif chart_type == "Pie":
            fig = px.pie(df_plot, names=x_col, values=y_col, hole=0.35,
                         color_discrete_sequence=colors)
        elif chart_type == "Scatter":
            fig = px.scatter(df_plot, x=x_col, y=y_col)
        elif chart_type == "Area":
            fig = px.area(df_plot, x=x_col, y=y_col)
        else:
            fig = px.bar(df_plot, x=x_col, y=y_col)
        fig.update_layout(**layout)
        st.plotly_chart(fig, use_container_width=True)
    except Exception as e:
        st.error(f"⚠️ Chart could not be rendered: {e}")
        st.info("Try selecting different X / Y columns or switching chart type.")
