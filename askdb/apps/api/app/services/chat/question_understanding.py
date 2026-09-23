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
    "comparison",
    "lookup",
    "ambiguous",
    "unknown",
]
AnalysisKind = Literal[
    "basic",
    "breakdown",
    "ranking",
    "top_n_per_group",
    "running_total",
    "moving_average",
    "period_growth",
    "contribution",
    "above_average",
    "year_window_compare",
]
AggregationKind = Literal["sum", "count", "count_distinct", "avg", "ratio"]

EntityKind = Literal[
    "salesperson",
    "dealer",
    "vehicle",
    "region",
    "agent",
    "product",
    "policy",
    "customer",
    "claim",
    "metric_only",
    "unknown",
]

MetricKind = Literal[
    "units",
    "revenue",
    "orders",
    "premium",
    "earned_premium",
    "claims_incurred",
    "claim_count",
    "severity",
    "frequency",
    "approval_rate",
    "renewal_rate",
    "loss_ratio",
    "average_selling_price",
    "unknown",
]
OrderDirection = Literal["asc", "desc"]


@dataclass(frozen=True, slots=True)
class ExtractedFilter:
    column: str  # e.g. automotive.dim_carline.car_type
    operator: str
    value: str
    label: str
    source: str = "question"


@dataclass(slots=True)
class QuestionPlan:
    industry: Industry
    intent: IntentKind
    entity: EntityKind
    metric: MetricKind
    filters: list[ExtractedFilter] = field(default_factory=list)
    limit: int = 10
    order_direction: OrderDirection = "desc"
    ambiguity_options: list[str] = field(default_factory=list)
    glossary_hits: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    aggregation: AggregationKind = "sum"
    dimensions: list[str] = field(default_factory=list)
    time_grain: str | None = None
    analysis: AnalysisKind = "basic"
    partition_by: list[str] = field(default_factory=list)
    window_months: int | None = None
    window_years: int | None = None
    year_filter: int | None = None

    @property
    def is_ambiguous(self) -> bool:
        return self.intent == "ambiguous" or bool(self.ambiguity_options)

    @property
    def requires_semantic_compiler(self) -> bool:
        """True when a fixed single-grain template cannot faithfully answer the plan."""
        advanced = {
            "ranking",
            "top_n_per_group",
            "running_total",
            "moving_average",
            "period_growth",
            "contribution",
            "above_average",
            "year_window_compare",
        }
        if self.analysis in advanced or len(self.dimensions) > 1:
            return True
        # These dimensions have no complete legacy template.
        return any(
            dimension
            in {
                "colour",
                "car_type",
                "make",
                "city",
                "state",
                "product_family",
                "line_of_business",
                "channel",
                "branch",
            }
            for dimension in self.dimensions
        )


_TOP = re.compile(r"\b(top|best|highest|leading|most|lowest|worst)\b", re.I)
_LOWEST = re.compile(r"\b(lowest|worst|least|bottom|minimum|smallest)\b", re.I)
_TREND = re.compile(r"\b(trend|by\s+month|monthly|over\s+time|time\s+series)\b", re.I)
_REVENUE = re.compile(r"\b(revenue|sales\s+value|dollar|amount|turnover)\b", re.I)
_UNITS = re.compile(r"\b(unit|units|volume|qty|quantity)\b", re.I)
_SELLING = re.compile(r"\b(selling|sold|popular)\b", re.I)
_RUNNING = re.compile(r"\b(running|cumulative)\s+(?:total\s+)?", re.I)
_MOVING_AVG = re.compile(r"\b(moving|rolling)\s+average\b", re.I)
_PERIOD_GROWTH = re.compile(
    r"\b(month[-\s]*over[-\s]*month|mom|year[-\s]*over[-\s]*year|yoy)\b|"
    r"\bgrowth\b",
    re.I,
)
_CONTRIBUTION = re.compile(
    r"\b(contribution|share|percentage|percent|%)\b",
    re.I,
)
_ABOVE_AVERAGE = re.compile(
    r"\b(above|greater\s+than|more\s+than|outperform(?:ing|ed)?|compared\s+to)\b"
    r"[\s\S]{0,40}\baverage\b",
    re.I,
)
_PER_GROUP = re.compile(r"\b(?:within\s+)?each\b|\bper\s+(?!cent\b)", re.I)

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
    if _UNITS.search(q) or _SELLING.search(q):
        return "units"
    if re.search(r"\b(orders?|transactions?)\b", q, re.I):
        return "orders"
    if _REVENUE.search(q):
        return "revenue"
    # "sales" is revenue unless it names a person (salesperson, sales rep).
    if re.search(r"\bsales\b", q, re.I) and not _SALESPERSON.search(q):
        return "revenue"
    return "unknown"


