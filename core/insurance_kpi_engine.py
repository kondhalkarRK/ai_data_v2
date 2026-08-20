"""Governed PostgreSQL KPI summary for the insurance pilot."""
from __future__ import annotations

from decimal import Decimal

import pandas as pd
import streamlit as st

from core.data_backend.factory import get_backend


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


def _number(value, *, money: bool = False, percent: bool = False) -> str:
    if value is None or pd.isna(value):
        return "N/A"
    numeric = float(value if not isinstance(value, Decimal) else float(value))
    if percent:
        return f"{numeric * 100:.1f}%"
    if money:
        abs_value = abs(numeric)
        if abs_value >= 1_000_000_000:
            return f"₹{numeric / 1_000_000_000:.2f}B"
        if abs_value >= 1_000_000:
            return f"₹{numeric / 1_000_000:.2f}M"
        return f"₹{numeric:,.0f}"
    return f"{numeric:,.1f}"


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
        "computed in PostgreSQL"
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
