"""Calendar resolution for typed requests. Never silently time-travel to MAX(date)."""

from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone

from app.schemas.semantic import SemanticQueryPolicy
from app.services.chat.request_contract import RequestedComparison, RequestedPeriod


class RequestClarificationError(ValueError):
    pass


def add_months(value: date, count: int) -> date:
    month = value.year * 12 + value.month - 1 + count
    year, index = divmod(month, 12)
    return date(year, index + 1, min(value.day, calendar.monthrange(year, index + 1)[1]))


def business_today(policy: SemanticQueryPolicy) -> date:
    return datetime.now(timezone(timedelta(minutes=policy.utc_offset_minutes))).date()


@dataclass(frozen=True)
class DateRange:
    start: date | None
    end: date | None
    label: str
    partial: bool = False


def resolve_period(period: RequestedPeriod, today: date, policy: SemanticQueryPolicy) -> DateRange:
    if period.start and period.end_exclusive:
        return DateRange(period.start, period.end_exclusive, period.label)
    month = today.replace(day=1)
    quarter = date(today.year, ((today.month - 1) // 3) * 3 + 1, 1)
    year = date(today.year, 1, 1)
    end = today + timedelta(days=1)
    kind, count = period.relative, period.count or 1
    if kind == "available_history":
        return DateRange(None, end, "Available history through today", True)
    if kind in {"this_month", "this_quarter", "this_year", "ytd", "fytd"}:
        start = {"this_month": month, "this_quarter": quarter, "this_year": year, "ytd": year}.get(
            kind
        )
        if kind == "fytd":
            start = date(
                today.year - (today.month < policy.fiscal_year_start_month),
                policy.fiscal_year_start_month,
                1,
            )
        return DateRange(start, end, period.label, True)
    if kind == "last_month":
        return DateRange(add_months(month, -1), month, period.label)
    if kind == "last_quarter":
        return DateRange(add_months(quarter, -3), quarter, period.label)
    if kind == "last_year":
        return DateRange(date(today.year - 1, 1, 1), year, period.label)
    if kind == "last_n_days":
        return DateRange(end - timedelta(days=count), end, period.label, True)
    if kind == "last_n_months":
        return DateRange(add_months(month, -(count - 1)), end, period.label, True)
    if kind == "last_n_quarters":
        return DateRange(add_months(quarter, -3 * (count - 1)), end, period.label, True)
    if kind == "last_n_years":
        return DateRange(date(today.year - count + 1, 1, 1), end, period.label, True)
    raise RequestClarificationError("Which date range should I use?")


def comparison_ranges(
    comparison: RequestedComparison,
    period: RequestedPeriod | None,
    today: date,
    policy: SemanticQueryPolicy,
) -> tuple[DateRange, DateRange]:
    current_period = comparison.current or period
    if current_period is None:
        raise RequestClarificationError("Which current period should I compare?")
    current = resolve_period(current_period, today, policy)
    if current.start is None or current.end is None:
        raise RequestClarificationError("Which bounded periods should I compare?")
    if comparison.baseline:
        baseline = resolve_period(comparison.baseline, today, policy)
    elif comparison.baseline_reference == "same_period_last_year":
        baseline_end = add_months(current.end, -12)
        months = {"this_month": 1, "this_quarter": 3, "this_year": 12, "ytd": 12, "fytd": 12}.get(
            current_period.relative or ""
        )
        if current.partial and months:
            baseline_end = add_months(current.start, -12 + months)
        baseline = DateRange(add_months(current.start, -12), baseline_end, "Same period last year")
    elif comparison.baseline_reference == "previous_period":
        months = {
            "this_month": 1,
            "last_month": 1,
            "this_quarter": 3,
            "last_quarter": 3,
            "this_year": 12,
            "last_year": 12,
            "ytd": 12,
            "fytd": 12,
        }.get(current_period.relative or "")
        if months:
            baseline = DateRange(
                add_months(current.start, -months), current.start, "Previous period"
            )
        else:
            baseline = DateRange(
                current.start - (current.end - current.start),
                current.start,
                "Previous equal-length period",
            )
    else:
        raise RequestClarificationError("Which baseline period should I use?")
    if baseline.start is None or baseline.end is None:
        raise RequestClarificationError("Which bounded baseline period should I use?")
    alignment = (
        comparison.alignment
        if comparison.alignment != "unspecified"
        else policy.comparison_alignment
    )
    if current.partial and alignment == "same_elapsed":
        aligned_end = baseline.start + (current.end - current.start)
        if comparison.baseline_reference == "same_period_last_year":
            # Corresponding inclusive calendar date, including Feb 29 -> Feb 28.
            aligned_end = add_months(current.end - timedelta(days=1), -12) + timedelta(days=1)
        baseline = DateRange(
            baseline.start,
            min(baseline.end, aligned_end),
            baseline.label + " (aligned elapsed period)",
            True,
        )
    return current, baseline
