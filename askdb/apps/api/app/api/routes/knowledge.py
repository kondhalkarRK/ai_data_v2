"""Knowledge document ingestion and retrieval."""

from __future__ import annotations

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, File, Form, UploadFile
from pydantic import Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import (
    ActiveIndustry,
    AppSession,
    RegionScopeDep,
    RequireAdmin,
    RequireRagMutations,
    RequireUser,
    get_app_settings,
)
from app.core.config import Settings
from app.rag.feature import rag_enabled
from app.schemas.common import ApiModel
from app.services.knowledge import KnowledgeService
from app.services.web_retrieval import WebRetrievalService

router = APIRouter(prefix="/documents", tags=["knowledge"])


class SearchRequest(ApiModel):
    query: str = Field(min_length=1, max_length=2000)
    top_k: int | None = Field(default=None, ge=1, le=20)
    web_retrieval: bool = False
    collection: str | None = None
    entities: list[str] = Field(default_factory=list)


def _service(
    settings: Settings,
    industry: ActiveIndustry,
    session: AsyncSession | None,
) -> KnowledgeService:
    return KnowledgeService(settings, industry, session=session)


@router.get("")
async def list_documents(
    user: RequireUser,
    industry: ActiveIndustry,
    settings: Annotated[Settings, Depends(get_app_settings)],
    session: AppSession,
    region_scope: RegionScopeDep,
) -> list[dict[str, Any]]:
    service = _service(settings, industry, session if rag_enabled(settings) else None)
    if rag_enabled(settings):
        return await service.list_documents_authorized(
            user=user, region_scope=region_scope
        )
    return service.list_documents()


@router.post("")
async def upload_document(
    user: RequireAdmin,
    industry: ActiveIndustry,
    _rag: RequireRagMutations,
    settings: Annotated[Settings, Depends(get_app_settings)],
    session: AppSession,
    file: UploadFile = File(...),
    title: str | None = Form(default=None),
    collection: str | None = Form(default=None),
    visibility: str = Form(default="INDUSTRY_WIDE"),
    region_zones: str | None = Form(default=None),
    replaces_document_id: str | None = Form(default=None),
) -> dict[str, Any]:
    raw = await file.read()
    zones = [z.strip() for z in (region_zones or "").split(",") if z.strip()] or None
    replace_id = uuid.UUID(replaces_document_id) if replaces_document_id else None
    service = _service(settings, industry, session)
    return await service.upload_document(
        user=user,
        title=title or (file.filename or "Untitled"),
        raw=raw,
        filename=file.filename or "upload.txt",
        content_type=file.content_type,
        collection=collection,
        visibility=visibility,
        region_zones=zones,
        replaces_document_id=replace_id,
    )


@router.post("/reindex")
async def reindex_documents(
    user: RequireAdmin,
    industry: ActiveIndustry,
    _rag: RequireRagMutations,
    settings: Annotated[Settings, Depends(get_app_settings)],
    session: AppSession,
) -> dict[str, int]:
    if rag_enabled(settings):
        return await _service(settings, industry, session).reindex_rag(user=user)
    return KnowledgeService(settings, industry).reindex_all()


@router.post("/{document_id}/retry")
async def retry_document(
    document_id: str,
    user: RequireAdmin,
    industry: ActiveIndustry,
    _rag: RequireRagMutations,
    settings: Annotated[Settings, Depends(get_app_settings)],
    session: AppSession,
) -> dict[str, Any]:
    return await _service(settings, industry, session).retry_document(
        user=user, document_id=document_id
    )


@router.delete("/{document_id}")
async def delete_document(
    document_id: str,
    user: RequireAdmin,
    industry: ActiveIndustry,
    _rag: RequireRagMutations,
    settings: Annotated[Settings, Depends(get_app_settings)],
    session: AppSession,
) -> dict[str, str]:
    if rag_enabled(settings):
        await _service(settings, industry, session).delete_document_rag(
            user=user, document_id=document_id
        )
    else:
        KnowledgeService(settings, industry).delete_document(document_id)
    return {"status": "deleted"}


@router.post("/search")
async def search_documents(
    body: SearchRequest,
    user: RequireUser,
    industry: ActiveIndustry,
    settings: Annotated[Settings, Depends(get_app_settings)],
    session: AppSession,
    region_scope: RegionScopeDep,
) -> list[dict[str, Any]]:
    service = _service(settings, industry, session if rag_enabled(settings) else None)
    hits = await service.search_authorized(
        body.query,
        user=user,
        region_scope=region_scope,
        top_k=body.top_k,
        collection=body.collection,
        entities=body.entities or None,
    )
    if body.web_retrieval:
        hits.extend(
            await WebRetrievalService(settings).retrieve(
                body.query, opted_in=body.web_retrieval
            )
        )
    return [
        {
            "documentId": hit.document_id,
            "title": hit.title,
            "chunkId": hit.chunk_id,
            "snippet": hit.snippet,
            "locator": hit.locator,
            "untrusted": hit.untrusted,
            "confidence": hit.confidence,
            "collection": hit.collection,
        }
        for hit in hits
    ]
