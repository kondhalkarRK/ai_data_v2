"""Realistic Indian automotive dataset generator (pure Python, deterministic).

Pipeline
--------
1. Calendar: daily demand weights (weekday, national + regional festivals, macro shocks).
2. Demand: monthly units per carline = model volume curve x lifecycle x powertrain mix
   x calendar, calibrated to national market size, scaled to the requested row count.
3. Network: brand-exclusive dealers (Nexa / Arena for Maruti), graded by city tier,
   with openings, closures and salesperson rosters (hires, exits, ramp-up).
4. Orders: each order picks a dealer (brand x zone x tier x segment x regional festival),
   a delivery day, an active salesperson, a colour, a quantity and a price.
5. Plans: forecasts (seasonal naive + trend, launch plans) and FY targets (last-12-month
   run-rate x ambition + launches - discontinued models), both from generated history.

``scripts/generate_india_auto_dataset.py`` writes CSVs; ``load_india_auto_dataset.py``
COPYs them into PostgreSQL.
"""

from __future__ import annotations

import bisect
import csv
import json
import math
import random
import re
import time
from array import array
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from datetime import date, timedelta
from itertools import pairwise
from pathlib import Path
from typing import Any, TextIO

from app.analytics import india_auto_market as mk

DEFAULT_ROWS = 2_100_000
DEFAULT_SEED = 20260930
FAR_FUTURE = date(9999, 12, 31)

TABLE_COLUMNS: dict[str, tuple[str, ...]] = {
    "dim_region": ("region_id", "region_name", "city", "state_code", "country"),
    "dim_carline": (
        "carline_id",
        "carline_name",
        "model",
        "make",
        "car_type",
        "engine_capacity",
        "engine_type",
    ),
    "dim_color": ("colour_id", "colour_name", "rcg_combination", "patent_number"),
    "dim_salesman": ("sales_person_id", "first_name", "last_name", "email", "corp_id", "active"),
    "dim_dealer": (
        "dealer_id",
        "dealer_code",
        "dealer_name",
        "region_id",
        "city",
        "dealer_grade",
        "active",
    ),
    "dim_targets": ("target_id", "year_month", "make", "target_units", "target_revenue"),
    # total_sales is a generated column: never part of the load.
    "fact_sales": (
        "order_id",
        "carline_id",
        "colour_id",
        "sales_person_id",
        "region_id",
        "dealer_id",
        "sales_date",
        "order_qty",
        "price_per_unit",
    ),
    "fact_forecast_monthly": (
        "sales_month",
        "carline_id",
        "region_id",
        "forecast_revenue",
        "forecast_units",
    ),
}
LOAD_ORDER = tuple(TABLE_COLUMNS)

_DOW = (0.9, 0.85, 0.95, 0.95, 1.0, 1.25, 1.3)  # Monday .. Sunday
_EV_ONLY_NAMES = {"Creta": "Creta Electric", "C3": "eC3"}


# --------------------------------------------------------------------------- helpers


def month_index(value: date) -> int:
    return (value.year - mk.DATA_START.year) * 12 + value.month - 1


def month_first(index: int) -> date:
    return date(mk.DATA_START.year + index // 12, index % 12 + 1, 1)


def month_last(index: int) -> date:
    return month_first(index + 1) - timedelta(days=1)


def _iso(value: str) -> date:
    return date.fromisoformat(value)


def _interp_year(points: dict[int, float], year: int, month: int) -> float:
    """Linear interpolation between mid-year anchors; flat outside the anchors."""
    t = year + (month - 0.5) / 12.0
    keys = sorted(points)
    if t <= keys[0] + 0.5:
        return points[keys[0]]
    if t >= keys[-1] + 0.5:
        return points[keys[-1]]
    for left, right in pairwise(keys):
        if left + 0.5 <= t <= right + 0.5:
            frac = (t - left - 0.5) / (right - left)
            return points[left] + (points[right] - points[left]) * frac
    return points[keys[-1]]


def _share(value: float | dict[int, float], year: int, month: int) -> float:
    return value if isinstance(value, float | int) else _interp_year(value, year, month)


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", text.casefold())


def _in_reach(city: mk.City, reach: int) -> bool:
    if reach == 3:
        return True
    if reach == 2:
        return city.tier <= 2
    return city.tier == 1 or (city.tier == 2 and city.weight >= 1.4)


def _poisson(rng: random.Random, lam: float) -> int:
    if lam <= 0:
        return 0
    if lam < 30:
        limit, k, p = math.exp(-lam), 0, 1.0
        while True:
            p *= rng.random()
            if p <= limit:
                return k
            k += 1
    return max(0, round(rng.gauss(lam, math.sqrt(lam))))


def _cumulative(weights: Iterable[float]) -> list[float]:
    out: list[float] = []
    total = 0.0
    for weight in weights:
        total += weight
        out.append(total)
    return out


def _pick(rng: random.Random, cum: list[float]) -> int:
    return bisect.bisect_right(cum, rng.random() * cum[-1])


# --------------------------------------------------------------------------- rows


@dataclass(slots=True)
class Carline:
    carline_id: int
    spec: mk.ModelSpec
    name: str
    engine_type: str
    capacity: float | None
    variants: list[mk.Variant]
    group: str
    small_car: bool
    fleet: float
    introduced: date = mk.DATA_START


def build_carlines() -> list[Carline]:
    """One carline per model x powertrain x displacement, in catalogue order."""
    carlines: list[Carline] = []
    for spec in mk.MODELS:
        grouped: dict[tuple[str, float | None], list[mk.Variant]] = {}
        for variant in spec.variants:
            grouped.setdefault((variant.engine_type, variant.capacity), []).append(variant)
        all_electric = all(v.engine_type == "Electric" for v in spec.variants)
        for (engine, capacity), variants in grouped.items():
            if engine == "Electric":
                name = (
                    spec.model
                    if all_electric
                    else _EV_ONLY_NAMES.get(spec.model, f"{spec.model} EV")
                )
                group = "ev"
            else:
                name = f"{spec.model} {capacity:.1f} {engine}"
                group = mk.SEGMENT_GROUP[spec.car_type]
            small = spec.car_type in mk.SMALL_CAR_TYPES and (
                (engine in {"Petrol", "Hybrid"} and (capacity or 0) <= 1.2)
                or (engine == "Diesel" and (capacity or 0) <= 1.5)
            )
            fleet = 0.25 if spec.model == "Tigor" and engine == "Electric" else spec.fleet
            starts = [mk.month_start(v.start) if v.start else spec.launch for v in variants]
            carlines.append(
                Carline(
                    carline_id=len(carlines) + 1,
                    spec=spec,
                    name=name,
                    engine_type=engine,
                    capacity=capacity,
                    variants=variants,
                    group=group,
                    small_car=small,
                    fleet=fleet,
                    introduced=max(min(starts), mk.DATA_START),
                )
            )
    return carlines


def carline_on_sale_until(carline: Carline) -> date | None:
    """Last day the carline can be sold, or None while it is still on sale."""
    ends = [mk.month_end(v.end) if v.end else None for v in carline.variants]
    variant_until = None if any(end is None for end in ends) else max(e for e in ends if e)
    last_window = carline.spec.windows[-1][1]
    window_until = mk.month_end(last_window) if last_window else None
    candidates = [d for d in (variant_until, window_until) if d]
    return min(candidates) if candidates else None


@dataclass(slots=True)
class Dealer:
    dealer_id: int
    code: str
    name: str
    make: str
    channel: str | None
    city: mk.City
    region_id: int
    grade: str
    opened: date
    closed: date | None
    size: float
    share_divisor: int = 1


@dataclass(slots=True)
class Salesperson:
    sales_person_id: int
    first_name: str
    last_name: str
    email: str
    corp_id: str
    dealer_id: int
    start: date
    end: date | None
    weight: float


@dataclass
class GeneratorConfig:
    rows: int = DEFAULT_ROWS
    seed: int = DEFAULT_SEED
    end_date: date = field(default_factory=date.today)
    split_date: date | None = None
    forecast_horizon: int = 6
    progress: Callable[[str], None] | None = None


@dataclass
class GenerationReport:
    counts: dict[str, int] = field(default_factory=dict)
    increment_counts: dict[str, int] = field(default_factory=dict)
    seconds: float = 0.0
    yearly_make_units: dict[int, dict[str, float]] = field(default_factory=dict)
    yearly_ev_units: dict[int, float] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "counts": self.counts,
            "increment_counts": self.increment_counts,
            "seconds": round(self.seconds, 1),
            "yearly_make_share_pct": {
                str(year): {
                    make: round(100 * units / max(sum(makes.values()), 1), 2)
                    for make, units in sorted(makes.items(), key=lambda item: -item[1])
                }
                for year, makes in sorted(self.yearly_make_units.items())
            },
            "yearly_ev_share_pct": {
                str(year): round(
                    100 * ev / max(sum(self.yearly_make_units.get(year, {}).values()), 1), 2
                )
                for year, ev in sorted(self.yearly_ev_units.items())
            },
        }


