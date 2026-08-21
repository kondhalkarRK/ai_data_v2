"""Server-side data quality for PostgreSQL insurance tables.

Runs COUNT / percentile SQL in the database. Streamlit only receives
small aggregate reports — never the full fact table.
"""
from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
import streamlit as st

from core.data_backend.factory import get_backend
from core.data_quality_engine import render_data_quality_report

WORKING_TABLE_PREF = ("v_claims_enriched", "fact_claims")
METRIC_COLUMNS = (
    "reported_amount",
    "approved_amount",
    "paid_amount",
    "reserve_amount",
    "incurred_amount",
)
DATE_COLUMN = "reported_date"


def _qualify(schema: str, table: str) -> str:
    return f'"{schema}"."{table}"'


def _working_table(tables: list[str]) -> str | None:
    for name in WORKING_TABLE_PREF:
        if name in tables:
            return name
    return tables[0] if tables else None


def _columns(backend, schema: str, table: str) -> list[tuple[str, str]]:
    sql = f"""
        SELECT column_name, data_type
        FROM information_schema.columns
        WHERE table_schema = '{schema}'
          AND table_name = '{table}'
        ORDER BY ordinal_position
        LIMIT 80
    """
    result, error = backend.execute_sql(sql)
    if error or result is None or result.empty:
        return []
    return [
        (str(row["column_name"]), str(row["data_type"]))
        for _, row in result.iterrows()
    ]


def _is_numeric_type(data_type: str) -> bool:
    return any(
        token in data_type.lower()
        for token in ("int", "numeric", "decimal", "real", "double", "float", "money")
    )


def _is_text_type(data_type: str) -> bool:
    return any(token in data_type.lower() for token in ("char", "text", "name"))


def _is_date_type(data_type: str) -> bool:
    return any(token in data_type.lower() for token in ("date", "time"))


