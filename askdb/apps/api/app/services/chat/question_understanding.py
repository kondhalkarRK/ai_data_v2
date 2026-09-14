"""Deterministic NLQ question understanding — entity, metric, filters.

Mirrors Streamlit intent/glossary behaviour without large prompts: resolve
business entities and mandatory filters BEFORE template or LLM SQL generation.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Literal

from app.core.config import Industry

IntentKind = Literal[
    "ranking",
    "aggregation",
    "trend",
    "lookup",
    "ambiguous",
    "unknown",
]

EntityKind = Literal[
    "salesperson",
    "dealer",
    "vehicle",
    "region",
    "metric_only",
    "unknown",
]

MetricKind = Literal["units", "revenue", "orders", "unknown"]


@dataclass(frozen=True, slots=True)
class ExtractedFilter:
    column: str  # e.g. automotive.dim_carline.car_type
    operator: str
    value: str
    label: str


@dataclass(slots=True)
class QuestionPlan:
    industry: Industry
    intent: IntentKind
    entity: EntityKind
    metric: MetricKind
    filters: list[ExtractedFilter] = field(default_factory=list)
    limit: int = 10
    ambiguity_options: list[str] = field(default_factory=list)
    glossary_hits: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    @property
    def is_ambiguous(self) -> bool:
        return self.intent == "ambiguous" or bool(self.ambiguity_options)


_TOP = re.compile(r"\b(top|best|highest|leading|most|lowest|worst)\b", re.I)
_TREND = re.compile(r"\b(trend|by\s+month|monthly|over\s+time|time\s+series)\b", re.I)
_REVENUE = re.compile(r"\b(revenue|sales\s+value|dollar|amount|turnover)\b", re.I)
_UNITS = re.compile(r"\b(unit|units|volume|qty|quantity)\b", re.I)
_SELLING = re.compile(r"\b(selling|sold|popular)\b", re.I)

_SALESPERSON = re.compile(
    r"\b(salesperson|salespersons|salespeople|sales\s*rep|sales\s*reps|"
    r"sales\s*executive|sales\s*consultant|sales\s*advisor|salesman|salesmen|"
    r"who\s+sold)\b",
    re.I,
)
_DEALER = re.compile(
    r"\b(dealer|dealers|dealership|dealerships|showroom|showrooms|outlet|outlets)\b",
    re.I,
)
_VEHICLE = re.compile(
    r"\b(car|cars|vehicle|vehicles|model|models|automobile|automobiles|carline)\b",
    re.I,
)
_REGION = re.compile(r"\b(region|regions|geo|geography|market|city|cities)\b", re.I)

# Seeded car_type values (automotive.dim_carline.car_type).
_BODY_STYLES: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\b(sedans?|saloons?)\b", re.I), "Sedan"),
    (re.compile(r"\b(suvs?|sport\s+utility|crossovers?)\b", re.I), "SUV"),
    (re.compile(r"\b(hatchbacks?|hatch)\b", re.I), "Hatchback"),
    (re.compile(r"\b(muvs?)\b", re.I), "MUV"),
    (re.compile(r"\b(coupes?)\b", re.I), "Coupe"),
]

_EV = re.compile(r"\b(ev|evs|electric(?:\s+vehicle|\s+car)?s?|battery\s+electric|bev)\b", re.I)


def _metric_from_question(q: str) -> MetricKind:
    if _REVENUE.search(q):
        return "revenue"
    if _UNITS.search(q) or _SELLING.search(q):
        return "units"
    if re.search(r"\b(orders?|transactions?)\b", q, re.I):
        return "orders"
    return "unknown"


def _extract_body_filters(q: str) -> list[ExtractedFilter]:
    out: list[ExtractedFilter] = []
    for pattern, value in _BODY_STYLES:
        if pattern.search(q):
            out.append(
                ExtractedFilter(
                    column="automotive.dim_carline.car_type",
                    operator="=",
                    value=value,
                    label=f"Car type = {value}",
                )
            )
    if _EV.search(q):
        out.append(
            ExtractedFilter(
                column="automotive.dim_carline.engine_type",
                operator="=",
                value="Electric",
                label="Engine type = Electric",
            )
        )
    return out


def _limit_from_question(q: str) -> int:
    match = re.search(r"\btop\s+(\d{1,3})\b", q, re.I)
    if match:
        return max(1, min(int(match.group(1)), 50))
    if re.search(r"\b(the\s+)?top\b|\bbest\b|\bhighest\b", q, re.I):
        return 10
    return 20


def understand_question(industry: Industry, question: str) -> QuestionPlan:
    q = (question or "").strip()
    if not q:
        return QuestionPlan(
            industry=industry,
            intent="unknown",
            entity="unknown",
            metric="unknown",
        )

    if industry is Industry.AUTOMOTIVE:
        return _understand_automotive(q)
    if industry is Industry.INSURANCE:
        return _understand_insurance(q)
    return QuestionPlan(
        industry=industry,
        intent="unknown",
        entity="unknown",
        metric="unknown",
    )


def _understand_automotive(q: str) -> QuestionPlan:
    metric = _metric_from_question(q)
    filters = _extract_body_filters(q)
    limit = _limit_from_question(q)
    hits: list[str] = []
    notes: list[str] = []

    # Entity priority: salesperson and dealer must beat vehicle/selling heuristics.
    if _SALESPERSON.search(q):
        hits.append("Salesperson")
        if metric == "unknown":
            metric = "units"
        notes.append("Salesperson is dim_salesman (person), not dealer.")
        return QuestionPlan(
            industry=Industry.AUTOMOTIVE,
            intent="ranking" if _TOP.search(q) else "aggregation",
            entity="salesperson",
            metric=metric,
            filters=filters,
            limit=limit if _TOP.search(q) else 20,
            glossary_hits=hits,
            notes=notes,
        )

    if _DEALER.search(q):
        hits.append("Dealer")
        if metric == "unknown":
            metric = "revenue" if _REVENUE.search(q) or not _SELLING.search(q) else "units"
        notes.append("Dealer is dim_dealer (outlet), not salesperson.")
        return QuestionPlan(
            industry=Industry.AUTOMOTIVE,
            intent="ranking" if _TOP.search(q) else "aggregation",
            entity="dealer",
            metric=metric,
            filters=filters,
            limit=limit if _TOP.search(q) else 20,
            glossary_hits=hits,
            notes=notes,
        )

    if _REGION.search(q) and (_TOP.search(q) or _TREND.search(q) or True):
        if _VEHICLE.search(q) or _SELLING.search(q) or filters:
            # region + vehicle still vehicle-ranked by region handled elsewhere
            pass
        elif not _VEHICLE.search(q) and _TOP.search(q):
            hits.append("Region")
            return QuestionPlan(
                industry=Industry.AUTOMOTIVE,
                intent="ranking",
                entity="region",
                metric="units" if metric == "unknown" else metric,
                filters=filters,
                limit=limit,
                glossary_hits=hits,
            )

    # Vehicle / top selling — require body-style clarity when bare "top selling car".
    if (_VEHICLE.search(q) or _SELLING.search(q) or filters) and _TOP.search(q):
        hits.append("Vehicle")
        if metric == "unknown":
            metric = "units"
        # Ambiguous only when bare "top selling car" with no metric/region/body cue.
        bare = bool(
            re.search(
                r"(top|best)\s+selling\s+(car|cars|vehicle|vehicles|model|models)\b",
                q,
                re.I,
            )
        )
        explicit_metric = bool(_UNITS.search(q) or _REVENUE.search(q) or _REGION.search(q))
        if bare and not filters and not explicit_metric:
            return QuestionPlan(
                industry=Industry.AUTOMOTIVE,
                intent="ambiguous",
                entity="vehicle",
                metric="units",
                filters=[],
                limit=limit,
                ambiguity_options=[
                    "Top selling car by units",
                    "Top selling car by revenue",
                    "Top selling sedan by units",
                    "Top selling SUV by units",
                ],
                glossary_hits=hits,
                notes=["Body style or metric not specified; offering clarifications."],
            )
        notes_out = list(notes)
        if _REGION.search(q):
            notes_out.append("Group by region")
        return QuestionPlan(
            industry=Industry.AUTOMOTIVE,
            intent="ranking",
            entity="vehicle",
            metric=metric,
            filters=filters,
            limit=limit,
            glossary_hits=hits,
            notes=notes_out,
        )

    if filters and (_VEHICLE.search(q) or _SELLING.search(q) or _TOP.search(q)):
        return QuestionPlan(
            industry=Industry.AUTOMOTIVE,
            intent="ranking" if _TOP.search(q) else "aggregation",
            entity="vehicle",
            metric="units" if metric == "unknown" else metric,
            filters=filters,
            limit=limit,
            glossary_hits=["Vehicle", "Car Type"],
        )

    if _TREND.search(q) or re.search(r"\brevenue\b", q, re.I):
        return QuestionPlan(
            industry=Industry.AUTOMOTIVE,
            intent="trend" if _TREND.search(q) else "aggregation",
            entity="metric_only",
            metric="revenue" if re.search(r"\brevenue\b", q, re.I) else metric,
            filters=filters,
            limit=36,
            glossary_hits=["Revenue"] if re.search(r"\brevenue\b", q, re.I) else [],
        )

    return QuestionPlan(
        industry=Industry.AUTOMOTIVE,
        intent="unknown",
        entity="unknown",
        metric=metric,
        filters=filters,
        limit=limit,
    )


def _understand_insurance(q: str) -> QuestionPlan:
    if re.search(r"loss\s*ratio", q, re.I):
        return QuestionPlan(
            industry=Industry.INSURANCE,
            intent="trend",
            entity="metric_only",
            metric="unknown",
            glossary_hits=["Loss Ratio"],
        )
    if re.search(r"\b(claim|claims)\b", q, re.I):
        return QuestionPlan(
            industry=Industry.INSURANCE,
            intent="aggregation",
            entity="metric_only",
            metric="orders",
            glossary_hits=["Claims"],
        )
    if re.search(r"premium|gwp", q, re.I):
        return QuestionPlan(
            industry=Industry.INSURANCE,
            intent="trend",
            entity="metric_only",
            metric="revenue",
            glossary_hits=["Premium"],
        )
    if re.search(r"\bregion\b", q, re.I) and _TOP.search(q):
        return QuestionPlan(
            industry=Industry.INSURANCE,
            intent="ranking",
            entity="region",
            metric="unknown",
            limit=15,
        )
    return QuestionPlan(
        industry=Industry.INSURANCE,
        intent="unknown",
        entity="unknown",
        metric="unknown",
    )


def plan_sql_requirements(plan: QuestionPlan) -> list[str]:
    """Strings that generated SQL should satisfy (validation hints)."""
    req: list[str] = []
    if plan.entity == "salesperson":
        req.append("dim_salesman")
        req.append("salesperson")
    if plan.entity == "dealer":
        req.append("dim_dealer")
    if plan.entity == "vehicle":
        req.append("dim_carline")
    for filt in plan.filters:
        req.append(filt.value)
        if "car_type" in filt.column:
            req.append("car_type")
        if "engine_type" in filt.column:
            req.append("engine_type")
    return req
