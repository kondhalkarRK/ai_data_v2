"""Classify NLQ failures for honest, actionable UI messages."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

FailureCategory = Literal[
    "llm",
    "sql_generation",
    "database",
    "semantic",
    "ambiguous",
    "timeout",
    "circuit_open",
    "cancelled",
    "unknown",
]


@dataclass(frozen=True, slots=True)
class FailureInfo:
    category: FailureCategory
    title: str
    reason: str
    retryable: bool = True

    def to_dict(self) -> dict[str, object]:
        return {
            "category": self.category,
            "title": self.title,
            "reason": self.reason,
            "retryable": self.retryable,
            "message": f"{self.title}: {self.reason}",
        }


def classify_llm_failure(exc_or_message: str) -> FailureInfo:
    text = (exc_or_message or "").lower()
    if "timeout" in text or "timed out" in text:
        return FailureInfo("llm", "AI Service Issue", "Timeout", retryable=True)
    if "circuit" in text or "degraded" in text:
        return FailureInfo(
            "circuit_open",
            "AI Service Degraded",
            "The language model provider is temporarily unavailable.",
            retryable=True,
        )
    if "token" in text or "context length" in text:
        return FailureInfo("llm", "AI Service Issue", "Token / context limit exceeded", retryable=False)
    if "json" in text or "parse" in text or "invalid" in text:
        return FailureInfo("llm", "AI Service Issue", "Invalid model response", retryable=True)
    return FailureInfo("llm", "AI Service Issue", exc_or_message[:240] or "Unavailable", retryable=True)


def classify_sql_validation(reason: str) -> FailureInfo:
    return FailureInfo(
        "sql_generation",
        "SQL Validation Error",
        (
            f"{reason[:180] or 'The generated SQL could not be validated.'} "
            "Try a glossary phrase such as revenue by month, orders per year, or top salesperson."
        ),
        retryable=True,
    )


def classify_database(exc_or_message: str) -> FailureInfo:
    text = (exc_or_message or "").lower()
    if "timeout" in text or "canceling statement" in text or "statement_timeout" in text:
        return FailureInfo(
            "timeout",
            "Timeout Error",
            "Query exceeded the execution timeout. Narrow the date range or add a filter such as region or product.",
            retryable=True,
        )
    if "column" in text and ("does not exist" in text or "undefined" in text):
        return FailureInfo(
            "sql_generation",
            "SQL Validation Error",
            "A field in the query is not in the business glossary. Rephrase with revenue, orders, units, or a known dimension.",
            retryable=True,
        )
    if "does not exist" in text and "relation" in text:
        return FailureInfo(
            "semantic",
            "Semantic Mapping Error",
            "The business term did not map to a known table. Use a metric from the glossary, such as revenue or orders.",
            retryable=False,
        )
    return FailureInfo(
        "database",
        "SQL Execution Error",
        "The database could not run this question. Try revenue by month, orders per year, or top salesperson.",
        retryable=True,
    )


def classify_semantic(term: str) -> FailureInfo:
    return FailureInfo(
        "semantic",
        "Semantic Mapping Error",
        f'No matching business metric found for: "{term}". Try revenue, orders, units, or a glossary name.',
        retryable=False,
    )


def classify_ambiguous(message: str) -> FailureInfo:
    return FailureInfo("ambiguous", "Ambiguous Question", message[:240], retryable=False)


def propose_sql_repair(sql: str, error: str) -> str | None:
    """Deterministic repair for common glossary mismatches. Returns None if unchanged."""
    if not sql or not error:
        return None
    lowered = error.lower()
    original = sql.strip()
    repaired = original.rstrip(";")
    replacements = (
        ("order_date", "sales_date"),
        ("fact_orders", "fact_sales"),
        ("dim_vehicle", "dim_carline"),
    )
    for bad, good in replacements:
        if bad in lowered and bad in repaired.lower():
            repaired = re.sub(rf"\b{bad}\b", good, repaired, flags=re.I)
    if repaired == original:
        return None
    return repaired
