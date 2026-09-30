"""Data-quality validation for the loaded Indian automotive dataset.

Usage
-----
    # from askdb/
    python scripts/validate_india_auto_dataset.py
    python scripts/validate_india_auto_dataset.py --min-rows 50000 --json dq_report.json

Integrity checks (FAIL): row counts, null business keys, orphans, valid engine / car
type / capacity, brand-model combinations, no sales outside launch windows, geography,
dealer brand exclusivity, value ranges, generated revenue, target / forecast shape.
Realism checks (FAIL): market-share order, Tata growth, Mahindra SUV mix, EV curve,
colour ranking, festive seasonality, COVID lockdown, order quantities, price inflation,
target achievement and forecast accuracy bands. Exits 1 when any check fails.
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from itertools import pairwise
from pathlib import Path
from typing import Any

import psycopg

API_ROOT = Path(__file__).resolve().parents[1] / "apps" / "api"
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))

from app.analytics import india_auto_market as mk  # noqa: E402
from app.analytics.india_auto_generator import (  # noqa: E402
    build_carlines,
    carline_on_sale_until,
)

SUV_TYPES = ("SUV", "Compact SUV", "Mid SUV", "Premium SUV")


@dataclass
class Check:
    name: str
    passed: bool
    detail: str
    category: str = "integrity"


class Validator:
    def __init__(self, conn: psycopg.Connection, *, min_rows: int) -> None:
        self.conn = conn
        self.min_rows = min_rows
        self.checks: list[Check] = []

    def scalar(self, query: str, params: tuple[Any, ...] = ()) -> Any:
        return self.conn.execute(query, params).fetchone()[0]

    def rows(self, query: str, params: tuple[Any, ...] = ()) -> list[tuple[Any, ...]]:
        return self.conn.execute(query, params).fetchall()

    def add(self, name: str, passed: bool, detail: str, category: str = "integrity") -> None:
        self.checks.append(Check(name, bool(passed), detail, category))

    def run(self, name: str, fn: Callable[[], None], category: str = "integrity") -> None:
        try:
            fn()
        except Exception as exc:
            self.conn.rollback()
            self.add(name, False, f"check errored: {exc}", category)

    # ------------------------------------------------------------------ integrity

    def row_counts(self) -> None:
        counts = {
            table: self.scalar(f"SELECT COUNT(*) FROM automotive.{table}")  # noqa: S608
            for table in (
                "fact_sales",
                "fact_forecast_monthly",
                "dim_carline",
                "dim_color",
                "dim_salesman",
                "dim_region",
                "dim_dealer",
                "dim_targets",
            )
        }
        inactive = self.scalar("SELECT COUNT(*) FROM automotive.dim_salesman WHERE NOT active")
        self.add(
            "fact_sales volume",
            counts["fact_sales"] >= self.min_rows,
            f"{counts['fact_sales']:,} rows (minimum {self.min_rows:,})",
        )
        self.add(
            "dealer network size",
            300 <= counts["dim_dealer"] <= 500,
            f"{counts['dim_dealer']} dealers (expected 300-500)",
        )
        self.add(
            "salesforce size",
            2000 <= counts["dim_salesman"] <= 5000 and inactive > 0,
            f"{counts['dim_salesman']:,} salespeople, {inactive:,} inactive",
        )
        empty = [table for table, count in counts.items() if count == 0]
        self.add("all tables populated", not empty, f"empty: {empty}" if empty else str(counts))

    def null_keys(self) -> None:
        keys = {
            "dim_region": ("region_id", "region_name", "city", "state_code", "country"),
            "dim_carline": (
                "carline_id",
                "carline_name",
                "model",
                "make",
                "car_type",
                "engine_type",
            ),
            "dim_color": ("colour_id", "colour_name", "rcg_combination"),
            "dim_salesman": ("sales_person_id", "first_name", "last_name", "email", "corp_id"),
            "dim_dealer": (
                "dealer_id",
                "dealer_code",
                "dealer_name",
                "region_id",
                "city",
                "dealer_grade",
            ),
            "dim_targets": ("target_id", "year_month", "make", "target_units", "target_revenue"),
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
                "total_sales",
            ),
            "fact_forecast_monthly": (
                "sales_month",
                "carline_id",
                "region_id",
                "forecast_revenue",
                "forecast_units",
            ),
        }
        problems = []
        for table, columns in keys.items():
            predicate = " OR ".join(f"{c} IS NULL OR {c}::text = ''" for c in columns)
            count = self.scalar(f"SELECT COUNT(*) FROM automotive.{table} WHERE {predicate}")  # noqa: S608
            if count:
                problems.append(f"{table}: {count:,}")
        self.add("no null business keys", not problems, "; ".join(problems) or "0 nulls")

    def orphans(self) -> None:
        links = (
            ("fact_sales", "carline_id", "dim_carline"),
            ("fact_sales", "colour_id", "dim_color"),
            ("fact_sales", "sales_person_id", "dim_salesman"),
            ("fact_sales", "region_id", "dim_region"),
            ("fact_sales", "dealer_id", "dim_dealer"),
            ("dim_dealer", "region_id", "dim_region"),
            ("fact_forecast_monthly", "carline_id", "dim_carline"),
            ("fact_forecast_monthly", "region_id", "dim_region"),
        )
        problems = []
        for child, column, parent in links:
            count = self.scalar(
                f"SELECT COUNT(*) FROM automotive.{child} c "  # noqa: S608
                f"LEFT JOIN automotive.{parent} p ON p.{column} = c.{column} "
                f"WHERE p.{column} IS NULL"
            )
            if count:
                problems.append(f"{child}.{column}: {count:,}")
        unused = self.scalar(
            "SELECT COUNT(*) FROM automotive.dim_dealer d WHERE NOT EXISTS "
            "(SELECT 1 FROM automotive.fact_sales f WHERE f.dealer_id = d.dealer_id)"
        )
        self.add("no orphan records", not problems, "; ".join(problems) or "all keys resolve")
        self.add("every dealer has sales", unused == 0, f"{unused} dealers without sales")

    def vehicle_rules(self) -> None:
        bad_engine = self.scalar(
            "SELECT COUNT(*) FROM automotive.dim_carline WHERE engine_type <> ALL(%s)",
            (list(mk.ENGINE_TYPES),),
        )
        bad_type = self.scalar(
            "SELECT COUNT(*) FROM automotive.dim_carline WHERE car_type <> ALL(%s)",
            (list(mk.CAR_TYPES),),
        )
        bad_capacity = self.scalar(
            "SELECT COUNT(*) FROM automotive.dim_carline WHERE "
            "(engine_type = 'Electric' AND engine_capacity IS NOT NULL) OR "
            "(engine_type <> 'Electric' AND (engine_capacity IS NULL "
            " OR engine_capacity < 0.6 OR engine_capacity > 3.6))"
        )
        bad_make = self.scalar(
            "SELECT COUNT(*) FROM automotive.dim_carline WHERE make <> ALL(%s)", (list(mk.MAKES),)
        )
        self.add("valid engine types", bad_engine == 0, f"{bad_engine} invalid")
        self.add("valid car types", bad_type == 0, f"{bad_type} invalid")
        self.add(
            "realistic engine capacity",
            bad_capacity == 0,
            f"{bad_capacity} carlines outside 0.6-3.6 L (EVs must be NULL)",
        )
        self.add("valid makes", bad_make == 0, f"{bad_make} unknown makes")

        catalogue = {(s.make, s.model): s.car_type for s in mk.MODELS}
        observed = self.rows(
            "SELECT d.make, d.model, d.car_type, (SELECT COUNT(DISTINCT x.make) "
            "FROM automotive.dim_carline x WHERE x.model = d.model) "
            "FROM automotive.dim_carline d GROUP BY d.make, d.model, d.car_type"
        )
        impossible = [
            f"{make} {model}"
            for make, model, car_type, makes in observed
            if catalogue.get((make, model)) != car_type or makes > 1
        ]
        self.add(
            "brand/model combinations real",
            not impossible,
            ", ".join(impossible[:8]) or f"{len(observed)} models match the catalogue",
        )

        combos = {(c.spec.model, c.engine_type, c.capacity) for c in build_carlines()}
        invalid = [
            f"{model} {engine} {capacity}"
            for model, engine, capacity in self.rows(
                "SELECT model, engine_type, engine_capacity::float FROM automotive.dim_carline"
            )
            if (model, engine, capacity) not in combos
        ]
        self.add(
            "valid powertrain per model",
            not invalid,
            ", ".join(invalid[:8]) or "every model/engine combination exists",
        )

    def launch_windows(self) -> None:
        catalogue = {(c.spec.model, c.engine_type, c.capacity): c for c in build_carlines()}
        ids = {
            carline_id: catalogue.get((model, engine, capacity))
            for carline_id, model, engine, capacity in self.rows(
                "SELECT carline_id, model, engine_type, engine_capacity::float "
                "FROM automotive.dim_carline"
            )
        }
        monthly = self.rows(
            "SELECT carline_id, date_trunc('month', sales_date)::date, MIN(sales_date), "
            "MAX(sales_date) FROM automotive.fact_sales GROUP BY 1, 2"
        )
        early: list[str] = []
        late: list[str] = []
        gaps: list[str] = []
        for carline_id, month, first_day, last_day in monthly:
            carline = ids.get(carline_id)
            if carline is None:
                continue
            if first_day < carline.introduced:
                early.append(f"{carline.name} {first_day}")
            until = carline_on_sale_until(carline)
            if until and last_day > until:
                late.append(f"{carline.name} {last_day}")
            in_window = any(
                (mk.month_start(start) if start else date(1900, 1, 1))
                <= month
                <= (mk.month_end(end) if end else date(9999, 12, 31))
                for start, end in carline.spec.windows
            )
            if not in_window:
                gaps.append(f"{carline.name} {month:%Y-%m}")
        self.add("no sales before launch", not early, ", ".join(early[:6]) or "0 violations")
        self.add("no sales after discontinuation", not late, ", ".join(late[:6]) or "0 violations")
        self.add("no sales while model off market", not gaps, ", ".join(gaps[:6]) or "0 violations")

    def geography(self) -> None:
        cities = {city.name: city for city in mk.CITIES}
        problems = []
        for region_id, zone, city, state, country in self.rows(
            "SELECT region_id, region_name, city, state_code, country FROM automotive.dim_region"
        ):
            known = cities.get(city)
            if known is None or known.state != state or known.zone != zone or country != "India":
                problems.append(f"{region_id}:{city}/{state}/{zone}")
        mismatch = self.scalar(
            "SELECT COUNT(*) FROM automotive.fact_sales f JOIN automotive.dim_dealer d "
            "ON d.dealer_id = f.dealer_id WHERE f.region_id <> d.region_id"
        )
        dealer_city = self.scalar(
            "SELECT COUNT(*) FROM automotive.dim_dealer d JOIN automotive.dim_region r "
            "ON r.region_id = d.region_id WHERE d.city <> r.city"
        )
        multi_state = self.scalar(
            "SELECT COUNT(*) FROM (SELECT city FROM automotive.dim_region GROUP BY city "
            "HAVING COUNT(DISTINCT state_code) > 1) x"
        )
        self.add(
            "valid city/state/region",
            not problems and multi_state == 0,
            ", ".join(problems[:6]) or "every city maps to one state and zone",
        )
        self.add(
            "sale region = dealer region",
            mismatch == 0 and dealer_city == 0,
            f"{mismatch:,} sale mismatches, {dealer_city} dealer city mismatches",
        )

    def network(self) -> None:
        multi_brand = self.scalar(
            "SELECT COUNT(*) FROM (SELECT f.dealer_id FROM automotive.fact_sales f "
            "JOIN automotive.dim_carline c ON c.carline_id = f.carline_id "
            "GROUP BY f.dealer_id HAVING COUNT(DISTINCT c.make) > 1) x"
        )
        multi_dealer = self.scalar(
            "SELECT COUNT(*) FROM (SELECT sales_person_id FROM automotive.fact_sales "
            "GROUP BY 1 HAVING COUNT(DISTINCT dealer_id) > 1) x"
        )
        self.add("dealers are brand-exclusive", multi_brand == 0, f"{multi_brand} multi-brand")
        self.add(
            "salesperson works at one dealer",
            multi_dealer == 0,
            f"{multi_dealer} salespeople at several dealers",
        )
        tiers = {city.name: city.tier for city in mk.CITIES}
        grade_by_tier: dict[int, dict[str, int]] = defaultdict(lambda: defaultdict(int))
        for city, grade, count in self.rows(
            "SELECT city, dealer_grade, COUNT(*) FROM automotive.dim_dealer GROUP BY 1, 2"
        ):
            grade_by_tier[tiers.get(city, 3)][grade] += count

        def share(tier: int, grade: str) -> float:
            total = sum(grade_by_tier[tier].values()) or 1
            return grade_by_tier[tier][grade] / total

        ok = share(1, "A") >= 0.7 and share(2, "B") >= 0.5 and share(3, "C") >= 0.6
        self.add(
            "dealer grade follows city tier",
            ok,
            f"metro A {share(1, 'A'):.0%}, tier-2 B {share(2, 'B'):.0%}, "
            f"tier-3 C {share(3, 'C'):.0%}",
            "realism",
        )

    def values(self) -> None:
        bad = self.scalar(
            "SELECT COUNT(*) FROM automotive.fact_sales WHERE order_qty <= 0 "
            "OR price_per_unit <= 0 OR total_sales < 0 "
            "OR total_sales <> order_qty * price_per_unit"
        )
        first, last = self.rows(
            "SELECT MIN(sales_date), MAX(sales_date) FROM automotive.fact_sales"
        )[0]
        self.add("no negative or inconsistent revenue", bad == 0, f"{bad:,} bad rows")
        self.add(
            "sales dates in range",
            first >= mk.DATA_START and last <= date.today(),
            f"{first} .. {last}",
        )
        bad_targets = self.scalar(
            "SELECT COUNT(*) FROM automotive.dim_targets WHERE target_units < 0 "
            "OR target_revenue < 0 OR make <> ALL(%s)",
            (list(mk.MAKES),),
        )
        bad_forecast = self.scalar(
            "SELECT COUNT(*) FROM automotive.fact_forecast_monthly WHERE forecast_units < 0 "
            "OR forecast_revenue < 0 OR EXTRACT(DAY FROM sales_month) <> 1"
        )
        self.add("targets valid", bad_targets == 0, f"{bad_targets} invalid target rows")
        self.add("forecasts valid", bad_forecast == 0, f"{bad_forecast} invalid forecast rows")

    # ------------------------------------------------------------------ realism

    def _yearly_make_units(self) -> dict[int, dict[str, float]]:
        out: dict[int, dict[str, float]] = defaultdict(dict)
        for year, make, units in self.rows(
            "SELECT EXTRACT(YEAR FROM f.sales_date)::int, c.make, SUM(f.order_qty) "
            "FROM automotive.fact_sales f JOIN automotive.dim_carline c "
            "ON c.carline_id = f.carline_id GROUP BY 1, 2"
        ):
            out[year][make] = float(units)
        return out

    def market_share(self) -> None:
        yearly = self._yearly_make_units()
        full_years = [y for y in sorted(yearly) if y < date.today().year or y < max(yearly)]
        leaders = {y: max(yearly[y], key=yearly[y].get) for y in yearly}
        overall: dict[str, float] = defaultdict(float)
        for makes in yearly.values():
            for make, units in makes.items():
                overall[make] += units
        ranking = sorted(overall, key=overall.get, reverse=True)
        total = sum(overall.values())
        byd = overall.get(mk.BY, 0) / total
        self.add(
            "Maruti Suzuki leads every year",
            all(v == mk.MS for v in leaders.values()),
            f"leaders: {sorted(set(leaders.values()))}",
            "realism",
        )
        self.add(
            "Hyundai second overall",
            ranking[1] == mk.HY,
            "ranking: " + ", ".join(f"{m} {overall[m] / total:.1%}" for m in ranking[:5]),
            "realism",
        )
        self.add("BYD remains niche", byd < 0.01, f"BYD share {byd:.2%}", "realism")

        def share(make: str, years: list[int]) -> float:
            units = sum(yearly[y].get(make, 0) for y in years)
            return units / max(sum(sum(yearly[y].values()) for y in years), 1)

        early = [y for y in full_years if y <= 2019]
        recent = [y for y in yearly if y >= 2022]
        tata_early, tata_recent = share(mk.TA, early), share(mk.TA, recent)
        self.add(
            "Tata grows after 2020",
            tata_recent > 1.8 * tata_early,
            f"{tata_early:.1%} (2015-19) -> {tata_recent:.1%} (2022+)",
            "realism",
        )
        suv = self.scalar(
            "SELECT SUM(CASE WHEN c.car_type = ANY(%s) THEN f.order_qty ELSE 0 END)::float "
            "/ SUM(f.order_qty) FROM automotive.fact_sales f JOIN automotive.dim_carline c "
            "ON c.carline_id = f.carline_id WHERE c.make = %s",
            (list(SUV_TYPES), mk.MA),
        )
        self.add("Mahindra is SUV-led", suv >= 0.8, f"SUV share of Mahindra {suv:.0%}", "realism")

    def ev_curve(self) -> None:
        shares = {
            int(year): float(share)
            for year, share in self.rows(
                "SELECT EXTRACT(YEAR FROM f.sales_date), SUM(CASE WHEN c.engine_type = "
                "'Electric' THEN f.order_qty ELSE 0 END)::float / SUM(f.order_qty) "
                "FROM automotive.fact_sales f JOIN automotive.dim_carline c "
                "ON c.carline_id = f.carline_id GROUP BY 1 ORDER BY 1"
            )
        }
        early = max((shares.get(y, 0) for y in range(2015, 2019)), default=0)
        mid = max((shares.get(y, 0) for y in range(2019, 2022)), default=0)
        rapid = [shares[y] for y in sorted(shares) if y >= 2022]
        rising = all(b > a for a, b in pairwise(rapid))
        ok = early < 0.003 and mid < 0.012 and rising and (rapid[-1] if rapid else 0) >= 0.03
        detail = ", ".join(f"{y}: {s:.2%}" for y, s in shares.items())
        self.add("EV adoption curve", ok, detail, "realism")
        ev_makes = self.rows(
            "SELECT c.make, SUM(f.order_qty) FROM automotive.fact_sales f "
            "JOIN automotive.dim_carline c ON c.carline_id = f.carline_id "
            "WHERE c.engine_type = 'Electric' GROUP BY 1 ORDER BY 2 DESC LIMIT 3"
        )
        leaders = [make for make, _units in ev_makes]
        self.add(
            "EV leaders are Tata / MG / Mahindra",
            bool(leaders) and leaders[0] in {mk.TA, mk.MG},
            f"top EV makes: {leaders}",
            "realism",
        )

    def colours(self) -> None:
        family = {colour.name: colour.family for colour in mk.COLOURS}
        totals: dict[str, int] = defaultdict(int)
        for name, count in self.rows(
            "SELECT c.colour_name, COUNT(*) FROM automotive.fact_sales f "
            "JOIN automotive.dim_color c ON c.colour_id = f.colour_id GROUP BY 1"
        ):
            totals[family.get(name, "other")] += count
        others = [v for k, v in totals.items() if k not in {"white", "silver", "black"}]
        ok = totals["white"] > totals["silver"] > totals["black"] > max(others, default=0)
        ranking = sorted(totals.items(), key=lambda item: -item[1])[:5]
        self.add(
            "colour ranking white > silver > black > rest",
            ok,
            ", ".join(f"{k} {v:,}" for k, v in ranking),
            "realism",
        )

    def seasonality(self) -> None:
        monthly = {
            (int(y), int(m)): float(units)
            for y, m, units in self.rows(
                "SELECT EXTRACT(YEAR FROM sales_date), EXTRACT(MONTH FROM sales_date), "
                "SUM(order_qty) FROM automotive.fact_sales GROUP BY 1, 2"
            )
        }
        festive_years = []
        for year in range(2015, date.today().year):
            months = [monthly.get((year, m), 0) for m in range(1, 13)]
            if year in {2020, 2021} or not all(months):
                continue
            mean = sum(months) / 12
            festive_years.append(max(months[9], months[10]) / mean)
        festive_ok = festive_years and statistics.median(festive_years) >= 1.15
        self.add(
            "festive peak (Oct/Nov)",
            bool(festive_ok),
            f"median peak index {statistics.median(festive_years):.2f}",
            "realism",
        )
        april_2019 = monthly.get((2019, 4), 0)
        april_2020 = monthly.get((2020, 4), 0)
        may_2021 = monthly.get((2021, 5), 0)
        may_2019 = monthly.get((2019, 5), 1)
        self.add(
            "COVID lockdown + second wave",
            april_2020 <= 0.02 * april_2019 and may_2021 < 0.6 * may_2019,
            f"Apr-2020 {april_2020:,.0f} vs Apr-2019 {april_2019:,.0f}; "
            f"May-2021 {may_2021:,.0f} vs May-2019 {may_2019:,.0f}",
            "realism",
        )
        march = [
            monthly.get((y, 3), 0) / monthly.get((y, 2), 1)
            for y in (2016, 2017, 2018, 2019, 2023, 2024, 2025)
        ]
        self.add(
            "financial-year-end push (March > February)",
            statistics.median(march) > 1.05,
            f"median Mar/Feb {statistics.median(march):.2f}",
            "realism",
        )

    def orders_and_prices(self) -> None:
        single, fleet, total = self.rows(
            "SELECT SUM((order_qty = 1)::int), SUM((order_qty >= 5)::int), COUNT(*) "
            "FROM automotive.fact_sales"
        )[0]
        self.add(
            "mostly single-unit orders",
            single / total >= 0.95 and fleet > 0,
            f"{single / total:.1%} qty=1, {fleet:,} fleet orders (qty>=5)",
            "realism",
        )
        prices = dict(
            self.rows(
                "SELECT EXTRACT(YEAR FROM f.sales_date)::int, AVG(f.price_per_unit)::float "
                "FROM automotive.fact_sales f JOIN automotive.dim_carline c "
                "ON c.carline_id = f.carline_id WHERE c.model = 'Swift' "
                "AND c.engine_type = 'Petrol' GROUP BY 1"
            )
        )
        low, high = self.rows(
            "SELECT MIN(price_per_unit), MAX(price_per_unit) FROM automotive.fact_sales"
        )[0]
        inflating = prices and prices.get(2024, 0) > prices.get(2016, 0) * 1.15
        self.add(
            "price inflation over time",
            bool(inflating),
            f"Swift petrol avg 2016 {prices.get(2016, 0):,.0f} -> 2024 "
            f"{prices.get(2024, 0):,.0f}; range {low:,.0f}..{high:,.0f}",
            "realism",
        )
        ev_premium = self.rows(
            "SELECT AVG(CASE WHEN c.engine_type = 'Electric' THEN f.price_per_unit END)::float, "
            "AVG(CASE WHEN c.engine_type = 'Petrol' THEN f.price_per_unit END)::float "
            "FROM automotive.fact_sales f JOIN automotive.dim_carline c "
            "ON c.carline_id = f.carline_id WHERE c.model = 'Nexon'"
        )[0]
        ok = ev_premium[0] and ev_premium[1] and ev_premium[0] > ev_premium[1] * 1.3
        self.add(
            "EV price premium",
            bool(ok),
            f"Nexon EV {ev_premium[0] or 0:,.0f} vs petrol {ev_premium[1] or 0:,.0f}",
            "realism",
        )

    def plans(self) -> None:
        missing = self.scalar(
            "SELECT COUNT(*) FROM (SELECT DISTINCT date_trunc('month', f.sales_date)::date m, "
            "c.make FROM automotive.fact_sales f JOIN automotive.dim_carline c "
            "ON c.carline_id = f.carline_id) s LEFT JOIN automotive.dim_targets t "
            "ON t.year_month = s.m AND t.make = s.make WHERE t.target_id IS NULL"
        )
        achievement = [
            float(ratio)
            for (ratio,) in self.rows(
                "SELECT a.units / NULLIF(t.target_units, 0) FROM automotive.dim_targets t "
                "JOIN (SELECT date_trunc('month', f.sales_date)::date m, c.make, "
                "SUM(f.order_qty)::numeric units FROM automotive.fact_sales f "
                "JOIN automotive.dim_carline c ON c.carline_id = f.carline_id GROUP BY 1, 2) a "
                "ON a.m = t.year_month AND a.make = t.make "
                "WHERE EXTRACT(YEAR FROM t.year_month) NOT IN (2020, 2021) "
                "AND t.year_month < date_trunc('month', CURRENT_DATE) AND t.target_units >= 20"
            )
            if ratio is not None
        ]
        median = statistics.median(achievement) if achievement else 0
        self.add(
            "targets cover every selling month",
            missing <= 3,
            f"{missing} make-months with sales but no target",
            "realism",
        )
        self.add(
            "target achievement realistic",
            0.8 <= median <= 1.1,
            f"median achievement {median:.0%} (excl. 2020-21)",
            "realism",
        )
        errors = [
            abs(float(forecast) - float(actual)) / float(actual)
            for forecast, actual in self.rows(
                "SELECT fc.units, a.units FROM (SELECT sales_month, SUM(forecast_units) units "
                "FROM automotive.fact_forecast_monthly GROUP BY 1) fc JOIN "
                "(SELECT date_trunc('month', sales_date)::date m, SUM(order_qty) units "
                "FROM automotive.fact_sales GROUP BY 1) a ON a.m = fc.sales_month "
                "WHERE EXTRACT(YEAR FROM fc.sales_month) NOT IN (2020, 2021) "
                "AND fc.sales_month < date_trunc('month', CURRENT_DATE)"
            )
            if actual
        ]
        mape = statistics.median(errors) if errors else 1.0
        future = self.scalar(
            "SELECT COUNT(*) FROM automotive.fact_forecast_monthly WHERE sales_month > "
            "(SELECT MAX(sales_date) FROM automotive.fact_sales)"
        )
        self.add(
            "forecast accuracy band",
            0.02 <= mape <= 0.3 and future > 0,
            f"median monthly error {mape:.1%}, {future:,} future forecast rows",
            "realism",
        )

    def all(self) -> list[Check]:
        for name, fn, category in (
            ("row counts", self.row_counts, "integrity"),
            ("null keys", self.null_keys, "integrity"),
            ("orphans", self.orphans, "integrity"),
            ("vehicle rules", self.vehicle_rules, "integrity"),
            ("launch windows", self.launch_windows, "integrity"),
            ("geography", self.geography, "integrity"),
            ("network", self.network, "integrity"),
            ("values", self.values, "integrity"),
            ("market share", self.market_share, "realism"),
            ("ev curve", self.ev_curve, "realism"),
            ("colours", self.colours, "realism"),
            ("seasonality", self.seasonality, "realism"),
            ("orders and prices", self.orders_and_prices, "realism"),
            ("plans", self.plans, "realism"),
        ):
            self.run(name, fn, category)
        return self.checks


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument("--database-url", default=None, help="override the database URL")
    parser.add_argument("--min-rows", type=int, default=1_800_000, help="minimum fact_sales rows")
    parser.add_argument("--json", type=Path, default=None, help="write the report as JSON")
    args = parser.parse_args()
    url = args.database_url
    if not url:
        from app.core.config import get_settings

        url = get_settings().automotive_migrate_database_url
    url = url.replace("postgresql+psycopg://", "postgresql://", 1)

    with psycopg.connect(url) as conn:
        checks = Validator(conn, min_rows=args.min_rows).all()

    width = max(len(check.name) for check in checks)
    for category in ("integrity", "realism"):
        print(f"\n{category.upper()}")
        for check in (c for c in checks if c.category == category):
            status = "PASS" if check.passed else "FAIL"
            print(f"  [{status}] {check.name:<{width}}  {check.detail}")
    failed = [check for check in checks if not check.passed]
    print(f"\n{len(checks) - len(failed)}/{len(checks)} checks passed.")
    if args.json:
        args.json.write_text(
            json.dumps([check.__dict__ for check in checks], indent=2, default=str),
            encoding="utf-8",
        )
    raise SystemExit(1 if failed else 0)


if __name__ == "__main__":
    main()
