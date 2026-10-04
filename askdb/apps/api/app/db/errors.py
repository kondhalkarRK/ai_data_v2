"""Map raw database failures to stable, actionable messages without leaking SQL."""

from __future__ import annotations

from sqlalchemy.exc import DBAPIError, OperationalError

# PostgreSQL SQLSTATE codes for a schema that is behind the ORM models.
_SCHEMA_STATES = {"42P01", "42703"}  # undefined_table, undefined_column

DATABASE_UNAVAILABLE = (
    "The application database is unreachable or rejected the login. Check that PostgreSQL "
    "is running and that the askdb_app credentials in .env match the database."
)
SCHEMA_OUT_OF_DATE = (
    "The application database schema is out of date. From the askdb folder run: "
    "python scripts/migrate.py app upgrade head, then restart the API."
)


def classify_database_error(exc: DBAPIError) -> tuple[str, str]:
    sqlstate = getattr(exc.orig, "sqlstate", None) or getattr(exc.orig, "pgcode", None)
    if sqlstate in _SCHEMA_STATES:
        return "schema_out_of_date", SCHEMA_OUT_OF_DATE
    if isinstance(exc, OperationalError) or exc.connection_invalidated:
        return "database_unavailable", DATABASE_UNAVAILABLE
    return "internal_error", "An unexpected error occurred. Quote the request id when reporting it."