def compute_postgres_data_quality(table: str | None = None) -> tuple[dict[str, Any], pd.DataFrame]:
    backend = get_backend()
    schema = str(getattr(backend, "_schema", "insurance") or "insurance")
    tables = backend.list_tables()
    target = table if table in tables else _working_table(tables)
    empty_preview = pd.DataFrame()
    if not target:
        return {}, empty_preview

    qualified = _qualify(schema, target)
    columns = _columns(backend, schema, target)
    if not columns:
        preview = backend.get_preview(target, limit=100)
        return {}, preview

    null_parts = [
        f'COUNT(*) FILTER (WHERE "{name}" IS NULL) AS "{name}__nulls"'
        for name, _ in columns
    ]
    metric_parts = []
    for name in METRIC_COLUMNS:
        if any(col == name for col, _ in columns):
            metric_parts.append(
                f'MIN("{name}") AS "{name}__min", '
                f'MAX("{name}") AS "{name}__max", '
                f'AVG("{name}") AS "{name}__avg", '
                f'STDDEV_SAMP("{name}") AS "{name}__std", '
                f'PERCENTILE_CONT(0.25) WITHIN GROUP (ORDER BY "{name}") AS "{name}__q1", '
                f'PERCENTILE_CONT(0.75) WITHIN GROUP (ORDER BY "{name}") AS "{name}__q3"'
            )

    summary_sql = f"""
        SELECT
            COUNT(*) AS total_rows,
            {", ".join(null_parts)}
            {"," if metric_parts else ""}
            {", ".join(metric_parts)}
        FROM {qualified}
    """
    summary, error = backend.execute_sql(summary_sql)
    if error or summary is None or summary.empty:
        preview = backend.get_preview(target, limit=100)
        return {
            "health_score": 0,
            "total_rows": 0,
            "total_cols": len(columns),
            "null_summary": {},
            "total_null_cells": 0,
            "total_null_pct": 0,
            "duplicate_count": 0,
            "duplicate_pct": 0,
            "outliers": {},
            "spikes": {},
            "date_col": DATE_COLUMN if any(c == DATE_COLUMN for c, _ in columns) else None,
            "type_issues": [],
            "cardinality_flags": [],
            "date_gaps": [],
            "error": error,
        }, preview

    row = summary.iloc[0]
    total_rows = int(row["total_rows"] or 0)
    total_cols = len(columns)
    total_cells = max(total_rows * total_cols, 1)
    null_summary = {}
    total_nulls = 0
    for name, _ in columns:
        count = int(row.get(f"{name}__nulls") or 0)
        if count > 0:
            pct = round(count / max(total_rows, 1) * 100, 2)
            null_summary[name] = {"count": count, "pct": pct}
            total_nulls += count

    dup_sql = f"""
        SELECT COUNT(*) - COUNT(DISTINCT claim_id) AS duplicate_count
        FROM {qualified}
    """ if any(c == "claim_id" for c, _ in columns) else None
    duplicate_count = 0
    if dup_sql:
        dup_df, _ = backend.execute_sql(dup_sql)
        if dup_df is not None and not dup_df.empty:
            duplicate_count = max(int(dup_df.iloc[0]["duplicate_count"] or 0), 0)

    outliers: dict[str, Any] = {}
    numeric_profiles = []
    for name in METRIC_COLUMNS:
        if f"{name}__q1" not in row.index:
            continue
        q1 = row.get(f"{name}__q1")
        q3 = row.get(f"{name}__q3")
        if q1 is None or q3 is None or pd.isna(q1) or pd.isna(q3):
            continue
        iqr = float(q3) - float(q1)
        if iqr <= 0:
            continue
        lower = float(q1) - 3.0 * iqr
        upper = float(q3) + 3.0 * iqr
        out_sql = f"""
            SELECT COUNT(*) AS outlier_count,
                   MIN("{name}") AS min_outlier,
                   MAX("{name}") AS max_outlier
            FROM {qualified}
            WHERE "{name}" IS NOT NULL
              AND ("{name}" < {lower} OR "{name}" > {upper})
        """
        out_df, _ = backend.execute_sql(out_sql)
        out_count = 0
        min_out = max_out = None
        if out_df is not None and not out_df.empty:
            out_count = int(out_df.iloc[0]["outlier_count"] or 0)
            min_out = out_df.iloc[0]["min_outlier"]
            max_out = out_df.iloc[0]["max_outlier"]
        if out_count > 0:
            outliers[name] = {
                "count": out_count,
                "pct": round(out_count / max(total_rows, 1) * 100, 2),
                "lower_fence": round(lower, 2),
                "upper_fence": round(upper, 2),
                "min_outlier": round(float(min_out), 2) if min_out is not None else None,
                "max_outlier": round(float(max_out), 2) if max_out is not None else None,
                "sample": [],
            }
        numeric_profiles.append({
            "Column": name,
            "Min": round(float(row.get(f"{name}__min") or 0), 2),
            "Max": round(float(row.get(f"{name}__max") or 0), 2),
            "Mean": round(float(row.get(f"{name}__avg") or 0), 2),
            "Std Dev": round(float(row.get(f"{name}__std") or 0), 2),
            "Shape": "🟢 profiled in PostgreSQL",
        })

    date_col = DATE_COLUMN if any(c == DATE_COLUMN for c, _ in columns) else None
    date_gaps: list[str] = []
    spikes: dict[str, list] = {}
    if date_col:
        gap_sql = f"""
            WITH months AS (
                SELECT date_trunc('month', "{date_col}")::date AS m
                FROM {qualified}
                WHERE "{date_col}" IS NOT NULL
                GROUP BY 1
            ),
            span AS (
                SELECT generate_series(
                    (SELECT MIN(m) FROM months),
                    (SELECT MAX(m) FROM months),
                    interval '1 month'
                )::date AS m
            )
            SELECT s.m
            FROM span s
            LEFT JOIN months mo ON mo.m = s.m
            WHERE mo.m IS NULL
            ORDER BY 1
            LIMIT 12
        """
        gap_df, _ = backend.execute_sql(gap_sql)
        if gap_df is not None and not gap_df.empty:
            date_gaps = [str(v)[:7] for v in gap_df.iloc[:, 0].tolist()]

        spike_sql = f"""
            SELECT date_trunc('month', "{date_col}")::date AS period,
                   SUM(COALESCE(incurred_amount, paid_amount + reserve_amount, 0)) AS value
            FROM {qualified}
            WHERE "{date_col}" IS NOT NULL
            GROUP BY 1
            ORDER BY 1
            LIMIT 48
        """
        spike_df, _ = backend.execute_sql(spike_sql)
        if spike_df is not None and len(spike_df) >= 4:
            monthly = spike_df.set_index("period")["value"].astype(float)
            rolling_mean = monthly.rolling(3, min_periods=2).mean().shift(1)
            rolling_std = monthly.rolling(3, min_periods=2).std().shift(1)
            z_scores = ((monthly - rolling_mean) / rolling_std.replace(0, np.nan)).abs()
            flagged = z_scores[z_scores > 2.5].dropna()
            if not flagged.empty:
                spikes["incurred_amount"] = [
                    {
                        "period": str(p)[:10],
                        "value": round(float(monthly[p]), 2),
                        "z_score": round(float(z_scores[p]), 2),
                        "direction": "▲ Spike UP" if monthly[p] > rolling_mean[p] else "▼ Spike DOWN",
                    }
                    for p in flagged.index[:8]
                ]

    cardinality_flags = []
    card_cols = [name for name, dtype in columns if _is_text_type(dtype)][:8]
    for name in card_cols:
        card_sql = f"""
            SELECT COUNT(DISTINCT "{name}") AS uniq,
                   COUNT("{name}") AS filled
            FROM {qualified}
        """
        card_df, _ = backend.execute_sql(card_sql)
        if card_df is None or card_df.empty:
            continue
        uniq = int(card_df.iloc[0]["uniq"] or 0)
        filled = int(card_df.iloc[0]["filled"] or 0)
        if filled == 0:
            continue
        ratio = uniq / filled
        if uniq == 1:
            cardinality_flags.append({
                "column": name,
                "issue": "Only 1 unique value — constant column",
                "unique": uniq,
                "ratio": round(ratio * 100, 1),
            })
        elif ratio > 0.95 and uniq > 100:
            cardinality_flags.append({
                "column": name,
                "issue": "Very high cardinality — possible ID / free-text",
                "unique": uniq,
                "ratio": round(ratio * 100, 1),
            })

    column_health = []
    for name, data_type in columns[:15]:
        nulls = int(row.get(f"{name}__nulls") or 0)
        completeness = round(100.0 * (total_rows - nulls) / max(total_rows, 1), 1)
        if completeness >= 100:
            status = "✅ Complete"
        elif completeness >= 95:
            status = "🟡 Minor gaps"
        elif completeness >= 80:
            status = "🟠 Gaps"
        else:
            status = "🔴 Sparse"
        column_health.append({
            "Column": name,
            "Type": data_type,
            "Completeness %": completeness,
            "Unique": "—",
            "Status": status,
        })

    score = 100.0
    total_null_pct = round(total_nulls / total_cells * 100, 2)
    duplicate_pct = round(duplicate_count / max(total_rows, 1) * 100, 2)
    score -= min(total_null_pct * 1.5, 25)
    score -= min(duplicate_pct * 2.0, 20)
    score -= min(len(outliers) * 3, 15)
    score -= min(len(cardinality_flags) * 2, 10)
    score -= min(len(date_gaps) * 1, 10)

    n_num = sum(1 for _, t in columns if _is_numeric_type(t))
    n_txt = sum(1 for _, t in columns if _is_text_type(t))
    n_date = sum(1 for _, t in columns if _is_date_type(t))
    n_bool = sum(1 for _, t in columns if "bool" in t.lower())

    report = {
        "health_score": max(round(score, 1), 0.0),
        "total_rows": total_rows,
        "total_cols": total_cols,
        "null_summary": null_summary,
        "total_null_cells": total_nulls,
        "total_null_pct": total_null_pct,
        "duplicate_count": duplicate_count,
        "duplicate_pct": duplicate_pct,
        "outliers": outliers,
        "spikes": spikes,
        "date_col": date_col,
        "type_issues": [],
        "cardinality_flags": cardinality_flags,
        "date_gaps": date_gaps,
        "column_health": column_health,
        "numeric_profiles": numeric_profiles,
        "n_num": n_num,
        "n_txt": n_txt,
        "n_date": n_date,
        "n_bool": n_bool,
        "working_table": target,
        "computed_in": "postgresql",
    }
    preview = backend.get_preview(target, limit=100)
    return report, preview


@st.cache_data(show_spinner=False, ttl=300)
def cached_postgres_data_quality(fingerprint: str) -> tuple[dict, pd.DataFrame]:
    return compute_postgres_data_quality()


def render_postgres_data_quality() -> None:
    backend = get_backend()
    fingerprint = backend.get_dataset_fingerprint()
    with st.spinner("Running PostgreSQL data quality checks…"):
        report, preview = cached_postgres_data_quality(fingerprint)

    if not report:
        st.info("Data quality is unavailable until insurance tables are readable.")
        return

    st.caption(
        f"Working grain: `{report.get('working_table')}` · "
        f"{report.get('total_rows', 0):,} rows scanned in PostgreSQL · "
        "preview below is LIMIT 100"
    )
    render_data_quality_report(report, preview)
