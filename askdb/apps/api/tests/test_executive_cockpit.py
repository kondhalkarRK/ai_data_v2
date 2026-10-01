"""Pure-logic tests for the executive KPI cockpit (no database)."""

from __future__ import annotations

from datetime import date
from typing import Any, cast

import pytest

from app.services.executive.cockpit import (
    Agg,
    CockpitFilters,
    ExecutiveCockpitService,
    Grouped,
    body_family,
    format_inr,
    growth,
    month_add,
    resolve_period,
    shift_year,
)


def _service() -> ExecutiveCockpitService:
    return ExecutiveCockpitService(cast(Any, None))


def test_resolve_period_year_to_date_compares_same_span_last_year() -> None:
    period = resolve_period(date(2026, 9, 30), CockpitFilters())
    assert (period.start, period.end) == (date(2026, 1, 1), date(2026, 9, 30))
    assert (period.prior_start, period.prior_end) == (date(2025, 1, 1), date(2025, 9, 30))
    assert period.label == "2026 to date (30 Sep)"
    assert period.prior_label == "2025 to date (30 Sep)"


def test_resolve_period_complete_past_year() -> None:
    period = resolve_period(date(2026, 9, 30), CockpitFilters(year=2024))
    assert (period.start, period.end, period.label) == (
        date(2024, 1, 1),
        date(2024, 12, 31),
        "2024",
    )


def test_resolve_period_month_overrides_quarter() -> None:
    period = resolve_period(date(2026, 9, 30), CockpitFilters(year=2025, quarter=1, month=10))
    assert (period.start, period.end, period.label) == (
        date(2025, 10, 1),
        date(2025, 10, 31),
        "Oct 2025",
    )


def test_resolve_period_quarter_label_and_leap_day() -> None:
    period = resolve_period(date(2026, 9, 30), CockpitFilters(year=2024, quarter=1))
    assert period.end == date(2024, 3, 31)
    assert period.label.startswith("Q1 2024")
    assert shift_year(date(2024, 2, 29)) == date(2023, 2, 28)


@pytest.mark.parametrize(
    ("car_type", "family"),
    [
        ("Compact SUV", "SUV"),
        ("Mid-size Sedan", "Sedan"),
        ("Premium Hatchback", "Hatchback"),
        ("MPV", "MUV / MPV"),
        ("Pickup", "Pickup"),
    ],
)
def test_body_family(car_type: str, family: str) -> None:
    assert body_family(car_type) == family


def test_helpers() -> None:
    assert growth(110, 100) == pytest.approx(0.1)
    assert growth(5, 0) is None
    assert month_add(date(2025, 11, 1), 3) == date(2026, 2, 1)
    assert format_inr(2_187_800_000_000) == "₹218,780 Cr"
    assert format_inr(4_500_000) == "₹45.0 L"


def _grouped() -> Grouped:
    grouped = Grouped()
    grouped.cur = {
        "total": {(): Agg(1000, 100, 90)},
        "model": {
            ("Maruti Suzuki", "Brezza"): Agg(600, 70, 60),
            ("Tata", "Nexon"): Agg(400, 30, 30),
        },
        "make": {("Maruti Suzuki",): Agg(600, 70, 60), ("Tata",): Agg(400, 30, 30)},
        "fuel": {("Petrol",): Agg(700, 75, 0), ("Electric",): Agg(300, 25, 0)},
        "zone_body": {
            ("South", "Compact SUV"): Agg(500, 0, 0),
            ("South", "Sedan"): Agg(100, 0, 0),
            ("North", "Compact SUV"): Agg(400, 0, 0),
        },
    }
    grouped.pri = {
        "total": {(): Agg(800, 90, 80)},
        "model": {
            ("Maruti Suzuki", "Brezza"): Agg(500, 60, 50),
            ("Tata", "Nexon"): Agg(300, 30, 30),
        },
        "make": {("Maruti Suzuki",): Agg(500, 60, 50), ("Tata",): Agg(300, 30, 30)},
        "fuel": {("Petrol",): Agg(700, 80, 0), ("Electric",): Agg(100, 10, 0)},
        "zone_body": {
            ("South", "Compact SUV"): Agg(400, 0, 0),
            ("North", "Compact SUV"): Agg(400, 0, 0),
        },
    }
    return grouped


def test_kpis_pick_top_model_by_revenue_and_top_make_by_units() -> None:
    grouped = _grouped()
    kpis = _service()._kpis(grouped, grouped.total("cur"), grouped.total("pri"))
    assert kpis.revenue.growth == pytest.approx(0.25)
    assert kpis.top_model is not None and kpis.top_model.name == "Brezza"
    assert kpis.top_model.share == pytest.approx(0.6)
    assert kpis.top_make is not None and kpis.top_make.name == "Maruti Suzuki"
    assert kpis.top_make.share == pytest.approx(0.7)
    assert kpis.top_make.share_change == pytest.approx(0.7 - 60 / 90)


def test_heat_matrix_rolls_car_types_into_families_with_row_shares() -> None:
    heat = _service()._heat(_grouped())
    assert heat.rows == ["South", "North"]
    assert heat.cols == ["SUV", "Sedan"]
    cells = {(c.row, c.col): c for c in heat.cells}
    assert cells[("South", "SUV")].share == pytest.approx(500 / 600)
    assert cells[("South", "SUV")].growth == pytest.approx(0.25)
    assert cells[("South", "Sedan")].growth is None


def test_mix_uses_unit_share_and_unit_growth() -> None:
    mix = _service()._mix(_grouped(), "fuel", lambda key: key[0])
    assert [item.name for item in mix] == ["Petrol", "Electric"]
    electric = mix[1]
    assert electric.share == pytest.approx(0.25)
    assert electric.prior_share == pytest.approx(10 / 90)
    assert electric.growth == pytest.approx(1.5)
