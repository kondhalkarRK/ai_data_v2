"""Common contract for ASK-DB structured-data backends."""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

import pandas as pd


class DataBackend(ABC):
    """Minimal interface used by NLQ, preview, health, and schema discovery."""

    @property
    @abstractmethod
    def backend_id(self) -> str:
        raise NotImplementedError

    @property
    @abstractmethod
    def sql_dialect(self) -> str:
        raise NotImplementedError

    @abstractmethod
    def health_check(self) -> tuple[bool, str]:
        raise NotImplementedError

    @abstractmethod
    def execute_sql(self, sql: str) -> tuple[pd.DataFrame | None, str | None]:
        raise NotImplementedError

    @abstractmethod
    def list_tables(self) -> list[str]:
        raise NotImplementedError

    @abstractmethod
    def describe_schema(self) -> str:
        raise NotImplementedError

    @abstractmethod
    def get_preview(self, table: str | None = None, limit: int = 100) -> pd.DataFrame:
        raise NotImplementedError

    @abstractmethod
    def get_dataset_fingerprint(self) -> str:
        raise NotImplementedError

    def public_status(self) -> dict[str, Any]:
        """Safe connection metadata for UI display; never include credentials."""
        healthy, message = self.health_check()
        return {
            "backend": self.backend_id,
            "dialect": self.sql_dialect,
            "healthy": healthy,
            "message": message,
            "tables": self.list_tables() if healthy else [],
        }
