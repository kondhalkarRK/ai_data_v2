"""Vehicle enumeration: which cars have a given paint colour."""

from __future__ import annotations

from app.core.config import Industry, get_settings
from app.services.chat.plan_coverage import coverage_gaps
from app.services.chat.pipeline import plan_turn
from app.services.chat.question_understanding import understand_question
from app.services.chat.semantic_context import build_allowed_schema, validate_sql_against_plan
from app.services.chat.templates import resolve_template
from app.services.chat.value_dictionary import BusinessValue, ValueDictionarySnapshot
from app.semantic.service import SemanticService

CORAL_PINK_QUESTION = "which all cars has Coral Pink color"


def _plan(question: str = CORAL_PINK_QUESTION):
    snapshot = ValueDictionarySnapshot(
        Industry.AUTOMOTIVE,
        (BusinessValue("Colour", "automotive.dim_color.colour_name", "Coral Pink", 50),),
    )
    return understand_question(
        Industry.AUTOMOTIVE,
        question,
        value_filters=snapshot.match(question),
    )


def test_coral_pink_question_is_vehicle_lookup() -> None:
    plan = _plan()
    assert plan.intent == "lookup"
    assert plan.entity == "vehicle"
    assert plan.time_grain is None
    assert "month" not in plan.dimensions
    assert plan.metric == "units"
    assert any("Coral Pink" in f.value for f in plan.filters)
    assert not coverage_gaps(CORAL_PINK_QUESTION, plan)


def test_coral_pink_sql_lists_distinct_models() -> None:
    plan = _plan()
    hit = resolve_template(Industry.AUTOMOTIVE, CORAL_PINK_QUESTION, plan=plan)
    assert hit is not None
    sql = hit.sql
    assert "DISTINCT" in sql.upper()
    assert "dim_carline" in sql
    assert "dim_color" in sql
    assert "Coral Pink" in sql
    assert "date_trunc('month'" not in sql
    assert "SUM(f.total_sales)" not in sql
    ok, reason = validate_sql_against_plan(sql, plan)
    assert ok, reason


def test_plan_turn_governs_coral_pink_lookup() -> None:
    pack = SemanticService(get_settings())._load_pack(Industry.AUTOMOTIVE)
    snapshot = ValueDictionarySnapshot(
        Industry.AUTOMOTIVE,
        (BusinessValue("Colour", "automotive.dim_color.colour_name", "Coral Pink", 50),),
    )
    allowed = build_allowed_schema(pack)
    turn = plan_turn(
        Industry.AUTOMOTIVE,
        CORAL_PINK_QUESTION,
        snapshot=snapshot,
        pack=pack,
        allowed_schema=allowed,
    )
    assert turn.validation_error is None
    assert turn.governed_sql is not None
    assert turn.plan is not None
    assert turn.plan.intent == "lookup"
    sql = turn.governed_sql.lower()
    assert "distinct" in sql
    assert "coral pink" in sql
    assert "date_trunc('month'" not in sql
