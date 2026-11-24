from __future__ import annotations

import copy
import csv
import json
import runpy
from datetime import date
from pathlib import Path

import pytest

from app.analytics.automotive_increment import (
    CUTOFF,
    Digest,
    Inventory,
    calendars,
    canonical,
    daily_weight,
    rake_weights,
    stage,
    validate_rows,
)
from app.analytics.india_auto_generator import TABLE_COLUMNS

ROOT = Path(__file__).resolve().parents[3]


def sources():
    return json.loads((ROOT / "database/automotive/refresh_2026_sources.json").read_text())


def fixture_inventory():
    inv = Inventory("fixture")
    cars = [
        {
            "carline_id": 1,
            "carline_name": "Triber 1.0 Petrol",
            "model": "Triber",
            "make": "Renault",
            "car_type": "MPV",
            "engine_capacity": "1.0",
            "engine_type": "Petrol",
        },
        {
            "carline_id": 2,
            "carline_name": "Creta 1.5 Petrol",
            "model": "Creta",
            "make": "Hyundai",
            "car_type": "Mid SUV",
            "engine_capacity": "1.5",
            "engine_type": "Petrol",
        },
        {
            "carline_id": 3,
            "carline_name": "Nexon EV",
            "model": "Nexon",
            "make": "Tata",
            "car_type": "Compact SUV",
            "engine_capacity": "",
            "engine_type": "Electric",
        },
        {
            "carline_id": 4,
            "carline_name": "Hyryder Hybrid",
            "model": "Hyryder",
            "make": "Toyota",
            "car_type": "Mid SUV",
            "engine_capacity": "1.5",
            "engine_type": "Hybrid",
        },
    ]
    rows = []
    for cid in range(1, 5):
        for day in range(1, 32):
            rows.append(
                {
                    "order_id": len(rows) + 1,
                    "carline_id": cid,
                    "colour_id": 1,
                    "sales_person_id": cid,
                    "region_id": cid,
                    "dealer_id": cid,
                    "sales_date": f"2026-08-{day:02}",
                    "order_qty": 2,
                    "price_per_unit": "900000.00",
                }
            )
    rows.append(dict(rows[0], order_id=999, sales_date="2026-09-01", order_qty=3))
    dims = {
        "dim_carline": cars,
        "dim_region": [
            {"region_id": i, "region_name": z, "city": z, "state_code": z[:2], "country": "India"}
            for i, z in enumerate(["North", "South", "East", "West"], 1)
        ],
        "dim_color": [
            {"colour_id": 1, "colour_name": "White", "rcg_combination": "FFF", "patent_number": ""}
        ],
        "dim_salesman": [
            {
                "sales_person_id": i,
                "first_name": "Demo",
                "last_name": str(i),
                "email": f"demo{i}@example.invalid",
                "corp_id": str(i),
                "active": True,
            }
            for i in range(1, 5)
        ],
        "dim_dealer": [
            {
                "dealer_id": i,
                "dealer_code": str(i),
                "dealer_name": "Synthetic Dealer",
                "region_id": i,
                "city": "Demo",
                "dealer_grade": "A",
                "active": True,
            }
            for i in range(1, 5)
        ],
        "dim_targets": [],
        "fact_sales": rows,
        "fact_forecast_monthly": [],
    }
    for table in TABLE_COLUMNS:
        inv.consume(table, dims[table])
    return inv


def read_rows(folder, table):
    with (folder / f"{table}.csv").open(newline="") as f:
        return list(csv.DictReader(f))


def test_quantity_not_order_count_controls_remaining_units(tmp_path):
    inv = fixture_inventory()
    baseline = copy.deepcopy(inv.identity())
    manifest = stage(inv, sources(), tmp_path / "stage", as_of=date(2026, 11, 24), seed=4)
    september = manifest["allocations"][0]
    assert september["existing_units"] == 3
    assert september["additional_units"] == september["nominal_units"] - 3
    assert inv.identity() == baseline
    assert manifest["live_database_verified"] is False


def test_launch_dates_identity_and_foreign_keys(tmp_path):
    inv = fixture_inventory()
    folder = tmp_path / "stage"
    manifest = stage(inv, sources(), folder, as_of=date(2026, 11, 24), seed=9)
    additions = read_rows(folder, "dim_carline")
    rows = read_rows(folder, "fact_sales")
    assert manifest["new_carlines"] == 2
    assert all(int(r["order_id"]) > 999 for r in rows)
    assert len({r["order_id"] for r in rows}) == len(rows)
    assert all("2026-09-01" <= r["sales_date"] <= "2026-11-23" for r in rows)
    for car in additions:
        sales = [r for r in rows if r["carline_id"] == car["carline_id"]]
        start = next(
            s["available_from"]
            for s in sources()["additions"]
            if s["carline_name"] == car["carline_name"]
        )
        assert all(r["sales_date"] >= start for r in sales)
    windows = calendars(inv)
    windows.update(
        {
            int(car["carline_id"]): (date.fromisoformat(spec["available_from"]), None)
            for car in additions
            for spec in sources()["additions"]
            if car["carline_name"] == spec["carline_name"]
        }
    )
    bad = [dict(rows[0], region_id=99)]
    with pytest.raises(ValueError, match="region"):
        validate_rows(inv, additions, bad, windows, date(2026, 11, 23))
    with pytest.raises(ValueError, match="window"):
        validate_rows(
            inv, additions, [dict(rows[0], sales_date=str(CUTOFF))], windows, date(2026, 11, 23)
        )