def _normalized_ask(question: str) -> str:
    return re.sub(r"\s+", " ", (question or "").strip().lower()).strip(" ?.!")


_BARE_SALES = {
    "sales",
    "show sales",
    "show me sales",
    "give me sales",
    "what is sales",
    "what's sales",
}
_BARE_PERFORMANCE = {
    "performance",
    "show performance",
    "show me performance",
    "how is performance",
}
_BARE_GROWTH = {
    "growth",
    "show growth",
    "show me growth",
    "what is growth",
}


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
    if re.search(r"\b(the\s+)?top\b|\bbest\b|\bhighest\b|\blowest\b|\bworst\b", q, re.I):
        return 10
    return 20


def understand_question(
    industry: Industry,
    question: str,
    *,
    value_filters: list[ExtractedFilter] | None = None,
) -> QuestionPlan:
    q = (question or "").strip()
    if not q:
        return QuestionPlan(
            industry=industry,
            intent="unknown",
            entity="unknown",
            metric="unknown",
        )

    if industry is Industry.AUTOMOTIVE:
        plan = _understand_automotive(q)
    else:
        plan = _understand_insurance(q)
    plan.order_direction = "asc" if _LOWEST.search(q) else "desc"
    plan.filters = _merge_filters(plan.filters, value_filters or [])
    _apply_value_inference(plan, q)
    _enrich_analytical_plan(plan, q)
    return plan


def _append_unique(items: list[str], value: str) -> None:
    if value not in items:
        items.append(value)


def _explicit_dimensions(industry: Industry, question: str) -> list[str]:
    """Extract ordered semantic GROUP BY dimensions, not concrete filter values."""
    q = question.lower()
    dimensions: list[str] = []

    patterns: list[tuple[str, str]] = [
        ("month", r"\bmonthly\b|\bby\s+month\b|\bper\s+month\b|\bmonth[-\s]*over[-\s]*month\b|\bmom\b"),
        ("quarter", r"\bquarterly\b|\bby\s+quarter\b|\bper\s+quarter\b"),
        ("year", r"\byearly\b|\bby\s+year\b|\bper\s+year\b|\beach\s+year\b|\byear[-\s]*over[-\s]*year\b|\byoy\b"),
    ]
    if industry is Industry.AUTOMOTIVE:
        patterns.extend(
            [
                ("car_type", r"\bcar\s+type\b|\bvehicle\s+type\b|\bbody\s+style\b"),
                ("colour", r"\bpaint\s+colou?r\b|\bcolou?r\b|\bpaint\b"),
                ("make", r"\bcar\s+brand\b|\bvehicle\s+brand\b|\bby\s+(?:make|brand)\b"),
                ("model", r"\bby\s+model\b|\bmodels?\s+(?:per|within\s+each)\b"),
                ("dealer", r"\bdealers?\b"),
                ("salesperson", r"\bsalespersons?\b|\bsalespeople\b|\bsales\s*rep\b"),
                ("region", r"\b(?:by|per|across)\s+regions?\b|\bwithin\s+each\s+region\b|\bregional\s+average\b"),
                ("city", r"\b(?:by|per)\s+cit(?:y|ies)\b|\bwithin\s+each\s+city\b|\beach\s+city\b"),
            ]
        )
    else:
        patterns.extend(
            [
                ("product", r"\bproducts?\b"),
                ("product_family", r"\b(?:product\s+)?categor(?:y|ies)\b|\bproduct\s+famil(?:y|ies)\b"),
                ("line_of_business", r"\bline\s+of\s+business\b|\blob\b"),
                ("customer", r"\bcustomers?\b|\bpolicyholders?\b"),
                ("policy", r"\bpolic(?:y|ies)\b"),
                ("agent", r"\bagents?\b|\bbrokers?\b"),
                ("channel", r"\bby\s+channel\b|\bper\s+channel\b"),
                ("branch", r"\bby\s+branch\b|\bper\s+branch\b"),
                ("region", r"\b(?:by|per|across)\s+regions?\b|\bwithin\s+each\s+region\b|\bregional\s+average\b"),
                ("state", r"\b(?:by|per)\s+state\b|\bwithin\s+each\s+state\b"),
                ("claim_status", r"\bby\s+(?:claim\s+)?status\b"),
            ]
        )

    hits: list[tuple[int, str]] = []
    for name, pattern in patterns:
        match = re.search(pattern, q, re.I)
        if match:
            hits.append((match.start(), name))
    for _, name in sorted(hits):
        _append_unique(dimensions, name)
    return dimensions


