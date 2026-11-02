"""Durable Traditional RAG ingest job processing (idempotent, restart-safe)."""

from __future__ import annotations

import logging
import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Industry, Settings
from app.core.exceptions import ValidationError
from app.models.knowledge import (
    KnowledgeDocumentStatus,
    KnowledgeJobType,
)
from app.rag.chunking import chunk_document_text
from app.rag.embeddings import (
    EmbeddingClient,
    EmbeddingIdentity,
    build_embedding_client,
    collection_name_for,
    embed_texts_batched,
    verify_embedding_identity,
)
from app.rag.parsers import extract_text
from app.rag.qdrant_index import QdrantIndex
from app.rag.storage import DocumentBlobStore
from app.repositories.knowledge_documents import KnowledgeDocumentRepository
from app.services.knowledge import extract_entities, suggested_questions_for

logger = logging.getLogger(__name__)


async def process_ingest_job(
    session: AsyncSession,
    settings: Settings,
    job_id: uuid.UUID,
    *,
    embedding_client: EmbeddingClient | None = None,
    qdrant: QdrantIndex | None = None,
) -> dict[str, Any]:
    """Reusable entry point for in-process and production workers."""
    repo = KnowledgeDocumentRepository(session)
    job = await repo.get_job(job_id)
    if job is None:
        return {"status": "missing"}
    doc = await repo.get(job.document_id)
    if doc is None:
        await repo.mark_job_failed(job_id, error="Document missing", backoff_seconds=0, cancel=True)
        return {"status": "failed", "error": "document_missing"}

    # Retries must never reactivate deleted or superseded documents.
    if doc.status in {
        KnowledgeDocumentStatus.DELETED.value,
        KnowledgeDocumentStatus.SUPERSEDED.value,
    }:
        await repo.mark_job_done(job_id)
        return {"status": "skipped", "reason": doc.status}

    job_type = job.job_type
    try:
        if job_type == KnowledgeJobType.DELETE_VECTORS.value:
            result = await _delete_vectors(repo, settings, doc, qdrant=qdrant)
        elif job_type == KnowledgeJobType.SUPERSEDE_CLEANUP.value:
            result = await _supersede_cleanup(repo, settings, doc, job.payload or {}, qdrant=qdrant)
        elif job_type in {
            KnowledgeJobType.INGEST.value,
            KnowledgeJobType.REINDEX.value,
        }:
            result = await _ingest_or_reindex(
                session,
                settings,
                repo,
                doc,
                job_id=job_id,
                embedding_client=embedding_client,
                qdrant=qdrant,
            )
        else:
            raise ValidationError(f"Unknown job type {job_type}")
        await repo.mark_job_done(job_id)
        await session.commit()
        return result
    except Exception as exc:
        logger.exception("Ingest job %s failed", job_id)
        await session.rollback()
        # Re-bind after rollback.
        repo = KnowledgeDocumentRepository(session)
        job = await repo.get_job(job_id)
        doc = await repo.get(job.document_id) if job else None
        if doc is not None and doc.status not in {
            KnowledgeDocumentStatus.DELETED.value,
            KnowledgeDocumentStatus.SUPERSEDED.value,
        }:
            await repo.transition_status(
                doc.id,
                KnowledgeDocumentStatus.FAILED,
                message=str(exc)[:1000],
            )
        if job is not None:
            await repo.mark_job_failed(
                job_id,
                error=str(exc),
                backoff_seconds=settings.rag_job_backoff_seconds,
            )
        await session.commit()
        return {"status": "failed", "error": str(exc)[:500]}