def test_staging_is_deterministic_and_does_not_overwrite(tmp_path):
    inv = fixture_inventory()
    a = stage(inv, sources(), tmp_path / "a", as_of=date(2026, 11, 24), seed=9)
    b = stage(inv, sources(), tmp_path / "b", as_of=date(2026, 11, 24), seed=9)
    assert a == b
    with pytest.raises(ValueError, match="immutable"):
        stage(inv, sources(), tmp_path / "a", as_of=date(2026, 11, 24), seed=9)


def test_overshoot_preserved_without_negative_rows(tmp_path):
    inv = fixture_inventory()
    inv.units[("2026-09", 1, 1)] = 2000
    result = stage(inv, sources(), tmp_path / "a", as_of=date(2026, 11, 24), seed=9)
    september = result["allocations"][0]
    assert september["existing_units"] == 2000
    assert september["additional_units"] == 0
    assert september["after_units"] == 2000
    assert json.loads((tmp_path / "a/bucket_conflicts.json").read_text())


def test_fingerprint_canonicalises_database_and_csv_values():
    inv = fixture_inventory()
    row = inv.dimensions["dim_carline"][0]
    assert canonical("dim_carline", row) == canonical("dim_carline", dict(row, engine_capacity=1))
    a, b = Digest(), Digest()
    for x in ["a", "b", "a"]:
        a.add(x)
    for x in ["b", "a", "a"]:
        b.add(x)
    assert a.value() == b.value()
    b.add("a")
    assert a.value() != b.value()


def test_festive_assumptions_are_regional_and_return_to_normal():
    for zone in ["North", "South", "East", "West"]:
        assert daily_weight(date(2026, 11, 6), zone, "Petrol") > 2 * daily_weight(
            date(2026, 11, 20), zone, "Petrol"
        )
    assert daily_weight(date(2026, 11, 6), "North", "Petrol") != daily_weight(
        date(2026, 11, 6), "South", "Petrol"
    )


def test_no_future_as_of_or_stale_research(tmp_path):
    with pytest.raises(ValueError, match="stale"):
        stage(fixture_inventory(), sources(), tmp_path / "a", as_of=date(2026, 12, 1), seed=9)


def test_zero_prior_month_is_not_silently_fabricated(tmp_path):
    inv = fixture_inventory()
    inv.monthly["2026-08"]["units"] = 0
    with pytest.raises(ValueError, match="August"):
        stage(inv, sources(), tmp_path / "a", as_of=date(2026, 11, 24), seed=9)


def test_csv_candidate_and_wrong_approval_cannot_reach_database(tmp_path, monkeypatch):
    folder = tmp_path / "candidate"
    manifest = stage(fixture_inventory(), sources(), folder, as_of=date(2026, 11, 24), seed=7)
    cli = runpy.run_path(str(ROOT / "scripts/refresh_automotive_increment.py"))

    def forbidden_connect(*args, **kwargs):
        raise AssertionError("A CSV candidate must not open a write connection")

    monkeypatch.setitem(cli["mutate"].__globals__, "connect", forbidden_connect)
    with pytest.raises(ValueError, match="exact reviewed batch"):
        cli["mutate"](folder, "unapproved")
    with pytest.raises(ValueError, match="CSV candidates"):
        cli["mutate"](folder, manifest["batch_id"])


def test_modified_batch_files_fail_checksum_validation(tmp_path):
    folder = tmp_path / "candidate"
    stage(fixture_inventory(), sources(), folder, as_of=date(2026, 11, 24), seed=7)
    cli = runpy.run_path(str(ROOT / "scripts/refresh_automotive_increment.py"))
    with (folder / "fact_sales.csv").open("a") as handle:
        handle.write("tampered\n")
    with pytest.raises(ValueError, match="Checksum mismatch"):
        cli["verify_files"](folder)


def test_make_and_fuel_calibration_are_fitted_together():
    cars = {
        1: {"make": "A", "engine_type": "Petrol"},
        2: {"make": "A", "engine_type": "Electric"},
        3: {"make": "B", "engine_type": "Petrol"},
        4: {"make": "B", "engine_type": "Hybrid"},
    }
    weights = rake_weights(
        {1: 10, 2: 1, 3: 5, 4: 2},
        cars,
        {"A": 60, "B": 40},
        {"Petrol": 50, "Electric": 20, "Hybrid": 30},
    )
    assert weights[1] + weights[2] == pytest.approx(0.6, abs=0.001)
    assert weights[2] == pytest.approx(0.2, abs=0.001)
    assert weights[4] == pytest.approx(0.3, abs=0.001)


async def test_refreshed_vehicle_values_use_existing_governed_planner():
    from app.core.config import Industry, Settings
    from app.semantic.service import SemanticService
    from app.services.chat.pipeline import plan_turn
    from app.services.chat.value_dictionary import build_snapshot

    pack = await SemanticService(Settings()).get_pack(Industry.AUTOMOTIVE)
    snapshot = build_snapshot(
        Industry.AUTOMOTIVE,
        [
            ("automotive.dim_carline.model", "Bayon", 100),
            ("automotive.dim_carline.carline_name", "Triber 100PS 1.0 Petrol", 100),
        ],
        pack=pack,
    )
    for question, literal in [
        ("Show units sold for Hyundai Bayon in November 2026", "Bayon"),
        ("Show units sold for Triber 100PS in October 2026", "Triber 100PS 1.0 Petrol"),
    ]:
        turn = plan_turn(
            Industry.AUTOMOTIVE, question, snapshot=snapshot, pack=pack, allowed_schema=None
        )
        assert literal in str(turn.resolution.filters())
        assert turn.governed_sql is not None, turn.validation_error or turn.clarification
        assert literal in turn.governed_sql