def _default_dimension(plan: QuestionPlan) -> str | None:
    return {
        "salesperson": "salesperson",
        "dealer": "dealer",
        "vehicle": "model",
        "region": "region",
        "agent": "agent",
        "product": "product",
        "policy": "policy",
        "customer": "customer",
        "claim": "claim_status",
    }.get(plan.entity)


_WINDOW = re.compile(
    r"last\s+(\d{1,2})\s+months?\b[\s\S]{0,80}last\s+(\d{1,2})\s+years?",
    re.I,
)


def _enrich_analytical_plan(plan: QuestionPlan, question: str) -> None:
    window = _WINDOW.search(question)
    if window and plan.intent != "ambiguous":
        plan.intent = "comparison"
        plan.analysis = "year_window_compare"
        plan.window_months = max(1, min(int(window.group(1)), 12))
        plan.window_years = max(1, min(int(window.group(2)), 10))
        plan.entity = "metric_only"
        if plan.metric in {"unknown", "units"}:
            plan.metric = "revenue"
        plan.dimensions = ["year", "month"]
        plan.time_grain = "month"
        plan.limit = 36
        plan.notes.append("Compare the latest months across prior years")
        return

    dimensions = _explicit_dimensions(plan.industry, question)
    default = _default_dimension(plan)
    if default and default not in dimensions and plan.entity != "metric_only":
        dimensions.append(default)

    if _TREND.search(question) and not any(d in dimensions for d in ("month", "quarter", "year")):
        dimensions.insert(0, "month")
    plan.dimensions = dimensions
    plan.time_grain = next(
        (grain for grain in ("month", "quarter", "year") if grain in dimensions),
        None,
    )

    if _ABOVE_AVERAGE.search(question):
        plan.analysis = "above_average"
    elif _MOVING_AVG.search(question):
        plan.analysis = "moving_average"
    elif _RUNNING.search(question):
        plan.analysis = "running_total"
    elif _PERIOD_GROWTH.search(question):
        plan.analysis = "period_growth"
    elif _CONTRIBUTION.search(question):
        plan.analysis = "contribution"
    elif _TOP.search(question) and _PER_GROUP.search(question) and len(dimensions) >= 2:
        plan.analysis = "top_n_per_group"
    elif _TOP.search(question) or re.search(r"\brank(?:ing)?\b", question, re.I):
        plan.analysis = "ranking"
    elif dimensions:
        plan.analysis = "breakdown"

    if plan.analysis in {"top_n_per_group", "above_average"} and len(dimensions) >= 2:
        scope_patterns = {
            "region": r"\bwithin\s+each\s+region\b|\bper\s+region\b|\bregional\s+average\b",
            "city": r"\bwithin\s+each\s+city\b|\bper\s+city\b|\beach\s+city\b",
            "state": r"\bwithin\s+each\s+state\b|\bper\s+state\b|\beach\s+state\b",
            "product_family": (
                r"\bwithin\s+each\s+(?:product\s+)?category\b|"
                r"\bper\s+(?:product\s+)?category\b|\bcategory\s+average\b"
            ),
        }
        plan.partition_by = [
            dimension
            for dimension, pattern in scope_patterns.items()
            if dimension in dimensions and re.search(pattern, question, re.I)
        ]
        if not plan.partition_by:
            plan.partition_by = dimensions[:-1]
        # Stable output reads scope -> leaf, regardless of phrase word order.
        dimensions = [
            *plan.partition_by,
            *(dimension for dimension in dimensions if dimension not in plan.partition_by),
        ]
        plan.dimensions = dimensions
    elif plan.analysis in {"period_growth", "running_total", "moving_average"}:
        plan.partition_by = [d for d in dimensions if d not in {"month", "quarter", "year"}]

    if plan.metric in {"orders", "claim_count"}:
        plan.aggregation = "count_distinct"
    elif plan.metric in {
        "loss_ratio",
        "frequency",
        "approval_rate",
        "renewal_rate",
        "severity",
    }:
        plan.aggregation = "ratio"


