"""User account model (``auth_users``)."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, Index, Integer, String, text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.config import Industry
from app.models.base import Base, TimestampMixin
from app.models.enums import Role

DEFAULT_WEEKLY_TOKEN_LIMIT = 60_000
DEFAULT_WEEKLY_CALL_LIMIT = 50


class User(TimestampMixin, Base):
    """An application user.

    Accounts are created by an administrator, the seeding CLI or the PoC seed SQL; there
    is no public self-registration. Python attribute names predate the PoC schema, so a
    few map onto differently named columns (``id`` -> ``user_id``, ``is_active`` ->
    ``active``, ``last_login_at`` -> ``last_login``).
    """

    __tablename__ = "auth_users"

    id: Mapped[uuid.UUID] = mapped_column("user_id", primary_key=True, default=uuid.uuid4)
    username: Mapped[str] = mapped_column(String(80), nullable=False, unique=True)
    email: Mapped[str] = mapped_column(String(320), nullable=False)
    # Lower-cased copy used for the uniqueness constraint and for lookups, so
    # "Alice@Example.com" and "alice@example.com" cannot both exist.
    email_normalized: Mapped[str] = mapped_column(String(320), nullable=False, unique=True)
    full_name: Mapped[str] = mapped_column(String(200), nullable=False)

    # Argon2id encoded hash. Never logged, never serialised.
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    password_changed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    must_change_password: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )

    role: Mapped[Role] = mapped_column(
        Enum(Role, name="user_role", native_enum=False, length=20),
        nullable=False,
        server_default=Role.USER.value,
    )
    default_industry: Mapped[Industry] = mapped_column(
        Enum(Industry, name="industry", native_enum=False, length=20),
        nullable=False,
        server_default=Industry.INSURANCE.value,
    )

    # NULL means unlimited (administrators). The database default (60000 / 50) lives in
    # the migration only: an ORM server_default would turn an explicit NULL into the default.
    weekly_token_limit: Mapped[int | None] = mapped_column(Integer, nullable=True)
    weekly_call_limit: Mapped[int | None] = mapped_column(Integer, nullable=True)

    is_active: Mapped[bool] = mapped_column(
        "active", Boolean, nullable=False, server_default=text("true")
    )
    last_login_at: Mapped[datetime | None] = mapped_column(
        "last_login", DateTime(timezone=True), nullable=True
    )

    __table_args__ = (Index("ix_auth_users_role_active", "role", "active"),)

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<User {self.username} role={self.role}>"
