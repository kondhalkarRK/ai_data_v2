"""SQL helpers for interactive NLQ safety and profiling."""

from __future__ import annotations

import re


_LIMIT_RE = re.compile(r"\blimit\s+\d+\b", re.IGNORECASE)


def ensure_result_limit(sql: str, limit: int) -> str:
    """Cap result size; never remove an existing stricter LIMIT."""
    cleaned = (sql or "").strip().rstrip(";")
    if not cleaned:
        return cleaned
    match = _LIMIT_RE.search(cleaned)
    if match:
        existing = int(re.search(r"\d+", match.group(0)).group(0))  # type: ignore[union-attr]
        if existing <= limit:
            return cleaned
        return _LIMIT_RE.sub(f"LIMIT {limit}", cleaned, count=1)
    return f"{cleaned}\nLIMIT {limit}"
