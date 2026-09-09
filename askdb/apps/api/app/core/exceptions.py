"""Application error types.

Every failure that reaches the client is one of these. Nothing is swallowed silently:
handlers log the cause with the request id and return a stable, non-leaking payload.
"""

from __future__ import annotations

from typing import Any


class NqlError(Exception):
    """Base class for all deliberate application errors."""

    status_code: int = 500
    code: str = "internal_error"
    message: str = "An unexpected error occurred."

    def __init__(
        self,
        message: str | None = None,
        *,
        code: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        self.message = message or self.message
        self.code = code or self.code
        self.details = details or {}
        super().__init__(self.message)


class AuthenticationError(NqlError):
    status_code = 401
    code = "unauthenticated"
    message = "Authentication is required."


class InvalidCredentialsError(AuthenticationError):
    code = "invalid_credentials"
    # Deliberately identical for unknown users and wrong passwords so the endpoint
    # cannot be used to enumerate accounts.
    message = "Incorrect email or password."


class AccountLockedError(AuthenticationError):
    code = "account_locked"
    message = "This account is disabled. Contact an administrator."


class TokenError(AuthenticationError):
    code = "invalid_token"
    message = "The session token is missing, expired or invalid."


class TokenReuseError(AuthenticationError):
    code = "token_reuse_detected"
    message = "Session revoked because a refresh token was reused."


class AuthorizationError(NqlError):
    status_code = 403
    code = "forbidden"
    message = "You do not have permission to perform this action."


class CsrfError(NqlError):
    status_code = 403
    code = "csrf_failed"
    message = "CSRF validation failed."


class NotFoundError(NqlError):
    status_code = 404
    code = "not_found"
    message = "The requested resource does not exist."


class ConflictError(NqlError):
    status_code = 409
    code = "conflict"
    message = "The request conflicts with the current state."


class ValidationError(NqlError):
    status_code = 422
    code = "validation_failed"
    message = "The request payload is invalid."


class RateLimitedError(NqlError):
    status_code = 429
    code = "rate_limited"
    message = "Too many requests. Try again shortly."

    def __init__(self, retry_after_seconds: int, message: str | None = None) -> None:
        super().__init__(message, details={"retry_after_seconds": retry_after_seconds})
        self.retry_after_seconds = retry_after_seconds


class DependencyUnavailableError(NqlError):
    status_code = 503
    code = "dependency_unavailable"
    message = "A required backing service is unavailable."


class GuardrailViolationError(NqlError):
    """Raised when generated SQL fails the read-only guardrails."""

    status_code = 400
    code = "sql_guardrail_violation"
    message = "The generated query was blocked by SQL guardrails."


class LLMError(NqlError):
    status_code = 502
    code = "llm_error"
    message = "The language model provider could not complete the request."
