"""Business time periods: quarters, fiscal years, halves, months and relative ranges.

Absolute periods compile to half-open date literals. Relative periods ("last
month", "YTD", "last 6 months") are anchored to the latest date in the fact
table, so answers stay meaningful when the warehouse lags the calendar.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from typing import Any

# Indian fiscal year: April to March, named by the ending year (FY2025 = FY 2024-25).
FISCAL_YEAR_START_MONTH = 4

_MONTHS = {
    "jan": 1, "january": 1, "feb": 2, "february": 2, "mar": 3, "march": 3,
    "apr": 4, "april": 4, "may": 5, "jun": 6, "june": 6, "jul": 7, "july": 7,
    "aug": 8, "august": 8, "sep": 9, "sept": 9, "september": 9, "oct": 10,
    "october": 10, "nov": 11, "november": 11, "dec": 12, "december": 12,
}  # fmt: skip
_MONTH = r"(jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|june?|july?|aug(?:ust)?|sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)"
_YEAR = r"(20\d\d|'\d\d)"
_ORDINAL = {
    "first": 1,
    "1st": 1,
    "second": 2,
    "2nd": 2,
    "third": 3,
    "3rd": 3,
    "fourth": 4,
    "4th": 4,
}

_FY = re.compile(
    r"\b(?:fy|fiscal\s+year|financial\s+year)\s*'?(\d{4}|\d{2})(?:\s*[-/]\s*(\d{4}|\d{2}))?\b",
    re.I,
)
_QUARTER_FY = re.compile(r"\bq([1-4])\s*[-/ ]?\s*fy\s*'?(\d{4}|\d{2})\b", re.I)
_QUARTER = re.compile(rf"\bq([1-4])\s*[-/,]?\s*(?:of\s+)?{_YEAR}?\b", re.I)
_YEAR_QUARTER = re.compile(r"\b(20\d\d)\s*[-/ ]?\s*q([1-4])\b", re.I)
_QUARTER_WORDS = re.compile(
    rf"\b(first|second|third|fourth|1st|2nd|3rd|4th)\s+quarter(?:\s+of)?(?:\s+{_YEAR})?\b", re.I
)
_HALF = re.compile(rf"\bh([12])\s*[-/,]?\s*(?:of\s+)?{_YEAR}?\b", re.I)
_HALF_WORDS = re.compile(rf"\b(first|second|1st|2nd)\s+half(?:\s+of)?(?:\s+{_YEAR})?\b", re.I)
_MONTH_RANGE = re.compile(
    rf"\b(?:from\s+|between\s+)?{_MONTH}\s*(?:-|\u2013|to|through|till|until|and)\s*{_MONTH}[\s,]*{_YEAR}\b",
    re.I,
)
_MONTH_YEAR = re.compile(rf"\b{_MONTH}[\s,'-]*{_YEAR}\b", re.I)

_LAST_N = re.compile(
    r"\b(?:last|past|previous|trailing|recent)\s+(\d{1,3})\s+(day|week|month|quarter|year)s?\b",
    re.I,
)
_RELATIVE: tuple[tuple[re.Pattern[str], str, str], ...] = (
    (re.compile(r"\b(?:last|previous|prior)\s+month\b", re.I), "last_month", "last month"),
    (re.compile(r"\b(?:this|current)\s+month\b|\bmtd\b|\bmonth\s+to\s+date\b", re.I), "this_month", "month to date"),
    (re.compile(r"\b(?:last|previous|prior)\s+quarter\b", re.I), "last_quarter", "last quarter"),
    (re.compile(r"\b(?:this|current)\s+quarter\b|\bqtd\b|\bquarter\s+to\s+date\b", re.I), "this_quarter", "quarter to date"),
    (
        re.compile(r"\b(?:this|current)\s+(?:fiscal|financial)\s+year\b|\bfytd\b|\bcurrent\s+fy\b|\bthis\s+fy\b", re.I),
        "fytd",
        "fiscal year to date",
    ),
    (re.compile(r"\bytd\b|\byear\s+to\s+date\b", re.I), "ytd", "year to date"),
)  # fmt: skip


@dataclass(frozen=True, slots=True)
class Period:
    """A date scope. Absolute periods use ``start``/``end`` (end exclusive)."""

    label: str
    start: date | None = None
    end: date | None = None
    relative: str | None = None
    count: int = 0
    years: tuple[int, ...] = ()

    def to_state(self) -> dict[str, Any]:
        return {
            "label": self.label,
            "start": self.start.isoformat() if self.start else None,
            "end": self.end.isoformat() if self.end else None,
            "relative": self.relative,
            "count": self.count,
            "years": list(self.years),
        }

    @classmethod
    def from_state(cls, data: dict[str, Any] | None) -> Period | None:
        if not data:
            return None
        return cls(
            label=str(data.get("label") or ""),
            start=date.fromisoformat(data["start"]) if data.get("start") else None,
            end=date.fromisoformat(data["end"]) if data.get("end") else None,
            relative=data.get("relative"),
            count=int(data.get("count") or 0),
            years=tuple(int(y) for y in data.get("years") or ()),
        )


def _full_year(text: str | None, default: int) -> int:
    if not text:
        return default
    digits = text.lstrip("'")
    return 2000 + int(digits) if len(digits) == 2 else int(digits)


def _add_months(day: date, months: int) -> date:
    index = day.year * 12 + day.month - 1 + months
    return date(index // 12, index % 12 + 1, 1)


def _quarter(year: int, quarter: int) -> tuple[date, date]:
    start = date(year, 3 * (quarter - 1) + 1, 1)
    return start, _add_months(start, 3)


def _fiscal_start(fy_end_year: int) -> date:
    return date(fy_end_year - 1, FISCAL_YEAR_START_MONTH, 1)


def _fy_label(fy_end_year: int) -> str:
    return f"FY{fy_end_year - 1}-{str(fy_end_year)[-2:]}"


def parse_period(question: str, *, today: date | None = None) -> Period | None:
    """The first business period named in the question, or ``None``."""
    q = question or ""
    this_year = (today or date.today()).year

    if m := _QUARTER_FY.search(q):
        quarter, fy = int(m.group(1)), _full_year(m.group(2), this_year)
        start = _add_months(_fiscal_start(fy), 3 * (quarter - 1))
        return Period(f"Q{quarter} {_fy_label(fy)}", start, _add_months(start, 3))
    if m := _FY.search(q):
        first, second = m.group(1), m.group(2)
        fy = _full_year(second, this_year) if second else _full_year(first, this_year)
        return Period(_fy_label(fy), _fiscal_start(fy), _fiscal_start(fy + 1))
    if m := _YEAR_QUARTER.search(q):
        year, quarter = int(m.group(1)), int(m.group(2))
        return Period(f"Q{quarter} {year}", *_quarter(year, quarter))
    if m := _QUARTER.search(q):
        quarter, year = int(m.group(1)), _full_year(m.group(2), this_year)
        return Period(f"Q{quarter} {year}", *_quarter(year, quarter))
    if m := _QUARTER_WORDS.search(q):
        quarter, year = _ORDINAL[m.group(1).lower()], _full_year(m.group(2), this_year)
        return Period(f"Q{quarter} {year}", *_quarter(year, quarter))
    for pattern in (_HALF, _HALF_WORDS):
        if m := pattern.search(q):
            half = int(m.group(1)) if m.group(1).isdigit() else _ORDINAL[m.group(1).lower()]
            year = _full_year(m.group(2), this_year)
            start = date(year, 1 if half == 1 else 7, 1)
            return Period(f"H{half} {year}", start, _add_months(start, 6))
    if m := _MONTH_RANGE.search(q):
        first, last = _MONTHS[m.group(1).lower()], _MONTHS[m.group(2).lower()]
        year = _full_year(m.group(3), this_year)
        if first <= last:
            start = date(year, first, 1)
            label = f"{m.group(1).title()}-{m.group(2).title()} {year}"
            return Period(label, start, _add_months(date(year, last, 1), 1))
    if m := _MONTH_YEAR.search(q):
        month, year = _MONTHS[m.group(1).lower()], _full_year(m.group(2), this_year)
        start = date(year, month, 1)
        return Period(start.strftime("%B %Y"), start, _add_months(start, 1))

    if m := _LAST_N.search(q):
        count, unit = int(m.group(1)), m.group(2).lower()
        if unit == "week":
            count, unit = count * 7, "day"
        if unit == "quarter":
            count, unit = count * 3, "month"
        return Period(
            f"last {m.group(1)} {m.group(2).lower()}s",
            relative=f"last_n_{unit}s",
            count=max(1, count),
        )
    for pattern, relative, label in _RELATIVE:
        if pattern.search(q):
            return Period(label, relative=relative)
    return None


def anchor_sql(table: str, column: str) -> str:
    """Latest loaded date of a fact table; relative periods count back from it."""
    # One alias per table: two facts in one statement must not share an alias.
    alias = f"{table.rsplit('.', 1)[-1]}_latest"
    return f"(SELECT MAX({alias}.{column}) FROM {table} {alias})"


def period_predicate(period: Period, column: str, anchor: str) -> str:
    """SQL predicate restricting ``column`` to the period."""
    if period.years:
        return f"EXTRACT(YEAR FROM {column})::int IN ({', '.join(str(y) for y in period.years)})"
    if period.start and period.end:
        return f"{column} >= DATE '{period.start.isoformat()}' AND {column} < DATE '{period.end.isoformat()}'"
    n = max(1, period.count)
    relative = {
        "last_month": (
            f"{column} >= date_trunc('month', {anchor}) - INTERVAL '1 month' "
            f"AND {column} < date_trunc('month', {anchor})"
        ),
        "this_month": f"{column} >= date_trunc('month', {anchor})",
        "last_quarter": (
            f"{column} >= date_trunc('quarter', {anchor}) - INTERVAL '3 months' "
            f"AND {column} < date_trunc('quarter', {anchor})"
        ),
        "this_quarter": f"{column} >= date_trunc('quarter', {anchor})",
        "ytd": f"{column} >= date_trunc('year', {anchor})",
        "fytd": (
            f"{column} >= date_trunc('year', {anchor} - INTERVAL '{FISCAL_YEAR_START_MONTH - 1} months') "
            f"+ INTERVAL '{FISCAL_YEAR_START_MONTH - 1} months'"
        ),
        "last_n_months": f"{column} >= date_trunc('month', {anchor}) - INTERVAL '{n - 1} months'",
        "last_n_years": f"{column} >= date_trunc('year', {anchor}) - INTERVAL '{n - 1} years'",
        "last_n_days": f"{column} > {anchor} - INTERVAL '{n} days'",
    }
    predicate = relative.get(period.relative or "")
    if predicate is None:
        raise ValueError(f"Unsupported period '{period.relative}'")
    return predicate
