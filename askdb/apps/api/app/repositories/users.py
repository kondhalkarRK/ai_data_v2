"""User data access."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Industry
from app.core.exceptions import ConflictError
from app.models.enums import Role
from app.models.user import DEFAULT_WEEKLY_CALL_LIMIT, DEFAULT_WEEKLY_TOKEN_LIMIT, User


def normalize_email(email: str) -> str:
    return email.strip().lower()


class UserRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(self, user_id: uuid.UUID) -> User | None:
        return await self._session.get(User, user_id)

    async def get_by_email(self, email: str) -> User | None:
        stmt = select(User).where(User.email_normalized == normalize_email(email))
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def get_by_login(self, login: str) -> User | None:
        """Resolve the login form's identifier: a username, or an email address."""
        normalized = normalize_email(login)
        stmt = select(User).where(func.lower(User.username) == normalized)
        user = (await self._session.execute(stmt)).scalar_one_or_none()
        if user is None and "@" in normalized:
            user = await self.get_by_email(normalized)
        return user

    async def count(self) -> int:
        stmt = select(func.count()).select_from(User)
        return int((await self._session.execute(stmt)).scalar_one())

    async def list_all(self, *, limit: int = 100, offset: int = 0) -> list[User]:
        stmt = (
            select(User).order_by(User.created_at.desc()).limit(limit).offset(offset)
        )
        return list((await self._session.execute(stmt)).scalars())

    async def create(
        self,
        *,
        email: str,
        full_name: str,
        password_hash: str,
        role: Role,
        default_industry: Industry,
        must_change_password: bool = False,
        username: str | None = None,
    ) -> User:
        unlimited = role is Role.ADMIN
        user = User(
            username=(username or normalize_email(email)).strip()[:80],
            weekly_token_limit=None if unlimited else DEFAULT_WEEKLY_TOKEN_LIMIT,
            weekly_call_limit=None if unlimited else DEFAULT_WEEKLY_CALL_LIMIT,
            email=email.strip(),
            email_normalized=normalize_email(email),
            full_name=full_name.strip(),
            password_hash=password_hash,
            password_changed_at=datetime.now(UTC),
            must_change_password=must_change_password,
            role=role,
            default_industry=default_industry,
            is_active=True,
        )
        self._session.add(user)
        try:
            await self._session.flush()
        except IntegrityError as exc:
            await self._session.rollback()
            raise ConflictError("An account with that username or email already exists.") from exc
        return user

    async def record_successful_login(self, user: User) -> None:
        user.last_login_at = datetime.now(UTC)
        await self._session.flush()

    async def update_password_hash(self, user: User, password_hash: str) -> None:
        user.password_hash = password_hash
        user.password_changed_at = datetime.now(UTC)
        user.must_change_password = False
        await self._session.flush()

    async def set_active(self, user: User, *, is_active: bool) -> None:
        user.is_active = is_active
        await self._session.flush()

    async def set_role(self, user: User, role: Role) -> None:
        user.role = role
        if role is Role.ADMIN:
            user.weekly_token_limit = user.weekly_call_limit = None
        elif user.weekly_token_limit is None and user.weekly_call_limit is None:
            user.weekly_token_limit = DEFAULT_WEEKLY_TOKEN_LIMIT
            user.weekly_call_limit = DEFAULT_WEEKLY_CALL_LIMIT
        await self._session.flush()

    async def set_default_industry(self, user: User, industry: Industry) -> None:
        user.default_industry = industry
        await self._session.flush()
