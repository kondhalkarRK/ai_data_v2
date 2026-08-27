"""Governed PostgreSQL KPI summary and dashboard for the insurance pilot."""
from __future__ import annotations

from datetime import date
from decimal import Decimal

import pandas as pd
import plotly.express as px
import streamlit as st

from core.data_backend.factory import get_backend
from core.kpi_engine import _fmt_currency, _fmt_number
from ui.kpi_flip_cards import render_flip_kpi_grid

_ALL = "All"


@st.cache_data(ttl=120, show_spinner=False)
def _cached_sql_frame(sql: str, fingerprint: str) -> tuple[list | None, list | None, str | None]:
    """Cache KPI SQL results by fingerprint + SQL text (120s TTL)."""
    backend = get_backend()
    df, err = backend.execute_sql(sql)
    if err or df is None:
        return None, None, err
    return df.to_dict(orient="list"), list(df.columns), None


def _exec_sql_cached(sql: str) -> tuple[pd.DataFrame | None, str | None]:
    try:
        fingerprint = get_backend().get_dataset_fingerprint()
    except Exception:
        fingerprint = "unknown"
    rows, cols, err = _cached_sql_frame(sql, fingerprint)
    if err or rows is None or cols is None:
        return None, err
    return pd.DataFrame(rows, columns=cols), None


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
    theme = str(st.session_state.get("ui_theme") or "dark").lower()
    if theme == "light":
        font = "#1b2430"
        grid = "rgba(27,36,48,0.12)"
        zero = "rgba(27,36,48,0.35)"
        legend = "#334155"
    elif theme == "ai":
        font = "#e2e8f0"
        grid = "rgba(148,163,184,0.18)"
        zero = "rgba(226,232,240,0.35)"
        legend = "#cbd5e1"
    else:
        font = "#e2e8f0"
        grid = "rgba(148,163,184,0.16)"
        zero = "rgba(226,232,240,0.28)"
        legend = "#cbd5e1"

    fig.update_layout(
        margin=dict(l=8, r=8, t=44, b=8),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        height=320,
        font=dict(color=font, size=12),
        title_font=dict(color=font, size=14),
        legend=dict(font=dict(color=legend)),
        xaxis=dict(
            color=font,
            gridcolor=grid,
            zerolinecolor=zero,
            linecolor=grid,
            tickfont=dict(color=font),
            title_font=dict(color=font),
        ),
        yaxis=dict(
            color=font,
            gridcolor=grid,
            zerolinecolor=zero,
            linecolor=grid,
            tickfont=dict(color=font),
            title_font=dict(color=font),
        ),
        colorway=["#2563eb", "#0f9d6e", "#c2410c", "#7c3aed", "#0891b2"]
        if theme == "light"
        else ["#38bdf8", "#34d399", "#fbbf24", "#a78bfa", "#f472b6"],
    )
    fig.update_traces(
        selector=dict(type="scatter"),
        line=dict(width=2.5),
        marker=dict(size=7),
    )
    return fig


def _distinct_values(backend, sql: str) -> list[str]:
    frame, error = _exec_sql_cached(sql)
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
    p.premium_rows,
    c.claims_incurred,
    c.claims_paid,
    c.claim_count,
    c.claim_rows,
    c.claims_incurred / NULLIF(p.earned_premium, 0) AS loss_ratio,
    c.claims_incurred / NULLIF(c.claim_count, 0) AS average_severity,
    c.approval_rate,
    c.avg_settlement_days,
    p.renewed::numeric / NULLIF(p.due_for_renewal, 0) AS renewal_rate,
    p.due_for_renewal
