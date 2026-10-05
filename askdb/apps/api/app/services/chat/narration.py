"""Executive narration for a governed result.

Turns result rows into an Executive Summary, Key Highlights, a Business Insight and an
optional Recommended Focus Area. Every number comes from the rows; drivers that the
result cannot show (e.g. "because of SUV demand") are never invented.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from statistics import median
from typing import Any, Literal

MeasureKind = Literal["currency", "percent", "number"]

_TIME_HINTS = ("month", "year", "date", "quarter", "week", "period", "day")
_PERCENT_HINTS = ("ratio", "share", "rate", "pct", "percent", "penetration", "mix", "margin_pct")
_CURRENCY_HINTS = (
    "revenue",
    "premium",
    "amount",
    "price",
    "cost",
    "sales_value",
    "discount",
    "incurred",
    "paid",
    "profit",
    "income",
    "spend",
    "asp",
)
_LOWER_IS_BETTER = (
    "loss",
    "claim_ratio",
    "cost",
    "expense",
    "churn",
    "cancel",
    "defect",
    "complaint",
    "lapse",
    "fraud",
    "delay",
    "days_to",
    "settlement_days",
)
_ISO_PERIOD = re.compile(r"^\d{4}(-\d{2}){0,2}")


@dataclass
class Narration:
    summary: str
    highlights: list[str] = field(default_factory=list)
    insight: str | None = None
    focus: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "summary": self.summary,
            "highlights": self.highlights,
            "insight": self.insight,
            "focus": self.focus,
        }

    def executive_text(self) -> str:
        return " ".join(part for part in (self.summary, self.insight) if part)

    def analyst_text(self) -> str:
        parts = [self.summary, *self.highlights, self.insight or "", self.focus or ""]
        return " ".join(part.strip() for part in parts if part and part.strip())


@dataclass(frozen=True)
class _Measure:
    column: str
    kind: MeasureKind
    scale_percent: bool

    @property
    def label(self) -> str:
        return _friendly(self.column)

    @property
    def additive(self) -> bool:
        return self.kind != "percent"

    @property
    def lower_is_better(self) -> bool:
        return any(hint in self.column.lower() for hint in _LOWER_IS_BETTER)

    def fmt(self, value: float) -> str:
        return _fmt(value, self.kind, scale_percent=self.scale_percent)

    def gap(self, high: float, low: float) -> str | None:
        """'13.0 pts' for percentages, '62%' otherwise; None when the two are level."""
        if self.kind == "percent":
            points = (high - low) * (100 if self.scale_percent else 1)
            return f"{points:.1f} pts" if points >= 0.05 else None
        change = _pct_change(low, high)
        return f"{change:.0%}" if change is not None and change > 0.005 else None


def narrate(columns: list[str], rows: list[dict[str, Any]]) -> Narration | None:
    """Return a narration for the result shape, or ``None`` when there is nothing numeric."""
    if not columns or not rows:
        return None
    measures = _measures(columns, rows)
    if not measures:
        return None
    primary = measures[0]
    label_col = next((c for c in columns if c not in {m.column for m in measures}), None)
    seed = _seed(columns, rows)

    if label_col is None or len(rows) == 1:
        return _single(rows[0], label_col, measures)
    points = _points(rows, label_col, primary.column)
    if len(points) < 2:
        return _single(rows[0], label_col, measures)
    if _is_time(label_col, points):
        return _trend(points, primary, seed)
    return _ranking(points, label_col, primary, measures[1:], rows, seed)


# Shapes ------------------------------------------------------------------------------


def _single(row: dict[str, Any], label_col: str | None, measures: list[_Measure]) -> Narration:
    primary = measures[0]
    value = _num(row.get(primary.column))
    subject = str(row.get(label_col)) if label_col and row.get(label_col) is not None else None
    if value is None:
        return Narration(summary="The result is ready in the table below.")
    if subject:
        summary = f"{subject} recorded {primary.label} of {primary.fmt(value)} for the selection."
    else:
        summary = f"{primary.label.capitalize()} stands at {primary.fmt(value)} for the selection."
    highlights = [
        f"{m.label.capitalize()}: {m.fmt(v)}"
        for m in measures[1:4]
        if (v := _num(row.get(m.column))) is not None
    ]
    return Narration(summary=summary, highlights=highlights)


def _trend(points: list[tuple[str, float]], measure: _Measure, seed: int) -> Narration:
    if all(_ISO_PERIOD.match(label) for label, _ in points):
        points = sorted(points, key=lambda item: item[0])
    labels = [label for label, _ in points]
    values = [value for _, value in points]
    first_label, first = points[0]
    last_label, last = points[-1]
    peak_label, peak = max(points, key=lambda item: item[1])
    low_label, low = min(points, key=lambda item: item[1])
    mean = sum(values) / len(values)
    change = _pct_change(first, last)
    name = measure.label

    if len(points) == 2 and change is not None:
        direction = "up" if change >= 0 else "down"
        summary = (
            f"{name.capitalize()} reached {measure.fmt(last)} in {last_label}, "
            f"{direction} {abs(change):.0%} on {first_label}"
        )
        summary += (
            f", making {last_label} the stronger of the two periods."
            if last >= first
            else f"; {first_label} remains the stronger period."
        )
    elif change is not None and change > 0.05:
        verb = _pick(["grew", "climbed", "rose"], seed)
        summary = (
            f"{name.capitalize()} {verb} {change:.0%} across the period, from "
            f"{measure.fmt(first)} in {first_label} to {measure.fmt(last)} in {last_label}."
        )
    elif change is not None and change < -0.05:
        verb = _pick(["declined", "fell", "slipped"], seed)
        summary = (
            f"{name.capitalize()} {verb} {abs(change):.0%} across the period, from "
            f"{measure.fmt(first)} in {first_label} to {measure.fmt(last)} in {last_label}."
        )
    else:
        summary = (
            f"{name.capitalize()} held broadly steady, averaging {measure.fmt(mean)} "
            f"per period from {first_label} to {last_label}."
        )
    if len(points) > 2 and peak_label == last_label:
        summary += f" {last_label} was the strongest period in the selection."
    elif len(points) > 2:
        summary += f" The high point came in {peak_label} at {measure.fmt(peak)}."

    highlights: list[str] = []
    if len(points) > 2:
        highlights.append(
            f"Range: {measure.fmt(low)} ({low_label}) to {measure.fmt(peak)} ({peak_label})."
        )
    latest = _pct_change(values[-2], last) if len(values) >= 3 else None
    if latest is not None:
        highlights.append(f"Latest period vs the one before: {latest:+.0%}.")
    if measure.additive and len(points) > 2:
        highlights.append(f"Total across {len(points)} periods: {measure.fmt(sum(values))}.")
    spread = _cv(values)
    if spread is not None and spread > 0.25 and len(points) >= 4:
        highlights.append(
            f"Results swing noticeably between periods (about \u00b1{spread:.0%} around the average)."
        )

    half = len(values) // 2
    momentum = (
        _pct_change(sum(values[:half]) / half, sum(values[-half:]) / half) if half >= 2 else None
    )
    earlier = _pct_change(values[-3], values[-2]) if len(values) >= 3 else None
    insight: str | None = None
    focus: str | None = None
    if latest is not None and latest < -0.4 and not measure.lower_is_better:
        insight = (
            f"{last_label} is sharply below {labels[-2]}. If {last_label} is still in progress, "
            "treat it as partial before drawing conclusions."
        )
    elif momentum is not None and abs(momentum) > 0.05 and measure.lower_is_better:
        if momentum > 0:
            insight = (
                f"{name.capitalize()} is creeping up: recent periods averaged {momentum:.0%} "
                "above the earlier ones, a trend worth containing before it compounds."
            )
            focus = (
                f"Find the segments driving the rise in {name} and set a target to bring it "
                "back to earlier levels."
            )
        else:
            insight = (
                f"{name.capitalize()} is improving: recent periods averaged "
                f"{abs(momentum):.0%} below the earlier ones."
            )
    elif momentum is not None and momentum > 0.05:
        insight = (
            f"Momentum is building: the most recent periods averaged {momentum:.0%} above the "
            f"earlier ones, so {name} is on a sustained upward path rather than a one-off spike."
        )
        focus = (
            "Identify the segments behind the recent lift (break this down by region, "
            "dealer or model) and plan capacity and inventory to sustain it."
        )
    elif momentum is not None and momentum < -0.05:
        insight = (
            f"The most recent periods averaged {abs(momentum):.0%} below the earlier ones, "
            f"a sustained softening in {name} rather than a one-off dip."
        )
        focus = (
            "Locate where the slowdown is concentrated by breaking this down by region, "
            "dealer or model, and act there first."
        )
    elif (
        latest is not None
        and earlier is not None
        and min(latest, earlier) > 0
        and abs(latest - earlier) > 0.03
        and not measure.lower_is_better
    ):
        pace = "accelerated" if latest > earlier else "slowed"
        insight = (
            f"Growth {pace} in the latest period ({latest:+.0%} versus {earlier:+.0%} the "
            f"period before)"
            + (
                ", a signal worth watching as the next period lands."
                if pace == "slowed"
                else ", so the trend is strengthening."
            )
        )
    elif spread is not None and spread > 0.25:
        insight = (
            f"{name.capitalize()} is stable on average but uneven period to period, "
            "which makes forecasting and stock planning harder."
        )
    return Narration(summary=summary, highlights=highlights[:3], insight=insight, focus=focus)


def _ranking(
    points: list[tuple[str, float]],
    label_col: str,
    measure: _Measure,
    others: list[_Measure],
    rows: list[dict[str, Any]],
    seed: int,
) -> Narration:
    ranked = sorted(points, key=lambda item: item[1], reverse=True)
    values = [value for _, value in ranked]
    n = len(ranked)
    leader, top = ranked[0]
    runner_up, second = ranked[1]
    bottom_name, bottom = ranked[-1]
    total = sum(values) if measure.additive else 0.0
    mean = sum(values) / n
    dim = _dimension(label_col)
    name = measure.label

    risk = measure.lower_is_better
    gap = _pct_change(second, top)
    gap_text = measure.gap(top, second)
    if risk:
        summary = f"{leader} has the highest {name} at {measure.fmt(top)}"
    else:
        lead_verb = _pick(["leads", "tops the list for", "comes out ahead on"], seed)
        summary = f"{leader} {lead_verb} {name} at {measure.fmt(top)}"
    if total > 0 and measure.additive:
        summary += f", {top / total:.0%} of the total"
    if gap_text:
        summary += f", {gap_text} {'above' if risk else 'ahead of'} {runner_up}."
    else:
        summary += f", essentially level with {runner_up}."

    highlights: list[str] = []
    if n >= 4 and total > 0:
        top3 = sum(values[:3])
        names = ", ".join(label for label, _ in ranked[:3])
        highlights.append(f"Top 3 ({names}) contribute {top3 / total:.0%} of the total.")
    if n >= 3 and risk:
        highlights.append(f"{bottom_name} is the best at {measure.fmt(bottom)}.")
    elif n >= 3:
        ratio = top / bottom if bottom > 0 else None
        tail = f"{bottom_name} trails at {measure.fmt(bottom)}"
        highlights.append(tail + (f", {ratio:.1f}x below the leader." if ratio else "."))
    if n >= 3:
        highlights.append(
            f"Median across {n} {_plural(dim)}: {measure.fmt(median(values))}."
        )
    leader_row = next((r for r in rows if str(r.get(label_col)) == leader), None)
    for other in others[:1]:
        value = _num(leader_row.get(other.column)) if leader_row else None
        if value is not None:
            highlights.append(f"{leader} also posts {other.label} of {other.fmt(value)}.")

    insight: str | None = None
    focus: str | None = None
    top3_share = sum(values[:3]) / total if total > 0 and n >= 5 else None
    middle = median(values)
    if risk:
        if n >= 3:
            insight = (
                f"{leader} stands out at {measure.fmt(top)} against a median of "
                f"{measure.fmt(middle)}; closing that gap is the biggest lever on overall {name}."
            )
            focus = (
                f"Prioritise {leader}" + (f" and {runner_up}" if n >= 4 else "")
                + f": review what is driving their {name} and set a target near "
                f"{bottom_name}'s {measure.fmt(bottom)}."
            )
        return Narration(summary=summary, highlights=highlights[:3], insight=insight, focus=focus)
    if gap is not None and gap >= 0.5 and gap_text:
        insight = (
            f"{leader} is a clear outlier, {gap_text} ahead of the next {dim}, so overall "
            f"{name} depends heavily on how {leader} performs."
        )
    elif top3_share is not None and top3_share >= 0.6:
        insight = (
            f"Performance is concentrated: three {_plural(dim)} deliver {top3_share:.0%} of "
            f"{name}, so a slip by any leader moves the total."
        )
    elif top3_share is not None and top3_share <= min(0.45, 3 / n + 0.15):
        insight = (
            f"Contribution is broad-based across {_plural(dim)}; growth will come from lifting "
            "the middle of the pack rather than one standout."
        )
    elif n >= 3 and measure.kind == "percent":
        insight = (
            f"The spread between {leader} ({measure.fmt(top)}) and {bottom_name} "
            f"({measure.fmt(bottom)}) shows where practices differ most."
        )

    if n >= 3 and bottom < 0.5 * mean:
        uplift = mean - bottom
        focus = f"Review the lower performers such as {bottom_name}"
        focus += (
            f"; bringing it up to the average would add about {measure.fmt(uplift)} "
            f"to {name}."
            if measure.additive
            else f", which sits well below the average of {measure.fmt(mean)}."
        )
    elif top3_share is not None and top3_share >= 0.6:
        focus = (
            f"Protect the top {_plural(dim)} and replicate {leader}'s approach in the mid-tier "
            "to reduce concentration risk."
        )
    return Narration(summary=summary, highlights=highlights[:3], insight=insight, focus=focus)


# Helpers -----------------------------------------------------------------------------


def _measures(columns: list[str], rows: list[dict[str, Any]]) -> list[_Measure]:
    found: list[_Measure] = []
    sample = rows[: min(len(rows), 20)]
    for index, column in enumerate(columns):
        values = [_num(row.get(column)) for row in sample]
        numeric = [v for v in values if v is not None]
        if not numeric or len(numeric) < len(sample) * 0.6:
            continue
        lowered = column.lower()
        if index == 0 and len(columns) > 1 and any(h in lowered for h in _TIME_HINTS):
            continue
        if lowered.endswith("_id") or lowered in {"id", "rank", "row_number"}:
            continue
        kind = _kind(lowered)
        scale = kind == "percent" and max(abs(v) for v in numeric) <= 1.5
        found.append(_Measure(column=column, kind=kind, scale_percent=scale))
    return found


def _kind(column: str) -> MeasureKind:
    if any(hint in column for hint in _PERCENT_HINTS):
        return "percent"
    if any(hint in column for hint in _CURRENCY_HINTS):
        return "currency"
    return "number"


def _points(rows: list[dict[str, Any]], label_col: str, value_col: str) -> list[tuple[str, float]]:
    points: list[tuple[str, float]] = []
    for row in rows:
        label = row.get(label_col)
        value = _num(row.get(value_col))
        if label is None or value is None:
            continue
        points.append((_label(label), value))
    return points


def _is_time(label_col: str, points: list[tuple[str, float]]) -> bool:
    if any(hint in label_col.lower() for hint in _TIME_HINTS):
        return True
    return all(_ISO_PERIOD.match(label) for label, _ in points)


def _label(value: Any) -> str:
    text = str(value)
    if re.match(r"^\d{4}-\d{2}-01(T00:00:00)?", text):
        return text[:7]
    if re.match(r"^\d{4}-\d{2}-\d{2}T", text):
        return text[:10]
    return text


def _num(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(str(value))
    except ValueError:
        return None


def _pct_change(old: float, new: float) -> float | None:
    if old == 0:
        return None
    return (new - old) / abs(old)


def _cv(values: list[float]) -> float | None:
    if len(values) < 2:
        return None
    mean = sum(values) / len(values)
    if mean == 0:
        return None
    variance = sum((v - mean) ** 2 for v in values) / len(values)
    return float(variance**0.5 / abs(mean))


def _friendly(column: str) -> str:
    return column.replace("_", " ").strip()


def _dimension(column: str) -> str:
    name = column.lower()
    for suffix in ("_name", "_code", "_desc", "_label"):
        if name.endswith(suffix):
            name = name[: -len(suffix)]
    return name.replace("_", " ").strip() or "item"


def _plural(word: str) -> str:
    if word.endswith("y") and not word.endswith(("ay", "ey", "oy", "uy")):
        return word[:-1] + "ies"
    if word.endswith(("s", "x", "ch", "sh")):
        return word + "es"
    return word + "s"


def _fmt(value: float, kind: MeasureKind, *, scale_percent: bool = False) -> str:
    if kind == "percent":
        return f"{value * 100 if scale_percent else value:.1f}%"
    prefix = "\u20b9" if kind == "currency" else ""
    size = abs(value)
    if size >= 10_000_000:
        text = f"{value / 10_000_000:.2f} Cr"
    elif size >= 100_000:
        text = f"{value / 100_000:.2f} L"
    elif size >= 1000:
        text = f"{value:,.0f}"
    elif float(value).is_integer():
        text = f"{int(value)}"
    else:
        text = f"{value:.2f}"
    return f"-{prefix}{text.lstrip('-')}" if value < 0 else f"{prefix}{text}"


def _seed(columns: list[str], rows: list[dict[str, Any]]) -> int:
    basis = "|".join(columns) + "|" + str(rows[0].get(columns[0]))
    return int(hashlib.sha256(basis.encode()).hexdigest()[:8], 16)


def _pick(options: list[str], seed: int) -> str:
    return options[seed % len(options)]
