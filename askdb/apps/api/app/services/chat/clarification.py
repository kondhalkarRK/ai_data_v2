"""Turn unanswerable or failed questions into clarifications with next-best questions.

Business users never see raw pipeline errors. Every dead end becomes a short
explanation plus "Did you mean" questions built from what was understood
(brand, metric, filters), so one click gets them to an answer.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Literal

from app.core.config import Industry
from app.services.chat.question_understanding import QuestionPlan

ClarificationKind = Literal["clarify", "unsupported", "unresolved", "recovery"]

_SCOPE_COLUMNS = ("make", "model", "car_type", "engine_type", "city", "region_name", "colour_name")
_METRIC_LABEL = {
    "revenue": "revenue",
    "units": "units sold",
    "orders": "orders",
    "average_selling_price": "average selling price",
    "premium": "written premium",
    "earned_premium": "earned premium",
    "claims_incurred": "claims incurred",
    "claim_count": "claim count",
    "loss_ratio": "loss ratio",
    "severity": "claim severity",
    "frequency": "claim frequency",
    "approval_rate": "approval rate",
    "renewal_rate": "renewal rate",
}


@dataclass(slots=True)
class Clarification:
    kind: ClarificationKind
    title: str
    message: str
    options: list[str] = field(default_factory=list)

    def payload(self, **extra: Any) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "title": self.title,
            "question": self.message,
            "options": list(self.options),
            **extra,
        }


def _values(plan: QuestionPlan | None, column: str) -> list[str]:
    if plan is None:
        return []
    return [
        value
        for item in plan.filters
        if item.column.rsplit(".", 1)[-1] == column
        for value in item.all_values
    ]


def scope_label(plan: QuestionPlan | None) -> str:
    """Business scope in words: "MG", "Maruti Suzuki SUV", "MG and Kia in Mumbai"."""
    if plan is None:
        return ""
    subject: list[str] = []
    for column in ("make", "model", "engine_type", "car_type", "colour_name"):
        values = _values(plan, column)
        if values:
            subject.append(" and ".join(values))
    places = _values(plan, "city") or _values(plan, "region_name")
    text = " ".join(subject)
    if places:
        text = f"{text} in {' and '.join(places)}".strip()
    return text


def interpretation(plan: QuestionPlan | None) -> str:
    """How the question was understood, e.g. "MG revenue by year in Mumbai"."""
    if plan is None:
        return "your question"
    metric = _METRIC_LABEL.get(plan.metric, "sales")
    subject = " ".join(
        " and ".join(values)
        for column in ("make", "model", "engine_type", "car_type")
        if (values := _values(plan, column))
    )
    text = f"{subject} {metric}".strip()
    dims = [d.replace("_", " ") for d in plan.dimensions]
    if dims:
        text += " by " + " and ".join(dims)
    places = _values(plan, "city") or _values(plan, "region_name")
    if places:
        text += f" in {' and '.join(places)}"
    if plan.year_filter:
        text += f" for {plan.year_filter}"
    return text[:1].upper() + text[1:] if text else "your question"


def plan_suggestions(
    plan: QuestionPlan | None,
    *,
    industry: Industry,
    question: str = "",
    limit: int = 4,
) -> list[str]:
    """Next-best questions that keep the user's scope ("MG sales by year")."""
    if industry is Industry.INSURANCE:
        options = [
            "Written premium by month",
            "Loss ratio by month",
            "Claim count by status",
            "Top agents by premium",
        ]
        return _dedupe(options, question, limit)
    scope = scope_label(plan)
    makes = _values(plan, "make")
    if scope:
        options = [
            f"{scope} sales by month",
            f"{scope} sales by year",
            f"{scope} revenue by year",
            f"{scope} units sold by year",
        ]
        if len(makes) == 1:
            options.append(f"Top selling {makes[0]} model")
            options.append(f"{makes[0]} market share by year")
        elif len(makes) > 1:
            options.insert(0, f"Compare {' and '.join(makes)} sales by year")
    else:
        options = [
            "Revenue by month",
            "Top brand by revenue",
            "Maruti Suzuki sales by year",
            "Market share by brand",
            "SUV sales by year",
        ]
    return _dedupe(options, question, limit)


