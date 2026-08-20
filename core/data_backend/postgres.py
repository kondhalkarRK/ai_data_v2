"""Read-only PostgreSQL backend with bounded results and pooled connections."""
from __future__ import annotations

import hashlib
import json
from typing import Any

import pandas as pd

from core.data_backend.base import DataBackend
from core.sql_guardrails import sql_is_safe

try:
    from psycopg import sql as pg_sql
    from psycopg_pool import ConnectionPool

    _PSYCOPG_AVAILABLE = True
except ImportError:
    pg_sql = None
    ConnectionPool = None
    _PSYCOPG_AVAILABLE = False


class PostgresBackend(DataBackend):
    def __init__(self, config: dict[str, Any]):
        self._config = dict(config)
        self._schema = str(config.get("schema") or "public")
        self._max_rows = max(1, int(config.get("max_result_rows") or 1000))
        self._timeout_seconds = max(
            1, int(config.get("statement_timeout_seconds") or 30)
        )
        self._pool = None

    @property
    def backend_id(self) -> str:
        return "postgres"

    @property
    def sql_dialect(self) -> str:
        return "PostgreSQL"

    def _ensure_driver(self) -> None:
        if not _PSYCOPG_AVAILABLE:
            raise RuntimeError(
                "PostgreSQL support requires psycopg and psycopg_pool. "
                "Install requirements.txt and restart Streamlit."
            )

    def _get_pool(self):
        self._ensure_driver()
        if self._pool is None:
            self._pool = ConnectionPool(
                conninfo="",
                kwargs={
                    "host": self._config.get("host", "localhost"),
                    "port": int(self._config.get("port", 5432)),
                    "dbname": self._config.get("database", "askdb_dev"),
                    "user": self._config.get("user", "askdb_app"),
                    "password": self._config.get("password") or "",
                    "sslmode": self._config.get("sslmode", "prefer"),
                    "connect_timeout": int(
                        self._config.get("connect_timeout_seconds", 10)
                    ),
                    "application_name": "askdb_streamlit",
                },
                min_size=max(1, int(self._config.get("pool_min_size") or 1)),
                max_size=max(1, int(self._config.get("pool_max_size") or 5)),
                open=True,
            )
            self._pool.wait(
                timeout=int(self._config.get("connect_timeout_seconds") or 10)
            )
        return self._pool

    def close(self) -> None:
        if self._pool is not None:
            self._pool.close()
            self._pool = None

    def health_check(self) -> tuple[bool, str]:
        if not self._config.get("password"):
            return False, "PostgreSQL password is not configured."
        try:
            with self._get_pool().connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT current_database(), current_schema()")
                    database, _ = cur.fetchone()
            return True, f"Connected to {database}.{self._schema}."
        except Exception as exc:
            return False, f"PostgreSQL unavailable: {exc}"

    def execute_sql(self, sql: str) -> tuple[pd.DataFrame | None, str | None]:
        safe, reason = sql_is_safe(sql)
        if not safe:
            return None, f"\U0001f512 Blocked: {reason}"

        statement = (sql or "").strip().rstrip(";")
        bounded_sql = (
            f"SELECT * FROM ({statement}) AS _askdb_result "
            f"LIMIT {self._max_rows + 1}"
        )
        try:
            with self._get_pool().connection() as conn:
                with conn.transaction():
                    with conn.cursor() as cur:
                        cur.execute("SET TRANSACTION READ ONLY")
                        cur.execute(
                            "SELECT set_config('statement_timeout', %s, true)",
                            (f"{self._timeout_seconds}s",),
                        )
                        cur.execute(bounded_sql)
                        columns = [description.name for description in cur.description]
                        rows = cur.fetchall()

            truncated = len(rows) > self._max_rows
            result = pd.DataFrame(rows[: self._max_rows], columns=columns)
            result.attrs["askdb_truncated"] = truncated
            result.attrs["askdb_max_rows"] = self._max_rows
            return result, None
        except Exception as exc:
            return None, str(exc)

    def _catalog_rows(self) -> list[tuple]:
        query = """
            SELECT table_name, column_name, data_type, ordinal_position
            FROM information_schema.columns
            WHERE table_schema = %s
            ORDER BY table_name, ordinal_position
        """
        with self._get_pool().connection() as conn:
            with conn.cursor() as cur:
                cur.execute(query, (self._schema,))
                return cur.fetchall()

    def list_tables(self) -> list[str]:
        try:
            with self._get_pool().connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        SELECT table_name
                        FROM information_schema.tables
                        WHERE table_schema = %s
                          AND table_type IN ('BASE TABLE', 'VIEW')
                        UNION
                        SELECT matviewname
                        FROM pg_catalog.pg_matviews
                        WHERE schemaname = %s
                        ORDER BY 1
                        """,
                        (self._schema, self._schema),
                    )
                    return [str(row[0]) for row in cur.fetchall()]
        except Exception:
            return []

    def describe_schema(self) -> str:
        try:
            lines: list[str] = []
            current_table = None
            for table, column, data_type, _ in self._catalog_rows():
                if table != current_table:
                    current_table = table
                    lines.append(f"TABLE {self._schema}.{table}:")
                lines.append(f"  {column} ({data_type})")
            return "\n".join(lines)
        except Exception:
            return ""

    def get_preview(self, table: str | None = None, limit: int = 100) -> pd.DataFrame:
        tables = self.list_tables()
        selected = table or (tables[0] if tables else None)
        if selected not in tables:
            return pd.DataFrame()
        safe_limit = max(1, min(int(limit), self._max_rows))

        with self._get_pool().connection() as conn:
            with conn.cursor() as cur:
                query = pg_sql.SQL("SELECT * FROM {}.{} LIMIT {}").format(
                    pg_sql.Identifier(self._schema),
                    pg_sql.Identifier(selected),
                    pg_sql.Literal(safe_limit),
                )
                cur.execute(query)
                columns = [description.name for description in cur.description]
                return pd.DataFrame(cur.fetchall(), columns=columns)

    def get_dataset_fingerprint(self) -> str:
        try:
            payload = {
                "backend": self.backend_id,
                "database": self._config.get("database"),
                "schema": self._schema,
                "catalog": self._catalog_rows(),
            }
            digest = hashlib.sha256(
                json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
            ).hexdigest()[:16]
            return f"postgres:{digest}"
        except Exception:
            return f"postgres:{self._config.get('database')}:{self._schema}:unavailable"
