"""
core/sql_guardrails.py
"""
import re

# ─────────────────────────────────────────────────────────────────
# SQL GUARDRAILS
# ─────────────────────────────────────────────────────────────────
_BLOCKED = re.compile(
    r'^\s*(drop|delete|truncate|update|insert|alter|create|replace|merge|call|exec)\b',
    re.IGNORECASE | re.MULTILINE,
)

def sql_is_safe(sql: str) -> tuple[bool, str]:
    if _BLOCKED.search(sql):
        keyword = _BLOCKED.search(sql).group(1).upper()
        return False, f"Statement contains blocked keyword: **{keyword}**. Only SELECT queries are allowed."
    if not re.search(r'\bSELECT\b', sql, re.IGNORECASE):
        return False, "Only SELECT queries are permitted."
    return True, ""
