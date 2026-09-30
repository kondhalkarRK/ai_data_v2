"""Read warehouse metadata and distinct values over the read-only analytics connection.

Identifiers come from the semantic pack and are validated in ``config``; values are
always bound parameters.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import bindparam, text
from sqlalchemy.ext.asyncio import AsyncConnection

from app.services.catalog.config import CatalogConfig, CatalogDomain
from app.services.catalog.drift import ColumnInfo

logger = logging.getLogger(__name__)

VALUE_LIMIT = 2000
_TERM = re.compile(r"^[a-z0-9][a-z0-9 .&'-]{1,60}$")


@dataclass(slots=True)
class DomainObservation:
    values: list[tuple[str, int]]
    distinct: int
    data_type: str | None = None
    error: str | None = None

    @property
    def complete(self) -> bool:
        return self.error is None and len(self.values) >= self.distinct


@dataclass(slots=True)
class CatalogObservation:
    columns: dict[tuple[str, str], ColumnInfo] | None
    domains: dict[str, DomainObservation] = field(default_factory=dict)
    fact_rows: dict[str, int] = field(default_factory=dict)

    @property
    def rows_processed(self) -> int | None:
        return sum(self.fact_rows.values()) if self.fact_rows else None


async def _nested(
    connection: AsyncConnection, sql: str, **params: object
) -> list[tuple[Any, ...]]:
    """Run one read in a savepoint so a missing column cannot abort the whole refresh."""
    async with connection.begin_nested():
        result = await connection.execute(text(sql), params)
        return [tuple(row) for row in result]


async def read_columns(
    connection: AsyncConnection, schemas: Iterable[str]
) -> dict[tuple[str, str], ColumnInfo]:
    statement = text(
        "SELECT table_schema, table_name, column_name, data_type, ordinal_position "
        "FROM information_schema.columns WHERE table_schema IN :schemas"
    ).bindparams(bindparam("schemas", expanding=True))
    async with connection.begin_nested():
        result = await connection.execute(statement, {"schemas": list(schemas)})
        rows = list(result)
    return {
        (f"{row[0]}.{row[1]}", str(row[2])): ColumnInfo(
            table=f"{row[0]}.{row[1]}",
            column=str(row[2]),
            data_type=str(row[3]),
            ordinal=int(row[4] or 0),
        )
        for row in rows
    }


async def read_domain(connection: AsyncConnection, domain: CatalogDomain) -> DomainObservation:
    column, table = domain.column, domain.table
    try:
        distinct_rows = await _nested(
            connection, f"SELECT COUNT(DISTINCT {column}) FROM {table}"  # noqa: S608
        )
        values = await _nested(
            connection,
            f"SELECT {column}::text AS value, COUNT(*)::bigint AS frequency "  # noqa: S608
            f"FROM {table} WHERE {column} IS NOT NULL AND {column}::text <> '' "
            "GROUP BY 1 ORDER BY 2 DESC, 1 LIMIT :limit",
            limit=VALUE_LIMIT,
        )
    except Exception as exc:
        logger.warning("catalog: could not read %s.%s", table, column, exc_info=True)
        return DomainObservation([], 0, error=type(exc).__name__)
    return DomainObservation(
        [(str(value), int(frequency or 0)) for value, frequency in values],
        int(distinct_rows[0][0] or 0) if distinct_rows else 0,
    )


async def observe(
    connection: AsyncConnection,
    config: CatalogConfig,
    *,
    include_schema: bool = True,
    domain_keys: Iterable[str] | None = None,
) -> CatalogObservation:
    wanted = set(domain_keys) if domain_keys is not None else None
    columns = await read_columns(connection, config.schemas) if include_schema else None
    observation = CatalogObservation(columns=columns)
    for domain in config.domains:
        if wanted is not None and domain.key not in wanted:
            continue
        found = await read_domain(connection, domain)
        if columns is not None:
            info = columns.get((domain.table, domain.column))
            found.data_type = info.data_type if info else None
        observation.domains[domain.key] = found
    if wanted is None:
        for table in config.fact_tables:
            try:
                rows = await _nested(connection, f"SELECT COUNT(*) FROM {table}")  # noqa: S608
                observation.fact_rows[table] = int(rows[0][0] or 0)
            except Exception:
                logger.warning("catalog: could not count %s", table, exc_info=True)
    return observation


async def lookup_values(
    connection: AsyncConnection,
    config: CatalogConfig,
    terms: Iterable[str],
    *,
    per_term: int = 3,
) -> list[tuple[str, str, int]]:
    """Targeted lookup for names the dictionary does not know: (domain_key, value, freq).

    Matches the whole value case-insensitively, or a value that starts with the term
    followed by a space ("curvv" finds "Curvv EV").
    """
    found: list[tuple[str, str, int]] = []
    clean = [t for t in dict.fromkeys(term.strip().lower() for term in terms) if _TERM.match(t)]
    for term in clean[:3]:
        for domain in config.domains:
            if not domain.ai_known:
                continue
            column, table = domain.column, domain.table
            try:
                rows = await _nested(
                    connection,
                    f"SELECT {column}::text, COUNT(*)::bigint FROM {table} "  # noqa: S608
                    f"WHERE lower({column}::text) = :term OR lower({column}::text) LIKE :prefix "
                    "GROUP BY 1 ORDER BY 2 DESC LIMIT :limit",
                    term=term,
                    prefix=term.replace("%", "").replace("_", "") + " %",
                    limit=per_term,
                )
            except Exception:
                logger.warning("catalog: lookup failed on %s.%s", table, column, exc_info=True)
                continue
            found.extend((domain.key, str(value), int(freq or 0)) for value, freq in rows)
    return found
