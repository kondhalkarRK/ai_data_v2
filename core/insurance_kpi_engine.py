"""Governed PostgreSQL KPI summary and dashboard for the insurance pilot."""
from __future__ import annotations

from datetime import date
from decimal import Decimal

import pandas as pd
import plotly.express as px
import streamlit as st

from core.data_backend.factory import get_backend
from core.kpi_engine import _fmt_currency, _fmt_number

_ALL = "All"


def _sql_date(value: date) -> str:
    return f"DATE '{value.isoformat()}'"


def _sql_text(value: str) -> str:
    return "'" + str(value).replace("'", "''") + "'"


def fy_april_march_bounds(as_of: date, *, previous: bool = False) -> tuple[date, date]:
    """India-style fiscal year: 1 Apr → 31 Mar."""
    if as_of.month >= 4:
        start = date(as_of.year, 4, 1)
    else:
        start = date(as_of.year - 1, 4, 1)
    if previous:
        start = date(start.year - 1, 4, 1)
    end = date(start.year + 1, 3, 31)
    return start, min(end, as_of)


def rolling_bounds(as_of: date, months: int = 12) -> tuple[date, date]:
    start = (pd.Timestamp(as_of) - pd.DateOffset(months=months)).date()
    return start, as_of


def calendar_ytd_bounds(as_of: date) -> tuple[date, date]:
    """Calendar year-to-date: 1 Jan of as_of year → as_of."""
    return date(as_of.year, 1, 1), as_of


def calendar_year_bounds(year: int, as_of: date) -> tuple[date, date]:
    """Calendar year Jan–Dec, capped at as_of for the current year."""
    start = date(int(year), 1, 1)
    end = date(int(year), 12, 31)
    if year == as_of.year:
        end = min(end, as_of)
    elif year > as_of.year:
        end = as_of
    return start, end


def _ytd_label(as_of: date) -> str:
    yy = as_of.year % 100
    return f"Current year YTD (Jan'{yy:02d}–{as_of.strftime('%b')}'{yy:02d})"


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


def _distinct_values(backend, sql: str) -> list[str]:
    frame, error = backend.execute_sql(sql)
    if error or frame is None or frame.empty:
        return []
    return [str(v) for v in frame.iloc[:, 0].dropna().tolist()]


def _claims_where(
    start: date | None, end: date | None, lob: str, region: str
) -> str:
    clauses: list[str] = []
    if start is not None:
        clauses.append(f"c.reported_date >= {_sql_date(start)}")
    if end is not None:
        clauses.append(f"c.reported_date <= {_sql_date(end)}")
    if lob and lob != _ALL:
        clauses.append(f"pr.line_of_business = {_sql_text(lob)}")
    if region and region != _ALL:
        clauses.append(f"r.region_name = {_sql_text(region)}")
    return " AND ".join(clauses) if clauses else "TRUE"


def _premium_where(
    start: date | None, end: date | None, lob: str, region: str
) -> str:
    clauses: list[str] = []
    if start is not None:
        clauses.append(
            f"pm.accounting_month >= date_trunc('month', {_sql_date(start)})::date"
        )
    if end is not None:
        clauses.append(
            f"pm.accounting_month <= date_trunc('month', {_sql_date(end)})::date"
        )
    if lob and lob != _ALL:
        clauses.append(f"pr.line_of_business = {_sql_text(lob)}")
    if region and region != _ALL:
        clauses.append(f"r.region_name = {_sql_text(region)}")
    return " AND ".join(clauses) if clauses else "TRUE"


def _kpi_sql(start: date | None, end: date | None, lob: str, region: str) -> str:
    cw = _claims_where(start, end, lob, region)
    pw = _premium_where(start, end, lob, region)
    through = _sql_date(end) if end is not None else "CURRENT_DATE"
    return f"""
SELECT
    {through} AS data_through,
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
FROM (
    SELECT
        COUNT(DISTINCT c.claim_id) AS claim_count,
        SUM(c.paid_amount) AS claims_paid,
        SUM(c.incurred_amount) AS claims_incurred,
        AVG(c.approved_flag::int) AS approval_rate,
        AVG(c.settlement_date - c.reported_date)
            FILTER (WHERE c.settlement_date IS NOT NULL) AS avg_settlement_days
    FROM insurance.fact_claims c
    JOIN insurance.dim_product pr ON pr.product_id = c.product_id
    LEFT JOIN insurance.dim_region r ON r.region_id = c.region_id
    WHERE {cw}
) c
CROSS JOIN (
    SELECT
        SUM(pm.written_premium) AS written_premium,
        SUM(pm.earned_premium) AS earned_premium,
        COUNT(*) FILTER (WHERE pm.due_for_renewal_flag) AS due_for_renewal,
        COUNT(*) FILTER (WHERE pm.renewed_flag) AS renewed
    FROM insurance.fact_policy_monthly pm
    JOIN insurance.dim_product pr ON pr.product_id = pm.product_id
    LEFT JOIN insurance.dim_region r ON r.region_id = pm.region_id
    WHERE {pw}
) p
"""


