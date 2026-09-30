"""AI Chat robustness: synonym resolution, full parsing, planning, and clarification."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from app.core.config import Industry, get_settings
from app.semantic.service import SemanticService
from app.services.chat.clarification import (
    assess_resolution,
    plan_suggestions,
    recovery_for_failure,
)
from app.services.chat.entity_resolver import CatalogEntry, EntityResolver
from app.services.chat.question_understanding import ExtractedFilter, understand_question
from app.services.chat.semantic_context import build_allowed_schema, validate_sql_against_plan
from app.services.chat.semantic_query_planner import is_self_contained, plan_semantic_query
from app.services.chat.value_dictionary import BusinessValue, ValueDictionarySnapshot, resolver_for

AUTO = Industry.AUTOMOTIVE


@pytest.fixture(scope="module")
def pack() -> Any:
    return SemanticService(get_settings())._load_pack(AUTO)


@pytest.fixture(scope="module")
def snapshot() -> ValueDictionarySnapshot:
    # Empty live dictionary: resolution must work from the pack vocabulary alone.
    return ValueDictionarySnapshot(AUTO, ())


def _resolve(snapshot: ValueDictionarySnapshot, pack: Any, question: str) -> dict[str, str]:
    return {m.entry.canonical: m.method for m in snapshot.resolve(question, pack=pack).matches}


@pytest.mark.parametrize(
    ("question", "canonical", "method"),
    [
        ("Maruti Suzuki sales", "Maruti Suzuki", "exact"),
        ("Maruti sales", "Maruti Suzuki", "synonym"),
        ("Suzuki sales trend", "Maruti Suzuki", "synonym"),
        ("MSIL revenue", "Maruti Suzuki", "synonym"),
        ("MG sales by year", "MG", "exact"),
        ("Morris Garages revenue", "MG", "synonym"),
        ("MG Motors units", "MG", "synonym"),
        ("Mahindra & Mahindra sales", "Mahindra", "synonym"),
        ("Hundai sales by year", "Hyundai", "fuzzy"),
        ("Marutti revenue", "Maruti Suzuki", "fuzzy"),
        ("Vitara sales", "Grand Vitara", "synonym"),
        ("Altis sales", "Corolla Altis", "alias"),
        ("Sales in Bombay", "Mumbai", "synonym"),
        ("Revenue in Bangalore", "Bengaluru", "synonym"),
        ("EV sales by year", "Electric", "synonym"),
        ("SUVs sold in 2025", "SUV", "synonym"),
    ],
)
def test_resolver_cascade_maps_business_words_to_canonical_values(
    snapshot: ValueDictionarySnapshot, pack: Any, question: str, canonical: str, method: str
) -> None:
    assert _resolve(snapshot, pack, question).get(canonical) == method


def test_glossary_value_terms_resolve_after_catalog_stages() -> None:
    catalog = [CatalogEntry("Car Type", "automotive.dim_carline.car_type", "SUV")]
    glossary = SimpleNamespace(
        terms={
            "Crossover": SimpleNamespace(
                sql_expression="automotive.dim_carline.car_type = 'SUV'",
                synonyms=["soft roader"],
            )
        }
    )
    resolver = EntityResolver(catalog, pack=SimpleNamespace(glossary=glossary))
    matches = resolver.resolve("soft roader revenue").matches
    assert [(m.entry.canonical, m.method) for m in matches] == [("SUV", "glossary")]


def test_everyday_words_do_not_become_model_filters(
    snapshot: ValueDictionarySnapshot, pack: Any
) -> None:
    assert snapshot.match("Sales by city", pack=pack) == []
    filters = snapshot.match("Honda City sales by year", pack=pack)
    assert [(f.column, f.value) for f in filters] == [("automotive.dim_carline.model", "City")]


def test_city_beats_region_for_the_same_name() -> None:
    snapshot = ValueDictionarySnapshot(
        AUTO,
        (
            BusinessValue("City", "automotive.dim_region.city", "Nagpur", 40),
            BusinessValue("Region", "automotive.dim_region.region_name", "Nagpur", 90),
        ),
    )
    filters = snapshot.match("Revenue in Nagpur")
    assert [(f.column, f.value) for f in filters] == [("automotive.dim_region.city", "Nagpur")]


def test_several_values_of_one_column_become_one_in_filter(
    snapshot: ValueDictionarySnapshot, pack: Any
) -> None:
    filters = snapshot.match("Compare MG and Maruti sales", pack=pack)
    assert len(filters) == 1
    assert filters[0].operator == "IN"
    assert filters[0].all_values == ("MG", "Maruti Suzuki")


def test_unavailable_terms_and_unknown_names_are_reported(
    snapshot: ValueDictionarySnapshot, pack: Any
) -> None:
    profit = snapshot.resolve("Profit of Maruti", pack=pack)
    assert profit.unsupported and "cost" in profit.unsupported[0].message
    cng = snapshot.resolve("CNG car sales", pack=pack)
    assert cng.unsupported and "Petrol" in cng.unsupported[0].message
    unknown = snapshot.resolve("Ferrari sales", pack=pack)
    assert [u.text for u in unknown.unresolved] == ["ferrari"]
    assert not snapshot.resolve("Top brand by revenue", pack=pack).unresolved


def _plan(snapshot: ValueDictionarySnapshot, pack: Any, question: str) -> Any:
    resolution = snapshot.resolve(question, pack=pack)
    return plan_semantic_query(AUTO, question, value_filters=resolution.filters(), pack=pack)


SUCCESS_CRITERIA = [
    ("What sales of Maruti?", ["Maruti Suzuki"], "month", "trend"),
    ("Maruti sales by year", ["Maruti Suzuki"], "year", None),
    ("Suzuki sales trend", ["Maruti Suzuki"], "month", "trend"),
    ("MG sales by year", ["MG"], "year", None),
    ("MG revenue by month", ["MG"], "month", "trend"),
    ("Top selling MG model", ["MG"], "model", "ranking"),
    ("Maruti sales in Mumbai", ["Maruti Suzuki", "Mumbai"], "month", "trend"),
    ("Compare MG and Maruti sales", ["MG", "Maruti Suzuki"], "make", "comparison"),
    ("SUV sales by year", ["SUV"], "year", None),
    ("Top brand by revenue", [], "make", "ranking"),
]


@pytest.mark.parametrize(("question", "values", "dimension", "intent"), SUCCESS_CRITERIA)
def test_success_criteria_questions_plan_and_compile(
    snapshot: ValueDictionarySnapshot,
    pack: Any,
    question: str,
    values: list[str],
    dimension: str,
    intent: str | None,
) -> None:
    planned = _plan(snapshot, pack, question)
    plan = planned.plan
    assert not plan.is_ambiguous
    assert planned.sql, f"no SQL for {question!r}"
    assert dimension in plan.dimensions
    if intent:
        assert plan.intent == intent
    for value in values:
        assert f"'{value}'" in planned.sql
    assert "GROUP BY" in planned.sql
    ok, reason = validate_sql_against_plan(
        planned.sql, plan, allowed_schema=build_allowed_schema(pack)
    )
    assert ok, reason
    structured = planned.structured_plan()
    assert structured["metric"] in {"revenue", "units"}
    assert structured["chart"] in {"line", "bar", "pie"}


def test_brand_comparison_uses_in_filter_and_brand_grouping(
    snapshot: ValueDictionarySnapshot, pack: Any
) -> None:
    planned = _plan(snapshot, pack, "Compare MG and Maruti sales")
    assert "IN ('MG', 'Maruti Suzuki')" in planned.sql
    assert planned.structured_plan()["brand"] == ["MG", "Maruti Suzuki"]


def test_comparison_over_time_is_pivoted_one_series_per_brand(
    snapshot: ValueDictionarySnapshot, pack: Any
) -> None:
    planned = _plan(snapshot, pack, "Compare MG and Maruti sales by year")
    assert planned.chart_series == ("mg_revenue", "maruti_suzuki_revenue")
    assert "FILTER (WHERE c.make = 'MG')" in planned.sql
    assert planned.chart_type == "line"


def test_full_question_keeps_brand_dimension_city_and_intent(
    snapshot: ValueDictionarySnapshot, pack: Any
) -> None:
    planned = _plan(snapshot, pack, "Compare MG sales by year in Mumbai")
    structured = planned.structured_plan()
    assert structured["brand"] == "MG"
    assert structured["dimension"] == "year"
    assert structured["intent"] == "comparison"
    assert {"column": "city", "operator": "=", "values": ["Mumbai"]} in structured["filters"]
    assert "'Mumbai'" in planned.sql and "'MG'" in planned.sql


def test_brand_without_period_is_a_recent_monthly_trend(
    snapshot: ValueDictionarySnapshot, pack: Any
) -> None:
    planned = _plan(snapshot, pack, "Maruti")
    assert planned.defaulted_grain
    assert planned.plan.dimensions == ["month"]
    assert "MAX(latest.sales_date)" in planned.sql


def test_market_share_is_measured_against_all_brands(
    snapshot: ValueDictionarySnapshot, pack: Any
) -> None:
    planned = _plan(snapshot, pack, "Maruti market share by year")
    assert planned.plan.analysis == "market_share"
    assert planned.plan.dimensions == ["year", "make"]
    sql = planned.sql
    assert "SUM(units_sold) OVER (PARTITION BY year)" in sql
    assert "WHERE make IN ('Maruti Suzuki')" in sql.split("FROM shared", 1)[1]


def test_year_literals_become_filters(snapshot: ValueDictionarySnapshot, pack: Any) -> None:
    planned = _plan(snapshot, pack, "MG sales in 2024 by month")
    assert planned.plan.year_filter == 2024
    assert "= 2024" in planned.sql


def test_scope_less_sales_trend_asks_for_scope() -> None:
    plan = understand_question(AUTO, "Sales trend")
    assert plan.is_ambiguous
    assert "Maruti Suzuki sales trend" in plan.ambiguity_options


def test_unresolved_brand_asks_instead_of_answering_unfiltered(
    snapshot: ValueDictionarySnapshot, pack: Any
) -> None:
    question = "Ferrari sales"
    resolution = snapshot.resolve(question, pack=pack)
    plan = understand_question(AUTO, question, value_filters=resolution.filters())
    brands = resolver_for(snapshot, pack).canonical_values("make")
    clarification = assess_resolution(question, plan, resolution, industry=AUTO, brands=brands)
    assert clarification is not None and clarification.kind == "unresolved"
    assert "Top brand by revenue" in clarification.options


def test_unavailable_metric_offers_scoped_alternatives(
    snapshot: ValueDictionarySnapshot, pack: Any
) -> None:
    question = "Profit of Maruti"
    resolution = snapshot.resolve(question, pack=pack)
    plan = understand_question(AUTO, question, value_filters=resolution.filters())
    clarification = assess_resolution(question, plan, resolution, industry=AUTO)
    assert clarification is not None and clarification.kind == "unsupported"
    assert "Maruti Suzuki revenue by year" in clarification.options


def test_failures_become_recovery_suggestions_in_the_users_scope(
    snapshot: ValueDictionarySnapshot, pack: Any
) -> None:
    plan = _plan(snapshot, pack, "MG sales by year").plan
    recovery = recovery_for_failure("database", plan, industry=AUTO, question="MG sales by year")
    assert recovery.kind == "recovery"
    assert "SQL" not in recovery.title and "Error" not in recovery.title
    assert recovery.options[:3] == [
        "MG sales by month",
        "MG revenue by year",
        "MG units sold by year",
    ]
    assert plan_suggestions(None, industry=AUTO)


def test_self_contained_question_is_not_treated_as_a_follow_up() -> None:
    mg = [ExtractedFilter("automotive.dim_carline.make", "=", "MG", "Make = MG")]
    assert is_self_contained("MG sales last year", mg)
    assert not is_self_contained("compare with last year", [])


def test_builder_multi_value_filter_is_in_not_and() -> None:
    from app.schemas.analytics import AnalyticsFilterSpec, AnalyticsSpec
    from app.services.analytics.spec_to_plan import spec_to_plan

    spec = AnalyticsSpec(
        metrics=["revenue"],
        dimensions=["make"],
        filters=[AnalyticsFilterSpec(domain="make", values=["MG", "Kia"])],
    )
    plan = spec_to_plan(spec, AUTO, None)
    assert len(plan.filters) == 1
    assert plan.filters[0].all_values == ("MG", "Kia")


def _filter_values(
    snapshot: ValueDictionarySnapshot, pack: Any, question: str
) -> dict[str, set[str]]:
    return {
        f.column.rsplit(".", 1)[-1]: set(f.values or (f.value,))
        for f in snapshot.resolve(question, pack=pack).filters()
    }


@pytest.mark.parametrize(
    ("question", "column", "expected"),
    [
        ("SUV sales in 2025", "car_type", {"SUV", "Compact SUV", "Mid SUV", "Premium SUV"}),
        ("compact SUV sales in 2025", "car_type", {"Compact SUV"}),
        ("sedan revenue by year", "car_type", {"Sedan", "Compact Sedan", "Premium Sedan"}),
        ("Innova sales by year", "model", {"Innova", "Innova Crysta", "Innova Hycross"}),
        ("sales in NCR", "city", {"New Delhi", "Gurugram", "Noida", "Faridabad", "Ghaziabad"}),
    ],
)
def test_umbrella_terms_expand_to_their_family(
    snapshot: ValueDictionarySnapshot, pack: Any, question: str, column: str, expected: set[str]
) -> None:
    assert _filter_values(snapshot, pack, question).get(column) == expected


def test_generic_words_do_not_become_model_filters(
    snapshot: ValueDictionarySnapshot, pack: Any
) -> None:
    assert "model" not in _filter_values(snapshot, pack, "which dealers show rapid growth")
    assert _filter_values(snapshot, pack, "Skoda Rapid sales").get("model") == {"Rapid"}
