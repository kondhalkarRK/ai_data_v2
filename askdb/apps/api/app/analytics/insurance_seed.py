"""Deterministic insurance dimension and fact generators (1M claims default)."""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from random import Random
from typing import TypeVar

T = TypeVar("T")

RNG_SEED = 42
DEFAULT_CLAIM_ROWS = 1_000_000
DEFAULT_POLICY_ROWS = 120_000
DEFAULT_AGENT_ROWS = 400
DEFAULT_MONTHLY_POLICY_SAMPLE = 40_000

PRODUCTS: tuple[tuple[str, str, str, str, str], ...] = (
    ("MOT-COMP", "Motor Comprehensive", "Motor", "Personal Lines", "Comprehensive"),
    ("MOT-TP", "Motor Third Party", "Motor", "Personal Lines", "Third Party"),
    ("HLTH-IND", "Health Individual", "Health", "Personal Lines", "Indemnity"),
    ("HLTH-FAM", "Health Family Floater", "Health", "Personal Lines", "Floater"),
    ("HOME-STD", "Home Standard", "Property", "Personal Lines", "Building+Contents"),
    ("HOME-PREM", "Home Premium", "Property", "Personal Lines", "All Risk"),
    ("TRAV-DOM", "Travel Domestic", "Travel", "Personal Lines", "Domestic"),
    ("TRAV-INT", "Travel International", "Travel", "Personal Lines", "International"),
    ("SME-FIRE", "SME Fire", "Commercial", "Commercial Lines", "Fire"),
    ("SME-BURG", "SME Burglary", "Commercial", "Commercial Lines", "Burglary"),
    ("CYBER", "Cyber Liability", "Liability", "Commercial Lines", "Cyber"),
    ("WC", "Workmen Compensation", "Liability", "Commercial Lines", "WC"),
)

REGIONS: tuple[tuple[str, str, str], ...] = (
    ("NCR", "National Capital Region", "Delhi"),
    ("MH-W", "Mumbai Metro", "Maharashtra"),
    ("MH-P", "Pune Belt", "Maharashtra"),
    ("KA-B", "Bengaluru Metro", "Karnataka"),
    ("TS-H", "Hyderabad Metro", "Telangana"),
    ("TN-C", "Chennai Metro", "Tamil Nadu"),
    ("WB-K", "Kolkata Metro", "West Bengal"),
    ("GJ-A", "Ahmedabad Hub", "Gujarat"),
    ("RJ-J", "Jaipur Circle", "Rajasthan"),
    ("UP-L", "Lucknow Circle", "Uttar Pradesh"),
    ("PB-C", "Chandigarh Tri-City", "Punjab"),
    ("KL-K", "Kochi Harbour", "Kerala"),
    ("MP-I", "Indore Belt", "Madhya Pradesh"),
    ("OD-B", "Bhubaneswar", "Odisha"),
    ("AS-G", "Guwahati", "Assam"),
    ("GA-P", "Goa Coastal", "Goa"),
    ("HR-G", "Gurugram Belt", "Haryana"),
    ("UP-N", "Noida Hub", "Uttar Pradesh"),
    ("KA-M", "Mysuru", "Karnataka"),
    ("TN-CBE", "Coimbatore", "Tamil Nadu"),
    ("AP-V", "Visakhapatnam", "Andhra Pradesh"),
    ("MH-N", "Nagpur", "Maharashtra"),
    ("GJ-S", "Surat Coast", "Gujarat"),
    ("RJ-JDH", "Jodhpur", "Rajasthan"),
    ("UK-D", "Dehradun", "Uttarakhand"),
    ("HP-S", "Shimla", "Himachal Pradesh"),
    ("BR-P", "Patna", "Bihar"),
    ("JH-R", "Ranchi", "Jharkhand"),
    ("CG-R", "Raipur", "Chhattisgarh"),
    ("PB-L", "Ludhiana", "Punjab"),
    ("TN-M", "Madurai", "Tamil Nadu"),
    ("KA-MNG", "Mangaluru", "Karnataka"),
    ("MH-NSK", "Nashik", "Maharashtra"),
    ("GJ-V", "Vadodara", "Gujarat"),
    ("UP-K", "Kanpur", "Uttar Pradesh"),
    ("UP-V", "Varanasi", "Uttar Pradesh"),
    ("KL-T", "Trivandrum", "Kerala"),
    ("AP-VJW", "Vijayawada", "Andhra Pradesh"),
    ("TS-W", "Hyderabad West", "Telangana"),
    ("DL-S", "South Delhi", "Delhi"),
)

