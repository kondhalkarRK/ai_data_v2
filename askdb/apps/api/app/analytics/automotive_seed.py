"""Deterministic automotive dimension and fact generators.

The seed is intentionally pure Python so unit tests can validate distributions without
PostgreSQL. ``scripts/seed_automotive.py`` loads the rows with ``COPY``.
"""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from datetime import date, timedelta
from random import Random
from typing import TypeVar

T = TypeVar("T")

RNG_SEED = 42
DEFAULT_FACT_ROWS = 1_000_000

# Mid-range of the proposal ranges, sized for a 1M fact table.
CARLINE_COUNT = 50
COLOUR_COUNT = 24
SALESMAN_COUNT = 500
REGION_COUNT = 50
DEALER_COUNT = 300
TARGET_START = date(2024, 1, 1)
TARGET_END = date(2026, 12, 1)
SALES_START = date(2019, 1, 1)
SALES_END = date(2026, 9, 9)

MAKES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("Maruti Suzuki", ("Swift", "Baleno", "Brezza", "Ertiga", "Grand Vitara")),
    ("Hyundai", ("i20", "Creta", "Venue", "Verna", "Alcazar")),
    ("Tata", ("Nexon", "Punch", "Harrier", "Safari", "Tiago")),
    ("Mahindra", ("XUV700", "Scorpio-N", "Thar", "Bolero", "XUV3XO")),
    ("Honda", ("City", "Amaze", "Elevate")),
    ("Toyota", ("Innova Crysta", "Fortuner", "Glanza", "Hyryder")),
    ("Kia", ("Seltos", "Sonet", "Carens", "EV6")),
    ("MG", ("Hector", "Astor", "ZS EV", "Comet EV")),
    ("Skoda", ("Kushaq", "Slavia", "Kodiaq")),
    ("Volkswagen", ("Taigun", "Virtus", "Tiguan")),
    ("Renault", ("Kiger", "Triber", "Kwid")),
    ("Nissan", ("Magnite", "X-Trail")),
)

