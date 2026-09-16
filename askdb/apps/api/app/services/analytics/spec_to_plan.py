"""Map Analytics Builder business specs onto QuestionPlan + compiler keys."""

from __future__ import annotations

from typing import Any, Literal

from app.core.config import Industry
from app.core.exceptions import NqlError
from app.schemas.analytics import AnalyticsAnalysisKind, AnalyticsSpec
from app.services.chat.question_understanding import (
    AnalysisKind,
    EntityKind,
    ExtractedFilter,
    IntentKind,
    MetricKind,
    QuestionPlan,
)

# Pack measure id → QuestionPlan MetricKind
_MEASURE_TO_METRIC: dict[str, MetricKind] = {
    "revenue": "revenue",
    "orders": "orders",
    "units_sold": "units",
    "units": "units",
    "average_selling_price": "revenue",
    "active_salespeople": "orders",
    "target_units": "units",
    "target_revenue": "revenue",
    "premium": "premium",
    "written_premium": "premium",
    "earned_premium": "earned_premium",
    "claims_amount": "claims_incurred",
    "claims_incurred": "claims_incurred",
    "claim_count": "claim_count",
    "severity": "severity",
    "average_claim_severity": "severity",
    "approval_rate": "approval_rate",
    "renewal_rate": "renewal_rate",
    "loss_ratio": "loss_ratio",
    "frequency": "frequency",
}

# Pack dimension key / attribute / display → compiler dimension key
_DIMENSION_ALIASES: dict[str, str] = {
    "date": "month",
    "month": "month",
    "quarter": "quarter",
    "year": "year",
    "region": "region",
    "city": "city",
    "state": "state",
    "state_code": "state",
    "dealer": "dealer",
    "dealer_name": "dealer",
    "salesperson": "salesperson",
    "salesman": "salesperson",
    "car": "car_type",
    "vehicle": "car_type",
    "car_type": "car_type",
    "vehicle_type": "car_type",
    "make": "make",
    "brand": "make",
    "model": "model",
    "colour": "colour",
    "color": "colour",
    "colour_name": "colour",
    "product": "product",
    "product_family": "product_family",
    "line_of_business": "line_of_business",
    "lob": "line_of_business",
    "channel": "channel",
    "branch": "branch",
    "claim_status": "claim_status",
    "policy_type": "product",
    "policy": "product",
}

_ANALYSIS_MAP: dict[AnalyticsAnalysisKind, AnalysisKind] = {
    "basic": "basic",
    "breakdown": "breakdown",
    "ranking": "ranking",
    "top_n": "ranking",
    "bottom_n": "ranking",
    "contribution": "contribution",
    "running_total": "running_total",
    "moving_average": "moving_average",
    "period_growth": "period_growth",
    "trend": "basic",
    "variance": "above_average",
}

_TIME_DIMS = {"month", "quarter", "year"}


class AnalyticsSpecError(NqlError):
    status_code = 400
    code = "analytics_spec_invalid"
    message = "The analytics specification could not be resolved against the semantic layer."


def map_measure_to_metric(measure_id: str, pack: Any | None = None) -> MetricKind:
    key = measure_id.strip().casefold().replace(" ", "_")
    if key in _MEASURE_TO_METRIC:
        return _MEASURE_TO_METRIC[key]
    model = getattr(pack, "model", None) if pack is not None else None
    measures = getattr(model, "measures", {}) or {}
    for mid, measure in measures.items():
        synonyms = [str(s).casefold() for s in getattr(measure, "synonyms", []) or []]
        display = str(getattr(measure, "display_name", mid)).casefold()
        if key in {mid.casefold(), display, *synonyms}:
            mapped = _MEASURE_TO_METRIC.get(mid.casefold())
            if mapped:
                return mapped
    raise AnalyticsSpecError(
        f"Measure '{measure_id}' is not supported by the analytical compiler yet.",
        details={"measure": measure_id},
    )


def map_dimension_key(raw: str, pack: Any | None = None) -> str:
    key = raw.strip().casefold().replace(" ", "_")
    if key in _DIMENSION_ALIASES:
        return _DIMENSION_ALIASES[key]
    model = getattr(pack, "model", None) if pack is not None else None
    dimensions = getattr(model, "dimensions", {}) or {}
    for did, dim in dimensions.items():
        display = str(getattr(dim, "display_name", did)).casefold()
        synonyms = [str(s).casefold() for s in getattr(dim, "synonyms", []) or []]
        attrs = [str(a).casefold() for a in getattr(dim, "attributes", []) or []]
        source_col = str(getattr(dim, "source_column", "") or "").casefold()
        candidates = {did.casefold(), display.replace(" ", "_"), *synonyms, *attrs, source_col}
        if key not in candidates and display not in {key, key.replace("_", " ")}:
            continue
        if key in attrs and key in _DIMENSION_ALIASES:
            return _DIMENSION_ALIASES[key]
        if source_col and source_col in _DIMENSION_ALIASES:
            return _DIMENSION_ALIASES[source_col]
        if did.casefold() in _DIMENSION_ALIASES:
            return _DIMENSION_ALIASES[did.casefold()]
        display_key = display.replace(" ", "_")
        if display_key in _DIMENSION_ALIASES:
            return _DIMENSION_ALIASES[display_key]
    raise AnalyticsSpecError(
        f"Dimension '{raw}' could not be mapped to a governed grain.",
        details={"dimension": raw},
    )


