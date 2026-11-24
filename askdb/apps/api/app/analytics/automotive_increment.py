"""Append-only, evidence-labelled Automotive demo increments (no database writes).

Original generator and analytical formulas are deliberately reused, not rebuilt.
The database adapter must recheck this inventory under write-blocking table locks.
"""

from __future__ import annotations

import calendar
import csv
import hashlib
import html
import json
import math
import random
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

from app.analytics.india_auto_generator import TABLE_COLUMNS, build_carlines, carline_on_sale_until

CUTOFF = date(2026, 8, 31)
START = CUTOFF + timedelta(days=1)
VERSION = "1.0"
DIMENSIONS = tuple(t for t in TABLE_COLUMNS if t.startswith("dim_"))
NUMBERS = frozenset(
    {
        "order_id",
        "carline_id",
        "colour_id",
        "sales_person_id",
        "region_id",
        "dealer_id",
        "target_id",
        "order_qty",
        "price_per_unit",
        "engine_capacity",
        "target_units",
        "target_revenue",
        "forecast_units",
        "forecast_revenue",
    }
)


def canonical(table: str, row: dict) -> str:
    values = []
    for name in TABLE_COLUMNS[table]:
        v = row.get(name)
        if v is None or v == "":
            v = None
        elif name == "active":
            v = str(v).lower() in {"true", "t", "1"}
        elif name in NUMBERS:
            v = format(Decimal(str(v)).normalize(), "f")
        else:
            v = str(v)
        values.append(v)
    return json.dumps(values, ensure_ascii=False, separators=(",", ":"))


@dataclass
class Digest:
    """Order-independent row fingerprint with multiplicity, not a dedup key."""

    count: int = 0
    total: int = 0

    def add(self, text: str) -> None:
        self.count += 1
        self.total = (self.total + int.from_bytes(hashlib.sha256(text.encode()).digest())) % (
            1 << 256
        )

    def value(self) -> dict:
        return {"rows": self.count, "sha256_multiset": f"{self.total:064x}"}


def empty_stat() -> dict:
    return {"orders": 0, "units": 0, "revenue": Decimal(0)}


def add_stat(stat: dict, row: dict) -> None:
    qty = int(row["order_qty"])
    stat["orders"] += 1
    stat["units"] += qty
    stat["revenue"] += qty * Decimal(str(row["price_per_unit"]))


def enabled(row: dict) -> bool:
    return str(row["active"]).lower() in {"true", "t", "1"}


def natural(row: dict) -> tuple:
    return (
        row["make"],
        row["model"],
        row["engine_type"],
        str(Decimal(str(row["engine_capacity"])).normalize())
        if row.get("engine_capacity") not in (None, "")
        else None,
    )


