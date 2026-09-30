"""Generate the release benchmark (``nlq_release.yaml``).

Parameterised coverage over the seed vocabulary plus hand-written complex,
spelling/alias and multi-turn follow-up cases. The release gate is 95% per
industry (``tests/test_nlq_release_gate.py``).

Usage (from apps/api):
    python tests/benchmark/build_release_suite.py
"""

from __future__ import annotations

from itertools import cycle, islice
from pathlib import Path
from typing import Any

import yaml

OUT = Path(__file__).with_name("nlq_release.yaml")

MAKES = ["Honda", "Hyundai", "Kia", "MG", "Mahindra", "Maruti Suzuki", "Nissan", "Renault",
         "Skoda", "Tata", "Toyota", "Volkswagen"]
MAKE_SAY = {"Maruti Suzuki": "Maruti", "MG": "MG"}
MODELS = ["Creta", "Seltos", "Nexon", "Swift", "Baleno", "Hector", "Thar", "City", "Fortuner",
          "Brezza", "Venue", "Punch"]
CAR_TYPES = ["SUV", "Sedan", "Hatchback", "MUV"]
FUELS = {"Petrol": "petrol", "Diesel": "diesel", "Electric": "electric", "Hybrid": "hybrid"}
COLOURS = ["Pearl White", "Midnight Black", "Fire Red", "Ocean Blue", "Arctic Silver",
           "Graphite Grey"]
CITIES = ["Mumbai", "Pune", "Chennai", "Hyderabad", "Kolkata", "Jaipur", "Ahmedabad", "Kochi",
          "Lucknow", "Nagpur"]
STATES = {"Maharashtra": "MH", "Karnataka": "KA", "Tamil Nadu": "TN", "Gujarat": "GJ",
          "Rajasthan": "RJ", "Kerala": "KL", "Telangana": "TS", "West Bengal": "WB"}
AUTO_METRICS = {"revenue": "revenue", "units": "units sold", "orders": "orders",
                "asp": "average selling price"}
AUTO_DIMS = {"make": "brands", "model": "models", "city": "cities", "dealer": "dealers",
             "state": "states", "colour": "colours", "salesperson": "salespeople"}

LOBS = ["Motor", "Health", "Property", "Travel", "Commercial", "Liability"]
PRODUCTS = ["Motor Comprehensive", "Motor Third Party", "Health Individual",
            "Health Family Floater", "Home Premium", "Travel International", "SME Fire",
            "Cyber Liability"]
CHANNELS = ["Agency", "Bancassurance", "Broker", "Digital", "Direct"]
INS_STATES = ["Maharashtra", "Karnataka", "Tamil Nadu", "Gujarat", "Kerala", "Delhi",
              "Uttar Pradesh", "West Bengal"]
INS_REGIONS = ["Mumbai Metro", "Bengaluru Metro", "Chennai Metro", "Pune Belt"]
# "Liability" is omitted: it is also a line of business, so the question is ambiguous.
CLAIM_TYPES = ["Accident", "Illness", "Theft", "Property Damage"]
CLAIM_STATUSES = ["Open", "Settled", "Approved", "Repudiated"]
TIERS = ["Basic", "Standard", "Gold", "Platinum"]
POLICY_METRICS = {"gwp": "written premium", "earned": "earned premium"}
CLAIM_METRICS = {"incurred": "claims incurred", "paid": "claims paid",
                 "claim_count": "number of claims"}
RATIO_METRICS = {"loss_ratio": "loss ratio", "severity": "average claim severity",
                 "frequency": "claim frequency"}
INS_METRICS = {**POLICY_METRICS, **CLAIM_METRICS, **RATIO_METRICS}
INS_DIMS = {"product": "products", "lob": "lines of business", "channel": "channels",
            "region": "regions", "state": "states", "agent": "agents"}

QUARTERS = {1: ("01-01", "04-01"), 2: ("04-01", "07-01"), 3: ("07-01", "10-01"),
            4: ("10-01", "01-01")}
MONTHS = [("January", 1), ("March", 3), ("June", 6), ("August", 8), ("October", 10),
          ("December", 12)]


CATEGORY_CODE = {
    "aggregation": "AGG", "trend": "TRD", "ranking": "RNK", "comparison": "CMP",
    "time_intelligence": "TIM", "geography": "GEO", "vehicle_attributes": "VEH",
    "insurance_metrics": "INS", "complex_analytics": "CPX", "spelling": "SPL",
    "followup": "FUP", "clarification": "CLR",
}


def say(make: str) -> str:
    return MAKE_SAY.get(make, make)


def take(items: Any, n: int) -> list[Any]:
    return list(islice(cycle(items), n))