CAR_TYPES = ("Hatchback", "Sedan", "SUV", "MUV", "Coupe")
ENGINE_TYPES = ("Petrol", "Diesel", "Hybrid", "Electric")
COLOUR_NAMES = (
    "Pearl White",
    "Arctic Silver",
    "Midnight Black",
    "Fire Red",
    "Ocean Blue",
    "Forest Green",
    "Sunburst Orange",
    "Graphite Grey",
    "Champagne Gold",
    "Royal Purple",
    "Sky Cyan",
    "Desert Beige",
    "Crimson Metallic",
    "Ice Blue",
    "Matte Bronze",
    "Storm Grey",
    "Emerald Pearl",
    "Coral Pink",
    "Titanium",
    "Nardo Grey",
    "Lava Orange",
    "Aurora Green",
    "Cosmic Blue",
    "Ivory",
)
FIRST_NAMES = (
    "Aarav",
    "Ananya",
    "Rohan",
    "Isha",
    "Kabir",
    "Meera",
    "Arjun",
    "Priya",
    "Vikram",
    "Neha",
    "Aditya",
    "Sneha",
    "Rahul",
    "Kavya",
    "Siddharth",
    "Pooja",
    "Nikhil",
    "Divya",
    "Harsh",
    "Shreya",
)
LAST_NAMES = (
    "Sharma",
    "Patel",
    "Singh",
    "Reddy",
    "Nair",
    "Iyer",
    "Gupta",
    "Khan",
    "Das",
    "Joshi",
    "Mehta",
    "Chopra",
    "Banerjee",
    "Pillai",
    "Verma",
)
# (region_name, city, state_code)
REGION_SEED: tuple[tuple[str, str, str], ...] = (
    ("North Delhi", "New Delhi", "DL"),
    ("South Delhi", "New Delhi", "DL"),
    ("Noida Hub", "Noida", "UP"),
    ("Gurgaon Belt", "Gurugram", "HR"),
    ("Mumbai West", "Mumbai", "MH"),
    ("Mumbai Central", "Mumbai", "MH"),
    ("Pune East", "Pune", "MH"),
    ("Pune West", "Pune", "MH"),
    ("Bengaluru North", "Bengaluru", "KA"),
    ("Bengaluru South", "Bengaluru", "KA"),
    ("Hyderabad East", "Hyderabad", "TS"),
    ("Hyderabad West", "Hyderabad", "TS"),
    ("Chennai Central", "Chennai", "TN"),
    ("Chennai South", "Chennai", "TN"),
    ("Kolkata North", "Kolkata", "WB"),
    ("Kolkata South", "Kolkata", "WB"),
    ("Ahmedabad City", "Ahmedabad", "GJ"),
    ("Surat Coast", "Surat", "GJ"),
    ("Jaipur Metro", "Jaipur", "RJ"),
    ("Lucknow Central", "Lucknow", "UP"),
    ("Chandigarh Tri-City", "Chandigarh", "CH"),
    ("Indore Belt", "Indore", "MP"),
    ("Bhopal Circle", "Bhopal", "MP"),
    ("Kochi Harbour", "Kochi", "KL"),
    ("Trivandrum", "Thiruvananthapuram", "KL"),
    ("Coimbatore", "Coimbatore", "TN"),
    ("Madurai", "Madurai", "TN"),
    ("Visakhapatnam", "Visakhapatnam", "AP"),
    ("Vijayawada", "Vijayawada", "AP"),
    ("Nagpur", "Nagpur", "MH"),
    ("Nashik", "Nashik", "MH"),
    ("Vadodara", "Vadodara", "GJ"),
    ("Rajkot", "Rajkot", "GJ"),
    ("Patna", "Patna", "BR"),
    ("Ranchi", "Ranchi", "JH"),
    ("Bhubaneswar", "Bhubaneswar", "OD"),
    ("Guwahati", "Guwahati", "AS"),
    ("Dehradun", "Dehradun", "UK"),
    ("Shimla", "Shimla", "HP"),
    ("Goa Coastal", "Panaji", "GA"),
    ("Mysuru", "Mysuru", "KA"),
    ("Mangaluru", "Mangaluru", "KA"),
    ("Hubballi", "Hubballi", "KA"),
    ("Aurangabad", "Chhatrapati Sambhajinagar", "MH"),
    ("Amritsar", "Amritsar", "PB"),
    ("Ludhiana", "Ludhiana", "PB"),
    ("Kanpur", "Kanpur", "UP"),
    ("Varanasi", "Varanasi", "UP"),
    ("Raipur", "Raipur", "CG"),
    ("Jodhpur", "Jodhpur", "RJ"),
)

YEAR_WEIGHTS: dict[int, float] = {
    2019: 0.10,
    2020: 0.07,  # volume dip
    2021: 0.11,
    2022: 0.13,
    2023: 0.15,
    2024: 0.16,
    2025: 0.16,
    2026: 0.12,
}


@dataclass(frozen=True, slots=True)
class Carline:
    carline_id: int
    carline_name: str
    model: str
    make: str
    car_type: str
    engine_capacity: float | None
    engine_type: str
    base_price: float


@dataclass(frozen=True, slots=True)
class Colour:
    colour_id: int
    colour_name: str
    rcg_combination: str
    patent_number: str | None


@dataclass(frozen=True, slots=True)
class Salesman:
    sales_person_id: int
    first_name: str
    last_name: str
    email: str
    corp_id: str
    active: bool


@dataclass(frozen=True, slots=True)
class Region:
    region_id: int
    region_name: str
    city: str
    state_code: str
    country: str = "India"


@dataclass(frozen=True, slots=True)
class Dealer:
    dealer_id: int
    dealer_code: str
    dealer_name: str
    region_id: int
    city: str
    dealer_grade: str
    active: bool


@dataclass(frozen=True, slots=True)
class Target:
    target_id: int
    year_month: date
    make: str
    target_units: int
    target_revenue: float


