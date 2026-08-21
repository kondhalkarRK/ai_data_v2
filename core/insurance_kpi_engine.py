"""Governed PostgreSQL KPI summary and dashboard for the insurance pilot."""
from __future__ import annotations

from decimal import Decimal

import pandas as pd
import plotly.express as px
import streamlit as st

from core.data_backend.factory import get_backend
from core.kpi_engine import _fmt_currency, _fmt_number

_KPI_SQL = """
WITH bounds AS (
    SELECT GREATEST(
        COALESCE((SELECT MAX(reported_date) FROM insurance.fact_claims), DATE '1900-01-01'),
        COALESCE((SELECT MAX(accounting_month) FROM insurance.fact_policy_monthly), DATE '1900-01-01')
    ) AS max_date
),
claims AS (
    SELECT
        COUNT(DISTINCT claim_id) AS claim_count,
        SUM(paid_amount) AS claims_paid,
        SUM(incurred_amount) AS claims_incurred,
        AVG(approved_flag::int) AS approval_rate,
        AVG(settlement_date - reported_date)
            FILTER (WHERE settlement_date IS NOT NULL) AS avg_settlement_days
    FROM insurance.fact_claims, bounds
    WHERE reported_date >= bounds.max_date - INTERVAL '12 months'
),
premium AS (
    SELECT
        SUM(written_premium) AS written_premium,
        SUM(earned_premium) AS earned_premium,
        COUNT(*) FILTER (WHERE due_for_renewal_flag) AS due_for_renewal,
        COUNT(*) FILTER (WHERE renewed_flag) AS renewed
    FROM insurance.fact_policy_monthly, bounds
    WHERE accounting_month >= date_trunc('month', bounds.max_date - INTERVAL '12 months')
)
SELECT
    b.max_date AS data_through,
    p.written_premium,
    p.earned_premium,
    c.claims_incurred,
    c.claims_paid,
    c.claim_count,
    c.claims_incurred / NULLIF(p.earned_premium, 0) AS loss_ratio,
    c.claims_incurred / NULLIF(c.claim_count, 0) AS average_severity,
    c.approval_rate,
    c.avg_settlement_days,
    p.renewed::numeric / NULLIF(p.due_for_renewal, 0) AS renewal_rate
FROM claims c
CROSS JOIN premium p
CROSS JOIN bounds b
"""

_MONTHLY_SQL = """
WITH premium AS (
    SELECT accounting_month,
           SUM(earned_premium) AS earned_premium
    FROM insurance.fact_policy_monthly
    GROUP BY 1
),
claims AS (
    SELECT date_trunc('month', reported_date)::date AS accounting_month,
           SUM(incurred_amount) AS claims_incurred,
           COUNT(*) AS claim_count
    FROM insurance.fact_claims
    GROUP BY 1
)
SELECT COALESCE(p.accounting_month, c.accounting_month) AS accounting_month,
       COALESCE(p.earned_premium, 0) AS earned_premium,
       COALESCE(c.claims_incurred, 0) AS claims_incurred,
       COALESCE(c.claim_count, 0) AS claim_count,
       COALESCE(c.claims_incurred, 0) / NULLIF(COALESCE(p.earned_premium, 0), 0) AS loss_ratio
FROM premium p
FULL OUTER JOIN claims c
  ON p.accounting_month = c.accounting_month
ORDER BY 1
LIMIT 36
"""

_LOB_SQL = """
SELECT pr.line_of_business,
       SUM(c.incurred_amount) AS claims_incurred,
       COUNT(*) AS claim_count
FROM insurance.fact_claims c
JOIN insurance.dim_product pr ON pr.product_id = c.product_id
GROUP BY 1
ORDER BY 2 DESC
LIMIT 20
"""

_REGION_SQL = """
SELECT COALESCE(r.region_name, 'Unknown') AS region_name,
       SUM(c.incurred_amount) AS claims_incurred,
       COUNT(*) AS claim_count
FROM insurance.fact_claims c
LEFT JOIN insurance.dim_region r ON r.region_id = c.region_id
GROUP BY 1
ORDER BY 2 DESC
LIMIT 20
"""

_STATUS_SQL = """
SELECT claim_status, COUNT(*) AS claim_count
FROM insurance.fact_claims
GROUP BY 1
ORDER BY 2 DESC
LIMIT 20
"""


def _number(value, *, money: bool = False, percent: bool = False) -> str:
    if value is None or pd.isna(value):
        return "N/A"
    numeric = float(value if not isinstance(value, Decimal) else float(value))
    if percent:
        return f"{numeric * 100:.1f}%"
    if money:
        return _fmt_currency(numeric)
    return _fmt_number(numeric)


