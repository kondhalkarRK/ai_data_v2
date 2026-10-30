"""Follow-up guard: a short message reuses the prior plan only when it names something real.

"Real" means a value from the industry's value dictionary, a measure/dimension/glossary
term from the industry's semantic pack, a date phrase, or a recognised plan operation.
Anything else must not run SQL on the prior plan.
"""

from __future__ import annotations

import re
from typing import Any

from app.core.config import Industry, Settings
from app.services.chat.conversation_context import is_contextual_followup
from app.services.chat.conversation_memory import SessionMemory, follow_up_context_status
from app.services.chat.intents import is_followup
from app.services.chat.time_periods import parse_period
from app.services.chat.value_dictionary import ValueDictionarySnapshot

_OPERATION = re.compile(
    r"\b(?:break\s+(?:it|this|that)?\s*down|(?:top|bottom|first|last)\s+\d{1,3}|"
    r"add\s+\w+|also\s+\w+|include\s+\w+|same\s+(?:for|but|thing)|instead|"
    r"compare\s+(?:with|to|against)|only\s+\w+|exclud(?:e|ing)\s+\w+)\b",
    re.I,
)
_DATE = re.compile(
    r"\b(?:20[12]\d|q[1-4]|fy\s?\d{2,4}|(?:last|previous|prior|this|next)\s+"
    r"(?:day|week|month|quarter|year)|ytd|mtd|qtd|yesterday|today|"
    r"january|february|march|april|may|june|july|august|september|october|"
    r"november|december|jan|feb|mar|apr|jun|jul|aug|sep|sept|oct|nov|dec)\b",
    re.I,
)
_GRAIN = ("day", "week", "month", "quarter", "year")
_WORD = re.compile(r"[a-z0-9][a-z0-9&'\-]*", re.I)


_VOCAB_CACHE: dict[int, frozenset[str]] = {}


def _pack_vocabulary(pack: Any) -> frozenset[str]:
    """Lower-cased measure, dimension and glossary phrases from one industry's pack."""
    if pack is None:
        return frozenset(_GRAIN)
    cached = _VOCAB_CACHE.get(id(pack))
    if cached is not None:
        return cached
    vocab = _build_pack_vocabulary(pack)
    if len(_VOCAB_CACHE) > 16:
        _VOCAB_CACHE.clear()
    _VOCAB_CACHE[id(pack)] = vocab
    return vocab


def _build_pack_vocabulary(pack: Any) -> frozenset[str]:
    terms: set[str] = set(_GRAIN)
    model = getattr(pack, "model", None)
    glossary = getattr(pack, "glossary", None)
    for name, measure in (getattr(model, "measures", None) or {}).items():
        terms.update({name.replace("_", " "), measure.display_name, *measure.synonyms})
    for name, dimension in (getattr(model, "dimensions", None) or {}).items():
        terms.update({name.replace("_", " "), dimension.display_name, *dimension.synonyms})
    for name, term in (getattr(glossary, "terms", None) or {}).items():
        if term.maps_to_measure or term.maps_to_dimension or term.maps_to_attribute:
            terms.update({name, *(term.synonyms or [])})
    return frozenset(t.strip().lower() for t in terms if t and t.strip())


def _mentions_pack_term(question: str, pack: Any) -> bool:
    text = " " + " ".join(_WORD.findall(question.lower())) + " "
    return any(f" {term} " in text for term in _pack_vocabulary(pack))


def _value_matches(question: str, snapshot: ValueDictionarySnapshot, pack: Any) -> list[str]:
    resolution = snapshot.resolve(question, pack=pack)
    return [
        match.entry.canonical
        for match in resolution.matches
        if getattr(match, "method", "") != "fuzzy"
    ]


def data_vocabulary_hit(question: str, snapshot: ValueDictionarySnapshot, pack: Any) -> bool:
    """True when the text names any governed value, measure, dimension or glossary term."""
    return bool(_value_matches(question, snapshot, pack)) or _mentions_pack_term(question, pack)


def needs_guard(
    question: str,
    session_memory: SessionMemory,
    settings: Settings,
    prior_state: dict[str, Any] | None,
    *,
    industry: Industry,
) -> bool:
    if not prior_state:
        return False
    status = follow_up_context_status(
        session_memory, question, settings, industry=industry
    )
    if status == "active":
        return True
    return is_contextual_followup(question) or is_followup(question)


def follow_up_guard_allows_sql(
    *,
    question: str,
    session_memory: SessionMemory,
    settings: Settings,
    prior_state: dict[str, Any] | None,
    snapshot: ValueDictionarySnapshot,
    pack: Any | None,
    industry: Industry,
) -> tuple[bool, str | None]:
    """Return (allowed, interpretation). Long, self-contained questions are not guarded."""
    q = (question or "").strip()
    if not needs_guard(q, session_memory, settings, prior_state, industry=industry):
        return True, None
    if len(q.split()) > 8:
        return True, None
    metric = str((prior_state or {}).get("metric") or "").replace("_", " ")
    values = _value_matches(q, snapshot, pack)
    if values:
        return True, f"Showing {metric or 'results'} for {', '.join(values[:3])}"
    if _mentions_pack_term(q, pack) or _OPERATION.search(q):
        return True, f"Applying \u201c{q.strip(' ?.!')}\u201d to {metric or 'the previous question'}"
    if _DATE.search(q) or parse_period(q) is not None:
        return True, f"Showing {metric or 'results'} for {q.strip(' ?.!')}"
    return False, None
