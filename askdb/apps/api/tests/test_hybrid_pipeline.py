"""Hybrid pipeline: spelling, decision engine, validator shape checks, LLM repair loop."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any

import pytest

from app.core.config import Industry, get_settings
from app.services.chat import llm_assist
from app.services.chat.decision_engine import (
    assess_confidence,
    decide_route,
    interpretation_options,
)
from app.services.chat.question_understanding import understand_question
from app.services.chat.semantic_context import validate_sql_against_plan
from app.services.chat.spell import correct_question, edit_distance
from app.services.llm import LlmResult

_RUNNER = Path(__file__).with_name("benchmark") / "run_benchmark.py"
_spec = importlib.util.spec_from_file_location("hybrid_benchmark_runner", _RUNNER)
assert _spec is not None and _spec.loader is not None
runner = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = runner
_spec.loader.exec_module(runner)

AUTO = Industry.AUTOMOTIVE
INS = Industry.INSURANCE


# ─────────────────────────────── spelling ───────────────────────────────


@pytest.mark.parametrize(
    ("typo", "fixed"),
    [("revnue", "revenue"), ("salse", "sales"), ("premuim", "premium"), ("incured", "incurred")],
)
def test_business_words_are_corrected(typo: str, fixed: str) -> None:
    result = correct_question(f"total {typo} by month")
    assert fixed in result.text.split()
    assert (typo, fixed) in result.corrections


def test_protected_and_everyday_words_are_left_alone() -> None:
    result = correct_question("who made the most sales in hector", protected=("hector",))
    assert result.corrections == []
    assert result.text == "who made the most sales in hector"


def test_edit_distance_counts_a_transposition_as_one() -> None:
    assert edit_distance("hyundia", "hyundai") == 1
    assert edit_distance("mumabi", "mumbai") == 1


@pytest.mark.parametrize(
    ("question", "canonical"),
    [
        ("marutii sales by year", "Maruti Suzuki"),
        ("hyundia sales trend", "Hyundai"),
        ("revenue in mumabi", "Mumbai"),
        ("MSIL units sold by year", "Maruti Suzuki"),
        ("Morris Garages sales by year", "MG"),
    ],
)
def test_typos_and_aliases_resolve_to_catalog_values(question: str, canonical: str) -> None:
    turn = runner.ask(AUTO, question)
    assert turn.outcome == "sql", turn.detail
    assert any(f"->{canonical} (" in item for item in turn.resolved), turn.resolved


# ─────────────────────────── decision engine ───────────────────────────


def test_simple_question_takes_the_semantic_path() -> None:
    plan = understand_question(AUTO, "MG sales by year")
    decision = decide_route(plan, has_governed_sql=True, llm_available=True)
    assert decision.path == "semantic"
    assert decision.complexity == "simple"


@pytest.mark.parametrize(
    "question",
    [
        "Top 3 models per make",
        "Running total of units sold by month",
        "Which dealers are growing fastest",
    ],
)
def test_complex_question_prefers_ai_reasoning_with_governed_fallback(question: str) -> None:
    plan = understand_question(AUTO, question)
    decision = decide_route(plan, has_governed_sql=True, llm_available=True)
    assert decision.path == "llm_reasoning"
    assert decision.governed_fallback


def test_governed_first_mode_keeps_complex_questions_on_the_semantic_path() -> None:
    plan = understand_question(AUTO, "Top 3 models per make")
    decision = decide_route(plan, has_governed_sql=True, llm_available=True, mode="governed_first")
    assert decision.path == "semantic"


def test_without_sql_or_llm_the_engine_clarifies() -> None:
    plan = understand_question(AUTO, "MG sales by year")
    assert decide_route(plan, has_governed_sql=False, llm_available=False).path == "clarify"
    assert decide_route(plan, has_governed_sql=False, llm_available=True).path == "llm_reasoning"


def test_confidence_levels() -> None:
    plan = understand_question(AUTO, "MG sales by year")
    assert assess_confidence(plan, has_sql=True).level == "high"
    corrected = assess_confidence(
        plan, has_sql=True, corrections=[("revnue", "revenue")], ai_generated=True
    )
    assert corrected.level == "high" and corrected.score < 100
    unsure = assess_confidence(plan, has_sql=True, reinterpreted=True, ai_generated=True,
                               contextual=True)
    assert unsure.level == "medium"
    unknown = understand_question(AUTO, "who is the best")
    assert assess_confidence(unknown, has_sql=False).level == "needs_clarification"


def test_interpretation_options_offer_concrete_readings() -> None:
    plan = understand_question(AUTO, "Who made the most revenue")
    options = interpretation_options(plan, industry=AUTO, question="Who made the most revenue")
    assert options[0].startswith("Top ") and options[0].endswith("by revenue")
    for option in options:
        assert runner.ask(AUTO, option).outcome == "sql", option


@pytest.mark.parametrize(("industry", "question"), [(AUTO, "Show me the numbers"),
                                                    (INS, "Show insurance numbers")])
def test_vague_questions_clarify_with_answerable_options(industry: Industry, question: str) -> None:
    plan = understand_question(industry, question)
    assert plan.is_ambiguous and plan.ambiguity_options
    for option in plan.ambiguity_options:
        assert runner.ask(industry, option).outcome == "sql", option


# ─────────────────────────── validator shape ───────────────────────────


_TOP_PER_MAKE_BAD = """
WITH aggregated AS (
  SELECT v.make, v.model, SUM(f.order_qty) AS units_sold
  FROM automotive.fact_sales f JOIN automotive.dim_carline v ON v.carline_id = f.carline_id
  GROUP BY v.make, v.model
), ranked AS (
  SELECT aggregated.*, ROW_NUMBER() OVER (PARTITION BY model ORDER BY units_sold DESC) AS rn
  FROM aggregated
)
SELECT * FROM ranked WHERE rn <= 3
"""


def test_validator_rejects_partition_by_the_ranked_dimension() -> None:
    plan = understand_question(AUTO, "Top 3 models per make")
    ok, reason = validate_sql_against_plan(_TOP_PER_MAKE_BAD, plan)
    assert not ok
    assert reason and "partition" in reason.lower()
    fixed = _TOP_PER_MAKE_BAD.replace("PARTITION BY model", "PARTITION BY make")
    assert validate_sql_against_plan(fixed, plan)[0]


def test_validator_requires_lag_for_growth() -> None:
    plan = understand_question(AUTO, "Year over year revenue growth for MG")
    sql = (
        "SELECT EXTRACT(YEAR FROM f.sales_date)::int AS year, SUM(f.total_sales) AS revenue "
        "FROM automotive.fact_sales f JOIN automotive.dim_carline v ON v.carline_id = f.carline_id "
        "WHERE v.make = 'MG' GROUP BY 1"
    )
    ok, reason = validate_sql_against_plan(sql, plan)
    assert not ok and reason and "lag" in reason.lower()


# ─────────────────────── growth / divergence / ratio ───────────────────────


def test_growth_ranking_compares_current_and_previous_periods() -> None:
    turn = runner.ask(AUTO, "Which dealers are growing fastest")
    sql = turn.sql.lower()
    assert "current_revenue" in sql and "previous_revenue" in sql
    assert "revenue_change_pct desc" in sql


def test_declining_phrase_orders_ascending() -> None:
    turn = runner.ask(INS, "Which regions have declining claims incurred")
    assert "change_pct asc" in turn.sql.lower()


def test_divergence_filters_on_both_directions() -> None:
    turn = runner.ask(AUTO, "Dealers with increasing revenue but decreasing units")
    sql = turn.sql.lower()
    assert "current_revenue > previous_revenue" in sql
    assert "current_units_sold < previous_units_sold" in sql


def test_loss_ratio_growth_uses_lag_per_group() -> None:
    turn = runner.ask(INS, "Year over year loss ratio by line of business")
    assert turn.outcome == "sql", turn.detail
    assert "lag(loss_ratio) over (partition by line_of_business order by year)" in turn.sql.lower()


# ─────────────────────────────── follow-ups ───────────────────────────────


def test_follow_up_chain_keeps_every_scope() -> None:
    turn = None
    for step in ("MG sales by year", "Only SUVs", "Only Maharashtra", "Show units instead"):
        turn = runner.ask(AUTO, step, turn)
        assert turn.outcome == "sql", (step, turn.detail)
    assert turn is not None
    sql = runner._normalise(turn.sql)
    assert "sum(f.order_qty)" in sql
    for literal in ("'mg'", "'suv'", "'mh'"):
        assert literal in sql


def test_ranking_follow_ups_change_direction_and_period() -> None:
    turn = None
    for step in ("Top 5 brands by revenue", "for 2024", "bottom 5 instead", "in Q1"):
        turn = runner.ask(AUTO, step, turn)
    assert turn is not None
    sql = runner._normalise(turn.sql)
    assert "'2024-01-01'" in sql and "'2024-04-01'" in sql
    assert "limit 5" in sql


# ─────────────────────────── LLM repair loop ───────────────────────────


async def test_llm_sql_is_repaired_until_the_validator_approves(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plan = understand_question(AUTO, "Top 3 models per make")
    bad = _TOP_PER_MAKE_BAD
    good = bad.replace("PARTITION BY model", "PARTITION BY make")
    feedback_seen: list[str | None] = []

    async def fake_complete_chat(**kwargs: Any) -> LlmResult:
        feedback_seen.append(kwargs.get("feedback"))
        sql = bad if len(feedback_seen) == 1 else good
        return LlmResult(sql=sql, narrative="", model="fake")

    monkeypatch.setattr(llm_assist, "complete_chat", fake_complete_chat)
    outcome = await llm_assist.generate_validated_sql(
        settings=get_settings(),
        industry=AUTO,
        question="Top 3 models per make",
        plan=plan,
        schema_hints="",
        validate=lambda sql: validate_sql_against_plan(sql, plan),
    )
    assert outcome.sql == good
    assert outcome.repaired and outcome.attempts == 2
    assert feedback_seen[0] is None
    assert feedback_seen[1] and "partition" in feedback_seen[1].lower()


async def test_llm_sql_that_never_validates_is_not_returned(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plan = understand_question(AUTO, "Top 3 models per make")

    async def always_bad(**_: Any) -> LlmResult:
        return LlmResult(sql=_TOP_PER_MAKE_BAD, narrative="", model="fake")

    monkeypatch.setattr(llm_assist, "complete_chat", always_bad)
    outcome = await llm_assist.generate_validated_sql(
        settings=get_settings(),
        industry=AUTO,
        question="Top 3 models per make",
        plan=plan,
        schema_hints="",
        validate=lambda sql: validate_sql_against_plan(sql, plan),
    )
    assert outcome.sql is None
    assert outcome.attempts == 2 and len(outcome.rejected) == 2


def test_plan_spec_states_the_partition_rule() -> None:
    plan = understand_question(AUTO, "Top 3 models per make")
    spec = llm_assist.plan_spec(plan)
    assert "PARTITION BY make" in spec
    assert "Never partition by the ranked dimension" in spec
