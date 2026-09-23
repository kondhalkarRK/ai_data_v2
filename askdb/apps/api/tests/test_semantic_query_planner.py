"""Semantic Query Planner stage order."""

from app.core.config import Industry
from app.services.chat.semantic_query_planner import (
    PIPELINE_STAGES,
    plan_semantic_query,
    recommend_chart,
    rewrite_question,
)
from app.services.chat.question_understanding import understand_question


def test_pipeline_stage_order() -> None:
    ids = [step["id"] for step in PIPELINE_STAGES]
    assert ids == [
        "question",
        "rewrite",
        "intent",
        "ambiguity",
        "context",
        "semantic",
        "joins",
        "formula",
        "sql",
        "validate",
        "repair",
        "execute",
        "chart",
        "narration",
    ]


def test_rewrite_strips_politeness_and_keeps_the_metric() -> None:
    assert rewrite_question("Show me total orders per year") == "total orders per year"
    assert rewrite_question("Can you show revenue by month") == "revenue by month"


def test_orders_per_year_resolves_formula_and_sql() -> None:
    planned = plan_semantic_query(Industry.AUTOMOTIVE, "Show me total orders per year")
    assert planned.plan.intent == "aggregation"
    assert planned.plan.metric == "orders"
    assert "year" in planned.plan.dimensions
    assert planned.formula == "COUNT(DISTINCT order_id)"
    assert planned.sql is not None
    assert "count(distinct" in planned.sql.lower()
    assert planned.chart_type == "line"


def test_bare_sales_stops_before_sql() -> None:
    planned = plan_semantic_query(Industry.AUTOMOTIVE, "Show me sales")
    assert planned.plan.is_ambiguous
    assert planned.sql is None
    assert planned.path == "clarification"


def test_chart_follows_intent() -> None:
    trend = understand_question(Industry.AUTOMOTIVE, "revenue by month")
    ranking = understand_question(Industry.AUTOMOTIVE, "top salesperson")
    assert recommend_chart(trend, ["month", "revenue"]) == "line"
    assert recommend_chart(ranking, ["name", "units"]) == "bar"
