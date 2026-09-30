"""How well AI Chat understands each catalogued value. Pure functions."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

Readiness = Literal["ai_ready", "needs_review", "missing_synonyms", "low_confidence"]

READINESS_LABEL: dict[Readiness, str] = {
    "ai_ready": "AI Ready",
    "needs_review": "Needs Review",
    "missing_synonyms": "Missing Synonyms",
    "low_confidence": "Low Confidence",
}

# Domains where users commonly shorten multi-word names ("Grand Vitara" -> "Vitara").
_SHORTHAND_DOMAINS = frozenset({"make", "model", "product", "dealer_name"})


@dataclass(slots=True)
class ValueReadiness:
    status: Readiness
    notes: list[str] = field(default_factory=list)
    rule: list[str] = field(default_factory=list)

    @property
    def label(self) -> str:
        return READINESS_LABEL[self.status]


def assess_value(
    value: str,
    *,
    domain_key: str,
    domain_ai_known: bool,
    in_dictionary: bool,
    is_new: bool,
    phrases: dict[str, list[str]],
    shadowed_by: str | None = None,
    ambiguous_with: list[str] | None = None,
    generic_word: bool = False,
    max_values: int = 0,
) -> ValueReadiness:
    """Status plus the resolution rule AI Chat actually applies to this value."""
    curated = phrases.get("synonym", [])
    partial = phrases.get("alias", [])
    glossary = phrases.get("glossary", [])
    rule: list[str] = []
    if in_dictionary and domain_ai_known:
        rule.append(f"Exact name \u201c{value}\u201d")
        if curated:
            rule.append("Curated synonyms: " + ", ".join(curated))
        if partial:
            rule.append("Distinctive word: " + ", ".join(partial))
        if glossary:
            rule.append("Glossary terms: " + ", ".join(glossary))
        if generic_word:
            rule.append("Only with the brand named (everyday word)")
        elif len(value) >= 4:
            rule.append("Spelling tolerance (close misspellings resolve)")

    if not domain_ai_known:
        return ValueReadiness(
            "needs_review",
            ["Column is watched by the catalog but not in the AI value dictionary yet"],
            ["Not resolvable by name in AI Chat"],
        )
    if not in_dictionary:
        return ValueReadiness(
            "needs_review",
            [
                f"Beyond the AI dictionary cap of {max_values} values for this column; "
                "found by the targeted lookup when a question names it"
            ],
            ["Targeted metadata lookup on demand"],
        )
    if shadowed_by:
        return ValueReadiness(
            "low_confidence",
            [f"Same name as {shadowed_by}; AI Chat resolves that first"],
            rule,
        )
    if ambiguous_with:
        return ValueReadiness(
            "low_confidence",
            [f"Same name as {', '.join(ambiguous_with)}; AI Chat asks which one"],
            rule,
        )
    if generic_word:
        return ValueReadiness(
            "low_confidence", ["Everyday word; resolves only when the brand is named"], rule
        )
    if is_new and not curated:
        return ValueReadiness("needs_review", ["New value", "No synonyms configured"], rule)
    if domain_key in _SHORTHAND_DOMAINS and len(value.split()) >= 2 and not (curated or partial):
        return ValueReadiness(
            "missing_synonyms",
            ["Multi-word name without a short form users might type"],
            rule,
        )
    return ValueReadiness("ai_ready", [], rule)
