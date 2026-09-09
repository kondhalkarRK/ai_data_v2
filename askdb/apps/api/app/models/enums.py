"""Enumerations shared by the ORM models and the API schemas."""

from __future__ import annotations

from enum import StrEnum


class Role(StrEnum):
    """Authorization roles (spec section 5).

    Ordered from most to least privileged. ``at_least`` gives a simple hierarchy so a
    route can require ``analyst`` and still admit an ``admin``.
    """

    ADMIN = "admin"
    ANALYST = "analyst"
    VIEWER = "viewer"

    @property
    def rank(self) -> int:
        return {Role.VIEWER: 0, Role.ANALYST: 1, Role.ADMIN: 2}[self]

    def at_least(self, required: Role) -> bool:
        return self.rank >= required.rank


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
