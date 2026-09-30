"""Business entity resolution for AI Chat.

Every business value (brand, model, body type, fuel type, city, ...) has one
canonical spelling plus synonyms. A question is resolved in a fixed cascade
before any SQL is planned:

    exact canonical -> curated synonym -> fuzzy (typos) -> partial-name alias -> glossary

Terms the warehouse cannot answer (CNG, profit) and names that match nothing
are reported instead of being silently dropped, so the planner can ask a
"Did you mean" question rather than returning an unfiltered answer.
"""

from __future__ import annotations

import difflib
import re
from collections.abc import Iterable
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

import yaml

from app.core.config import APP_ROOT, Industry
from app.services.chat.question_understanding import ExtractedFilter
from app.services.chat.spell import edit_distance

MatchMethod = Literal["exact", "synonym", "fuzzy", "alias", "glossary"]

_METHOD_RANK: dict[str, int] = {"exact": 0, "synonym": 1, "fuzzy": 2, "alias": 3, "glossary": 4}
_METHOD_CONFIDENCE: dict[str, float] = {
    "exact": 1.0,
    "synonym": 0.97,
    "alias": 0.9,
    "glossary": 0.9,
}
# Lower wins when two domains claim the same words ("Nagpur" is a city and a region).
_DOMAIN_PRIORITY: dict[str, int] = {
    "make": 0,
    "model": 1,
    "car_type": 2,
    "engine_type": 3,
    "city": 4,
    "state_code": 5,
    "region_name": 6,
    "colour_name": 7,
}
_FUZZY_MIN_LENGTH = 4
_SUGGESTION_RATIO = 0.72
_STOPWORDS = frozenset(
    """
    a an the of for in on at by to from with and or vs versus v what whats what's which who
    how much many show me give tell list get find display please can could would you i we
    is are was were be been do does did has have had this that these those it its their
    our my your all any each every per wise across between during over within than then
    about around only just also both either same other more most less least top bottom
    best worst highest lowest high low number count amount value values total overall
    compare comparison compared versus trend trends trending growth change up down
    last previous prior next current this year years yearly annual annually month months
    monthly quarter quarters quarterly week weeks weekly day days daily ytd mtd qtd
    date time period so far since till until ago now today sales sale sold selling sell
    revenue revenues income turnover units unit volume volumes qty quantity orders order
    transactions performance performing perform analysis breakdown split distribution
    share market brand brands make makes manufacturer manufacturers model models car cars
    vehicle vehicles segment segments type types body style fuel engine powertrain
    city cities region regions state states location locations dealer dealers
    dealership dealerships salesperson salespeople rep reps average avg mean median
    rate ratio percent percentage pct contribution running cumulative moving rolling
    trend chart graph table plot line bar view data report numbers figures kpi kpis
    rank ranking ranked leading popular much india indian wise business line lines
    target targets fiscal financial half first second third fourth past trailing recent
    latest
    """.split()  # noqa: SIM905
)
# Period words: quarters, halves, fiscal years and month names are time, never names.
_TIME_TOKEN = re.compile(
    r"(?:q[1-4]|h[12]|fy\d{0,4}|20\d\d|jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|"
    r"june?|july?|aug(?:ust)?|sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)"
)
_MAKE_CUE = frozenset({"model", "models", "car", "cars", "suv", "sedan", "hatchback"})


@dataclass(frozen=True, slots=True)
class CatalogEntry:
    domain: str  # business label, e.g. "Make"
    column: str  # qualified physical column, e.g. automotive.dim_carline.make
    canonical: str
    synonyms: tuple[str, ...] = ()
    frequency: int = 0

    @property
    def key(self) -> str:
        return self.column.rsplit(".", 1)[-1]

    @property
    def priority(self) -> int:
        return _DOMAIN_PRIORITY.get(self.key, 10)


@dataclass(frozen=True, slots=True)
class EntityMatch:
    entry: CatalogEntry
    text: str
    method: MatchMethod
    confidence: float
    start: int
    end: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "text": self.text,
            "canonical": self.entry.canonical,
            "domain": self.entry.domain,
            "column": self.entry.column,
            "method": self.method,
            "confidence": round(self.confidence, 2),
        }


@dataclass(frozen=True, slots=True)
class UnresolvedTerm:
    text: str
    suggestions: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class UnsupportedTerm:
    term: str
    kind: str
    message: str
    alternatives: tuple[str, ...] = ()