def _monthly_sql(
    start: date | None, end: date | None, lob: str, region: str
) -> str:
    cw = _claims_where(start, end, lob, region)
    pw = _premium_where(start, end, lob, region)
    return f"""
WITH premium AS (
    SELECT pm.accounting_month,
           SUM(pm.earned_premium) AS earned_premium
    FROM insurance.fact_policy_monthly pm
    JOIN insurance.dim_product pr ON pr.product_id = pm.product_id
    LEFT JOIN insurance.dim_region r ON r.region_id = pm.region_id
    WHERE {pw}
    GROUP BY 1
),
claims AS (
    SELECT date_trunc('month', c.reported_date)::date AS accounting_month,
           SUM(c.incurred_amount) AS claims_incurred,
           COUNT(*) AS claim_count
    FROM insurance.fact_claims c
    JOIN insurance.dim_product pr ON pr.product_id = c.product_id
    LEFT JOIN insurance.dim_region r ON r.region_id = c.region_id
    WHERE {cw}
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
LIMIT 60
"""


def _lob_sql(start: date | None, end: date | None, lob: str, region: str) -> str:
    cw = _claims_where(start, end, lob, region)
    return f"""
SELECT pr.line_of_business,
       SUM(c.incurred_amount) AS claims_incurred,
       COUNT(*) AS claim_count
FROM insurance.fact_claims c
JOIN insurance.dim_product pr ON pr.product_id = c.product_id
LEFT JOIN insurance.dim_region r ON r.region_id = c.region_id
WHERE {cw}
GROUP BY 1
ORDER BY 2 DESC
LIMIT 20
"""


def _region_sql(start: date | None, end: date | None, lob: str, region: str) -> str:
    cw = _claims_where(start, end, lob, region)
    return f"""
SELECT COALESCE(r.region_name, 'Unknown') AS region_name,
       SUM(c.incurred_amount) AS claims_incurred,
       COUNT(*) AS claim_count
FROM insurance.fact_claims c
JOIN insurance.dim_product pr ON pr.product_id = c.product_id
LEFT JOIN insurance.dim_region r ON r.region_id = c.region_id
WHERE {cw}
GROUP BY 1
ORDER BY 2 DESC
LIMIT 20
"""


def _status_sql(start: date | None, end: date | None, lob: str, region: str) -> str:
    cw = _claims_where(start, end, lob, region)
    return f"""
SELECT c.claim_status, COUNT(*) AS claim_count
FROM insurance.fact_claims c
JOIN insurance.dim_product pr ON pr.product_id = c.product_id
LEFT JOIN insurance.dim_region r ON r.region_id = c.region_id
WHERE {cw}
GROUP BY 1
ORDER BY 2 DESC
LIMIT 20
"""


