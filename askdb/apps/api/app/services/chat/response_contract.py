"""Presentation outcomes derived from executed workflow state, not question wording."""

from typing import Literal

ResponseKind = Literal[
    "conversation",
    "definition",
    "clarification",
    "data",
    "report",
    "partial",
    "unavailable",
    "denied",
    "empty",
    "cancelled",
    "failed",
]


def response_kind(path: str, *, sql=False, rows=0, failed=False, partial=False) -> ResponseKind:
    if failed or path in {"recovery", "typed_error"}:
        return "failed"
    if path == "cancelled":
        return "cancelled"
    if "denied" in path:
        return "denied"
    if path == "clarification":
        return "clarification"
    if partial:
        return "partial"
    if path in {"report", "typed_report"}:
        return "report"
    if path == "definition":
        return "definition"
    if sql:
        return "data" if rows else "empty"
    if any(key in path for key in ("unavailable", "unsupported", "disabled")):
        return "unavailable"
    return "conversation"