CLAIM_STATUSES = ("Open", "Approved", "Settled", "Repudiated", "Pending Docs")
CLAIM_TYPES = ("Accident", "Theft", "Illness", "Property Damage", "Liability", "Other")
CHANNELS = ("Agency", "Bancassurance", "Direct", "Digital", "Broker")
TIERS = ("Basic", "Standard", "Gold", "Platinum")
STATUSES = ("Active", "Lapsed", "Cancelled", "Expired")


def _weighted_choice(rng: Random, items: tuple[T, ...], weights: tuple[float, ...]) -> T:
    total = sum(weights)
    pick = rng.random() * total
    cumulative = 0.0
    for item, weight in zip(items, weights, strict=True):
        cumulative += weight
        if pick <= cumulative:
            return item
    return items[-1]


@dataclass(frozen=True, slots=True)
class Product:
    product_id: int
    product_code: str
    product_name: str
    line_of_business: str
    product_family: str
    coverage_type: str
    active_flag: bool = True


@dataclass(frozen=True, slots=True)
class Agent:
    agent_id: int
    agent_code: str
    agent_name: str
    channel_name: str
    branch_name: str
    active_flag: bool = True


@dataclass(frozen=True, slots=True)
class Region:
    region_id: int
    region_code: str
    region_name: str
    state_name: str
    country_name: str = "India"


@dataclass(frozen=True, slots=True)
class Policy:
    policy_id: int
    policy_number: str
    product_id: int
    agent_id: int
    region_id: int
    customer_key: str
    inception_date: date
    expiry_date: date
    policy_status: str
    coverage_tier: str
    sum_insured: float
    cancelled_flag: bool


@dataclass(frozen=True, slots=True)
class InsuranceDimensions:
    products: tuple[Product, ...]
    agents: tuple[Agent, ...]
    regions: tuple[Region, ...]
    policies: tuple[Policy, ...]


def build_dimensions(
    *,
    policy_count: int = DEFAULT_POLICY_ROWS,
    agent_count: int = DEFAULT_AGENT_ROWS,
    rng_seed: int = RNG_SEED,
) -> InsuranceDimensions:
    rng = Random(rng_seed)
    products = tuple(
        Product(
            product_id=i + 1,
            product_code=code,
            product_name=name,
            line_of_business=lob,
            product_family=family,
            coverage_type=coverage,
        )
        for i, (code, name, lob, family, coverage) in enumerate(PRODUCTS)
    )
    regions = tuple(
        Region(
            region_id=i + 1,
            region_code=code,
            region_name=name,
            state_name=state,
        )
        for i, (code, name, state) in enumerate(REGIONS)
    )
    agents = tuple(
        Agent(
            agent_id=i + 1,
            agent_code=f"AG{i + 1:04d}",
            agent_name=f"Agent {i + 1:04d}",
            channel_name=rng.choice(CHANNELS),
            branch_name=regions[i % len(regions)].region_name,
            active_flag=i % 19 != 0,
        )
        for i in range(agent_count)
    )

    policies: list[Policy] = []
    start = date(2019, 1, 1)
    for i in range(policy_count):
        product = products[i % len(products)]
        agent = agents[i % len(agents)]
        region = regions[i % len(regions)]
        inception = start + timedelta(days=rng.randint(0, 2500))
        term_days = rng.choice([365, 365, 366, 730])
        expiry = inception + timedelta(days=term_days)
        cancelled = i % 37 == 0
        status = (
            "Cancelled" if cancelled else _weighted_choice(rng, STATUSES, (0.72, 0.12, 0.08, 0.08))
        )
        policies.append(
            Policy(
                policy_id=i + 1,
                policy_number=f"POL{i + 1:08d}",
                product_id=product.product_id,
                agent_id=agent.agent_id,
                region_id=region.region_id,
                customer_key=f"CUST{(i % 80_000) + 1:06d}",
                inception_date=inception,
                expiry_date=expiry,
                policy_status=status,
                coverage_tier=rng.choice(TIERS),
                sum_insured=round(rng.uniform(50_000, 5_000_000), 2),
                cancelled_flag=cancelled,
            )
        )

    return InsuranceDimensions(
        products=products,
        agents=agents,
        regions=regions,
        policies=tuple(policies),
    )


