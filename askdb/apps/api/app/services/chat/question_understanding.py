"""Deterministic NLQ question understanding — entity, metric, filters.

Mirrors Streamlit intent/glossary behaviour without large prompts: resolve
business entities and mandatory filters BEFORE template or LLM SQL generation.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal

from app.core.config import Industry
from app.services.chat.time_periods import Period, parse_period

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
    "market_share",
    "growth_ranking",
    "divergence",
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
    "claims_paid",
    "claim_count",
    "severity",
    "frequency",
    "approval_rate",
    "renewal_rate",
    "loss_ratio",
    "average_selling_price",
    "active_salespeople",
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
    # Several canonical values for one column (Compare MG and Maruti) render as IN.
    values: tuple[str, ...] = ()
    match_type: str = "exact"
    matched_text: str = ""
    confidence: float = 1.0

    @property
    def all_values(self) -> tuple[str, ...]:
        return self.values or (self.value,)


_FILTER_OPERATORS = {"=", "!=", "<>", ">", ">=", "<", "<=", "IN"}


def sql_literal(value: str) -> str:
    return "'" + str(value).replace("'", "''") + "'"


def filter_predicate(expression: str, filt: ExtractedFilter) -> str:
    """Render one governed filter; multi-value filters become ``IN (...)``."""
    operator = filt.operator.strip().upper()
    if operator not in _FILTER_OPERATORS:
        raise ValueError(f"Unsupported filter operator '{filt.operator}'")
    values = filt.all_values
    if operator == "IN" or len(values) > 1:
        return f"{expression} IN ({', '.join(sql_literal(value) for value in values)})"
    return f"{expression} {operator} {sql_literal(values[0])}"


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
    # Quarter, fiscal year, month, relative range or several years. Takes
    # precedence over ``year_filter`` and suppresses default trend windows.
    period: Period | None = None
    # Dimension implied by the entity (not asked for); dropped when the question
    # names a more specific grouping.
    default_dimension: str | None = None
    # "Increasing revenue but decreasing units": [(metric, "up"), (metric, "down")].
    divergence: list[tuple[str, str]] = field(default_factory=list)

    @property
    def has_time_scope(self) -> bool:
        return bool(self.year_filter or self.period)

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
            "growth_ranking",
            "divergence",
        }
        if self.analysis in advanced or len(self.dimensions) > 1:
            return True
        # These dimensions have no complete legacy template.
        return any(
            dimension
            in {
                "colour",
                "car_type",
                "engine_type",
                "make",
                "city",
                "state",
                "product_family",
                "line_of_business",
                "channel",
                "branch",
                "coverage_tier",
                "coverage_type",
                "claim_type",
                "policy_status",
            }
            for dimension in self.dimensions
        )


_TOP = re.compile(r"\b(top|best|highest|leading|most|lowest|worst|bottom)\b", re.I)
_LOWEST = re.compile(r"\b(lowest|worst|least|bottom|minimum|smallest)\b", re.I)
_TREND = re.compile(r"\b(trend|by\s+month|monthly|over\s+time|time\s+series)\b", re.I)
_REVENUE = re.compile(r"\b(revenue|sales\s+value|dollar|amount|turnover)\b", re.I)
_UNITS = re.compile(r"\b(unit|units|volume|qty|quantity)\b", re.I)
_SELLING = re.compile(r"\b(selling|sold|popular|sells?)\b", re.I)
_RUNNING = re.compile(r"\b(running|cumulative)\s+(?:total\s+)?", re.I)
_MOVING_AVG = re.compile(r"\b(moving|rolling)\s+average\b", re.I)
_PERIOD_GROWTH = re.compile(
    r"\b(month[-\s]*over[-\s]*month|mom|year[-\s]*over[-\s]*year|yoy)\b|"
    r"\bgrowth\b",
    re.I,
)
_GROWTH_RANK = re.compile(
    r"\b(?:fastest|quickest|most\s+rapidly)[-\s]+(?:growing|improving|rising|declining|shrinking|"
    r"falling)\b|\b(?:growing|declining|shrinking|falling)\s+(?:the\s+)?(?:fastest|most)\b|"
    r"\b(?:highest|biggest|top|best|largest|strongest|lowest|worst|weakest)\s+growth\b|"
    r"\b(?:biggest|largest|steepest|sharpest)\s+(?:decline|drop|fall)s?\b|"
    r"\b(?:which|what)\s+\w+(?:\s+\w+)?\s+(?:are|is|have|has|show|shows)\s+"
    r"(?:growing|declining|increasing|decreasing|falling|shrinking|dropping)\b|"
    r"\b(?:with|showing)\s+(?:growing|declining|increasing|decreasing|falling|shrinking)\s+"
    r"(?!\w+\s+(?:but|while|and|yet)\b)",
    re.I,
)
_DECLINE = re.compile(
    r"\b(declin\w*|decreas\w*|shrink\w*|falling|drop\w*|lowest\s+growth|worst\s+growth|"
    r"weakest\s+growth)\b",
    re.I,
)
_UP_WORDS = r"(?:increasing|growing|rising|higher|improving|up)"
_DOWN_WORDS = r"(?:decreasing|declining|falling|lower|dropping|shrinking|down)"
_METRIC_PHRASE = r"([a-z]+(?:\s+[a-z]+)?)"
_DIVERGENCE = re.compile(
    rf"\b(?P<d1>{_UP_WORDS}|{_DOWN_WORDS})\s+{_METRIC_PHRASE}\s+(?:but|while|and|with|yet)\s+"
    rf"(?:a\s+|an\s+)?(?:(?P<d2>{_UP_WORDS}|{_DOWN_WORDS})\s+)?{_METRIC_PHRASE}"
    rf"(?:\s+(?P<d3>{_UP_WORDS}|{_DOWN_WORDS}))?",
    re.I,
)
# Policies as a list to rank ("top 10 policies"), not a qualifier ("motor policies premium").
_POLICY_LIST = re.compile(
    r"\b(?:by|per|each|which|top|bottom|every|list|largest|biggest|highest|lowest)\s+"
    r"(?:\d+\s+)?(?:insurance\s+)?(?:polic(?:y|ies)|contracts?)\b(?!\s+status)|\bpolicy[-\s]?wise\b|"
    r"^(?:show\s+)?(?:polic(?:y|ies)|contracts?)\b(?!\s+status)",
    re.I,
)
_DIVERGENCE_POST = re.compile(
    rf"\b{_METRIC_PHRASE}\s+(?P<d1>{_UP_WORDS}|{_DOWN_WORDS})\s+(?:but|while|yet|and|with)\s+"
    rf"{_METRIC_PHRASE}\s+(?P<d2>{_UP_WORDS}|{_DOWN_WORDS})\b",
    re.I,
)
_METRIC_PHRASES: tuple[tuple[str, str], ...] = (
    (r"earned\s+premium", "earned_premium"),
    (r"premium|gwp", "premium"),
    (r"claims?\s+incurred|incurred", "claims_incurred"),
    (r"claims?\s+paid|paid", "claims_paid"),
    (r"claims?(?:\s+count)?", "claim_count"),
    (r"average\s+selling\s+price|asp|price", "average_selling_price"),
    (r"units?(?:\s+sold)?|volume|quantity|sold", "units"),
    (r"orders?", "orders"),
    (r"revenue|sales(?:\s+value)?|turnover", "revenue"),
)


def _metric_from_phrase(phrase: str) -> str | None:
    text = phrase.strip().lower()
    for pattern, metric in _METRIC_PHRASES:
        if re.match(rf"(?:{pattern})\b", text):
            return metric
    return None


def _parse_divergence(question: str) -> list[tuple[str, str]]:
    """Two metrics moving in stated directions ("increasing revenue but decreasing units")."""

    def direction(word: str | None) -> str | None:
        if not word:
            return None
        return "up" if re.fullmatch(_UP_WORDS, word, re.I) else "down"

    found = _DIVERGENCE.search(question)
    if found:
        groups = [g for g in found.groups() if g is not None]
        first_dir = direction(found.group("d1"))
        phrases = [
            g for g in groups if not re.fullmatch(f"{_UP_WORDS}|{_DOWN_WORDS}", g, re.I)
        ]
        second_dir = direction(found.group("d2") or found.group("d3"))
        if second_dir is None and first_dir is not None:
            joined = found.group(0).lower()
            opposite = {"up": "down", "down": "up"}[first_dir]
            second_dir = first_dir if re.search(r"\band\b", joined) else opposite
    else:
        found = _DIVERGENCE_POST.search(question)
        if not found:
            return []
        first_dir, second_dir = direction(found.group("d1")), direction(found.group("d2"))
        phrases = [found.group(1), found.group(3)]
    if len(phrases) < 2 or first_dir is None or second_dir is None:
        return []
    first, second = _metric_from_phrase(phrases[0]), _metric_from_phrase(phrases[1])
    if not first or not second or first == second:
        return []
    return [(first, first_dir), (second, second_dir)]


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
_BRAND_WORD = re.compile(
    r"\b(brand|brands|make|makes|manufacturer|manufacturers|oem|oems|carmakers?|automakers?)\b",
    re.I,
)
_MODEL_WORD = re.compile(r"\b(models?|carlines?|variants?)\b", re.I)
_MARKET_SHARE = re.compile(
    r"\bmarket\s+share\b|\bshare\s+of\s+(?:the\s+)?market\b|\b(?:brand|make|segment)\s+share\b|"
    r"\bshare\s+(?:by|per|of\s+each)\s+(?:brand|make|manufacturer)\b",
    re.I,
)
_COMPARE = re.compile(r"\b(compare|comparison|compared|versus|vs\.?|against)\b", re.I)
_YEAR_LITERAL = re.compile(r"\b(20[12]\d)\b")
_YEAR_RANGE = re.compile(r"\b(20[12]\d)\s*(?:-|\u2013|to|through|till|until)\s*(20[12]\d)\b", re.I)
_THIS_YEAR = re.compile(r"\b(this|current)\s+year\b|\bytd\b|\byear\s+to\s+date\b", re.I)
_LAST_YEAR_PHRASE = re.compile(r"\b(last|previous|prior)\s+year\b", re.I)
_SALES_TREND_ONLY = re.compile(
    r"^(?:show\s+(?:me\s+)?|what\s+is\s+(?:the\s+)?|give\s+me\s+)?(?:the\s+)?(?:overall\s+)?"
    r"(?:sales\s+trends?|trends?|trend\s+of\s+sales|sales\s+over\s+time)$",
    re.I,
)
_TIME_DIMS = ("month", "quarter", "year")
# Filter column -> GROUP BY dimension when several values are compared.
FILTER_DIMENSION: dict[str, str] = {
    "make": "make",
    "model": "model",
    "car_type": "car_type",
    "engine_type": "engine_type",
    "city": "city",
    "region_name": "region",
    "colour_name": "colour",
    "state_code": "state",
    "dealer_grade": "dealer_grade",
    "state_name": "state",
    "product_name": "product",
    "line_of_business": "line_of_business",
    "product_family": "product_family",
    "coverage_type": "coverage_type",
    "channel_name": "channel",
    "branch_name": "branch",
    "claim_status": "claim_status",
    "claim_type": "claim_type",
    "coverage_tier": "coverage_tier",
    "policy_status": "policy_status",
}
# Dimensions answering the same business question as an entity default: a named
# colour or fuel grouping replaces the default model list.
_DIMENSION_FAMILY: dict[str, frozenset[str]] = {
    "model": frozenset({"make", "model", "car_type", "engine_type", "colour"}),
    "region": frozenset({"region", "city", "state"}),
    "product": frozenset({"product", "product_family", "line_of_business", "coverage_type"}),
    "agent": frozenset({"agent", "channel", "branch"}),
    "policy": frozenset({"policy", "coverage_tier", "policy_status"}),
}
# Words after "per / within each / for each" that name the ranking partition.
_SCOPE_WORDS: dict[str, str] = {
    "make": "make", "makes": "make", "brand": "make", "brands": "make",
    "manufacturer": "make", "oem": "make", "model": "model", "models": "model",
    "segment": "car_type", "type": "car_type", "body": "car_type", "fuel": "engine_type",
    "colour": "colour", "color": "colour", "region": "region", "city": "city",
    "state": "state", "dealer": "dealer", "year": "year", "quarter": "quarter",
    "month": "month", "product": "product", "category": "product_family",
    "lob": "line_of_business", "line": "line_of_business", "channel": "channel",
    "branch": "branch", "agent": "agent",
}  # fmt: skip
_SCOPE = re.compile(r"\b(?:within\s+each|for\s+each|in\s+each|within|per|each)\s+(\w+)", re.I)
_MOVING_WINDOW = re.compile(r"\b(\d{1,2})[-\s]*(?:month|period|point)s?\s+(?:moving|rolling)\b", re.I)
# Case-sensitive so the article in "a grade" is never read as grade A.
_DEALER_GRADE = re.compile(r"\b[Gg]rade[-\s]+([ABCabc])\b|\b([ABC])[-\s]+[Gg]rade\b")
_BY_WORD = re.compile(r"\b(by|per|each|across|every|wise|breakdown|split)\b", re.I)
_FRAUD = re.compile(r"\bfraud(?:ulent)?\b|\bsuspicious\b", re.I)

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


VAGUE_OPTIONS: dict[Industry, tuple[str, ...]] = {
    Industry.AUTOMOTIVE: (
        "Total Revenue",
        "Total Units Sold",
        "Total Orders",
        "Revenue trend by month",
        "Revenue by region",
    ),
    Industry.INSURANCE: (
        "Total written premium",
        "Written premium trend by month",
        "Claims incurred by line of business",
        "Loss ratio by product",
        "Number of claims by region",
    ),
}

_VAGUE_ASK = re.compile(
    r"\b(numbers|data|figures|stats|statistics|metrics|kpis?|dashboard|overview|summary|"
    r"performance|details|info|report)\b",
    re.I,
)

_EXPLICIT_N = re.compile(
    r"\b(?:top|bottom|best|worst|highest|lowest|leading)\s+(\d{1,3})\b", re.I
)


def _limit_from_question(q: str) -> int:
    match = _EXPLICIT_N.search(q)
    if match:
        return max(1, min(int(match.group(1)), 50))
    if re.search(r"\b(the\s+)?top\b|\bbest\b|\bhighest\b|\blowest\b|\bworst\b|\bbottom\b", q, re.I):
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
        plan = _understand_automotive(q, value_filters or [])
    else:
        plan = _understand_insurance(q)
    plan.order_direction = "asc" if _LOWEST.search(q) else "desc"
    plan.filters = _merge_filters(plan.filters, value_filters or [])
    _apply_value_inference(plan, q)
    _enrich_analytical_plan(plan, q)
    if (
        plan.intent == "unknown"
        and plan.metric == "unknown"
        and not plan.filters
        and len(q.split()) <= 6
        and _VAGUE_ASK.search(q)
    ):
        plan.intent = "ambiguous"
        plan.ambiguity_options = list(VAGUE_OPTIONS[industry])
        plan.notes.append("No metric was named; offering the main measures.")
    if not plan.is_ambiguous:
        _apply_business_shape(plan, q)
        if explicit := _EXPLICIT_N.search(q):
            plan.limit = max(1, min(int(explicit.group(1)), 50))
    return plan


def _apply_time_scope(plan: QuestionPlan, question: str) -> None:
    """Quarter / FY / month / relative period, a single year, or several years."""
    if plan.analysis == "year_window_compare":
        return
    period = parse_period(question)
    if period is not None:
        plan.period = period
        plan.year_filter = None
        return
    if plan.year_filter is not None:
        return
    span = _YEAR_RANGE.search(question)
    if span and int(span.group(1)) < int(span.group(2)):
        years = list(range(int(span.group(1)), int(span.group(2)) + 1))
    else:
        years = sorted({int(year) for year in _YEAR_LITERAL.findall(question)})
    if len(years) == 1:
        plan.year_filter = years[0]
    elif len(years) >= 2:
        if not any(d in plan.dimensions for d in _TIME_DIMS):
            plan.dimensions.insert(0, "year")
        plan.period = Period(", ".join(str(y) for y in years), years=tuple(years))
    elif _THIS_YEAR.search(question):
        plan.year_filter = datetime.now().year
    elif _LAST_YEAR_PHRASE.search(question):
        plan.year_filter = datetime.now().year - 1


def _ensure_time_axis(plan: QuestionPlan, question: str) -> None:
    """Growth, running totals and moving averages are computed along time."""
    if plan.analysis not in {"period_growth", "running_total", "moving_average"}:
        return
    dims = plan.dimensions
    if not any(d in dims for d in _TIME_DIMS):
        grain = "year" if plan.analysis == "period_growth" and not re.search(
            r"\bmonth", question, re.I
        ) else "month"
        dims.append(grain)
    plan.time_grain = next((g for g in _TIME_DIMS if g in dims), None)
    plan.partition_by = [d for d in dims if d not in _TIME_DIMS]
    # Output reads category -> period so each series is contiguous.
    plan.dimensions = [*plan.partition_by, *(d for d in dims if d in _TIME_DIMS)]


def _apply_business_shape(plan: QuestionPlan, question: str) -> None:
    """Complete the plan from every part of the question: brand, comparison, period, share."""
    dims = plan.dimensions
    _apply_time_scope(plan, question)

    # Several named values of one column (MG and Maruti) are compared side by side.
    compared = [f for f in plan.filters if len(f.all_values) > 1]
    for filt in compared:
        key = FILTER_DIMENSION.get(filt.column.rsplit(".", 1)[-1])
        if key and key not in dims:
            dims.append(key)
            if plan.default_dimension in dims and plan.default_dimension != key:
                dims.remove(plan.default_dimension)
    if compared or _COMPARE.search(question):
        if plan.intent not in {"ranking"} or compared:
            plan.intent = "comparison"
        if not dims:
            # "Compare MG sales" without a grain reads naturally as year over year.
            dims.append("year")

    if plan.industry is Industry.INSURANCE:
        _ensure_time_axis(plan, question)
        plan.time_grain = next((g for g in _TIME_DIMS if g in plan.dimensions), None)
        if plan.analysis == "basic" and plan.dimensions:
            plan.analysis = "breakdown"
        return

    if _MARKET_SHARE.search(question):
        explicit = _explicit_dimensions(plan.industry, question)
        share_keys = ("make", "car_type", "engine_type", "model", "city", "region")
        filtered = [
            FILTER_DIMENSION.get(f.column.rsplit(".", 1)[-1], "") for f in plan.filters
        ]
        share_dim = next(
            (d for d in explicit if d in share_keys),
            next((d for d in ("make", "car_type", "engine_type") if d in filtered), "make"),
        )
        # Share is measured against every value of the share dimension, so drop
        # entity defaults (a model list) and keep only the period grain.
        dims[:] = [d for d in dims if d in _TIME_DIMS]
        dims.append(share_dim)
        plan.analysis = "market_share"
        plan.entity = "metric_only"
        if plan.metric == "unknown" or not re.search(r"\b(revenue|value|turnover)\b", question, re.I):
            plan.metric = "units"
        plan.notes.append(f"Market share = share of total {plan.metric} across all {share_dim} values")

    _ensure_time_axis(plan, question)
    dims = plan.dimensions
    plan.time_grain = next((g for g in ("month", "quarter", "year") if g in dims), None)
    if plan.analysis == "basic" and dims:
        plan.analysis = "breakdown"
    if plan.analysis == "ranking" and plan.intent not in {"comparison"}:
        plan.intent = "ranking"
    if plan.metric == "unknown" and (plan.filters or dims):
        plan.metric = "units" if _SELLING.search(question) else "revenue"
    if plan.entity == "unknown" and plan.metric != "unknown":
        plan.entity = "metric_only"
    if plan.intent == "unknown" and plan.metric != "unknown":
        plan.intent = "trend" if plan.time_grain else "aggregation"


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
                (
                    "car_type",
                    r"\bcar\s+types?\b|\bvehicle\s+types?\b|\bbody\s+(?:style|type)s?\b|\bsegments?\b",
                ),
                ("colour", r"\bpaint\s+colou?r\b|\bcolou?rs?\b|\bpaint\b"),
                ("engine_type", r"\bfuel(?:\s+types?)?\b|\bengine\s+types?\b|\bpowertrains?\b"),
                (
                    "make",
                    r"\bbrands?\b|\bmakes?\b|\bmanufacturers?\b|\boems?\b|\bcarmakers?\b|\bautomakers?\b",
                ),
                ("model", r"\bby\s+model\b|\bmodels?\s+(?:per|within\s+each|in\s+each|for\s+each)\b|\beach\s+model\b"),
                ("dealer", r"\bdealers?\b"),
                ("salesperson", r"\bsalespersons?\b|\bsalespeople\b|\bsales\s*rep\b"),
                (
                    "region",
                    r"\b(?:by|per|across|which|each)\s+regions?\b|\bregions\b|\bregion[-\s]?wise\b|"
                    r"\bregional\s+average\b",
                ),
                (
                    "city",
                    r"\b(?:by|per|across|which|each|every)\s+cit(?:y|ies)\b|\bcities\b|\bcity[-\s]?wise\b",
                ),
                ("state", r"\bstates?\b|\bstate[-\s]?wise\b"),
            ]
        )
    else:
        patterns.extend(
            [
                ("product", r"\bproducts?\b"),
                ("product_family", r"\b(?:product\s+)?categor(?:y|ies)\b|\bproduct\s+famil(?:y|ies)\b"),
                ("line_of_business", r"\blines?\s+of\s+business\b|\blobs?\b"),
                ("coverage_type", r"\bcoverage\s+types?\b"),
                ("coverage_tier", r"\b(?:coverage\s+)?tiers?\b"),
                ("customer", r"\bcustomers?\b|\bpolicyholders?\b"),
                ("policy_status", r"\bpolicy\s+status(?:es)?\b"),
                ("policy", _POLICY_LIST.pattern),
                ("agent", r"\bagents?\b|\bbrokers\b|\bintermediar(?:y|ies)\b"),
                ("channel", r"\bchannels?\b"),
                ("branch", r"\bbranch(?:es)?\b"),
                ("region", r"\b(?:by|per|across|which|each)\s+regions?\b|\bregions\b|\bregional\s+average\b"),
                ("state", r"\bstates?\b|\bstate[-\s]?wise\b"),
                ("claim_status", r"\bby\s+(?:claim\s+)?status\b|\bclaim\s+status(?:es)?\b"),
                ("claim_type", r"\bclaim\s+types?\b|\btype\s+of\s+claim\b"),
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
    if plan.entity == "claim" and plan.metric in {
        "approval_rate",
        "severity",
        "frequency",
        "loss_ratio",
    }:
        return None  # a claim-status split of a rate answers nothing
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
    # "Motor line of business" or "Karnataka state" names a value, not a grouping.
    if not _BY_WORD.search(question):
        named = {
            FILTER_DIMENSION.get(f.column.rsplit(".", 1)[-1])
            for f in plan.filters
            if len(f.all_values) == 1
        }
        dimensions = [d for d in dimensions if d not in named]
    default = _default_dimension(plan)
    family = _DIMENSION_FAMILY.get(default or "", frozenset({default}))
    if plan.entity == "claim":
        # Claim status is only a fallback grouping for a bare claims question.
        family = frozenset(d for d in dimensions if d not in _TIME_DIMS) or family
    if (
        default
        and plan.entity != "metric_only"
        and not any(d in family for d in dimensions)
    ):
        dimensions.append(default)
        plan.default_dimension = default
    elif plan.entity == "vehicle" and not any(
        d in {"make", "model", "car_type", "engine_type"} for d in dimensions
    ) and not any("dim_carline" in f.column for f in plan.filters):
        # "Which colour sells most" is a colour ranking, not a vehicle list.
        plan.entity = "metric_only"

    if _TREND.search(question) and not any(d in dimensions for d in ("month", "quarter", "year")):
        dimensions.insert(0, "month")
    plan.dimensions = dimensions
    plan.time_grain = next(
        (grain for grain in ("month", "quarter", "year") if grain in dimensions),
        None,
    )

    divergence = _parse_divergence(question)
    if divergence:
        plan.analysis = "divergence"
        plan.divergence = divergence
        plan.metric = divergence[0][0]  # type: ignore[assignment]
        plan.intent = "comparison"
        plan.dimensions = [d for d in dimensions if d not in _TIME_DIMS]
        plan.time_grain = None
        plan.limit = 20
        return
    if _GROWTH_RANK.search(question):
        plan.analysis = "growth_ranking"
        plan.intent = "ranking"
        plan.order_direction = "asc" if _DECLINE.search(question) else "desc"
        plan.dimensions = [d for d in dimensions if d not in _TIME_DIMS]
        plan.time_grain = None
        if plan.metric in {"orders", "claim_count"}:
            plan.aggregation = "count_distinct"
        return
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

    if plan.analysis == "moving_average" and (size := _MOVING_WINDOW.search(question)):
        plan.window_months = max(2, min(int(size.group(1)), 24))

    if plan.analysis in {"top_n_per_group", "above_average"} and len(dimensions) >= 2:
        scoped = [
            _SCOPE_WORDS[word.lower()]
            for word in _SCOPE.findall(question)
            if word.lower() in _SCOPE_WORDS and _SCOPE_WORDS[word.lower()] in dimensions
        ]
        scope_patterns = {
            "region": r"\bwithin\s+each\s+region\b|\bper\s+region\b|\bregional\s+average\b",
            "city": r"\bwithin\s+each\s+city\b|\bper\s+city\b|\beach\s+city\b",
            "state": r"\bwithin\s+each\s+state\b|\bper\s+state\b|\beach\s+state\b",
            "product_family": (
                r"\bwithin\s+each\s+(?:product\s+)?category\b|"
                r"\bper\s+(?:product\s+)?category\b|\bcategory\s+average\b"
            ),
        }
        plan.partition_by = list(dict.fromkeys(scoped)) or [
            dimension
            for dimension, pattern in scope_patterns.items()
            if dimension in dimensions and re.search(pattern, question, re.I)
        ]
        if len(plan.partition_by) >= len(dimensions):
            plan.partition_by = plan.partition_by[:1]
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
    """One filter per column; several values on a column become ``IN`` (never AND)."""
    by_column: dict[str, list[ExtractedFilter]] = {}
    for filt in [*primary, *additional]:
        by_column.setdefault(filt.column.casefold(), []).append(filt)
    merged: list[ExtractedFilter] = []
    for items in by_column.values():
        values = tuple(
            dict.fromkeys(value for item in items for value in item.all_values)
        )
        first = items[0]
        if len(items) == 1 or len(values) == len(first.all_values):
            merged.append(first)
            continue
        if any(item.operator.strip().upper() not in {"=", "IN"} for item in items):
            merged.extend(items)
            continue
        domain = first.label.split(" ", 1)[0] if first.label else first.column.rsplit(".", 1)[-1]
        if " = " in first.label:
            domain = first.label.split(" = ", 1)[0]
        elif " in (" in first.label:
            domain = first.label.split(" in (", 1)[0]
        merged.append(
            ExtractedFilter(
                column=first.column,
                operator="IN",
                value=values[0],
                label=f"{domain} in ({', '.join(values)})",
                source=first.source,
                values=values,
                match_type=first.match_type,
                matched_text=first.matched_text,
                confidence=min(item.confidence for item in items),
            )
        )
    return merged


def _apply_value_inference(plan: QuestionPlan, question: str) -> None:
    """Promote a plan when a live dictionary value supplies the missing entity."""
    columns = {f.column.casefold() for f in plan.filters}
    if plan.industry is Industry.AUTOMOTIVE:
        if any("dim_carline" in col for col in columns) and plan.entity == "unknown":
            # A named brand/model alone ("Maruti") asks for its performance, not a
            # model leaderboard; only vehicle/ranking words make it a vehicle list.
            vehicle_ask = bool(_VEHICLE.search(question) or _TOP.search(question))
            plan.entity = "vehicle" if vehicle_ask else "metric_only"
            if plan.entity == "metric_only" and plan.metric == "unknown":
                plan.metric = "units" if _SELLING.search(question) else "revenue"
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


def _understand_automotive(
    q: str, value_filters: list[ExtractedFilter] | None = None
) -> QuestionPlan:
    normalized = _normalized_ask(q)
    if _SALES_TREND_ONLY.match(normalized) and not value_filters:
        return QuestionPlan(
            industry=Industry.AUTOMOTIVE,
            intent="ambiguous",
            entity="metric_only",
            metric="unknown",
            ambiguity_options=[
                "Total revenue trend by month",
                "Units sold trend by month",
                "Revenue by brand by year",
                "Maruti Suzuki sales trend",
            ],
            notes=["A sales trend needs a scope: all brands, one brand, or a metric."],
        )
    if normalized in _BARE_SALES:
        return QuestionPlan(
            industry=Industry.AUTOMOTIVE,
            intent="ambiguous",
            entity="metric_only",
            metric="unknown",
            ambiguity_options=[
                "Total Revenue",
                "Total Units Sold",
                "Total Orders",
                "Revenue trend by month",
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
    if grade := _DEALER_GRADE.search(q):
        value = (grade.group(1) or grade.group(2)).upper()
        filters.append(
            ExtractedFilter(
                column="automotive.dim_dealer.dealer_grade",
                operator="=",
                value=value,
                label=f"Dealer grade = {value}",
            )
        )
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

    if _BRAND_WORD.search(q) and not _MODEL_WORD.search(q):
        # Brand questions group by dim_carline.make ("Top brand by revenue").
        hits.append("Brand")
        if metric == "unknown":
            metric = "units" if _SELLING.search(q) else "revenue"
        return QuestionPlan(
            industry=Industry.AUTOMOTIVE,
            intent="ranking" if _TOP.search(q) else "aggregation",
            entity="metric_only",
            metric=metric,
            filters=filters,
            limit=limit if _TOP.search(q) else 20,
            glossary_hits=hits,
            notes=["Brand means dim_carline.make."],
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
        explicit_metric = bool(
            _UNITS.search(q)
            or _REVENUE.search(q)
            or _REGION.search(q)
            or _YEAR_LITERAL.search(q)
            or parse_period(q)
            or re.search(r"\b(?:in|for|at|within)\s+(?!the\b|a\b)[a-z]", q, re.I)
        )
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


_PRODUCT_WITH_METRIC_WORD = re.compile(r"\bhome\s+premium\b", re.I)


def _understand_insurance(q: str) -> QuestionPlan:
    # "Home Premium" is a product name; it must not select the premium metric.
    plan = _understand_insurance_metric(_PRODUCT_WITH_METRIC_WORD.sub("home product", q))
    if _FRAUD.search(q):
        plan.filters.append(
            ExtractedFilter(
                column="insurance.fact_claims.fraud_suspected_flag",
                operator="=",
                value="true",
                label="Fraud suspected",
            )
        )
        if plan.metric in {"unknown", "premium"}:
            plan.metric = "claim_count"
    return plan


def _understand_insurance_metric(q: str) -> QuestionPlan:
    limit = _limit_from_question(q)
    intent: IntentKind = "ranking" if _TOP.search(q) else "aggregation"
    entity: EntityKind = "metric_only"
    # "Broker" alone is usually the Broker channel; only "brokers" lists people.
    if re.search(r"\b(agent|agents|brokers|intermediar(?:y|ies)|advisors?)\b", q, re.I):
        entity = "agent"
    elif re.search(r"\b(customer|customers|policyholder|policyholders)\b", q, re.I):
        entity = "customer"
    elif _POLICY_LIST.search(q):
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
    if re.search(
        r"\b(claims?\s+paid|paid\s+(?:claims?|amount)|payouts?|claim\s+payments?|amount\s+paid)\b",
        q,
        re.I,
    ):
        return QuestionPlan(
            industry=Industry.INSURANCE,
            intent=intent,
            entity=entity,
            metric="claims_paid",
            limit=limit,
            glossary_hits=["Claims Paid"],
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
        req.extend(filt.all_values)
        if "car_type" in filt.column:
            req.append("car_type")
        if "engine_type" in filt.column:
            req.append("engine_type")
    return req
