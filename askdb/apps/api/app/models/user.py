"""User account model."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, Index, String, text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.config import Industry
from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import Role


class User(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """An application user.

    Accounts are created by an administrator or by the seeding CLI; there is no public
    self-registration (spec section 5).
    """

    __tablename__ = "users"

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
        server_default=Role.VIEWER.value,
    )
    default_industry: Mapped[Industry] = mapped_column(
        Enum(Industry, name="industry", native_enum=False, length=20),
        nullable=False,
        server_default=Industry.INSURANCE.value,
    )

    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("true")
    )
    last_login_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    __table_args__ = (Index("ix_users_role_active", "role", "is_active"),)

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<User {self.email_normalized} role={self.role}>"
