"""Time helpers.

All application timestamps are timezone-aware UTC. PostgreSQL returns aware datetimes for
``TIMESTAMPTZ``, but SQLite (used by the test suite) returns naive ones, so values read
back from a database are normalised before they are compared.
"""

from __future__ import annotations

from datetime import UTC, datetime


def utc_now() -> datetime:
    return datetime.now(UTC)


def ensure_aware(value: datetime) -> datetime:
    """Interpret a naive datetime as UTC, and leave an aware one unchanged."""
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value
