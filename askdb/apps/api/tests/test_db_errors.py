from __future__ import annotations

from sqlalchemy.exc import OperationalError, ProgrammingError

from app.db.errors import classify_database_error


class _PgError(Exception):
    def __init__(self, sqlstate: str | None) -> None:
        super().__init__("boom")
        self.sqlstate = sqlstate


def test_missing_column_reports_schema_out_of_date() -> None:
    exc = ProgrammingError("SELECT 1", {}, _PgError("42703"))
    assert classify_database_error(exc)[0] == "schema_out_of_date"


def test_missing_table_reports_schema_out_of_date() -> None:
    exc = ProgrammingError("SELECT 1", {}, _PgError("42P01"))
    assert classify_database_error(exc)[0] == "schema_out_of_date"


def test_connection_failure_reports_database_unavailable() -> None:
    exc = OperationalError("connect", {}, _PgError(None))
    code, message = classify_database_error(exc)
    assert code == "database_unavailable"
    assert "credentials" in message


def test_other_errors_stay_generic() -> None:
    exc = ProgrammingError("SELECT 1", {}, _PgError("42601"))
    assert classify_database_error(exc)[0] == "internal_error"
