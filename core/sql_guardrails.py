"""
core/sql_guardrails.py
"""
import re

# ─────────────────────────────────────────────────────────────────
# SQL GUARDRAILS
# ─────────────────────────────────────────────────────────────────
# Start-of-statement block (SET/RESET/VACUUM etc. and classic DDL/DML).
_BLOCKED_START = re.compile(
    r"^\s*(drop|delete|truncate|update|insert|alter|create|replace|merge|call|exec|"
    r"copy|attach|detach|export|import|pragma|vacuum|analyze|grant|revoke|set|reset)\b",
    re.IGNORECASE,
)
# DML/DDL anywhere (CTE bodies like WITH x AS (DELETE FROM ...)).
_DML_ANYWHERE = re.compile(
    r"\b(drop|delete|truncate|insert|alter|create|replace|merge|call|exec|"
    r"copy|attach|detach|grant|revoke)\b",
    re.IGNORECASE,
)
_SELECT_INTO = re.compile(
    r"\bselect\b[\s\S]+?\binto\b",
    re.IGNORECASE,
)
_FOR_UPDATE = re.compile(r"\bfor\s+update\b", re.IGNORECASE)
_CHAINED = re.compile(
    r";\s*\S",
    re.IGNORECASE,
)
_DANGEROUS_FUNCTIONS = re.compile(
    r"\b(pg_sleep|pg_read_file|pg_read_binary_file|pg_ls_dir|lo_import|"
    r"lo_export|dblink|dblink_exec|read_csv|read_csv_auto|read_blob|"
    r"read_text|read_json|read_parquet)\s*\(",
    re.IGNORECASE,
)


def sql_is_safe(sql: str) -> tuple[bool, str]:
    statement = (sql or "").strip()
    if not statement:
        return False, "SQL is empty."
    if not re.match(r"^(select|with)\b", statement, re.IGNORECASE):
        return False, "Only SELECT queries and read-only CTEs are permitted."
    if _BLOCKED_START.search(statement):
        keyword = _BLOCKED_START.search(statement).group(1).upper()
        return False, (
            f"Statement contains blocked keyword: **{keyword}**. "
            "Only SELECT queries are allowed."
        )
    dml = _DML_ANYWHERE.search(statement)
    if dml:
        return False, (
            f"Statement contains blocked keyword: **{dml.group(1).upper()}**. "
            "Only SELECT queries are allowed."
        )
    if _SELECT_INTO.search(statement):
        return False, "SELECT INTO is blocked. Only read-only SELECT queries are allowed."
    if _FOR_UPDATE.search(statement):
        return False, "FOR UPDATE is blocked. Only read-only SELECT queries are allowed."
    if _CHAINED.search(statement.rstrip(";")):
        return False, "Chained statements are blocked. Only one SELECT query is allowed."
    dangerous = _DANGEROUS_FUNCTIONS.search(statement)
    if dangerous:
        return False, f"Dangerous function blocked: **{dangerous.group(1)}**."
    if not re.search(r"\bSELECT\b", statement, re.IGNORECASE):
        return False, "Only SELECT queries are permitted."
    return True, ""
