"""PostgreSQL data quality for large claim stores.

Inventory (row/column counts) uses catalog + COUNT(*) per table.
Quality metrics use a rolling 12-month window on indexed reported_date
so 2M-row history is not fully scanned for IQR / null profiling.
"""
from __future__ import annotations

from datetime import date
from typing import Any

import pandas as pd
import streamlit as st

from core.data_backend.factory import get_backend

QUALITY_COLUMNS = (
    "claim_id",
    "claim_number",
    "policy_id",
    "product_id",
    "region_id",
    "reported_date",
    "claim_status",
    "reported_amount",
    "paid_amount",
    "reserve_amount",
    "incurred_amount",
)
AMOUNT_COLUMNS = ("reported_amount", "paid_amount", "reserve_amount", "incurred_amount")


def _sql_date(value: date) -> str:
    return f"DATE '{value.isoformat()}'"


def _inventory(backend) -> dict[str, Any]:
    schema = str(getattr(backend, "_schema", "insurance") or "insurance")
    counts = backend.table_row_counts(include_views=False)
    col_sql = f"""
        SELECT table_name, COUNT(*) AS column_count
        FROM information_schema.columns
        WHERE table_schema = '{schema}'
        GROUP BY table_name
        ORDER BY table_name
        LIMIT 40
    """
    col_df, _ = backend.execute_sql(col_sql)
    col_map = {}
    if col_df is not None and not col_df.empty:
        col_map = {
            str(row["table_name"]): int(row["column_count"])
            for _, row in col_df.iterrows()
        }
    tables = []
    for name, rows in sorted(counts.items()):
        tables.append(
            {
                "Table": name,
                "Rows": int(rows),
                "Columns": int(col_map.get(name) or 0),
            }
        )
    return {
        "tables": tables,
        "claim_rows": int(counts.get("fact_claims") or 0),
        "physical_rows": int(sum(counts.values()) if counts else 0),
        "table_count": len(tables),
        "claim_columns": int(col_map.get("fact_claims") or 0),
    }


def _qualify(schema: str, table: str) -> str:
    return f'"{schema}"."{table}"'


