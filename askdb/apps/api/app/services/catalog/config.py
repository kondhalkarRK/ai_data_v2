"""Which warehouse columns the Entity Catalog tracks, from the semantic pack."""

from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from app.core.config import Industry, get_settings

_IDENTIFIER = re.compile(r"^[a-z_][a-z0-9_]*$")

GROUPS = ("Vehicle", "Sales", "Customer", "Dealer", "Geography", "Insurance")


@dataclass(frozen=True, slots=True)
class CatalogDomain:
    key: str
    label: str
    group: str
    table: str  # physical, schema-qualified
    column: str
    max_values: int
    ai_known: bool  # part of the AI Chat value dictionary
    value_aliases: tuple[tuple[str, tuple[str, ...]], ...] = ()
    column_aliases: tuple[str, ...] = ()

    @property
    def qualified_column(self) -> str:
        return f"{self.table}.{self.column}"


@dataclass(frozen=True, slots=True)
class CatalogConfig:
    industry: Industry
    schemas: tuple[str, ...]
    domains: tuple[CatalogDomain, ...]
    fact_tables: tuple[str, ...]
    # (physical table, column) -> semantic objects that use it
    references: dict[tuple[str, str], tuple[str, ...]]
    table_groups: dict[str, str]

    def domain(self, key: str) -> CatalogDomain | None:
        return next((d for d in self.domains if d.key == key), None)


@lru_cache(maxsize=4)
def _read_yaml(industry: Industry) -> dict[str, Any]:
    path = Path(get_settings().semantic_packs_dir) / industry.value / "entity_catalog.yaml"
    if not path.exists():
        return {}
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def _safe_table(physical: str) -> str:
    parts = physical.split(".")
    if len(parts) != 2 or not all(_IDENTIFIER.match(part) for part in parts):
        raise ValueError(f"Unsafe table identifier in semantic pack: {physical!r}")
    return physical


def _safe_column(column: str) -> str:
    if not _IDENTIFIER.match(column):
        raise ValueError(f"Unsafe column identifier in semantic pack: {column!r}")
    return column


def _default_group(industry: Industry, table: str) -> str:
    name = table.rsplit(".", 1)[-1]
    if any(word in name for word in ("region", "geo", "city", "state")):
        return "Geography"
    if "dealer" in name:
        return "Dealer"
    if any(word in name for word in ("customer", "policyholder")):
        return "Customer"
    if industry is Industry.INSURANCE:
        return "Insurance"
    if any(word in name for word in ("carline", "color", "colour", "vehicle")):
        return "Vehicle"
    return "Sales"


def build_catalog_config(industry: Industry, pack: Any) -> CatalogConfig:
    """Value domains (AI-known) plus watched columns, with pack references for impact."""
    raw = _read_yaml(industry)
    model = pack.model
    tables = model.tables
    physical = {name: str(table.physical_name) for name, table in tables.items()}
    groups: dict[str, str] = dict(raw.get("groups") or {})

    domains: list[CatalogDomain] = []
    for key, definition in model.value_domains.items():
        table = _safe_table(physical[definition.table])
        domains.append(
            CatalogDomain(
                key=key,
                label=str(definition.label),
                group=groups.get(key) or _default_group(industry, table),
                table=table,
                column=_safe_column(definition.column),
                max_values=int(definition.max_values),
                ai_known=True,
                value_aliases=tuple(
                    (str(value), tuple(str(alias) for alias in aliases))
                    for value, aliases in (definition.value_aliases or {}).items()
                ),
                column_aliases=tuple(str(alias) for alias in definition.aliases or ()),
            )
        )
    for key, item in (raw.get("tracked_columns") or {}).items():
        table = _safe_table(physical[str(item["table"])])
        domains.append(
            CatalogDomain(
                key=str(key),
                label=str(item.get("label") or key),
                group=str(item.get("group") or _default_group(industry, table)),
                table=table,
                column=_safe_column(str(item["column"])),
                max_values=int(item.get("max_values") or 500),
                ai_known=False,
            )
        )

    references: dict[tuple[str, str], list[str]] = {}

    def refer(table_name: str, column: str, label: str) -> None:
        if table_name in physical and column:
            references.setdefault((physical[table_name], column), []).append(label)

    for table_name, table in tables.items():
        for column_name, column in table.columns.items():
            role = str(getattr(column, "role", "") or "")
            if role in {"key", "foreign_key"}:
                refer(table_name, column_name, f"Join key {table_name}.{column_name}")
    for name, measure in model.measures.items():
        source = measure.source_table or ""
        if measure.source_column:
            refer(source, measure.source_column, f"Measure {name}")
        for column_name in tables[source].columns if source in tables else ():
            if re.search(rf"\b{re.escape(column_name)}\b", measure.expression):
                refer(source, column_name, f"Measure {name}")
    for name, dimension in model.dimensions.items():
        for column_name in (dimension.source_column, *dimension.attributes):
            refer(dimension.source_table, column_name or "", f"Dimension {name}")
    for domain in domains:
        references.setdefault((domain.table, domain.column), []).append(
            f"{'Value domain' if domain.ai_known else 'Tracked column'} {domain.key}"
        )

    fact_tables = tuple(
        physical[name]
        for name, table in tables.items()
        if str(getattr(table, "type", "")) == "fact"
    )
    schemas = tuple(raw.get("schemas") or sorted({t.split(".")[0] for t in physical.values()}))
    table_groups = {table: _default_group(industry, table) for table in physical.values()}
    return CatalogConfig(
        industry=industry,
        schemas=schemas,
        domains=tuple(domains),
        fact_tables=fact_tables,
        references={key: tuple(dict.fromkeys(value)) for key, value in references.items()},
        table_groups=table_groups,
    )
