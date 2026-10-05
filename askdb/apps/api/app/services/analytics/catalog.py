"""What Analytics Builder can combine, and a business explanation when it can't.

The catalog is the single source of the builder's rules: the API serves it to the
screen (to disable options with a reason) and the runner checks it again before any
SQL is compiled, so an invalid combination never reaches the database.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Literal

from app.core.config import Industry
from app.schemas.analytics import (
    AnalysisCapability,
    AnalyticsCapabilities,
    AnalyticsFix,
    AnalyticsInspection,
    AnalyticsIssue,
    AnalyticsOption,
    AnalyticsSpec,
    AnalyticsSuggestion,
    DatePresetCapability,
    DimensionCapability,
    FilterDomainCapability,
    MetricCapability,
)
from app.services.chat.semantic_analytics import (
    _AUTOMOTIVE_DIMENSIONS,
    _INSURANCE_DIMENSIONS,
    DimensionSpec,
)
from app.services.chat.value_dictionary import ValueDomain, domains_for

MetricKindName = Literal["sum", "count", "distinct", "ratio", "target", "unsupported"]
TimeRule = Literal["required", "forbidden", "optional"]

# --- metrics -----------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class MetricDef:
    id: str
    plan_metric: str
    fact: str
    kind: MetricKindName
    format: str
    reason: str | None = None

    @property
    def supported(self) -> bool:
        return self.kind not in {"target", "unsupported"}

    @property
    def additive(self) -> bool:
        return self.kind in {"sum", "count"}

    @property
    def nature(self) -> str:
        return {
            "ratio": "an average or rate",
            "distinct": "a distinct count",
        }.get(self.kind, "not a total")


_TARGET_REASON = (
    "Targets are shown next to actuals: pick Revenue or Units Sold and choose Actual vs Target."
)
_CROSS_FACT_REASON = (
    "{label} combines premium and claims data at different grains. Ask AI Chat or open the "
    "Executive Cockpit for it."
)

_METRICS: dict[Industry, tuple[MetricDef, ...]] = {
    Industry.AUTOMOTIVE: (
        MetricDef("revenue", "revenue", "fact_sales", "sum", "currency"),
        MetricDef("units_sold", "units", "fact_sales", "sum", "integer"),
        MetricDef("orders", "orders", "fact_sales", "count", "integer"),
        MetricDef(
            "average_selling_price", "average_selling_price", "fact_sales", "ratio", "currency"
        ),
        MetricDef("active_salespeople", "active_salespeople", "fact_sales", "distinct", "integer"),
        MetricDef("target_revenue", "revenue", "dim_targets", "target", "currency", _TARGET_REASON),
        MetricDef("target_units", "units", "dim_targets", "target", "integer", _TARGET_REASON),
    ),
    Industry.INSURANCE: (
        MetricDef("gross_written_premium", "premium", "fact_policy_monthly", "sum", "currency"),
        MetricDef("earned_premium", "earned_premium", "fact_policy_monthly", "sum", "currency"),
        MetricDef("claims_incurred", "claims_incurred", "fact_claims", "sum", "currency"),
        MetricDef("claims_paid", "claims_paid", "fact_claims", "sum", "currency"),
        MetricDef("claim_count", "claim_count", "fact_claims", "count", "integer"),
        MetricDef("average_claim_severity", "severity", "fact_claims", "ratio", "currency"),
        MetricDef("approval_rate", "approval_rate", "fact_claims", "ratio", "percent"),
        MetricDef("renewal_rate", "renewal_rate", "fact_policy_monthly", "ratio", "percent"),
        MetricDef("loss_ratio", "loss_ratio", "", "unsupported", "percent", _CROSS_FACT_REASON),
        MetricDef("claim_frequency", "frequency", "", "unsupported", "decimal", _CROSS_FACT_REASON),
    ),
}

# Ids saved by earlier versions of the builder or produced by AI Assist.
_METRIC_ALIASES: dict[str, str] = {
    "units": "units_sold",
    "premium": "gross_written_premium",
    "written_premium": "gross_written_premium",
    "severity": "average_claim_severity",
    "frequency": "claim_frequency",
}

# --- dimensions ----------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class DimensionDef:
    id: str
    label: str
    group: str

    @property
    def time(self) -> bool:
        return self.id in TIME_GRAINS


TIME_GRAINS = ("month", "quarter", "year")

_DIMENSIONS: dict[Industry, tuple[DimensionDef, ...]] = {
    Industry.AUTOMOTIVE: (
        DimensionDef("month", "Month", "Time"),
        DimensionDef("quarter", "Quarter", "Time"),
        DimensionDef("year", "Year", "Time"),
        DimensionDef("region", "Region", "Geography"),
        DimensionDef("state", "State", "Geography"),
        DimensionDef("city", "City", "Geography"),
        DimensionDef("make", "Brand", "Vehicle"),
        DimensionDef("model", "Model", "Vehicle"),
        DimensionDef("car_type", "Vehicle Type", "Vehicle"),
        DimensionDef("engine_type", "Fuel Type", "Vehicle"),
        DimensionDef("colour", "Colour", "Vehicle"),
        DimensionDef("dealer", "Dealer", "Sales Organization"),
        DimensionDef("salesperson", "Salesperson", "Sales Organization"),
    ),
    Industry.INSURANCE: (
        DimensionDef("month", "Month", "Time"),
        DimensionDef("quarter", "Quarter", "Time"),
        DimensionDef("year", "Year", "Time"),
        DimensionDef("line_of_business", "Line of Business", "Product"),
        DimensionDef("product_family", "Product Family", "Product"),
        DimensionDef("product", "Product", "Product"),
        DimensionDef("coverage_type", "Coverage Type", "Product"),
        DimensionDef("coverage_tier", "Coverage Tier", "Policy"),
        DimensionDef("policy_status", "Policy Status", "Policy"),
        DimensionDef("region", "Region", "Geography"),
        DimensionDef("state", "State", "Geography"),
        DimensionDef("agent", "Agent", "Distribution"),
        DimensionDef("channel", "Channel", "Distribution"),
        DimensionDef("branch", "Branch", "Distribution"),
        DimensionDef("claim_status", "Claim Status", "Claims"),
        DimensionDef("claim_type", "Claim Type", "Claims"),
    ),
}

_DIMENSION_ALIASES: dict[str, str] = {
    "date": "month",
    "brand": "make",
    "vehicle_type": "car_type",
    "car": "car_type",
    "vehicle": "car_type",
    "fuel_type": "engine_type",
    "color": "colour",
    "colour_name": "colour",
    "dealer_name": "dealer",
    "salesman": "salesperson",
    "state_code": "state",
    "state_name": "state",
    "region_name": "region",
    "lob": "line_of_business",
    "product_name": "product",
    "agent_name": "agent",
    "channel_name": "channel",
    "branch_name": "branch",
}

# --- analyses -------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class AnalysisDef:
    id: str
    label: str
    group: str
    description: str
    requirement: str
    time: TimeRule = "optional"
    min_categories: int = 0
    max_categories: int = 3
    max_dimensions: int = 3
    additive_only: bool = False


ANALYSES: tuple[AnalysisDef, ...] = (
    AnalysisDef(
        "basic",
        "Standard",
        "Basics",
        "Totals for the metric, split by the dimensions you pick.",
        "Any metric; up to three dimensions.",
    ),
    AnalysisDef(
        "trend",
        "Trend",
        "Basics",
        "How the metric moves over time.",
        "A time dimension (Month, Quarter or Year).",
        time="required",
        max_categories=1,
        max_dimensions=2,
    ),
    AnalysisDef(
        "comparison",
        "Compare values",
        "Basics",
        "Two or more chosen values side by side, e.g. Tata vs Mahindra.",
        "One business dimension and at least two of its values in Filters.",
        min_categories=1,
        max_categories=1,
        max_dimensions=2,
    ),
    AnalysisDef(
        "top_n",
        "Top N",
        "Ranking",
        "The highest N values, e.g. top 5 models by revenue.",
        "One business dimension, no time dimension.",
        time="forbidden",
        min_categories=1,
        max_categories=1,
        max_dimensions=1,
    ),
    AnalysisDef(
        "bottom_n",
        "Bottom N",
        "Ranking",
        "The lowest N values, to spot under-performers.",
        "One business dimension, no time dimension.",
        time="forbidden",
        min_categories=1,
        max_categories=1,
        max_dimensions=1,
    ),
    AnalysisDef(
        "top_n_per_group",
        "Top N within group",
        "Ranking",
        "The top N inside each group, e.g. top 3 models within each brand.",
        "Two dimensions: the group first, then what to rank inside it.",
        min_categories=1,
        max_categories=2,
        max_dimensions=2,
    ),
    AnalysisDef(
        "ranking",
        "Rank",
        "Ranking",
        "A leaderboard with Rank, Dense Rank or Row Number. Add a second dimension to rank "
        "within each group.",
        "A business dimension to rank; optionally a group or time dimension.",
        min_categories=1,
        max_categories=2,
        max_dimensions=2,
    ),
    AnalysisDef(
        "contribution",
        "Share of total %",
        "Distribution",
        "Each value's share of the total: market share, revenue or category contribution.",
        "A business dimension; a total-type metric.",
        min_categories=1,
        max_categories=2,
        max_dimensions=2,
        additive_only=True,
    ),
    AnalysisDef(
        "running_total",
        "Running total",
        "Running",
        "The cumulative total over time, e.g. cumulative revenue this year.",
        "A time dimension; a total-type metric.",
        time="required",
        max_categories=1,
        max_dimensions=2,
        additive_only=True,
    ),
    AnalysisDef(
        "moving_average",
        "Moving average",
        "Moving",
        "Smooths the trend over the last 3, 6 or 12 periods.",
        "A time dimension.",
        time="required",
        max_categories=1,
        max_dimensions=2,
    ),
    AnalysisDef(
        "period_growth",
        "Period growth % (MoM / QoQ)",
        "Growth",
        "Change against the previous period at the chosen grain: MoM, QoQ or year on year.",
        "A time dimension.",
        time="required",
        max_categories=1,
        max_dimensions=2,
    ),
    AnalysisDef(
        "yoy_growth",
        "YoY growth %",
        "Growth",
        "Change against the same period last year.",
        "A time dimension.",
        time="required",
        max_categories=1,
        max_dimensions=2,
    ),
    AnalysisDef(
        "growth_contribution",
        "Growth contribution",
        "Growth",
        "Which values drove the change between the selected period and the one before it.",
        "One business dimension, no time dimension; a total-type metric.",
        time="forbidden",
        min_categories=1,
        max_categories=1,
        max_dimensions=1,
        additive_only=True,
    ),
    AnalysisDef(
        "actual_vs_target",
        "Actual vs Target",
        "Variance",
        "Actual against target with variance and achievement %.",
        "Revenue or Units Sold, split by Brand, Month, Quarter or Year.",
        max_categories=1,
        max_dimensions=2,
    ),
    AnalysisDef(
        "above_average",
        "Above average",
        "Variance",
        "Values that beat the average, with how far above it they are.",
        "A business dimension.",
        min_categories=1,
        max_categories=2,
        max_dimensions=2,
    ),
)
_ANALYSIS_BY_ID = {item.id: item for item in ANALYSES}
_LEGACY_ANALYSIS = {"breakdown": "basic", "variance": "above_average"}

TARGET_DIMENSIONS = frozenset({"make", *TIME_GRAINS})
TARGET_METRICS = {"revenue": "target_revenue", "units_sold": "target_units"}

# --- dates ----------------------------------------------------------------------

DATE_PRESETS: tuple[tuple[str, str], ...] = (
    ("last_7_days", "Last 7 days"),
    ("last_30_days", "Last 30 days"),
    ("last_3_months", "Last 3 months"),
    ("last_6_months", "Last 6 months"),
    ("last_12_months", "Last 12 months"),
    ("last_24_months", "Last 24 months"),
    ("this_month", "This month"),
    ("last_month", "Last month"),
    ("this_quarter", "This quarter"),
    ("last_quarter", "Last quarter"),
    ("ytd", "Year to date"),
    ("fytd", "Fiscal year to date"),
    ("last_year", "Last year"),
    ("custom", "Custom range"),
)
_DATE_PRESET_IDS = {preset for preset, _ in DATE_PRESETS}
# Presets saved by the first builder release.
LEGACY_DATE_PRESETS: dict[str, str | None] = {
    "last_7": "last_7_days",
    "last_30": "last_30_days",
    "this_year": "ytd",
    "today": "last_7_days",
    "yesterday": "last_7_days",
    "yoy": None,
    "mom": None,
    "qoq": None,
}
_ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


# --- resolved selection ------------------------------------------------------------


@dataclass(slots=True)
class Selection:
    """A spec resolved against the catalog: what the user picked, in catalog terms."""

    industry: Industry
    analysis: AnalysisDef
    metric: MetricDef | None
    metric_raw: str | None
    extra_metrics: list[MetricDef] = field(default_factory=list)
    dimensions: list[DimensionDef] = field(default_factory=list)
    unknown_dimensions: list[str] = field(default_factory=list)
    filters: list[tuple[ValueDomain | None, str, list[str]]] = field(default_factory=list)
    date_preset: str | None = None

    @property
    def time_dims(self) -> list[DimensionDef]:
        return [d for d in self.dimensions if d.time]

    @property
    def category_dims(self) -> list[DimensionDef]:
        return [d for d in self.dimensions if not d.time]


class Catalog:
    """Capabilities of one industry pack."""

    def __init__(self, industry: Industry, pack: Any | None) -> None:
        self.industry = industry
        self.pack = pack
        self.metrics = _METRICS[industry]
        self.dimensions = _DIMENSIONS[industry]
        self._metric_by_id = {m.id: m for m in self.metrics}
        self._dimension_by_id = {d.id: d for d in self.dimensions}
        self.domains = domains_for(industry, pack)
        self._compat: dict[tuple[str, str], bool] = {}

    # -- lookups --

    def metric(self, raw: str | None) -> MetricDef | None:
        if not raw:
            return None
        key = raw.strip().casefold().replace(" ", "_")
        key = _METRIC_ALIASES.get(key, key)
        if key in self._metric_by_id:
            return self._metric_by_id[key]
        for measure_id, measure in self._pack_measures().items():
            names = {
                measure_id.casefold(),
                str(getattr(measure, "display_name", "")).casefold().replace(" ", "_"),
                *(
                    str(s).casefold().replace(" ", "_")
                    for s in getattr(measure, "synonyms", []) or []
                ),
            }
            if key in names and measure_id in self._metric_by_id:
                return self._metric_by_id[measure_id]
        return None

    def metric_for_plan(self, plan_metric: str) -> MetricDef | None:
        return next((m for m in self.metrics if m.plan_metric == plan_metric and m.supported), None)

    def dimension(self, raw: str) -> DimensionDef | None:
        key = raw.strip().casefold().replace(" ", "_")
        key = _DIMENSION_ALIASES.get(key, key)
        return self._dimension_by_id.get(key)

    def metric_label(self, metric: MetricDef) -> str:
        measure = self._pack_measures().get(metric.id)
        label = getattr(measure, "display_name", None)
        return str(label) if label else metric.id.replace("_", " ").title()

    def domain(self, raw: str) -> ValueDomain | None:
        needle = raw.strip().casefold().replace("_", " ")
        for item in self.domains:
            leaf = item.column.casefold().replace("_", " ")
            if needle in {item.name.casefold(), item.label.casefold(), leaf}:
                return item
        dim = self.dimension(raw)
        return self.domain_for_dimension(dim.id) if dim else None

    def domain_for_dimension(self, dimension_id: str) -> ValueDomain | None:
        spec = self._dimension_spec(dimension_id)
        if spec is None or spec.expression:
            return None
        physical = self._physical(spec.table)
        return next(
            (d for d in self.domains if d.table == physical and d.column == spec.column), None
        )

    # -- compatibility --

    def dimension_fits(self, dimension_id: str, metric: MetricDef | None) -> bool:
        if metric is None or not metric.supported or dimension_id in TIME_GRAINS:
            return True
        spec = self._dimension_spec(dimension_id)
        if spec is None:
            return False
        return self._reachable(metric.fact, spec.table)

    def domain_fits(self, domain: ValueDomain, metric: MetricDef | None) -> bool:
        if metric is None or not metric.supported:
            return True
        logical = self._logical(domain.table)
        return logical is not None and self._reachable(metric.fact, logical)

    def _reachable(self, fact: str, table: str) -> bool:
        """Only many-to-one hops away from the fact; never fan out through another fact."""
        if fact == table:
            return True
        if table.startswith("fact_"):
            return False
        key = (fact, table)
        if key not in self._compat:
            relationships = list(
                getattr(getattr(self.pack, "model", None), "relationships", []) or []
            )
            frontier, seen = [fact], {fact}
            found = False
            while frontier and not found:
                node = frontier.pop()
                for rel in relationships:
                    if rel.from_table != node or rel.to_table in seen:
                        continue
                    if rel.to_table == table:
                        found = True
                        break
                    seen.add(rel.to_table)
                    frontier.append(rel.to_table)
            self._compat[key] = found
        return self._compat[key]

    # -- resolution --

    def resolve(self, spec: AnalyticsSpec) -> Selection:
        analysis_id = _LEGACY_ANALYSIS.get(spec.analysis, spec.analysis)
        selection = Selection(
            industry=self.industry,
            analysis=_ANALYSIS_BY_ID.get(analysis_id, _ANALYSIS_BY_ID["basic"]),
            metric=self.metric(spec.metrics[0]) if spec.metrics else None,
            metric_raw=spec.metrics[0] if spec.metrics else None,
        )
        for raw in spec.metrics[1:]:
            extra = self.metric(raw)
            if extra is not None and extra.supported and extra != selection.metric:
                selection.extra_metrics.append(extra)
        grain = (spec.time_grain or "").casefold()
        for raw in spec.dimensions:
            dim = self.dimension(raw)
            if dim is None:
                selection.unknown_dimensions.append(raw)
                continue
            if dim.time and grain in TIME_GRAINS:
                dim = self._dimension_by_id[grain]
            if dim not in selection.dimensions:
                selection.dimensions.append(dim)
        for filt in spec.filters:
            values = list(dict.fromkeys(v for v in filt.values if str(v).strip()))
            if values:
                selection.filters.append((self.domain(filt.domain), filt.domain, values))
        preset = spec.date_preset
        if preset in LEGACY_DATE_PRESETS:
            preset = LEGACY_DATE_PRESETS[preset]
        selection.date_preset = preset or None
        return selection

    # -- helpers --

    def _pack_measures(self) -> dict[str, Any]:
        model = getattr(self.pack, "model", None)
        return dict(getattr(model, "measures", {}) or {})

    def _dimension_spec(self, dimension_id: str) -> DimensionSpec | None:
        catalog = (
            _AUTOMOTIVE_DIMENSIONS
            if self.industry is Industry.AUTOMOTIVE
            else _INSURANCE_DIMENSIONS
        )
        return catalog.get(dimension_id)

    def _tables(self) -> dict[str, Any]:
        model = getattr(self.pack, "model", None)
        return dict(getattr(model, "tables", {}) or {})

    def _physical(self, logical: str) -> str:
        return str(getattr(self._tables().get(logical), "physical_name", logical))

    def _logical(self, physical: str) -> str | None:
        for logical, table in self._tables().items():
            if str(getattr(table, "physical_name", logical)) == physical:
                return logical
        return None

    # -- capabilities --

    def capabilities(self, *, data_as_of: str | None = None) -> AnalyticsCapabilities:
        measures = self._pack_measures()
        return AnalyticsCapabilities(
            metrics=[
                MetricCapability(
                    id=m.id,
                    label=self.metric_label(m),
                    description=getattr(measures.get(m.id), "description", None),
                    format=m.format,
                    additive=m.additive,
                    supported=m.supported,
                    reason=(m.reason or "").format(label=self.metric_label(m)) or None,
                )
                for m in self.metrics
            ],
            dimensions=[
                DimensionCapability(
                    id=d.id,
                    label=d.label,
                    group=d.group,
                    time=d.time,
                    filter_domain=(dom.name if (dom := self.domain_for_dimension(d.id)) else None),
                )
                for d in self.dimensions
            ],
            analyses=[
                AnalysisCapability(
                    id=a.id,
                    label=a.label,
                    group=a.group,
                    description=a.description,
                    requirement=a.requirement,
                )
                for a in ANALYSES
                if a.id != "actual_vs_target" or self.industry is Industry.AUTOMOTIVE
            ],
            filter_domains=[FilterDomainCapability(id=d.name, label=d.label) for d in self.domains],
            date_presets=[DatePresetCapability(id=i, label=label) for i, label in DATE_PRESETS],
            data_as_of=data_as_of,
        )

    # -- inspection --

    def inspect(self, spec: AnalyticsSpec) -> AnalyticsInspection:
        selection = self.resolve(spec)
        issues = self._issues(selection, spec)
        return AnalyticsInspection(
            valid=not any(issue.severity == "error" for issue in issues),
            issues=issues,
            analyses=self._analysis_options(selection),
            metrics=self._metric_options(selection),
            dimensions=self._dimension_options(selection),
            suggestions=self.suggestions(spec, selection),
        )

    def _issues(self, sel: Selection, spec: AnalyticsSpec) -> list[AnalyticsIssue]:
        issues: list[AnalyticsIssue] = []
        metric = sel.metric
        if sel.metric_raw is None:
            issues.append(
                AnalyticsIssue(
                    code="metric_required",
                    message="Pick a metric to start, for example "
                    + " or ".join(self.metric_label(m) for m in self._headline_metrics()[:2])
                    + ".",
                    fixes=[_fix_metric(self, m) for m in self._headline_metrics()[:3]],
                )
            )
        elif metric is None and (as_dim := self.dimension(sel.metric_raw)) is not None:
            fixes = []
            if as_dim not in sel.dimensions:
                fixes.append(
                    AnalyticsFix(
                        label=f"Use {as_dim.label} as a dimension",
                        action="add_dimension",
                        value=as_dim.id,
                    )
                )
            counted = "active_salespeople" if as_dim.id == "salesperson" else None
            candidates = [self._metric_by_id[counted]] if counted in self._metric_by_id else []
            candidates += [m for m in self._headline_metrics()[:2] if m not in candidates]
            fixes += [_fix_metric(self, m) for m in candidates]
            issues.append(
                AnalyticsIssue(
                    code="metric_is_dimension",
                    message=f"{as_dim.label} is a dimension, not a metric. Measure something such as "
                    f"{self.metric_label(candidates[0])} and split it by {as_dim.label}.",
                    fixes=fixes,
                )
            )
        elif metric is None:
            issues.append(
                AnalyticsIssue(
                    code="metric_unknown",
                    message=f"\u201c{sel.metric_raw}\u201d isn't a metric in this data. Pick one "
                    "from the Metrics list.",
                    fixes=[_fix_metric(self, m) for m in self._headline_metrics()[:3]],
                )
            )
        elif not metric.supported:
            fixes = [_fix_metric(self, m) for m in self._headline_metrics()[:2]]
            if metric.kind == "target":
                fixes.append(
                    AnalyticsFix(
                        label="Use Actual vs Target",
                        action="set_analysis",
                        value="actual_vs_target",
                    )
                )
            issues.append(
                AnalyticsIssue(
                    code="metric_unsupported",
                    message=(metric.reason or "").format(label=self.metric_label(metric)),
                    fixes=fixes,
                )
            )

        for raw in sel.unknown_dimensions:
            issues.append(
                AnalyticsIssue(
                    code="dimension_unknown",
                    message=f"\u201c{raw}\u201d can't be used as a dimension here.",
                    fixes=[
                        AnalyticsFix(label=f"Remove {raw}", action="remove_dimension", value=raw)
                    ],
                )
            )
        if metric is not None and metric.supported:
            for dim in sel.dimensions:
                if not self.dimension_fits(dim.id, metric):
                    alternatives = [
                        m for m in self.metrics if m.supported and self.dimension_fits(dim.id, m)
                    ][:2]
                    issues.append(
                        AnalyticsIssue(
                            code="dimension_incompatible",
                            message=f"{dim.label} isn't recorded with {self.metric_label(metric)}, "
                            "so they can't be combined.",
                            fixes=[
                                AnalyticsFix(
                                    label=f"Remove {dim.label}",
                                    action="remove_dimension",
                                    value=dim.id,
                                ),
                                *(_fix_metric(self, m) for m in alternatives),
                            ],
                        )
                    )
        if len(sel.time_dims) > 1:
            issues.append(
                AnalyticsIssue(
                    code="time_grain_conflict",
                    message="Use one time grain at a time: Month, Quarter or Year.",
                    fixes=[
                        AnalyticsFix(
                            label=f"Remove {d.label}", action="remove_dimension", value=d.id
                        )
                        for d in sel.time_dims[1:]
                    ],
                )
            )

        if metric is None or metric.supported:
            problem = self._analysis_problem(sel.analysis, sel, include_filters=True)
            if problem is not None:
                issues.append(problem)

        for domain, raw, _values in sel.filters:
            if domain is None:
                issues.append(
                    AnalyticsIssue(
                        code="filter_unknown",
                        message=f"\u201c{raw}\u201d can't be used as a filter.",
                        fixes=[
                            AnalyticsFix(
                                label=f"Remove {raw} filter", action="remove_filter", value=raw
                            )
                        ],
                    )
                )
            elif metric is not None and metric.supported and not self.domain_fits(domain, metric):
                issues.append(
                    AnalyticsIssue(
                        code="filter_incompatible",
                        message=f"{domain.label} isn't recorded with {self.metric_label(metric)}, "
                        "so that filter can't apply.",
                        fixes=[
                            AnalyticsFix(
                                label=f"Remove {domain.label} filter",
                                action="remove_filter",
                                value=raw,
                            )
                        ],
                    )
                )

        issues.extend(_date_issues(sel.date_preset, spec.date_from, spec.date_to))

        if sel.extra_metrics and sel.analysis.id not in {"basic", "trend", "comparison"}:
            issues.append(
                AnalyticsIssue(
                    code="extra_metrics_ignored",
                    severity="warning",
                    message=f"{sel.analysis.label} uses one metric; "
                    f"{', '.join(self.metric_label(m) for m in sel.extra_metrics)} will be left out.",
                )
            )
        elif any(m.fact != (metric.fact if metric else "") for m in sel.extra_metrics):
            issues.append(
                AnalyticsIssue(
                    code="extra_metrics_incompatible",
                    severity="warning",
                    message="Metrics from claims and premium data can't share one table; "
                    "only metrics recorded with the first one are shown.",
                )
            )
        return issues

    def _analysis_problem(
        self, analysis: AnalysisDef, sel: Selection, *, include_filters: bool
    ) -> AnalyticsIssue | None:
        """The first reason this analysis can't run on the selection, or None."""
        metric = sel.metric
        time_dims, cats = sel.time_dims, sel.category_dims
        label = analysis.label

        if analysis.id == "actual_vs_target":
            return self._target_problem(sel, include_filters=include_filters)

        if analysis.time == "required" and not time_dims:
            return AnalyticsIssue(
                code="time_required",
                message=f"{label} needs a time dimension so it knows the order of periods. "
                "Add Month, Quarter or Year.",
                fixes=[_fix_add(d) for d in self.dimensions if d.time],
            )
        if len(cats) < analysis.min_categories:
            return AnalyticsIssue(
                code="category_required",
                message=f"{label} needs a business dimension to "
                + ("rank" if analysis.group == "Ranking" else "split by")
                + f", such as {self._category_examples(metric)}.",
                fixes=[_fix_add(d) for d in self._headline_categories(metric)[:3]],
            )
        if analysis.time == "forbidden" and time_dims:
            time = time_dims[0]
            fixes = [
                AnalyticsFix(label=f"Remove {time.label}", action="remove_dimension", value=time.id)
            ]
            if analysis.id in {"top_n", "bottom_n"}:
                message = (
                    f"{label} ranks across the whole period, so it can't also split by "
                    f"{time.label}. Remove {time.label}, or use Top N within group to rank inside "
                    f"each {time.label.lower()}."
                )
                fixes.append(
                    AnalyticsFix(
                        label="Use Top N within group",
                        action="set_analysis",
                        value="top_n_per_group",
                    )
                )
            else:
                message = (
                    f"{label} compares the selected period with the one before it, so it doesn't "
                    f"need {time.label}. Use the date filter to choose the period."
                )
            return AnalyticsIssue(code="time_not_allowed", message=message, fixes=fixes)
        if analysis.id == "top_n_per_group" and len(sel.dimensions) != 2:
            examples = self._group_pair()
            return AnalyticsIssue(
                code="group_pair_required",
                message="Top N within group needs two dimensions: the group first (for example "
                f"{examples[0].label}), then what to rank inside it (for example {examples[1].label}).",
                fixes=[_fix_add(d) for d in examples if d not in sel.dimensions],
            )
        if len(cats) > analysis.max_categories or len(sel.dimensions) > analysis.max_dimensions:
            keep = analysis.max_dimensions
            extra = (
                sel.dimensions[keep:]
                if len(sel.dimensions) > keep
                else cats[analysis.max_categories :]
            )
            limit_text = f"{analysis.max_dimensions} dimension" + (
                "s" if analysis.max_dimensions > 1 else ""
            )
            return AnalyticsIssue(
                code="too_many_dimensions",
                message=f"{label} works with up to {limit_text}"
                + (
                    " including time"
                    if analysis.time != "forbidden" and analysis.max_dimensions > 1
                    else ""
                )
                + f". Remove {', '.join(d.label for d in extra)}.",
                fixes=[
                    AnalyticsFix(label=f"Remove {d.label}", action="remove_dimension", value=d.id)
                    for d in extra
                ],
            )
        if (
            analysis.additive_only
            and metric is not None
            and metric.supported
            and not metric.additive
        ):
            alternatives = [m for m in self._headline_metrics() if m.additive][:2]
            fixes = [_fix_metric(self, m) for m in alternatives]
            if time_dims:
                fixes.insert(
                    0,
                    AnalyticsFix(
                        label="Use Moving average", action="set_analysis", value="moving_average"
                    ),
                )
            return AnalyticsIssue(
                code="metric_not_additive",
                message=f"{label} adds values together, which isn't meaningful for "
                f"{self.metric_label(metric)} because it's {metric.nature}.",
                fixes=fixes,
            )
        if analysis.id == "comparison":
            dim = cats[0]
            domain = self.domain_for_dimension(dim.id)
            if domain is None:
                return AnalyticsIssue(
                    code="compare_not_filterable",
                    message=f"{dim.label} values can't be picked individually yet. Compare by "
                    f"{self._filterable_examples()} instead.",
                    fixes=[_fix_add(d) for d in self._filterable_dimensions()[:2]],
                )
            if include_filters:
                chosen = next(
                    (
                        values
                        for dom, _raw, values in sel.filters
                        if dom is not None and dom == domain
                    ),
                    [],
                )
                if len(chosen) < 2:
                    plural = _plural(dim.label.lower())
                    return AnalyticsIssue(
                        code="compare_values_required",
                        message=f"Compare values needs at least two {plural}. Open Filters and "
                        f"choose the {plural} to compare.",
                        fixes=[
                            AnalyticsFix(
                                label=f"Choose {plural}", action="open_filters", value=domain.name
                            )
                        ],
                    )
        return None

    def _target_problem(self, sel: Selection, *, include_filters: bool) -> AnalyticsIssue | None:
        label = "Actual vs Target"
        if self.industry is not Industry.AUTOMOTIVE:
            return AnalyticsIssue(
                code="targets_unavailable", message="Targets aren't recorded for insurance data."
            )
        metric = sel.metric
        if metric is None or metric.id not in TARGET_METRICS:
            return AnalyticsIssue(
                code="target_metric",
                message=f"{label} works with Revenue or Units Sold, the two metrics that have targets.",
                fixes=[_fix_metric(self, self._metric_by_id[m]) for m in TARGET_METRICS],
            )
        outside = [d for d in sel.dimensions if d.id not in TARGET_DIMENSIONS]
        if outside:
            return AnalyticsIssue(
                code="target_dimension",
                message="Targets are set by brand and month, so Actual vs Target can split by Brand, "
                f"Month, Quarter or Year only. Remove {', '.join(d.label for d in outside)}.",
                fixes=[
                    AnalyticsFix(label=f"Remove {d.label}", action="remove_dimension", value=d.id)
                    for d in outside
                ],
            )
        if not sel.dimensions:
            return AnalyticsIssue(
                code="target_dimension_required",
                message=f"{label} needs Brand or a time dimension to compare against targets.",
                fixes=[
                    _fix_add(self._dimension_by_id["make"]),
                    _fix_add(self._dimension_by_id["month"]),
                ],
            )
        if len(sel.time_dims) > 1 or len(sel.dimensions) > 2:
            return AnalyticsIssue(
                code="too_many_dimensions",
                message=f"{label} works with Brand and one time grain at most.",
            )
        if include_filters:
            for domain, raw, _values in sel.filters:
                if domain is not None and domain.column != "make":
                    return AnalyticsIssue(
                        code="target_filter",
                        message=f"Targets are set by brand only, so a {domain.label} filter would compare "
                        f"filtered sales with unfiltered targets. Remove the {domain.label} filter.",
                        fixes=[
                            AnalyticsFix(
                                label=f"Remove {domain.label} filter",
                                action="remove_filter",
                                value=raw,
                            )
                        ],
                    )
        return None

    def _analysis_options(self, sel: Selection) -> list[AnalyticsOption]:
        options: list[AnalyticsOption] = []
        for analysis in ANALYSES:
            if analysis.id == "actual_vs_target" and self.industry is not Industry.AUTOMOTIVE:
                continue
            problem = None
            if sel.metric is not None and sel.metric.supported:
                problem = self._analysis_problem(analysis, sel, include_filters=False)
            options.append(
                AnalyticsOption(
                    id=analysis.id,
                    label=analysis.label,
                    available=problem is None,
                    reason=problem.message if problem else None,
                )
            )
        return options

    def _metric_options(self, sel: Selection) -> list[AnalyticsOption]:
        options: list[AnalyticsOption] = []
        for metric in self.metrics:
            reason: str | None = None
            if not metric.supported:
                reason = (metric.reason or "").format(label=self.metric_label(metric))
            else:
                misfit = next(
                    (d for d in sel.dimensions if not self.dimension_fits(d.id, metric)), None
                )
                if misfit is not None:
                    reason = f"{misfit.label} isn't recorded with {self.metric_label(metric)}."
                elif sel.analysis.additive_only and not metric.additive:
                    reason = (
                        f"{sel.analysis.label} isn't meaningful for {self.metric_label(metric)} "
                        f"because it's {metric.nature}."
                    )
                elif sel.analysis.id == "actual_vs_target" and metric.id not in TARGET_METRICS:
                    reason = "Targets exist for Revenue and Units Sold only."
            options.append(
                AnalyticsOption(
                    id=metric.id,
                    label=self.metric_label(metric),
                    available=reason is None,
                    reason=reason,
                )
            )
        return options

    def _dimension_options(self, sel: Selection) -> list[AnalyticsOption]:
        options: list[AnalyticsOption] = []
        for dim in self.dimensions:
            reason: str | None = None
            if sel.metric is not None and not self.dimension_fits(dim.id, sel.metric):
                reason = f"{dim.label} isn't recorded with {self.metric_label(sel.metric)}."
            elif sel.analysis.id == "actual_vs_target" and dim.id not in TARGET_DIMENSIONS:
                reason = "Targets are set by brand and month only."
            elif sel.analysis.time == "forbidden" and dim.time:
                reason = f"{sel.analysis.label} doesn't use a time dimension; use the date filter instead."
            options.append(
                AnalyticsOption(id=dim.id, label=dim.label, available=reason is None, reason=reason)
            )
        return options

    # -- suggestions --

    def suggestions(
        self, spec: AnalyticsSpec, sel: Selection | None = None, *, limit: int = 6
    ) -> list[AnalyticsSuggestion]:
        """Ready-to-run analyses that make sense for the current metric and dimensions."""
        sel = sel or self.resolve(spec)
        metric = (
            sel.metric
            if sel.metric is not None and sel.metric.supported
            else self._headline_metrics()[0]
        )
        m_label = self.metric_label(metric)
        base = AnalyticsSpec(
            metrics=[metric.id],
            filters=list(spec.filters),
            date_preset=spec.date_preset,
            date_from=spec.date_from,
            date_to=spec.date_to,
        )
        cats = [d.id for d in sel.category_dims]
        time = sel.time_dims[0].id if sel.time_dims else "month"
        candidates: list[tuple[str, str, AnalyticsSpec]] = []

        def add(label: str, description: str, **changes: Any) -> None:
            candidates.append((label, description, base.model_copy(update=changes)))

        auto = self.industry is Industry.AUTOMOTIVE
        if "dealer" in cats:
            add(
                "Dealer ranking",
                f"Rank dealers by {m_label.lower()}",
                analysis="ranking",
                dimensions=["dealer"],
            )
            add(
                "Top 10 dealers",
                f"Highest {m_label.lower()} dealers",
                analysis="top_n",
                dimensions=["dealer"],
                limit=10,
            )
            add(
                "Dealer growth drivers",
                "Which dealers drove the change",
                analysis="growth_contribution",
                dimensions=["dealer"],
            )
        if "salesperson" in cats:
            add(
                "Salesperson ranking",
                f"Rank salespeople by {m_label.lower()}",
                analysis="ranking",
                dimensions=["salesperson"],
            )
            add(
                f"{m_label} contribution by salesperson",
                "Each salesperson's share of the total",
                analysis="contribution",
                dimensions=["salesperson"],
            )
            add(
                "Top 10 salespeople",
                f"Highest {m_label.lower()} salespeople",
                analysis="top_n",
                dimensions=["salesperson"],
                limit=10,
            )
        if sel.time_dims and not cats:
            add(f"{m_label} trend", "How it moves over time", analysis="trend", dimensions=[time])
            add(
                "3-period moving average",
                "Smoothed trend",
                analysis="moving_average",
                dimensions=[time],
                window=3,
            )
            add(
                "YoY growth",
                "Against the same period last year",
                analysis="yoy_growth",
                dimensions=[time],
            )
            add(
                "Running total",
                "Cumulative over the period",
                analysis="running_total",
                dimensions=[time],
            )
        if cats and not sel.time_dims:
            first = self._dimension_by_id[cats[0]]
            add(
                f"{first.label} trend",
                f"{m_label} by month for each {first.label.lower()}",
                analysis="trend",
                dimensions=["month", first.id],
            )
            add(
                f"{first.label} share",
                f"Each {first.label.lower()}'s share of {m_label.lower()}",
                analysis="contribution",
                dimensions=[first.id],
            )
            add(
                f"{first.label} growth drivers",
                "Who drove the change vs the previous period",
                analysis="growth_contribution",
                dimensions=[first.id],
            )
        if auto:
            add(f"{m_label} trend", "Monthly trend", analysis="trend", dimensions=["month"])
            add(
                "YoY growth",
                "Against the same month last year",
                analysis="yoy_growth",
                dimensions=["month"],
            )
            add(
                "Market share by brand",
                "Each brand's share of the total",
                analysis="contribution",
                dimensions=["make"],
            )
            add(
                "Top regions",
                f"Highest {m_label.lower()} regions",
                analysis="top_n",
                dimensions=["region"],
                limit=10,
            )
            add(
                "Top models",
                f"Highest {m_label.lower()} models",
                analysis="top_n",
                dimensions=["model"],
                limit=10,
            )
            add(
                "Top 3 models within each brand",
                "Best sellers inside every brand",
                analysis="top_n_per_group",
                dimensions=["make", "model"],
                limit=3,
            )
            if metric.id in TARGET_METRICS:
                add(
                    "Target achievement by brand",
                    "Actual vs target with achievement %",
                    analysis="actual_vs_target",
                    dimensions=["make"],
                )
        else:
            add(f"{m_label} trend", "Monthly trend", analysis="trend", dimensions=["month"])
            add(
                "YoY growth",
                "Against the same month last year",
                analysis="yoy_growth",
                dimensions=["month"],
            )
            add(
                "Share by line of business",
                "Each line's share of the total",
                analysis="contribution",
                dimensions=["line_of_business"],
            )
            add(
                "Top products",
                f"Highest {m_label.lower()} products",
                analysis="top_n",
                dimensions=["product"],
                limit=10,
            )
            add(
                "Top regions",
                f"Highest {m_label.lower()} regions",
                analysis="top_n",
                dimensions=["region"],
                limit=10,
            )

        current = (sel.analysis.id, tuple(d.id for d in sel.dimensions))
        seen: set[tuple[str, tuple[str, ...]]] = {current}
        labels: set[str] = set()
        picked: list[AnalyticsSuggestion] = []
        for label, description, candidate in candidates:
            key = (candidate.analysis, tuple(candidate.dimensions))
            if key in seen or label in labels:
                continue
            seen.add(key)
            labels.add(label)
            resolved = self.resolve(candidate)
            if any(i.severity == "error" for i in self._issues(resolved, candidate)):
                continue
            picked.append(AnalyticsSuggestion(label=label, description=description, spec=candidate))
            if len(picked) >= limit:
                break
        return picked

    # -- examples --

    def _headline_metrics(self) -> list[MetricDef]:
        return [m for m in self.metrics if m.supported]

    def _headline_categories(self, metric: MetricDef | None) -> list[DimensionDef]:
        preferred = (
            ("model", "dealer", "region", "make", "salesperson")
            if self.industry is Industry.AUTOMOTIVE
            else ("product", "agent", "region", "line_of_business", "channel")
        )
        dims = [self._dimension_by_id[d] for d in preferred if d in self._dimension_by_id]
        return [d for d in dims if self.dimension_fits(d.id, metric)]

    def _category_examples(self, metric: MetricDef | None) -> str:
        names = [d.label for d in self._headline_categories(metric)[:3]]
        return (
            ", ".join(names[:-1]) + f" or {names[-1]}"
            if len(names) > 1
            else (names[0] if names else "Region")
        )

    def _group_pair(self) -> tuple[DimensionDef, DimensionDef]:
        if self.industry is Industry.AUTOMOTIVE:
            return self._dimension_by_id["make"], self._dimension_by_id["model"]
        return self._dimension_by_id["line_of_business"], self._dimension_by_id["product"]

    def _filterable_dimensions(self) -> list[DimensionDef]:
        return [
            d for d in self.dimensions if not d.time and self.domain_for_dimension(d.id) is not None
        ]

    def _filterable_examples(self) -> str:
        names = [d.label for d in self._filterable_dimensions()[:3]]
        return ", ".join(names[:-1]) + f" or {names[-1]}" if len(names) > 1 else "Brand"