def _quality_window(backend) -> dict[str, Any]:
    schema = str(getattr(backend, "_schema", "insurance") or "insurance")
    claims = _qualify(schema, "fact_claims")
    bounds_sql = f"""
        SELECT COALESCE(MAX(reported_date), CURRENT_DATE) AS max_date
        FROM {claims}
    """
    bounds, error = backend.execute_sql(bounds_sql)
    if error or bounds is None or bounds.empty:
        return {"error": error or "No claims date bound", "rows": 0}
    as_of = pd.to_datetime(bounds.iloc[0]["max_date"]).date()
    start = (pd.Timestamp(as_of) - pd.DateOffset(months=12)).date()

    null_parts = [
        f'COUNT(*) FILTER (WHERE c.{col} IS NULL) AS {col}_nulls'
        for col in QUALITY_COLUMNS
    ]
    amount_parts = []
    for col in AMOUNT_COLUMNS:
        amount_parts.append(
            f'PERCENTILE_CONT(0.25) WITHIN GROUP (ORDER BY c.{col}) AS {col}_q1, '
            f'PERCENTILE_CONT(0.75) WITHIN GROUP (ORDER BY c.{col}) AS {col}_q3'
        )
    quality_sql = f"""
        SELECT
            COUNT(*) AS rows_12m,
            COUNT(DISTINCT c.claim_id) AS distinct_claims,
            COUNT(DISTINCT c.claim_number) AS distinct_numbers,
            {", ".join(null_parts)},
            {", ".join(amount_parts)}
        FROM {claims} c
        WHERE c.reported_date >= {_sql_date(start)}
          AND c.reported_date <= {_sql_date(as_of)}
    """
    quality, qerr = backend.execute_sql(quality_sql)
    if qerr or quality is None or quality.empty:
        return {"error": qerr or "Quality query failed", "rows": 0, "start": start, "end": as_of}

    row = quality.iloc[0]
    rows_12m = int(row["rows_12m"] or 0)
    distinct_claims = int(row["distinct_claims"] or 0)
    distinct_numbers = int(row["distinct_numbers"] or 0)
    duplicate_ids = max(rows_12m - distinct_claims, 0)
    duplicate_numbers = max(rows_12m - distinct_numbers, 0)

    nulls = []
    total_nulls = 0
    for col in QUALITY_COLUMNS:
        key = f"{col}_nulls"
        count = int(row[key] or 0) if key in row.index else 0
        if count:
            total_nulls += count
            nulls.append(
                {
                    "Check": f"Nulls in {col}",
                    "Value": f"{count:,} ({round(count / max(rows_12m, 1) * 100, 2)}%)",
                    "Status": "Watch" if count / max(rows_12m, 1) < 0.05 else "Action",
                }
            )

    outliers = []
    for col in AMOUNT_COLUMNS:
        q1, q3 = row.get(f"{col}_q1"), row.get(f"{col}_q3")
        if q1 is None or q3 is None or pd.isna(q1) or pd.isna(q3):
            continue
        iqr = float(q3) - float(q1)
        if iqr <= 0:
            continue
        lower, upper = float(q1) - 3 * iqr, float(q3) + 3 * iqr
        out_sql = f"""
            SELECT COUNT(*) AS outlier_count
            FROM {claims} c
            WHERE c.reported_date >= {_sql_date(start)}
              AND c.reported_date <= {_sql_date(as_of)}
              AND c.{col} IS NOT NULL
              AND (c.{col} < {lower} OR c.{col} > {upper})
        """
        out_df, _ = backend.execute_sql(out_sql)
        n = int(out_df.iloc[0]["outlier_count"] or 0) if out_df is not None and not out_df.empty else 0
        if n:
            outliers.append(
                {
                    "Check": f"Extreme {col}",
                    "Value": f"{n:,} rows beyond 3×IQR",
                    "Status": "Watch",
                }
            )

    gap_sql = f"""
        WITH months AS (
            SELECT date_trunc('month', reported_date)::date AS m
            FROM {claims}
            WHERE reported_date >= {_sql_date(start)}
              AND reported_date <= {_sql_date(as_of)}
            GROUP BY 1
        ),
        span AS (
            SELECT generate_series(
                date_trunc('month', {_sql_date(start)})::date,
                date_trunc('month', {_sql_date(as_of)})::date,
                interval '1 month'
            )::date AS m
        )
        SELECT COUNT(*) AS missing_months
        FROM span s
        LEFT JOIN months mo ON mo.m = s.m
        WHERE mo.m IS NULL
    """
    gap_df, _ = backend.execute_sql(gap_sql)
    missing_months = (
        int(gap_df.iloc[0]["missing_months"] or 0)
        if gap_df is not None and not gap_df.empty
        else 0
    )

    assessed_cells = max(rows_12m * len(QUALITY_COLUMNS), 1)
    null_pct = round(total_nulls / assessed_cells * 100, 2)
    completeness = round(100.0 - null_pct, 1)
    score = 100.0
    score -= min(null_pct * 1.5, 20)
    score -= min(duplicate_numbers * 2, 15)
    score -= min(len(outliers) * 3, 15)
    score -= min(missing_months * 2, 10)
    score = max(round(score, 1), 0.0)

    findings = [
        {
            "Check": "Completeness",
            "Value": f"{completeness}% on 12-month grain",
            "Status": "Good" if completeness >= 98 else "Watch",
        },
        {
            "Check": "Claim id uniqueness",
            "Value": f"{duplicate_ids:,} extra rows",
            "Status": "Good" if duplicate_ids == 0 else "Action",
        },
        {
            "Check": "Claim number uniqueness",
            "Value": f"{duplicate_numbers:,} collisions",
            "Status": "Good" if duplicate_numbers == 0 else "Watch",
        },
        {
            "Check": "Calendar continuity",
            "Value": f"{missing_months} missing month(s)",
            "Status": "Good" if missing_months == 0 else "Watch",
        },
    ]
    findings.extend(nulls[:4])
    findings.extend(outliers[:3])

    return {
        "error": None,
        "start": start.isoformat(),
        "end": as_of.isoformat(),
        "rows": rows_12m,
        "completeness": completeness,
        "null_pct": null_pct,
        "duplicates": duplicate_numbers,
        "outlier_checks": len(outliers),
        "missing_months": missing_months,
        "score": score,
        "findings": findings,
    }


