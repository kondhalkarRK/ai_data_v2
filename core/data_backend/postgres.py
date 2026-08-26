"""Read-only PostgreSQL backend with bounded results and pooled connections."""
from __future__ import annotations

import hashlib
import json
import time
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
        self._catalog_cache: list[tuple] | None = None
        self._catalog_cache_ts: float = 0.0
        self._health_cache: tuple[bool, str] | None = None
        self._health_cache_ts: float = 0.0
        self._schema_text_cache: str | None = None
        self._fingerprint_cache: str | None = None
        self._catalog_ttl_seconds = 120.0
        self._health_ttl_seconds = 60.0

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

    def _pool_kwargs(self) -> dict[str, Any]:
        """Build psycopg connect kwargs from discrete fields or a connection URL."""
        url = (self._config.get("connection_url") or "").strip()
        timeout = int(self._config.get("connect_timeout_seconds", 10))
        if url:
            # libpq connection string / URI; still force a bounded connect timeout.
            return {
                "conninfo": url,
                "connect_timeout": timeout,
                "application_name": "askdb_streamlit",
            }
        return {
            "host": self._config.get("host", "localhost"),
            "port": int(self._config.get("port", 5432)),
            "dbname": self._config.get("database", "askdb_dev"),
            "user": self._config.get("user", "askdb_app"),
            "password": self._config.get("password") or "",
            "sslmode": self._config.get("sslmode", "prefer"),
            "connect_timeout": timeout,
            "application_name": "askdb_streamlit",
        }

    def _get_pool(self):
        self._ensure_driver()
        if self._pool is None:
            kwargs = self._pool_kwargs()
            conninfo = kwargs.pop("conninfo", "")
            self._pool = ConnectionPool(
                conninfo=conninfo,
                kwargs=kwargs,
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
        url = (self._config.get("connection_url") or "").strip()
        if not url and not self._config.get("password"):
            return False, "PostgreSQL password is not configured."
        now = time.time()
        if (
            self._health_cache is not None
            and (now - self._health_cache_ts) < self._health_ttl_seconds
        ):
            return self._health_cache
        try:
            with self._get_pool().connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT current_database(), current_schema()")
                    database, _ = cur.fetchone()
            result = (True, f"Connected to {database}.{self._schema}.")
            self._health_cache = result
            self._health_cache_ts = now
            return result
        except Exception as exc:
            result = (False, f"PostgreSQL unavailable: {exc}")
            self._health_cache = result
            self._health_cache_ts = now
            return result

    def execute_sql(self, sql: str) -> tuple[pd.DataFrame | None, str | None]:
        safe, reason = sql_is_safe(sql)
        if not safe:
            return None, f"\U0001f512 Blocked: {reason}"

        statement = (sql or "").strip().rstrip(";")
        bounded_sql = (
            f"SELECT * FROM ({statement}) AS _askdb_result "
            f"LIMIT {self._max_rows + 1}"
        )
        t1 = time.perf_counter()
        try:
            from core.observability import span as obs_span
        except Exception:
            obs_span = None
        exec_cm = obs_span("pg.execute") if obs_span else None
        rec = {}
        if exec_cm is not None:
            rec = exec_cm.__enter__()
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
            latency_ms = int((time.perf_counter() - t1) * 1000)
            result.attrs["askdb_db_ms"] = latency_ms
            if rec is not None:
                rec.setdefault("attrs", {})
                rec["attrs"]["rows"] = len(result)
                rec["attrs"]["truncated"] = truncated
                rec["attrs"]["sql_chars"] = len(statement)
            if exec_cm is not None:
                exec_cm.__exit__(None, None, None)
            return result, None
        except Exception as exc:
            if rec is not None:
                rec["ok"] = False
                rec["error"] = str(exc)[:300]
            if exec_cm is not None:
                exec_cm.__exit__(None, None, None)
            return None, str(exc)

    def _catalog_rows(self) -> list[tuple]:
        now = time.time()
        if (
            self._catalog_cache is not None
            and (now - self._catalog_cache_ts) < self._catalog_ttl_seconds
        ):
            return self._catalog_cache
        query = """
            SELECT table_name, column_name, data_type, ordinal_position
            FROM information_schema.columns
            WHERE table_schema = %s
            ORDER BY table_name, ordinal_position
        """
        with self._get_pool().connection() as conn:
            with conn.cursor() as cur:
                cur.execute(query, (self._schema,))
                rows = cur.fetchall()
        self._catalog_cache = rows
        self._catalog_cache_ts = now
        self._schema_text_cache = None
        self._fingerprint_cache = None
        return rows

    def list_tables(self) -> list[str]:
        return [name for name, _kind in self.list_relations()]

    def list_relations(self) -> list[tuple[str, str]]:
        """Return (name, BASE TABLE|VIEW|MATERIALIZED VIEW) in the configured schema."""
        if not self._config.get("password"):
            return []
        try:
            with self._get_pool().connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        SELECT table_name, table_type
                        FROM information_schema.tables
                        WHERE table_schema = %s
                          AND table_type IN ('BASE TABLE', 'VIEW')
                        UNION ALL
                        SELECT matviewname, 'MATERIALIZED VIEW'
                        FROM pg_catalog.pg_matviews
                        WHERE schemaname = %s
                        ORDER BY 1
                        """,
                        (self._schema, self._schema),
                    )
                    return [(str(row[0]), str(row[1])) for row in cur.fetchall()]
        except Exception:
            return []

    def list_base_tables(self) -> list[str]:
        return [name for name, kind in self.list_relations() if kind == "BASE TABLE"]

    def describe_schema(self) -> str:
        if self._schema_text_cache:
            return self._schema_text_cache
        try:
            lines: list[str] = []
            current_table = None
            for table, column, data_type, _ in self._catalog_rows():
                if table != current_table:
                    current_table = table
                    lines.append(f"TABLE {self._schema}.{table}:")
                lines.append(f"  {column} ({data_type})")
            text = "\n".join(lines)
            # Keep prompt lean: facts + key dims first, cap size
            self._schema_text_cache = text[:4500] if len(text) > 4500 else text
            return self._schema_text_cache
        except Exception:
            return ""

    def count_relation(self, name: str) -> int:
        allowed = {rel for rel, _kind in self.list_relations()}
        if name not in allowed:
            return 0
        with self._get_pool().connection() as conn:
            with conn.cursor() as cur:
                query = pg_sql.SQL("SELECT COUNT(*) FROM {}.{}").format(
                    pg_sql.Identifier(self._schema),
                    pg_sql.Identifier(name),
                )
                cur.execute(query)
                return int(cur.fetchone()[0])

    def table_row_counts(self, include_views: bool = False) -> dict[str, int]:
        counts: dict[str, int] = {}
        if not self._config.get("password"):
            return counts
        try:
            relations = self.list_relations()
            with self._get_pool().connection() as conn:
                with conn.cursor() as cur:
                    for table, kind in relations:
                        if not include_views and kind != "BASE TABLE":
                            continue
                        query = pg_sql.SQL("SELECT COUNT(*) FROM {}.{}").format(
                            pg_sql.Identifier(self._schema),
                            pg_sql.Identifier(table),
                        )
                        cur.execute(query)
                        counts[table] = int(cur.fetchone()[0])
        except Exception:
            return counts
        return counts

    def list_foreign_keys(self) -> list[dict[str, str]]:
        if not self._config.get("password"):
            return []
        query = """
            SELECT
                tc.table_name AS from_table,
                kcu.column_name AS from_column,
                ccu.table_name AS to_table,
                ccu.column_name AS to_column
            FROM information_schema.table_constraints AS tc
            JOIN information_schema.key_column_usage AS kcu
              ON tc.constraint_name = kcu.constraint_name
             AND tc.table_schema = kcu.table_schema
            JOIN information_schema.constraint_column_usage AS ccu
              ON ccu.constraint_name = tc.constraint_name
             AND ccu.table_schema = tc.table_schema
            WHERE tc.constraint_type = 'FOREIGN KEY'
              AND tc.table_schema = %s
            ORDER BY from_table, from_column
        """
        try:
            with self._get_pool().connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(query, (self._schema,))
                    return [
                        {
                            "from_table": str(row[0]),
                            "from_column": str(row[1]),
                            "to_table": str(row[2]),
                            "to_column": str(row[3]),
                        }
                        for row in cur.fetchall()
                    ]
        except Exception:
            return []

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
        if self._fingerprint_cache:
            return self._fingerprint_cache
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
            self._fingerprint_cache = f"postgres:{digest}"
            return self._fingerprint_cache
        except Exception:
            return f"postgres:{self._config.get('database')}:{self._schema}:unavailable"
