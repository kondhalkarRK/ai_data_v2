"""Compact, domain-scoped semantic hints for LLM SQL (Streamlit-style, size-capped)."""

from __future__ import annotations

import re
from typing import Any

from app.core.config import Industry
from app.services.chat.question_understanding import QuestionPlan


def build_domain_sql_hints(
    *,
    industry: Industry,
    question: str,
    plan: QuestionPlan,
    pack: Any | None,
) -> str:
    """Build a tight prompt block from the active industry pack only."""
    lines: list[str] = [
        f"DOMAIN: {industry.value}",
        "Use only schema-qualified PostgreSQL tables listed below. Never invent columns.",
    ]

    if plan.entity != "unknown":
        lines.append(f"Resolved entity: {plan.entity}")
    if plan.metric != "unknown":
        lines.append(f"Resolved metric: {plan.metric}")
    if plan.filters:
        lines.append("Mandatory filters (must appear in SQL WHERE):")
        for filt in plan.filters:
            lines.append(f"  - {filt.column} {filt.operator} '{filt.value}'")
    for note in plan.notes:
        lines.append(f"Rule: {note}")

    if pack is not None:
        glossary = getattr(pack, "glossary", None)
        model = getattr(pack, "model", None)
        if glossary is not None:
            hits = _match_glossary_terms(question, glossary)
            if hits:
                lines.append("GLOSSARY MATCHES:")
                for hit in hits[:8]:
                    lines.append(f"  - {hit}")
            rules = getattr(glossary, "domain_rules", None) or {}
            for rule in (rules.get("always_rules") or [])[:6]:
                lines.append(f"ALWAYS: {rule}")
            for rule in (rules.get("never_rules") or [])[:4]:
                lines.append(f"NEVER: {rule}")
        if model is not None:
            lines.append("TABLES:")
            tables = getattr(model, "tables", {}) or {}
            for name, table in list(tables.items())[:8]:
                physical = getattr(table, "physical_name", name)
                cols = getattr(table, "columns", {}) or {}
                col_names = ", ".join(list(cols.keys())[:12])
                lines.append(f"  - {physical} ({col_names})")
            measures = getattr(model, "measures", {}) or {}
            if measures:
                lines.append("MEASURES:")
                for mname, measure in list(measures.items())[:8]:
                    expr = getattr(measure, "expression", "")
                    lines.append(f"  - {mname}: {expr}")

    # Hard industry fallbacks if pack missing.
    if pack is None:
        lines.append(_fallback_schema(industry))

    text = "\n".join(lines)
    if len(text) > 2800:
        return text[:2800] + "\n...[trimmed]"
    return text


def _match_glossary_terms(question: str, glossary: Any) -> list[str]:
    q = (question or "").lower()
    terms = getattr(glossary, "terms", {}) or {}
    hits: list[str] = []
    for name, term in terms.items():
        candidates = [name.lower()]
        display = getattr(term, "display_label", None)
        if display:
            candidates.append(str(display).lower())
        candidates.extend(str(s).lower() for s in (getattr(term, "synonyms", None) or []))
        if any(re.search(rf"\b{re.escape(token)}\b", q) for token in candidates if token):
            expr = getattr(term, "sql_expression", None)
            disamb = (getattr(term, "disambiguation", None) or [None])[0]
            piece = f"{name}"
            if expr:
                piece += f" → {expr}"
            if disamb:
                piece += f" ({disamb})"
            hits.append(piece)
    return hits


def _fallback_schema(industry: Industry) -> str:
    if industry is Industry.AUTOMOTIVE:
        return (
            "TABLES:\n"
            "- automotive.fact_sales (order_qty, total_sales, sales_date, carline_id, sales_person_id, dealer_id, region_id)\n"
            "- automotive.dim_carline (model, make, car_type, engine_type)\n"
            "- automotive.dim_salesman (first_name, last_name, sales_person_id)\n"
            "- automotive.dim_dealer (dealer_name, dealer_grade, city)\n"
            "- automotive.dim_region (region_name)\n"
            "ALWAYS: salesperson → dim_salesman; dealer → dim_dealer; sedan → car_type = 'Sedan'"
        )
    return (
        "TABLES:\n"
        "- insurance.fact_claims (incurred_amount, reported_date, claim_status, region_id)\n"
        "- insurance.fact_policy_monthly (written_premium, earned_premium, accounting_month)\n"
        "- insurance.dim_region (region_name)"
    )


def validate_sql_against_plan(sql: str, plan: QuestionPlan) -> tuple[bool, str | None]:
    """Light validation: required entities/filters must appear in SQL text."""
    if not sql:
        return False, "Empty SQL"
    lowered = sql.lower()
    if plan.entity == "salesperson" and "dim_salesman" not in lowered:
        return False, "Salesperson questions must join automotive.dim_salesman"
    if plan.entity == "salesperson" and "dim_dealer" in lowered and "dim_salesman" not in lowered:
        return False, "Salesperson must not be answered with dealers only"
    if plan.entity == "dealer" and "dim_dealer" not in lowered:
        return False, "Dealer questions must join automotive.dim_dealer"
    for filt in plan.filters:
        if filt.value.lower() not in lowered:
            return False, f"Missing mandatory filter value '{filt.value}' in SQL"
        if "car_type" in filt.column and "car_type" not in lowered:
            return False, "Missing car_type filter in SQL"
    return True, None
