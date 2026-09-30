"""Industry-scoped business value dictionary built from the live warehouse.

This is the PostgreSQL equivalent of Streamlit's ``top_values`` grounding.  The
dictionary is bounded, cached, and only matched values are carried into a query
plan or LLM prompt.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from app.core.cache import TTLCache
from app.core.config import Industry
from app.services.chat.entity_resolver import (
    EntityResolver,
    Resolution,
    catalog_from_domains,
    load_chat_vocabulary,
)
from app.services.chat.question_understanding import ExtractedFilter


@dataclass(frozen=True, slots=True)
class ValueDomain:
    name: str
    table: str
    column: str
    label: str
    max_values: int = 100
    value_aliases: tuple[tuple[str, tuple[str, ...]], ...] = ()

    @property
    def qualified_column(self) -> str:
        return f"{self.table}.{self.column}"


@dataclass(frozen=True, slots=True)
class BusinessValue:
    domain: str
    column: str
    value: str
    frequency: int = 0
    aliases: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ValueDictionarySnapshot:
    industry: Industry
    values: tuple[BusinessValue, ...]

    def resolve(self, question: str, *, pack: Any | None = None) -> Resolution:
        """Resolve business values: exact -> synonym -> fuzzy -> alias -> glossary."""
        return resolver_for(self, pack).resolve(question)

    def match(
        self, question: str, *, limit: int = 8, pack: Any | None = None
    ) -> list[ExtractedFilter]:
        """Mandatory filters for every business value named in the question."""
        return self.resolve(question, pack=pack).filters()[:limit]


_RESOLVERS: dict[tuple[int, int], tuple[ValueDictionarySnapshot, Any, EntityResolver]] = {}


def resolver_for(snapshot: ValueDictionarySnapshot, pack: Any | None = None) -> EntityResolver:
    """One resolver per (dictionary snapshot, pack); both are long-lived cached objects."""
    key = (id(snapshot), id(pack))
    cached = _RESOLVERS.get(key)
    if cached is not None and cached[0] is snapshot and cached[1] is pack:
        return cached[2]
    catalog = catalog_from_domains(domains_for(snapshot.industry, pack), snapshot.values)
    resolver = EntityResolver(
        catalog,
        pack=pack,
        vocabulary=load_chat_vocabulary(snapshot.industry),
    )
    if len(_RESOLVERS) >= 8:
        _RESOLVERS.clear()
    _RESOLVERS[key] = (snapshot, pack, resolver)
    return resolver


AUTOMOTIVE_DOMAINS: tuple[ValueDomain, ...] = (
    ValueDomain("Car Type", "automotive.dim_carline", "car_type", "Car type", 30),
    ValueDomain("Make", "automotive.dim_carline", "make", "Make", 100),
    ValueDomain("Model", "automotive.dim_carline", "model", "Model", 200),
    ValueDomain("Engine Type", "automotive.dim_carline", "engine_type", "Engine type", 30),
    ValueDomain("Colour", "automotive.dim_color", "colour_name", "Colour", 100),
    ValueDomain("City", "automotive.dim_region", "city", "City", 100),
    ValueDomain("Region", "automotive.dim_region", "region_name", "Region", 100),
    ValueDomain("State", "automotive.dim_region", "state_code", "State", 100),
    ValueDomain("Dealer Grade", "automotive.dim_dealer", "dealer_grade", "Dealer grade", 10),
)

INSURANCE_DOMAINS: tuple[ValueDomain, ...] = (
    ValueDomain("Claim Status", "insurance.fact_claims", "claim_status", "Claim status", 30),
    ValueDomain("Claim Type", "insurance.fact_claims", "claim_type", "Claim type", 50),
    ValueDomain("Policy Status", "insurance.dim_policy", "policy_status", "Policy status", 20),
    ValueDomain("Coverage Tier", "insurance.dim_policy", "coverage_tier", "Coverage tier", 20),
    ValueDomain("Product", "insurance.dim_product", "product_name", "Product", 100),
    ValueDomain("Line of Business", "insurance.dim_product", "line_of_business", "LOB", 50),
    ValueDomain("Product Family", "insurance.dim_product", "product_family", "Product family", 50),
    ValueDomain("Coverage Type", "insurance.dim_product", "coverage_type", "Coverage type", 50),
    ValueDomain("Channel", "insurance.dim_agent", "channel_name", "Channel", 30),
    ValueDomain("Branch", "insurance.dim_agent", "branch_name", "Branch", 100),
    ValueDomain("Region", "insurance.dim_region", "region_name", "Region", 100),
    ValueDomain("State", "insurance.dim_region", "state_name", "State", 100),
)

_CACHE: TTLCache[ValueDictionarySnapshot] = TTLCache(ttl_seconds=1800, max_entries=4)


def domains_for(industry: Industry, pack: Any | None = None) -> tuple[ValueDomain, ...]:
    model = getattr(pack, "model", None)
    configured = getattr(model, "value_domains", {}) if model is not None else {}
    tables = getattr(model, "tables", {}) if model is not None else {}
    if configured:
        domains: list[ValueDomain] = []
        for name, definition in configured.items():
            logical_table = str(getattr(definition, "table", ""))
            table = tables.get(logical_table)
            physical_table = str(getattr(table, "physical_name", logical_table))
            domains.append(
                ValueDomain(
                    name=str(getattr(definition, "label", name)),
                    table=physical_table,
                    column=str(getattr(definition, "column", "")),
                    label=str(getattr(definition, "label", name)),
                    max_values=int(getattr(definition, "max_values", 100)),
                    value_aliases=tuple(
                        (str(value), tuple(str(alias) for alias in aliases))
                        for value, aliases in (
                            getattr(definition, "value_aliases", {}) or {}
                        ).items()
                    ),
                )
            )
        return tuple(domains)
    return AUTOMOTIVE_DOMAINS if industry is Industry.AUTOMOTIVE else INSURANCE_DOMAINS


async def get_value_dictionary(
    connection: AsyncConnection,
    industry: Industry,
    *,
    pack: Any | None = None,
) -> ValueDictionarySnapshot:
    """Load a bounded dictionary once per industry/TTL."""

    async def load() -> ValueDictionarySnapshot:
        domains = domains_for(industry, pack)
        pieces: list[str] = []
        for index, domain in enumerate(domains):
            pieces.append(
                "SELECT "
                f"'{domain.name}' AS domain_name, "
                f"'{domain.qualified_column}' AS column_name, "
                "v.value, v.frequency "
                "FROM ("
                f"SELECT {domain.column}::text AS value, COUNT(*)::bigint AS frequency "
                f"FROM {domain.table} "
                f"WHERE {domain.column} IS NOT NULL AND {domain.column}::text <> '' "
                f"GROUP BY {domain.column} "
                "ORDER BY frequency DESC, value "
                f"LIMIT {int(domain.max_values)}"
                f") AS v{index}"
            )
        result = await connection.execute(text("\nUNION ALL\n".join(pieces)))
        aliases_by_value = {
            (domain.qualified_column.casefold(), value.casefold()): aliases
            for domain in domains
            for value, aliases in domain.value_aliases
        }
        values = tuple(
            BusinessValue(
                domain=str(row.domain_name),
                column=str(row.column_name),
                value=str(row.value),
                frequency=int(row.frequency or 0),
                aliases=aliases_by_value.get(
                    (str(row.column_name).casefold(), str(row.value).casefold()),
                    (),
                ),
            )
            for row in result
        )
        return ValueDictionarySnapshot(industry=industry, values=values)

    return await _CACHE.get_or_set(industry.value, load)


def build_snapshot(
    industry: Industry,
    rows: Iterable[tuple[str, str, int]],
    *,
    pack: Any | None = None,
) -> ValueDictionarySnapshot:
    """Snapshot from (qualified_column, value, frequency) rows, e.g. the Entity Catalog."""
    domains = {domain.qualified_column.casefold(): domain for domain in domains_for(industry, pack)}
    aliases_by_value = {
        (column, value.casefold()): aliases
        for column, domain in domains.items()
        for value, aliases in domain.value_aliases
    }
    values = tuple(
        BusinessValue(
            domain=domains[column.casefold()].name,
            column=domains[column.casefold()].qualified_column,
            value=value,
            frequency=frequency,
            aliases=aliases_by_value.get((column.casefold(), value.casefold()), ()),
        )
        for column, value, frequency in rows
        if column.casefold() in domains
    )
    return ValueDictionarySnapshot(industry=industry, values=values)


def cached_value_dictionary(industry: Industry) -> ValueDictionarySnapshot | None:
    return _CACHE.get(industry.value)


def replace_value_dictionary(snapshot: ValueDictionarySnapshot) -> None:
    """Swap in a freshly refreshed dictionary so AI Chat sees new values immediately."""
    _CACHE.set(snapshot.industry.value, snapshot)
    _RESOLVERS.clear()


def invalidate_value_dictionary(industry: Industry | None = None) -> None:
    if industry is None:
        _CACHE.clear()
    else:
        _CACHE.invalidate(industry.value)
    _RESOLVERS.clear()
