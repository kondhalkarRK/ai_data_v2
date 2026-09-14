"""NLQ accuracy regression suite — entity, filter, SQL routing.

Asserts Streamlit-parity behaviours without a live warehouse:
- salesperson ≠ dealer
- body-style filters (Sedan/SUV/Hatchback) are mandatory in SQL
- bare "top selling car" stays ambiguous
- domain templates remain available for common KPIs
"""

from __future__ import annotations

import pytest

from app.core.config import Industry
from app.services.chat.entity_match import match_entities, resolve_with_entity_match
from app.services.chat.question_understanding import understand_question
from app.services.chat.semantic_context import validate_sql_against_plan
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
        (Industry.AUTOMOTIVE, "Best selling vehicle by revenue", "vehicles"),
        (Industry.AUTOMOTIVE, "Top cars by region", "region"),
        (Industry.AUTOMOTIVE, "Electric share by year", "EV"),
        (Industry.AUTOMOTIVE, "Dealer performance", "dealer"),
        (Industry.AUTOMOTIVE, "What is the top salesperson?", "salespeople"),
        (Industry.AUTOMOTIVE, "Top selling sedan", "Sedan"),
        (Industry.AUTOMOTIVE, "Top hatchback", "Hatchback"),
        (Industry.AUTOMOTIVE, "Highest revenue dealer", "dealer"),
        (Industry.AUTOMOTIVE, "Lowest selling SUV", "SUV"),
    ],
)
def test_template_resolves(industry: Industry, question: str, expect_title_substr: str) -> None:
    hit = resolve_template(industry, question)
    assert hit is not None, f"Expected template for: {question}"
    assert expect_title_substr.lower() in hit.title.lower()
    assert "select" in hit.sql.lower()
    assert "limit" in hit.sql.lower()


def test_top_salesperson_uses_dim_salesman_not_dealer() -> None:
    plan = understand_question(Industry.AUTOMOTIVE, "What is the top salesperson?")
    assert plan.entity == "salesperson"
    assert not plan.is_ambiguous
    hit = resolve_template(Industry.AUTOMOTIVE, "What is the top salesperson?")
    assert hit is not None
    sql = hit.sql.lower()
    assert "dim_salesman" in sql
    assert "salesperson_name" in sql
    assert "dim_dealer" not in sql
    ok, reason = validate_sql_against_plan(hit.sql, plan)
    assert ok, reason


def test_top_selling_sedan_requires_car_type_filter() -> None:
    plan = understand_question(Industry.AUTOMOTIVE, "Top selling sedan car")
    assert plan.entity == "vehicle"
    assert any(f.value == "Sedan" for f in plan.filters)
    hit = resolve_template(Industry.AUTOMOTIVE, "Top selling sedan car")
    assert hit is not None
    sql = hit.sql.lower()
    assert "car_type" in sql
    assert "sedan" in sql
    assert "hatchback" not in sql or "car_type = 'sedan'" in sql
    ok, reason = validate_sql_against_plan(hit.sql, plan)
    assert ok, reason


def test_top_dealer_by_revenue_uses_dim_dealer() -> None:
    plan = understand_question(Industry.AUTOMOTIVE, "Top dealer by revenue")
    assert plan.entity == "dealer"
    assert plan.metric == "revenue"
    hit = resolve_template(Industry.AUTOMOTIVE, "Top dealer by revenue")
    assert hit is not None
    assert "dim_dealer" in hit.sql.lower()
    assert "dim_salesman" not in hit.sql.lower()


def test_top_selling_car_is_ambiguous() -> None:
    plan = understand_question(Industry.AUTOMOTIVE, "Top selling car")
    assert plan.is_ambiguous
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
        plan = understand_question(Industry.AUTOMOTIVE, q)
        assert plan.entity == "vehicle"
        assert not plan.is_ambiguous


def test_salesperson_synonyms() -> None:
    for q in (
        "top sales executive",
        "best sales rep by units",
        "highest sales consultant",
    ):
        plan = understand_question(Industry.AUTOMOTIVE, q)
        assert plan.entity == "salesperson", q


def test_validate_rejects_dealer_sql_for_salesperson() -> None:
    plan = understand_question(Industry.AUTOMOTIVE, "top salesperson")
    bad_sql = """
    SELECT d.dealer_name, SUM(f.order_qty)
    FROM automotive.fact_sales f
    JOIN automotive.dim_dealer d ON d.dealer_id = f.dealer_id
    GROUP BY 1 ORDER BY 2 DESC LIMIT 10
    """
    ok, reason = validate_sql_against_plan(bad_sql, plan)
    assert not ok
    assert reason is not None


def test_validate_rejects_missing_sedan_filter() -> None:
    plan = understand_question(Industry.AUTOMOTIVE, "top selling sedan")
    bad_sql = """
    SELECT c.model, SUM(f.order_qty)
    FROM automotive.fact_sales f
    JOIN automotive.dim_carline c ON c.carline_id = f.carline_id
    GROUP BY 1 ORDER BY 2 DESC LIMIT 10
    """
    ok, reason = validate_sql_against_plan(bad_sql, plan)
    assert not ok
    assert reason is not None


def test_ensure_result_limit_caps_and_preserves_stricter() -> None:
    assert "LIMIT 20" in ensure_result_limit("SELECT 1 FROM t", 20)
    assert ensure_result_limit("SELECT 1 FROM t LIMIT 5", 20).endswith("LIMIT 5")
    assert "LIMIT 20" in ensure_result_limit("SELECT 1 FROM t LIMIT 500", 20)


def test_complex_multi_join_template_exists() -> None:
    hit = resolve_template(Industry.AUTOMOTIVE, "top selling car by units")
    assert hit is not None
    assert "dim_carline" in hit.sql
    assert "fact_sales" in hit.sql