def quarter_period(q: int, year: int) -> list[str]:
    start, end = QUARTERS[q]
    return [f"{year}-{start}", f"{year + 1 if q == 4 else year}-{end}"]


def month_period(month: int, year: int) -> list[str]:
    end = f"{year + 1}-01-01" if month == 12 else f"{year}-{month + 1:02d}-01"
    return [f"{year}-{month:02d}-01", end]


class Suite:
    def __init__(self) -> None:
        self.cases: list[dict[str, Any]] = []
        self._seen: set[tuple[str, str, str]] = set()
        self._counters: dict[str, int] = {}

    def add(self, industry: str, category: str, question: str, **expect: Any) -> None:
        key = (industry, str(expect.get("prior")), question.lower())
        if key in self._seen:
            return
        self._seen.add(key)
        prefix = f"{industry[0].upper()}-{CATEGORY_CODE[category]}"
        self._counters[prefix] = self._counters.get(prefix, 0) + 1
        case = {"id": f"{prefix}-{self._counters[prefix]:02d}", "industry": industry,
                "category": category, "question": question}
        case.update({k: v for k, v in expect.items() if v is not None})
        self.cases.append(case)


def automotive(s: Suite) -> None:
    a = "automotive"

    # Aggregation
    for make, (metric, phrase) in zip(MAKES, take(AUTO_METRICS.items(), 12), strict=True):
        s.add(a, "aggregation", f"Total {phrase} for {say(make)}", metric=metric,
              filters={"make": [make]})
    for year in (2024, 2025):
        for metric, phrase in AUTO_METRICS.items():
            s.add(a, "aggregation", f"What was the {phrase} in {year}?", metric=metric, year=year)
    for car_type, metric in zip(CAR_TYPES, take(["revenue", "units"], 4), strict=True):
        phrase = AUTO_METRICS[metric]
        s.add(a, "aggregation", f"Total {phrase} of {car_type} cars", metric=metric,
              filters={"car_type": [car_type]})
    s.add(a, "aggregation", "How many cars did Tata sell?", metric="units",
          filters={"make": ["Tata"]})
    s.add(a, "aggregation", "How many cars were sold in total?", metric="units")

    # Trend
    for make in MAKES[:10]:
        s.add(a, "trend", f"{say(make)} revenue by month", metric="revenue",
              filters={"make": [make]}, group=["month"])
    for car_type in CAR_TYPES:
        s.add(a, "trend", f"Units sold trend by year for {car_type}s", metric="units",
              filters={"car_type": [car_type]}, group=["year"])
    for make in ("Hyundai", "Tata", "Kia", "Toyota"):
        s.add(a, "trend", f"Quarterly revenue for {say(make)} in 2025", metric="revenue",
              filters={"make": [make]}, group=["quarter"], year=2025)
    for metric in ("orders", "units", "asp"):
        s.add(a, "trend", f"Monthly {AUTO_METRICS[metric]} trend", metric=metric, group=["month"])
    s.add(a, "trend", "Yearly units sold", metric="units", group=["year"])
    s.add(a, "trend", "Revenue trend by month for electric cars", metric="revenue",
          filters={"engine_type": ["Electric"]}, group=["month"])

    # Ranking
    for n, (dim, noun) in zip(take([3, 5, 10], 7), AUTO_DIMS.items(), strict=True):
        for metric in ("revenue", "units"):
            s.add(a, "ranking", f"Top {n} {noun} by {AUTO_METRICS[metric]}", metric=metric,
                  group=[dim], order="desc", limit=n)
    for dim, noun in (("model", "models"), ("city", "cities"), ("make", "brands"),
                      ("dealer", "dealers")):
        s.add(a, "ranking", f"Bottom 5 {noun} by revenue", metric="revenue", group=[dim],
              order="asc", limit=5)
    for dim, noun in (("city", "city"), ("make", "brand"), ("model", "model"),
                      ("dealer", "dealer")):
        s.add(a, "ranking", f"Which {noun} has the highest units sold?", metric="units",
              group=[dim], order="desc")
    for state, code in list(STATES.items())[:4]:
        s.add(a, "ranking", f"Best selling model in {state}", metric="units", group=["model"],
              filters={"state_code": [code]}, order="desc")

    # Comparison
    pairs = [("MG", "Tata"), ("Hyundai", "Kia"), ("Honda", "Toyota"), ("Maruti Suzuki", "Hyundai"),
             ("Mahindra", "Tata"), ("Skoda", "Volkswagen")]
    for (m1, m2), metric in zip(pairs, take(["revenue", "units"], 6), strict=True):
        s.add(a, "comparison", f"Compare {say(m1)} and {say(m2)} {AUTO_METRICS[metric]}",
              metric=metric, filters={"make": [m1, m2]}, group=["make"])
        s.add(a, "comparison", f"{say(m1)} vs {say(m2)} revenue by year", metric="revenue",
              filters={"make": [m1, m2]}, group=["year"])
    for c1, c2 in (("Pune", "Chennai"), ("Hyderabad", "Kolkata"), ("Jaipur", "Lucknow")):
        s.add(a, "comparison", f"Compare {c1} and {c2} units sold", metric="units",
              filters={"city": [c1, c2]}, group=["city"])
    for f1, f2 in (("Petrol", "Electric"), ("Diesel", "Hybrid")):
        s.add(a, "comparison", f"Compare {f1.lower()} vs {f2.lower()} units sold",
              metric="units", filters={"engine_type": [f1, f2]}, group=["engine_type"])
    s.add(a, "comparison", "Compare SUV vs Sedan revenue", metric="revenue",
          filters={"car_type": ["SUV", "Sedan"]}, group=["car_type"])

    # Time intelligence
    for q, year in ((1, 2024), (2, 2024), (4, 2024), (2, 2025), (3, 2025)):
        s.add(a, "time_intelligence", f"Revenue in Q{q} {year}", metric="revenue",
              period=quarter_period(q, year))
    for (name, month), year in zip(MONTHS, take([2024, 2025], 6), strict=True):
        s.add(a, "time_intelligence", f"Units sold in {name} {year}", metric="units",
              period=month_period(month, year))
    s.add(a, "time_intelligence", "Revenue for FY2024", metric="revenue",
          period=["2023-04-01", "2024-04-01"])
    s.add(a, "time_intelligence", "Units sold in FY 2023-24", metric="units",
          period=["2023-04-01", "2024-04-01"])
    s.add(a, "time_intelligence", "Revenue in H2 2024", metric="revenue",
          period=["2024-07-01", "2025-01-01"])
    for make in ("MG", "Kia", "Tata"):
        s.add(a, "time_intelligence", f"Year over year revenue growth for {say(make)}",
              metric="revenue", filters={"make": [make]}, group=["year"], must=["lag\\("])
    s.add(a, "time_intelligence", "Month over month units growth", metric="units",
          group=["month"], must=["lag\\("])
    s.add(a, "time_intelligence", "Running total of revenue in 2024", metric="revenue",
          year=2024, must=["sum\\(.*\\) over"])
    s.add(a, "time_intelligence", "Cumulative units sold for Hyundai in 2025", metric="units",
          filters={"make": ["Hyundai"]}, year=2025, must=["sum\\(.*\\) over"])
    s.add(a, "time_intelligence", "3 month moving average of units sold", metric="units",
          group=["month"], must=["avg\\(.*\\) over", "2 preceding"])
    s.add(a, "time_intelligence", "Units sold last month", metric="units",
          must=["date_trunc\\('month'", "(max\\(|current_date)"])
    s.add(a, "time_intelligence", "Revenue in the last 3 months", metric="revenue",
          must=["(max\\(|current_date)", "interval '(2|3) months'"])

    # Geography
    for city, metric in zip(CITIES, take(["revenue", "units"], 10), strict=True):
        s.add(a, "geography", f"{AUTO_METRICS[metric].capitalize()} in {city}", metric=metric,
              filters={"city": [city]})
    for state, code in STATES.items():
        s.add(a, "geography", f"Revenue in {state}", metric="revenue",
              filters={"state_code": [code]})
    for make in ("MG", "Hyundai", "Tata", "Kia"):
        s.add(a, "geography", f"{say(make)} units sold by city", metric="units",
              filters={"make": [make]}, group=["city"])
    for state, code in list(STATES.items())[:3]:
        s.add(a, "geography", f"SUV sales in {state}", metric="revenue",
              filters={"car_type": ["SUV"], "state_code": [code]})
    s.add(a, "geography", "Units sold by region", metric="units", group=["region"])
    s.add(a, "geography", "SUV sales by state", metric="revenue",
          filters={"car_type": ["SUV"]}, group=["state"])

    # Vehicle attributes
    for colour, metric in zip(COLOURS, take(["revenue", "units"], 6), strict=True):
        s.add(a, "vehicle_attributes", f"{AUTO_METRICS[metric].capitalize()} of {colour} cars",
              metric=metric, filters={"colour_name": [colour]})
    for fuel, word in FUELS.items():
        s.add(a, "vehicle_attributes", f"How many {word} cars were sold?", metric="units",
              filters={"engine_type": [fuel]})
        s.add(a, "vehicle_attributes", f"{word.capitalize()} car revenue by year",
              metric="revenue", filters={"engine_type": [fuel]}, group=["year"])
    for model in MODELS[:7]:
        s.add(a, "vehicle_attributes", f"{model} units sold by month", metric="units",
              filters={"model": [model]}, group=["month"])
    s.add(a, "vehicle_attributes", "Honda City units sold by month", metric="units",
          filters={"model": ["City"]}, group=["month"])
    s.add(a, "vehicle_attributes", "Tata Punch revenue by year", metric="revenue",
          filters={"model": ["Punch"]}, group=["year"])
    for car_type in ("SUV", "Sedan", "Hatchback"):
        s.add(a, "vehicle_attributes", f"Top selling colour for {car_type}s", metric="units",
              filters={"car_type": [car_type]}, group=["colour"], order="desc")
    s.add(a, "vehicle_attributes", "Units sold by body type", metric="units", group=["car_type"])
    s.add(a, "vehicle_attributes", "Average selling price by fuel type", metric="asp",
          group=["engine_type"])
    s.add(a, "vehicle_attributes", "Electric SUV units sold", metric="units",
          filters={"engine_type": ["Electric"], "car_type": ["SUV"]})

    # Complex analytics
    top_per_make = {
        "must": ["partition by @make\\b", "<= 3"],
        "must_not": ["partition by @model\\b"],
    }
    s.add(a, "complex_analytics", "Top 3 models per make", metric="units", group=["make", "model"],
          **top_per_make)
    s.add(a, "complex_analytics", "Top 3 models per brand by units sold", metric="units",
          group=["make", "model"], **top_per_make)
    s.add(a, "complex_analytics", "Best 3 models for each make by revenue", metric="revenue",
          group=["make", "model"], **top_per_make)
    s.add(a, "complex_analytics", "Top 2 cities per state by revenue", metric="revenue",
          group=["state", "city"], must=["partition by @state_(code|name)\\b", "<= 2"])
    s.add(a, "complex_analytics", "Compare SUV vs Sedan growth over the last 3 years",
          filters={"car_type": ["SUV", "Sedan"]}, group=["car_type", "year"],
          must=["lag\\(", "partition by @car_type\\b"])
    s.add(a, "complex_analytics", "Running total sales", metric="revenue",
          must=["sum\\(.*\\) over"])
    s.add(a, "complex_analytics", "Running total of units sold by month", metric="units",
          group=["month"], must=["sum\\(.*\\) over"])
    s.add(a, "complex_analytics", "6 month moving average of revenue", metric="revenue",
          group=["month"], must=["avg\\(.*\\) over", "5 preceding"])
    s.add(a, "complex_analytics", "Which dealers are growing fastest", metric="revenue",
          group=["dealer"], order="desc", must=["current_", "previous_", "change_pct"])
    s.add(a, "complex_analytics", "Fastest growing brands by units sold", metric="units",
          group=["make"], order="desc", must=["change_pct"])
    s.add(a, "complex_analytics", "Which models are declining the most in revenue",
          metric="revenue", group=["model"], order="asc", must=["change_pct"])
    s.add(a, "complex_analytics", "Dealers with increasing revenue but decreasing units",
          group=["dealer"], must=["total_sales", "order_qty", "change_pct"])
    s.add(a, "complex_analytics", "Revenue share by brand", metric="revenue", group=["make"],
          must=["over\\s*\\("])
    s.add(a, "complex_analytics", "Compare MG SUV sales by year in Maharashtra",
          metric="revenue", filters={"make": ["MG"], "car_type": ["SUV"], "state_code": ["MH"]},
          group=["year"])
    s.add(a, "complex_analytics", "Year over year growth of SUV revenue in Karnataka",
          metric="revenue", filters={"car_type": ["SUV"], "state_code": ["KA"]}, group=["year"],
          must=["lag\\("])

    # Spelling and aliases
    spelled = [
        ("marutii sales by year", "revenue", {"make": ["Maruti Suzuki"]}, ["year"]),
        ("maruthi revenue by month", "revenue", {"make": ["Maruti Suzuki"]}, ["month"]),
        ("suzki units sold", "units", {"make": ["Maruti Suzuki"]}, None),
        ("hyundia sales trend", "revenue", {"make": ["Hyundai"]}, ["month"]),
        ("mahindraa revenue by year", "revenue", {"make": ["Mahindra"]}, ["year"]),
        ("revenue in mumabi", "revenue", {"city": ["Mumbai"]}, None),
        ("SUV sales in maharastra", "revenue", {"car_type": ["SUV"], "state_code": ["MH"]}, None),
        ("MG revnue by year", "revenue", {"make": ["MG"]}, ["year"]),
        ("tata salse by month", "revenue", {"make": ["Tata"]}, ["month"]),
        ("MSIL units sold by year", "units", {"make": ["Maruti Suzuki"]}, ["year"]),
        ("MG Motors revenue by month", "revenue", {"make": ["MG"]}, ["month"]),
        ("Morris Garages sales by year", "revenue", {"make": ["MG"]}, ["year"]),
        ("Suzuki units sold in 2024", "units", {"make": ["Maruti Suzuki"]}, None),
        ("Top 5 brands by revnue", "revenue", None, ["make"]),
        ("toyta units by month", "units", {"make": ["Toyota"]}, ["month"]),
    ]
    for question, metric, filters, group in spelled:
        s.add(a, "spelling", question, metric=metric, filters=filters, group=group,
              year=2024 if "2024" in question else None)

    # Follow-up chains
    chain = ["MG sales by year"]
    for step, expect in (
        ("Only SUVs", {"filters": {"make": ["MG"], "car_type": ["SUV"]}, "metric": "revenue"}),
        ("Only Maharashtra", {"filters": {"make": ["MG"], "car_type": ["SUV"],
                                          "state_code": ["MH"]}, "metric": "revenue"}),
        ("Show units instead", {"filters": {"make": ["MG"], "car_type": ["SUV"],
                                            "state_code": ["MH"]}, "metric": "units"}),
    ):
        s.add(a, "followup", step, prior=list(chain), group=["year"], **expect)
        chain.append(step)
    ranking = ["Top 5 brands by revenue"]
    for step, expect in (
        ("for 2024", {"year": 2024, "order": "desc", "limit": 5}),
        ("bottom 5 instead", {"year": 2024, "order": "asc", "limit": 5}),
        ("in Q1", {"period": ["2024-01-01", "2024-04-01"], "limit": 5}),
    ):
        s.add(a, "followup", step, prior=list(ranking), metric="revenue", group=["make"],
              **expect)
        ranking.append(step)
    for prior, question, expect in (
        ("Hyundai revenue by month", "What about Kia?",
         {"metric": "revenue", "filters": {"make": ["Kia"]}, "group": ["month"],
          "must_not": ["'hyundai'"]}),
        ("Revenue by city", "Only for SUVs",
         {"metric": "revenue", "filters": {"car_type": ["SUV"]}, "group": ["city"]}),
        ("Units sold by model", "Only electric",
         {"metric": "units", "filters": {"engine_type": ["Electric"]}, "group": ["model"]}),
        ("Tata sales by year", "Break it down by month",
         {"metric": "revenue", "filters": {"make": ["Tata"]}, "group": ["month"]}),
        ("Compare Hyundai and Kia sales", "Add Tata",
         {"metric": "revenue", "filters": {"make": ["Hyundai", "Kia", "Tata"]},
          "group": ["make"]}),
        ("Top 10 models by units sold", "Only in 2025",
         {"metric": "units", "group": ["model"], "year": 2025, "limit": 10}),
        ("Revenue by region", "Show orders instead",
         {"metric": "orders", "group": ["region"]}),
        ("Kia revenue by year", "Only in Pune",
         {"metric": "revenue", "filters": {"make": ["Kia"], "city": ["Pune"]},
          "group": ["year"]}),
        ("SUV sales by state", "Only diesel",
         {"metric": "revenue", "filters": {"car_type": ["SUV"], "engine_type": ["Diesel"]},
          "group": ["state"]}),
        ("MG sales by year", "Top 5 models by revenue",
         {"metric": "revenue", "group": ["model"], "limit": 5}),
    ):
        s.add(a, "followup", question, prior=[prior], **expect)

    # Clarification
    for question in ("Show sales", "Profit by brand", "CNG car sales", "Ferari sales",
                     "Sales trend", "Show me the numbers"):
        s.add(a, "clarification", question, outcome="clarify")