def _merge_filters(
    primary: list[ExtractedFilter],
    additional: list[ExtractedFilter],
) -> list[ExtractedFilter]:
    merged: list[ExtractedFilter] = []
    seen: set[tuple[str, str]] = set()
    for filt in [*primary, *additional]:
        key = (filt.column.casefold(), filt.value.casefold())
        if key not in seen:
            merged.append(filt)
            seen.add(key)
    return merged


def _apply_value_inference(plan: QuestionPlan, question: str) -> None:
    """Promote a plan when a live dictionary value supplies the missing entity."""
    columns = {f.column.casefold() for f in plan.filters}
    if plan.industry is Industry.AUTOMOTIVE:
        if any("dim_carline" in col for col in columns) and plan.entity == "unknown":
            plan.entity = "vehicle"
        elif any("dim_region" in col for col in columns) and plan.entity == "unknown":
            plan.entity = "region"
        if plan.entity != "unknown" and plan.intent == "unknown":
            plan.intent = "ranking" if _TOP.search(question) else "aggregation"
        if plan.metric == "unknown" and plan.entity in {
            "vehicle",
            "region",
            "salesperson",
            "dealer",
        }:
            plan.metric = "units" if _SELLING.search(question) else "revenue"
    else:
        if any("dim_agent" in col for col in columns) and plan.entity == "unknown":
            plan.entity = "agent"
        elif any("dim_product" in col for col in columns) and plan.entity == "unknown":
            plan.entity = "product"
        elif any("dim_policy" in col for col in columns) and plan.entity == "unknown":
            plan.entity = "policy"
        elif any("dim_region" in col for col in columns) and plan.entity == "unknown":
            plan.entity = "region"
        if plan.entity != "unknown" and plan.intent == "unknown":
            plan.intent = "ranking" if _TOP.search(question) else "aggregation"