@dataclass
class Inventory:
    source_kind: str
    dimensions: dict[str, list[dict]] = field(default_factory=dict)
    fingerprints: dict[str, dict] = field(default_factory=dict)
    protected: Digest = field(default_factory=Digest)
    monthly: dict = field(default_factory=lambda: defaultdict(empty_stat))
    daily: dict = field(default_factory=lambda: defaultdict(empty_stat))
    units: Counter = field(default_factory=Counter)
    reference: Counter = field(default_factory=Counter)
    reference_price: dict = field(default_factory=lambda: defaultdict(lambda: [Decimal(0), 0]))
    rosters: dict = field(default_factory=lambda: defaultdict(Counter))
    max_order_id: int = 0

    def consume(self, table: str, rows) -> None:
        digest = Digest()
        if table in DIMENSIONS:
            self.dimensions[table] = []
        cars = {int(r["carline_id"]): r for r in self.dimensions.get("dim_carline", [])}
        for row in rows:
            digest.add(canonical(table, row))
            if table in DIMENSIONS:
                self.dimensions[table].append(dict(row))
            if table != "fact_sales":
                continue
            d = date.fromisoformat(str(row["sales_date"]))
            self.max_order_id = max(self.max_order_id, int(row["order_id"]))
            if d <= CUTOFF:
                self.protected.add(canonical(table, row))
            if d < date(2026, 6, 1):
                continue
            month = d.strftime("%Y-%m")
            add_stat(self.monthly[month], row)
            add_stat(self.daily[d.isoformat()], row)
            cid, rid, qty = int(row["carline_id"]), int(row["region_id"]), int(row["order_qty"])
            self.units[(month, cid, rid)] += qty
            car = cars[cid]
            if date(2026, 8, 1) <= d <= CUTOFF:
                self.reference[(cid, rid)] += qty
                self.reference_price[cid][0] += qty * Decimal(str(row["price_per_unit"]))
                self.reference_price[cid][1] += qty
            if d <= CUTOFF:
                self.rosters[car["make"]][(int(row["dealer_id"]), int(row["sales_person_id"]))] += (
                    qty
                )
        self.fingerprints[table] = digest.value()

    def identity(self) -> dict:
        return {
            "tables": self.fingerprints,
            "protected": self.protected.value(),
            "max_order_id": self.max_order_id,
        }

    def coverage(self) -> dict:
        cars = {int(r["carline_id"]): r for r in self.dimensions["dim_carline"]}
        coverage = {}
        for month in sorted(self.monthly):
            keys = [(c, r) for (m, c, r), n in self.units.items() if m == month and n]
            coverage[month] = {
                **self.monthly[month],
                "makes": sorted({cars[c]["make"] for c, _ in keys}),
                "models": len({(cars[c]["make"], cars[c]["model"]) for c, _ in keys}),
                "fuels": sorted({cars[c]["engine_type"] for c, _ in keys}),
                "regions": len({r for _, r in keys}),
            }
        return {
            "source_kind": self.source_kind,
            "monthly": coverage,
            "daily": self.daily,
            "sparse_days": [
                d
                for d, s in sorted(self.daily.items())
                if d >= START.isoformat() and s["orders"] <= 100
            ],
            "september_substantial": self.monthly.get("2026-09", {}).get("orders", 0) > 100,
        }