@dataclass(frozen=True, slots=True)
class DimensionBundle:
    carlines: tuple[Carline, ...]
    colours: tuple[Colour, ...]
    salesmen: tuple[Salesman, ...]
    regions: tuple[Region, ...]
    dealers: tuple[Dealer, ...]
    targets: tuple[Target, ...]

    @property
    def makes(self) -> tuple[str, ...]:
        return tuple(sorted({row.make for row in self.carlines}))


def _weighted_choice(rng: Random, items: Sequence[T], weights: Sequence[float]) -> T:
    total = sum(weights)
    pick = rng.random() * total
    cumulative = 0.0
    for item, weight in zip(items, weights, strict=True):
        cumulative += weight
        if pick <= cumulative:
            return item
    return items[-1]


def build_dimensions(*, rng_seed: int = RNG_SEED) -> DimensionBundle:
    """Build the full dimension set with a fixed seed."""
    rng = Random(rng_seed)

    carlines: list[Carline] = []
    carline_id = 1
    while len(carlines) < CARLINE_COUNT:
        for make, models in MAKES:
            for model in models:
                if len(carlines) >= CARLINE_COUNT:
                    break
                # EV share is higher for brands that already list EV models.
                if "EV" in model.upper() or model in {"Comet EV", "ZS EV", "EV6"}:
                    engine_type = "Electric"
                else:
                    engine_type = _weighted_choice(rng, ENGINE_TYPES, (0.48, 0.22, 0.18, 0.12))
                capacity = (
                    None
                    if engine_type == "Electric"
                    else round(rng.choice([1.0, 1.2, 1.5, 2.0, 2.2, 2.5]), 1)
                )
                car_type = rng.choice(CAR_TYPES)
                base = {
                    "Petrol": 850_000,
                    "Diesel": 980_000,
                    "Hybrid": 1_250_000,
                    "Electric": 1_450_000,
                }[engine_type]
                premium = {
                    "Maruti Suzuki": 0.85,
                    "Hyundai": 1.0,
                    "Tata": 0.95,
                    "Mahindra": 1.05,
                    "Honda": 1.1,
                    "Toyota": 1.25,
                    "Kia": 1.05,
                    "MG": 1.15,
                    "Skoda": 1.2,
                    "Volkswagen": 1.22,
                    "Renault": 0.9,
                    "Nissan": 0.95,
                }[make]
                carlines.append(
                    Carline(
                        carline_id=carline_id,
                        carline_name=f"{make} {model}",
                        model=model,
                        make=make,
                        car_type=car_type,
                        engine_capacity=capacity,
                        engine_type=engine_type,
                        base_price=round(base * premium * rng.uniform(0.9, 1.15), 2),
                    )
                )
                carline_id += 1
            if len(carlines) >= CARLINE_COUNT:
                break

    colours = tuple(
        Colour(
            colour_id=i + 1,
            colour_name=COLOUR_NAMES[i],
            rcg_combination=f"R{i + 1:02d}-C{(i * 3) % 12 + 1:02d}-G{(i * 5) % 8 + 1}",
            patent_number=None if i % 5 == 0 else f"IN-PAT-{10_000 + i}",
        )
        for i in range(COLOUR_COUNT)
    )

    salesmen = tuple(
        Salesman(
            sales_person_id=i + 1,
            first_name=FIRST_NAMES[i % len(FIRST_NAMES)],
            last_name=LAST_NAMES[i % len(LAST_NAMES)],
            email=f"sp{i + 1:04d}@nql-dealers.example",
            corp_id=f"CORP{i + 1:05d}",
            active=i % 17 != 0,
        )
        for i in range(SALESMAN_COUNT)
    )

    if len(REGION_SEED) < REGION_COUNT:
        raise RuntimeError("REGION_SEED must cover REGION_COUNT entries")
    regions = tuple(
        Region(
            region_id=i + 1,
            region_name=REGION_SEED[i][0],
            city=REGION_SEED[i][1],
            state_code=REGION_SEED[i][2],
        )
        for i in range(REGION_COUNT)
    )

    dealers: list[Dealer] = []
    for i in range(DEALER_COUNT):
        region = regions[i % len(regions)]
        grade = _weighted_choice(rng, ("A", "B", "C"), (0.25, 0.45, 0.30))
        dealers.append(
            Dealer(
                dealer_id=i + 1,
                dealer_code=f"DLR{i + 1:04d}",
                dealer_name=f"{region.city} Motors {i % 7 + 1}",
                region_id=region.region_id,
                city=region.city,
                dealer_grade=grade,
                active=i % 23 != 0,
            )
        )

    makes = sorted({row.make for row in carlines})
    targets: list[Target] = []
    target_id = 1
    month = TARGET_START
    while month <= TARGET_END:
        for make in makes:
            units = rng.randint(800, 4_500)
            asp = rng.uniform(900_000, 1_800_000)
            targets.append(
                Target(
                    target_id=target_id,
                    year_month=month,
                    make=make,
                    target_units=units,
                    target_revenue=round(units * asp, 2),
                )
            )
            target_id += 1
        if month.month == 12:
            month = date(month.year + 1, 1, 1)
        else:
            month = date(month.year, month.month + 1, 1)

    return DimensionBundle(
        carlines=tuple(carlines),
        colours=colours,
        salesmen=salesmen,
        regions=regions,
        dealers=tuple(dealers),
        targets=tuple(targets),
    )


