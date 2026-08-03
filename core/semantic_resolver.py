"""
core/semantic_resolver.py
Resolve validated intent → deterministic execution contract (CSV/DataFrame domain).
"""
from __future__ import annotations

from typing import Any

import pandas as pd

_DIMENSION_ALIAS = {
    "regions": "region",
    "categories": "category",
    "colours": "colour_name",
    "colors": "colour_name",
    "colour": "colour_name",
    "color": "colour_name",
    "salespeople": "salesperson",
    "reps": "salesperson",
    "models": "model",
    "makes": "make",
    "brands": "make",
    "brand": "make",
}

_MONTH_MAP = {
    "january": 1, "february": 2, "march": 3, "april": 4,
    "may": 5, "june": 6, "july": 7, "august": 8,
    "september": 9, "october": 10, "november": 11, "december": 12,
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "sept": 9, "oct": 10,
    "nov": 11, "dec": 12,
}

_BYPASS_INTENTS = {
    "unsupported", "scenario_analysis", "objective_override", "out_of_scope",
}


def _normalise_month(value: Any) -> int | None:
    if value is None:
        return None
    if isinstance(value, int) and 1 <= value <= 12:
        return value
    if isinstance(value, str):
        text = value.strip().lower()
        if text.isdigit():
            n = int(text)
            return n if 1 <= n <= 12 else None
        return _MONTH_MAP.get(text)
    return None


def _resolve_col(df: pd.DataFrame, col: str) -> str | None:
    if col in df.columns:
        return col
    lower_map = {c.lower(): c for c in df.columns}
    return lower_map.get(col.lower())


def _measure_expression_from_intent(validated: dict) -> str | None:
    """Fallback expression from LLM intent measures list."""
    measures = validated.get("measures")
    if isinstance(measures, list) and measures:
        first = measures[0]
        if isinstance(first, dict):
            expr = first.get("expression")
            if isinstance(expr, str) and expr.strip():
                return expr.strip()
    expr = validated.get("expression")
    if isinstance(expr, str) and expr.strip():
        return expr.strip()
    return None