FROM (
    SELECT
        COUNT(DISTINCT c.claim_id) AS claim_count,
        COUNT(*) AS claim_rows,
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
        COUNT(*) AS premium_rows,
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


def _filter_summary(window_label: str, lob: str, region: str) -> str:
    parts = [window_label]
    if lob and lob != _ALL:
        parts.append(f"LOB={lob}")
    else:
        parts.append("LOB=All")
    if region and region != _ALL:
        parts.append(f"Region={region}")
    else:
        parts.append("Region=All")
    return " · ".join(parts)


def _safe_int(value) -> int | None:
    try:
        if value is None or (isinstance(value, float) and pd.isna(value)):
            return None
        return int(float(value))
    except Exception:
        return None


def _build_insurance_flip_cards(row: pd.Series, filters: str) -> list[dict]:
    premium_rows = _safe_int(row.get("premium_rows"))
    claim_rows = _safe_int(row.get("claim_rows"))
    claim_count = _safe_int(row.get("claim_count"))
    due_renewal = _safe_int(row.get("due_for_renewal"))

    return [
        {
            "label": "Gross Written Premium",
            "value": _number(row["written_premium"], money=True),
            "accent": "premium",
            "source_columns": "insurance.fact_policy_monthly.written_premium",
            "aggregation": "SUM",
            "records_count": premium_rows,
            "records_label": "Policy-month rows",
            "filters": filters,
            "business_logic": "GWP from policy-month grain — never from claim rows.",
            "featured": True,
        },
        {
            "label": "Earned Premium",
            "value": _number(row["earned_premium"], money=True),
            "accent": "premium",
            "source_columns": "insurance.fact_policy_monthly.earned_premium",
            "aggregation": "SUM",
            "records_count": premium_rows,
            "records_label": "Policy-month rows",
            "filters": filters,
            "business_logic": "Earned premium recognised over the coverage period.",
        },
        {
            "label": "Claims Incurred",
            "value": _number(row["claims_incurred"], money=True),
            "accent": "claims",
            "source_columns": "insurance.fact_claims.incurred_amount",
            "aggregation": "SUM",
            "records_count": claim_rows,
            "records_label": "Claim rows",
            "filters": filters,
            "business_logic": "Total incurred amount on reported claims in window.",
        },
        {
            "label": "Claims Paid",
            "value": _number(row["claims_paid"], money=True),
            "accent": "claims",
            "source_columns": "insurance.fact_claims.paid_amount",
            "aggregation": "SUM",
            "records_count": claim_rows,
            "records_label": "Claim rows",
            "filters": filters,
            "business_logic": "Cash paid on claims (may lag incurred).",
        },
        {
            "label": "Claim Count",
            "value": _number(row["claim_count"]),
            "accent": "units",
            "source_columns": "insurance.fact_claims.claim_id",
            "aggregation": "COUNT DISTINCT",
            "records_count": claim_count,
            "records_label": "Distinct claims",
            "filters": filters,
            "business_logic": "Unique claim IDs after LOB / region / time filters.",
        },
        {
            "label": "Loss Ratio",
            "value": _number(row["loss_ratio"], percent=True),
            "accent": "ratio",
            "source_columns": [
                "fact_claims.incurred_amount",
                "fact_policy_monthly.earned_premium",
            ],
            "formula": "SUM(incurred_amount) ÷ SUM(earned_premium)",
            "records_count": claim_rows,
            "records_label": "Claim rows in num.",
            "filters": filters,
            "business_logic": (
                "Incurred claims over earned premium. Premium stays on "
                "policy-month grain so claim joins cannot inflate it."
            ),
        },
        {
            "label": "Average Severity",
            "value": _number(row["average_severity"], money=True),
            "accent": "ratio",
            "source_columns": [
                "fact_claims.incurred_amount",
                "fact_claims.claim_id",
            ],
            "formula": "SUM(incurred_amount) ÷ COUNT(DISTINCT claim_id)",
            "records_count": claim_count,
            "records_label": "Distinct claims",
            "filters": filters,
            "business_logic": "Average incurred cost per distinct claim.",
        },
        {
            "label": "Approval Rate",
            "value": _number(row["approval_rate"], percent=True),
            "accent": "ratio",
            "source_columns": "insurance.fact_claims.approved_flag",
            "aggregation": "AVG (0/1 flag)",
            "records_count": claim_rows,
            "records_label": "Claim rows",
            "filters": filters,
            "business_logic": "Share of claim rows with approved_flag = true.",
        },
        {
            "label": "Avg Settlement Days",
            "value": _number(row["avg_settlement_days"]),
            "accent": "date",
            "source_columns": [
                "fact_claims.settlement_date",
                "fact_claims.reported_date",
            ],
            "formula": "AVG(settlement_date − reported_date) WHERE settled",
            "records_count": claim_rows,
            "records_label": "Claim rows",
            "filters": filters,
            "business_logic": "Only settled claims (non-null settlement_date).",
        },
        {
            "label": "Renewal Rate",
            "value": _number(row["renewal_rate"], percent=True),
            "accent": "share",
            "source_columns": [
                "fact_policy_monthly.renewed_flag",
                "fact_policy_monthly.due_for_renewal_flag",
            ],
            "formula": "COUNT(renewed) ÷ COUNT(due_for_renewal)",
            "records_count": due_renewal,
            "records_label": "Due for renewal",
            "filters": filters,
            "business_logic": "Renewals among policies marked due in the window.",
        },
    ]


def render_insurance_kpi_tab() -> None:
    backend = get_backend()
    bounds_df, bounds_err = _exec_sql_cached(
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

    result, error = _exec_sql_cached(_kpi_sql(start, end, lob, region))
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
        st.markdown(
            '<p class="kpi-flip-caption">'
            "Hover a card to peek at the calculation — click to pin the explanation."
            "</p>",
            unsafe_allow_html=True,
        )

        filters = _filter_summary(window_label, lob, region)
        flip_cards = _build_insurance_flip_cards(row, filters)
        st.markdown(
            render_flip_kpi_grid(flip_cards, columns=5),
            unsafe_allow_html=True,
        )

        st.caption(
            "Loss ratio uses incurred claims ÷ earned premium. Premium is sourced "
            "from policy-month grain, never duplicated across claim rows."
        )

        monthly, monthly_err = _exec_sql_cached(_monthly_sql(start, end, lob, region))
        lob_df, lob_err = _exec_sql_cached(_lob_sql(start, end, lob, region))
        region_df, region_err = _exec_sql_cached(_region_sql(start, end, lob, region))
        status, status_err = _exec_sql_cached(_status_sql(start, end, lob, region))

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