def _domain_column(domain: str, pack: Any | None, industry: Industry) -> str:
    from app.services.chat.value_dictionary import domains_for

    domains = domains_for(industry, pack)
    needle = domain.strip().casefold()
    for item in domains:
        col_leaf = item.column.split(".")[-1].casefold()
        if needle in {
            item.name.casefold(),
            item.label.casefold(),
            col_leaf,
            item.qualified_column.casefold(),
            needle.replace(" ", "_"),
        }:
            return item.qualified_column
        if needle.replace(" ", "_") == item.name.casefold().replace(" ", "_"):
            return item.qualified_column
        if needle.replace(" ", "_") == col_leaf:
            return item.qualified_column
    mapped = _DIMENSION_ALIASES.get(needle) or _DIMENSION_ALIASES.get(needle.replace(" ", "_"))
    if mapped:
        for item in domains:
            leaf = item.column.split(".")[-1]
            if leaf == mapped or leaf.endswith(mapped):
                return item.qualified_column
    raise AnalyticsSpecError(
        f"Filter domain '{domain}' is not in the value dictionary.",
        details={"domain": domain},
    )


def spec_to_plan(spec: AnalyticsSpec, industry: Industry, pack: Any | None) -> QuestionPlan:
    if not spec.metrics:
        raise AnalyticsSpecError("Select at least one metric to run an analysis.")

    primary = map_measure_to_metric(spec.metrics[0], pack)
    dimensions = [map_dimension_key(d, pack) for d in spec.dimensions]

    if spec.time_grain and spec.time_grain.casefold() in _TIME_DIMS:
        grain = spec.time_grain.casefold()
        dimensions = [grain if d in _TIME_DIMS else d for d in dimensions]
        if not any(d in _TIME_DIMS for d in dimensions):
            dimensions.insert(0, grain)

    analysis = _ANALYSIS_MAP.get(spec.analysis, "basic")
    if spec.analysis == "trend" and not any(d in _TIME_DIMS for d in dimensions):
        dimensions.append(spec.time_grain.casefold() if spec.time_grain else "month")
        analysis = "basic"

    order: Literal["asc", "desc"] = spec.order_direction
    if spec.analysis == "bottom_n":
        order = "asc"
    elif spec.analysis in {"top_n", "ranking"}:
        order = "desc"

    intent: IntentKind = "aggregation"
    if analysis == "ranking" or spec.analysis in {"top_n", "bottom_n"}:
        intent = "ranking"
    elif spec.analysis == "trend" or any(d in _TIME_DIMS for d in dimensions):
        intent = "trend"

    filters: list[ExtractedFilter] = []
    for filt in spec.filters:
        if not filt.values:
            continue
        column = _domain_column(filt.domain, pack, industry)
        for value in filt.values:
            filters.append(
                ExtractedFilter(
                    column=column,
                    operator=filt.operator or "=",
                    value=value,
                    label=f"{filt.domain} = {value}",
                    source="analytics_builder",
                )
            )

    entity: EntityKind = "metric_only"
    if "dealer" in dimensions:
        entity = "dealer"
    elif "salesperson" in dimensions:
        entity = "salesperson"
    elif any(d in {"car_type", "make", "model"} for d in dimensions):
        entity = "vehicle"
    elif "region" in dimensions or "city" in dimensions:
        entity = "region"

    return QuestionPlan(
        industry=industry,
        intent=intent,
        entity=entity,
        metric=primary,
        filters=filters,
        limit=spec.limit,
        order_direction=order,
        aggregation="sum",
        dimensions=dimensions,
        time_grain=spec.time_grain,
        analysis=analysis,
    )


def plan_to_builder_spec(plan: QuestionPlan, pack: Any | None = None) -> AnalyticsSpec:
    """Inverse map for AI Assist — surface business-friendly measure/dimension ids."""
    from app.schemas.analytics import AnalyticsFilterSpec, AnalyticsSpec as Spec

    metric_to_measure: dict[str, str] = {
        "revenue": "revenue",
        "units": "units_sold",
        "orders": "orders",
        "premium": "premium",
        "earned_premium": "earned_premium",
        "claims_incurred": "claims_incurred",
        "claim_count": "claim_count",
        "severity": "severity",
        "approval_rate": "approval_rate",
        "renewal_rate": "renewal_rate",
    }
    measure = metric_to_measure.get(plan.metric, plan.metric)

    analysis: AnalyticsAnalysisKind = "basic"
    if plan.analysis == "ranking":
        analysis = "top_n" if plan.order_direction == "desc" else "bottom_n"
    elif plan.analysis in {
        "contribution",
        "running_total",
        "moving_average",
        "period_growth",
        "breakdown",
    }:
        analysis = plan.analysis  # type: ignore[assignment]
    elif plan.intent == "trend":
        analysis = "trend"

    filters = []
    for filt in plan.filters:
        leaf = filt.column.split(".")[-1]
        domain = leaf
        for alias, key in _DIMENSION_ALIASES.items():
            if key == leaf or alias == leaf:
                domain = alias if alias in {"region", "city", "make", "car_type", "colour"} else key
                break
        filters.append(AnalyticsFilterSpec(domain=domain, values=[filt.value], operator=filt.operator))

    return Spec(
        metrics=[measure],
        dimensions=list(plan.dimensions),
        filters=filters,
        analysis=analysis,
        limit=plan.limit,
        order_direction=plan.order_direction,
        time_grain=plan.time_grain,
        viz="auto",
    )
