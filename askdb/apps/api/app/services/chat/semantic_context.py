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
    if plan.intent == "ranking":
        lines.append(f"Ranking direction: {plan.order_direction.upper()}")
    if plan.filters:
        lines.append("MATCHED BUSINESS VALUES — mandatory SQL filters:")
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
            relationships = getattr(model, "relationships", None) or []
            relevant_names = {
                part
                for filt in plan.filters
                for part in filt.column.split(".")
                if part.startswith(("dim_", "fact_"))
            }
            if plan.entity != "unknown":
                relevant_names.add(
                    {
                        "salesperson": "dim_salesman",
                        "dealer": "dim_dealer",
                        "vehicle": "dim_carline",
                        "region": "dim_region",
                        "agent": "dim_agent",
                        "product": "dim_product",
                        "policy": "dim_policy",
                        "customer": "dim_policy",
                        "claim": "fact_claims",
                    }.get(plan.entity, "")
                )
            join_hints: list[str] = []
            for relationship in relationships:
                from_table = getattr(relationship, "from_table", "")
                to_table = getattr(relationship, "to_table", "")
                if from_table in relevant_names or to_table in relevant_names:
                    join_hints.append(
                        f"  - {from_table}.{getattr(relationship, 'from_column', '')} = "
                        f"{to_table}.{getattr(relationship, 'to_column', '')}"
                    )
            if join_hints:
                lines.append("RELEVANT JOINS:")
                lines.extend(join_hints[:8])

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


def build_allowed_schema(pack: Any | None) -> dict[str, set[str]]:
    """Compile physical table/column whitelist from one validated semantic pack."""
    if pack is None:
        return {}
    model = getattr(pack, "model", None)
    tables = getattr(model, "tables", {}) if model is not None else {}
    return {
        str(getattr(table, "physical_name", name)).lower(): {
            str(column).lower() for column in (getattr(table, "columns", {}) or {})
        }
        for name, table in (tables or {}).items()
    }


def validate_sql_against_plan(
    sql: str,
    plan: QuestionPlan,
    *,
    allowed_schema: dict[str, set[str]] | None = None,
) -> tuple[bool, str | None]:
    """Validate entity, filters, ranking direction, and semantic schema."""
    if not sql:
        return False, "Empty SQL"
    lowered = sql.lower()
    if plan.entity == "salesperson" and "dim_salesman" not in lowered:
        return False, "Salesperson questions must join automotive.dim_salesman"
    if plan.entity == "salesperson" and "dim_dealer" in lowered and "dim_salesman" not in lowered:
        return False, "Salesperson must not be answered with dealers only"
    if plan.entity == "dealer" and "dim_dealer" not in lowered:
        return False, "Dealer questions must join automotive.dim_dealer"
    required_entities = {
        "vehicle": "dim_carline",
        "agent": "dim_agent",
        "product": "dim_product",
        "policy": "dim_policy",
        "customer": "dim_policy",
        "claim": "fact_claims",
        "region": "dim_region",
    }
    required_table = required_entities.get(plan.entity)
    if required_table and required_table not in lowered:
        return False, f"{plan.entity.title()} questions must use {required_table}"
    for filt in plan.filters:
        if filt.value.lower() not in lowered:
            return False, f"Missing mandatory filter value '{filt.value}' in SQL"
        column_name = filt.column.rsplit(".", 1)[-1].lower()
        if column_name not in lowered:
            return False, f"Missing mandatory filter column '{column_name}' in SQL"
    if plan.intent == "ranking":
        required_direction = plan.order_direction.lower()
        if not re.search(rf"\border\s+by\b[\s\S]*?\b{required_direction}\b", lowered):
            return False, f"Ranking SQL must order {required_direction.upper()}"

    if allowed_schema:
        alias_map: dict[str, str] = {}
        table_pattern = re.compile(
            r"\b(?:from|join)\s+([a-z_][\w]*\.[a-z_][\w]*)(?:\s+(?:as\s+)?([a-z_][\w]*))?",
            re.I,
        )
        reserved = {
            "where",
            "join",
            "left",
            "right",
            "inner",
            "outer",
            "full",
            "group",
            "order",
            "limit",
            "on",
        }
        for match in table_pattern.finditer(sql):
            table = match.group(1).lower()
            if table not in allowed_schema:
                return False, f"Table '{table}' is outside the selected domain semantic pack"
            alias = (match.group(2) or table.rsplit(".", 1)[-1]).lower()
            if alias in reserved:
                alias = table.rsplit(".", 1)[-1]
            alias_map[alias] = table
        for alias, column in re.findall(r"\b([a-z_][\w]*)\.([a-z_][\w]*)\b", lowered):
            table = alias_map.get(alias)
            if table and column not in allowed_schema[table]:
                return (
                    False,
                    f"Column '{alias}.{column}' is not in the selected domain semantic pack",
                )
    return True, None
