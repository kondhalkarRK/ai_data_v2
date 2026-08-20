"""Structured data backends for ASK-DB."""

from core.data_backend.base import DataBackend
from core.data_backend.factory import (
    get_active_backend_id,
    get_backend,
    postgres_mode_enabled,
)

__all__ = [
    "DataBackend",
    "get_active_backend_id",
    "get_backend",
    "postgres_mode_enabled",
]