def _dedupe(options: list[str], question: str, limit: int) -> list[str]:
    asked = _norm(question)
    out: list[str] = []
    for option in options:
        option = re.sub(r"\s+", " ", option).strip()
        option = option[:1].upper() + option[1:]
        if _norm(option) == asked or option in out:
            continue
        out.append(option)
    return out[:limit]


def _norm(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (text or "").casefold()).strip()


def assess_resolution(
    question: str,
    plan: QuestionPlan,
    resolution: Any,
    *,
    industry: Industry,
    brands: list[str] | None = None,
) -> Clarification | None:
    """Ask instead of answering the wrong question when a named term cannot be used."""
    unsupported = list(getattr(resolution, "unsupported", None) or [])
    if unsupported:
        term = unsupported[0]
        scope = scope_label(plan)
        options = [
            _scoped(alternative, scope)
            for alternative in (term.alternatives or ())
        ] or plan_suggestions(plan, industry=industry, question=question)
        return Clarification(
            kind="unsupported",
            title="That isn't in the sales data yet",
            message=term.message,
            options=_dedupe(options, question, 4),
        )

    unresolved = list(getattr(resolution, "unresolved", None) or [])
    if not unresolved:
        return None
    term = unresolved[0]
    metric_word = "revenue" if re.search(r"\brevenue\b", question, re.I) else "sales"
    if term.suggestions:
        names = list(term.suggestions)
        message = (
            f"I couldn't find \u201c{term.text}\u201d in the data. "
            f"Did you mean {_join_or(names[:3])}?"
        )
        options = [f"{name} {metric_word} by year" for name in names[:3]]
    else:
        known = ", ".join((brands or [])[:6])
        message = (
            f"\u201c{term.text}\u201d isn't a brand, model or city in the sales data."
            + (f" Available brands include {known}." if known else "")
        )
        options = [f"{name} {metric_word} by year" for name in (brands or [])[:3]]
        options.append("Top brand by revenue")
    return Clarification(
        kind="unresolved",
        title="Did you mean…",
        message=message,
        options=_dedupe(options, question, 4),
    )


def _scoped(alternative: str, scope: str) -> str:
    if not scope or re.search(r"\bbrand\b|\bby\s+fuel\b", alternative, re.I):
        return alternative
    return f"{scope} {alternative[:1].lower()}{alternative[1:]}"


def _join_or(items: list[str]) -> str:
    if len(items) <= 1:
        return "".join(items)
    return ", ".join(items[:-1]) + f" or {items[-1]}"


def recovery_for_failure(
    category: str,
    plan: QuestionPlan | None,
    *,
    industry: Industry,
    question: str,
) -> Clarification:
    """A recoverable answer for any failed stage — never a raw technical error."""
    understood = interpretation(plan)
    if category in {"llm", "circuit_open"}:
        message = (
            f"I understood this as \u201c{understood}\u201d, but it needs the AI model, "
            "which isn't available right now. These governed questions answer instantly:"
        )
    elif category == "timeout":
        message = (
            f"\u201c{understood}\u201d took too long over the full history. "
            "A narrower period or a single brand will be faster:"
        )
    elif category == "semantic":
        message = (
            "I couldn't match that to a business metric. "
            "Try one of these, or name a metric such as revenue, units sold or orders:"
        )
    else:
        message = (
            f"I understood this as \u201c{understood}\u201d but couldn't build a reliable "
            "query for that exact shape. Here are the closest questions I can answer:"
        )
    return Clarification(
        kind="recovery",
        title="Here's what I can answer",
        message=message,
        options=plan_suggestions(plan, industry=industry, question=question),
    )


def resolution_notes(resolution: Any) -> list[str]:
    """Plain-language notes for non-literal matches ("Suzuki" -> Maruti Suzuki)."""
    notes: list[str] = []
    for match in getattr(resolution, "matches", None) or []:
        if match.method == "exact":
            continue
        label = match.entry.domain.lower()
        if match.method == "fuzzy":
            notes.append(
                f"Interpreted \u201c{match.text}\u201d as {match.entry.canonical} ({label}) — closest match."
            )
        elif match.text.casefold() != match.entry.canonical.casefold():
            notes.append(f"\u201c{match.text}\u201d means {match.entry.canonical} ({label}).")
    return notes
