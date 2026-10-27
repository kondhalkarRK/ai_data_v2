"""Intent preservation: question plan, coverage gaps, and governed SQL."""

from __future__ import annotations

import pytest

from app.core.config import Industry, get_settings
from app.services.chat.plan_coverage import coverage_gaps, sql_covers_plan_metrics
from app.services.chat.pipeline import plan_turn
from app.services.chat.question_understanding import QuestionPlan, understand_question
from app.services.chat.semantic_context import build_allowed_schema
from app.services.chat.value_dictionary import ValueDictionarySnapshot
from app.semantic.service import SemanticService

ACCEPTANCE = (
    "Models with declining units but stable average selling price by month"
)


def test_divergence_plan_parses_declining_and_stable_metrics() -> None:
    plan = understand_question(Industry.AUTOMOTIVE, ACCEPTANCE)
    assert plan.analysis == "divergence"
    assert plan.divergence == [
        ("units", "down"),
        ("average_selling_price", "flat"),
    ]
    assert "model" in plan.dimensions
    assert plan.time_grain == "month"
    assert not coverage_gaps(ACCEPTANCE, plan)


def test_coverage_gaps_detects_missing_divergence() -> None:
    plan = QuestionPlan(
        industry=Industry.AUTOMOTIVE,
        intent="trend",
        entity="metric_only",
        metric="average_selling_price",
        analysis="breakdown",
        dimensions=["month"],
        time_grain="month",
    )
    gaps = coverage_gaps(ACCEPTANCE, plan)
    assert any("divergence" in g.lower() for g in gaps)


def test_coverage_gaps_detects_missing_model_grouping() -> None:
    plan = understand_question(Industry.AUTOMOTIVE, ACCEPTANCE)
    plan.dimensions = []
    gaps = coverage_gaps(ACCEPTANCE, plan)
    assert any("model" in g.lower() for g in gaps)


@pytest.fixture(scope="module")
def automotive_pack():
    return SemanticService(get_settings())._load_pack(Industry.AUTOMOTIVE)


def test_plan_turn_compiles_acceptance_divergence_sql(automotive_pack) -> None:
    snapshot = ValueDictionarySnapshot(Industry.AUTOMOTIVE, ())
    allowed = build_allowed_schema(automotive_pack)
    turn = plan_turn(
        Industry.AUTOMOTIVE,
        ACCEPTANCE,
        snapshot=snapshot,
        pack=automotive_pack,
        allowed_schema=allowed,
    )
    assert turn.validation_error is None
    assert turn.governed_sql is not None
    sql = turn.governed_sql.lower()
    assert "model" in sql
    assert "month" in sql
    assert "units" in sql
    assert "average_selling_price" in sql
    assert "abs(" in sql
    plan = turn.plan
    assert plan is not None
    ok, reason = sql_covers_plan_metrics(plan, turn.governed_sql)
    assert ok, reason


def test_sql_covers_plan_metrics_rejects_single_metric_sql() -> None:
    plan = understand_question(Industry.AUTOMOTIVE, ACCEPTANCE)
    sql = "SELECT model, SUM(order_qty) AS units FROM automotive.fact_sales GROUP BY model"
    ok, reason = sql_covers_plan_metrics(plan, sql)
    assert not ok
    assert reason and "average_selling_price" in reason