def _pick_sales_date(rng: Random) -> date:
    years = list(YEAR_WEIGHTS.keys())
    weights = [YEAR_WEIGHTS[year] for year in years]
    year = _weighted_choice(rng, years, weights)
    if year == SALES_END.year:
        start = date(year, 1, 1)
        end = SALES_END
    else:
        start = date(year, 1, 1)
        end = date(year, 12, 31)
    span = (end - start).days
    return start + timedelta(days=rng.randint(0, span))


def _ev_probability(year: int) -> float:
    # Rising EV share across the fixture window.
    return {
        2019: 0.04,
        2020: 0.05,
        2021: 0.08,
        2022: 0.12,
        2023: 0.16,
        2024: 0.22,
        2025: 0.28,
        2026: 0.34,
    }[year]


def iter_fact_sales(
    dims: DimensionBundle,
    *,
    row_count: int = DEFAULT_FACT_ROWS,
    rng_seed: int = RNG_SEED,
) -> Iterator[tuple[int, int, int, int, int, int, date, int, float]]:
    """Yield fact_sales tuples without ``total_sales`` (generated column).

    Column order:
    order_id, carline_id, colour_id, sales_person_id, region_id, dealer_id,
    sales_date, order_qty, price_per_unit
    """
    if row_count < 1:
        raise ValueError("row_count must be >= 1")

    rng = Random(rng_seed + 7)
    active_dealers = [d for d in dims.dealers if d.active] or list(dims.dealers)
    active_salesmen = [s for s in dims.salesmen if s.active] or list(dims.salesmen)
    ev_carlines = [c for c in dims.carlines if c.engine_type == "Electric"]
    ice_carlines = [c for c in dims.carlines if c.engine_type != "Electric"]
    # Dealer popularity is skewed so plans see non-uniform cardinality.
    dealer_weights = [
        {"A": 3.0, "B": 2.0, "C": 1.0}[dealer.dealer_grade] for dealer in active_dealers
    ]

    for order_id in range(1, row_count + 1):
        sales_date = _pick_sales_date(rng)
        want_ev = rng.random() < _ev_probability(sales_date.year)
        pool = ev_carlines if want_ev and ev_carlines else ice_carlines or dims.carlines
        carline = rng.choice(pool)
        colour = rng.choice(dims.colours)
        salesman = rng.choice(active_salesmen)
        dealer = _weighted_choice(rng, active_dealers, dealer_weights)
        qty = 1 if rng.random() < 0.92 else rng.randint(2, 4)
        price = round(carline.base_price * rng.uniform(0.92, 1.08), 2)
        yield (
            order_id,
            carline.carline_id,
            colour.colour_id,
            salesman.sales_person_id,
            dealer.region_id,
            dealer.dealer_id,
            sales_date,
            qty,
            price,
        )
