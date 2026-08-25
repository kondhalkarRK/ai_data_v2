"""
ui/tab_preview.py
Data Preview tab — DQ intelligence + controlled table preview.
"""
import pandas as pd
import streamlit as st

from core.data_quality_engine import render_data_quality
from core.data_backend.factory import get_backend, postgres_mode_enabled
from ui.safe_display import safe_dataframe

_JOINED_SQL = """
    SELECT
        c.*,
        p.policy_number,
        p.policy_status,
        p.coverage_tier,
        p.sum_insured,
        pr.product_code,
        pr.product_name,
        pr.line_of_business,
        pr.product_family,
        pr.coverage_type,
        r.region_code,
        r.region_name,
        r.state_name,
        a.agent_code,
        a.agent_name,
        a.channel_name,
        a.branch_name
    FROM insurance.fact_claims c
    LEFT JOIN insurance.dim_policy p ON p.policy_id = c.policy_id
    LEFT JOIN insurance.dim_product pr ON pr.product_id = c.product_id
    LEFT JOIN insurance.dim_region r ON r.region_id = c.region_id
    LEFT JOIN insurance.dim_agent a ON a.agent_id = p.agent_id
    ORDER BY c.reported_date DESC NULLS LAST, c.claim_id DESC
    LIMIT 100
"""


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
      <div class="stat-card"><div class="sv">{total_loaded:,}</div><div class="sl">Physical table rows</div></div>
      <div class="stat-card"><div class="sv">{len(tables)}</div><div class="sl">Tables / views</div></div>
    </div>""",
        unsafe_allow_html=True,
    )

    with st.expander("Data quality", expanded=True):
        from core.postgres_dq_engine import render_postgres_data_quality

        try:
            render_postgres_data_quality()
        except Exception as exc:
            st.error("Data quality could not be computed.")
            with st.expander("Technical details"):
                st.code(str(exc))

    with st.expander(
        "Joined claims view (all columns · LIMIT 100)",
        expanded=False,
    ):
        st.caption(
            "Claims LEFT JOIN policy, product, region, agent. "
            "Hidden until expanded — warehouse stays in PostgreSQL."
        )
        with st.spinner("ASK-DB is preparing the joined preview…"):
            joined, joined_err = backend.execute_sql(_JOINED_SQL)
        if joined_err or joined is None:
            st.warning(f"Joined preview unavailable: {joined_err or 'No rows'}")
        else:
            st.markdown(
                f"""<div class="stat-row">
              <div class="stat-card"><div class="sv">{len(joined):,}</div><div class="sl">Rows shown</div></div>
              <div class="stat-card"><div class="sv">{joined.shape[1]}</div><div class="sl">Columns (joined)</div></div>
              <div class="stat-card"><div class="sv">{claim_rows:,}</div><div class="sl">Claim grain in DB</div></div>
            </div>""",
                unsafe_allow_html=True,
            )
            safe_dataframe(joined, use_container_width=True)

    if not tables:
        st.info("No readable tables or views were found in the configured schema.")
        return

    st.markdown("---")
    st.markdown("#### Individual table view")
    selected = st.selectbox(
        "Select PostgreSQL table or view",
        tables,
        key="postgres_preview_table",
    )
    preview_limit = 100
    preview = backend.get_preview(selected, limit=preview_limit)
    full_n = int(counts.get(selected) or 0)
    if selected not in counts:
        full_n = int(backend.count_relation(selected))
    st.markdown(f"#### {selected}")
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

    with st.expander("Column details"):
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

    with st.expander("Data Quality Intelligence", expanded=True):
        render_data_quality(working_preview_df, "working_dataset")

    if working_preview_df is not None:
        multi = len(dfs) > 1
        label = "Joined / Working Dataset" if multi else "Working Dataset"
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
    st.markdown("#### Individual Table View")
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

    with st.expander("Column Details"):
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
