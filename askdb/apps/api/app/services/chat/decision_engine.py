"""Decision engine: how confident we are, and which path answers the question.

Paths
    semantic       governed SQL compiled from the semantic layer (fast, consistent)
    llm_reasoning  planner spec -> LLM SQL -> validation -> repair; the governed
                   query (when one exists) is the fallback, never an unvalidated answer
    clarify        no reliable answer: offer interpretations instead of guessing

Confidence is a score from what was actually resolved (spelling guesses, missing
metric, no governed query), bucketed into High / Medium / Needs clarification.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any, Literal

from app.core.config import Industry
from app.services.chat.clarification import plan_suggestions, scope_label
from app.services.chat.question_understanding import QuestionPlan

ConfidenceLevel = Literal["high", "medium", "needs_clarification"]
DecisionPath = Literal["semantic", "llm_reasoning", "clarify"]

HIGH_CONFIDENCE = 85
MEDIUM_CONFIDENCE = 60

COMPLEX_ANALYSES = frozenset(
    {
        "top_n_per_group",
        "running_total",
        "moving_average",
        "period_growth",
        "growth_ranking",
        "divergence",
        "above_average",
        "year_window_compare",
    }
)
_LEVEL_LABEL: dict[str, str] = {
    "high": "High confidence",
    "medium": "Medium confidence",
    "needs_clarification": "Needs clarification",
}
_PATH_LABEL: dict[str, str] = {
    "semantic": "Semantic layer",
    "llm_reasoning": "Planner + AI reasoning",
    "clarify": "Clarification",
}


@dataclass(slots=True)
class Confidence:
    level: ConfidenceLevel
    score: int
    reasons: list[str] = field(default_factory=list)

    @property
    def label(self) -> str:
        return _LEVEL_LABEL[self.level]

    def to_dict(self) -> dict[str, Any]:
        return {
            "level": self.level,
            "label": self.label,
            "score": self.score,
            "reasons": list(self.reasons),
        }


@dataclass(slots=True)
class RouteDecision:
    path: DecisionPath
    complexity: Literal["simple", "complex"]
    reason: str
    llm_available: bool = False
    governed_fallback: bool = False

    @property
    def label(self) -> str:
        return _PATH_LABEL[self.path]

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "label": self.label,
            "complexity": self.complexity,
            "reason": self.reason,
            "llmAvailable": self.llm_available,
            "governedFallback": self.governed_fallback,
        }


def is_complex(plan: QuestionPlan) -> bool:
    """Window / multi-period reasoning, or several business dimensions at once."""
    if plan.analysis in COMPLEX_ANALYSES:
        return True
    business_dims = [d for d in plan.dimensions if d not in {"month", "quarter", "year"}]
    return len(business_dims) >= 2


def level_for(score: int) -> ConfidenceLevel:
    if score >= HIGH_CONFIDENCE:
        return "high"
    if score >= MEDIUM_CONFIDENCE:
        return "medium"
    return "needs_clarification"


def assess_confidence(
    plan: QuestionPlan,
    *,
    resolution: Any | None = None,
    corrections: Iterable[tuple[str, str]] = (),
    has_sql: bool,
    contextual: bool = False,
    reinterpreted: bool = False,
    ai_generated: bool = False,
) -> Confidence:
    score = 100
    reasons: list[str] = []
    for match in getattr(resolution, "matches", None) or []:
        if match.method == "fuzzy":
            score -= 16
            reasons.append(
                f"\u201c{match.text}\u201d read as {match.entry.canonical} (closest spelling)"
            )
    fixed = list(corrections)
    if fixed:
        score -= 4 * len(fixed)
        reasons.append(
            "Spelling corrected: " + ", ".join(f"{wrong} \u2192 {right}" for wrong, right in fixed)
        )
    if plan.metric == "unknown":
        score -= 45
        reasons.append("No business metric was identified")
    if plan.entity == "unknown":
        score -= 15
    if not has_sql:
        score -= 45
        reasons.append("No governed query matches this exact shape")
    if contextual:
        score -= 5
        reasons.append("Continues the previous question")
    if reinterpreted:
        score -= 18
        reasons.append("The AI rephrased the question before planning")
    if ai_generated:
        score -= 8
        reasons.append("SQL written by the AI and checked by the validator")
    score = max(0, min(100, score))
    return Confidence(level_for(score), score, reasons)


def decide_route(
    plan: QuestionPlan,
    *,
    has_governed_sql: bool,
    llm_available: bool,
    mode: str = "llm_first",
) -> RouteDecision:
    complexity: Literal["simple", "complex"] = "complex" if is_complex(plan) else "simple"
    if not has_governed_sql:
        if llm_available:
            return RouteDecision(
                "llm_reasoning",
                complexity,
                "No governed template for this shape; the AI drafts SQL from the plan "
                "and the validator must approve it",
                llm_available=True,
            )
        return RouteDecision(
            "clarify",
            complexity,
            "No governed query for this shape and no AI model configured",
        )
    if complexity == "complex" and llm_available and mode == "llm_first":
        return RouteDecision(
            "llm_reasoning",
            complexity,
            "Complex analytical question: planner spec + AI reasoning, validated; "
            "governed SQL is the safety net",
            llm_available=True,
            governed_fallback=True,
        )
    return RouteDecision(
        "semantic",
        complexity,
        "Understood with high confidence: governed semantic-layer SQL"
        if complexity == "simple"
        else "Complex question compiled by the governed semantic planner",
        llm_available=llm_available,
    )


_METRIC_WORD = {
    "revenue": "revenue",
    "units": "units sold",
    "orders": "orders",
    "average_selling_price": "average selling price",
    "premium": "written premium",
    "earned_premium": "earned premium",
    "claims_incurred": "claims incurred",
    "claims_paid": "claims paid",
    "claim_count": "claim count",
    "loss_ratio": "loss ratio",
    "severity": "claim severity",
    "frequency": "claim frequency",
}
_WHO = re.compile(r"^\s*(who|which)\b", re.I)


def interpretation_options(
    plan: QuestionPlan | None,
    *,
    industry: Industry,
    question: str = "",
    limit: int = 4,
) -> list[str]:
    """Concrete readings of an unclear question, each answerable by the semantic layer."""
    if plan is not None and not scope_label(plan) and plan.metric in _METRIC_WORD:
        metric = _METRIC_WORD[plan.metric]
        if industry is Industry.AUTOMOTIVE:
            subjects = ("brand", "model", "dealer", "salesperson")
        else:
            subjects = ("product", "agent", "region", "channel")
        if plan.intent == "ranking" or _WHO.search(question):
            options = [f"Top {subject} by {metric}" for subject in subjects]
        else:
            options = [
                f"{metric.capitalize()} by month",
                f"{metric.capitalize()} by year",
                f"{metric.capitalize()} by {subjects[0]}",
                f"{metric.capitalize()} by region",
            ]
        return options[:limit]
    return plan_suggestions(plan, industry=industry, question=question, limit=limit)