def compute_postgres_data_quality() -> dict[str, Any]:
    backend = get_backend()
    inventory = _inventory(backend)
    quality = _quality_window(backend)
    return {"inventory": inventory, "quality": quality}


def render_postgres_data_quality() -> None:
    backend = get_backend()
    fingerprint = backend.get_dataset_fingerprint()
    cached = st.session_state.get("_pg_dq_cache")
    if not cached or cached.get("fp") != fingerprint:
        with st.spinner("Profiling inventory and rolling 12-month quality…"):
            st.session_state["_pg_dq_cache"] = {
                "fp": fingerprint,
                "report": compute_postgres_data_quality(),
            }
        cached = st.session_state["_pg_dq_cache"]

    report = cached["report"]
    inv = report["inventory"]
    q = report["quality"]
    if q.get("error"):
        st.warning(f"Quality window could not run: {q['error']}")

    score = float(q.get("score") or 0)
    if score >= 90:
        score_color, score_label = "#10b981", "Excellent"
    elif score >= 75:
        score_color, score_label = "#f59e0b", "Good"
    else:
        score_color, score_label = "#ef4444", "Needs attention"

    st.markdown("### Data health")
    st.caption(
        "Full-store inventory is exact table counts. Quality tests run only on the "
        "rolling 12-month claims window (index-friendly). History beyond 12 months "
        "is not scanned for nulls or outliers."
    )

    left, right = st.columns([1.1, 2.2])
    with left:
        st.markdown(
            f"<div style='text-align:center;padding:12px 0;'>"
            f"<div style='font-size:56px;font-weight:800;color:{score_color};line-height:1;'>"
            f"{score:.0f}</div>"
            f"<div style='color:#94a3b8;letter-spacing:0.08em;font-size:12px;margin-top:8px;'>"
            f"HEALTH SCORE</div>"
            f"<div style='color:{score_color};font-weight:700;margin-top:4px;'>{score_label}</div>"
            f"</div>",
            unsafe_allow_html=True,
        )
    with right:
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Claims in store", f"{inv['claim_rows']:,}")
        c2.metric("Claim columns", f"{inv['claim_columns']}")
        c3.metric("Physical rows", f"{inv['physical_rows']:,}")
        c4.metric("Tables", f"{inv['table_count']}")
        d1, d2, d3, d4 = st.columns(4)
        d1.metric("12m claims tested", f"{int(q.get('rows') or 0):,}")
        d2.metric("Completeness", f"{q.get('completeness', 0)}%")
        d3.metric("Duplicate numbers", f"{int(q.get('duplicates') or 0):,}")
        d4.metric("Missing months", f"{int(q.get('missing_months') or 0)}")

    st.caption(
        f"Quality window {q.get('start') or '—'} → {q.get('end') or '—'} · "
        "incremental loads should keep this window current without restating history."
    )

    if inv.get("tables"):
        st.markdown("#### Dataset inventory")
        inv_df = pd.DataFrame(inv["tables"])
        inv_df["Rows"] = inv_df["Rows"].map(lambda n: f"{int(n):,}")
        st.dataframe(inv_df, use_container_width=True, hide_index=True)

    findings = q.get("findings") or []
    if findings:
        st.markdown("#### Quality findings (12 months)")
        find_df = pd.DataFrame(findings)
        st.dataframe(find_df, use_container_width=True, hide_index=True)
        st.caption("Good = within operating tolerance. Watch = explain in the demo. Action = fix before scale-up.")
