"""Resolve glossary synonyms and metric expressions before SQL is generated."""

from __future__ import annotations

import re
from typing import Any

from app.services.chat.question_understanding import QuestionPlan

_MEASURE_KIND = {
    "revenue": "revenue",
    "units_sold": "units",
    "units": "units",
    "orders": "orders",
    "average_selling_price": "average_selling_price",
    "premium": "premium",
    "written_premium": "premium",
    "earned_premium": "earned_premium",
    "claims_incurred": "claims_incurred",
    "claim_count": "claim_count",
    "loss_ratio": "loss_ratio",
    "severity": "severity",
}

_DIMENSION_ENTITY = {
    "salesperson": "salesperson",
    "dealer": "dealer",
    "region": "region",
    "car": "vehicle",
    "vehicle": "vehicle",
    "product": "product",
    "agent": "agent",
    "policy": "policy",
    "customer": "customer",
}

_DIMENSION_KEY = {
    "salesperson": "salesperson",
    "dealer": "dealer",
    "region": "region",
    "car": "model",
    "vehicle": "model",
    "colour": "colour",
    "color": "colour",
    "product": "product",
    "agent": "agent",
}


def apply_glossary(plan: QuestionPlan, question: str, pack: Any | None) -> str | None:
    """Override a guessed metric when the glossary has a more specific match.

    Returns the glossary SQL expression when a measure term matches.
    Ambiguous questions are left unchanged so clarification still wins.
    """
    if pack is None or plan.is_ambiguous:
        return None
    glossary = getattr(pack, "glossary", None)
    terms = getattr(glossary, "terms", None) or {}
    if not terms:
        return None

    question_text = (question or "").lower()
    matches: list[tuple[int, Any, str]] = []
    for name, term in terms.items():
        labels = [name, getattr(term, "display_label", None) or ""]
        labels.extend(getattr(term, "synonyms", None) or [])
        for label in labels:
            token = str(label or "").strip().lower()
            if len(token) < 3:
                continue
            if re.search(rf"\b{re.escape(token)}\b", question_text):
                matches.append((len(token), term, token))
    if not matches:
        return None
    matches.sort(key=lambda item: item[0], reverse=True)

    formula: str | None = None
    matched_names: list[str] = []
    measure_applied = False
    entity_applied = False
    for _length, term, token in matches:
        measure = str(getattr(term, "maps_to_measure", None) or "")
        kind = _MEASURE_KIND.get(measure)
        if kind and not measure_applied and (
            kind == "average_selling_price" or plan.metric == "unknown"
        ):
            plan.metric = kind  # type: ignore[assignment]
            if kind == "average_selling_price":
                plan.aggregation = "ratio"
                formula = getattr(term, "sql_expression", None) or (
                    "SUM(total_sales) / NULLIF(SUM(order_qty), 0)"
                )
            else:
                formula = formula or getattr(term, "sql_expression", None)
            measure_applied = True
            matched_names.append(token)
        dimension = str(getattr(term, "maps_to_dimension", None) or "").strip().lower()
        entity = _DIMENSION_ENTITY.get(dimension)
        if entity and plan.entity == "unknown" and not entity_applied:
            plan.entity = entity  # type: ignore[assignment]
            key = _DIMENSION_KEY.get(dimension)
            if key and key not in plan.dimensions:
                plan.dimensions.append(key)
            entity_applied = True
            matched_names.append(token)
    if matched_names:
        plan.glossary_hits = list(dict.fromkeys([*plan.glossary_hits, *matched_names]))
    return formula