def _understand_automotive(q: str) -> QuestionPlan:
    normalized = _normalized_ask(q)
    if normalized in _BARE_SALES:
        return QuestionPlan(
            industry=Industry.AUTOMOTIVE,
            intent="ambiguous",
            entity="metric_only",
            metric="unknown",
            ambiguity_options=[
                "Total Revenue",
                "Total Orders",
                "Quantity Sold",
                "Revenue by month",
                "Revenue by region",
            ],
            notes=["Sales was not specific enough to choose a metric."],
        )
    if normalized in _BARE_PERFORMANCE:
        return QuestionPlan(
            industry=Industry.AUTOMOTIVE,
            intent="ambiguous",
            entity="unknown",
            metric="unknown",
            ambiguity_options=[
                "Dealer performance",
                "Best performing region",
                "Top selling car by units",
                "Top salesperson",
            ],
            notes=["Performance needs a business entity."],
        )
    if normalized in _BARE_GROWTH:
        return QuestionPlan(
            industry=Industry.AUTOMOTIVE,
            intent="ambiguous",
            entity="metric_only",
            metric="unknown",
            ambiguity_options=[
                "Revenue growth by month",
                "Order growth by month",
                "Quantity sold growth by month",
            ],
            notes=["Growth needs a metric."],
        )

    metric = _metric_from_question(q)
    filters = _extract_body_filters(q)
    if re.search(r"\bmumbai\b", q, re.I):
        filters.append(
            ExtractedFilter(
                column="automotive.dim_region.city",
                operator="=",
                value="Mumbai",
                label="City = Mumbai",
            )
        )
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
        elif not _VEHICLE.search(q) and (
            _TOP.search(q) or re.search(r"\bperform", q, re.I)
        ):
            hits.append("Region")
            if metric == "unknown":
                metric = "revenue" if re.search(r"\bperform", q, re.I) else "units"
            return QuestionPlan(
                industry=Industry.AUTOMOTIVE,
                intent="ranking",
                entity="region",
                metric=metric,
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

    if metric != "unknown" or filters:
        resolved = metric if metric != "unknown" else "revenue"
        return QuestionPlan(
            industry=Industry.AUTOMOTIVE,
            intent="trend" if _TREND.search(q) else "aggregation",
            entity="metric_only",
            metric=resolved,
            filters=filters,
            limit=36,
            glossary_hits=(
                ["Orders"]
                if resolved == "orders"
                else ["Revenue"]
                if resolved == "revenue"
                else ["Units"]
            ),
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
    limit = _limit_from_question(q)
    intent: IntentKind = "ranking" if _TOP.search(q) else "aggregation"
    entity: EntityKind = "metric_only"
    if re.search(r"\b(agent|agents|broker|brokers|intermediar(?:y|ies)|advisor)\b", q, re.I):
        entity = "agent"
    elif re.search(r"\b(customer|customers|policyholder|policyholders)\b", q, re.I):
        entity = "customer"
    elif re.search(r"\b(policy|policies|contract|contracts)\b", q, re.I):
        entity = "policy"
    elif re.search(r"\b(product|products|lob|line\s+of\s+business|business\s+line)\b", q, re.I):
        entity = "product"
    elif re.search(r"\b(region|regions|territory|territories|state|states)\b", q, re.I):
        entity = "region"
    elif re.search(r"\b(claim|claims)\b", q, re.I):
        entity = "claim"

    if re.search(r"loss\s*ratio", q, re.I):
        return QuestionPlan(
            industry=Industry.INSURANCE,
            intent="trend" if _TREND.search(q) else intent,
            entity=entity,
            metric="loss_ratio",
            limit=limit,
            glossary_hits=["Loss Ratio"],
        )
    if re.search(r"\b(severity|average\s+(claim|loss))\b", q, re.I):
        return QuestionPlan(
            industry=Industry.INSURANCE,
            intent=intent,
            entity=entity,
            metric="severity",
            limit=limit,
            glossary_hits=["Average Claim Severity"],
        )
    if re.search(r"\b(frequency|claims?\s+per\s+exposure)\b", q, re.I):
        return QuestionPlan(
            industry=Industry.INSURANCE,
            intent=intent,
            entity=entity,
            metric="frequency",
            limit=limit,
            glossary_hits=["Claim Frequency"],
        )
    if re.search(r"\b(approval\s+rate|approved\s+(percentage|rate))\b", q, re.I):
        return QuestionPlan(
            industry=Industry.INSURANCE,
            intent=intent,
            entity=entity,
            metric="approval_rate",
            limit=limit,
            glossary_hits=["Approval Rate"],
        )
    if re.search(r"\b(renewal\s+rate|persistency|retention\s+rate)\b", q, re.I):
        return QuestionPlan(
            industry=Industry.INSURANCE,
            intent=intent,
            entity=entity,
            metric="renewal_rate",
            limit=limit,
            glossary_hits=["Renewal Rate"],
        )
    if re.search(r"\b(earned\s+premium|premium\s+earned)\b", q, re.I):
        return QuestionPlan(
            industry=Industry.INSURANCE,
            intent="trend" if _TREND.search(q) else intent,
            entity=entity,
            metric="earned_premium",
            limit=limit,
            glossary_hits=["Earned Premium"],
        )
    if re.search(r"\b(premium|gwp|business\s+written)\b", q, re.I):
        return QuestionPlan(
            industry=Industry.INSURANCE,
            intent="trend" if _TREND.search(q) else intent,
            entity=entity,
            metric="premium",
            limit=limit,
            glossary_hits=["Gross Written Premium"],
        )
    if re.search(r"\b(incurred|claims?\s+cost|loss(?:es)?)\b", q, re.I):
        return QuestionPlan(
            industry=Industry.INSURANCE,
            intent=intent,
            entity=entity,
            metric="claims_incurred",
            limit=limit,
            glossary_hits=["Claims Incurred"],
        )
    if re.search(r"\b(claim|claims)\b", q, re.I):
        return QuestionPlan(
            industry=Industry.INSURANCE,
            intent=intent,
            entity=entity,
            metric="claim_count",
            limit=limit,
            glossary_hits=["Claim Count"],
        )
    if entity != "metric_only":
        return QuestionPlan(
            industry=Industry.INSURANCE,
            intent=intent,
            entity=entity,
            metric="premium"
            if entity in {"agent", "product", "policy", "customer"}
            else "claim_count",
            limit=limit,
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
