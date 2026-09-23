"""Semantic Query Planner — the governed NLQ pipeline.

User Question → Query Rewrite → Intent Detection → Ambiguity Check →
Conversation Context → Semantic Resolver → Join Path Discovery →
Business Formula Engine → SQL Generation → SQL Validation → Auto Repair →
Execution → Chart Recommendation → Narration.

Stages before execution are pure. Validation, repair, execution, and narration
stay in the chat service so they can use the live database.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from app.core.config import Industry
from app.services.chat.conversation_context import (
    apply_followup,
    is_contextual_followup,
    state_to_plan,
)
from app.services.chat.glossary_resolve import apply_glossary
from app.services.chat.question_understanding import QuestionPlan, understand_question
from app.services.chat.templates import resolve_template

PIPELINE_STAGES: list[dict[str, str]] = [
    {"id": "question", "label": "User Question"},
    {"id": "rewrite", "label": "Query Rewrite"},
    {"id": "intent", "label": "Intent Detection"},
    {"id": "ambiguity", "label": "Ambiguity Check"},
    {"id": "context", "label": "Conversation Context"},
    {"id": "semantic", "label": "Semantic Resolver"},
    {"id": "joins", "label": "Join Path Discovery"},
    {"id": "formula", "label": "Business Formula Engine"},
    {"id": "sql", "label": "SQL Generation"},
    {"id": "validate", "label": "SQL Validation"},
    {"id": "repair", "label": "Auto Repair"},
    {"id": "execute", "label": "Execution"},
    {"id": "chart", "label": "Chart Recommendation"},
    {"id": "narration", "label": "Narration"},
]

_FORMULAS: dict[str, str] = {
    "revenue": "SUM(total_sales)",
    "units": "SUM(order_qty)",
    "orders": "COUNT(DISTINCT order_id)",
    "premium": "SUM(written_premium)",
    "earned_premium": "SUM(earned_premium)",
    "claims_incurred": "SUM(incurred_amount)",
    "claim_count": "COUNT(DISTINCT claim_id)",
    "loss_ratio": "claims_incurred / earned_premium",
    "severity": "SUM(incurred_amount) / COUNT(DISTINCT claim_id)",
}

_JOIN_FOR_DIMENSION: dict[str, str] = {
    "region": "fact_sales → dim_region",
    "city": "fact_sales → dim_region",
    "state": "fact_sales → dim_region",
    "dealer": "fact_sales → dim_dealer",
    "salesperson": "fact_sales → dim_salesman",
    "model": "fact_sales → dim_carline",
    "make": "fact_sales → dim_carline",
    "car_type": "fact_sales → dim_carline",
    "colour": "fact_sales → dim_color",
    "product": "fact_policy_monthly → dim_product",
    "agent": "fact_policy_monthly → dim_agent",
    "policy": "fact_policy_monthly → dim_policy",
    "customer": "fact_policy_monthly → dim_policy",
}


@dataclass(slots=True)
class SemanticQuery:
    """Artifacts produced before SQL validation."""

    original: str
    rewritten: str
    plan: QuestionPlan
    prior_sql: str | None = None
    formula: str = ""
    joins: list[str] = field(default_factory=list)
    sql: str | None = None
    title: str | None = None
    path: str = "fallback"
    glossary_matches: int = 0
    chart_type: str = "bar"

    def trace(self) -> dict[str, Any]:
        return {
            "rewritten": self.rewritten,
            "intent": self.plan.intent,
            "entity": self.plan.entity,
            "metric": self.plan.metric,
            "analysis": self.plan.analysis,
            "dimensions": list(self.plan.dimensions),
            "formula": self.formula,
            "joins": list(self.joins),
            "filters": [item.label for item in self.plan.filters],
            "ambiguous": self.plan.is_ambiguous,
            "options": list(self.plan.ambiguity_options),
            "chartType": self.chart_type,
            "hasPriorSql": bool(self.prior_sql),
        }


def rewrite_question(question: str) -> str:
    """Normalize business phrasing before intent detection."""
    text = re.sub(r"\s+", " ", (question or "").strip())
    prefix = re.compile(
        r"^(?:please|can you|could you|would you|i want to|i'd like to|show me|show)\s+",
        re.I,
    )
    for _ in range(3):
        stripped = prefix.sub("", text)
        if stripped == text:
            break
        text = stripped.strip()
    swaps = (
        (r"\bper annum\b", "per year"),
        (r"\byoy\b", "year over year"),
        (r"\bmom\b", "month over month"),
        (r"\bturnover\b", "revenue"),
        (r"\bqty\b", "quantity"),
    )
    for pattern, repl in swaps:
        text = re.sub(pattern, repl, text, flags=re.I)
    return text.strip() or (question or "").strip()


def business_formula(plan: QuestionPlan) -> str:
    return _FORMULAS.get(plan.metric, plan.metric)


def join_path(plan: QuestionPlan) -> list[str]:
    path: list[str] = []
    fact = "fact_sales" if plan.industry is Industry.AUTOMOTIVE else "fact_policy_monthly"
    if plan.metric in {"claims_incurred", "claim_count", "severity", "approval_rate"}:
        fact = "fact_claims"
    path.append(fact)
    for dimension in plan.dimensions:
        hop = _JOIN_FOR_DIMENSION.get(dimension)
        if hop and hop not in path:
            path.append(hop)
    for filt in plan.filters:
        table = filt.column.split(".")[-2] if "." in filt.column else ""
        if table and table not in " ".join(path):
            path.append(f"{fact} → {table}")
    return path


def recommend_chart(plan: QuestionPlan | None, columns: list[str]) -> str:
    """Pick a chart from intent, not from a default bar."""
    if plan is None or len(columns) < 2:
        return "table"
    if plan.intent in {"trend", "comparison"} or plan.time_grain in {"month", "quarter", "year"}:
        return "line"
    if plan.analysis == "year_window_compare":
        return "line"
    if plan.intent == "ranking" or plan.analysis == "ranking":
        return "bar"
    return "bar"


def plan_semantic_query(
    industry: Industry,
    question: str,
    *,
    value_filters: list[Any] | None = None,
    prior_sql: str | None = None,
    pack: object | None = None,
    surprise_sql: tuple[str, str, int] | None = None,
    prior_state: dict[str, Any] | None = None,
) -> SemanticQuery:
    """Run rewrite through SQL generation. Stops SQL when the question is ambiguous."""
    rewritten = rewrite_question(question)
    contextual = bool(prior_state) and is_contextual_followup(question)
    if contextual and prior_state is not None:
        plan = apply_followup(state_to_plan(industry, prior_state), rewritten)
    else:
        plan = understand_question(industry, rewritten, value_filters=value_filters)
    formula = apply_glossary(plan, rewritten, pack)
    query = SemanticQuery(
        original=question,
        rewritten=rewritten,
        plan=plan,
        prior_sql=prior_sql,
        formula=formula or business_formula(plan),
        joins=join_path(plan),
        chart_type=recommend_chart(plan, ["dimension", "metric"]),
        glossary_matches=len(plan.glossary_hits),
    )
    if plan.is_ambiguous and not contextual:
        query.chart_type = "table"
        query.path = "clarification"
        return query
    if prior_sql and not contextual:
        # No stored plan to recompile. The chat service may still ask the model.
        query.path = "followup"
        return query
    if surprise_sql is not None:
        sql, title, matches = surprise_sql
        query.sql = sql
        query.title = title
        query.glossary_matches = matches
        query.path = "template"
        return query
    hit = resolve_template(industry, rewritten, plan=plan, pack=pack)
    if hit is not None:
        query.sql = hit.sql
        query.title = hit.title
        query.glossary_matches = hit.glossary_matches
        query.path = hit.path
    return query