@dataclass(slots=True)
class Resolution:
    matches: list[EntityMatch] = field(default_factory=list)
    unresolved: list[UnresolvedTerm] = field(default_factory=list)
    unsupported: list[UnsupportedTerm] = field(default_factory=list)

    @property
    def low_confidence(self) -> list[EntityMatch]:
        return [match for match in self.matches if match.method == "fuzzy"]

    def values_for(self, key: str) -> list[str]:
        """Canonical values for one column key (``make``, ``city``) in question order."""
        return list(
            dict.fromkeys(match.entry.canonical for match in self.matches if match.entry.key == key)
        )

    def filters(self) -> list[ExtractedFilter]:
        grouped: dict[str, list[EntityMatch]] = {}
        for match in sorted(self.matches, key=lambda item: item.start):
            grouped.setdefault(match.entry.column, []).append(match)
        out: list[ExtractedFilter] = []
        for column, items in grouped.items():
            values = tuple(dict.fromkeys(item.entry.canonical for item in items))
            weakest = max(items, key=lambda item: _METHOD_RANK[item.method])
            domain = items[0].entry.domain
            multi = len(values) > 1
            out.append(
                ExtractedFilter(
                    column=column,
                    operator="IN" if multi else "=",
                    value=values[0],
                    label=(
                        f"{domain} in ({', '.join(values)})" if multi else f"{domain} = {values[0]}"
                    ),
                    source="entity_resolver",
                    values=values if multi else (),
                    match_type=weakest.method,
                    matched_text=", ".join(dict.fromkeys(item.text for item in items)),
                    confidence=min(item.confidence for item in items),
                )
            )
        return out

    def trace(self) -> list[dict[str, Any]]:
        return [match.to_dict() for match in sorted(self.matches, key=lambda item: item.start)]


@dataclass(frozen=True, slots=True)
class ChatVocabulary:
    unavailable: tuple[tuple[tuple[str, ...], str, str, tuple[str, ...]], ...] = ()
    generic_value_words: frozenset[str] = frozenset()
    known_words: frozenset[str] = frozenset()


def normalize(text: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^\w]+", " ", (text or "").casefold())).strip()


@lru_cache(maxsize=8)
def load_chat_vocabulary(industry: Industry, packs_dir: str | None = None) -> ChatVocabulary:
    """Chat-only rules from ``semantic/packs/<industry>/chat_vocabulary.yaml``."""
    root = Path(packs_dir) if packs_dir else APP_ROOT / "semantic" / "packs"
    path = root / industry.value / "chat_vocabulary.yaml"
    if not path.is_file():
        return ChatVocabulary()
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    unavailable = tuple(
        (
            tuple(normalize(str(term)) for term in item.get("terms") or [] if str(term).strip()),
            str(item.get("kind") or "metric"),
            " ".join(str(item.get("message") or "").split()),
            tuple(str(alt) for alt in item.get("alternatives") or []),
        )
        for item in raw.get("unavailable") or []
    )
    return ChatVocabulary(
        unavailable=unavailable,
        generic_value_words=frozenset(normalize(str(w)) for w in raw.get("generic_value_words") or []),
        known_words=frozenset(normalize(str(w)) for w in raw.get("known_words") or []),
    )


_GENERIC_SUFFIXES = re.compile(
    r"\b(metro|metropolitan|hub|belt|circle|coast|coastal|central|west|east|north|south|city|tri)\b"
)
_CORPORATE_WORDS = frozenset(
    {"motor", "motors", "india", "limited", "ltd", "cars", "auto", "automobiles", "company"}
)


def _partial_aliases(entry: CatalogEntry, catalog: Iterable[CatalogEntry]) -> set[str]:
    """Distinctive words of a multi-word canonical ("Grand Vitara" -> "vitara")."""
    canonical = normalize(entry.canonical)
    aliases: set[str] = set()
    if entry.key == "region_name":
        simplified = re.sub(r"\s+", " ", _GENERIC_SUFFIXES.sub(" ", canonical)).strip()
        if simplified and simplified != canonical and len(simplified) >= 3:
            aliases.add(simplified)
    words = canonical.split()
    if len(words) < 2 or entry.key not in {"make", "model"}:
        return aliases
    siblings = [normalize(other.canonical) for other in catalog if other.column == entry.column]
    for word in words:
        if len(word) < 4 or word in _STOPWORDS or word in _CORPORATE_WORDS:
            continue
        owners = [name for name in siblings if word in name.split()]
        if len(owners) == 1:
            aliases.add(word)
    return aliases


@dataclass(slots=True)
class _Form:
    tokens: tuple[str, ...]
    entry: CatalogEntry
    method: MatchMethod


