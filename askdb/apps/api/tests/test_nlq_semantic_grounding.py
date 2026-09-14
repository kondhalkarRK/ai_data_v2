"""Semantic-pack, value-domain, and prompt-isolation contracts."""

from __future__ import annotations

import pytest

from app.core.config import Industry, get_settings
from app.semantic.service import SemanticService
from app.services.chat.question_understanding import understand_question
from app.services.chat.semantic_context import (
    build_allowed_schema,
    build_domain_sql_hints,
)
from app.services.chat.value_dictionary import (
    BusinessValue,
    ValueDictionarySnapshot,
    domains_for,
)
from app.services.llm import _slim_system_prompt


@pytest.mark.asyncio
@pytest.mark.parametrize("industry", list(Industry))
async def test_pack_declares_valid_value_domains(industry: Industry) -> None:
    pack = await SemanticService(get_settings()).get_pack(industry)
    assert pack.model.value_domains
    domains = domains_for(industry, pack)
    assert domains
    allowed = build_allowed_schema(pack)
    for domain in domains:
        assert domain.table.lower() in allowed
        assert domain.column.lower() in allowed[domain.table.lower()]


@pytest.mark.asyncio
async def test_domain_prompts_are_strictly_isolated() -> None:
    service = SemanticService(get_settings())
    auto_pack = await service.get_pack(Industry.AUTOMOTIVE)
    auto_plan = understand_question(Industry.AUTOMOTIVE, "Top salesperson")
    auto_hints = build_domain_sql_hints(
        industry=Industry.AUTOMOTIVE,
        question="Top salesperson",
        plan=auto_plan,
        pack=auto_pack,
    ).lower()
    assert "automotive.fact_sales" in auto_hints
    assert "insurance.fact_claims" not in auto_hints

    insurance_pack = await service.get_pack(Industry.INSURANCE)
    insurance_plan = understand_question(Industry.INSURANCE, "Top agent by premium")
    insurance_hints = build_domain_sql_hints(
        industry=Industry.INSURANCE,
        question="Top agent by premium",
        plan=insurance_plan,
        pack=insurance_pack,
    ).lower()
    assert "insurance.fact_policy_monthly" in insurance_hints
    assert "automotive.fact_sales" not in insurance_hints


def test_pack_value_aliases_resolve_business_language() -> None:
    snapshot = ValueDictionarySnapshot(
        Industry.AUTOMOTIVE,
        (
            BusinessValue(
                domain="City",
                column="automotive.dim_region.city",
                value="New Delhi",
                frequency=2,
                aliases=("Delhi", "Delhi NCR"),
            ),
        ),
    )
    filters = snapshot.match("Revenue in Delhi")
    assert len(filters) == 1
    assert filters[0].value == "New Delhi"
    assert filters[0].column == "automotive.dim_region.city"


def test_prompt_contains_only_matched_value_not_dictionary_dump() -> None:
    plan = understand_question(
        Industry.AUTOMOTIVE,
        "Top dealer in Mumbai",
        value_filters=[
            ValueDictionarySnapshot(
                Industry.AUTOMOTIVE,
                (
                    BusinessValue(
                        "City",
                        "automotive.dim_region.city",
                        "Mumbai",
                        2,
                    ),
                    BusinessValue(
                        "City",
                        "automotive.dim_region.city",
                        "Pune",
                        2,
                    ),
                ),
            ).match("Top dealer in Mumbai")[0]
        ],
    )
    hints = build_domain_sql_hints(
        industry=Industry.AUTOMOTIVE,
        question="Top dealer in Mumbai",
        plan=plan,
        pack=None,
    )
    assert "Mumbai" in hints
    assert "Pune" not in hints
    assert len(hints) < 2800


def test_followup_prompt_carries_prior_successful_sql() -> None:
    prior = (
        "SELECT c.model, SUM(f.order_qty) AS units_sold "
        "FROM automotive.fact_sales f "
        "JOIN automotive.dim_carline c ON c.carline_id = f.carline_id "
        "GROUP BY 1 ORDER BY units_sold DESC LIMIT 10"
    )
    prompt = _slim_system_prompt(
        Industry.AUTOMOTIVE,
        "Resolved entity: region\nMandatory filter: city = 'Mumbai'",
        prior,
    )
    assert "PRIOR SUCCESSFUL SQL" in prompt
    assert prior in prompt
    assert "preserve its intent, joins, and filters" in prompt
