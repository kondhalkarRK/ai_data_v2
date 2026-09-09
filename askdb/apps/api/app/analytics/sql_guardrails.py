"""Read-only SQL guardrails for analytics queries."""

from __future__ import annotations

import re

_BLOCKED_START = re.compile(
    r"^\s*(drop|delete|truncate|update|insert|alter|create|replace|merge|call|exec|"
    r"copy|attach|detach|export|import|pragma|vacuum|analyze|grant|revoke|set|reset)\b",
    re.IGNORECASE,
)
_DML_ANYWHERE = re.compile(
    r"\b(drop|delete|truncate|insert|alter|create|replace|merge|call|exec|"
    r"copy|attach|detach|grant|revoke)\b",
    re.IGNORECASE,
)
_SELECT_INTO = re.compile(r"\bselect\b[\s\S]+?\binto\b", re.IGNORECASE)
_FOR_UPDATE = re.compile(r"\bfor\s+update\b", re.IGNORECASE)
_CHAINED = re.compile(r";\s*\S", re.IGNORECASE)
_DANGEROUS_FUNCTIONS = re.compile(
    r"\b(pg_sleep|pg_read_file|pg_read_binary_file|pg_ls_dir|lo_import|"
    r"lo_export|dblink|dblink_exec)\s*\(",
    re.IGNORECASE,
)
_IDENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def sql_is_safe(sql: str) -> tuple[bool, str]:
    """Return ``(ok, reason)``. Reason is empty when the statement is allowed."""
    statement = (sql or "").strip()
    if not statement:
        return False, "SQL is empty."
    if not re.match(r"^(select|with)\b", statement, re.IGNORECASE):
        return False, "Only SELECT queries and read-only CTEs are permitted."
    if _BLOCKED_START.search(statement):
        keyword = _BLOCKED_START.search(statement)
        assert keyword is not None
        return False, f"Statement contains blocked keyword: {keyword.group(1).upper()}."
    dml = _DML_ANYWHERE.search(statement)
    if dml:
        return False, f"Statement contains blocked keyword: {dml.group(1).upper()}."
    if _SELECT_INTO.search(statement):
        return False, "SELECT INTO is blocked."
    if _FOR_UPDATE.search(statement):
        return False, "FOR UPDATE is blocked."
    if _CHAINED.search(statement.rstrip(";")):
        return False, "Chained statements are blocked."
    dangerous = _DANGEROUS_FUNCTIONS.search(statement)
    if dangerous:
        return False, f"Dangerous function blocked: {dangerous.group(1)}."
    if not re.search(r"\bSELECT\b", statement, re.IGNORECASE):
        return False, "Only SELECT queries are permitted."
    return True, ""


def qualify_ident(name: str) -> str:
    if not _IDENT.match(name):
        raise ValueError(f"Invalid SQL identifier: {name!r}")
    return f'"{name}"'


def qualify_table(schema: str, table: str) -> str:
    return f"{qualify_ident(schema)}.{qualify_ident(table)}"
