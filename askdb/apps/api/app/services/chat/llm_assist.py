"""LLM reasoning under governance.

The LLM never answers from the raw prompt alone:

* ``plan_spec`` turns the planner's structured plan into hard requirements
  (metric formula, mandatory filters, partition, window, period).
* ``generate_validated_sql`` runs Generate -> Validate -> Repair -> Validate.
  Only SQL the validator approves is returned.
* ``interpret_question`` asks the LLM to restate an unclear question in the
  governed vocabulary; the semantic pipeline then plans the restatement.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from app.core.config import Industry, Settings
from app.services.chat.question_understanding import QuestionPlan, filter_predicate
from app.services.llm import complete_chat, complete_text

_FORMULA: dict[str, str] = {
    "revenue": "SUM(fact_sales.total_sales)",
    "units": "SUM(fact_sales.order_qty)",
    "orders": "COUNT(DISTINCT fact_sales.order_id)",
    "average_selling_price": "SUM(total_sales) / NULLIF(SUM(order_qty), 0)",
    "premium": "SUM(fact_policy_monthly.written_premium)",
    "earned_premium": "SUM(fact_policy_monthly.earned_premium)",
    "claims_incurred": "SUM(fact_claims.incurred_amount)",
    "claims_paid": "SUM(fact_claims.paid_amount)",
    "claim_count": "COUNT(DISTINCT fact_claims.claim_id)",
    "severity": "SUM(incurred_amount) / NULLIF(COUNT(DISTINCT claim_id), 0)",
    "loss_ratio": "SUM(claims incurred) / NULLIF(SUM(earned premium), 0), same grain",
    "frequency": "COUNT(DISTINCT claim_id) / NULLIF(SUM(exposure_units), 0)",
}


def plan_spec(plan: QuestionPlan) -> str:
    """Requirements the generated SQL must satisfy; the validator enforces the same rules."""
    lines = ["QUERY PLAN (mandatory — the validator rejects SQL that deviates):"]
    lines.append(f"- Metric: {plan.metric} = {_FORMULA.get(plan.metric, plan.metric)}")
    if plan.dimensions:
        lines.append(f"- Group by (in this order): {', '.join(plan.dimensions)}")
    for filt in plan.filters:
        lines.append(f"- Filter: {filter_predicate(filt.column, filt)}")
    if plan.period is not None:
        if plan.period.start and plan.period.end:
            lines.append(
                f"- Period {plan.period.label}: date >= '{plan.period.start.isoformat()}' "
                f"AND date < '{plan.period.end.isoformat()}'"
            )
        elif plan.period.years:
            lines.append(f"- Years: {', '.join(str(y) for y in plan.period.years)}")
        else:
            lines.append(
                f"- Period {plan.period.label}: relative to MAX(date) in the fact table"
            )
    elif plan.year_filter:
        lines.append(f"- Year: EXTRACT(YEAR FROM date) = {plan.year_filter}")
    analysis = plan.analysis
    if analysis == "top_n_per_group":
        lines.append(
            f"- ROW_NUMBER() OVER (PARTITION BY {', '.join(plan.partition_by)} ORDER BY metric "
            f"{plan.order_direction.upper()}); keep row_number <= {plan.limit}. "
            "Never partition by the ranked dimension."
        )
    elif analysis == "period_growth":
        partition = (
            f"PARTITION BY {', '.join(plan.partition_by)} " if plan.partition_by else ""
        )
        lines.append(f"- Growth % with LAG(metric) OVER ({partition}ORDER BY {plan.time_grain})")
    elif analysis == "running_total":
        lines.append(
            "- Running total: SUM(metric) OVER (ORDER BY period ROWS BETWEEN UNBOUNDED "
            "PRECEDING AND CURRENT ROW)"
        )
    elif analysis == "moving_average":
        preceding = max(1, (plan.window_months or 3) - 1)
        lines.append(
            f"- Moving average: AVG(metric) OVER (ORDER BY period ROWS BETWEEN {preceding} "
            "PRECEDING AND CURRENT ROW)"
        )
    elif analysis == "growth_ranking":
        lines.append(
            "- Compare the latest 12 months with the previous 12 months (anchored at "
            "MAX(date)); growth % = (current - previous) / previous; order by growth "
            f"{plan.order_direction.upper()}"
        )
    elif analysis == "divergence":
        moves = ", ".join(f"{metric} {direction}" for metric, direction in plan.divergence)
        lines.append(
            "- Latest 12 months vs previous 12 months per group; keep groups where "
            f"{moves}"
        )
    elif plan.intent == "ranking":
        lines.append(f"- ORDER BY metric {plan.order_direction.upper()} LIMIT {plan.limit}")
    return "\n".join(lines)


@dataclass(slots=True)
class LlmSqlOutcome:
    sql: str | None = None
    attempts: int = 0
    repaired: bool = False
    error: str | None = None
    rejected: list[str] = field(default_factory=list)
    model: str = ""
    prompt_tokens: int = 0
    completion_tokens: int = 0
    circuit_open: bool = False


async def generate_validated_sql(
    *,
    settings: Settings,
    industry: Industry,
    question: str,
    plan: QuestionPlan,
    schema_hints: str,
    validate: Callable[[str], tuple[bool, str | None]],
    prior_sql: str | None = None,
    model_override: str | None = None,
    temperature: float | None = None,
    top_p: float | None = None,
    top_k: int | None = None,
    max_repairs: int = 1,
    initial_feedback: str | None = None,
) -> LlmSqlOutcome:
    """Generate -> Validate -> Repair -> Validate. Returns SQL only when approved."""
    outcome = LlmSqlOutcome()
    hints = f"{schema_hints}\n\n{plan_spec(plan)}"
    feedback: str | None = initial_feedback
    for attempt in range(1 + max_repairs):
        result = await complete_chat(
            settings=settings,
            industry=industry,
            question=question,
            schema_hints=hints,
            prior_sql=prior_sql,
            model_override=model_override,
            temperature=0.0 if attempt else temperature,
            top_p=top_p,
            top_k=top_k,
            feedback=feedback,
        )
        outcome.attempts += 1
        outcome.model = result.model
        outcome.prompt_tokens += result.prompt_tokens
        outcome.completion_tokens += result.completion_tokens
        if result.circuit_open:
            outcome.circuit_open = True
            outcome.error = result.error
            return outcome
        if not result.sql:
            outcome.error = result.error or "empty response"
            return outcome
        ok, reason = validate(result.sql)
        if ok:
            outcome.sql = result.sql
            outcome.repaired = attempt > 0
            return outcome
        outcome.rejected.append(reason or "rejected")
        feedback = f"Validator: {reason}\nRejected SQL:\n{result.sql}"
    outcome.error = outcome.rejected[-1] if outcome.rejected else "rejected"
    return outcome


_INDUSTRY_METRICS: dict[Industry, str] = {
    Industry.AUTOMOTIVE: (
        "revenue, units sold, orders, average selling price, market share, growth, "
        "running total, moving average"
    ),
    Industry.INSURANCE: (
        "written premium, earned premium, claims incurred, claims paid, claim count, "
        "loss ratio, claim severity, claim frequency, renewal rate, approval rate"
    ),
}
_INDUSTRY_DIMENSIONS: dict[Industry, str] = {
    Industry.AUTOMOTIVE: (
        "month, quarter, year, brand, model, car type, fuel type, colour, city, state, "
        "region, dealer, salesperson"
    ),
    Industry.INSURANCE: (
        "month, quarter, year, product, line of business, coverage type, coverage tier, "
        "agent, channel, branch, region, state, claim status, claim type, policy status"
    ),
}
_VALUE_KEYS: dict[Industry, tuple[str, ...]] = {
    Industry.AUTOMOTIVE: ("make", "car_type", "engine_type", "state_code", "city"),
    Industry.INSURANCE: ("line_of_business", "coverage_type", "channel_name", "state_name"),
}


def interpretation_vocabulary(industry: Industry, resolver: Any) -> str:
    values: list[str] = []
    for key in _VALUE_KEYS[industry]:
        names = resolver.canonical_values(key)[:15] if resolver is not None else []
        if names:
            values.append(f"{key}: {', '.join(names)}")
    return (
        f"Metrics: {_INDUSTRY_METRICS[industry]}\n"
        f"Dimensions: {_INDUSTRY_DIMENSIONS[industry]}\n"
        + "\n".join(values)
    )


_JSON = re.compile(r"\{[\s\S]*\}")


async def interpret_question(
    *,
    settings: Settings,
    industry: Industry,
    question: str,
    vocabulary: str,
    model_override: str | None = None,
) -> tuple[str | None, int, int]:
    """Restate a question in governed vocabulary. Returns (question or None, tokens in, out)."""
    system = (
        f"You rewrite {industry.value} analytics questions for a governed semantic layer. "
        "Use ONLY the metrics, dimensions and values listed. Keep every brand, place, "
        "period and filter the user gave; never invent one. If the question cannot be "
        'expressed with this vocabulary, return {"question": null}. Otherwise return JSON '
        '{"question": "<one short question>"} and nothing else.\n\n'
        f"{vocabulary}"
    )
    result = await complete_text(
        settings=settings,
        system=system,
        user=question,
        max_tokens=120,
        model_override=model_override,
    )
    found = _JSON.search(result.content or "")
    rewritten: str | None = None
    if found:
        try:
            value = json.loads(found.group(0)).get("question")
        except (ValueError, AttributeError):
            value = None
        if isinstance(value, str) and value.strip() and value.strip() != question.strip():
            rewritten = value.strip()[:240]
    return rewritten, result.prompt_tokens, result.completion_tokens