def insurance(s: Suite) -> None:
    i = "insurance"

    # Aggregation
    for metric, phrase in INS_METRICS.items():
        s.add(i, "aggregation", f"Total {phrase}", metric=metric)
    for lob, (metric, phrase) in zip(LOBS, take(INS_METRICS.items(), 6), strict=True):
        s.add(i, "aggregation", f"{phrase.capitalize()} for {lob} line of business",
              metric=metric, filters={"line_of_business": [lob]})
    for year in (2024, 2025):
        for metric in ("gwp", "earned", "incurred", "paid", "claim_count"):
            s.add(i, "aggregation", f"What was the {INS_METRICS[metric]} in {year}?",
                  metric=metric, year=year)
    for product, metric in zip(PRODUCTS, take(["gwp", "incurred", "claim_count"], 8),
                               strict=True):
        s.add(i, "aggregation", f"{INS_METRICS[metric].capitalize()} for {product}",
              metric=metric, filters={"product_name": [product]})

    # Trend
    for metric, phrase in INS_METRICS.items():
        s.add(i, "trend", f"{phrase.capitalize()} trend by month", metric=metric,
              group=["month"])
    for metric in ("gwp", "incurred", "claim_count", "loss_ratio"):
        s.add(i, "trend", f"{INS_METRICS[metric].capitalize()} by year", metric=metric,
              group=["year"])
    for lob in LOBS[:5]:
        s.add(i, "trend", f"{lob} written premium by month", metric="gwp",
              filters={"line_of_business": [lob]}, group=["month"])
    for product in PRODUCTS[:4]:
        s.add(i, "trend", f"{product} claims incurred by year", metric="incurred",
              filters={"product_name": [product]}, group=["year"])
    s.add(i, "trend", "Quarterly written premium for 2025", metric="gwp", group=["quarter"],
          year=2025)
    s.add(i, "trend", "Quarterly claims paid in 2024", metric="paid", group=["quarter"],
          year=2024)

    # Ranking
    for n, (dim, noun) in zip(take([3, 5, 10], 6), INS_DIMS.items(), strict=True):
        for metric in ("gwp", "incurred", "claim_count"):
            s.add(i, "ranking", f"Top {n} {noun} by {INS_METRICS[metric]}", metric=metric,
                  group=[dim], order="desc", limit=n)
    for dim, noun in (("product", "product"), ("channel", "channel"), ("region", "region"),
                      ("state", "state"), ("lob", "line of business")):
        s.add(i, "ranking", f"Which {noun} has the highest loss ratio?", metric="loss_ratio",
              group=[dim], order="desc")
    for dim, noun in (("product", "products"), ("agent", "agents"), ("region", "regions")):
        s.add(i, "ranking", f"Bottom 5 {noun} by written premium", metric="gwp", group=[dim],
              order="asc", limit=5)
    s.add(i, "ranking", "Lowest earned premium channel", metric="earned", group=["channel"],
          order="asc")

    # Comparison
    for l1, l2 in (("Motor", "Health"), ("Property", "Travel"), ("Motor", "Property"),
                   ("Health", "Travel")):
        for metric in ("gwp", "incurred", "loss_ratio"):
            s.add(i, "comparison",
                  f"Compare {INS_METRICS[metric]} of {l1} and {l2}", metric=metric,
                  filters={"line_of_business": [l1, l2]}, group=["lob"])
    for c1, c2 in (("Agency", "Broker"), ("Digital", "Direct"), ("Bancassurance", "Agency")):
        s.add(i, "comparison", f"{c1} vs {c2} written premium", metric="gwp",
              filters={"channel_name": [c1, c2]}, group=["channel"])
    for p1, p2 in (("Motor Comprehensive", "Motor Third Party"),
                   ("Health Individual", "Health Family Floater")):
        s.add(i, "comparison", f"Compare claims incurred for {p1} and {p2}", metric="incurred",
              filters={"product_name": [p1, p2]}, group=["product"])
    s.add(i, "comparison", "Compare written premium in 2024 and 2025", metric="gwp",
          group=["year"], must=["2024", "2025"])
    for s1, s2 in (("Maharashtra", "Karnataka"), ("Tamil Nadu", "Kerala")):
        s.add(i, "comparison", f"Compare claims count in {s1} and {s2}", metric="claim_count",
              filters={"state_name": [s1, s2]}, group=["state"])

    # Time intelligence
    for q, year in ((1, 2024), (3, 2024), (1, 2025), (2, 2025)):
        s.add(i, "time_intelligence", f"Written premium in Q{q} {year}", metric="gwp",
              period=quarter_period(q, year))
        s.add(i, "time_intelligence", f"Claims incurred in Q{q} {year}", metric="incurred",
              period=quarter_period(q, year))
    for (name, month), year in zip(MONTHS[:4], take([2024, 2025], 4), strict=True):
        s.add(i, "time_intelligence", f"Number of claims in {name} {year}",
              metric="claim_count", period=month_period(month, year))
    s.add(i, "time_intelligence", "Written premium for FY2025", metric="gwp",
          period=["2024-04-01", "2025-04-01"])
    s.add(i, "time_intelligence", "Claims paid in FY 2023-24", metric="paid",
          period=["2023-04-01", "2024-04-01"])
    s.add(i, "time_intelligence", "Earned premium in H1 2025", metric="earned",
          period=["2025-01-01", "2025-07-01"])
    s.add(i, "time_intelligence", "Year over year written premium growth", metric="gwp",
          group=["year"], must=["lag\\("])
    s.add(i, "time_intelligence", "Month over month claims incurred growth", metric="incurred",
          group=["month"], must=["lag\\("])
    s.add(i, "time_intelligence", "Running total of written premium in 2025", metric="gwp",
          year=2025, must=["sum\\(.*\\) over"])
    s.add(i, "time_intelligence", "3 month moving average of claims paid", metric="paid",
          group=["month"], must=["avg\\(.*\\) over", "2 preceding"])
    s.add(i, "time_intelligence", "Written premium last month", metric="gwp",
          must=["date_trunc\\('month'", "(max\\(|current_date)"])
    s.add(i, "time_intelligence", "Claims incurred in the last 6 months", metric="incurred",
          must=["(max\\(|current_date)", "interval '(5|6) months'"])

    # Geography
    for state, metric in zip(INS_STATES, take(["gwp", "incurred", "claim_count"], 8),
                             strict=True):
        s.add(i, "geography", f"{INS_METRICS[metric].capitalize()} in {state}", metric=metric,
              filters={"state_name": [state]})
    for metric in ("gwp", "incurred", "paid", "loss_ratio"):
        s.add(i, "geography", f"{INS_METRICS[metric].capitalize()} by region", metric=metric,
              group=["region"])
        s.add(i, "geography", f"{INS_METRICS[metric].capitalize()} by state", metric=metric,
              group=["state"])
    for region in INS_REGIONS:
        s.add(i, "geography", f"Written premium in {region} region", metric="gwp",
              filters={"region_name": [region]})
    for lob in ("Motor", "Health"):
        s.add(i, "geography", f"{lob} claims by state", metric="claim_count",
              filters={"line_of_business": [lob]}, group=["state"])

    # Insurance metrics
    for claim_type in CLAIM_TYPES:
        s.add(i, "insurance_metrics", f"{claim_type} claims incurred", metric="incurred",
              filters={"claim_type": [claim_type]})
    for status in CLAIM_STATUSES:
        s.add(i, "insurance_metrics", f"How many claims are {status.lower()}?",
              metric="claim_count", filters={"claim_status": [status]})
    for dim, noun in (("product", "product"), ("lob", "line of business"),
                      ("channel", "channel"), ("region", "region")):
        s.add(i, "insurance_metrics", f"Average claim severity by {noun}", metric="severity",
              group=[dim])
        s.add(i, "insurance_metrics", f"Claim frequency by {noun}", metric="frequency",
              group=[dim])
    for dim, noun in (("product", "product"), ("region", "region"), ("lob", "line of business")):
        s.add(i, "insurance_metrics", f"Claim approval rate by {noun}", metric="approval_rate",
              group=[dim])
        s.add(i, "insurance_metrics", f"Renewal rate by {noun}", metric="renewal_rate",
              group=[dim])
    for tier in TIERS:
        s.add(i, "insurance_metrics", f"Written premium for {tier} tier", metric="gwp",
              filters={"coverage_tier": [tier]})
    s.add(i, "insurance_metrics", "Claims by claim type", metric="claim_count",
          group=["claim_type"])
    s.add(i, "insurance_metrics", "Claims incurred by claim type", metric="incurred",
          group=["claim_type"])
    s.add(i, "insurance_metrics", "Loss ratio for Motor", metric="loss_ratio",
          filters={"line_of_business": ["Motor"]})
    s.add(i, "insurance_metrics", "Comprehensive policies written premium", metric="gwp",
          must=["comprehensive"])
    s.add(i, "insurance_metrics", "Third party written premium by year", metric="gwp",
          group=["year"], must=["third party"])

    # Complex analytics
    s.add(i, "complex_analytics", "Top 3 products per line of business by written premium",
          metric="gwp", group=["lob", "product"],
          must=["partition by @line_of_business\\b", "<= 3"])
    s.add(i, "complex_analytics", "Top 2 agents per channel by written premium", metric="gwp",
          group=["channel", "agent"], must=["partition by @channel_name\\b", "<= 2"])
    s.add(i, "complex_analytics", "Which products are growing fastest in written premium",
          metric="gwp", group=["product"], order="desc", must=["change_pct"])
    s.add(i, "complex_analytics", "Fastest growing channels by written premium", metric="gwp",
          group=["channel"], order="desc", must=["change_pct"])
    s.add(i, "complex_analytics", "Which regions have declining claims incurred",
          metric="incurred", group=["region"], order="asc", must=["change_pct"])
    s.add(i, "complex_analytics", "Running total of claims paid", metric="paid",
          must=["sum\\(.*\\) over"])
    s.add(i, "complex_analytics", "6 month moving average of written premium", metric="gwp",
          group=["month"], must=["avg\\(.*\\) over", "5 preceding"])
    s.add(i, "complex_analytics", "Written premium share by channel", metric="gwp",
          group=["channel"], must=["over\\s*\\("])
    s.add(i, "complex_analytics", "Compare Motor vs Health claims growth over the last 3 years",
          filters={"line_of_business": ["Motor", "Health"]}, group=["lob", "year"],
          must=["lag\\("])
    s.add(i, "complex_analytics", "Year over year loss ratio for Motor", metric="loss_ratio",
          filters={"line_of_business": ["Motor"]}, group=["year"], must=["lag\\("])
    s.add(i, "complex_analytics", "Motor written premium by year in Maharashtra", metric="gwp",
          filters={"line_of_business": ["Motor"], "state_name": ["Maharashtra"]}, group=["year"])

    # Spelling and aliases
    for question, metric, filters, group in (
        ("lose ratio by product", "loss_ratio", None, ["product"]),
        ("loose ratio trend", "loss_ratio", None, ["month"]),
        ("writen premium by month", "gwp", None, ["month"]),
        ("premuim by channel", "gwp", None, ["channel"]),
        ("claims incured by region", "incurred", None, ["region"]),
        ("claims in maharastra", "claim_count", {"state_name": ["Maharashtra"]}, None),
        ("GWP by line of business", "gwp", None, ["lob"]),
        ("gross written premium for helth", "gwp", {"line_of_business": ["Health"]}, None),
        ("motr claims incurred", "incurred", {"line_of_business": ["Motor"]}, None),
        ("top 5 agents by premum", "gwp", None, ["agent"]),
    ):
        s.add(i, "spelling", question, metric=metric, filters=filters, group=group)

    # Follow-up chains
    chain = ["Written premium by year"]
    for step, filters in (
        ("Only Motor", {"line_of_business": ["Motor"]}),
        ("Only Maharashtra", {"line_of_business": ["Motor"], "state_name": ["Maharashtra"]}),
    ):
        s.add(i, "followup", step, prior=list(chain), metric="gwp", filters=filters,
              group=["year"])
        chain.append(step)
    s.add(i, "followup", "Show claims incurred instead", prior=list(chain), metric="incurred",
          filters={"line_of_business": ["Motor"], "state_name": ["Maharashtra"]}, group=["year"])
    for prior, question, expect in (
        ("Loss ratio by product", "Only for 2025",
         {"metric": "loss_ratio", "group": ["product"], "year": 2025}),
        ("Top 5 agents by written premium", "for 2024",
         {"metric": "gwp", "group": ["agent"], "year": 2024, "limit": 5}),
        ("Claims incurred by region", "Only Health",
         {"metric": "incurred", "group": ["region"], "filters": {"line_of_business": ["Health"]}}),
        ("Written premium by channel", "Show earned premium instead",
         {"metric": "earned", "group": ["channel"]}),
        ("Motor claims by month", "What about Health?",
         {"metric": "claim_count", "group": ["month"],
          "filters": {"line_of_business": ["Health"]}, "must_not": ["'motor'"]}),
        ("Claims paid by product", "in Q1 2025",
         {"metric": "paid", "group": ["product"], "period": ["2025-01-01", "2025-04-01"]}),
        ("Written premium by product", "Break it down by month",
         {"metric": "gwp", "group": ["month"]}),
    ):
        s.add(i, "followup", question, prior=[prior], **expect)

    # Clarification
    s.add(i, "trend", "Show claims data trend", metric="claim_count", group=["month"])
    for question in ("Show insurance numbers", "Profit by product", "Show me the data",
                     "Customer satisfaction score", "Combined ratio by product"):
        s.add(i, "clarification", question, outcome="clarify")


def build() -> list[dict[str, Any]]:
    suite = Suite()
    automotive(suite)
    insurance(suite)
    return suite.cases


def main() -> None:
    cases = build()
    header = (
        "# Release benchmark, generated by tests/benchmark/build_release_suite.py.\n"
        "# Same keys as nlq_benchmark.yaml; `prior` may be a list (multi-turn chain).\n"
        "# Do not edit by hand: change the generator and re-run it.\n"
    )
    body = yaml.safe_dump({"cases": cases}, sort_keys=False, allow_unicode=True, width=120)
    OUT.write_text(header + body, encoding="utf-8")
    counts: dict[str, int] = {}
    for case in cases:
        counts[case["industry"]] = counts.get(case["industry"], 0) + 1
    print(f"{len(cases)} cases -> {OUT.name}: {counts}")


if __name__ == "__main__":
    main()
