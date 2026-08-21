"""DuckDB backend over the current in-memory Pandas working dataset."""
from __future__ import annotations

import hashlib
import json

import duckdb
import pandas as pd

from core.data_backend.base import DataBackend
from core.sql_guardrails import sql_is_safe


class CsvDuckDbBackend(DataBackend):
    def __init__(
        self,
        working_df: pd.DataFrame | None,
        extra_tables: dict[str, pd.DataFrame] | None = None,
    ):
        self._df = working_df
        self._extra_tables = extra_tables or {}

    @property
    def backend_id(self) -> str:
        return "csv_duckdb"

    @property
    def sql_dialect(self) -> str:
        return "DuckDB"

    def health_check(self) -> tuple[bool, str]:
        if self._df is None or self._df.empty:
            return False, "No CSV working dataset is loaded."
        return True, f"{len(self._df):,} rows loaded in DuckDB."

    def _connection(self):
        con = duckdb.connect()
        con.register("df", self._df)
        for table_name, table_df in self._extra_tables.items():
            if isinstance(table_df, pd.DataFrame) and not table_df.empty:
                con.register(str(table_name), table_df)
        return con

    def execute_sql(self, sql: str) -> tuple[pd.DataFrame | None, str | None]:
        safe, reason = sql_is_safe(sql)
        if not safe:
            return None, f"\U0001f512 Blocked: {reason}"
        if self._df is None or self._df.empty:
            return None, "No CSV working dataset is loaded."

        con = None
        try:
            con = self._connection()
            result = con.execute(sql.strip()).df()
            max_rows = 1000
            truncated = len(result) > max_rows
            if truncated:
                result = result.head(max_rows).copy()
            result.attrs["askdb_truncated"] = truncated
            result.attrs["askdb_max_rows"] = max_rows
            return result, None
        except Exception as exc:
            return None, str(exc)
        finally:
            if con is not None:
                con.close()

    def table_row_counts(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        if self._df is not None and not self._df.empty:
            counts["df"] = int(len(self._df))
        for name, frame in self._extra_tables.items():
            if isinstance(frame, pd.DataFrame) and not frame.empty:
                counts[str(name)] = int(len(frame))
        return counts

    def list_tables(self) -> list[str]:
        names = ["df"] if self._df is not None and not self._df.empty else []
        names.extend(
            str(name)
            for name, frame in self._extra_tables.items()
            if isinstance(frame, pd.DataFrame) and not frame.empty
        )
        return sorted(set(names))

    def describe_schema(self) -> str:
        if self._df is None:
            return ""
        lines = ["TABLE df:"]
        lines.extend(f"  {column} ({dtype})" for column, dtype in self._df.dtypes.items())
        return "\n".join(lines)

    def get_preview(self, table: str | None = None, limit: int = 100) -> pd.DataFrame:
        if table and table != "df" and table in self._extra_tables:
            return self._extra_tables[table].head(limit).copy()
        if self._df is None:
            return pd.DataFrame()
        return self._df.head(limit).copy()

    def get_dataset_fingerprint(self) -> str:
        if self._df is None:
            return "csv_duckdb:empty"
        payload = {
            "rows": len(self._df),
            "columns": [(str(c), str(t)) for c, t in self._df.dtypes.items()],
            "tables": self.list_tables(),
        }
        digest = hashlib.sha256(
            json.dumps(payload, sort_keys=True).encode("utf-8")
        ).hexdigest()[:16]
        return f"csv_duckdb:{digest}"
