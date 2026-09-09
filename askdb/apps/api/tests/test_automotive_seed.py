"""Unit tests for the automotive seed generator (no PostgreSQL required)."""

from __future__ import annotations

from datetime import date

from app.analytics.automotive_seed import (
    CARLINE_COUNT,
    COLOUR_COUNT,
    DEALER_COUNT,
    DEFAULT_FACT_ROWS,
    REGION_COUNT,
    SALESMAN_COUNT,
    build_dimensions,
    iter_fact_sales,
)


def test_dimensions_are_deterministic_and_sized() -> None:
    a = build_dimensions()
    b = build_dimensions()
    assert len(a.carlines) == CARLINE_COUNT
    assert len(a.colours) == COLOUR_COUNT
    assert len(a.salesmen) == SALESMAN_COUNT
    assert len(a.regions) == REGION_COUNT
    assert len(a.dealers) == DEALER_COUNT
    assert a.carlines == b.carlines
    assert a.dealers == b.dealers
    assert a.targets == b.targets
    assert all(t.year_month.day == 1 for t in a.targets)
    assert min(t.year_month for t in a.targets) == date(2024, 1, 1)
    assert max(t.year_month for t in a.targets) == date(2026, 12, 1)


def test_dealers_inherit_region_city() -> None:
    dims = build_dimensions()
    regions = {r.region_id: r for r in dims.regions}
    for dealer in dims.dealers:
        assert dealer.city == regions[dealer.region_id].city


def test_fact_sales_preserve_dealer_region_and_default_scale() -> None:
    dims = build_dimensions()
    dealers = {d.dealer_id: d for d in dims.dealers}
    rows = list(iter_fact_sales(dims, row_count=5_000))
    assert len(rows) == 5_000
    assert DEFAULT_FACT_ROWS == 1_000_000
    for (
        order_id,
        carline_id,
        colour_id,
        sales_person_id,
        region_id,
        dealer_id,
        sales_date,
        order_qty,
        price_per_unit,
    ) in rows:
        assert order_id >= 1
        assert dealers[dealer_id].region_id == region_id
        assert 1 <= carline_id <= len(dims.carlines)
        assert 1 <= colour_id <= len(dims.colours)
        assert 1 <= sales_person_id <= len(dims.salesmen)
        assert order_qty >= 1
        assert price_per_unit >= 0
        assert date(2019, 1, 1) <= sales_date <= date(2026, 9, 9)


def test_ev_share_rises_over_time() -> None:
    dims = build_dimensions()
    carlines = {c.carline_id: c for c in dims.carlines}
    early = late = 0
    early_ev = late_ev = 0
    for row in iter_fact_sales(dims, row_count=40_000):
        _, carline_id, _, _, _, _, sales_date, qty, _ = row
        is_ev = carlines[carline_id].engine_type == "Electric"
        if sales_date.year <= 2020:
            early += qty
            early_ev += qty if is_ev else 0
        elif sales_date.year >= 2025:
            late += qty
            late_ev += qty if is_ev else 0
    assert early > 0 and late > 0
    assert (late_ev / late) > (early_ev / early)
