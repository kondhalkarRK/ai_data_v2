"""Pure scoring for the Data Reliability Center.

Rule score: the pass rate (percent of checked units that pass); freshness rules score 100
within SLA, falling linearly to 0 at three times the SLA.
Dimension score: severity-weighted mean of its rule scores (critical 4, high 3, medium 2, low 1).
Trust score: dimension-weighted mean of the measured dimensions (weights renormalised when a
dimension has no runnable rules). Rules that are disabled, errored or had nothing to check
are excluded rather than scored as zero.
"""

from __future__ import annotations

import statistics
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import date, timedelta

from app.services.reliability.model import (
    DIMENSION_INFO,
    DIMENSIONS,
    SEVERITY_WEIGHT,
    Dimension,
    RuleResult,
    RuleSpec,
)

SCORED = frozenset({"passing", "failing"})


@dataclass(slots=True)
class DimensionScore:
    key: Dimension
    score: float | None
    weight: float
    rules: int = 0
    passing: int = 0
    failing: int = 0
    errored: int = 0


@dataclass(slots=True)
class TrendPoint:
    day: date
    score: float | None
    dimensions: dict[str, float | None] = field(default_factory=dict)
    failing_rules: list[str] = field(default_factory=list)


def _weighted(items: Iterable[tuple[float, float]]) -> float | None:
    pairs = [(s, w) for s, w in items if w > 0]
    total = sum(w for _, w in pairs)
    if not pairs or total <= 0:
        return None
    return round(sum(s * w for s, w in pairs) / total, 2)


def scored(
    rules: Iterable[RuleSpec], results: dict[str, RuleResult]
) -> list[tuple[RuleSpec, RuleResult]]:
    out = []
    for rule in rules:
        result = results.get(rule.id)
        if (
            rule.enabled
            and result is not None
            and result.status in SCORED
            and result.score is not None
        ):
            out.append((rule, result))
    return out


def dimension_scores(
    rules: list[RuleSpec], results: dict[str, RuleResult]
) -> dict[Dimension, DimensionScore]:
    out: dict[Dimension, DimensionScore] = {}
    for key in DIMENSIONS:
        members = [r for r in rules if r.dimension == key and r.enabled]
        pairs = scored(members, results)
        out[key] = DimensionScore(
            key=key,
            score=_weighted(
                (res.score or 0.0, SEVERITY_WEIGHT[rule.severity]) for rule, res in pairs
            ),
            weight=DIMENSION_INFO[key].weight,
            rules=len(members),
            passing=sum(1 for _, res in pairs if res.status == "passing"),
            failing=sum(1 for _, res in pairs if res.status == "failing"),
            errored=sum(
                1 for r in members if (results.get(r.id) and results[r.id].status == "error")
            ),
        )
    return out


def overall_score(dimensions: dict[Dimension, DimensionScore]) -> float | None:
    score = _weighted((d.score, d.weight) for d in dimensions.values() if d.score is not None)
    return round(score, 1) if score is not None else None


def effective_weights(dimensions: dict[Dimension, DimensionScore]) -> dict[Dimension, float]:
    """Share of the trust score each measured dimension carries (sums to 100)."""
    measured = {k: d.weight for k, d in dimensions.items() if d.score is not None}
    total = sum(measured.values())
    return {k: round(100 * w / total, 1) for k, w in measured.items()} if total else {}


def dataset_score(rules: list[RuleSpec], results: dict[str, RuleResult]) -> float | None:
    """Datasets are scored like a dimension: severity-weighted mean of their rule scores."""
    value = _weighted(
        (res.score or 0.0, SEVERITY_WEIGHT[rule.severity]) for rule, res in scored(rules, results)
    )
    return round(value, 1) if value is not None else None


def _day_score(result: RuleResult, day: date) -> float | None:
    if not result.trend:
        return None
    monthly = all(key.day == 1 for key in result.trend)
    entry = result.trend.get(day.replace(day=1) if monthly else day)
    if entry is None:
        return None
    total, failed = entry
    if total <= 0:
        return None
    return 100.0 * (1 - min(failed, total) / total)


def record_date_trend(
    rules: list[RuleSpec],
    results: dict[str, RuleResult],
    *,
    end: date,
    days: int = 90,
) -> list[TrendPoint]:
    """Trust score by business date.

    Rules with per-period results (row checks on daily datasets, volume and forecast checks)
    contribute their result for that day or month; every other rule contributes its latest
    result, so the series moves only where the data itself shows a change.
    """
    pairs = scored(rules, results)
    if not pairs or not any(res.trend for _, res in pairs):
        return []
    points: list[TrendPoint] = []
    for offset in range(days - 1, -1, -1):
        day = end - timedelta(days=offset)
        dims: dict[str, float | None] = {}
        failing: list[str] = []
        for key in DIMENSIONS:
            values = []
            for rule, res in pairs:
                if rule.dimension != key:
                    continue
                value = _day_score(res, day)
                if value is not None and value < rule.threshold:
                    failing.append(rule.id)
                values.append(
                    (res.score if value is None else value, SEVERITY_WEIGHT[rule.severity])
                )
            dims[key] = _weighted((s or 0.0, w) for s, w in values)
        score = _weighted(
            (value, DIMENSION_INFO[key].weight)
            for key in DIMENSIONS
            if (value := dims.get(key)) is not None
        )
        points.append(
            TrendPoint(day, round(score, 1) if score is not None else None, dims, failing)
        )
    return points


def quality_drops(points: list[TrendPoint], *, min_drop: float = 0.5) -> list[TrendPoint]:
    """Days noticeably below the period's typical score."""
    values = [p.score for p in points if p.score is not None]
    if len(values) < 7:
        return []
    median = statistics.median(values)
    spread = statistics.pstdev(values)
    floor = median - max(min_drop, 2 * spread)
    return [p for p in points if p.score is not None and p.score < floor]


def window_delta(values: list[float | None], window: int = 7) -> float | None:
    """Mean of the last ``window`` values minus the mean of the ``window`` before them."""
    clean = [v for v in values if v is not None]
    if len(clean) < window * 2:
        return None
    recent = clean[-window:]
    prior = clean[-2 * window : -window]
    return round(statistics.fmean(recent) - statistics.fmean(prior), 2)


def format_inr(value: float | None) -> str:
    if value is None:
        return "INR 0"
    amount = abs(value)
    if amount >= 1e7:
        return f"\u20b9{amount / 1e7:,.2f} Cr"
    if amount >= 1e5:
        return f"\u20b9{amount / 1e5:,.1f} L"
    return f"\u20b9{amount:,.0f}"


def format_hours(value: float | None) -> str:
    if value is None:
        return "unknown"
    return f"{value:.0f} h" if value < 48 else f"{value / 24:.1f} days"


def impact_text(rule: RuleSpec, result: RuleResult) -> str:
    """Business-language impact for a failing rule."""
    template = rule.impact or "{failed} {unit} failed this check."
    gap = max(0.0, rule.threshold - (result.pass_rate or 0.0))
    lag_over = (result.lag_hours or 0.0) - (rule.max_age_hours or 0.0)
    values = {
        "failed": f"{result.failed:,}",
        "total": f"{result.total:,}",
        "unit": rule.unit,
        "value": format_inr(result.value_at_risk),
        "gap": f"{gap:.1f}",
        "threshold": f"{rule.threshold:g}",
        "lag": format_hours(max(lag_over, 0.0)),
        "sla": format_hours(rule.max_age_hours),
    }
    try:
        return template.format(**values)
    except (KeyError, IndexError, ValueError):
        return template