# --------------------------------------------------------------------------- writer


class _SplitWriter:
    """CSV writers for the base load and (optionally) the post-split increment."""

    def __init__(self, out_dir: Path, split: bool) -> None:
        self.out_dir = out_dir
        self.split = split
        self._files: list[TextIO] = []
        self._writers: dict[tuple[str, bool], Any] = {}
        self.counts: dict[tuple[str, bool], int] = {}
        out_dir.mkdir(parents=True, exist_ok=True)
        if split:
            (out_dir / "increment").mkdir(parents=True, exist_ok=True)

    def _writer(self, table: str, increment: bool) -> Any:
        key = (table, increment)
        if key not in self._writers:
            folder = self.out_dir / "increment" if increment else self.out_dir
            handle = (folder / f"{table}.csv").open("w", newline="", encoding="utf-8")
            self._files.append(handle)
            writer = csv.writer(handle, lineterminator="\n")
            writer.writerow(TABLE_COLUMNS[table])
            self._writers[key] = writer
            self.counts[key] = 0
        return self._writers[key]

    def write(self, table: str, row: tuple[Any, ...], increment: bool = False) -> None:
        increment = increment and self.split
        self._writer(table, increment).writerow(row)
        self.counts[(table, increment)] += 1

    def ensure(self, table: str) -> None:
        self._writer(table, False)
        if self.split:
            self._writer(table, True)

    def close(self) -> None:
        for handle in self._files:
            handle.close()


# --------------------------------------------------------------------------- generator


