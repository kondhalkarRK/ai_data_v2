"""Request-scoped context.

This is the typed replacement for ``st.session_state``. The legacy engines reached into
Streamlit's session dictionary from anywhere in the call stack; here the same information
is passed explicitly, which makes the pipeline safe for concurrent users and testable
without a UI runtime.
"""

from __future__ import annotations

from contextvars import ContextVar
from dataclasses import dataclass, field
from datetime import UTC, datetime
from uuid import UUID

from app.core.config import Industry
from app.models.enums import Role


@dataclass(slots=True)
class UsageAccumulator:
    """Token and cost tally for one request.

    Replaces ``st.session_state.llm_calls`` / ``total_tokens`` / ``llm_est_usd``. Flushed
    to the ``llm_usage`` table when the request completes.
    """

    calls: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    estimated_usd: float = 0.0
    models: list[str] = field(default_factory=list)

    def add(
        self,
        *,
        model: str,
        prompt_tokens: int,
        completion_tokens: int,
        estimated_usd: float,
    ) -> None:
        self.calls += 1
        self.prompt_tokens += prompt_tokens
        self.completion_tokens += completion_tokens
        self.estimated_usd += estimated_usd
        if model not in self.models:
            self.models.append(model)

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens


@dataclass(slots=True)
class RequestContext:
    """Everything a service needs to know about the caller and the request."""

    request_id: str
    industry: Industry
    started_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    user_id: UUID | None = None
    role: Role | None = None
    email: str | None = None
    conversation_id: str | None = None
    usage: UsageAccumulator = field(default_factory=UsageAccumulator)

    @property
    def is_authenticated(self) -> bool:
        return self.user_id is not None

    @property
    def elapsed_ms(self) -> int:
        return int((datetime.now(UTC) - self.started_at).total_seconds() * 1000)


_request_context: ContextVar[RequestContext | None] = ContextVar(
    "nql_request_context", default=None
)


def set_request_context(context: RequestContext) -> None:
    _request_context.set(context)


def get_request_context() -> RequestContext | None:
    """Return the current context, or ``None`` outside a request.

    Only logging and tracing should read this. Business code receives the context as an
    argument so its dependencies stay visible in its signature.
    """
    return _request_context.get()


def current_request_id() -> str:
    context = _request_context.get()
    return context.request_id if context else "-"
