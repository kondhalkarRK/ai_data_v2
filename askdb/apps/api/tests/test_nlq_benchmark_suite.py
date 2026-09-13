"""NLQ regression suite — representative questions for CI.

These tests assert semantic routing (templates / entity ambiguity) without requiring
a live warehouse. Expand expected SQL/result checks when DB fixtures are available.
"""

from __future__ import annotations

import pytest

from app.core.config import Industry
from app.services.chat.entity_match import match_entities, resolve_with_entity_match
from app.services.chat.sql_limits import ensure_result_limit
from app.services.chat.templates import resolve_template


@pytest.mark.parametrize(
    ("industry", "question", "expect_title_substr"),
    [
        (Industry.INSURANCE, "Show loss ratio by month", "Loss ratio"),
        (Industry.INSURANCE, "How many claims by status", "Claim count"),
        (Industry.INSURANCE, "Written premium trend", "Premium"),
        (Industry.INSURANCE, "Top region by incurred", "region"),
        (Industry.AUTOMOTIVE, "Revenue by month", "Revenue"),
        (Industry.AUTOMOTIVE, "Top model by units", "vehicles"),
        (Industry.AUTOMOTIVE, "Top selling car by units", "vehicles"),
        (Industry.AUTOMOTIVE, "Best selling vehicle by revenue", "revenue"),
        (Industry.AUTOMOTIVE, "Top cars by region", "region"),
        (Industry.AUTOMOTIVE, "Electric share by year", "EV"),
        (Industry.AUTOMOTIVE, "Dealer performance", "Dealer"),
    ],
)
def test_template_resolves(industry: Industry, question: str, expect_title_substr: str) -> None:
    hit = resolve_template(industry, question)
    assert hit is not None, f"Expected template for: {question}"
    assert expect_title_substr.lower() in hit.title.lower()
    assert "select" in hit.sql.lower()
    assert "limit" in hit.sql.lower()


def test_top_selling_car_is_ambiguous() -> None:
    msg, opts = resolve_with_entity_match(Industry.AUTOMOTIVE, "Top selling car")
    assert msg is not None
    assert len(opts) >= 3
    assert any("units" in o.lower() for o in opts)
    assert any("revenue" in o.lower() for o in opts)


def test_vehicle_synonyms_match_entity() -> None:
    for q in ("top vehicle by units", "best selling model by units", "highest car by units"):
        match = match_entities(Industry.AUTOMOTIVE, q)
        assert match is not None
        assert match.entity == "vehicle"


def test_ensure_result_limit_caps_and_preserves_stricter() -> None:
    assert "LIMIT 20" in ensure_result_limit("SELECT 1 FROM t", 20)
    assert ensure_result_limit("SELECT 1 FROM t LIMIT 5", 20).endswith("LIMIT 5")
    assert "LIMIT 20" in ensure_result_limit("SELECT 1 FROM t LIMIT 500", 20)


def test_complex_multi_join_template_exists() -> None:
    hit = resolve_template(Industry.AUTOMOTIVE, "top selling car by units")
    assert hit is not None
    assert "dim_carline" in hit.sql
    assert "fact_sales" in hit.sql
