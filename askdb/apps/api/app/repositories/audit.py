"""Authentication audit persistence."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit import AuthAuditEvent
from app.models.enums import AuthEventType


class AuthAuditRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def record(
        self,
        event_type: AuthEventType,
        *,
        succeeded: bool,
        user_id: uuid.UUID | None = None,
        email_attempted: str | None = None,
        request_id: str | None = None,
        ip_address: str | None = None,
        user_agent: str | None = None,
        reason: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        self._session.add(
            AuthAuditEvent(
                event_type=event_type,
                succeeded=succeeded,
                user_id=user_id,
                email_attempted=(email_attempted or "").lower()[:320] or None,
                request_id=request_id,
                ip_address=ip_address if ip_address and ip_address != "unknown" else None,
                user_agent=(user_agent or "")[:400] or None,
                reason=(reason or "")[:120] or None,
                metadata_json=metadata,
            )
        )
        await self._session.flush()

    async def recent(
        self, *, limit: int = 50, user_id: uuid.UUID | None = None
    ) -> list[AuthAuditEvent]:
        stmt = select(AuthAuditEvent).order_by(AuthAuditEvent.occurred_at.desc()).limit(limit)
        if user_id is not None:
            stmt = stmt.where(AuthAuditEvent.user_id == user_id)
        return list((await self._session.execute(stmt)).scalars())
