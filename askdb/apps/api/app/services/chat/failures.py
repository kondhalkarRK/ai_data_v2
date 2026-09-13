"""Classify NLQ failures for honest, actionable UI messages."""

from __future__ import annotations

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
        "SQL Generation Failed",
        reason[:240] or "The generated SQL could not be validated.",
        retryable=True,
    )


def classify_database(exc_or_message: str) -> FailureInfo:
    text = (exc_or_message or "").lower()
    if "timeout" in text or "canceling statement" in text or "statement_timeout" in text:
        return FailureInfo(
            "database",
            "Database Execution Failed",
            "Query exceeded execution timeout.",
            retryable=True,
        )
    if "column" in text and ("does not exist" in text or "undefined" in text):
        return FailureInfo("sql_generation", "SQL Generation Failed", exc_or_message[:240], retryable=True)
    return FailureInfo(
        "database",
        "Database Execution Failed",
        exc_or_message[:240] or "Query failed during execution.",
        retryable=True,
    )


def classify_semantic(term: str) -> FailureInfo:
    return FailureInfo(
        "semantic",
        "Metric Not Found",
        f'No matching business metric found for: "{term}"',
        retryable=False,
    )


def classify_ambiguous(message: str) -> FailureInfo:
    return FailureInfo("ambiguous", "Ambiguous Question", message[:240], retryable=False)
