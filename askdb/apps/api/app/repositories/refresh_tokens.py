"""Refresh token persistence, including rotation and family revocation."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any, cast

from sqlalchemy import Executable, delete, select, update
from sqlalchemy.engine import CursorResult
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.tokens import IssuedRefreshToken
from app.models.refresh_token import RefreshToken


class RefreshTokenRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def _execute_affecting(self, stmt: Executable) -> int:
        """Run a DML statement and report how many rows it touched.

        ``execute`` is typed as returning ``Result``, but an UPDATE or DELETE always
        yields a ``CursorResult``, which is the only variant carrying ``rowcount``. A
        driver that cannot report a count returns -1, which is normalised to 0.
        """
        result = cast(CursorResult[Any], await self._session.execute(stmt))
        return max(result.rowcount, 0)

    async def store(
        self,
        issued: IssuedRefreshToken,
        *,
        user_id: uuid.UUID,
        user_agent: str | None,
        ip_address: str | None,
    ) -> RefreshToken:
        token = RefreshToken(
            user_id=user_id,
            family_id=issued.family_id,
            token_hash=issued.token_hash,
            expires_at=issued.expires_at,
            user_agent=(user_agent or "")[:400] or None,
            ip_address=ip_address,
        )
        self._session.add(token)
        await self._session.flush()
        return token

    async def get_by_hash(self, token_hash: str) -> RefreshToken | None:
        stmt = select(RefreshToken).where(RefreshToken.token_hash == token_hash)
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def mark_rotated(self, token: RefreshToken) -> None:
        token.rotated_at = datetime.now(UTC)
        await self._session.flush()

    async def revoke(self, token: RefreshToken, *, reason: str) -> None:
        if token.revoked_at is None:
            token.revoked_at = datetime.now(UTC)
            token.revoked_reason = reason
        await self._session.flush()

    async def revoke_family(self, family_id: uuid.UUID, *, reason: str) -> int:
        """Revoke every token in a rotation chain.

        Called when a rotated token is presented a second time, which means either the
        client replayed it or an attacker captured it. Either way the safe response is to
        end the whole session chain.
        """
        stmt = (
            update(RefreshToken)
            .where(
                RefreshToken.family_id == family_id,
                RefreshToken.revoked_at.is_(None),
            )
            .values(revoked_at=datetime.now(UTC), revoked_reason=reason)
        )
        affected = await self._execute_affecting(stmt)
        await self._session.flush()
        return affected

    async def revoke_all_for_user(self, user_id: uuid.UUID, *, reason: str) -> int:
        stmt = (
            update(RefreshToken)
            .where(
                RefreshToken.user_id == user_id,
                RefreshToken.revoked_at.is_(None),
            )
            .values(revoked_at=datetime.now(UTC), revoked_reason=reason)
        )
        affected = await self._execute_affecting(stmt)
        await self._session.flush()
        return affected

    async def purge_expired(self, *, older_than: datetime | None = None) -> int:
        cutoff = older_than or datetime.now(UTC)
        stmt = delete(RefreshToken).where(RefreshToken.expires_at < cutoff)
        return await self._execute_affecting(stmt)
