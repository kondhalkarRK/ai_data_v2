"""Date windows and KPI formatting helpers."""

from __future__ import annotations

from datetime import date
from typing import Literal

WindowId = Literal[
    "ytd",
    "rolling_12m",
    "full",
    "fy_current",
    "fy_previous",
]


def calendar_ytd_bounds(as_of: date) -> tuple[date | None, date | None]:
    return date(as_of.year, 1, 1), as_of


def rolling_bounds(as_of: date, months: int = 12) -> tuple[date | None, date | None]:
    year = as_of.year
    month = as_of.month - months
    while month <= 0:
        month += 12
        year -= 1
    return date(year, month, as_of.day if as_of.day <= 28 else 28), as_of


def fy_april_march_bounds(
    as_of: date, *, previous: bool = False
) -> tuple[date | None, date | None]:
    if as_of.month >= 4:
        start = date(as_of.year, 4, 1)
    else:
        start = date(as_of.year - 1, 4, 1)
    if previous:
        start = date(start.year - 1, 4, 1)
    end = date(start.year + 1, 3, 31)
    return start, min(end, as_of)


def resolve_window(window: WindowId, as_of: date) -> tuple[date | None, date | None, str]:
    if window == "ytd":
        start, end = calendar_ytd_bounds(as_of)
        return start, end, f"YTD {as_of.year}"
    if window == "rolling_12m":
        start, end = rolling_bounds(as_of, 12)
        return start, end, "Rolling 12 months"
    if window == "fy_current":
        start, end = fy_april_march_bounds(as_of, previous=False)
        return start, end, f"FY {start.year}-{str(start.year + 1)[-2:]}" if start else "FY"
    if window == "fy_previous":
        start, end = fy_april_march_bounds(as_of, previous=True)
        return (
            start,
            end,
            f"Prior FY {start.year}-{str(start.year + 1)[-2:]}" if start else "Prior FY",
        )
    return None, as_of, "Full history"


def format_currency(value: float | None) -> str:
    if value is None:
        return "N/A"
    abs_value = abs(value)
    sign = "-" if value < 0 else ""
    if abs_value >= 10_000_000:
        return f"{sign}₹{abs_value / 10_000_000:.2f} Cr"
    if abs_value >= 100_000:
        return f"{sign}₹{abs_value / 100_000:.2f} L"
    return f"{sign}₹{abs_value:,.0f}"


def format_number(value: float | None, *, digits: int = 0) -> str:
    if value is None:
        return "N/A"
    if digits == 0:
        return f"{value:,.0f}"
    return f"{value:,.{digits}f}"


def format_percent(ratio: float | None) -> str:
    if ratio is None:
        return "N/A"
    return f"{ratio * 100:.1f}%"
