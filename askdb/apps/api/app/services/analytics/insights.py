"""Business insight for Analytics Builder results.

Each analysis gets a narration written for its shape: a trend says how the metric moved
and what drove the latest period, a ranking says who leads and by how much, Actual vs
Target says overall achievement and who is behind. Every number comes from the result
rows or the driver query; nothing is inferred beyond them.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from app.services.analytics.compiler import BuilderQuery
from app.services.chat.narration import Narration, _fmt, _label, _num, _pct_change


@dataclass(slots=True)
class DriverResult:
    """Latest complete period vs the one before, per model / product."""

    dimension_label: str
    period_label: str
    previous_label: str
    rows: list[tuple[str, float, float]] = field(default_factory=list)


@dataclass(slots=True)
class InsightContext:
    query: BuilderQuery
    columns: list[str]
    rows: list[dict[str, Any]]
    metric_label: str
    partial_period: str | None = None
    driver: DriverResult | None = None


def build_narration(ctx: InsightContext) -> Narration | None:
    if not ctx.rows:
        return None
    q = ctx.query
    handler = {
        "contribution": _contribution,
        "running_total": _running_total,
        "moving_average": _moving_average,
        "period_growth": _growth,
        "yoy_growth": _growth,
        "growth_contribution": _growth_contribution,
        "actual_vs_target": _actual_vs_target,
        "top_n_per_group": _per_group,
        "above_average": _above_average,
    }.get(q.analysis)
    if handler is None:
        if q.time_column and not q.category_columns:
            handler = _trend
        elif q.time_column:
            handler = _trend_by_category
        elif q.category_columns:
            handler = _ranking
        else:
            handler = _single
    narration = handler(ctx)
    if narration is None:
        return None
    if ctx.driver is not None and q.analysis in _DRIVER_ANALYSES:
        narration.highlights.extend(_driver_lines(ctx))
    if ctx.partial_period:
        narration.highlights.append(
            f"{ctx.partial_period} is still in progress, so it is left out of period-on-period comparisons."
        )
    return narration


_DRIVER_ANALYSES = frozenset(
    {"basic", "trend", "period_growth", "yoy_growth", "moving_average", "running_total"}
)


# -- formatting -----------------------------------------------------------------------


class _Fmt:
    def __init__(self, metric_format: str) -> None:
        self.metric_format = metric_format

    def value(self, number: float) -> str:
        if self.metric_format == "currency":
            return _fmt(number, "currency")
        if self.metric_format == "percent":
            return _fmt(number, "percent", scale_percent=abs(number) <= 1.5)
        return _fmt(number, "number")

    def delta(self, number: float) -> str:
        text = self.value(abs(number))
        return f"+{text}" if number >= 0 else f"-{text}"


def _pct(value: float | None, *, signed: bool = True) -> str:
    if value is None:
        return "n/a"
    return f"{value:+.1f}%" if signed else f"{value:.1f}%"


def _period(value: Any, grain: str | None) -> str:
    text = _label(value)
    if grain == "quarter" and len(text) >= 7:
        try:
            year, month = int(text[:4]), int(text[5:7])
            return f"Q{(month - 1) // 3 + 1} {year}"
        except ValueError:
            return text
    if grain == "month" and len(text) == 7:
        try:
            return date(int(text[:4]), int(text[5:7]), 1).strftime("%b %Y")
        except ValueError:
            return text
    return text


def _cat_label(row: dict[str, Any], columns: list[str]) -> str:
    return " \u00b7 ".join(str(row.get(c)) for c in columns if row.get(c) is not None) or "(blank)"


def _series(
    ctx: InsightContext, value_col: str, *, complete_only: bool = True
) -> list[tuple[str, float]]:
    q = ctx.query
    points = [
        (_period(row.get(q.time_column), q.time_grain), v)
        for row in ctx.rows
        if (v := _num(row.get(value_col))) is not None
    ]
    if complete_only and ctx.partial_period and points and points[-1][0] == ctx.partial_period:
        points = points[:-1]
    return points


# -- shapes ---------------------------------------------------------------------------


def _single(ctx: InsightContext) -> Narration | None:
    value = _num(ctx.rows[0].get(ctx.query.metric_column))
    if value is None:
        return None
    period = f" for {ctx.query.date_label.lower()}" if ctx.query.date_label else ""
    return Narration(
        summary=f"{ctx.metric_label} is {_Fmt(ctx.query.metric_format).value(value)}{period}."
    )


def _trend(ctx: InsightContext) -> Narration | None:
    q = ctx.query
    f = _Fmt(q.metric_format)
    points = _series(ctx, q.metric_column)
    if len(points) < 2:
        return _single(ctx) if len(points) == 1 else None
    (first_label, first), (last_label, last) = points[0], points[-1]
    change = _pct_change(first, last)
    direction = "increased" if last > first else "decreased" if last < first else "was flat"
    summary = (
        f"{ctx.metric_label} {direction} {abs(change):.0%} from {first_label} to {last_label}"
        if change is not None and direction != "was flat"
        else f"{ctx.metric_label} {direction} between {first_label} and {last_label}"
    ) + f" ({f.value(first)} \u2192 {f.value(last)})."
    peak = max(points, key=lambda p: p[1])
    low = min(points, key=lambda p: p[1])
    prev_label, prev = points[-2]
    highlights = [f"Peak: {peak[0]} at {f.value(peak[1])}; lowest: {low[0]} at {f.value(low[1])}."]
    latest = _pct_change(prev, last)
    if latest is not None:
        highlights.append(f"{last_label} vs {prev_label}: {latest:+.1%}.")
    if q.metric_format != "percent":
        total = sum(v for _, v in points)
        highlights.append(
            f"Total across {len(points)} {q.time_grain or 'period'}s: {f.value(total)}."
        )
    insight = None
    if len(points) >= 4:
        recent = points[-3:]
        if all(recent[i][1] < recent[i + 1][1] for i in range(2)):
            insight = (
                f"{ctx.metric_label} has grown for three consecutive {q.time_grain or 'period'}s."
            )
        elif all(recent[i][1] > recent[i + 1][1] for i in range(2)):
            insight = (
                f"{ctx.metric_label} has fallen for three consecutive {q.time_grain or 'period'}s."
            )
    return Narration(summary=summary, highlights=highlights, insight=insight)


def _trend_by_category(ctx: InsightContext) -> Narration | None:
    q = ctx.query
    f = _Fmt(q.metric_format)
    value_col = q.value_column or q.metric_column
    totals: dict[str, float] = defaultdict(float)
    by_cat: dict[str, list[tuple[str, float]]] = defaultdict(list)
    for row in ctx.rows:
        value = _num(row.get(value_col))
        if value is None:
            continue
        cat = _cat_label(row, q.category_columns)
        totals[cat] += value
        by_cat[cat].append((_period(row.get(q.time_column), q.time_grain), value))
    if not totals:
        return None
    leader = max(totals, key=lambda k: totals[k])
    summary = f"{leader} leads {ctx.metric_label.lower()} across the period"
    if q.metric_format != "percent":
        grand = sum(totals.values())
        if grand:
            summary += (
                f" with {f.value(totals[leader])} ({totals[leader] / grand:.0%} of the total shown)"
            )
    summary += "."
    growth: list[tuple[str, float]] = []
    for cat, points in by_cat.items():
        if ctx.partial_period and points and points[-1][0] == ctx.partial_period:
            points = points[:-1]
        if len(points) >= 2 and (change := _pct_change(points[0][1], points[-1][1])) is not None:
            growth.append((cat, change))
    highlights: list[str] = []
    if growth:
        best = max(growth, key=lambda g: g[1])
        worst = min(growth, key=lambda g: g[1])
        highlights.append(
            f"Fastest growing: {best[0]} ({best[1]:+.0%} first to last {q.time_grain or 'period'})."
        )
        if worst[0] != best[0]:
            highlights.append(f"Weakest: {worst[0]} ({worst[1]:+.0%}).")
    return Narration(summary=summary, highlights=highlights)


def _ranking(ctx: InsightContext) -> Narration | None:
    q = ctx.query
    f = _Fmt(q.metric_format)
    col = q.metric_column
    ranked = [
        (_cat_label(r, q.category_columns), v)
        for r in ctx.rows
        if (v := _num(r.get(col))) is not None
    ]
    if not ranked:
        return None
    if len(ranked) == 1:
        return Narration(
            summary=f"{ranked[0][0]}: {f.value(ranked[0][1])} {ctx.metric_label.lower()}."
        )
    bottom = q.analysis == "bottom_n"
    ordered = sorted(ranked, key=lambda r: r[1], reverse=not bottom)
    (lead, lead_v), (second, second_v) = ordered[0], ordered[1]
    if q.analysis == "comparison":
        hi, lo = (ordered[0], ordered[-1])
        gap = _pct_change(lo[1], hi[1])
        summary = f"{hi[0]} leads {lo[0]} on {ctx.metric_label.lower()}: {f.value(hi[1])} vs {f.value(lo[1])}"
        summary += f" ({gap:+.0%})." if gap is not None else "."
        return Narration(summary=summary)
    noun = "lowest" if bottom else "highest"
    summary = f"{lead} has the {noun} {ctx.metric_label.lower()} at {f.value(lead_v)}"
    gap = _pct_change(second_v, lead_v) if not bottom else _pct_change(lead_v, second_v)
    if gap is not None and abs(gap) > 0.005:
        summary += f", {abs(gap):.0%} {'below' if bottom else 'ahead of'} {second}"
    summary += "."
    highlights: list[str] = []
    if q.metric_format != "percent" and not bottom:
        total = sum(v for _, v in ranked)
        if total > 0:
            top3 = sum(v for _, v in ordered[:3])
            highlights.append(f"Top 3 make up {top3 / total:.0%} of the {len(ranked)} shown.")
    if len(ordered) > 2:
        highlights.append(
            f"Range: {f.value(ordered[-1][1])} ({ordered[-1][0]}) to {f.value(ordered[0][1])} ({ordered[0][0]})."
        )
    insight = None
    if not bottom and q.metric_format != "percent" and len(ranked) >= 5:
        values = sorted((v for _, v in ranked), reverse=True)
        if values[0] > 2 * (sum(values) / len(values)):
            insight = f"{lead} is more than twice the average of the group, a concentration worth watching."
    return Narration(summary=summary, highlights=highlights, insight=insight)


def _per_group(ctx: InsightContext) -> Narration | None:
    q = ctx.query
    f = _Fmt(q.metric_format)
    group_col = next((c for c in ctx.columns if c not in {q.metric_column, "row_number"}), None)
    item_col = next(
        (c for c in ctx.columns if c not in {group_col, q.metric_column, "row_number"}), None
    )
    if group_col is None or item_col is None:
        return _ranking(ctx)
    leaders = [
        (row.get(group_col), row.get(item_col), _num(row.get(q.metric_column)))
        for row in ctx.rows
        if row.get("row_number") == 1
    ]
    leaders = [entry for entry in leaders if entry[2] is not None]
    if not leaders:
        return None
    leaders.sort(key=lambda e: e[2] or 0, reverse=True)
    top = leaders[0]
    summary = f"{top[1]} is the strongest performer overall, leading {top[0]} with {f.value(top[2] or 0)}."
    highlights = [f"{g}: {item} ({f.value(v or 0)})" for g, item, v in leaders[1:6]]
    return Narration(summary=summary, highlights=highlights)


def _contribution(ctx: InsightContext) -> Narration | None:
    q = ctx.query
    share_col = q.value_column
    items = [
        (_cat_label(r, q.category_columns), v, r)
        for r in ctx.rows
        if (v := _num(r.get(share_col))) is not None
    ]
    if not items:
        return None
    if q.time_column:
        latest = max(str(r.get(q.time_column)) for _, _, r in items)
        items = [i for i in items if str(i[2].get(q.time_column)) == latest]
    items.sort(key=lambda i: i[1], reverse=True)
    lead, lead_share, _ = items[0]
    summary = f"{lead} contributes {lead_share:.1f}% of {ctx.metric_label.lower()}."
    highlights: list[str] = []
    if len(items) >= 3:
        top3 = sum(i[1] for i in items[:3])
        highlights.append(f"The top 3 together account for {top3:.1f}%.")
    cumulative = [
        (_cat_label(r, q.category_columns), c)
        for r in ctx.rows
        if (c := _num(r.get("cumulative_share_pct"))) is not None
    ]
    if cumulative:
        reach = next((i for i, (_, c) in enumerate(cumulative, start=1) if c >= 80), None)
        if reach is not None:
            highlights.append(f"{reach} of {len(cumulative)} shown make up 80% of the total.")
    if len(items) > 1:
        highlights.append(f"Smallest share: {items[-1][0]} at {items[-1][1]:.1f}%.")
    return Narration(summary=summary, highlights=highlights)


def _running_total(ctx: InsightContext) -> Narration | None:
    q = ctx.query
    f = _Fmt(q.metric_format)
    if q.category_columns:
        finals: dict[str, float] = {}
        for row in ctx.rows:
            v = _num(row.get(q.value_column))
            if v is not None:
                finals[_cat_label(row, q.category_columns)] = v
        if not finals:
            return None
        leader = max(finals, key=lambda k: finals[k])
        return Narration(
            summary=f"{leader} reaches the highest cumulative {ctx.metric_label.lower()} at {f.value(finals[leader])}."
        )
    running = _series(ctx, q.value_column, complete_only=False)
    period = _series(ctx, q.metric_column, complete_only=False)
    if not running:
        return None
    summary = f"Cumulative {ctx.metric_label.lower()} reached {f.value(running[-1][1])} by {running[-1][0]}."
    highlights: list[str] = []
    if period:
        best = max(period, key=lambda p: p[1])
        highlights.append(f"Largest single addition: {best[0]} ({f.value(best[1])}).")
        if len(period) >= 2:
            half = running[-1][1] / 2
            midpoint = next((label for label, value in running if value >= half), None)
            if midpoint:
                highlights.append(f"Half of the total was reached by {midpoint}.")
    return Narration(summary=summary, highlights=highlights)


def _moving_average(ctx: InsightContext) -> Narration | None:
    q = ctx.query
    f = _Fmt(q.metric_format)
    if q.category_columns:
        return _trend_by_category(ctx)
    smooth = _series(ctx, q.value_column)
    actual = _series(ctx, q.metric_column)
    if len(smooth) < 2:
        return Narration(
            summary="Not enough history in the selected range for a full moving average yet; widen the date range."
        )
    first, last = smooth[0], smooth[-1]
    change = _pct_change(first[1], last[1])
    direction = "rising" if last[1] > first[1] else "falling" if last[1] < first[1] else "flat"
    summary = f"The smoothed trend of {ctx.metric_label.lower()} is {direction}"
    summary += f" ({change:+.0%} from {first[0]} to {last[0]})." if change is not None else "."
    highlights = [f"Latest moving average: {f.value(last[1])} ({last[0]})."]
    if actual:
        latest_actual = actual[-1][1]
        gap = _pct_change(last[1], latest_actual)
        if gap is not None:
            highlights.append(
                f"{actual[-1][0]} came in {abs(gap):.0%} {'above' if gap >= 0 else 'below'} its moving average."
            )
    return Narration(summary=summary, highlights=highlights)


def _growth(ctx: InsightContext) -> Narration | None:
    q = ctx.query
    col = q.value_column
    label = {"mom_growth_pct": "Month-on-month", "qoq_growth_pct": "Quarter-on-quarter"}.get(
        col, "Year-on-year"
    )
    if q.category_columns:
        latest_by_cat: dict[str, tuple[str, float]] = {}
        for row in ctx.rows:
            v = _num(row.get(col))
            period = _period(row.get(q.time_column), q.time_grain)
            if v is None or period == ctx.partial_period:
                continue
            latest_by_cat[_cat_label(row, q.category_columns)] = (period, v)
        if not latest_by_cat:
            return Narration(
                summary=f"{label} growth needs data for the comparison period; widen the date range."
            )
        best = max(latest_by_cat.items(), key=lambda kv: kv[1][1])
        worst = min(latest_by_cat.items(), key=lambda kv: kv[1][1])
        summary = f"{best[0]} grew fastest in {best[1][0]} at {_pct(best[1][1])} {label.lower()}."
        highlights = []
        if worst[0] != best[0]:
            highlights.append(f"Weakest: {worst[0]} at {_pct(worst[1][1])}.")
        declining = sum(1 for _, (_, v) in latest_by_cat.items() if v < 0)
        if declining:
            highlights.append(f"{declining} of {len(latest_by_cat)} declined in the latest period.")
        return Narration(summary=summary, highlights=highlights)
    points = _series(ctx, col)
    if not points:
        return Narration(
            summary=f"{label} growth needs data for the comparison period; widen the date range."
        )
    last_label, last = points[-1]
    summary = f"{label} growth in {ctx.metric_label.lower()} was {_pct(last)} in {last_label}."
    highlights: list[str] = []
    if len(points) >= 2:
        best = max(points, key=lambda p: p[1])
        worst = min(points, key=lambda p: p[1])
        avg = sum(v for _, v in points) / len(points)
        highlights.append(
            f"Best: {best[0]} ({_pct(best[1])}); weakest: {worst[0]} ({_pct(worst[1])})."
        )
        highlights.append(f"Average {label.lower()} growth over the range: {_pct(avg)}.")
        negatives = sum(1 for _, v in points if v < 0)
        if negatives:
            highlights.append(f"{negatives} of {len(points)} periods declined.")
    return Narration(summary=summary, highlights=highlights)


def _growth_contribution(ctx: InsightContext) -> Narration | None:
    q = ctx.query
    f = _Fmt(q.metric_format)
    m = q.metric_column
    rows = [
        (
            _cat_label(r, q.category_columns),
            _num(r.get(f"change_{m}")) or 0.0,
            _num(r.get("contribution_to_change_pct")),
            _num(r.get(f"current_{m}")) or 0.0,
            _num(r.get(f"previous_{m}")) or 0.0,
        )
        for r in ctx.rows
    ]
    if not rows:
        return None
    current = sum(r[3] for r in rows)
    previous = sum(r[4] for r in rows)
    total_change = current - previous
    change_pct = _pct_change(previous, current)
    verb = "grew" if total_change >= 0 else "fell"
    summary = f"{ctx.metric_label} {verb} {f.delta(total_change)}"
    summary += f" ({change_pct:+.1%})" if change_pct is not None else ""
    summary += f", comparing {q.date_label}." if q.date_label else "."
    gainers = sorted((r for r in rows if r[1] > 0), key=lambda r: r[1], reverse=True)
    losers = sorted((r for r in rows if r[1] < 0), key=lambda r: r[1])
    highlights: list[str] = []
    if gainers:
        g = gainers[0]
        share = f", {g[2]:.0f}% of the net change" if g[2] is not None and total_change > 0 else ""
        highlights.append(f"Top contributor: {g[0]} ({f.delta(g[1])}{share}).")
    if losers:
        highlights.append(f"Biggest drag: {losers[0][0]} ({f.delta(losers[0][1])}).")
    if gainers and losers:
        highlights.append(
            f"{len(gainers)} grew and {len(losers)} declined among the {len(rows)} shown."
        )
    return Narration(summary=summary, highlights=highlights)


def _actual_vs_target(ctx: InsightContext) -> Narration | None:
    q = ctx.query
    f = _Fmt(q.metric_format)
    actual = sum(_num(r.get("actual")) or 0.0 for r in ctx.rows)
    target = sum(_num(r.get("target")) or 0.0 for r in ctx.rows)
    if target <= 0:
        return Narration(summary="No targets are recorded for the selected period.")
    achievement = 100.0 * actual / target
    status = "ahead of" if achievement >= 100 else "behind"
    summary = (
        f"{ctx.metric_label} is at {achievement:.1f}% of target ({f.value(actual)} vs {f.value(target)}), "
        f"{f.delta(actual - target)} {status} plan."
    )
    highlights: list[str] = []
    if "make" in ctx.columns:
        per_make: dict[str, list[float]] = defaultdict(lambda: [0.0, 0.0])
        for row in ctx.rows:
            make = str(row.get("make"))
            per_make[make][0] += _num(row.get("actual")) or 0.0
            per_make[make][1] += _num(row.get("target")) or 0.0
        scored = [(k, 100.0 * a / t) for k, (a, t) in per_make.items() if t > 0]
        if scored:
            scored.sort(key=lambda s: s[1], reverse=True)
            above = sum(1 for _, s in scored if s >= 100)
            highlights.append(f"{above} of {len(scored)} brands met or beat target.")
            highlights.append(
                f"Best: {scored[0][0]} at {scored[0][1]:.0f}%; furthest behind: {scored[-1][0]} at {scored[-1][1]:.0f}%."
            )
    elif q.time_column:
        missed = [
            _period(r.get(q.time_column), q.time_grain)
            for r in ctx.rows
            if (a := _num(r.get("achievement_pct"))) is not None and a < 100
        ]
        if missed:
            highlights.append(
                f"Target missed in {len(missed)} of {len(ctx.rows)} periods, most recently {missed[-1]}."
            )
    focus = None
    if achievement < 95 and "make" in ctx.columns and highlights:
        focus = "Focus on the brands furthest behind target; they hold the largest recoverable gap."
    return Narration(summary=summary, highlights=highlights, focus=focus)


def _above_average(ctx: InsightContext) -> Narration | None:
    q = ctx.query
    f = _Fmt(q.metric_format)
    m = q.metric_column
    items = [
        (
            _cat_label(r, q.category_columns),
            _num(r.get(m)),
            _num(r.get("above_average_pct")),
            _num(r.get(f"average_{m}")),
        )
        for r in ctx.rows
    ]
    items = [i for i in items if i[1] is not None]
    if not items:
        return Narration(summary="No values are above the average for this selection.")
    lead = max(items, key=lambda i: i[1] or 0)
    avg = items[0][3]
    summary = f"{len(items)} values beat the average"
    summary += f" of {f.value(avg)}" if avg is not None else ""
    summary += f"; {lead[0]} is furthest ahead at {f.value(lead[1] or 0)}"
    summary += f" ({lead[2]:+.0f}% vs average)." if lead[2] is not None else "."
    return Narration(summary=summary)


def _driver_lines(ctx: InsightContext) -> list[str]:
    driver = ctx.driver
    if driver is None or not driver.rows:
        return []
    f = _Fmt(ctx.query.metric_format)
    lines: list[str] = []
    total = sum(current for _, current, _ in driver.rows)
    top = max(driver.rows, key=lambda r: r[1])
    if top[1] > 0 and total > 0:
        lines.append(
            f"Top contributing {driver.dimension_label.lower()} in {driver.period_label}: {top[0]} "
            f"({f.value(top[1])}, {top[1] / total:.0%} of the total)."
        )
    changes = [(label, current - previous) for label, current, previous in driver.rows]
    gain = max(changes, key=lambda c: c[1])
    drop = min(changes, key=lambda c: c[1])
    if gain[1] > 0:
        lines.append(
            f"Biggest increase vs {driver.previous_label}: {gain[0]} ({f.delta(gain[1])})."
        )
    if drop[1] < 0:
        lines.append(f"Biggest decline vs {driver.previous_label}: {drop[0]} ({f.delta(drop[1])}).")
    return lines


def period_name(start: date, grain: str) -> str:
    if grain == "quarter":
        return f"Q{(start.month - 1) // 3 + 1} {start.year}"
    if grain == "year":
        return str(start.year)
    return start.strftime("%b %Y")