def resolve_semantics(
    validated: dict[str, Any],
    df: pd.DataFrame,
) -> dict[str, Any]:
    """
    Resolve validated intent dict to an execution contract for the SQL compiler.
    """
    validated = validated or {}
    warnings: list[str] = []

    intent_type = str(validated.get("intent_type") or "").lower()

    # STEP 1 — Intent bypass routing
    if intent_type in _BYPASS_INTENTS:
        return {
            "expression": "1",
            "display_label": intent_type,
            "format": "",
            "dimensions": [],
            "filters": {},
            "time_grain": None,
            "limit": validated.get("limit"),
            "order": "DESC",
            "metric_name": None,
            "resolution_source": "bypass",
            "bypass": True,
            "warnings": warnings,
        }

    # STEP 2 — Metric resolution
    metric_name = (
        validated.get("metric_name")
        or validated.get("metric")
    )
    if not metric_name and isinstance(validated.get("measures"), list) and validated["measures"]:
        m0 = validated["measures"][0]
        if isinstance(m0, dict):
            metric_name = m0.get("name")

    expression = None
    display_label = "Value"
    fmt = ""
    resolution_source = "llm_fallback"

    try:
        from core.metric_registry import get_metric_registry
        registry = get_metric_registry()
    except Exception:
        registry = None

    resolved = None
    if registry and metric_name:
        resolved = registry.resolve_metric(str(metric_name))
        if resolved:
            resolution_source = "registry"
        else:
            syn = registry.find_metric_by_synonym(str(metric_name))
            if syn:
                resolved = registry.resolve_metric(syn)
                metric_name = syn
                resolution_source = "synonym"

    # Semantic phrase mapping via semantic_loader synonyms
    if resolved is None and metric_name:
        try:
            from semantic.semantic_loader import get_semantic_loader
            loader = get_semantic_loader()
            syn_map = loader.get_synonym_map()
            canon = syn_map.get(str(metric_name).lower())
            if canon and registry:
                # Try metric registry by display/canonical
                hit = registry.find_metric_by_synonym(canon) or registry.find_metric_by_synonym(
                    str(metric_name)
                )
                if hit:
                    resolved = registry.resolve_metric(hit)
                    metric_name = hit
                    resolution_source = "synonym"
            # Also try loader measure expressions
            if resolved is None:
                exprs = loader.get_measure_expressions()
                if canon in exprs:
                    expression = exprs[canon]
                    display_label = canon
                    resolution_source = "synonym"
                elif str(metric_name) in exprs:
                    expression = exprs[str(metric_name)]
                    display_label = str(metric_name)
                    resolution_source = "synonym"
        except Exception:
            pass

    if resolved:
        expression = resolved.get("formula") or expression
        display_label = resolved.get("display_label") or display_label
        fmt = resolved.get("format") or fmt
        metric_name = resolved.get("name") or metric_name

    if not expression:
        expression = _measure_expression_from_intent(validated)
        resolution_source = "llm_fallback"

    if not expression:
        expression = "COUNT(*)"
        warnings.append("No metric resolved — defaulting to COUNT(*)")
        resolution_source = "llm_fallback"

    # STEP 3 — Dimension normalisation
    raw_dims = validated.get("dimensions") or []
    if isinstance(raw_dims, str):
        raw_dims = [raw_dims]
    normalised_dims: list[str] = []
    for d in raw_dims:
        if isinstance(d, dict):
            col = d.get("column") or d.get("alias") or ""
        else:
            col = str(d)
        if not col:
            continue
        col = _DIMENSION_ALIAS.get(col.lower(), col)
        physical = _resolve_col(df, col)
        if physical:
            if physical not in normalised_dims:
                normalised_dims.append(physical)
        else:
            warnings.append(f"Dimension '{col}' not found in dataset columns")

    # STEP 4 — Filter validation
    raw_filters = validated.get("filters") or []
    filter_dict: dict[str, Any] = {}

    if isinstance(raw_filters, dict):
        items = [{"column": k, "value": v} for k, v in raw_filters.items()]
    elif isinstance(raw_filters, list):
        items = raw_filters
    else:
        items = []

    for f in items:
        if not isinstance(f, dict):
            continue
        col = f.get("column") or f.get("field")
        if not col:
            continue
        col = _DIMENSION_ALIAS.get(str(col).lower(), str(col))
        physical = _resolve_col(df, col)
        if not physical:
            # Allow year/month pseudo-filters even if not real columns
            if str(col).lower() in ("year", "month", "quarter"):
                physical = str(col).lower()
            else:
                warnings.append(f"Filter column '{col}' not found in dataset")
                continue

        value = f.get("value")
        key = physical.lower() if physical.lower() in ("year", "month", "quarter") else physical

        if key == "year":
            try:
                value = int(value)
            except (TypeError, ValueError):
                pass
        elif key == "month":
            norm = _normalise_month(value)
            if norm is not None:
                value = norm

        filter_dict[key] = value
        # Preserve operator if present
        if f.get("operator"):
            filter_dict[f"_{key}_op"] = f.get("operator")

    # STEP 5 — Smart defaults
    date_cols = [
        c for c in df.columns
        if pd.api.types.is_datetime64_any_dtype(df[c])
        or "date" in c.lower()
    ]
    if not any(k in filter_dict for k in ("year", "month")) and date_cols:
        warnings.append(
            f"No time filter applied — date column '{date_cols[0]}' exists "
            "(CSV data may be single-period; filter not auto-applied)."
        )

    if resolved and resolved.get("default_filters"):
        for dk, dv in resolved["default_filters"].items():
            if dk not in filter_dict:
                filter_dict[dk] = dv

    # STEP 6 — Build execution contract
    order = "DESC"
    order_by = validated.get("order_by")
    if isinstance(order_by, list) and order_by:
        direction = order_by[0].get("direction") if isinstance(order_by[0], dict) else None
        if isinstance(direction, str) and direction.upper() in ("ASC", "DESC"):
            order = direction.upper()
    elif isinstance(validated.get("order"), str):
        o = validated["order"].strip().upper()
        if o in ("ASC", "DESC"):
            order = o

    return {
        "expression": expression,
        "display_label": display_label,
        "format": fmt,
        "dimensions": normalised_dims,
        "filters": filter_dict,
        "time_grain": validated.get("time_grain"),
        "limit": validated.get("limit"),
        "order": order,
        "metric_name": metric_name if isinstance(metric_name, str) else None,
        "resolution_source": resolution_source,
        "bypass": False,
        "warnings": warnings,
        "intent_type": intent_type or validated.get("intent_type"),
    }