def read_csv_inventory(folder: Path, source_kind: str = "csv_reference") -> Inventory:
    inventory = Inventory(source_kind)
    for table in TABLE_COLUMNS:
        with (folder / f"{table}.csv").open(encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            if tuple(reader.fieldnames or ()) != TABLE_COLUMNS[table]:
                raise ValueError(f"Unexpected columns for {table}")
            inventory.consume(table, reader)
    return inventory


def json_write(path: Path, value: Any) -> None:
    path.write_text(
        json.dumps(value, default=str, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )


def write_csv(path: Path, columns, rows) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)


def apportion(total: int, weights: dict) -> dict:
    weights = {k: w for k, w in weights.items() if w > 0}
    if total < 0 or (total and not weights):
        raise ValueError("No eligible allocation for requested units")
    denominator = sum(weights.values()) or 1
    exact = {k: total * w / denominator for k, w in weights.items()}
    result = {k: int(v) for k, v in exact.items()}
    ranked = sorted(exact, key=lambda k: (-(exact[k] - result[k]), str(k)))
    for k in ranked[: total - sum(result.values())]:
        result[k] += 1
    return result


def rake_weights(weights: dict, cars: dict, make_targets: dict, fuel_targets: dict) -> dict:
    """Fit compatible make/fuel margins without introducing unsupported carlines.

    Published margins describe different coverage from this limited sample; their
    normalised values are calibration goals, not evidence of model-level actuals.
    """
    values = dict(weights)
    for _ in range(100):
        for dimension, targets in (("make", make_targets), ("engine_type", fuel_targets)):
            groups = defaultdict(list)
            for cid in values:
                groups[cars[cid][dimension]].append(cid)
            denominator = sum(targets.get(k, 0) for k in groups)
            if not denominator:
                raise ValueError("No supported published calibration margin")
            for key, ids in groups.items():
                current = sum(values[cid] for cid in ids)
                target = targets.get(key, 0) / denominator
                if current:
                    for cid in ids:
                        values[cid] *= target / current
    return values


def daily_weight(d: date, zone: str, fuel: str) -> float:
    """Explicit synthetic daily/region assumptions, never claimed as actuals."""
    base = (0.9, 0.85, 0.95, 0.95, 1.0, 1.2, 1.25)[d.weekday()]
    amplitude = {"North": 3.2, "West": 2.7, "East": 2.2, "South": 1.9}.get(zone, 2.2)
    if fuel == "Electric":
        amplitude *= 0.9
    distance = abs((d - date(2026, 11, 6)).days)
    bump = amplitude * math.exp(-((distance / 3.5) ** 2))
    build = 0.35 if date(2026, 10, 28) <= d <= date(2026, 11, 4) else 0
    return base * (1 + bump + build)


def calendars(inventory: Inventory) -> dict:
    known = {
        natural(
            {
                "make": c.spec.make,
                "model": c.spec.model,
                "engine_type": c.engine_type,
                "engine_capacity": c.capacity,
            }
        ): c
        for c in build_carlines()
    }
    result = {}
    for row in inventory.dimensions["dim_carline"]:
        car = known.get(natural(row))
        if car:
            result[int(row["carline_id"])] = (car.introduced, carline_on_sale_until(car))
    return result


def stage(
    inventory: Inventory,
    sources: dict,
    out: Path,
    *,
    as_of: date,
    seed: int,
    database_identity: list | None = None,
) -> dict:
    if as_of > date.fromisoformat(sources["as_of"]):
        raise ValueError("Research is stale for this as-of date; update source evidence first")
    end = as_of - timedelta(days=1)
    if end < START:
        raise ValueError("Increment must begin after the protected cutoff")
    if any(d >= as_of.isoformat() for d in inventory.daily):
        raise ValueError("Existing current/future-dated sales require review before staging")
    if out.exists():
        raise ValueError("Use a new staging directory; existing batches are immutable")
    out.mkdir(parents=True)
    rng = random.Random(seed)
    cars = {int(r["carline_id"]): dict(r) for r in inventory.dimensions["dim_carline"]}
    dealers = {int(r["dealer_id"]): r for r in inventory.dimensions["dim_dealer"]}
    people = {int(r["sales_person_id"]): r for r in inventory.dimensions["dim_salesman"]}
    regions = {int(r["region_id"]): r for r in inventory.dimensions["dim_region"]}
    colours = [int(r["colour_id"]) for r in inventory.dimensions["dim_color"]]
    roster = {
        make: {
            pair: n
            for pair, n in pairs.items()
            if enabled(dealers[pair[0]]) and enabled(people[pair[1]])
        }
        for make, pairs in inventory.rosters.items()
    }
    windows = calendars(inventory)
    additions, new_specs = [], {}
    for spec in sources["additions"]:
        if date.fromisoformat(spec["available_from"]) > end:
            continue
        if not roster.get(spec["make"]):
            raise ValueError(f"No validated active dealer/salesperson roster for {spec['make']}")
        existing_id = next(
            (
                cid
                for cid, r in cars.items()
                if r["carline_name"] == spec["carline_name"] and r["make"] == spec["make"]
            ),
            None,
        )
        cid = existing_id if existing_id is not None else max(cars, default=0) + 1
        if existing_id is None:
            row = {k: spec[k] for k in TABLE_COLUMNS["dim_carline"] if k != "carline_id"}
            row["carline_id"] = cid
            cars[cid] = row
            additions.append(row)
        new_specs[cid] = spec
        windows[cid] = (date.fromisoformat(spec["available_from"]), None)
    anchor = inventory.monthly.get("2026-08", {}).get("units", 0)
    if not anchor:
        raise ValueError("A validated August 2026 sample is required for scaling")
    september = round(anchor * sources["assumptions"]["september_vs_august_sample"])
    october = round(
        september
        * sources["benchmarks"]["2026-10"]["pv_units"]
        / sources["benchmarks"]["2026-09"]["pv_units"]
    )
    nominal = {
        "2026-09": september,
        "2026-10": october,
        "2026-11": round(
            october * sources["assumptions"]["november_vs_october_full_month_scenario"]
        ),
    }
    rows, allocations, conflicts = [], [], []
    next_id = inventory.max_order_id
    for month, full_total in nominal.items():
        first = date.fromisoformat(month + "-01")
        last = date(first.year, first.month, calendar.monthrange(first.year, first.month)[1])
        if first > end:
            continue
        last_in_scope = min(last, end)
        dates = [first + timedelta(days=i) for i in range((last_in_scope - first).days + 1)]
        full_dates = [first + timedelta(days=i) for i in range((last - first).days + 1)]
        ratio = sum(daily_weight(d, "West", "Petrol") for d in dates) / sum(
            daily_weight(d, "West", "Petrol") for d in full_dates
        )
        total = round(full_total * ratio)
        weights = {}
        fuel = sources["benchmarks"].get(month, sources["benchmarks"]["2026-10"])["fuel_pct"]
        for cid, car in sorted(cars.items()):
            if cid not in windows or not roster.get(car["make"]):
                continue
            lo, hi = windows[cid]
            if lo > last_in_scope or (hi and hi < first):
                continue
            # Existing observed model/fuel/region distribution is the prior. OEM
            # and supported fuel benchmarks reweight it; no model-level actuals implied.
            make_ref = sum(
                n for (c, _r), n in inventory.reference.items() if cars[c]["make"] == car["make"]
            )
            base = sum(n for (c, _r), n in inventory.reference.items() if c == cid)
            if cid in new_specs:
                base = make_ref * new_specs[cid]["within_make_weight"]
            if base <= 0:
                continue
            make_units = sources["october_make_units"].get(car["make"])
            make_factor = (
                make_units / max(make_ref, 1)
                if make_units
                else sources["benchmarks"]["2026-10"]["pv_units"] / anchor
            )
            observed_fuel = sum(
                n
                for (c, _r), n in inventory.reference.items()
                if cars[c]["engine_type"] == car["engine_type"]
            )
            fuel_factor = fuel.get(car["engine_type"], 0) / max(observed_fuel, 1)
            # Available days explicitly limit newly launched vehicles.
            available = sum(lo <= d and (hi is None or d <= hi) for d in dates) / len(dates)
            weights[cid] = base * make_factor * fuel_factor * available
        make_targets = {}
        for cid in weights:
            make = cars[cid]["make"]
            prior = sum(n for (c, _r), n in inventory.reference.items() if cars[c]["make"] == make)
            make_targets[make] = sources["october_make_units"].get(
                make, prior / anchor * sources["benchmarks"]["2026-10"]["pv_units"]
            )
        weights = rake_weights(weights, cars, make_targets, fuel)
        desired = apportion(total, weights)
        current = Counter()
        for (m, cid, _rid), units in inventory.units.items():
            if m == month:
                current[cid] += units
        # Preserve overshoots and also avoid filling the same month twice. The
        # nominal total is raised only if existing rows already exceed it.
        actual_target = max(total, sum(current.values()))
        residual = {cid: max(0, n - current[cid]) for cid, n in desired.items()}
        needed = actual_target - sum(current.values())
        if needed and not any(residual.values()):
            residual = weights
        additional = apportion(needed, residual)
        for cid, existing in current.items():
            if existing > desired.get(cid, 0):
                conflicts.append(
                    {
                        "month": month,
                        "carline_id": cid,
                        "existing_units": existing,
                        "nominal_bucket_units": desired.get(cid, 0),
                        "action": "preserved",
                    }
                )
        month_added = 0
        for cid, qty in additional.items():
            if not qty:
                continue
            car = cars[cid]
            pairs = roster[car["make"]]
            pair_list = sorted(pairs)
            pair_weights = [pairs[p] for p in pair_list]
            by_region = Counter()
            for (c, r), n in inventory.reference.items():
                if cars[c]["make"] == car["make"]:
                    by_region[r] += n
            mean = (
                Decimal(new_specs[cid]["mean_price_inr"])
                if cid in new_specs
                else inventory.reference_price[cid][0] / inventory.reference_price[cid][1]
            )
            mean *= Decimal("1.002") ** (first.month - 8)
            lo, hi = windows[cid]
            allowed_days = [d for d in dates if lo <= d and (hi is None or d <= hi)]
            # Exact day/region unit allocation makes seasonality reproducible.
            day_weights = {
                d: sum(
                    daily_weight(d, regions[r]["region_name"], car["engine_type"]) * n
                    for r, n in by_region.items()
                )
                for d in allowed_days
            }
            for d, daily_qty in apportion(qty, day_weights).items():
                remaining = daily_qty
                while remaining:
                    dealer_id, person_id = rng.choices(pair_list, pair_weights, k=1)[0]
                    amount = min(remaining, 1 if rng.random() < 0.96 else rng.randint(2, 3))
                    price = (mean * Decimal(str(rng.uniform(0.94, 1.06)))).quantize(Decimal("0.01"))
                    next_id += 1
                    rows.append(
                        {
                            "order_id": next_id,
                            "carline_id": cid,
                            "colour_id": rng.choice(colours),
                            "sales_person_id": person_id,
                            "region_id": int(dealers[dealer_id]["region_id"]),
                            "dealer_id": dealer_id,
                            "sales_date": d.isoformat(),
                            "order_qty": amount,
                            "price_per_unit": str(price),
                        }
                    )
                    remaining -= amount
                    month_added += amount
        allocations.append(
            {
                "month": month,
                "period_end": last_in_scope.isoformat(),
                "status": "MTD synthetic" if last_in_scope < last else "complete synthetic",
                "nominal_units": total,
                "existing_units": sum(current.values()),
                "additional_units": month_added,
                "after_units": sum(current.values()) + month_added,
            }
        )
    write_csv(out / "dim_carline.csv", TABLE_COLUMNS["dim_carline"], additions)
    write_csv(out / "fact_sales.csv", TABLE_COLUMNS["fact_sales"], rows)
    write_csv(
        out / "reference_model_calendar.csv",
        ["carline_id", "carline_name", "make", "model", "on_sale_from", "source", "basis"],
        [
            {
                "carline_id": cid,
                "carline_name": cars[cid]["carline_name"],
                "make": cars[cid]["make"],
                "model": cars[cid]["model"],
                "on_sale_from": s["available_from"],
                "source": s["source"],
                "basis": s["availability_basis"],
            }
            for cid, s in new_specs.items()
        ],
    )
    json_write(out / "sources.json", sources)
    json_write(out / "coverage_before.json", inventory.coverage())
    json_write(out / "bucket_conflicts.json", conflicts)
    facts = validate_rows(inventory, additions, rows, windows, end)
    json_write(out / "validation.json", facts)
    manifest = {
        "version": VERSION,
        "as_of": as_of.isoformat(),
        "start": START.isoformat(),
        "end": end.isoformat(),
        "protected_cutoff": CUTOFF.isoformat(),
        "seed": seed,
        "source_kind": inventory.source_kind,
        "live_database_verified": inventory.source_kind == "database",
        "database_identity": database_identity,
        "baseline": inventory.identity(),
        "allocations": allocations,
        "new_carlines": len(additions),
        "new_orders": len(rows),
        "new_units": sum(int(r["order_qty"]) for r in rows),
        "warnings": [
            "Synthetic sample, not genuine transactions or national totals.",
            sources["assumptions"]["unsupported_fuel"],
            "Targets and forecasts are preserved unchanged.",
            "Existing bucket overshoots preserved; see bucket_conflicts.json.",
        ],
    }
    if inventory.coverage()["september_substantial"]:
        manifest["warnings"].append(
            "Substantial September coverage exists; all those rows are preserved."
        )
    if inventory.source_kind != "database":
        manifest["warnings"].append(
            "CSV candidate only: export live database and restage before approval/load."
        )
    manifest["files"] = {
        p.name: hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(out.iterdir())
        if p.is_file()
    }
    manifest["batch_id"] = (
        "auto-" + hashlib.sha256(json.dumps(manifest, sort_keys=True).encode()).hexdigest()[:20]
    )
    write_report(inventory, rows, manifest, out)
    manifest["files"] = {
        p.name: hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(out.iterdir())
        if p.is_file()
    }
    json_write(out / "manifest.json", manifest)
    return manifest


def validate_rows(
    inventory: Inventory, additions: list[dict], rows: list[dict], windows: dict, end: date
) -> dict:
    cars = {int(r["carline_id"]): r for r in inventory.dimensions["dim_carline"] + additions}
    dealers = {int(r["dealer_id"]): r for r in inventory.dimensions["dim_dealer"]}
    people = {int(r["sales_person_id"]): r for r in inventory.dimensions["dim_salesman"]}
    colours = {int(r["colour_id"]) for r in inventory.dimensions["dim_color"]}
    ids = set()
    for row in rows:
        oid = int(row["order_id"])
        cid, did, sid = (int(row[n]) for n in ("carline_id", "dealer_id", "sales_person_id"))
        if oid <= inventory.max_order_id or oid in ids:
            raise ValueError("Duplicate or overlapping order identity")
        ids.add(oid)
        d = date.fromisoformat(str(row["sales_date"]))
        lo, hi = windows[cid]
        if not START <= d <= end or d < lo or (hi and d > hi):
            raise ValueError("Sale outside refresh/availability window")
        if int(row["colour_id"]) not in colours or int(row["region_id"]) != int(
            dealers[did]["region_id"]
        ):
            raise ValueError("Invalid colour or dealer/region relationship")
        if not enabled(people[sid]) or not enabled(dealers[did]):
            raise ValueError("Inactive dealer or salesperson")
        if (did, sid) not in inventory.rosters[cars[cid]["make"]]:
            raise ValueError("Unverified make/dealer/salesperson relationship")
        if int(row["order_qty"]) <= 0 or Decimal(str(row["price_per_unit"])) <= 0:
            raise ValueError("Invalid quantity or price")
    return {
        "passed": True,
        "orders_checked": len(rows),
        "protected_history_writes": 0,
        "checks": [
            "identity",
            "cutoff",
            "future_dates",
            "launch_windows",
            "foreign_keys",
            "active_roster",
            "brand_relationship",
            "positive_quantity_price",
        ],
        "not_verified": [
            "live PostgreSQL and office gateway",
            "UI acceptance",
            "national model-level actuals",
        ],
    }


def write_report(inventory: Inventory, rows: list[dict], manifest: dict, out: Path) -> None:
    daily = {
        d: dict(s) for d, s in inventory.daily.items() if START.isoformat() <= d <= manifest["end"]
    }
    for row in rows:
        add_stat(daily.setdefault(row["sales_date"], empty_stat()), row)
    maximum = max((v["units"] for v in daily.values()), default=1)
    bars = "".join(
        f'<div title="{d}: {s["units"]} units" '
        f'style="height:{max(1, s["units"] / maximum * 150):.1f}px;'
        f"background:{'#7952b3' if '2026-11-04' <= d <= '2026-11-09' else '#087f9d'};"
        'flex:1"></div>'
        for d, s in sorted(daily.items())
    )
    body = "".join(
        "<tr>"
        + "".join(
            f"<td>{html.escape(str(a[k]))}</td>"
            for k in ["month", "status", "existing_units", "additional_units", "after_units"]
        )
        + "</tr>"
        for a in manifest["allocations"]
    )
    text = f"""<!doctype html><html><meta charset="utf-8"><title>Automotive increment review</title>
<style>
body{{font:16px Aptos,Arial,sans-serif;margin:40px;max-width:1100px;color:#142238}}
td,th{{padding:12px;border-bottom:1px solid #d5dee9;text-align:left}}
table{{border-collapse:collapse;width:100%}}p{{line-height:1.6}}
.chart{{display:flex;gap:2px;align-items:flex-end;height:160px}}
</style>
<h1>Automotive increment review</h1><p><b>Market-informed synthetic sample.</b>
{html.escape(manifest["source_kind"])}. Batch {manifest["batch_id"]}.
Existing rows are retained. Protected cutoff: {CUTOFF}. New sales end: {manifest["end"]}.</p>
<table><tr><th>Month</th><th>Period</th><th>Existing units</th>
<th>Added units</th><th>After units</th></tr>{body}</table>
<h2>Daily units: existing plus proposed</h2><div class="chart">{bars}</div>
<p>September through November MTD. Purple: 4-9 November. Diwali: 8 November.
Daily shape and uplift are synthetic assumptions;
monthly reference figures are separate published benchmarks.</p>
<h2>Review limitations</h2>
<ul>{"".join("<li>" + html.escape(w) + "</li>" for w in manifest["warnings"])}</ul>
<p>Review sources.json, coverage_before.json, reference_model_calendar.csv,
bucket_conflicts.json and validation.json alongside this report.
CSV candidates cannot be applied to a database.</p></html>"""
    (out / "review.html").write_text(text, encoding="utf-8")
    write_csv(
        out / "daily_after.csv",
        ["date", "orders", "units", "revenue"],
        [{"date": d, **s} for d, s in sorted(daily.items())],
    )
    monthly = defaultdict(empty_stat)
    for d, values in daily.items():
        for field_name in ("orders", "units", "revenue"):
            monthly[d[:7]][field_name] += values[field_name]
    write_csv(
        out / "monthly_after.csv",
        ["month", "status", "orders", "units", "revenue"],
        [
            {
                "month": m,
                "status": next(a["status"] for a in manifest["allocations"] if a["month"] == m),
                **s,
            }
            for m, s in sorted(monthly.items())
        ],
    )
    sources = json.loads((out / "sources.json").read_text(encoding="utf-8"))
    cars = {int(r["carline_id"]): r for r in inventory.dimensions["dim_carline"]}
    with (out / "dim_carline.csv").open(encoding="utf-8", newline="") as handle:
        cars.update({int(r["carline_id"]): r for r in csv.DictReader(handle)})
    before, added = Counter(), Counter()
    for (m, cid, _rid), units in inventory.units.items():
        if START.isoformat()[:7] <= m <= manifest["end"][:7]:
            for dimension in ("make", "engine_type"):
                before[(m, dimension, cars[cid][dimension])] += units
    for r in rows:
        for dimension in ("make", "engine_type"):
            added[(r["sales_date"][:7], dimension, cars[int(r["carline_id"])][dimension])] += int(
                r["order_qty"]
            )
    comparison = []
    for key in sorted(before.keys() | added.keys()):
        m, dimension, value = key
        published = None
        conditional = None
        if m in sources["benchmarks"] and dimension == "engine_type":
            shares = sources["benchmarks"][m]["fuel_pct"]
            published = shares.get(value)
            if published is not None:
                supported_total = sum(v for k, v in shares.items() if k != "CNG/LPG")
                conditional = round(published / supported_total * 100, 3)
        if m == "2026-10" and dimension == "make":
            n = sources["october_make_units"].get(value)
            if n is not None:
                published = round(n / sources["benchmarks"][m]["pv_units"] * 100, 3)
        comparison.append(
            {
                "month": m,
                "dimension": dimension,
                "value": value,
                "existing_units": before[key],
                "added_units": added[key],
                "after_units": before[key] + added[key],
                "after_pct": round((before[key] + added[key]) / monthly[m]["units"] * 100, 3),
                "published_pct": published,
                "conditional_supported_fuel_pct": conditional,
                "basis": "No November monthly actual; modelled scenario"
                if m == "2026-11"
                else "Published reference vs synthetic sample; variances retained",
            }
        )
    if comparison:
        write_csv(out / "benchmark_comparison.csv", list(comparison[0]), comparison)
