"""Public seed vocabulary for chat routing eval (mirrors benchmark dictionary sources)."""

from __future__ import annotations

from collections import Counter
from functools import cache

from app.analytics import automotive_seed, insurance_seed
from app.core.config import Industry
from app.services.chat.value_dictionary import BusinessValue


@cache
def seed_values_for_industry(industry: Industry) -> tuple[BusinessValue, ...]:
    rows: list[tuple[str, str, list[str]]] = []
    if industry is Industry.AUTOMOTIVE:
        d = automotive_seed.build_dimensions()
        rows = [
            ("Car Type", "automotive.dim_carline.car_type", [c.car_type for c in d.carlines]),
            ("Make", "automotive.dim_carline.make", [c.make for c in d.carlines]),
            ("Model", "automotive.dim_carline.model", [c.model for c in d.carlines]),
            (
                "Engine Type",
                "automotive.dim_carline.engine_type",
                [c.engine_type for c in d.carlines],
            ),
            ("Colour", "automotive.dim_color.colour_name", [c.colour_name for c in d.colours]),
            ("City", "automotive.dim_region.city", [r.city for r in d.regions]),
            ("Region", "automotive.dim_region.region_name", [r.region_name for r in d.regions]),
            ("State", "automotive.dim_region.state_code", [r.state_code for r in d.regions]),
            (
                "Dealer Grade",
                "automotive.dim_dealer.dealer_grade",
                [x.dealer_grade for x in d.dealers],
            ),
        ]
    else:
        d = insurance_seed.build_dimensions(policy_count=2_000)
        rows = [
            (
                "Claim Status",
                "insurance.fact_claims.claim_status",
                list(insurance_seed.CLAIM_STATUSES),
            ),
            ("Claim Type", "insurance.fact_claims.claim_type", list(insurance_seed.CLAIM_TYPES)),
            (
                "Policy Status",
                "insurance.dim_policy.policy_status",
                [p.policy_status for p in d.policies],
            ),
            (
                "Coverage Tier",
                "insurance.dim_policy.coverage_tier",
                [p.coverage_tier for p in d.policies],
            ),
            ("Product", "insurance.dim_product.product_name", [p.product_name for p in d.products]),
            (
                "Line of Business",
                "insurance.dim_product.line_of_business",
                [p.line_of_business for p in d.products],
            ),
            (
                "Product Family",
                "insurance.dim_product.product_family",
                [p.product_family for p in d.products],
            ),
            (
                "Coverage Type",
                "insurance.dim_product.coverage_type",
                [p.coverage_type for p in d.products],
            ),
            ("Channel", "insurance.dim_agent.channel_name", [a.channel_name for a in d.agents]),
            ("Branch", "insurance.dim_agent.branch_name", [a.branch_name for a in d.agents]),
            ("Region", "insurance.dim_region.region_name", [r.region_name for r in d.regions]),
            ("State", "insurance.dim_region.state_name", [r.state_name for r in d.regions]),
        ]
    values: list[BusinessValue] = []
    for domain, column, items in rows:
        for value, count in Counter(items).items():
            values.append(BusinessValue(domain, column, str(value), count))
    return tuple(values)
