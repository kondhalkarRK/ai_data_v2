"""Pure-Python port of the legacy pandas data-quality scoring formula.

Scores match ``core/data_quality_engine.compute_data_quality`` on the same fixture
without requiring pandas at runtime.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from datetime import date, datetime
from typing import Any

DATE_CANDIDATES = (
    "date",
    "sales_date",
    "reported_date",
    "loss_date",
    "accounting_month",
    "inception_date",
    "year_month",
    "created_at",
)

_EXCLUDE_PATTERNS = (
    "id",
    "_id",
    "id_",
    "key",
    "_key",
    "code",
    "_code",
    "code_",
    "index",
    "idx",
    "_idx",
    "num",
    "_num",
    "number",
    "ref",
    "_ref",
    "seq",
    "row",
    "record",
    "pk",
    "fk",
    "capacity",
    "engine",
    "patent",
)

_METRIC_PATTERNS = (
    "sale",
    "sales",
    "revenue",
    "amount",
    "total",
    "price",
    "cost",
    "value",
    "profit",
    "margin",
    "unit",
    "units",
    "qty",
    "quantity",
    "count",
    "volume",
    "rate",
    "score",
    "age",
    "salary",
    "income",
    "expense",
    "tax",
    "discount",
    "share",
    "growth",
    "change",
    "pct",
    "percent",
    "ratio",
    "premium",
    "reserve",
    "paid",
    "exposure",
)


def _is_null(value: Any) -> bool:
    return value is None or (isinstance(value, float) and math.isnan(value))


def _is_number(value: Any) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and not (isinstance(value, float) and math.isnan(value))
    )


def _is_metric_col(col_name: str, values: Sequence[Any]) -> bool:
    col_lower = col_name.lower()
    for pattern in _EXCLUDE_PATTERNS:
        if (
            col_lower == pattern
            or col_lower.endswith(f"_{pattern}")
            or col_lower.startswith(f"{pattern}_")
            or col_lower.endswith(pattern)
        ):
            return False

    numeric = [float(v) for v in values if _is_number(v)]
    if not numeric:
        return False
    unique_ratio = len(set(numeric)) / max(len(numeric), 1)
    if unique_ratio > 0.95:
        return False
    if all(float(v).is_integer() for v in numeric):
        col_min = min(numeric)
        col_max = max(numeric)
        if col_min >= 0 and col_max == len(set(numeric)):
            return False
    for pattern in _METRIC_PATTERNS:
        if pattern in col_lower:
            return True
    return len(set(numeric)) < 1000


def _quantile(sorted_vals: list[float], q: float) -> float:
    if not sorted_vals:
        return 0.0
    if len(sorted_vals) == 1:
        return sorted_vals[0]
    pos = (len(sorted_vals) - 1) * q
    low = math.floor(pos)
    high = math.ceil(pos)
    if low == high:
        return sorted_vals[low]
    return sorted_vals[low] * (high - pos) + sorted_vals[high] * (pos - low)


def _find_date_col(columns: Sequence[str], rows: Sequence[Mapping[str, Any]]) -> str | None:
    lowered = {c.lower(): c for c in columns}
    for candidate in DATE_CANDIDATES:
        if candidate in lowered:
            return lowered[candidate]
    for col in columns:
        sample = [row.get(col) for row in rows[:50] if not _is_null(row.get(col))]
        if sample and all(isinstance(v, (date, datetime)) for v in sample):
            return col
    return None


def _month_key(value: Any) -> str | None:
    if isinstance(value, datetime):
        return f"{value.year:04d}-{value.month:02d}"
    if isinstance(value, date):
        return f"{value.year:04d}-{value.month:02d}"
    if isinstance(value, str) and len(value) >= 7:
        return value[:7]
    return None


def compute_data_quality(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Compute the legacy health score over an in-memory table sample/fixture."""
    if not rows:
        return {
            "health_score": 0.0,
            "total_rows": 0,
            "total_cols": 0,
            "total_null_cells": 0,
            "total_null_pct": 0.0,
            "duplicate_count": 0,
            "duplicate_pct": 0.0,
            "null_summary": {},
            "outliers": {},
            "spikes": {},
            "type_issues": [],
            "cardinality_flags": [],
            "date_gaps": [],
            "date_col": None,
            "computed_in": "python",
        }

    columns = list(rows[0].keys())
    total_rows = len(rows)
    total_cells = total_rows * len(columns)

    null_summary: dict[str, dict[str, float | int]] = {}
    total_null_cells = 0
    for col in columns:
        count = sum(1 for row in rows if _is_null(row.get(col)))
        if count:
            null_summary[col] = {
                "count": count,
                "pct": round(count / total_rows * 100, 2),
            }
            total_null_cells += count
    total_null_pct = round(total_null_cells / total_cells * 100, 2) if total_cells else 0.0

    seen: set[tuple[Any, ...]] = set()
    duplicate_count = 0
    for row in rows:
        key = tuple(row.get(col) for col in columns)
        if key in seen:
            duplicate_count += 1
        else:
            seen.add(key)
    duplicate_pct = round(duplicate_count / total_rows * 100, 2)

    outlier_report: dict[str, dict[str, Any]] = {}
    for col in columns:
        values = [row.get(col) for row in rows]
        if not _is_metric_col(col, values):
            continue
        numeric = sorted(float(v) for v in values if _is_number(v))
        if len(numeric) < 10:
            continue
        q1 = _quantile(numeric, 0.25)
        q3 = _quantile(numeric, 0.75)
        iqr = q3 - q1
        if iqr == 0:
            continue
        lower = q1 - 3.0 * iqr
        upper = q3 + 3.0 * iqr
        outliers = [v for v in numeric if v < lower or v > upper]
        if outliers:
            outlier_report[col] = {
                "count": len(outliers),
                "pct": round(len(outliers) / len(numeric) * 100, 2),
                "lower_fence": round(lower, 2),
                "upper_fence": round(upper, 2),
                "min_outlier": round(min(outliers), 2),
                "max_outlier": round(max(outliers), 2),
                "sample": [round(x, 2) for x in outliers[:5]],
            }

    date_col = _find_date_col(columns, rows)
    date_gaps: list[str] = []
    if date_col:
        months = sorted({key for row in rows if (key := _month_key(row.get(date_col))) is not None})
        if len(months) >= 3:
            start_y, start_m = map(int, months[0].split("-"))
            end_y, end_m = map(int, months[-1].split("-"))
            present = set(months)
            y, m = start_y, start_m
            missing: list[str] = []
            while (y, m) <= (end_y, end_m):
                key = f"{y:04d}-{m:02d}"
                if key not in present:
                    missing.append(key)
                if m == 12:
                    y, m = y + 1, 1
                else:
                    m += 1
            date_gaps = missing[:12]

    type_issues: list[dict[str, Any]] = []
    cardinality_flags: list[dict[str, Any]] = []
    for col in columns:
        sample_vals = [row.get(col) for row in rows if not _is_null(row.get(col))][:500]
        if not sample_vals:
            continue
        if all(isinstance(v, str) for v in sample_vals):
            numeric_convertible = 0
            for value in sample_vals:
                try:
                    float(value)
                    numeric_convertible += 1
                except ValueError:
                    pass
            pct_numeric = numeric_convertible / len(sample_vals)
            if pct_numeric >= 0.85:
                type_issues.append(
                    {
                        "column": col,
                        "issue": "Stored as text but looks numeric",
                        "pct_numeric": round(pct_numeric * 100, 1),
                        "sample": sample_vals[:3],
                    }
                )
            uniq = len({str(v) for v in sample_vals})
            total = len(sample_vals)
            uniq_ratio = uniq / total
            if uniq_ratio > 0.95 and uniq > 100:
                cardinality_flags.append(
                    {
                        "column": col,
                        "issue": "Very high cardinality — possible free-text or ID column",
                        "unique": uniq,
                        "ratio": round(uniq_ratio * 100, 1),
                    }
                )
            elif uniq == 1:
                cardinality_flags.append(
                    {
                        "column": col,
                        "issue": "Only 1 unique value — constant column, no analytical value",
                        "unique": 1,
                        "ratio": round(uniq_ratio * 100, 1),
                    }
                )
            elif uniq == total and total > 50:
                cardinality_flags.append(
                    {
                        "column": col,
                        "issue": "All values unique — likely an ID/key column",
                        "unique": uniq,
                        "ratio": 100.0,
                    }
                )

    score = 100.0
    score -= min(total_null_pct * 1.5, 25)
    score -= min(duplicate_pct * 2.0, 20)
    score -= min(len(outlier_report) * 3, 15)
    score -= min(len(type_issues) * 4, 16)
    score -= min(len(cardinality_flags) * 2, 10)
    score -= min(len(date_gaps) * 1, 10)

    return {
        "health_score": max(round(score, 1), 0.0),
        "total_rows": total_rows,
        "total_cols": len(columns),
        "total_null_cells": total_null_cells,
        "total_null_pct": total_null_pct,
        "duplicate_count": duplicate_count,
        "duplicate_pct": duplicate_pct,
        "null_summary": null_summary,
        "outliers": outlier_report,
        "spikes": {},
        "type_issues": type_issues,
        "cardinality_flags": cardinality_flags,
        "date_gaps": date_gaps,
        "date_col": date_col,
        "computed_in": "python",
        # Kept for UI parity with the legacy renderer.
        "n_num": sum(1 for col in columns if any(_is_number(row.get(col)) for row in rows[:20])),
        "n_txt": sum(
            1 for col in columns if any(isinstance(row.get(col), str) for row in rows[:20])
        ),
        "n_date": 1 if date_col else 0,
        "n_bool": sum(
            1 for col in columns if any(isinstance(row.get(col), bool) for row in rows[:20])
        ),
    }
