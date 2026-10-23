"""Human-readable period labels for chat SQL (YYYY-MM for month/quarter/half)."""

from __future__ import annotations

_TIME_GRAINS = frozenset({"month", "quarter", "half"})


def period_label_sql(column: str, grain: str) -> str:
    """Return a SQL text expression suitable for SELECT and GROUP BY.

    ``column`` must be a qualified date column (e.g. ``f.sales_date``).
    """
    if grain == "month":
        return f"to_char(date_trunc('month', {column})::date, 'YYYY-MM')"
    if grain == "quarter":
        return f"to_char(date_trunc('quarter', {column})::date, 'YYYY-MM')"
    if grain == "half":
        bucket = (
            f"(date_trunc('year', {column}) + "
            f"((EXTRACT(MONTH FROM {column})::int - 1) / 6) * INTERVAL '6 months')::date"
        )
        return f"to_char({bucket}, 'YYYY-MM')"
    raise ValueError(f"Unsupported period grain for label SQL: {grain}")


def is_time_grain(grain: str | None) -> bool:
    return grain in _TIME_GRAINS or grain == "year"