async def _ingest_or_reindex(
    session: AsyncSession,
    settings: Settings,
    repo: KnowledgeDocumentRepository,
    doc: Any,
    *,
    job_id: uuid.UUID,
    embedding_client: EmbeddingClient | None,
    qdrant: QdrantIndex | None,
) -> dict[str, Any]:
    # Re-check terminal states before each stage.
    fresh = await repo.get(doc.id)
    if fresh is None or fresh.status in {
        KnowledgeDocumentStatus.DELETED.value,
        KnowledgeDocumentStatus.SUPERSEDED.value,
    }:
        return {"status": "skipped", "reason": fresh.status if fresh else "missing"}

    industry = Industry(doc.industry)
    store = DocumentBlobStore(settings, industry)
    raw = store.read_bytes(doc.storage_key)
    await repo.renew_lease(job_id, lease_seconds=settings.rag_job_lease_seconds)

    await repo.transition_status(doc.id, KnowledgeDocumentStatus.EXTRACTING)
    text = extract_text(doc.filename, raw)
    if not text.strip():
        raise ValidationError("Document produced no extractable text.")
    store.write_extracted_text(doc.id, text)

    await repo.transition_status(doc.id, KnowledgeDocumentStatus.CHUNKING)
    pieces = chunk_document_text(
        text,
        max_chars=settings.rag_chunk_max_chars,
        min_chars=settings.rag_chunk_min_chars,
        overlap=settings.rag_chunk_overlap_chars,
    )
    if not pieces:
        raise ValidationError("Chunking produced no passages.")

    client = embedding_client or build_embedding_client(settings)
    identity = verify_embedding_identity(settings, client)
    collection = collection_name_for(settings, industry=doc.industry, identity=identity)

    await repo.transition_status(doc.id, KnowledgeDocumentStatus.EMBEDDING)
    await repo.renew_lease(job_id, lease_seconds=settings.rag_job_lease_seconds)
    vectors = embed_texts_batched(
        client,
        [piece.text for piece in pieces],
        batch_size=settings.rag_embedding_batch_size,
    )

    chunk_rows: list[dict[str, Any]] = []
    for piece in pieces:
        chunk_id = f"{doc.id}:{piece.ordinal}"
        chunk_rows.append(
            {
                "id": chunk_id,
                "ordinal": piece.ordinal,
                "locator": piece.locator,
                "text_preview": piece.text[:400],
                "text_content": piece.text,
                "embedding_model_id": identity.model_id,
            }
        )

    index = qdrant or QdrantIndex(settings)
    # Clean any partial prior upsert for this document before writing.
    try:
        index.delete_document_points(collection, str(doc.id))
    except Exception:
        logger.debug("pre-upsert cleanup skipped", exc_info=True)

    await repo.transition_status(doc.id, KnowledgeDocumentStatus.INDEXING)
    await repo.renew_lease(job_id, lease_seconds=settings.rag_job_lease_seconds)
    try:
        point_ids = index.upsert_chunks(
            collection_name=collection,
            identity=identity,
            document_id=str(doc.id),
            industry=doc.industry,
            title=doc.title,
            doc_collection=doc.collection,
            version=doc.version,
            region_zones=list(doc.region_zones or []),
            chunks=chunk_rows,
            vectors=vectors,
        )
    except Exception:
        # Partial upsert cleanup.
        index.delete_document_points(collection, str(doc.id))
        raise

    verified = index.count_points_for_document(collection, str(doc.id))
    if verified != len(chunk_rows):
        index.delete_document_points(collection, str(doc.id))
        raise ValidationError(
            f"Qdrant verification failed: expected {len(chunk_rows)} points, found {verified}."
        )

    for row, point_id in zip(chunk_rows, point_ids, strict=True):
        row["qdrant_point_id"] = point_id

    # Final terminal-state check before activation.
    fresh = await repo.get(doc.id)
    if fresh is None or fresh.status in {
        KnowledgeDocumentStatus.DELETED.value,
        KnowledgeDocumentStatus.SUPERSEDED.value,
    }:
        index.delete_document_points(collection, str(doc.id))
        return {"status": "skipped", "reason": fresh.status if fresh else "missing"}

    await repo.replace_chunks(doc.id, chunk_rows)
    entities = extract_entities(f"{doc.title} {text[:4000]}")
    fresh.entities = entities
    fresh.suggested_questions = suggested_questions_for(doc.collection)
    await repo.set_indexed(
        doc.id,
        chunk_count=len(chunk_rows),
        qdrant_collection=collection,
        qdrant_point_count=verified,
        embedding_provider=identity.provider,
        embedding_model_id=identity.model_id,
        embedding_dimension=identity.dimension,
    )

    # Atomic supersede of previous version after successful indexing verification.
    if fresh.replaces_document_id is not None:
        old_id = fresh.replaces_document_id
        await repo.supersede_atomically(old_id=old_id, new_id=fresh.id)
        await repo.enqueue_job(
            document_id=old_id,
            job_type=KnowledgeJobType.SUPERSEDE_CLEANUP,
            idempotency_key=f"supersede-cleanup:{old_id}:{fresh.id}",
            payload={"replacement_id": str(fresh.id)},
            max_attempts=settings.rag_job_max_attempts,
        )

    return {
        "status": "indexed",
        "document_id": str(doc.id),
        "chunks": len(chunk_rows),
        "collection": collection,
        "dimension": identity.dimension,
    }


async def _delete_vectors(
    repo: KnowledgeDocumentRepository,
    settings: Settings,
    doc: Any,
    *,
    qdrant: QdrantIndex | None,
) -> dict[str, Any]:
    index = qdrant or QdrantIndex(settings)
    collection = doc.qdrant_collection
    if collection:
        index.delete_document_points(collection, str(doc.id))
    return {"status": "vectors_deleted", "document_id": str(doc.id)}


async def _supersede_cleanup(
    repo: KnowledgeDocumentRepository,
    settings: Settings,
    doc: Any,
    payload: dict[str, Any],
    *,
    qdrant: QdrantIndex | None,
) -> dict[str, Any]:
    # Only clean vectors for superseded docs; never reactivate.
    if doc.status != KnowledgeDocumentStatus.SUPERSEDED.value:
        return {"status": "skipped", "reason": doc.status}
    return await _delete_vectors(repo, settings, doc, qdrant=qdrant)


async def claim_and_process_one(
    session: AsyncSession,
    settings: Settings,
    *,
    worker_id: str,
    embedding_client: EmbeddingClient | None = None,
    qdrant: QdrantIndex | None = None,
) -> dict[str, Any] | None:
    repo = KnowledgeDocumentRepository(session)
    job = await repo.claim_next_job(
        worker_id=worker_id, lease_seconds=settings.rag_job_lease_seconds
    )
    if job is None:
        await session.commit()
        return None
    job_id = job.id
    await session.commit()
    return await process_ingest_job(
        session,
        settings,
        job_id,
        embedding_client=embedding_client,
        qdrant=qdrant,
    )
