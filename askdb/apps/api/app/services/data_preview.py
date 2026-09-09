"""Analytics data preview: catalog + keyset-paginated rows."""

from __future__ import annotations

import base64
import json
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from app.analytics.sql_guardrails import qualify_ident, qualify_table, sql_is_safe
from app.core.config import Industry, Settings
from app.core.exceptions import GuardrailViolationError, NotFoundError, ValidationError
from app.schemas.common import PageMeta
from app.schemas.data import (
    PreviewColumn,
    PreviewPage,
    PreviewRow,
    PreviewTableSummary,
)
from app.semantic.service import SemanticService


def _jsonable(value: Any) -> Any:
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, memoryview):
        return bytes(value).hex()
    return value


def _encode_cursor(primary_key: str, value: Any) -> str:
    payload = {"k": primary_key, "v": _jsonable(value)}
    raw = json.dumps(payload, separators=(",", ":"), default=str).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii")


def _decode_cursor(cursor: str) -> tuple[str, Any]:
    try:
        payload = json.loads(base64.urlsafe_b64decode(cursor.encode("ascii")))
        return str(payload["k"]), payload["v"]
    except Exception as exc:
        raise ValidationError("The pagination cursor is invalid.") from exc


class DataPreviewService:
    def __init__(
        self,
        *,
        connection: AsyncConnection,
        semantic: SemanticService,
        settings: Settings,
        industry: Industry,
    ) -> None:
        self._connection = connection
        self._semantic = semantic
        self._settings = settings
        self._industry = industry

    async def list_tables(self) -> list[PreviewTableSummary]:
        pack = await self._semantic.get_pack(self._industry)
        summaries: list[PreviewTableSummary] = []
        for name, table in pack.model.tables.items():
            schema, _, physical = table.physical_name.partition(".")
            if not physical:
                schema, physical = self._industry.value, table.physical_name
            estimate = await self._estimate_rows(schema, physical)
            summaries.append(
                PreviewTableSummary(
                    name=name,
                    display_name=table.display_name,
                    physical_name=table.physical_name,
                    table_type=table.type,
                    primary_key=table.primary_key,
                    grain=table.grain,
                    estimated_rows=estimate,
                    column_count=len(table.columns),
                )
            )
        summaries.sort(key=lambda item: (item.table_type != "fact", item.display_name))
        return summaries

    async def preview_rows(
        self,
        table_name: str,
        *,
        cursor: str | None,
        limit: int | None,
    ) -> PreviewPage:
        pack = await self._semantic.get_pack(self._industry)
        table = pack.model.tables.get(table_name)
        if table is None:
            raise NotFoundError(f"Unknown table '{table_name}'.")

        page_size = min(
            limit or self._settings.sql_preview_page_size,
            self._settings.sql_preview_page_size,
            self._settings.sql_max_result_rows,
        )
        if page_size < 1:
            raise ValidationError("limit must be >= 1")

        schema, _, physical = table.physical_name.partition(".")
        if not physical:
            schema, physical = self._industry.value, table.physical_name
        qualified = qualify_table(schema, physical)
        pk = table.primary_key
        pk_sql = qualify_ident(pk)

        params: dict[str, Any] = {"limit": page_size + 1}
        where = ""
        if cursor:
            cursor_pk, cursor_value = _decode_cursor(cursor)
            if cursor_pk != pk:
                raise ValidationError("The pagination cursor does not match this table.")
            where = f"WHERE {pk_sql} < :cursor_value"
            params["cursor_value"] = cursor_value

        sql = f"SELECT * FROM {qualified} {where} ORDER BY {pk_sql} DESC LIMIT :limit"  # noqa: S608
        ok, reason = sql_is_safe(sql)
        if not ok:
            raise GuardrailViolationError(reason)

        result = await self._connection.execute(text(sql), params)
        mappings = result.mappings().all()
        has_more = len(mappings) > page_size
        page_rows = mappings[:page_size]

        columns = [
            PreviewColumn(
                name=col_name,
                display_name=meta.display_name,
                type=meta.type,
                role=meta.role,
            )
            for col_name, meta in table.columns.items()
        ]
        # Include any physical columns not listed in the semantic model.
        if page_rows:
            known = {column.name for column in columns}
            for key in page_rows[0]:
                if key not in known:
                    columns.append(
                        PreviewColumn(
                            name=key,
                            display_name=key,
                            type="unknown",
                            role="attribute",
                        )
                    )

        items = [
            PreviewRow(values={key: _jsonable(value) for key, value in row.items()})
            for row in page_rows
        ]
        next_cursor = None
        if has_more and page_rows:
            next_cursor = _encode_cursor(pk, page_rows[-1][pk])

        return PreviewPage(
            table=table_name,
            physical_name=table.physical_name,
            columns=columns,
            items=items,
            meta=PageMeta(
                total=None,
                limit=page_size,
                next_cursor=next_cursor,
                has_more=has_more,
            ),
        )

    async def _estimate_rows(self, schema: str, table: str) -> int | None:
        result = await self._connection.execute(
            text(
                """
                SELECT c.reltuples::bigint AS estimate
                FROM pg_class c
                JOIN pg_namespace n ON n.oid = c.relnamespace
                WHERE n.nspname = :schema AND c.relname = :table
                """
            ),
            {"schema": schema, "table": table},
        )
        row = result.first()
        if row is None:
            return None
        estimate = int(row.estimate)
        return max(estimate, 0)