def _fix_add(dim: DimensionDef) -> AnalyticsFix:
    return AnalyticsFix(label=f"Add {dim.label}", action="add_dimension", value=dim.id)


def _fix_metric(catalog: Catalog, metric: MetricDef) -> AnalyticsFix:
    return AnalyticsFix(
        label=f"Use {catalog.metric_label(metric)}", action="set_metric", value=metric.id
    )


def _plural(word: str) -> str:
    if word.endswith("y") and not word.endswith(("ay", "ey", "oy", "uy")):
        return word[:-1] + "ies"
    if word.endswith(("s", "x", "ch", "sh")):
        return word + "es"
    return word + "s"


def _date_issues(
    preset: str | None, date_from: str | None, date_to: str | None
) -> list[AnalyticsIssue]:
    if not preset:
        return []
    clear = AnalyticsFix(label="Clear date filter", action="clear_date")
    if preset not in _DATE_PRESET_IDS:
        return [
            AnalyticsIssue(
                code="date_unknown", message="That date range isn't recognised.", fixes=[clear]
            )
        ]
    if preset != "custom":
        return []
    start, end = parse_iso(date_from), parse_iso(date_to)
    if start is None or end is None:
        return [
            AnalyticsIssue(
                code="date_incomplete",
                message="Choose both a start and an end date.",
                fixes=[clear],
            )
        ]
    if end < start:
        return [
            AnalyticsIssue(
                code="date_order", message="The end date is before the start date.", fixes=[clear]
            )
        ]
    return []


def parse_iso(value: str | None) -> date | None:
    if not value or not _ISO_DATE.match(value.strip()):
        return None
    try:
        return date.fromisoformat(value.strip())
    except ValueError:
        return None


def normalized_analysis(spec: AnalyticsSpec) -> str:
    return _LEGACY_ANALYSIS.get(spec.analysis, spec.analysis)


def with_analysis(spec: AnalyticsSpec, analysis: str) -> AnalyticsSpec:
    return spec.model_copy(update={"analysis": analysis})


def first_error(issues: Iterable[AnalyticsIssue]) -> AnalyticsIssue | None:
    return next((issue for issue in issues if issue.severity == "error"), None)


__all__ = [
    "ANALYSES",
    "TARGET_METRICS",
    "TIME_GRAINS",
    "Catalog",
    "MetricDef",
    "Selection",
    "first_error",
    "normalized_analysis",
    "parse_iso",
    "with_analysis",
]
