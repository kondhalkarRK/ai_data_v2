"""Glossary resolution, follow-up state, and pack-aware SQL repair."""

from types import SimpleNamespace

from app.core.config import Industry
from app.services.chat.conversation_context import apply_followup, plan_state
from app.services.chat.failures import propose_sql_repair
from app.services.chat.glossary_resolve import apply_glossary
from app.services.chat.question_understanding import understand_question
from app.services.chat.semantic_context import validate_sql_against_plan
from app.services.chat.semantic_query_planner import plan_semantic_query
from app.services.chat.templates import resolve_template


def _pack() -> SimpleNamespace:
    terms = {
        "Average Selling Price": SimpleNamespace(
            display_label="Average Selling Price",
            synonyms=["ASP", "average price", "price achieved"],
            maps_to_measure="average_selling_price",
            maps_to_dimension=None,
            sql_expression="SUM(total_sales) / NULLIF(SUM(order_qty), 0)",
        ),
        "Revenue": SimpleNamespace(
            display_label="Revenue",
            synonyms=["sales", "turnover"],
            maps_to_measure="revenue",
            maps_to_dimension=None,
            sql_expression="SUM(total_sales)",
        ),
        "Region": SimpleNamespace(
            display_label="Region",
            synonyms=["zone", "territory"],
            maps_to_measure=None,
            maps_to_dimension="Region",
            sql_expression=None,
        ),
    }
    table = SimpleNamespace(columns={"sales_date": {}, "order_qty": {}, "total_sales": {}})
    return SimpleNamespace(
        glossary=SimpleNamespace(terms=terms),
        model=SimpleNamespace(tables={"fact_sales": table}),
    )


def test_average_selling_price_overrides_units_guess() -> None:
    plan = understand_question(Industry.AUTOMOTIVE, "average selling price by region")
    assert plan.metric == "units"
    formula = apply_glossary(plan, "average selling price by region", _pack())
    assert plan.metric == "average_selling_price"
    assert formula is not None
    assert "total_sales" in formula
    hit = resolve_template(Industry.AUTOMOTIVE, "average selling price by region", plan=plan)
    assert hit is not None
    assert "average_selling_price" in hit.sql.lower()


def test_followup_keeps_metric_and_adds_constraints() -> None:
    first = plan_semantic_query(Industry.AUTOMOTIVE, "sales by region", pack=_pack())
    assert first.plan.metric == "revenue"
    assert "region" in first.plan.dimensions

    mumbai = apply_followup(first.plan, "Only Mumbai")
    assert mumbai.metric == "revenue"
    assert any(item.value == "Mumbai" for item in mumbai.filters)
    assert "region" in mumbai.dimensions

    last_year = apply_followup(mumbai, "Last year")
    assert last_year.metric == "revenue"
    assert last_year.year_filter == mumbai.year_filter or last_year.year_filter
    assert any(item.value == "Mumbai" for item in last_year.filters)
    hit = resolve_template(Industry.AUTOMOTIVE, "Last year", plan=last_year)
    assert hit is not None
    assert "mumbai" in hit.sql.lower()
    assert "extract(year" in hit.sql.lower()

    compared = apply_followup(first.plan, "Compare with previous year")
    assert compared.analysis == "period_growth"
    assert compared.metric == "revenue"
    compared_sql = resolve_template(Industry.AUTOMOTIVE, "Compare with previous year", plan=compared)
    assert compared_sql is not None
    assert "lag(" in compared_sql.sql.lower()
    ok, reason = validate_sql_against_plan(compared_sql.sql, compared)
    assert ok, reason


def test_query_plan_trace_includes_formula_and_filters() -> None:
    planned = plan_semantic_query(Industry.AUTOMOTIVE, "sales in Mumbai", pack=_pack())
    trace = planned.trace()
    assert "SUM" in trace["formula"].upper() or "total_sales" in trace["formula"]
    assert any("Mumbai" in item for item in trace["filters"])


def test_group_by_validation_rejects_missing_dimension() -> None:
    plan = understand_question(Industry.AUTOMOTIVE, "revenue by region")
    sql = "SELECT SUM(f.total_sales) AS revenue FROM automotive.fact_sales f"
    ok, reason = validate_sql_against_plan(sql, plan)
    assert not ok
    assert reason is not None
    assert "dimension" in reason.lower() or "group by" in reason.lower()


def test_repair_uses_pack_date_column() -> None:
    sql = "SELECT invoice_date FROM automotive.fact_sales"
    repaired = propose_sql_repair(
        sql,
        'column "invoice_date" does not exist',
        _pack(),
    )
    assert repaired is not None
    assert "sales_date" in repaired


def test_plan_state_round_trip() -> None:
    plan = understand_question(Industry.AUTOMOTIVE, "revenue by region")
    restored = apply_followup(plan, "Only Mumbai")
    state = plan_state(restored)
    assert state["metric"] == "revenue"
    assert state["filters"]
