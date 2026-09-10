"""Numeric parity helpers for KPI formulas on a fixed window (no live DB).

These assert the same algebraic definitions as the SQL ports of the legacy engines.
"""

from __future__ import annotations

import re
from datetime import date
from pathlib import Path

from app.services.kpi.windows import (
    format_currency,
    format_percent,
    prior_comparable_window,
    resolve_window,
)


def loss_ratio(incurred: float, earned: float) -> float | None:
    if earned == 0:
        return None
    return incurred / earned


def average_severity(incurred: float, claim_count: float) -> float | None:
    if claim_count == 0:
        return None
    return incurred / claim_count


def avg_order_value(revenue: float, orders: float) -> float | None:
    if orders == 0:
        return None
    return revenue / orders


def attach_delta_ratio_local(current: float, prior: float) -> float | None:
    if prior == 0:
        return None
    return (current - prior) / abs(prior)


def test_insurance_kpi_formulas_fixed_window() -> None:
    # Fixed window fixture values (synthetic, deterministic).
    written = 12_500_000.0
    earned = 10_000_000.0
    incurred = 6_500_000.0
    claims = 1300.0

    assert loss_ratio(incurred, earned) == 0.65
    assert average_severity(incurred, claims) == 5000.0
    assert format_percent(0.65) == "65.0%"
    assert "Cr" in format_currency(written) or "L" in format_currency(written)


def test_automotive_kpi_formulas_fixed_window() -> None:
    revenue = 85_000_000.0
    units = 4250.0
    orders = 3100.0
    assert avg_order_value(revenue, orders) == revenue / orders
    assert abs((revenue / units) - 20_000.0) < 1e-9


def test_period_comparison_ytd_prior_bounds() -> None:
    as_of = date(2026, 9, 10)
    start, end, label = resolve_window("ytd", as_of)
    assert start == date(2026, 1, 1)
    assert end == as_of
    assert "2026" in label
    prior = prior_comparable_window("ytd", as_of)
    assert prior is not None
    p_start, p_end, _ = prior
    assert p_start == date(2025, 1, 1)
    assert p_end == date(2025, 9, 10)


def test_delta_ratio_parity() -> None:
    assert attach_delta_ratio_local(110.0, 100.0) == 0.1
    assert attach_delta_ratio_local(90.0, 100.0) == -0.1
    assert attach_delta_ratio_local(50.0, 0.0) is None


def test_full_history_has_no_prior() -> None:
    assert prior_comparable_window("full", date(2026, 1, 1)) is None


def test_nullable_kpi_bind_parameters_are_explicitly_typed() -> None:
    """PostgreSQL cannot infer the type of ``NULL`` in ``:param IS NULL``.

    This regression test guards every KPI query against psycopg's
    ``AmbiguousParameter`` error when optional dashboard filters are unset.
    """
    kpi_dir = Path(__file__).parents[1] / "app" / "services" / "kpi"
    sources = "\n".join(
        (kpi_dir / filename).read_text(encoding="utf-8")
        for filename in ("automotive.py", "insurance.py")
    )
    ambiguous = re.compile(
        r":(?:start_date|end_date|make|region|lob)\s+IS\s+NULL",
        re.IGNORECASE,
    )
    assert ambiguous.search(sources) is None
    assert "CAST(:make AS text)" in sources
    assert "CAST(:lob AS text)" in sources
    assert "CAST(:start_date AS date)" in sources