def _index_forms(
    catalog: tuple[CatalogEntry, ...],
    glossary_entries: tuple[tuple[CatalogEntry, tuple[str, ...]], ...],
) -> dict[str, list[_Form]]:
    forms: dict[str, list[_Form]] = {"exact": [], "synonym": [], "alias": [], "glossary": []}
    for entry in catalog:
        canonical = normalize(entry.canonical)
        if canonical:
            forms["exact"].append(_Form(tuple(canonical.split()), entry, "exact"))
        for synonym in entry.synonyms:
            norm = normalize(synonym)
            if norm and norm != canonical:
                forms["synonym"].append(_Form(tuple(norm.split()), entry, "synonym"))
        for alias in _partial_aliases(entry, catalog):
            forms["alias"].append(_Form(tuple(alias.split()), entry, "alias"))
    for entry, phrases in glossary_entries:
        for phrase in phrases:
            norm = normalize(phrase)
            if norm:
                forms["glossary"].append(_Form(tuple(norm.split()), entry, "glossary"))
    return forms


def _short_form_allowed(form: _Form) -> bool:
    """Two-letter tokens are only trusted when curated or a real brand ("MG", "EV")."""
    text = " ".join(form.tokens)
    if len(text) >= 3:
        return True
    return form.method in {"synonym", "glossary"} or form.entry.key == "make"


def _glossary_entries(
    pack: Any | None,
    catalog: tuple[CatalogEntry, ...],
) -> tuple[tuple[CatalogEntry, tuple[str, ...]], ...]:
    """Glossary terms whose SQL is a single value filter (``car_type = 'SUV'``)."""
    glossary = getattr(pack, "glossary", None)
    terms = getattr(glossary, "terms", None) or {}
    columns = {entry.column.casefold(): entry for entry in catalog}
    by_leaf: dict[str, str] = {}
    for entry in catalog:
        by_leaf.setdefault(entry.column.split(".", 1)[-1].casefold(), entry.column)
    out: list[tuple[CatalogEntry, tuple[str, ...]]] = []
    for name, term in terms.items():
        expression = str(getattr(term, "sql_expression", "") or "")
        match = re.fullmatch(r"\s*([\w.]+)\s*=\s*'([^']+)'\s*", expression)
        if not match:
            continue
        column = match.group(1).casefold()
        qualified = column if column in columns else by_leaf.get(column.split(".", 1)[-1])
        if qualified is None:
            continue
        domain = columns.get(qualified.casefold())
        entry = CatalogEntry(
            domain=domain.domain if domain else qualified.rsplit(".", 1)[-1],
            column=domain.column if domain else qualified,
            canonical=match.group(2),
        )
        phrases = (name, *(str(s) for s in getattr(term, "synonyms", None) or []))
        out.append((entry, phrases))
    return tuple(out)


