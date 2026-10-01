"""Executive KPI cockpit for the automotive warehouse.

One grouped scan over the selected period and the same period a year earlier feeds the
KPIs, sunburst, rankings, mix and geography; a monthly series feeds the trend, plan and
festive markers. Every insight sentence is computed from those numbers.
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from app.analytics.india_auto_market import DIWALI
from app.schemas.executive_cockpit import (
    BulletMetric,
    CockpitInsight,
    CockpitKpis,
    CockpitOptions,
    CockpitPeriod,
    CockpitPlan,
    CockpitResponse,
    HeatCell,
    HeatMatrix,
    LeaderKpi,
    MakeAchievement,
    MetricKpi,
    OptionItem,
    RankedItem,
    SunburstNode,
    TrendEvent,
    TrendPoint,
)

logger = logging.getLogger(__name__)

_CACHE: dict[str, tuple[float, CockpitResponse]] = {}
_OPTIONS_CACHE: dict[str, tuple[float, CockpitOptions]] = {}
_CACHE_TTL_SECONDS = 300
_CACHE_MAX = 64

TREND_MONTHS = 24
FORECAST_AHEAD = 6
MODELS_PER_MAKE = 12

STATE_NAMES = {
    "AP": "Andhra Pradesh",
    "AS": "Assam",
    "BR": "Bihar",
    "CG": "Chhattisgarh",
    "CH": "Chandigarh",
    "DL": "Delhi",
    "GA": "Goa",
    "GJ": "Gujarat",
    "HP": "Himachal Pradesh",
    "HR": "Haryana",
    "JH": "Jharkhand",
    "JK": "Jammu & Kashmir",
    "KA": "Karnataka",
    "KL": "Kerala",
    "MH": "Maharashtra",
    "MP": "Madhya Pradesh",
    "OD": "Odisha",
    "PB": "Punjab",
    "RJ": "Rajasthan",
    "TN": "Tamil Nadu",
    "TS": "Telangana",
    "UK": "Uttarakhand",
    "UP": "Uttar Pradesh",
    "WB": "West Bengal",
}

SHOCKS = {"2020-04-01": "COVID lockdown", "2021-05-01": "Second wave"}

CARLINE_FILTERS = ("make", "model", "engine_type", "car_type")
REGION_FILTERS = ("zone", "state", "city")
FILTER_KEYS = (*CARLINE_FILTERS, *REGION_FILTERS, "dealer_id", "sales_person_id")

SETS: dict[str, tuple[str, ...]] = {
    "total": (),
    "make": ("make",),
    "model": ("make", "model"),
    "powertrain": ("make", "model", "engine_type"),
    "fuel": ("engine_type",),
    "body": ("car_type",),
    "zone": ("zone",),
    "state": ("zone", "state"),
    "city": ("zone", "state", "city"),
    "dealer": ("zone", "city", "dealer"),
    "zone_body": ("zone", "car_type"),
}


def body_family(car_type: str) -> str:
    if "SUV" in car_type:
        return "SUV"
    if "Sedan" in car_type:
        return "Sedan"
    if "Hatchback" in car_type:
        return "Hatchback"
    return "MUV / MPV" if car_type in {"MUV", "MPV"} else car_type


def format_inr(value: float) -> str:
    sign = "-" if value < 0 else ""
    value = abs(value)
    if value >= 1e7:
        crore = value / 1e7
        return f"{sign}₹{crore:,.0f} Cr" if crore >= 100 else f"{sign}₹{crore:,.1f} Cr"
    if value >= 1e5:
        return f"{sign}₹{value / 1e5:,.1f} L"
    return f"{sign}₹{value:,.0f}"


def format_pct(value: float, signed: bool = True) -> str:
    return f"{value * 100:+.1f}%" if signed else f"{value * 100:.1f}%"


def growth(current: float, prior: float) -> float | None:
    return current / prior - 1 if prior > 0 else None


def month_add(day: date, months: int) -> date:
    index = day.year * 12 + day.month - 1 + months
    return date(index // 12, index % 12 + 1, 1)


def month_end(day: date) -> date:
    return month_add(day, 1) - timedelta(days=1)


def shift_year(day: date, years: int = -1) -> date:
    try:
        return day.replace(year=day.year + years)
    except ValueError:  # 29 Feb
        return day.replace(year=day.year + years, day=28)


@dataclass(frozen=True)
class CockpitFilters:
    year: int | None = None
    quarter: int | None = None
    month: int | None = None
    make: str | None = None
    model: str | None = None
    engine_type: str | None = None
    car_type: str | None = None
    zone: str | None = None
    state: str | None = None
    city: str | None = None
    dealer_id: int | None = None
    sales_person_id: int | None = None

    def dimensions(self) -> dict[str, Any]:
        return {
            key: getattr(self, key) for key in FILTER_KEYS if getattr(self, key) not in (None, "")
        }

    def cache_key(self) -> str:
        return json.dumps(self.__dict__, sort_keys=True, default=str)


@dataclass
class Period:
    start: date
    end: date
    prior_start: date
    prior_end: date
    label: str
    prior_label: str


@dataclass
class Agg:
    revenue: float = 0.0
    units: float = 0.0
    orders: float = 0.0


@dataclass
class Dimensions:
    carlines: dict[int, dict[str, str]]
    regions: dict[int, dict[str, str]]


_DIM_CACHE: dict[str, tuple[float, Dimensions]] = {}


@dataclass
class Grouped:
    cur: dict[str, dict[tuple[Any, ...], Agg]] = field(default_factory=dict)
    pri: dict[str, dict[tuple[Any, ...], Agg]] = field(default_factory=dict)

    def get(self, name: str, period: str = "cur") -> dict[tuple[Any, ...], Agg]:
        bucket = self.cur if period == "cur" else self.pri
        return bucket.get(name, {})

    def total(self, period: str = "cur") -> Agg:
        return self.get("total", period).get((), Agg())


def resolve_period(data_max: date, filters: CockpitFilters) -> Period:
    year = filters.year or data_max.year
    if filters.month:
        start = date(year, filters.month, 1)
        end = month_end(start)
        label = start.strftime("%b %Y")
    elif filters.quarter:
        start = date(year, 3 * (filters.quarter - 1) + 1, 1)
        end = month_end(month_add(start, 2))
        label = f"Q{filters.quarter} {year} ({start:%b}\u2013{end:%b})"
    else:
        start, end = date(year, 1, 1), date(year, 12, 31)
        label = str(year)
    if end > data_max >= start:
        end = data_max
        label = f"{label} to date ({end:%d %b})" if not filters.month else f"{label} to date"
    prior_start, prior_end = shift_year(start), shift_year(end)
    prior_label = label.replace(str(year), str(year - 1))
    return Period(start, end, prior_start, prior_end, label, prior_label)


class ExecutiveCockpitService:
    def __init__(self, connection: AsyncConnection) -> None:
        self._connection = connection

    # ------------------------------------------------------------------ queries

    async def _rows(self, sql: str, params: dict[str, Any]) -> list[dict[str, Any]]:
        result = await self._connection.execute(text(sql), params)
        return [dict(row) for row in result.mappings().all()]

    async def _data_max(self) -> date | None:
        value: date | None = (
            await self._connection.execute(
                text("SELECT MAX(sales_date) FROM automotive.fact_sales")
            )
        ).scalar_one_or_none()
        return value

    async def _dimensions(self) -> Dimensions:
        cached = _DIM_CACHE.get("dims")
        if cached and cached[0] > time.time():
            return cached[1]
        carlines = await self._rows(
            "SELECT carline_id, make, model, engine_type, car_type FROM automotive.dim_carline", {}
        )
        regions = await self._rows(
            "SELECT region_id, region_name AS zone, state_code AS state, city "
            "FROM automotive.dim_region",
            {},
        )
        dims = Dimensions(
            carlines={row.pop("carline_id"): row for row in carlines},
            regions={row.pop("region_id"): row for row in regions},
        )
        _DIM_CACHE["dims"] = (time.time() + _CACHE_TTL_SECONDS, dims)
        return dims

    def _where(
        self, filters: CockpitFilters, dims: Dimensions, *, people: bool = True
    ) -> tuple[str, dict[str, Any]]:
        """Dimension filters as id lists, so the large scans never join."""
        wanted = filters.dimensions()
        clauses: list[str] = []
        params: dict[str, Any] = {}
        carline_keys = [k for k in CARLINE_FILTERS if k in wanted]
        if carline_keys:
            params["carline_ids"] = [
                cid
                for cid, row in dims.carlines.items()
                if all(row[k] == str(wanted[k]) for k in carline_keys)
            ]
            clauses.append("f.carline_id = ANY(:carline_ids)")
        region_keys = [k for k in REGION_FILTERS if k in wanted]
        if region_keys:
            params["region_ids"] = [
                rid
                for rid, row in dims.regions.items()
                if all(row[k] == str(wanted[k]) for k in region_keys)
            ]
            clauses.append("f.region_id = ANY(:region_ids)")
        if people:
            for key in ("dealer_id", "sales_person_id"):
                if key in wanted:
                    params[key] = int(wanted[key])
                    clauses.append(f"f.{key} = :{key}")
        return "".join(f" AND {clause}" for clause in clauses), params

    async def _grouped(self, period: Period, filters: CockpitFilters, dims: Dimensions) -> Grouped:
        where, params = self._where(filters, dims)
        sql = f"""
            SELECT CASE WHEN f.sales_date >= :cs THEN 'cur' ELSE 'pri' END AS p,
                   f.carline_id, f.region_id, f.dealer_id,
                   SUM(f.total_sales)::float AS revenue,
                   SUM(f.order_qty)::float AS units,
                   COUNT(*)::float AS orders
            FROM automotive.fact_sales f
            WHERE ((f.sales_date BETWEEN :cs AND :ce) OR (f.sales_date BETWEEN :ps AND :pe))
            {where}
            GROUP BY 1, 2, 3, 4
        """  # noqa: S608
        params |= {
            "cs": period.start,
            "ce": period.end,
            "ps": period.prior_start,
            "pe": period.prior_end,
        }
        grouped = Grouped()
        for row in await self._rows(sql, params):
            carline = dims.carlines.get(row["carline_id"])
            region = dims.regions.get(row["region_id"])
            if carline is None or region is None:
                continue
            attrs = {**carline, **region, "dealer": row["dealer_id"]}
            bucket = grouped.cur if row["p"] == "cur" else grouped.pri
            for name, cols in SETS.items():
                key = tuple(attrs[col] for col in cols)
                agg = bucket.setdefault(name, {}).setdefault(key, Agg())
                agg.revenue += row["revenue"] or 0.0
                agg.units += row["units"] or 0.0
                agg.orders += row["orders"] or 0.0
        return grouped

    async def _monthly_actuals(
        self, start: date, end: date, filters: CockpitFilters, dims: Dimensions
    ) -> dict[date, Agg]:
        wanted = filters.dimensions()
        if set(wanted) <= {"make", "zone"}:
            clauses = []
            params: dict[str, Any] = {"ts": start, "te": end}
            if "make" in wanted:
                clauses.append("make = :make")
                params["make"] = wanted["make"]
            if "zone" in wanted:
                clauses.append("region = :zone")
                params["zone"] = wanted["zone"]
            sql = f"""
                SELECT month AS m, SUM(revenue)::float AS revenue, SUM(units)::float AS units
                FROM automotive.mv_sales_monthly
                WHERE month BETWEEN :ts AND :te {"".join(f" AND {c}" for c in clauses)}
                GROUP BY 1
            """  # noqa: S608
            try:
                async with self._connection.begin_nested():
                    rows = await self._rows(sql, params)
                if rows:
                    return {row["m"]: Agg(row["revenue"] or 0, row["units"] or 0) for row in rows}
            except Exception:  # materialised view not populated yet: use the fact table
                logger.debug("mv_sales_monthly unavailable; using fact_sales", exc_info=True)
        where, params = self._where(filters, dims)
        params |= {"ts": start, "te": month_end(end)}
        sql = f"""
            SELECT date_trunc('month', f.sales_date)::date AS m,
                   SUM(f.total_sales)::float AS revenue, SUM(f.order_qty)::float AS units
            FROM automotive.fact_sales f
            WHERE f.sales_date BETWEEN :ts AND :te {where}
            GROUP BY 1
        """  # noqa: S608
        rows = await self._rows(sql, params)
        return {row["m"]: Agg(row["revenue"] or 0, row["units"] or 0) for row in rows}

    async def _monthly_forecast(
        self, start: date, end: date, filters: CockpitFilters, dims: Dimensions
    ) -> dict[date, Agg]:
        where, params = self._where(filters, dims, people=False)
        params |= {"ts": start, "te": end}
        sql = f"""
            SELECT f.sales_month AS m, SUM(f.forecast_revenue)::float AS revenue,
                   SUM(f.forecast_units)::float AS units
            FROM automotive.fact_forecast_monthly f
            WHERE f.sales_month BETWEEN :ts AND :te {where}
            GROUP BY 1
        """  # noqa: S608
        try:
            async with self._connection.begin_nested():
                rows = await self._rows(sql, params)
        except Exception:
            return {}
        return {row["m"]: Agg(row["revenue"] or 0, row["units"] or 0) for row in rows}

    async def _targets(self, start: date, end: date, make: str | None) -> dict[str, Agg]:
        params: dict[str, Any] = {"ts": start, "te": end}
        clause = ""
        if make:
            clause = " AND make = :make"
            params["make"] = make
        sql = f"""
            SELECT make, SUM(target_revenue)::float AS revenue, SUM(target_units)::float AS units
            FROM automotive.dim_targets
            WHERE year_month BETWEEN :ts AND :te {clause}
            GROUP BY make
        """  # noqa: S608
        try:
            async with self._connection.begin_nested():
                rows = await self._rows(sql, params)
        except Exception:
            return {}
        return {row["make"]: Agg(row["revenue"] or 0, row["units"] or 0) for row in rows}

    async def _actuals_by_make(
        self, start: date, end: date, filters: CockpitFilters, dims: Dimensions
    ) -> dict[str, Agg]:
        where, params = self._where(filters, dims)
        params |= {"ts": start, "te": end}
        sql = f"""
            SELECT f.carline_id, SUM(f.total_sales)::float AS revenue,
                   SUM(f.order_qty)::float AS units
            FROM automotive.fact_sales f
            WHERE f.sales_date BETWEEN :ts AND :te {where}
            GROUP BY 1
        """  # noqa: S608
        out: dict[str, Agg] = {}
        for row in await self._rows(sql, params):
            make = dims.carlines.get(row["carline_id"], {}).get("make")
            if make:
                agg = out.setdefault(make, Agg())
                agg.revenue += row["revenue"] or 0.0
                agg.units += row["units"] or 0.0
        return out

    async def _dealer_names(self, ids: list[int]) -> dict[int, tuple[str, str]]:
        if not ids:
            return {}
        rows = await self._rows(
            "SELECT dealer_id, dealer_name, city FROM automotive.dim_dealer "
            "WHERE dealer_id = ANY(:ids)",
            {"ids": ids},
        )
        return {row["dealer_id"]: (row["dealer_name"], row["city"]) for row in rows}

    # ------------------------------------------------------------------ bundle

    async def get_cockpit(
        self, filters: CockpitFilters, *, force_refresh: bool = False
    ) -> CockpitResponse:
        key = filters.cache_key()
        now = time.time()
        cached = _CACHE.get(key)
        if cached and cached[0] > now and not force_refresh:
            return cached[1]
        response = await self._build(filters)
        if len(_CACHE) >= _CACHE_MAX:
            _CACHE.pop(next(iter(_CACHE)))
        _CACHE[key] = (now + _CACHE_TTL_SECONDS, response)
        return response

    async def _build(self, filters: CockpitFilters) -> CockpitResponse:
        data_max = await self._data_max() or datetime.now(UTC).date()
        period = resolve_period(data_max, filters)
        dims = await self._dimensions()
        grouped = await self._grouped(period, filters, dims)
        cur, pri = grouped.total("cur"), grouped.total("pri")

        end_month = date(period.end.year, period.end.month, 1)
        trend_start = month_add(end_month, -(TREND_MONTHS - 1))
        actuals = await self._monthly_actuals(month_add(trend_start, -12), end_month, filters, dims)
        latest_month = date(data_max.year, data_max.month, 1)
        show_future = end_month == latest_month
        forecast_end = month_add(end_month, FORECAST_AHEAD if show_future else 0)
        people_filtered = bool(filters.dealer_id or filters.sales_person_id)
        forecast = (
            {}
            if people_filtered
            else await self._monthly_forecast(trend_start, forecast_end, filters, dims)
        )

        last_complete = (
            latest_month if data_max == month_end(data_max) else month_add(latest_month, -1)
        )
        trend, events = self._trend(
            trend_start, end_month, forecast_end, actuals, forecast, period, latest_month, data_max
        )

        plan = await self._plan(period, filters, dims, actuals, forecast, last_complete)
        kpis = self._kpis(grouped, cur, pri)
        zones = self._ranked(grouped, "zone", lambda k: (k[0], k[0], None, None), cur.revenue)
        states = self._ranked(
            grouped,
            "state",
            lambda k: (k[1], STATE_NAMES.get(k[1], k[1]), k[0], k[0]),
            cur.revenue,
        )
        cities = self._ranked(
            grouped,
            "city",
            lambda k: (k[2], k[2], STATE_NAMES.get(k[1], k[1]), k[0]),
            cur.revenue,
        )[:15]
        dealer_rows = self._ranked(
            grouped, "dealer", lambda k: (str(k[2]), str(k[2]), k[1], k[0]), cur.revenue
        )[:15]
        names = await self._dealer_names([int(item.key) for item in dealer_rows])
        dealers = [
            item.model_copy(update={"name": names.get(int(item.key), (item.name, ""))[0]})
            for item in dealer_rows
        ]
        models = self._ranked(
            grouped, "model", lambda k: (f"{k[0]}|{k[1]}", k[1], k[0], k[0]), cur.revenue
        )
        by_units = sorted(models, key=lambda item: item.units, reverse=True)[:10]
        fuel = self._mix(grouped, "fuel", lambda k: k[0])
        body = self._mix(grouped, "body", lambda k: k[0], group=lambda k: body_family(k[0]))
        response = CockpitResponse(
            period=CockpitPeriod(
                label=period.label,
                start=period.start.isoformat(),
                end=period.end.isoformat(),
                prior_label=period.prior_label,
                prior_start=period.prior_start.isoformat(),
                prior_end=period.prior_end.isoformat(),
                data_as_of=data_max.isoformat(),
                plan_months_label=plan.months_label,
            ),
            applied_filters={k: str(v) for k, v in filters.dimensions().items()},
            empty=cur.orders == 0,
            kpis=kpis,
            trend=trend,
            events=events,
            zones=zones,
            states=states,
            cities=cities,
            dealers=dealers,
            sunburst=self._sunburst(grouped),
            top_models_by_revenue=models[:10],
            top_models_by_units=by_units,
            fuel_mix=fuel,
            body_mix=body,
            heat=self._heat(grouped),
            plan=plan,
            insights=[],
            computed_at=datetime.now(UTC).isoformat(),
        )
        response.insights = self._insights(response, grouped, filters, actuals)
        return response

    # ------------------------------------------------------------------ sections

    def _kpis(self, grouped: Grouped, cur: Agg, pri: Agg) -> CockpitKpis:
        def metric(a: float, b: float) -> MetricKpi:
            return MetricKpi(value=a, prior=b, growth=growth(a, b))

        avg_cur = cur.revenue / cur.units if cur.units else 0.0
        avg_pri = pri.revenue / pri.units if pri.units else 0.0
        top_model = None
        models = grouped.get("model")
        if models and cur.revenue:
            (make, model), agg = max(models.items(), key=lambda item: item[1].revenue)
            prior = grouped.get("model", "pri").get((make, model), Agg())
            top_model = LeaderKpi(
                name=model,
                make=make,
                revenue=agg.revenue,
                share=agg.revenue / cur.revenue,
                growth=growth(agg.revenue, prior.revenue),
            )
        top_make = None
        makes = grouped.get("make")
        if makes and cur.units:
            (make,), agg = max(makes.items(), key=lambda item: item[1].units)
            prior = grouped.get("make", "pri").get((make,), Agg())
            share = agg.units / cur.units
            prior_share = prior.units / pri.units if pri.units else None
            top_make = LeaderKpi(
                name=make,
                revenue=agg.revenue,
                share=share,
                share_change=share - prior_share if prior_share is not None else None,
                growth=growth(agg.units, prior.units),
            )
        return CockpitKpis(
            revenue=metric(cur.revenue, pri.revenue),
            units=metric(cur.units, pri.units),
            orders=metric(cur.orders, pri.orders),
            avg_price=metric(avg_cur, avg_pri),
            top_model=top_model,
            top_make=top_make,
        )

    def _ranked(
        self,
        grouped: Grouped,
        name: str,
        describe: Any,
        total_revenue: float,
    ) -> list[RankedItem]:
        prior_total = grouped.total("pri").revenue
        prior = grouped.get(name, "pri")
        items = []
        for key, agg in grouped.get(name).items():
            ident, label, detail, group = describe(key)
            before = prior.get(key, Agg())
            items.append(
                RankedItem(
                    key=str(ident),
                    name=str(label),
                    detail=detail,
                    group=group,
                    revenue=agg.revenue,
                    units=agg.units,
                    prior_revenue=before.revenue,
                    growth=growth(agg.revenue, before.revenue),
                    share=agg.revenue / total_revenue if total_revenue else 0.0,
                    prior_share=before.revenue / prior_total if prior_total else None,
                )
            )
        return sorted(items, key=lambda item: item.revenue, reverse=True)

    def _mix(self, grouped: Grouped, name: str, label: Any, group: Any = None) -> list[RankedItem]:
        cur_units = grouped.total("cur").units
        pri_units = grouped.total("pri").units
        prior = grouped.get(name, "pri")
        items = []
        for key, agg in grouped.get(name).items():
            before = prior.get(key, Agg())
            items.append(
                RankedItem(
                    key=str(label(key)),
                    name=str(label(key)),
                    group=group(key) if group else None,
                    revenue=agg.revenue,
                    units=agg.units,
                    prior_revenue=before.revenue,
                    growth=growth(agg.units, before.units),
                    share=agg.units / cur_units if cur_units else 0.0,
                    prior_share=before.units / pri_units if pri_units else None,
                )
            )
        return sorted(items, key=lambda item: item.units, reverse=True)

    def _sunburst(self, grouped: Grouped) -> list[SunburstNode]:
        tree: dict[str, dict[str, dict[str, Agg]]] = {}
        for (make, model, engine), agg in grouped.get("powertrain").items():
            tree.setdefault(make, {}).setdefault(model, {})[engine] = agg
        nodes: list[SunburstNode] = []
        for make, models in tree.items():
            children = []
            for model, engines in models.items():
                children.append(
                    SunburstNode(
                        name=model,
                        dimension="model",
                        revenue=sum(a.revenue for a in engines.values()),
                        units=sum(a.units for a in engines.values()),
                        children=sorted(
                            (
                                SunburstNode(
                                    name=engine,
                                    dimension="engine_type",
                                    revenue=a.revenue,
                                    units=a.units,
                                )
                                for engine, a in engines.items()
                            ),
                            key=lambda n: n.revenue,
                            reverse=True,
                        ),
                    )
                )
            children.sort(key=lambda n: n.revenue, reverse=True)
            if len(children) > MODELS_PER_MAKE:
                rest = children[MODELS_PER_MAKE:]
                children = [
                    *children[:MODELS_PER_MAKE],
                    SunburstNode(
                        name=f"{len(rest)} other models",
                        dimension="model",
                        revenue=sum(n.revenue for n in rest),
                        units=sum(n.units for n in rest),
                    ),
                ]
            nodes.append(
                SunburstNode(
                    name=make,
                    dimension="make",
                    revenue=sum(n.revenue for n in children),
                    units=sum(n.units for n in children),
                    children=children,
                )
            )
        return sorted(nodes, key=lambda n: n.revenue, reverse=True)

    def _heat(self, grouped: Grouped) -> HeatMatrix:
        cells: dict[tuple[str, str], list[float]] = {}
        zone_total: dict[str, float] = {}
        for period in ("cur", "pri"):
            for (zone, car_type), agg in grouped.get("zone_body", period).items():
                slot = cells.setdefault((zone, body_family(car_type)), [0.0, 0.0])
                slot[0 if period == "cur" else 1] += agg.revenue
                if period == "cur":
                    zone_total[zone] = zone_total.get(zone, 0.0) + agg.revenue
        rows = sorted(zone_total, key=lambda z: zone_total[z], reverse=True)
        col_total: dict[str, float] = {}
        for (_zone, family), (value, _prior) in cells.items():
            col_total[family] = col_total.get(family, 0.0) + value
        cols = sorted(col_total, key=lambda c: col_total[c], reverse=True)
        return HeatMatrix(
            rows=rows,
            cols=cols,
            cells=[
                HeatCell(
                    row=zone,
                    col=family,
                    revenue=value,
                    share=value / zone_total[zone] if zone_total.get(zone) else 0.0,
                    growth=growth(value, prior),
                )
                for (zone, family), (value, prior) in cells.items()
                if zone in zone_total
            ],
        )

    def _trend(
        self,
        trend_start: date,
        end_month: date,
        forecast_end: date,
        actuals: dict[date, Agg],
        forecast: dict[date, Agg],
        period: Period,
        latest_month: date,
        data_max: date,
    ) -> tuple[list[TrendPoint], list[TrendEvent]]:
        points: list[TrendPoint] = []
        month = trend_start
        while month <= forecast_end:
            actual = actuals.get(month) if month <= end_month else None
            prior = actuals.get(month_add(month, -12))
            fc = forecast.get(month)
            yoy = growth(actual.revenue, prior.revenue) if actual and prior else None
            partial = month == latest_month and data_max < month_end(data_max)
            points.append(
                TrendPoint(
                    month=month.isoformat(),
                    revenue=actual.revenue if actual else None,
                    units=actual.units if actual else None,
                    prior_revenue=prior.revenue if prior else None,
                    forecast_revenue=fc.revenue if fc else None,
                    forecast_units=fc.units if fc else None,
                    in_period=period.start <= month <= period.end,
                    partial=partial,
                    growth_period=bool(yoy is not None and yoy >= 0.1 and not partial),
                )
            )
            month = month_add(month, 1)
        complete = [p for p in points if p.revenue is not None and not p.partial]
        for point in sorted(complete, key=lambda p: p.revenue or 0, reverse=True)[:3]:
            point.peak = True
        events: list[TrendEvent] = []
        for year, iso in DIWALI.items():
            day = date.fromisoformat(iso)
            first = date(day.year, day.month, 1)
            if trend_start <= first <= end_month:
                events.append(TrendEvent(month=first.isoformat(), label=f"Diwali {year}"))
        for iso, label in SHOCKS.items():
            if trend_start <= date.fromisoformat(iso) <= end_month:
                events.append(TrendEvent(month=iso, label=label, kind="shock"))
        return points, sorted(events, key=lambda e: e.month)

    async def _plan(
        self,
        period: Period,
        filters: CockpitFilters,
        dims: Dimensions,
        actuals: dict[date, Agg],
        forecast: dict[date, Agg],
        last_complete: date,
    ) -> CockpitPlan:
        first = date(period.start.year, period.start.month, 1)
        last = min(date(period.end.year, period.end.month, 1), last_complete)
        months: list[date] = []
        month = first
        while month <= last:
            months.append(month)
            month = month_add(month, 1)
        actual_rev = sum(actuals.get(m, Agg()).revenue for m in months)
        actual_units = sum(actuals.get(m, Agg()).units for m in months)
        label = None
        if months:
            label = (
                f"{months[0]:%b %Y}"
                if len(months) == 1
                else f"{months[0]:%b}\u2013{months[-1]:%b %Y}"
                if months[0].year == months[-1].year
                else f"{months[0]:%b %Y}\u2013{months[-1]:%b %Y}"
            )
        wanted = filters.dimensions()
        target_ok = bool(months) and set(wanted) <= {"make"}
        targets = (
            await self._targets(months[0], months[-1], wanted.get("make")) if target_ok else {}
        )
        target_rev = sum(a.revenue for a in targets.values()) if targets else None
        target_units = sum(a.units for a in targets.values()) if targets else None
        fc_rev = sum(forecast.get(m, Agg()).revenue for m in months) if months else 0.0
        fc_units = sum(forecast.get(m, Agg()).units for m in months) if months else 0.0
        has_fc = bool(months) and any(m in forecast for m in months)

        def bullet(label_: str, actual: float, target: float | None, fmt: str) -> BulletMetric:
            return BulletMetric(
                label=label_,
                actual=actual,
                target=target,
                achievement=actual / target if target else None,
                format=fmt,
            )

        by_make: list[MakeAchievement] = []
        if target_ok and targets and "make" not in wanted:
            make_actuals = await self._actuals_by_make(
                months[0], month_end(months[-1]), filters, dims
            )
            for make, target in targets.items():
                actual = make_actuals.get(make, Agg())
                if target.units <= 0:
                    continue
                by_make.append(
                    MakeAchievement(
                        make=make,
                        actual_units=actual.units,
                        target_units=target.units,
                        achievement=actual.units / target.units,
                    )
                )
            by_make.sort(key=lambda item: item.actual_units, reverse=True)
        target_note = None
        if not months:
            target_note = "No completed month in this period yet."
        elif not target_ok:
            target_note = (
                "Targets are set per brand and month. Clear model, fuel, body, region, "
                "dealer and salesperson filters to compare."
            )
        forecast_note = None
        if wanted.keys() & {"dealer_id", "sales_person_id"}:
            forecast_note = (
                "Forecasts are planned by model and city, not by dealer or salesperson. "
                "Clear those filters to compare."
            )
        return CockpitPlan(
            months_label=label,
            revenue=bullet("Revenue vs target", actual_rev, target_rev, "currency"),
            units=bullet("Units vs target", actual_units, target_units, "integer"),
            forecast_revenue=bullet(
                "Revenue vs forecast", actual_rev, fc_rev if has_fc else None, "currency"
            ),
            forecast_units=bullet(
                "Units vs forecast", actual_units, fc_units if has_fc else None, "integer"
            ),
            target_note=target_note,
            forecast_note=forecast_note,
            by_make=by_make,
        )

    # ------------------------------------------------------------------ storytelling

    def _insights(
        self,
        data: CockpitResponse,
        grouped: Grouped,
        filters: CockpitFilters,
        actuals: dict[date, Agg],
    ) -> list[CockpitInsight]:
        out: list[CockpitInsight] = []
        rev = data.kpis.revenue
        if rev.growth is not None:
            families: dict[str, list[float]] = {}
            for period in ("cur", "pri"):
                for (car_type,), agg in grouped.get("body", period).items():
                    slot = families.setdefault(body_family(car_type), [0.0, 0.0])
                    slot[0 if period == "cur" else 1] += agg.revenue
            deltas = {name: v[0] - v[1] for name, v in families.items()}
            up = rev.growth >= 0
            driver = max(deltas, key=lambda n: deltas[n] if up else -deltas[n]) if deltas else None
            detail = (
                f"{format_inr(rev.value)} in {data.period.label} "
                f"vs {format_inr(rev.prior)} a year earlier."
            )
            headline = f"Revenue {'up' if up else 'down'} {abs(rev.growth) * 100:.1f}% YoY"
            if driver and (deltas[driver] > 0) == up:
                headline += (
                    f", driven by {driver} demand" if up else f", with {driver} the largest drag"
                )
                detail += (
                    f" {driver} {'added' if up else 'lost'} {format_inr(abs(deltas[driver]))}."
                )
            out.append(
                CockpitInsight(
                    id="revenue_growth",
                    tone="positive" if up else "negative",
                    headline=headline,
                    detail=detail,
                    metric=format_pct(rev.growth),
                )
            )

        zones = [z for z in data.zones if z.growth is not None and z.share >= 0.05]
        if len(zones) > 1 and not filters.zone:
            best = max(zones, key=lambda z: z.growth or 0)
            best_growth = best.growth or 0
            out.append(
                CockpitInsight(
                    id="zone_growth",
                    tone="positive" if best_growth >= 0 else "neutral",
                    headline=(
                        f"{best.name} region delivered the highest growth at "
                        f"{format_pct(best_growth)}"
                        if best_growth >= 0
                        else f"{best.name} region held up best at {format_pct(best_growth)}"
                    ),
                    detail=(
                        f"{format_inr(best.revenue)} revenue, "
                        f"{format_pct(best.share, False)} of the total."
                    ),
                    metric=format_pct(best.growth or 0),
                    filter_dimension="zone",
                    filter_value=best.name,
                )
            )

        ev = [i for i in data.fuel_mix if i.name == "Electric"]
        ev_models = [
            (key, agg) for key, agg in grouped.get("powertrain").items() if key[2] == "Electric"
        ]
        if ev and ev_models and not filters.engine_type:
            ev_revenue = sum(agg.revenue for _, agg in ev_models)
            (make, model, _), top = max(ev_models, key=lambda item: item[1].revenue)
            share_note = ""
            if ev[0].prior_share is not None:
                share_note = (
                    f" EV share of units moved from {format_pct(ev[0].prior_share, False)}"
                    f" to {format_pct(ev[0].share, False)}."
                )
            top_pct = top.revenue / ev_revenue * 100 if ev_revenue else 0.0
            out.append(
                CockpitInsight(
                    id="ev_leader",
                    tone="positive",
                    headline=f"{make} {model} contributed {top_pct:.0f}% of EV revenue",
                    detail=f"EVs generated {format_inr(ev_revenue)}.{share_note}",
                    metric=format_pct(ev[0].share, False),
                    filter_dimension="engine_type",
                    filter_value="Electric",
                )
            )

        top_make = data.kpis.top_make
        if top_make and top_make.share < 0.999:
            change = top_make.share_change
            trend = (
                f"{'gained' if change >= 0 else 'lost'} {abs(change) * 100:.1f} pts"
                if change is not None
                else "leads"
            )
            out.append(
                CockpitInsight(
                    id="make_share",
                    tone="neutral",
                    headline=(
                        f"{top_make.name} leads with {format_pct(top_make.share, False)} unit share"
                    ),
                    detail=f"{top_make.name} {trend} of share vs {data.period.prior_label}.",
                    metric=format_pct(top_make.share, False),
                    filter_dimension="make",
                    filter_value=top_make.name,
                )
            )
        # Established models only: a launch "growing" from a few units is not a trend.
        movers = [
            m
            for m in data.top_models_by_revenue[:10]
            if m.growth is not None and m.growth > 0 and m.prior_revenue >= 0.4 * m.revenue
        ]
        if movers and not filters.model:
            fastest = max(movers, key=lambda m: m.growth or 0)
            out.append(
                CockpitInsight(
                    id="model_mover",
                    tone="positive",
                    headline=f"{fastest.group} {fastest.name} is the fastest-growing top-10 model",
                    detail=(
                        f"Revenue {format_pct(fastest.growth or 0)} "
                        f"to {format_inr(fastest.revenue)}."
                    ),
                    metric=format_pct(fastest.growth or 0),
                    filter_dimension="model",
                    filter_value=fastest.name,
                )
            )

        festive = [
            e
            for e in data.events
            if e.kind == "festive" and actuals.get(date.fromisoformat(e.month))
        ]
        for event in reversed(festive):
            month = date.fromisoformat(event.month)
            window = [actuals.get(month_add(month, -i)) for i in range(12)]
            values = [a.revenue for a in window if a]
            point = next((p for p in data.trend if p.month == event.month), None)
            if len(values) >= 6 and point and not point.partial:
                average = sum(values) / len(values)
                ratio = (actuals[month].revenue / average) if average else 0
                out.append(
                    CockpitInsight(
                        id="festive",
                        tone="positive",
                        headline=(
                            f"{event.label} month generated {ratio:.1f}x average monthly sales"
                        ),
                        detail=(
                            f"{format_inr(actuals[month].revenue)} in {month:%b %Y} "
                            f"vs a 12-month average of {format_inr(average)}."
                        ),
                        metric=f"{ratio:.1f}x",
                    )
                )
                break

        plan = data.plan
        if plan.units.achievement is not None:
            ach = plan.units.achievement
            out.append(
                CockpitInsight(
                    id="target",
                    tone="positive" if ach >= 1 else "negative" if ach < 0.9 else "neutral",
                    headline=f"Units at {ach * 100:.0f}% of target for {plan.months_label}",
                    detail=(
                        f"{plan.units.actual:,.0f} sold "
                        f"vs a target of {plan.units.target or 0:,.0f}."
                    ),
                    metric=f"{ach * 100:.0f}%",
                )
            )
        priority = [
            "revenue_growth",
            "zone_growth",
            "ev_leader",
            "target",
            "festive",
            "make_share",
            "model_mover",
        ]
        return sorted(out, key=lambda item: priority.index(item.id))[:6]


async def fetch_cockpit_options(
    connection: AsyncConnection, dealer_id: int | None = None
) -> CockpitOptions:
    key = f"options|{dealer_id}"
    cached = _OPTIONS_CACHE.get(key)
    if cached and cached[0] > time.time():
        return cached[1]

    async def rows(sql: str, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        result = await connection.execute(text(sql), params or {})
        return [dict(row) for row in result.mappings().all()]

    span = (
        await rows("SELECT MIN(sales_date) AS lo, MAX(sales_date) AS hi FROM automotive.fact_sales")
    )[0]
    years = list(range(span["hi"].year, span["lo"].year - 1, -1)) if span["lo"] else []
    carlines = await rows(
        "SELECT DISTINCT make, model, engine_type, car_type FROM automotive.dim_carline"
    )
    regions = await rows("SELECT DISTINCT region_name, state_code FROM automotive.dim_region")
    dealers = await rows(
        "SELECT dealer_id, dealer_name, city FROM automotive.dim_dealer ORDER BY dealer_name"
    )
    salespeople: list[OptionItem] = []
    if dealer_id is not None:
        people = await rows(
            """
            SELECT s.sales_person_id, s.first_name, s.last_name, s.active
            FROM automotive.dim_salesman s
            WHERE s.sales_person_id IN (
                SELECT DISTINCT sales_person_id FROM automotive.fact_sales WHERE dealer_id = :d
            )
            ORDER BY s.first_name, s.last_name
            """,
            {"d": dealer_id},
        )
        salespeople = [
            OptionItem(
                value=str(p["sales_person_id"]),
                label=f"{p['first_name']} {p['last_name']}"
                + ("" if p["active"] else " (inactive)"),
            )
            for p in people
        ]

    def unique(values: list[tuple[str, str | None]]) -> list[OptionItem]:
        seen = sorted(set(values), key=lambda v: (v[1] or "", v[0]))
        return [OptionItem(value=v, label=v, group=g) for v, g in seen]

    options = CockpitOptions(
        years=years,
        makes=unique([(c["make"], None) for c in carlines]),
        models=unique([(c["model"], c["make"]) for c in carlines]),
        engine_types=unique([(c["engine_type"], None) for c in carlines]),
        car_types=unique([(c["car_type"], body_family(c["car_type"])) for c in carlines]),
        zones=unique([(r["region_name"], None) for r in regions]),
        states=[
            OptionItem(value=code, label=STATE_NAMES.get(code, code), group=zone)
            for zone, code in sorted({(r["region_name"], r["state_code"]) for r in regions})
        ],
        dealers=[
            OptionItem(value=str(d["dealer_id"]), label=d["dealer_name"], group=d["city"])
            for d in dealers
        ],
        salespeople=salespeople,
    )
    _OPTIONS_CACHE[key] = (time.time() + _CACHE_TTL_SECONDS, options)
    return options


def clear_cockpit_cache() -> None:
    _CACHE.clear()
    _OPTIONS_CACHE.clear()
