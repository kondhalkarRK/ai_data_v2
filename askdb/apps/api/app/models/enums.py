"""Enumerations shared by the ORM models and the API schemas."""

from __future__ import annotations

from enum import StrEnum


class Role(StrEnum):
    """The two PoC roles: ``admin`` governs the platform, ``user`` consumes it.

    ``at_least`` lets a route require ``user`` and still admit an ``admin``.
    """

    ADMIN = "admin"
    USER = "user"

    @property
    def rank(self) -> int:
        return {Role.USER: 0, Role.ADMIN: 1}[self]

    def at_least(self, required: Role) -> bool:
        return self.rank >= required.rank


class ExecutionMode(StrEnum):
    """How an AI Chat question was answered (Hybrid AI Governance dashboard)."""

    SCHEMA = "SCHEMA"  # semantic layer alone, no LLM tokens
    LLM = "LLM"  # the LLM wrote the SQL
    HYBRID = "HYBRID"  # the LLM assisted, governed semantic SQL answered
    CACHE = "CACHE"  # served from the result cache


class AuthEventType(StrEnum):
    """Auth audit event names (spec section 5, 'Include auth audit events')."""

    LOGIN_SUCCEEDED = "login_succeeded"
    LOGIN_FAILED = "login_failed"
    LOGIN_RATE_LIMITED = "login_rate_limited"
    LOGIN_BLOCKED_INACTIVE = "login_blocked_inactive"
    # The S105 suppressions below are false positives: these are event names.
    TOKEN_REFRESHED = "token_refreshed"  # noqa: S105
    TOKEN_REUSE_DETECTED = "token_reuse_detected"  # noqa: S105
    LOGOUT = "logout"
    PASSWORD_CHANGED = "password_changed"  # noqa: S105
    USER_CREATED = "user_created"
    USER_DISABLED = "user_disabled"
    ROLE_CHANGED = "role_changed"