class EntityResolver:
    """Resolve business values in a question against one industry catalog."""

    def __init__(
        self,
        catalog: Iterable[CatalogEntry],
        *,
        pack: Any | None = None,
        vocabulary: ChatVocabulary | None = None,
    ) -> None:
        self.catalog = tuple(catalog)
        self.vocabulary = vocabulary or ChatVocabulary()
        self._protected: frozenset[str] | None = None
        self._forms = _index_forms(self.catalog, _glossary_entries(pack, self.catalog))
        self._max_len = max(
            (len(form.tokens) for forms in self._forms.values() for form in forms), default=1
        )
        self._by_tokens: dict[str, dict[tuple[str, ...], list[_Form]]] = {}
        for method, forms in self._forms.items():
            index: dict[tuple[str, ...], list[_Form]] = {}
            for form in forms:
                index.setdefault(form.tokens, []).append(form)
            self._by_tokens[method] = index
        self._fuzzy_targets: list[_Form] = [
            form
            for form in (*self._forms["exact"], *self._forms["synonym"])
            if len(" ".join(form.tokens)) >= _FUZZY_MIN_LENGTH
            and not self._is_generic(form.entry)
        ]

    def _is_generic(self, entry: CatalogEntry) -> bool:
        return entry.key == "model" and normalize(entry.canonical) in self.vocabulary.generic_value_words

    def _is_vocabulary(self, token: str) -> bool:
        return (
            token in _STOPWORDS
            or token in self.vocabulary.known_words
            or token.isdigit()
            or len(token) < 2
            or bool(_TIME_TOKEN.fullmatch(token))
        )

    def resolve(self, question: str) -> Resolution:
        tokens = normalize(question).split()
        resolution = Resolution()
        if not tokens:
            return resolution
        claimed = [False] * len(tokens)

        self._unsupported(tokens, claimed, resolution)
        # 1. exact canonical and 2. curated synonyms, longest phrase first.
        self._deterministic(tokens, claimed, resolution, ("exact", "synonym"))
        # 3. fuzzy spelling ("Hundai", "Marutti") on words nothing else claimed.
        self._fuzzy(tokens, claimed, resolution)
        # 4. distinctive partial names ("Vitara") and 5. glossary value terms.
        self._deterministic(tokens, claimed, resolution, ("alias",))
        self._deterministic(tokens, claimed, resolution, ("glossary",))
        self._drop_generic_without_context(tokens, claimed, resolution)
        self._unresolved(tokens, claimed, resolution)
        return resolution

    def _unsupported(self, tokens: list[str], claimed: list[bool], out: Resolution) -> None:
        text = " ".join(tokens)
        candidates = sorted(
            (
                (term, kind, message, alternatives)
                for terms, kind, message, alternatives in self.vocabulary.unavailable
                for term in terms
            ),
            key=lambda item: len(item[0]),
            reverse=True,
        )
        reported: set[str] = set()
        for term, kind, message, alternatives in candidates:
            found = re.search(rf"(?<!\w){re.escape(term)}(?!\w)", text)
            if not found:
                continue
            start = len(text[: found.start()].split())
            span = range(start, min(len(tokens), start + len(term.split())))
            if any(claimed[index] for index in span):
                continue
            for index in span:
                claimed[index] = True
            if message not in reported:
                reported.add(message)
                out.unsupported.append(UnsupportedTerm(term, kind, message, alternatives))

    def _deterministic(
        self,
        tokens: list[str],
        claimed: list[bool],
        out: Resolution,
        methods: tuple[str, ...],
    ) -> None:
        for length in range(min(self._max_len, len(tokens)), 0, -1):
            for start in range(0, len(tokens) - length + 1):
                if any(claimed[start : start + length]):
                    continue
                key = tuple(tokens[start : start + length])
                candidates = [
                    form
                    for method in methods
                    for form in self._by_tokens[method].get(key, [])
                    if _short_form_allowed(form)
                ]
                if not candidates:
                    continue
                best = min(
                    candidates,
                    key=lambda form: (
                        form.entry.priority,
                        _METHOD_RANK[form.method],
                        -form.entry.frequency,
                    ),
                )
                # A curated family synonym ("red") names every value that lists it.
                family = [
                    form
                    for form in candidates
                    if form.method == "synonym" == best.method
                    and form.entry.column == best.entry.column
                ] or [best]
                for form in family:
                    out.matches.append(
                        EntityMatch(
                            entry=form.entry,
                            text=" ".join(key),
                            method=form.method,
                            confidence=_METHOD_CONFIDENCE.get(form.method, 0.9),
                            start=start,
                            end=start + length,
                        )
                    )
                for index in range(start, start + length):
                    claimed[index] = True

    def _fuzzy(self, tokens: list[str], claimed: list[bool], out: Resolution) -> None:
        for length in (3, 2, 1):
            for start in range(0, len(tokens) - length + 1):
                window = tokens[start : start + length]
                if any(claimed[start : start + length]):
                    continue
                if any(self._is_vocabulary(token) for token in window):
                    continue
                phrase = " ".join(window)
                if len(phrase) < _FUZZY_MIN_LENGTH:
                    continue
                best, ratio = self._closest(phrase, length)
                threshold = 0.86 if len(phrase) >= 6 else 0.88
                if best is None or ratio < threshold:
                    continue
                out.matches.append(
                    EntityMatch(
                        entry=best.entry,
                        text=phrase,
                        method="fuzzy",
                        confidence=round(ratio, 2),
                        start=start,
                        end=start + length,
                    )
                )
                for index in range(start, start + length):
                    claimed[index] = True

    def _closest(self, phrase: str, length: int) -> tuple[_Form | None, float]:
        best: _Form | None = None
        best_ratio = 0.0
        for form in self._fuzzy_targets:
            if len(form.tokens) != length:
                continue
            target = " ".join(form.tokens)
            if abs(len(target) - len(phrase)) > 3:
                continue
            ratio = difflib.SequenceMatcher(None, phrase, target).ratio()
            if (
                length == 1
                and len(phrase) >= 5
                and phrase[0] == target[0]
                and edit_distance(phrase, target) == 1
            ):
                # One slip ("hyundia", "mumabi") is closer than the ratio suggests.
                ratio = max(ratio, 0.9)
            if ratio > best_ratio or (
                ratio == best_ratio and best is not None and form.entry.priority < best.entry.priority
            ):
                best, best_ratio = form, ratio
        return best, best_ratio

    def _drop_generic_without_context(
        self, tokens: list[str], claimed: list[bool], out: Resolution
    ) -> None:
        has_make = any(match.entry.key == "make" for match in out.matches)
        kept: list[EntityMatch] = []
        for match in out.matches:
            if (
                self._is_generic(match.entry)
                and match.end - match.start == 1
                and not has_make
                and not (match.end < len(tokens) and tokens[match.end] in _MAKE_CUE)
            ):
                claimed[match.start] = False
                continue
            kept.append(match)
        out.matches = kept

    def _unresolved(self, tokens: list[str], claimed: list[bool], out: Resolution) -> None:
        """Name-like words in entity positions that matched nothing in the catalog."""
        text = " ".join(tokens)
        positions: set[int] = set()
        patterns = (
            r"\b(?:of|for|in|from|at)\s+(\w+(?:\s+\w+)?)",
            r"^(?:what\s+(?:is|are|were)\s+|how\s+(?:much|many)\s+|compare\s+)?(\w+(?:\s+\w+)?)\s+"
            r"(?:sales|revenue|units|orders|volume|market\s+share|models?|cars?)\b",
            r"\bcompare\s+(\w+)\s+(?:and|with|vs|versus)\s+(\w+)",
            r"\b(\w+)\s+(?:vs|versus)\s+(\w+)",
        )
        for pattern in patterns:
            for found in re.finditer(pattern, text):
                for group_index in range(1, (found.lastindex or 0) + 1):
                    group_start = found.start(group_index)
                    if group_start < 0:
                        continue
                    first = len(text[:group_start].split())
                    count = len(found.group(group_index).split())
                    positions.update(range(first, first + count))
        seen: set[str] = set()
        for index in sorted(positions):
            if index >= len(tokens) or claimed[index]:
                continue
            token = tokens[index]
            if self._is_vocabulary(token) or token in seen:
                continue
            seen.add(token)
            out.unresolved.append(UnresolvedTerm(token, self.suggest(token)))

    def suggest(self, term: str, *, limit: int = 4) -> tuple[str, ...]:
        """Closest canonical values for an unknown word ("Ferari" -> nothing; "Hyndai" -> Hyundai)."""
        norm = normalize(term)
        scored: dict[str, float] = {}
        for form in (*self._forms["exact"], *self._forms["synonym"], *self._forms["alias"]):
            target = " ".join(form.tokens)
            ratio = difflib.SequenceMatcher(None, norm, target).ratio()
            if norm and norm in form.tokens:
                ratio = max(ratio, 0.8)
            if ratio >= _SUGGESTION_RATIO:
                name = form.entry.canonical
                scored[name] = max(scored.get(name, 0.0), ratio)
        ranked = sorted(scored.items(), key=lambda item: item[1], reverse=True)
        return tuple(name for name, _ in ranked[:limit])

    def protected_words(self) -> frozenset[str]:
        """Words spell correction must leave alone: vocabulary and every catalog name."""
        if self._protected is None:
            words = set(_STOPWORDS) | set(self.vocabulary.known_words)
            for forms in self._forms.values():
                for form in forms:
                    words.update(form.tokens)
            self._protected = frozenset(words)
        return self._protected

    def canonical_values(self, key: str) -> list[str]:
        return list(
            dict.fromkeys(
                entry.canonical
                for entry in sorted(self.catalog, key=lambda item: -item.frequency)
                if entry.key == key
            )
        )


