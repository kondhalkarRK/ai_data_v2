"""Compact approved context for interpretation; no queries or global catalog fallback.

Callers must bind a catalog snapshot to its authorized user and regional scope. The
preview API uses the existing global cache only for unrestricted administrators.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import date
from difflib import SequenceMatcher
from typing import Any
from uuid import UUID

from app.core.config import Industry
from app.core.exceptions import AuthorizationError
from app.schemas.semantic import SemanticPackResponse
from app.services.chat.entity_resolver import CatalogEntry, EntityResolver, normalize
from app.services.chat.request_capabilities import measure_capabilities
from app.services.chat.request_contract import InterpretedRequest
from app.services.chat.value_dictionary import ValueDictionarySnapshot, domains_for
from app.services.security.region_scope import RegionScope


class ContextBudgetError(ValueError):
    pass


@dataclass(frozen=True)
class RequestPrincipal:
    user_id: UUID
    scope: RegionScope
    industry: Industry

    @property
    def binding(self) -> str:
        return f"{self.user_id}|{self.industry.value}|{self.scope.cache_key()}"


@dataclass(frozen=True)
class ScopedCatalog:
    binding: str
    snapshot: ValueDictionarySnapshot
    model_makes: tuple[tuple[str, str], ...] = ()


@dataclass(frozen=True)
class PreviousRequest:
    binding: str
    semantic_version: str
    request_id: str
    request: InterpretedRequest


@dataclass(frozen=True)
class RequestContext:
    binding: str
    semantic_version: str
    payload: dict[str, Any]


def pack_fingerprint(pack: SemanticPackResponse) -> str:
    return (
        f"{pack.summary.version}:{hashlib.sha256(pack.model_dump_json().encode()).hexdigest()[:16]}"
    )


def _score(text: str, names: list[str]) -> float:
    question = normalize(text)
    words = question.split()
    best = 0.0
    for name in names:
        phrase = normalize(name)
        if not phrase:
            continue
        if f" {phrase} " in f" {question} ":
            best = max(best, 2 + len(phrase) / 100)
        elif len(phrase) >= 4:
            count = len(phrase.split())
            for i in range(len(words)):
                span = " ".join(words[i : i + count])
                ratio = SequenceMatcher(None, phrase, span).ratio()
                if ratio >= 0.8:
                    best = max(best, ratio)
    return best


def build_request_context(
    question: str,
    *,
    pack: SemanticPackResponse,
    principal: RequestPrincipal,
    catalog: ScopedCatalog | None = None,
    previous: PreviousRequest | None = None,
    max_chars: int = 9000,
    current_date: date | None = None,
    data_as_of: date | None = None,
) -> RequestContext:
    if principal.industry != Industry.AUTOMOTIVE or pack.summary.industry != principal.industry:
        raise AuthorizationError("The request context is not available for this industry.")
    if principal.scope.user_id not in {None, principal.user_id}:
        raise AuthorizationError("The regional scope belongs to another user.")
    if catalog and (
        catalog.binding != principal.binding or catalog.snapshot.industry != principal.industry
    ):
        raise AuthorizationError("The entity catalog belongs to another access scope.")
    version = pack_fingerprint(pack)
    if previous and (previous.binding != principal.binding or previous.semantic_version != version):
        raise AuthorizationError("Previous interpretation belongs to a different scope or model.")
    relevant_text = question + (" " + previous.request.summary if previous else "")
    terms = pack.glossary.terms
    ranked_measures = []
    measure_phrases: set[str] = set()
    for key, measure in pack.model.measures.items():
        names = [key, measure.display_name, *measure.synonyms]
        for name, term in terms.items():
            if term.maps_to_measure == key:
                names += [name, *term.synonyms]
        score = _score(relevant_text, names)
        measure_phrases.update(normalize(name) for name in names)
        ranked_measures.append(
            (
                score,
                key,
                {
                    "id": key,
                    "label": measure.display_name,
                    "aliases": list(dict.fromkeys(names[2:])),
                    "formula": measure.expression,
                    "aggregation": measure.aggregation,
                    "fact": measure.source_table,
                    "description": measure.description,
                },
            )
        )
    # Search the whole pack; never replace explicitly relevant measures with a first-N list.
    ranked_measures.sort(key=lambda item: (-item[0], item[1]))
    selected = [m for score, _, m in ranked_measures if score > 0]
    if len(ranked_measures) <= 12:
        selected = [m for _, _, m in ranked_measures]
    if not selected:
        selected = [m for _, _, m in ranked_measures[:8]]
    if previous:
        required = {m.id for m in previous.request.measures}
        selected += [
            m
            for _, key, m in ranked_measures
            if key in required and key not in {x["id"] for x in selected}
        ]
    fields: dict[str, Any] = {}
    for dim in pack.model.dimensions.values():
        for column in [dim.source_column] if dim.source_column else dim.attributes:
            if column:
                if column.casefold() in {
                    "email",
                    "corp_id",
                    "password",
                    "password_hash",
                    "api_key",
                    "secret",
                }:
                    continue
                key = f"{dim.source_table}.{column}"
                spec = pack.model.tables[dim.source_table].columns.get(column)
                fields[key] = {
                    "label": column.replace("_", " "),
                    "dimension": dim.display_name,
                    "type": spec.type if spec else "string",
                    "aliases": dim.synonyms,
                }
    entries: list[CatalogEntry] = []
    approved_domains = {
        domain.qualified_column: domain for domain in domains_for(principal.industry, pack)
    }
    if catalog:
        for item in catalog.snapshot.values:
            domain = approved_domains.get(item.column)
            if domain is None or not principal.scope.allows_label(item.value):
                continue
            field = ".".join(item.column.split(".")[-2:])
            if field not in fields:
                continue
            aliases = dict(domain.value_aliases).get(item.value, ())
            entries.append(
                CatalogEntry(
                    item.domain,
                    item.column,
                    item.value,
                    tuple(dict.fromkeys((*aliases, *item.aliases))),
                )
            )
    # Reuse the resolver's identity normalization and approved aliases, without merging
    # unscoped pack values into an authorized snapshot.
    # Recognized measure/operator phrases must not become fuzzy model values (e.g.
    # a measure name being matched to a similarly spelled vehicle). This affects
    # candidate gathering only; it never adds a filter to the proposed request.
    entity_text = normalize(relevant_text)
    for phrase in sorted(measure_phrases, key=len, reverse=True):
        if phrase:
            entity_text = re.sub(rf"(?<!\w){re.escape(phrase)}(?!\w)", " ", entity_text)
    resolver = EntityResolver(tuple(entries), pack=pack)
    matches = resolver.resolve(entity_text).matches
    matched = {(m.entry.column, m.entry.canonical) for m in matches}
    previous_entities: set[str] = set()
    if previous:
        previous_entities.update(previous.request.entity_ids)
        for filt in previous.request.filters:
            previous_entities.update(filt.entity_ids)
        for comparison in previous.request.comparisons:
            previous_entities.update(comparison.member_ids)
    candidates = []
    for entry in entries:
        score = _score(entity_text, [entry.canonical, *entry.synonyms])
        field = ".".join(entry.column.split(".")[-2:])
        key = hashlib.sha256(f"{entry.column}|{entry.canonical}".encode()).hexdigest()[:16]
        if (
            score <= 0
            and (entry.column, entry.canonical) not in matched
            and key not in previous_entities
        ):
            continue
        candidates.append(
            (score, {"id": key, "field": field, "value": entry.canonical, "domain": entry.domain})
        )
        if field == "dim_carline.model" and catalog:
            candidates[-1][1]["makes"] = sorted(
                {make for model, make in catalog.model_makes if model == entry.canonical}
            )
    candidates.sort(key=lambda item: (-item[0], item[1]["id"]))
    if not previous_entities <= {item["id"] for _, item in candidates}:
        raise AuthorizationError(
            "Previous entity references are no longer available in this scope."
        )
    # Fail explicitly when relevant candidates exceed budget; don't silently drop members.
    if len(candidates) > 40:
        raise ContextBudgetError("Too many relevant entity candidates for one interpretation")
    glossary = [
        {
            "id": name,
            "definition": term.definition,
            "measure": term.maps_to_measure,
            "rules": term.calculation_rules,
            "ambiguity": term.disambiguation,
        }
        for name, term in terms.items()
        if _score(relevant_text, [name, term.display_label or "", *term.synonyms]) > 0
    ]
    facts = {
        key: {
            "grain": table.grain,
            "key": table.primary_key,
            "dates": [
                c
                for c, spec in table.columns.items()
                if spec.type in {"date", "datetime", "timestamp"}
            ],
        }
        for key, table in pack.model.tables.items()
        if table.type == "fact" or key in {m["fact"] for m in selected}
    }
    capabilities = measure_capabilities(pack)
    for measure in selected:
        measure["capability"] = {
            k: v
            for k, v in capabilities[measure["id"]].items()
            if k not in {"source", "formula"} and v is not None
        }
    payload = {
        "semantic_version": version,
        "calendar_date": (current_date or date.today()).isoformat(),
        "calendar_basis": "server calendar date; resolve business period policy in compiler bridge",
        "data_as_of": data_as_of.isoformat() if data_as_of else None,
        "query_policy": pack.model.query_policy.model_dump(mode="json")
        if pack.model.query_policy
        else None,
        "measures": selected,
        "fields": fields,
        "entities": [item for _, item in candidates],
        "glossary": glossary,
        "facts": facts,
        "relationships": [
            r.model_dump(
                include={"name", "from_table", "from_column", "to_table", "to_column", "type"}
            )
            for r in pack.model.relationships
        ],
        "previous": {
            "request_id": previous.request_id,
            "request": previous.request.model_dump(mode="json", exclude_defaults=True),
        }
        if previous
        else None,
        "catalog_available": catalog is not None,
    }
    if len(json.dumps(payload, ensure_ascii=False, separators=(",", ":"))) > max_chars:
        raise ContextBudgetError("Relevant approved context exceeds the interpretation budget")
    return RequestContext(principal.binding, version, payload)
