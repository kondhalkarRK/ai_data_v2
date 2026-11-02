"""Centralized authorized document retrieval helpers."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.repositories.knowledge_documents import KnowledgeDocumentRepository
from app.services.security.region_scope import RegionScope


@dataclass(frozen=True, slots=True)
class RetrievalPrincipal:
    user: User
    industry: str
    region_scope: RegionScope | None


def region_resolution(scope: RegionScope | None) -> tuple[bool, set[str] | None]:
    """Return (region_resolved, zones).

    Admin with unrestricted access is treated as resolved with all zones.
    Unresolved scopes fail closed for region-restricted documents.
    """
    if scope is None:
        return False, None
    if getattr(scope, "unrestricted", False):
        return True, {"North", "South", "East", "West"}
    zones = set(getattr(scope, "zones", ()) or ())
    if not zones:
        # Explicit empty grant: resolved but no zones → region-restricted docs denied.
        return True, set()
    return True, zones


async def authorized_document_ids(
    session: AsyncSession,
    principal: RetrievalPrincipal,
) -> set[uuid.UUID]:
    repo = KnowledgeDocumentRepository(session)
    resolved, zones = region_resolution(principal.region_scope)
    return await repo.allowed_document_ids(
        industry=principal.industry,
        user=principal.user,
        user_zones=zones,
        region_resolved=resolved,
        for_chat=True,
    )