def render_insurance_kpi_tab() -> None:
    backend = get_backend()
    bounds_df, bounds_err = backend.execute_sql(
        """
        SELECT GREATEST(
            COALESCE((SELECT MAX(reported_date) FROM insurance.fact_claims), DATE '1900-01-01'),
            COALESCE((SELECT MAX(accounting_month) FROM insurance.fact_policy_monthly), DATE '1900-01-01')
        ) AS max_date
        """
    )
    if bounds_err or bounds_df is None or bounds_df.empty:
        st.warning(
            "Insurance KPI tables are not ready yet. Complete the PostgreSQL DDL "
            f"and data load first. Details: {bounds_err or 'No KPI result'}"
        )
        return

    as_of = pd.to_datetime(bounds_df.iloc[0]["max_date"]).date()
    ytd_default = _ytd_label(as_of)
    year_vals = _distinct_values(
        backend,
        """
        SELECT DISTINCT EXTRACT(YEAR FROM reported_date)::int AS y
        FROM insurance.fact_claims
        WHERE reported_date IS NOT NULL
        ORDER BY 1 DESC
        LIMIT 12
        """,
    )
    calendar_years = sorted(
        {int(float(y)) for y in year_vals if str(y).replace(".", "", 1).isdigit()},
        reverse=True,
    )
    window_options = [
        ytd_default,
        "Rolling 12 months",
        "Full history (all records)",
    ]
    for year in calendar_years:
        if year == as_of.year:
            continue
        window_options.append(f"Calendar year {year} (Jan–Dec)")
    window_options.extend(
        [
            "FY Apr–Mar (current)",
            "FY Apr–Mar (previous)",
        ]
    )

    lobs = [_ALL] + _distinct_values(
        backend,
        "SELECT DISTINCT line_of_business FROM insurance.dim_product ORDER BY 1 LIMIT 20",
    )
    regions = [_ALL] + _distinct_values(
        backend,
        "SELECT DISTINCT region_name FROM insurance.dim_region ORDER BY 1 LIMIT 20",
    )

    if "ins_kpi_window" not in st.session_state:
        st.session_state.ins_kpi_window = ytd_default
    elif st.session_state.ins_kpi_window not in window_options:
        # Refresh YTD label when as_of month changes (same key pattern)
        if str(st.session_state.ins_kpi_window).startswith("Current year YTD"):
            st.session_state.ins_kpi_window = ytd_default
        else:
            st.session_state.ins_kpi_window = ytd_default

    main_col, filter_col = st.columns([4, 1])
    with filter_col:
        st.markdown(
            '<div class="kpi-filter-panel-title">Filters</div>',
            unsafe_allow_html=True,
        )
        window = st.selectbox(
            "Time window",
            window_options,
            key="ins_kpi_window",
        )
        lob = st.selectbox("Line of business", lobs, key="ins_kpi_lob")
        region = st.selectbox("Region", regions, key="ins_kpi_region")
        if st.button("Clear filters", key="ins_kpi_clear", use_container_width=True):
            st.session_state.ins_kpi_window = ytd_default
            st.session_state.ins_kpi_lob = _ALL
            st.session_state.ins_kpi_region = _ALL
            st.rerun()

    start: date | None
    end: date | None
    if window == "Full history (all records)":
        start, end = None, None
        window_label = "Full history (all records)"
    elif window == "Rolling 12 months":
        start, end = rolling_bounds(as_of, 12)
        window_label = "Rolling 12 months"
    elif window == "FY Apr–Mar (current)":
        start, end = fy_april_march_bounds(as_of, previous=False)
        window_label = f"FY {start.year}–{end.year} (Apr–Mar)"
    elif window == "FY Apr–Mar (previous)":
        start, end = fy_april_march_bounds(as_of, previous=True)
        window_label = f"FY {start.year}–{start.year + 1} (Apr–Mar)"
    elif window.startswith("Calendar year "):
        year = int(window.split()[2])
        start, end = calendar_year_bounds(year, as_of)
        window_label = f"Calendar year {year} (Jan–Dec)"
    else:
        start, end = calendar_ytd_bounds(as_of)
        window_label = ytd_default

    result, error = backend.execute_sql(_kpi_sql(start, end, lob, region))
    if error or result is None or result.empty:
        st.warning(
            "Insurance KPI query failed. "
            f"Details: {error or 'No KPI result'}"
        )
        return

    row = result.iloc[0]
    with main_col:
        st.markdown("### Insurance Executive KPI Summary")
        if start is None and end is None:
            range_txt = "all loaded dates"
        else:
            range_txt = f"{start.isoformat()} to {end.isoformat()}"
        st.caption(
            f"{window_label} · {range_txt} · "
            f"LOB={lob} · Region={region} · computed in PostgreSQL"
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

        monthly, monthly_err = backend.execute_sql(_monthly_sql(start, end, lob, region))
        lob_df, lob_err = backend.execute_sql(_lob_sql(start, end, lob, region))
        region_df, region_err = backend.execute_sql(_region_sql(start, end, lob, region))
        status, status_err = backend.execute_sql(_status_sql(start, end, lob, region))

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
            if lob_df is not None and not lob_df.empty and not lob_err:
                fig = px.pie(
                    lob_df,
                    names="line_of_business",
                    values="claims_incurred",
                    hole=0.35,
                    title="Incurred by line of business",
                )
                st.plotly_chart(_chart_layout(fig), use_container_width=True)
                st.dataframe(lob_df, use_container_width=True, hide_index=True)
            else:
                st.info("LOB mix is not available yet.")

        with bottom_right:
            if region_df is not None and not region_df.empty and not region_err:
                fig = px.bar(
                    region_df,
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
