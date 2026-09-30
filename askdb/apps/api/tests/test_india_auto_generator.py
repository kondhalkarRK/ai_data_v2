"""Small-scale run of the Indian automotive market generator: catalog and relational integrity."""

from __future__ import annotations

import csv
from collections import Counter
from datetime import date
from pathlib import Path

import pytest

from app.analytics import india_auto_market as mk
from app.analytics.india_auto_generator import (
    TABLE_COLUMNS,
    GeneratorConfig,
    IndiaAutoDatasetGenerator,
    build_carlines,
    carline_on_sale_until,
)

END = date(2026, 9, 30)
SPLIT = date(2026, 6, 30)


def _rows(folder: Path, table: str) -> list[dict[str, str]]:
    path = folder / f"{table}.csv"
    if not path.exists():
        return []
    with path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        assert tuple(reader.fieldnames or ()) == TABLE_COLUMNS[table]
        return list(reader)


def _both(out: Path, table: str) -> list[dict[str, str]]:
    return _rows(out, table) + _rows(out / "increment", table)


@pytest.fixture(scope="module")
def dataset(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, object]:
    out = tmp_path_factory.mktemp("india_auto")
    config = GeneratorConfig(rows=40_000, end_date=END, split_date=SPLIT, forecast_horizon=3)
    report = IndiaAutoDatasetGenerator(config).generate(out)
    return out, report


def test_catalog_is_consistent() -> None:
    carlines = build_carlines()
    assert len({c.name for c in carlines}) == len(carlines)
    for carline in carlines:
        spec = carline.spec
        assert spec.car_type in mk.CAR_TYPES
        assert carline.engine_type in mk.ENGINE_TYPES
        if carline.engine_type == "Electric":
            assert carline.capacity is None
        else:
            assert carline.capacity is not None and 0.6 <= carline.capacity <= 6.5
            assert round(carline.capacity, 1) == carline.capacity


def test_row_volume_and_split(dataset: tuple[Path, object]) -> None:
    out, _ = dataset
    base, extra = _rows(out, "fact_sales"), _rows(out / "increment", "fact_sales")
    assert 30_000 <= len(base) + len(extra) <= 50_000
    assert base and extra
    assert max(r["sales_date"] for r in base) <= SPLIT.isoformat()
    assert min(r["sales_date"] for r in extra) > SPLIT.isoformat()
    assert max(r["sales_date"] for r in extra) <= END.isoformat()


def test_relational_integrity(dataset: tuple[Path, object]) -> None:
    out, _ = dataset
    carlines = {r["carline_id"]: r for r in _both(out, "dim_carline")}
    regions = {r["region_id"] for r in _both(out, "dim_region")}
    dealers = {r["dealer_id"]: r for r in _both(out, "dim_dealer")}
    people = {r["sales_person_id"] for r in _both(out, "dim_salesman")}
    colours = {r["colour_id"] for r in _both(out, "dim_color")}
    order_ids: Counter[str] = Counter()
    for row in _both(out, "fact_sales"):
        order_ids[row["order_id"]] += 1
        assert row["carline_id"] in carlines
        assert row["colour_id"] in colours
        assert row["sales_person_id"] in people
        assert row["region_id"] in regions
        assert dealers[row["dealer_id"]]["region_id"] == row["region_id"]
        assert int(row["order_qty"]) >= 1 and float(row["price_per_unit"]) > 0
    assert max(order_ids.values()) == 1


def test_no_sales_outside_model_windows(dataset: tuple[Path, object]) -> None:
    out, _ = dataset
    carlines = {c.carline_id: c for c in build_carlines()}
    for row in _both(out, "fact_sales"):
        day = date.fromisoformat(row["sales_date"])
        carline = carlines[int(row["carline_id"])]
        until = carline_on_sale_until(carline) or END
        assert carline.introduced <= day <= until, row
        assert any(
            (mk.month_start(start) if start else mk.DATA_START)
            <= day
            <= (mk.month_end(end) if end else END)
            for start, end in carline.spec.windows
        ), row


def test_plans_cover_history_and_future(dataset: tuple[Path, object]) -> None:
    out, _ = dataset
    targets = _both(out, "dim_targets")
    assert len({(t["year_month"], t["make"]) for t in targets}) == len(targets)
    assert all(int(t["target_units"]) >= 0 for t in targets)
    months = {r["sales_month"] for r in _both(out, "fact_forecast_monthly")}
    assert all(m.endswith("-01") for m in months)
    assert max(months) > END.isoformat()
