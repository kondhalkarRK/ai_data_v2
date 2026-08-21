"""
core/sql_guardrails.py
"""
import re

# ─────────────────────────────────────────────────────────────────
# SQL GUARDRAILS
# ─────────────────────────────────────────────────────────────────
# Only the start of the statement (not every line). MULTILINE false-positives
# on identifiers such as created_at or on CTE bodies.
_BLOCKED = re.compile(
    r'^\s*(drop|delete|truncate|update|insert|alter|create|replace|merge|call|exec|'
    r'copy|attach|detach|export|import|pragma|vacuum|analyze|grant|revoke|set|reset)\b',
    re.IGNORECASE,
)
_CHAINED = re.compile(
    r';\s*\S',
    re.IGNORECASE,
)
_DANGEROUS_FUNCTIONS = re.compile(
    r"\b(pg_sleep|pg_read_file|pg_read_binary_file|pg_ls_dir|lo_import|"
    r"lo_export|dblink|dblink_exec)\s*\(",
    re.IGNORECASE,
)

def sql_is_safe(sql: str) -> tuple[bool, str]:
    statement = (sql or "").strip()
    if not statement:
        return False, "SQL is empty."
    if not re.match(r"^(select|with)\b", statement, re.IGNORECASE):
        return False, "Only SELECT queries and read-only CTEs are permitted."
    if _BLOCKED.search(statement):
        keyword = _BLOCKED.search(statement).group(1).upper()
        return False, f"Statement contains blocked keyword: **{keyword}**. Only SELECT queries are allowed."
    if _CHAINED.search(statement.rstrip(";")):
        return False, "Chained statements are blocked. Only one SELECT query is allowed."
    dangerous = _DANGEROUS_FUNCTIONS.search(statement)
    if dangerous:
        return False, f"Dangerous function blocked: **{dangerous.group(1)}**."
    if not re.search(r'\bSELECT\b', statement, re.IGNORECASE):
        return False, "Only SELECT queries are permitted."
    return True, ""
