"""Knowledge document ingestion and retrieval."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, File, Form, UploadFile
from pydantic import Field

from app.api.deps import ActiveIndustry, RequireAnalyst, RequireViewer, get_app_settings
from app.core.config import Settings
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


@router.get("")
async def list_documents(
    user: RequireViewer,
    industry: ActiveIndustry,
    settings: Annotated[Settings, Depends(get_app_settings)],
) -> list[dict[str, Any]]:
    return KnowledgeService(settings, industry).list_documents()


@router.post("")
async def upload_document(
    user: RequireAnalyst,
    industry: ActiveIndustry,
    settings: Annotated[Settings, Depends(get_app_settings)],
    file: UploadFile = File(...),
    title: str | None = Form(default=None),
    collection: str | None = Form(default=None),
) -> dict[str, Any]:
    raw = await file.read()
    service = KnowledgeService(settings, industry)
    return service.ingest_bytes(
        title=title or (file.filename or "Untitled"),
        raw=raw,
        filename=file.filename or "upload.txt",
        collection=collection,
    )


@router.post("/reindex")
async def reindex_documents(
    user: RequireAnalyst,
    industry: ActiveIndustry,
    settings: Annotated[Settings, Depends(get_app_settings)],
) -> dict[str, int]:
    return KnowledgeService(settings, industry).reindex_all()


@router.delete("/{document_id}")
async def delete_document(
    document_id: str,
    user: RequireAnalyst,
    industry: ActiveIndustry,
    settings: Annotated[Settings, Depends(get_app_settings)],
) -> dict[str, str]:
    KnowledgeService(settings, industry).delete_document(document_id)
    return {"status": "deleted"}


@router.post("/search")
async def search_documents(
    body: SearchRequest,
    user: RequireViewer,
    industry: ActiveIndustry,
    settings: Annotated[Settings, Depends(get_app_settings)],
) -> list[dict[str, Any]]:
    hits = KnowledgeService(settings, industry).search(
        body.query,
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