class IndiaAutoDatasetGenerator:
    def __init__(self, config: GeneratorConfig) -> None:
        self.config = config
        self.rng = random.Random(config.seed)
        self.end = config.end_date
        if self.end < date(2015, 6, 30):
            raise ValueError("end_date must be after 2015-06-30")
        self.split = config.split_date
        self.hist_months = month_index(self.end) + 1
        fy_end = date(self.end.year + (self.end.month >= 4), 3, 1)
        self.total_months = max(month_index(fy_end) + 1, self.hist_months + config.forecast_horizon)
        self.calibration_months = max(self.total_months, (self.end.year - 2014) * 12)
        self._log = config.progress or (lambda _msg: None)

    # ------------------------------------------------------------------ calendar

    def _build_calendar(self) -> None:
        start = mk.DATA_START
        last = month_last(self.calibration_months - 1)
        n_days = (last - start).days + 1
        self.n_days = n_days
        base = [_DOW[(start + timedelta(days=i)).weekday()] for i in range(n_days)]
        discount = [0.0] * n_days
        macro = [1.0] * n_days

        def idx(day: date) -> int | None:
            offset = (day - start).days
            return offset if 0 <= offset < n_days else None

        def scale(day: date, factor: float, disc: float = 0.0) -> None:
            i = idx(day)
            if i is not None:
                base[i] *= factor
                discount[i] = max(discount[i], disc)

        for year in range(start.year, last.year + 1):
            for day_no in range(1, 32):
                for month, factor, disc in (
                    (12, 0.85 if day_no <= 14 else 1.08, 0.0 if day_no <= 14 else 0.035),
                    (1, 1.1 if day_no <= 7 else 1.0, 0.0),
                    (3, 1.3 if day_no >= 20 else 1.0, 0.015 if day_no >= 20 else 0.0),
                    (6, 0.95, 0.0),
                    (7, 0.92, 0.0),
                    (8, 0.92 if day_no <= 20 else 1.0, 0.0),
                ):
                    try:
                        scale(date(year, month, day_no), factor, disc)
                    except ValueError:
                        continue
            for month in range(1, 13):
                month_end = month_last(month_index(date(year, month, 1)))
                for back in range(3):
                    scale(month_end - timedelta(days=back), 1.12)
            if year in mk.DUSSEHRA:
                dussehra = _iso(mk.DUSSEHRA[year])
                navratri = dussehra - timedelta(days=9)
                for back in range(1, 17):
                    scale(navratri - timedelta(days=back), 0.62)  # Pitru Paksha
                for offset in range(9):
                    scale(navratri + timedelta(days=offset), 1.35, 0.015)
                scale(dussehra, 2.6, 0.015)
            if year in mk.DIWALI:
                diwali = _iso(mk.DIWALI[year])
                for back in range(3, 13):
                    scale(diwali - timedelta(days=back), 1.45, 0.015)
                scale(diwali - timedelta(days=2), 3.2, 0.02)  # Dhanteras
                scale(diwali - timedelta(days=1), 1.6, 0.015)
                scale(diwali, 0.8)
                for ahead in range(1, 5):
                    scale(diwali + timedelta(days=ahead), 0.55)
            if year in mk.AKSHAYA_TRITIYA:
                scale(_iso(mk.AKSHAYA_TRITIYA[year]), 1.7)

        for event in mk.MACRO_EVENTS:
            day = _iso(event.start)
            while day <= _iso(event.end):
                i = idx(day)
                if i is not None:
                    macro[i] *= event.factor
                day += timedelta(days=1)

        regional: dict[str, dict[int, float]] = {}
        for _name, dates, states, peak, window in mk.REGIONAL_FESTIVALS:
            for iso in dates.values():
                festival = _iso(iso)
                for back in range(window + 1):
                    i = idx(festival - timedelta(days=back))
                    if i is None:
                        continue
                    factor = peak if back == 0 else 1 + (peak - 1) / 2
                    for state in states:
                        regional.setdefault(state, {})[i] = factor
        for _name, month, day_no, states, peak in mk.FIXED_REGIONAL_FESTIVALS:
            for year in range(start.year, last.year + 1):
                for delta in (-1, 0, 1):
                    i = idx(date(year, month, day_no) + timedelta(days=delta))
                    if i is None:
                        continue
                    for state in states:
                        regional.setdefault(state, {})[i] = peak if delta == 0 else 1.25

        self.day_base = base
        self.day_weight = [b * m for b, m in zip(base, macro, strict=True)]
        self.day_discount = discount
        self.regional = regional

        year_norm: dict[int, float] = {}
        for i, weight in enumerate(base):
            year = (start + timedelta(days=i)).year
            year_norm[year] = year_norm.get(year, 0.0) + weight
        self.month_first_day = [
            (month_first(m) - start).days for m in range(self.calibration_months + 1)
        ]
        self.month_factor: list[float] = []
        for m in range(self.calibration_months):
            lo, hi = self.month_first_day[m], self.month_first_day[m + 1]
            year = month_first(m).year
            self.month_factor.append(sum(self.day_weight[lo:hi]) / (year_norm[year] / 12.0))
        end_offset = (self.end - start).days
        last_m = self.hist_months - 1
        lo, hi = self.month_first_day[last_m], self.month_first_day[last_m + 1]
        full = sum(self.day_weight[lo:hi]) or 1.0
        self.last_month_fraction = sum(self.day_weight[lo : end_offset + 1]) / full
        self._state_month_cache: dict[tuple[str, int], tuple[list[float], float]] = {}

    def _state_month(self, state: str, m: int) -> tuple[list[float], float]:
        """Cumulative day weights for one state and month, plus the month factor."""
        key = (state, m)
        cached = self._state_month_cache.get(key)
        if cached is not None:
            return cached
        lo, hi = self.month_first_day[m], self.month_first_day[m + 1]
        boosts = self.regional.get(state, {})
        weights = [self.day_weight[i] * boosts.get(i, 1.0) for i in range(lo, hi)]
        national = sum(self.day_weight[lo:hi])
        factor = sum(weights) / national if national else 0.0
        result = (_cumulative(weights), factor)
        self._state_month_cache[key] = result
        return result

    # ------------------------------------------------------------------ catalogue

    def _build_carlines(self) -> None:
        self.carlines = build_carlines()

    def _window_state(self, spec: mk.ModelSpec, m: int) -> tuple[int, int, int] | None:
        """(window number, months since launch, months until runout end) or None."""
        first = month_first(m)
        for number, (start, end) in enumerate(spec.windows):
            lo = mk.month_start(start) if start else date(1900, 1, 1)
            hi = mk.month_end(end) if end else FAR_FUTURE
            if lo <= first <= hi:
                age = m - month_index(lo) if start else 999
                left = month_index(hi) - m if end else 999
                return number, age, left
        return None

    def _model_volume(self, spec: mk.ModelSpec, window: int, m: int) -> float:
        first = month_first(m)
        start, end = spec.windows[window]
        lo_year = mk.month_start(start).year if start else 0
        hi_year = mk.month_end(end).year if end else 9999
        points = {y: v for y, v in spec.volume.items() if lo_year <= y <= hi_year}
        if not points:
            return 0.0
        return _interp_year(points, first.year, first.month)

    @staticmethod
    def _lifecycle(age: int, left: int) -> float:
        factor = 1.0
        if 0 <= age <= 5:
            factor = (1.3, 1.25, 1.1, 0.92, 0.92, 0.92)[age]
        if 0 <= left <= 2:
            factor *= (0.45, 0.65, 0.8)[left]
        return factor

    def _variant_shares(self, carline: Carline, m: int) -> float:
        """This carline's share of its model's volume in month ``m``."""
        first = month_first(m)
        spec = carline.spec
        total = 0.0
        mine = 0.0
        for variant in spec.variants:
            lo = mk.month_start(variant.start) if variant.start else date(1900, 1, 1)
            hi = mk.month_end(variant.end) if variant.end else FAR_FUTURE
            if not lo <= first <= hi:
                continue
            weight = _share(variant.share, first.year, first.month)
            total += weight
            if variant in carline.variants:
                mine += weight
        return mine / total if total else 0.0

    def _active_variant(self, carline: Carline, m: int) -> mk.Variant | None:
        first = month_first(m)
        for variant in carline.variants:
            lo = mk.month_start(variant.start) if variant.start else date(1900, 1, 1)
            hi = mk.month_end(variant.end) if variant.end else FAR_FUTURE
            if lo <= first <= hi:
                return variant
        return None

    def _build_demand(self) -> None:
        months = self.calibration_months
        raw: list[list[float]] = []
        for carline in self.carlines:
            series = [0.0] * months
            for m in range(months):
                state = self._window_state(carline.spec, m)
                if state is None:
                    continue
                window, age, left = state
                share = self._variant_shares(carline, m)
                if share <= 0:
                    continue
                series[m] = (
                    self._model_volume(carline.spec, window, m)
                    * self._lifecycle(age, left)
                    * share
                    * self.month_factor[m]
                )
            raw.append(series)

        year_raw: dict[int, float] = {}
        full_years = {month_first(m).year for m in range(months) if month_first(m).month == 12}
        for series in raw:
            for m, value in enumerate(series):
                year = month_first(m).year
                if year in full_years:
                    year_raw[year] = year_raw.get(year, 0.0) + value
        anchors = {
            year: mk.MARKET_UNITS_MILLION.get(year, mk.MARKET_UNITS_MILLION[2026]) / total
            for year, total in year_raw.items()
            if total > 0
        }
        mean_anchor = sum(anchors.values()) / len(anchors)
        anchors = {year: value / mean_anchor for year, value in anchors.items()}
        calib = [
            _interp_year(anchors, month_first(m).year, month_first(m).month) for m in range(months)
        ]
        self.expected = [[value * calib[m] for m, value in enumerate(series)] for series in raw]

        expected_orders = 0.0
        for carline, series in zip(self.carlines, self.expected, strict=True):
            mean_qty = self._mean_qty(carline)
            for m in range(self.hist_months):
                fraction = self.last_month_fraction if m == self.hist_months - 1 else 1.0
                expected_orders += series[m] * fraction / mean_qty
        self.scale = self.config.rows / expected_orders if expected_orders else 0.0

    @staticmethod
    def _mean_qty(carline: Carline) -> float:
        return 1.0 + carline.fleet * 1.13 * 4.5 + 0.006 * 1.33

    # ------------------------------------------------------------------ network

    def _build_network(self) -> None:
        rng = self.rng
        region_ids = {city.name: i + 1 for i, city in enumerate(mk.CITIES)}
        dealers: list[Dealer] = []
        used_names: set[str] = set()
        codes: dict[tuple[str, str], int] = {}
        for make in mk.MAKES:
            entry = mk.make_entry(make)
            reach = mk.MAKE_REACH[make]
            prefs = mk.ZONE_PREFERENCE[make]
            eligible = [city for city in mk.CITIES if _in_reach(city, reach)]
            weights = {city.name: city.weight * prefs[city.zone] for city in eligible}
            total = sum(weights.values())
            target = mk.DEALER_TARGETS[make]
            quota = {name: target * w / total for name, w in weights.items()}
            counts = {name: int(q) for name, q in quota.items()}
            tiers = {city.name: city.tier for city in eligible}
            for name, q in quota.items():
                everywhere = make == mk.MS or (make in {mk.HY, mk.TA, mk.MA} and tiers[name] <= 2)
                if counts[name] == 0 and (everywhere or q >= 0.5):
                    counts[name] = 1
            remaining = target - sum(counts.values())
            for name, _q in sorted(quota.items(), key=lambda item: -(item[1] % 1)):
                if remaining <= 0:
                    break
                counts[name] += 1
                remaining -= 1
            ranked = sorted(eligible, key=lambda city: -city.weight)
            anchor_city = ranked[0].name
            for city in ranked:
                n = counts.get(city.name, 0)
                if n <= 0:
                    continue
                channels: list[str | None]
                if make == mk.MS:
                    nexa = 0 if city.tier == 3 and n < 2 else max(1, round(n * 0.38))
                    nexa = min(nexa, n - 1) if n > 1 else 0
                    channels = [*(["Arena"] * (n - nexa)), *(["Nexa"] * nexa)]
                else:
                    channels = [None] * n
                arena_seen = False
                nexa_seen = False
                for channel in channels:
                    first_outlet = (channel != "Nexa" and not arena_seen) or (
                        channel == "Nexa" and not nexa_seen
                    )
                    if channel == "Nexa":
                        nexa_seen = True
                    else:
                        arena_seen = True
                    opened = self._open_date(make, entry, city, channel, first_outlet)
                    if city.name == anchor_city and first_outlet:
                        launch = mk.NEXA_LAUNCH if channel == "Nexa" else entry
                        opened = min(opened, launch - timedelta(days=20))
                    if opened > self.end:
                        continue
                    closed = None
                    if (
                        not (city.name == anchor_city and first_outlet)
                        and rng.random() < mk.DEALER_CLOSURE_RATE[make]
                    ):
                        lo = max(opened + timedelta(days=730), date(2016, 6, 1))
                        hi = min(date(2025, 12, 31), self.end - timedelta(days=30))
                        if make in {mk.NI, mk.HO}:
                            lo = max(lo, date(2019, 6, 1))
                        if lo < hi:
                            closed = lo + timedelta(days=rng.randrange((hi - lo).days))
                    grade = self._grade(city.tier)
                    prefix_pool = mk.DEALER_PREFIXES[city.zone] + mk.DEALER_PREFIXES["any"]
                    brand = mk.DEALER_BRAND_WORD[make]
                    if make == mk.MS:
                        brand = "Nexa" if channel == "Nexa" else "Maruti Arena"
                    name = f"{rng.choice(prefix_pool)} {brand}"
                    if name in used_names:
                        name = f"{name} {city.name}"
                    suffix = 2
                    base_name = name
                    while name in used_names:
                        name = f"{base_name} {suffix}"
                        suffix += 1
                    used_names.add(name)
                    code_prefix = mk.MAKE_CODES[make] + ("N" if channel == "Nexa" else "")
                    seq_key = (code_prefix, city.state)
                    codes[seq_key] = codes.get(seq_key, 0) + 1
                    dealers.append(
                        Dealer(
                            dealer_id=0,
                            code=f"{code_prefix}-{city.state}-{codes[seq_key]:04d}",
                            name=name,
                            make=make,
                            channel=channel,
                            city=city,
                            region_id=region_ids[city.name],
                            grade=grade,
                            opened=opened,
                            closed=closed,
                            size=math.exp(rng.gauss(0.0, 0.3)),
                        )
                    )
        per_city: dict[tuple[str, str | None, str], int] = {}
        for dealer in dealers:
            key = (dealer.make, dealer.channel, dealer.city.name)
            per_city[key] = per_city.get(key, 0) + 1
        for number, dealer in enumerate(dealers, start=1):
            dealer.dealer_id = number
            dealer.share_divisor = per_city[(dealer.make, dealer.channel, dealer.city.name)]
        self.dealers = dealers
        self.region_ids = region_ids
        self.dealers_by_key: dict[tuple[str, str | None], list[Dealer]] = {}
        for dealer in dealers:
            self.dealers_by_key.setdefault((dealer.make, dealer.channel), []).append(dealer)
        self._build_salespeople()

    def _open_date(
        self, make: str, entry: date, city: mk.City, channel: str | None, first: bool
    ) -> date:
        rng = self.rng

        def between(lo: date, hi: date) -> date:
            if hi <= lo:
                return lo
            return lo + timedelta(days=rng.randrange((hi - lo).days))

        city_entry = mk.month_start(city.entry) if city.entry else None
        latest = min(date(2025, 12, 31), self.end - timedelta(days=45))
        if channel == "Nexa":
            windows = {
                1: (mk.NEXA_LAUNCH, date(2015, 12, 31)),
                2: (date(2015, 10, 1), date(2017, 6, 30)),
            }
            lo, hi = windows.get(city.tier, (date(2018, 1, 1), date(2020, 12, 31)))
            opened = between(lo, hi) if first else between(date(2016, 1, 1), latest)
        elif entry > mk.DATA_START:
            if first:
                lead = {
                    1: (entry - timedelta(days=45), entry),
                    2: (entry, entry + timedelta(days=540)),
                }
                lo, hi = lead.get(
                    city.tier, (entry + timedelta(days=180), entry + timedelta(days=900))
                )
                opened = between(lo, hi)
            else:
                opened = between(entry + timedelta(days=180), entry + timedelta(days=1460))
        else:
            if first:
                opened = (
                    between(date(2000, 1, 1), date(2014, 12, 31))
                    if rng.random() < 0.9
                    else between(date(2015, 1, 1), date(2019, 12, 31))
                )
            elif make == mk.TA and rng.random() < 0.5:
                opened = between(date(2020, 6, 1), date(2024, 12, 31))
            else:
                opened = (
                    between(date(2000, 1, 1), date(2014, 12, 31))
                    if rng.random() < 0.6
                    else between(date(2015, 1, 1), latest)
                )
        if opened > mk.DATA_START:
            opened = min(opened, latest)
        if city_entry:
            if first:
                opened = city_entry + timedelta(days=rng.randrange(20))
            else:
                opened = max(opened, city_entry + timedelta(days=90 + rng.randrange(200)))
        return opened

    def _grade(self, tier: int) -> str:
        roll = self.rng.random()
        if tier == 1:
            return "A" if roll < 0.85 else "B"
        if tier == 2:
            return "A" if roll < 0.2 else ("B" if roll < 0.9 else "C")
        return "B" if roll < 0.25 else "C"

    def _build_salespeople(self) -> None:
        rng = self.rng
        people: list[Salesperson] = []
        self.roster: dict[int, list[Salesperson]] = {}
        for dealer in self.dealers:
            lo, hi = mk.HEADCOUNT_BY_GRADE[dealer.grade]
            seats = rng.randint(lo, hi)
            zone = dealer.city.zone
            domain = _slug(dealer.name)[:28] + ".in"
            stop = dealer.closed or FAR_FUTURE
            for _seat in range(seats):
                start = dealer.opened
                while start <= min(stop, self.end):
                    years = max(0.3, rng.expovariate(1.0 / mk.MEAN_TENURE_YEARS))
                    end = start + timedelta(days=int(years * 365))
                    finished = end if end < min(stop, self.end) else None
                    if dealer.closed and finished is None:
                        finished = dealer.closed
                    if (finished or FAR_FUTURE) >= mk.DATA_START:
                        pid = len(people) + 1
                        first = rng.choice(mk.FIRST_NAMES[zone])
                        last = rng.choice(mk.LAST_NAMES[zone])
                        person = Salesperson(
                            sales_person_id=pid,
                            first_name=first,
                            last_name=last,
                            email=f"{_slug(first)}.{_slug(last)}.{pid}@{domain}",
                            corp_id=f"{mk.MAKE_CODES[dealer.make]}-{pid:06d}",
                            dealer_id=dealer.dealer_id,
                            start=start,
                            end=finished,
                            weight=math.exp(rng.gauss(0.0, 0.45)),
                        )
                        people.append(person)
                        self.roster.setdefault(dealer.dealer_id, []).append(person)
                    if finished is None or (dealer.closed and finished >= dealer.closed):
                        break
                    start = end + timedelta(days=1)
        self.salespeople = people
        self._roster_month: dict[tuple[int, int], list[Salesperson]] = {}

    # ------------------------------------------------------------------ sampling tables

    def _dealer_table(
        self, m: int, make: str, channel: str | None, group: str
    ) -> tuple[list[Dealer], list[float]] | None:
        key = (m, make, channel, group)
        cached = self._dealer_cache.get(key)
        if cached is not None or key in self._dealer_cache:
            return cached
        first, last = month_first(m), min(month_last(m), self.end)
        year = first.year
        pool: list[Dealer] = []
        weights: list[float] = []
        tiers = mk.TIER_PREFERENCE[group]
        for dealer in self.dealers_by_key.get((make, channel), []):
            lo = max(dealer.opened, first)
            hi = min(dealer.closed or FAR_FUTURE, last)
            if hi < lo:
                continue
            city = dealer.city
            tier_growth = 1.0 + (0.03 if city.tier == 3 else 0.015 if city.tier == 2 else 0.0) * (
                year - 2015
            )
            tier_pref = tiers[city.tier]
            if group == "ev":
                tier_pref *= mk.EV_STATE_PREFERENCE.get(city.state, 0.7)
                if city.tier == 2:
                    tier_pref *= 1 + 0.08 * max(0, year - 2020)
            if group == "rugged" and city.zone in {"North", "Central"}:
                tier_pref *= 1.2
            _cum, state_factor = self._state_month(city.state, m)
            active = ((hi - lo).days + 1) / ((last - first).days + 1)
            weight = (
                city.weight
                * tier_growth
                * mk.ZONE_PREFERENCE[make][city.zone]
                * tier_pref
                * state_factor
                * active
                * dealer.size
                * {"A": 1.35, "B": 1.0, "C": 0.75}[dealer.grade]
                / dealer.share_divisor
            )
            if weight > 0:
                pool.append(dealer)
                weights.append(weight)
        result = (pool, _cumulative(weights)) if pool else None
        self._dealer_cache[key] = result
        return result

    def _colour_table(self, group: str, year: int) -> list[float]:
        key = (group, year)
        cached = self._colour_cache.get(key)
        if cached is None:
            t = min(max((year - 2015) / 11.0, 0.0), 1.0)
            profile = mk.COLOUR_PROFILE[group]
            weights = [
                (c.share_2015 + (c.share_2026 - c.share_2015) * t) * profile.get(c.family, 1.0)
                for c in mk.COLOURS
            ]
            cached = _cumulative(weights)
            self._colour_cache[key] = cached
        return cached

    def _trim_table(self, year: int) -> list[float]:
        t = min(max((year - 2015) / 11.0, 0.0), 1.0)
        start, stop = mk.TRIM_MIX[2015], mk.TRIM_MIX[2026]
        return _cumulative(a + (b - a) * t for a, b in zip(start, stop, strict=True))

    def _base_price(self, carline: Carline, variant: mk.Variant, m: int) -> float:
        first = month_first(m)
        price = variant.price_lakh * 100_000 * _interp_year(mk.PRICE_INDEX, first.year, first.month)
        if carline.engine_type == "Electric":
            price *= _interp_year(mk.EV_PRICE_FACTOR, first.year, first.month)
        else:
            if first < mk.BS6_PHASE2_DATE:
                price /= 1.02
            if carline.engine_type == "Diesel" and first < mk.BS6_DATE:
                price /= 1.07
        for when, factor in carline.spec.price_steps:
            if first >= mk.month_start(when):
                price *= factor
        return price

    def _gst_factor(self, carline: Carline, day: date) -> float:
        if day < mk.GST_CUT_DATE or carline.engine_type == "Electric":
            return 1.0
        return 0.915 if carline.small_car else 0.955

    def _roster_for(self, dealer_id: int, m: int) -> list[Salesperson]:
        key = (dealer_id, m)
        cached = self._roster_month.get(key)
        if cached is None:
            first, last = month_first(m), month_last(m)
            cached = [
                person
                for person in self.roster.get(dealer_id, [])
                if person.start <= last and (person.end or FAR_FUTURE) >= first
            ]
            self._roster_month[key] = cached
        return cached

    # ------------------------------------------------------------------ facts

    def _generate_facts(self, writer: _SplitWriter) -> None:
        rng = self.rng
        n_hist = self.hist_months
        self._dealer_cache: dict[tuple[int, str, str | None, str], Any] = {}
        self._colour_cache: dict[tuple[str, int], list[float]] = {}
        colour_ids = list(range(1, len(mk.COLOURS) + 1))
        fleet_cum = _cumulative(mk.FLEET_COLOURS.get(colour.name, 0.0) for colour in mk.COLOURS)
        trims_ev = mk.EV_TRIM_MULTIPLIERS
        trims = mk.TRIM_MULTIPLIERS
        split = self.split
        start = mk.DATA_START

        self.pair_units: dict[tuple[int, int], array[float]] = {}
        self.pair_revenue: dict[tuple[int, int], array[float]] = {}
        self.carline_units = [array("d", bytes(8 * n_hist)) for _ in self.carlines]
        self.carline_revenue = [array("d", bytes(8 * n_hist)) for _ in self.carlines]
        self.make_units = {make: array("d", bytes(8 * n_hist)) for make in mk.MAKES}
        self.make_revenue = {make: array("d", bytes(8 * n_hist)) for make in mk.MAKES}
        self.make_region_units: dict[tuple[str, int], array[float]] = {}
        self.market_units = array("d", bytes(8 * n_hist))
        report_units: dict[int, dict[str, float]] = {}
        report_ev: dict[int, float] = {}

        order_id = 0
        started = time.perf_counter()
        for m in range(n_hist):
            first = month_first(m)
            year, moy = first.year, first.month
            fraction = self.last_month_fraction if m == n_hist - 1 else 1.0
            trim_cum = self._trim_table(year)
            month_rows: list[tuple[Any, ...]] = []
            for carline, series in zip(self.carlines, self.expected, strict=True):
                expected = series[m] * self.scale * fraction
                if expected <= 0:
                    continue
                n_orders = _poisson(rng, expected / self._mean_qty(carline))
                if n_orders == 0:
                    continue
                spec = carline.spec
                variant = self._active_variant(carline, m)
                if variant is None:
                    continue
                table = self._dealer_table(m, spec.make, spec.channel, carline.group)
                if table is None:
                    continue
                pool, dealer_cum = table
                state = self._window_state(spec, m)
                age, left = (state[1], state[2]) if state else (999, 999)
                base_price = self._base_price(carline, variant, m)
                if 0 <= age <= 2:
                    base_price *= 0.97
                runout = 0.04 if 0 <= left <= 3 else 0.0
                colour_cum = self._colour_table(carline.group, year)
                fleet_p = carline.fleet * (1.8 if moy == 3 else 1.0)
                trim_values = trims_ev if carline.engine_type == "Electric" else trims
                c_idx = carline.carline_id - 1
                variant_start = max(
                    mk.month_start(variant.start) if variant.start else first, first
                )
                for _ in range(n_orders):
                    dealer = pool[_pick(rng, dealer_cum)]
                    day_cum, _factor = self._state_month(dealer.city.state, m)
                    lo_day = max(dealer.opened, variant_start, first).day - 1
                    hi_day = min(dealer.closed or FAR_FUTURE, self.end, month_last(m)).day - 1
                    if hi_day < lo_day:
                        continue
                    floor = day_cum[lo_day - 1] if lo_day > 0 else 0.0
                    ceiling = day_cum[hi_day]
                    if ceiling <= floor:
                        continue
                    offset = bisect.bisect_right(day_cum, floor + rng.random() * (ceiling - floor))
                    offset = min(max(offset, lo_day), hi_day)
                    day = first + timedelta(days=offset)
                    candidates = [
                        p
                        for p in self._roster_for(dealer.dealer_id, m)
                        if p.start <= day and (p.end is None or p.end >= day)
                    ]
                    if not candidates:
                        continue
                    if len(candidates) == 1:
                        person = candidates[0]
                    else:
                        cum = _cumulative(
                            p.weight * (0.5 if (day - p.start).days < 90 else 1.0)
                            for p in candidates
                        )
                        person = candidates[_pick(rng, cum)]
                    roll = rng.random()
                    fleet = roll < fleet_p
                    if fleet:
                        qty = 2 + min(int(rng.expovariate(1 / 3.5)), 23)
                        colour_id = colour_ids[_pick(rng, fleet_cum)]
                        trim = trim_values[0] if rng.random() < 0.8 else trim_values[1]
                    else:
                        qty = (2 if rng.random() < 0.67 else 3) if roll < fleet_p + 0.006 else 1
                        colour_id = colour_ids[_pick(rng, colour_cum)]
                        trim = trim_values[_pick(rng, trim_cum)]
                    day_index = (day - start).days
                    discount = self.day_discount[day_index] + runout + rng.random() * 0.012
                    if fleet:
                        discount += 0.04
                    price = (
                        base_price
                        * self._gst_factor(carline, day)
                        * trim
                        * (1 - discount)
                        * (1 + rng.gauss(0.0, 0.01))
                    )
                    price = max(100.0, round(price / 100.0) * 100.0)
                    month_rows.append(
                        (
                            day,
                            c_idx,
                            colour_id,
                            person.sales_person_id,
                            dealer.region_id,
                            dealer.dealer_id,
                            qty,
                            price,
                        )
                    )
            month_rows.sort(key=lambda row: row[0])
            for day, c_idx, colour_id, sp_id, region_id, dealer_id, qty, price in month_rows:
                order_id += 1
                carline = self.carlines[c_idx]
                writer.write(
                    "fact_sales",
                    (
                        order_id,
                        carline.carline_id,
                        colour_id,
                        sp_id,
                        region_id,
                        dealer_id,
                        day.isoformat(),
                        qty,
                        f"{price:.2f}",
                    ),
                    increment=bool(split and day > split),
                )
                revenue = qty * price
                key = (c_idx, region_id)
                units = self.pair_units.get(key)
                if units is None:
                    units = self.pair_units[key] = array("d", bytes(8 * n_hist))
                    self.pair_revenue[key] = array("d", bytes(8 * n_hist))
                units[m] += qty
                self.pair_revenue[key][m] += revenue
                self.carline_units[c_idx][m] += qty
                self.carline_revenue[c_idx][m] += revenue
                make = carline.spec.make
                self.make_units[make][m] += qty
                self.make_revenue[make][m] += revenue
                mr_key = (make, region_id)
                mr = self.make_region_units.get(mr_key)
                if mr is None:
                    mr = self.make_region_units[mr_key] = array("d", bytes(8 * n_hist))
                mr[m] += qty
                self.market_units[m] += qty
                bucket = report_units.setdefault(year, {})
                bucket[make] = bucket.get(make, 0.0) + qty
                if carline.engine_type == "Electric":
                    report_ev[year] = report_ev.get(year, 0.0) + qty
            if moy == 12 or m == n_hist - 1:
                rate = order_id / max(time.perf_counter() - started, 1e-6)
                self._log(f"  fact_sales through {first:%Y-%m}: {order_id:,} rows ({rate:,.0f}/s)")
        self.report.yearly_make_units = report_units
        self.report.yearly_ev_units = report_ev

    # ------------------------------------------------------------------ plans

    def _last_complete_month(self) -> int:
        return (
            self.hist_months - 1
            if self.end == month_last(self.hist_months - 1)
            else (self.hist_months - 2)
        )

    def _seasonal_profiles(self) -> dict[int, list[float]]:
        """Month-of-year demand index per year, learned only from earlier full years."""
        last_complete = self._last_complete_month()
        yearly: dict[int, list[float]] = {}
        for year in range(mk.DATA_START.year, month_first(last_complete).year + 1):
            base = month_index(date(year, 1, 1))
            if base + 11 > last_complete:
                continue
            values = [self.market_units[base + i] for i in range(12)]
            mean = sum(values) / 12
            if mean > 0:
                yearly[year] = [v / mean for v in values]
        planning = [
            sum(self.month_factor[month_index(date(y, mo, 1))] for y in (2016, 2017, 2018))
            for mo in range(1, 13)
        ]
        mean_plan = sum(planning) / 12
        planning = [value / mean_plan for value in planning]
        profiles: dict[int, list[float]] = {}
        last_year = month_first(self.total_months - 1).year
        for year in range(mk.DATA_START.year, last_year + 1):
            prior = [
                yearly[y]
                for y in range(year - 1, year - 6, -1)
                if y in yearly and y not in {2020, 2021}
            ][:3]
            if not prior:
                profiles[year] = planning
                continue
            profiles[year] = [sum(p[i] for p in prior) / len(prior) for i in range(12)]
        return profiles

    def _generate_forecasts(self, writer: _SplitWriter) -> None:
        rng = self.rng
        profiles = self._seasonal_profiles()
        last_complete = self._last_complete_month()
        horizon_end = min(
            self.hist_months - 1 + self.config.forecast_horizon, self.total_months - 1
        )
        carline_launch = [month_index(c.introduced) for c in self.carlines]
        make_dealer_share: dict[str, dict[int, float]] = {}
        for dealer in self.dealers:
            share = make_dealer_share.setdefault(dealer.make, {})
            share[dealer.region_id] = share.get(dealer.region_id, 0.0) + dealer.city.weight
        pairs_by_carline: dict[int, list[int]] = {}
        for c_idx, region_id in self.pair_units:
            pairs_by_carline.setdefault(c_idx, []).append(region_id)
        increment_regions = self._increment_regions()
        increment_carlines = {
            c.carline_id - 1 for c in self.carlines if self.split and c.introduced > self.split
        }

        for t in range(3, horizon_end + 1):
            month = month_first(t)
            if t <= last_complete + 1:
                history = [h for h in (t - 3, t - 2, t - 1) if h >= 0]
            else:
                history = [last_complete - 2, last_complete - 1, last_complete]
            profile_t = profiles[month.year]
            season_target = profile_t[month.month - 1]
            season_hist = sum(
                profiles[month_first(h).year][month_first(h).month - 1] for h in history
            ) / len(history)
            seasonal = season_target / season_hist if season_hist > 0 else 1.0
            increment_month = bool(self.split and month > self.split)
            for c_idx, carline in enumerate(self.carlines):
                launch = carline_launch[c_idx]
                if t < launch:
                    continue
                if self._window_state(carline.spec, t) is None and t > last_complete:
                    continue
                cu = self.carline_units[c_idx]
                usable = [h for h in history if h >= launch]
                recent = sum(cu[h] for h in usable)
                is_new = t - launch < 3
                if recent <= 0 and not is_new:
                    continue
                prior = sum(cu[h - 12] for h in usable if h - 12 >= 0)
                growth = recent / prior - 1 if prior > 0 else 0.0
                trend = 1 + 0.15 * min(max(growth, -0.3), 0.4)
                cr = self.carline_revenue[c_idx]
                asp = (sum(cr[h] for h in usable) / recent) if recent > 0 else None
                if asp is None:
                    variant = self._active_variant(carline, min(t, self.calibration_months - 1))
                    if variant is None:
                        continue
                    asp = self._base_price(carline, variant, min(t, self.calibration_months - 1))
                months_ahead = t - (sum(usable) / len(usable) if usable else t)
                asp *= 1.004**months_ahead
                regions: dict[int, float] = {}
                if is_new:
                    plan = self.expected[c_idx][min(t, self.calibration_months - 1)] * self.scale
                    shares = make_dealer_share.get(carline.spec.make, {})
                    total_share = sum(shares.values()) or 1.0
                    for region_id, dealer_share in shares.items():
                        regions[region_id] = plan * dealer_share / total_share * 1.1
                for region_id in pairs_by_carline.get(c_idx, []):
                    units = self.pair_units[(c_idx, region_id)]
                    level = sum(units[h] for h in usable) / max(len(usable), 1)
                    if level <= 0:
                        continue
                    regions[region_id] = level * seasonal * trend * 1.03
                for region_id, value in regions.items():
                    forecast = value * math.exp(rng.gauss(0.0, 0.07))
                    if forecast < 0.05:
                        continue
                    writer.write(
                        "fact_forecast_monthly",
                        (
                            month.isoformat(),
                            carline.carline_id,
                            region_id,
                            f"{forecast * asp:.2f}",
                            f"{forecast:.2f}",
                        ),
                        increment=increment_month
                        or c_idx in increment_carlines
                        or region_id in increment_regions,
                    )

    def _generate_targets(self, writer: _SplitWriter) -> None:
        profiles = self._seasonal_profiles()
        last_complete = self._last_complete_month()
        target_id = 0
        carlines_by_make: dict[str, list[int]] = {}
        for c_idx, carline in enumerate(self.carlines):
            carlines_by_make.setdefault(carline.spec.make, []).append(c_idx)
        months = min(self.total_months, self.calibration_months)

        def expected_units(c_idx: int, m: int) -> float:
            return self.expected[c_idx][m] * self.scale if m < self.calibration_months else 0.0

        for make in mk.MAKES:
            entry_m = month_index(mk.make_entry(make))
            plan_cache: dict[int, tuple[float, float, float, list[float]]] = {}
            for m in range(max(entry_m, 0), months):
                month = month_first(m)
                fy = month.year if month.month >= 4 else month.year - 1
                fy_months = [month_index(date(fy, 4, 1)) + i for i in range(12)]
                if fy not in plan_cache:
                    plan_m = month_index(date(fy, 1, 1))
                    plan_m = min(plan_m, last_complete)
                    mu = self.make_units[make]
                    mr = self.make_revenue[make]
                    if plan_m - 11 < 0:
                        plan_cache[fy] = (-1.0, 0.0, 0.0, [])
                    else:
                        last12 = range(plan_m - 11, plan_m + 1)
                        base12 = sum(mu[i] for i in last12)
                        if entry_m > plan_m - 11:
                            base12 *= 12 / max(plan_m - entry_m + 1, 1)  # young brand
                        prev12 = (
                            sum(mu[i] for i in range(plan_m - 23, plan_m - 11))
                            if plan_m - 23 >= 0
                            else 0.0
                        )
                        market_now = sum(self.market_units[i] for i in last12)
                        market_prev = (
                            sum(self.market_units[i] for i in range(plan_m - 23, plan_m - 11))
                            if plan_m - 23 >= 0
                            else 0.0
                        )
                        market_growth = market_now / market_prev - 1 if market_prev else 0.06
                        brand_growth = base12 / prev12 - 1 if prev12 else market_growth
                        ambition = min(
                            max(0.5 * brand_growth + 0.5 * market_growth + 0.03, -0.08), 0.35
                        )
                        fy_start = month_first(fy_months[0])
                        retired = 0.0
                        for c_idx in carlines_by_make.get(make, []):
                            spec = self.carlines[c_idx].spec
                            last_end = spec.windows[-1][1]
                            if last_end and mk.month_end(last_end) < fy_start:
                                retired += sum(self.carline_units[c_idx][i] for i in last12)
                        revenue12 = sum(mr[i] for i in last12)
                        asp = revenue12 / base12 * 1.04 if base12 > 0 else 0.0
                        profile = profiles[fy_start.year]
                        phase = [profile[month_first(i).month - 1] for i in fy_months]
                        total_phase = sum(phase) or 1.0
                        plan_cache[fy] = (
                            max(base12 - retired, 0.0) * (1 + ambition),
                            asp,
                            total_phase,
                            phase,
                        )
                annual, asp, total_phase, phase = plan_cache[fy]
                launches = 0.0
                launch_revenue = 0.0
                for c_idx in carlines_by_make.get(make, []):
                    carline = self.carlines[c_idx]
                    launch_m = month_index(carline.introduced)
                    if annual < 0 or (launch_m >= fy_months[0] and launch_m <= m):
                        units = expected_units(c_idx, m)
                        launches += units
                        variant = self._active_variant(carline, min(m, self.calibration_months - 1))
                        if variant is not None and units > 0:
                            launch_revenue += units * self._base_price(
                                carline, variant, min(m, self.calibration_months - 1)
                            )
                if annual < 0:
                    units = launches * 1.04
                    revenue = launch_revenue * 1.04
                else:
                    share = phase[fy_months.index(m)] / total_phase if m in fy_months else 1 / 12
                    run_rate = annual * share
                    if annual == 0:
                        run_rate = 0.0
                    units = run_rate + launches * 1.1
                    unit_price = asp or (launch_revenue / launches if launches else 0.0)
                    revenue = run_rate * unit_price + launch_revenue * 1.1
                    if fy == 2020 and month >= date(2020, 7, 1):
                        units *= 0.82  # mid-year COVID re-plan
                        revenue *= 0.82
                if units < 1:
                    # Niche brands in small samples still get a (one-unit) plan every month.
                    unit_price = revenue / units if units > 0 else asp
                    units, revenue = 1.0, unit_price
                target_id += 1
                writer.write(
                    "dim_targets",
                    (target_id, month.isoformat(), make, round(units), f"{revenue:.2f}"),
                    increment=bool(self.split and month > self.split),
                )

    # ------------------------------------------------------------------ dimensions

    def _increment_regions(self) -> set[int]:
        if not self.split:
            return set()
        first_open: dict[int, date] = {}
        for dealer in self.dealers:
            first_open[dealer.region_id] = min(
                first_open.get(dealer.region_id, FAR_FUTURE), dealer.opened
            )
        return {region_id for region_id, opened in first_open.items() if opened > self.split}

    def _write_dimensions(self, writer: _SplitWriter) -> None:
        split = self.split
        used_regions = {dealer.region_id for dealer in self.dealers}
        increment_regions = self._increment_regions()
        for city in mk.CITIES:
            region_id = self.region_ids[city.name]
            if region_id not in used_regions:
                continue
            writer.write(
                "dim_region",
                (region_id, city.zone, city.name, city.state, "India"),
                increment=region_id in increment_regions,
            )
        for carline in self.carlines:
            writer.write(
                "dim_carline",
                (
                    carline.carline_id,
                    carline.name,
                    carline.spec.model,
                    carline.spec.make,
                    carline.spec.car_type,
                    "" if carline.capacity is None else f"{carline.capacity:.1f}",
                    carline.engine_type,
                ),
                increment=bool(split and carline.introduced > split),
            )
        for colour_id, colour in enumerate(mk.COLOURS, start=1):
            tone = "Dual-tone, black roof" if colour.dual_tone else "Mono-tone"
            writer.write(
                "dim_color",
                (colour_id, colour.name, f"{colour.code} | {tone}", colour.patent or ""),
            )
        dealer_by_id = {dealer.dealer_id: dealer for dealer in self.dealers}
        for person in self.salespeople:
            dealer = dealer_by_id[person.dealer_id]
            active = person.end is None and dealer.closed is None
            writer.write(
                "dim_salesman",
                (
                    person.sales_person_id,
                    person.first_name,
                    person.last_name,
                    person.email,
                    person.corp_id,
                    "true" if active else "false",
                ),
                increment=bool(split and person.start > split),
            )
        for dealer in self.dealers:
            writer.write(
                "dim_dealer",
                (
                    dealer.dealer_id,
                    dealer.code,
                    dealer.name,
                    dealer.region_id,
                    dealer.city.name,
                    dealer.grade,
                    "true" if dealer.closed is None else "false",
                ),
                increment=bool(split and dealer.opened > split),
            )

    def _write_reference(self, out_dir: Path) -> None:
        with (out_dir / "reference_model_calendar.csv").open(
            "w", newline="", encoding="utf-8"
        ) as handle:
            out = csv.writer(handle, lineterminator="\n")
            out.writerow(
                ("carline_id", "carline_name", "make", "model", "car_type", "engine_type",
                 "engine_capacity", "on_sale_from", "on_sale_until", "anchor_price_lakh_2024")
            )  # fmt: skip
            for carline in self.carlines:
                spec = carline.spec
                until = carline_on_sale_until(carline)
                out.writerow(
                    (
                        carline.carline_id,
                        carline.name,
                        spec.make,
                        spec.model,
                        spec.car_type,
                        carline.engine_type,
                        "" if carline.capacity is None else carline.capacity,
                        carline.introduced.isoformat(),
                        until.isoformat() if until else "",
                        carline.variants[0].price_lakh,
                    )
                )

    # ------------------------------------------------------------------ public

    def generate(self, out_dir: Path) -> GenerationReport:
        started = time.perf_counter()
        self.report = GenerationReport()
        self._log("Building calendar (festivals, macro shocks)...")
        self._build_calendar()
        self._build_carlines()
        self._log(f"Calibrating demand for {len(self.carlines)} carlines...")
        self._build_demand()
        self._build_network()
        self._log(
            f"Network: {len(self.dealers)} dealers, {len(self.salespeople)} salespeople, "
            f"{len({d.region_id for d in self.dealers})} cities"
        )
        writer = _SplitWriter(out_dir, split=self.split is not None)
        try:
            for table in LOAD_ORDER:
                writer.ensure(table)
            self._write_dimensions(writer)
            self._log(f"Generating ~{self.config.rows:,} fact_sales rows...")
            self._generate_facts(writer)
            self._log("Deriving forecasts from generated history...")
            self._generate_forecasts(writer)
            self._log("Deriving FY targets from generated history...")
            self._generate_targets(writer)
        finally:
            writer.close()
        self._write_reference(out_dir)
        for (table, increment), count in writer.counts.items():
            bucket = self.report.increment_counts if increment else self.report.counts
            bucket[table] = count
        self.report.seconds = time.perf_counter() - started
        manifest = {
            "generator": "india_auto_generator",
            "seed": self.config.seed,
            "rows_requested": self.config.rows,
            "data_start": mk.DATA_START.isoformat(),
            "end_date": self.end.isoformat(),
            "split_date": self.split.isoformat() if self.split else None,
            "load_order": list(LOAD_ORDER),
            "columns": {table: list(cols) for table, cols in TABLE_COLUMNS.items()},
            **self.report.to_dict(),
        }
        (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        return self.report
