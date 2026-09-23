"""Governed answers for common business questions — no LLM, no warehouse."""

from __future__ import annotations

import pytest

from app.core.config import Industry
from app.services.chat.failures import propose_sql_repair
from app.services.chat.question_understanding import understand_question
from app.services.chat.semantic_context import validate_sql_against_plan
from app.services.chat.templates import resolve_template

_AUTOMOTIVE_SCHEMA = {
    "automotive.fact_sales": {
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
    },
    "automotive.dim_carline": {"carline_id", "model", "make", "car_type", "engine_type"},
    "automotive.dim_salesman": {"sales_person_id", "first_name", "last_name"},
    "automotive.dim_dealer": {"dealer_id", "dealer_name", "city", "dealer_grade"},
    "automotive.dim_region": {"region_id", "region_name", "city"},
}


@pytest.mark.parametrize(
    ("question", "sql_bits"),
    [
        ("Show total sales per year", ("total_sales", "extract(year", "sales_date", "fact_sales")),
        ("Show me total orders per year", ("count(distinct", "extract(year", "fact_sales")),
        ("Show orders per year", ("count(distinct", "extract(year", "fact_sales")),
        ("Show revenue by month", ("total_sales", "date_trunc('month'", "fact_sales")),
        ("Monthly revenue trend", ("total_sales", "date_trunc('month'", "fact_sales")),
        ("Show revenue trend", ("total_sales", "date_trunc('month'", "fact_sales")),
        ("Show top salesperson", ("dim_salesman", "fact_sales")),
        ("Show dealer performance", ("dim_dealer", "total_sales")),
        ("Best performing region", ("dim_region", "total_sales")),
        ("Show SUV sales by region", ("car_type = 'suv'", "region_name", "total_sales")),
        ("Compare SUV sales across regions", ("car_type = 'suv'", "region_name", "total_sales")),
        ("Show sales in Mumbai", ("city = 'mumbai'", "total_sales")),
        (
            "Compare last 3 months sales for last 3 years",
            ("interval '3 years'", "generate_series(1, 3)", "total_sales"),
        ),
    ],
)
def test_business_questions_compile(question: str, sql_bits: tuple[str, ...]) -> None:
    plan = understand_question(Industry.AUTOMOTIVE, question)
    assert not plan.is_ambiguous, question
    hit = resolve_template(Industry.AUTOMOTIVE, question, plan=plan)
    assert hit is not None, question
    sql = hit.sql.lower()
    for bit in sql_bits:
        assert bit in sql, f"{question} missing {bit}"
    ok, reason = validate_sql_against_plan(hit.sql, plan, allowed_schema=_AUTOMOTIVE_SCHEMA)
    assert ok, reason


def test_bare_sales_asks_for_a_metric() -> None:
    plan = understand_question(Industry.AUTOMOTIVE, "Show me sales")
    assert plan.is_ambiguous
    labels = " ".join(plan.ambiguity_options).lower()
    assert "revenue" in labels
    assert "orders" in labels
    assert resolve_template(Industry.AUTOMOTIVE, "Show me sales", plan=plan) is None


def test_clarification_choices_compile() -> None:
    for question in ("Total Revenue", "Total Orders", "Quantity Sold", "Revenue by region"):
        hit = resolve_template(Industry.AUTOMOTIVE, question)
        assert hit is not None, question
        assert "fact_sales" in hit.sql.lower()


def test_sql_repair_rewrites_unknown_order_date() -> None:
    sql = "SELECT order_date FROM automotive.fact_sales"
    repaired = propose_sql_repair(sql, 'column "order_date" does not exist')
    assert repaired is not None
    assert "sales_date" in repaired
    assert "order_date" not in repaired.lower()
