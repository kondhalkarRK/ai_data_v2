"""Secret redaction for logs.

Spec section 18: prompts, passwords, tokens, connection strings and document contents must
never reach a general log. This module is applied by the logging filter, so redaction does
not depend on every call site remembering to do it.
"""

from __future__ import annotations

import re
from typing import Any, Final

REDACTED: Final = "[redacted]"

# Keys whose values are always removed, whatever they contain.
SENSITIVE_KEYS: Final[frozenset[str]] = frozenset(
    {
        "password",
        "current_password",
        "new_password",
        "password_hash",
        "token",
        "access_token",
        "refresh_token",
        "csrf_token",
        "id_token",
        "authorization",
        "cookie",
        "set-cookie",
        "api_key",
        "apikey",
        "secret",
        "jwt_secret_key",
        "llm_api_key",
        "qdrant_api_key",
        "connection_url",
        "database_url",
        "dsn",
        "prompt",
        "system_prompt",
        "messages",
        "document_text",
        "chunk_text",
        "page_content",
    }
)

_PATTERNS: Final[tuple[tuple[re.Pattern[str], str], ...]] = (
    # postgresql://user:password@host/db  ->  postgresql://user:[redacted]@host/db
    (
        re.compile(r"(?i)\b([a-z0-9+.\-]+://[^:/\s]+:)([^@/\s]+)(@)"),
        rf"\1{REDACTED}\3",
    ),
    # Bearer / Basic credentials in a header value.
    (re.compile(r"(?i)\b(bearer|basic)\s+[A-Za-z0-9._\-~+/=]{8,}"), rf"\1 {REDACTED}"),
    # Compact JWTs.
    (
        re.compile(r"\beyJ[A-Za-z0-9_\-]{4,}\.[A-Za-z0-9_\-]{4,}\.[A-Za-z0-9_\-]{4,}\b"),
        REDACTED,
    ),
    # Common provider key shapes.
    (re.compile(r"\bsk-[A-Za-z0-9]{16,}\b"), REDACTED),
    # key=value / key: value pairs for sensitive names inside free text.
    (
        re.compile(
            r"(?i)\b(password|api[_-]?key|secret|token)\b\s*[=:]\s*[\"']?([^\s\"',;]+)"
        ),
        rf"\1={REDACTED}",
    ),
)

_MAX_STRING_LENGTH: Final = 2000


def redact_text(value: str) -> str:
    redacted = value
    for pattern, replacement in _PATTERNS:
        redacted = pattern.sub(replacement, redacted)
    if len(redacted) > _MAX_STRING_LENGTH:
        redacted = f"{redacted[:_MAX_STRING_LENGTH]}...[truncated]"
    return redacted


def redact(value: Any, *, _depth: int = 0) -> Any:
    """Recursively redact a structure before it is logged or returned in diagnostics."""
    if _depth > 8:
        return "[max depth]"

    if isinstance(value, str):
        return redact_text(value)
    if isinstance(value, dict):
        result: dict[str, Any] = {}
        for key, item in value.items():
            key_text = str(key)
            if key_text.lower() in SENSITIVE_KEYS:
                result[key_text] = REDACTED
            else:
                result[key_text] = redact(item, _depth=_depth + 1)
        return result
    if isinstance(value, list | tuple | set):
        return [redact(item, _depth=_depth + 1) for item in value][:100]
    return value