def iter_claims(
    dims: InsuranceDimensions,
    *,
    row_count: int = DEFAULT_CLAIM_ROWS,
    rng_seed: int = RNG_SEED,
) -> Iterator[
    tuple[
        int,
        str,
        int,
        int,
        int,
        date,
        date,
        date | None,
        date | None,
        str,
        str,
        float,
        float,
        float,
        float,
        bool,
        bool,
        bool,
        str | None,
        datetime,
    ]
]:
    if row_count < 1:
        raise ValueError("row_count must be >= 1")
    rng = Random(rng_seed + 11)
    policies = dims.policies
    for claim_id in range(1, row_count + 1):
        policy = policies[(claim_id * 7) % len(policies)]
        loss = policy.inception_date + timedelta(
            days=rng.randint(0, max((policy.expiry_date - policy.inception_date).days, 1))
        )
        reported = loss + timedelta(days=rng.randint(0, 45))
        status = _weighted_choice(rng, CLAIM_STATUSES, (0.18, 0.22, 0.40, 0.12, 0.08))
        approved = status in {"Approved", "Settled"}
        repudiated = status == "Repudiated"
        reported_amount = round(rng.uniform(2_000, 450_000), 2)
        approved_amount = round(reported_amount * rng.uniform(0.6, 1.0), 2) if approved else 0.0
        paid_amount = (
            round(approved_amount * rng.uniform(0.5, 1.0), 2) if status == "Settled" else 0.0
        )
        reserve_amount = (
            round(max(approved_amount - paid_amount, 0) * rng.uniform(0.2, 0.8), 2)
            if status in {"Open", "Approved", "Pending Docs"}
            else 0.0
        )
        approved_date = reported + timedelta(days=rng.randint(5, 60)) if approved else None
        settlement_date = (
            (approved_date or reported) + timedelta(days=rng.randint(5, 90))
            if status == "Settled"
            else None
        )
        yield (
            claim_id,
            f"CLM{claim_id:09d}",
            policy.policy_id,
            policy.product_id,
            policy.region_id,
            loss,
            reported,
            approved_date,
            settlement_date,
            status,
            rng.choice(CLAIM_TYPES),
            reported_amount,
            approved_amount,
            paid_amount,
            reserve_amount,
            approved,
            repudiated,
            claim_id % 211 == 0,
            f"CAT-{reported.year}" if claim_id % 503 == 0 else None,
            datetime(reported.year, reported.month, reported.day, tzinfo=UTC),
        )


def iter_policy_monthly(
    dims: InsuranceDimensions,
    *,
    sample_policies: int = DEFAULT_MONTHLY_POLICY_SAMPLE,
    rng_seed: int = RNG_SEED,
) -> Iterator[tuple[int, int, int, int, int, date, float, float, float, bool, bool, bool | None]]:
    rng = Random(rng_seed + 19)
    row_id = 1
    for policy in dims.policies[:sample_policies]:
        months = rng.randint(6, 18)
        month = date(policy.inception_date.year, policy.inception_date.month, 1)
        for _ in range(months):
            written = round(rng.uniform(800, 18_000), 2)
            earned = round(written * rng.uniform(0.7, 1.0), 2)
            yield (
                row_id,
                policy.policy_id,
                policy.product_id,
                policy.agent_id,
                policy.region_id,
                month,
                written,
                earned,
                round(rng.uniform(0.2, 1.0), 6),
                policy.policy_status == "Active",
                month.month == policy.expiry_date.month,
                True if rng.random() < 0.55 else False if rng.random() < 0.5 else None,
            )
            row_id += 1
            if month.month == 12:
                month = date(month.year + 1, 1, 1)
            else:
                month = date(month.year, month.month + 1, 1)


def iter_operating_expense(
    dims: InsuranceDimensions,
    *,
    rng_seed: int = RNG_SEED,
) -> Iterator[tuple[int, date, int, int, float, float]]:
    rng = Random(rng_seed + 23)
    row_id = 1
    month = date(2023, 1, 1)
    end = date(2026, 9, 1)
    while month <= end:
        for product in dims.products:
            for region in dims.regions[::2]:  # every other region keeps opex manageable
                yield (
                    row_id,
                    month,
                    product.product_id,
                    region.region_id,
                    round(rng.uniform(5_000, 80_000), 2),
                    round(rng.uniform(8_000, 120_000), 2),
                )
                row_id += 1
        if month.month == 12:
            month = date(month.year + 1, 1, 1)
        else:
            month = date(month.year, month.month + 1, 1)
