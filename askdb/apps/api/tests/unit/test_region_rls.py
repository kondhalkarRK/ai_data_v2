"""Region row-level security: zone mapping, SQL rewrite, deny rules."""

from __future__ import annotations

from app.core.config import Industry
from app.services.security.region_scope import (
    RegionScope,
    apply_region_sql,
    forbidden_zones,
    mentioned_zones,
    zone_for_label,
)


def _north() -> RegionScope:
    return RegionScope(unrestricted=False, zones=("North",))


def test_zone_mapping_uses_state_not_compass_word_in_the_name() -> None:
    assert zone_for_label("North Delhi") == "North"
    assert zone_for_label("Bengaluru North") == "South"
    assert zone_for_label("Mumbai West") == "West"
    assert zone_for_label("Kolkata South") == "East"
    assert zone_for_label("South") == "South"
    assert zone_for_label("KA") == "South"


def test_compare_question_is_denied_for_a_single_zone_user() -> None:
    assert mentioned_zones("Compare North and South sales") == ("North", "South")
    assert forbidden_zones("Compare North and South sales", _north()) == ("South",)
    assert forbidden_zones("Show total sales by region", _north()) == ()
    assert forbidden_zones("Show top dealers", _north()) == ()


def test_sql_rewrite_scopes_fact_and_region_tables() -> None:
    sql = (
        "SELECT r.region_name, SUM(f.total_sales) "
        "FROM automotive.fact_sales f "
        "JOIN automotive.dim_region r ON r.region_id = f.region_id "
        "GROUP BY 1"
    )
    out = apply_region_sql(sql, Industry.AUTOMOTIVE, _north())
    assert "/*rls*/" in out
    assert "IN ('North')" in out
    assert "automotive.fact_sales" in out
    assert apply_region_sql(sql, Industry.AUTOMOTIVE, RegionScope.all_regions()) == sql


def test_explain_and_set_are_left_intact() -> None:
    assert apply_region_sql(
        "SET LOCAL statement_timeout = 5000", Industry.AUTOMOTIVE, _north()
    ).startswith("SET")
    explained = apply_region_sql(
        "EXPLAIN SELECT 1 FROM automotive.fact_sales f",
        Industry.AUTOMOTIVE,
        _north(),
    )
    assert explained.upper().startswith("EXPLAIN")
    assert "/*rls*/" in explained