def catalog_from_domains(
    domains: Iterable[Any],
    live_values: Iterable[Any] = (),
) -> tuple[CatalogEntry, ...]:
    """Merge pack canonical values/synonyms with live warehouse values.

    Pack values keep chat working when the live dictionary is unavailable; live
    values add anything the pack does not list (regions, colours, new models).
    """
    entries: dict[tuple[str, str], CatalogEntry] = {}
    labels: dict[str, str] = {}
    for domain in domains:
        column = str(domain.qualified_column)
        labels[column.casefold()] = str(domain.name)
        for value, aliases in domain.value_aliases:
            key = (column.casefold(), str(value).casefold())
            entries[key] = CatalogEntry(str(domain.name), column, str(value), tuple(aliases))
    for item in live_values:
        column = str(item.column)
        key = (column.casefold(), str(item.value).casefold())
        existing = entries.get(key)
        if existing is None:
            entries[key] = CatalogEntry(
                labels.get(column.casefold(), str(item.domain)),
                column,
                str(item.value),
                tuple(item.aliases),
                int(item.frequency or 0),
            )
        else:
            entries[key] = CatalogEntry(
                existing.domain,
                existing.column,
                existing.canonical,
                tuple(dict.fromkeys((*existing.synonyms, *item.aliases))),
                int(item.frequency or 0),
            )
    return tuple(entries.values())