def _chart_layout(fig):
    fig.update_layout(
        margin=dict(l=0, r=0, t=40, b=0),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        height=320,
    )
    return fig


def render_insurance_kpi_tab() -> None:
    backend = get_backend()
    result, error = backend.execute_sql(_KPI_SQL)
    if error or result is None or result.empty:
        st.warning(
            "Insurance KPI tables are not ready yet. Complete the PostgreSQL DDL "
            f"and data load first. Details: {error or 'No KPI result'}"
        )
        return

    row = result.iloc[0]
    st.markdown("### Insurance Executive KPI Summary")
    st.caption(
        f"Rolling 12 months · data through {str(row['data_through'])[:10]} · "
        "computed in PostgreSQL · chart series limited to 36 months / 20 groups"
    )

    cards = [
        ("Gross Written Premium", _number(row["written_premium"], money=True)),
        ("Earned Premium", _number(row["earned_premium"], money=True)),
        ("Claims Incurred", _number(row["claims_incurred"], money=True)),
        ("Claims Paid", _number(row["claims_paid"], money=True)),
        ("Claim Count", _number(row["claim_count"])),
        ("Loss Ratio", _number(row["loss_ratio"], percent=True)),
        ("Average Severity", _number(row["average_severity"], money=True)),
        ("Approval Rate", _number(row["approval_rate"], percent=True)),
        ("Avg Settlement Days", _number(row["avg_settlement_days"])),
        ("Renewal Rate", _number(row["renewal_rate"], percent=True)),
    ]

    for offset in range(0, len(cards), 5):
        columns = st.columns(5)
        for column, (label, value) in zip(columns, cards[offset : offset + 5]):
            column.metric(label, value)

    st.caption(
        "Loss ratio uses incurred claims ÷ earned premium. Premium is sourced "
        "from policy-month grain, never duplicated across claim rows."
    )

    monthly, monthly_err = backend.execute_sql(_MONTHLY_SQL)
    lob, lob_err = backend.execute_sql(_LOB_SQL)
    region, region_err = backend.execute_sql(_REGION_SQL)
    status, status_err = backend.execute_sql(_STATUS_SQL)

    st.markdown("---")
    st.markdown("#### Insurance KPI dashboard")

    left, right = st.columns(2)
    with left:
        if monthly is not None and not monthly.empty and not monthly_err:
            plot = monthly.copy()
            plot["accounting_month"] = pd.to_datetime(plot["accounting_month"])
            plot["loss_ratio_pct"] = pd.to_numeric(plot["loss_ratio"], errors="coerce") * 100
            fig = px.line(
                plot,
                x="accounting_month",
                y="loss_ratio_pct",
                markers=True,
                title="Monthly loss ratio (%)",
            )
            fig.update_layout(xaxis_title="Month", yaxis_title="Loss ratio (%)")
            st.plotly_chart(_chart_layout(fig), use_container_width=True)
        else:
            st.info("Monthly loss ratio is not available yet.")

    with right:
        if monthly is not None and not monthly.empty and not monthly_err:
            plot = monthly.copy()
            plot["accounting_month"] = pd.to_datetime(plot["accounting_month"])
            fig = px.bar(
                plot,
                x="accounting_month",
                y="claims_incurred",
                title="Monthly claims incurred",
            )
            fig.update_layout(xaxis_title="Month", yaxis_title="Incurred (INR)")
            st.plotly_chart(_chart_layout(fig), use_container_width=True)

    bottom_left, bottom_right = st.columns(2)
    with bottom_left:
        if lob is not None and not lob.empty and not lob_err:
            fig = px.pie(
                lob,
                names="line_of_business",
                values="claims_incurred",
                hole=0.35,
                title="Incurred by line of business",
            )
            st.plotly_chart(_chart_layout(fig), use_container_width=True)
            st.dataframe(lob, use_container_width=True, hide_index=True)
        else:
            st.info("LOB mix is not available yet.")

    with bottom_right:
        if region is not None and not region.empty and not region_err:
            fig = px.bar(
                region,
                x="region_name",
                y="claims_incurred",
                title="Incurred by region",
            )
            fig.update_layout(xaxis_title="Region", yaxis_title="Incurred (INR)")
            st.plotly_chart(_chart_layout(fig), use_container_width=True)
        if status is not None and not status.empty and not status_err:
            fig = px.bar(
                status,
                x="claim_status",
                y="claim_count",
                title="Claims by status",
            )
            fig.update_layout(xaxis_title="Status", yaxis_title="Claim count")
            st.plotly_chart(_chart_layout(fig), use_container_width=True)
