"""Knowledge ingestion, chunking, retrieval, and citations.

When ``ASK_ME_RAG_ENABLED`` is false, the legacy filesystem + hash path is used.
When true, PostgreSQL metadata, durable jobs, real embeddings and Qdrant retrieval
are used — never the hash fallback.
"""

from __future__ import annotations

import hashlib
import re
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Industry, Settings
from app.core.exceptions import AuthorizationError, NotFoundError, ValidationError
from app.models.enums import Role
from app.models.knowledge import (
    KnowledgeDocument,
    KnowledgeDocumentStatus,
    KnowledgeJobType,
    KnowledgeVisibility,
)
from app.models.user import User
from app.rag.acl import RetrievalPrincipal, authorized_document_ids, region_resolution
from app.rag.embeddings import (
    EmbeddingClient,
    build_embedding_client,
    collection_name_for,
    verify_embedding_identity,
)
from app.rag.feature import rag_enabled
from app.rag.parsers import extract_text
from app.rag.qdrant_index import QdrantIndex
from app.rag.storage import DocumentBlobStore
from app.rag.store import KnowledgeStore
from app.repositories.knowledge_documents import KnowledgeDocumentRepository
from app.services.security.region_scope import RegionScope

COLLECTIONS = (
    "dealer_reports",
    "market_research",
    "product_catalogs",
    "sales_reports",
    "policies",
    "general",
)

_ENTITY_TERMS = (
    "hyundai",
    "toyota",
    "suzuki",
    "honda",
    "tata",
    "kia",
    "mahindra",
    "mumbai",
    "delhi",
    "pune",
    "bengaluru",
    "bangalore",
    "chennai",
    "hyderabad",
    "kolkata",
    "suv",
    "sedan",
    "hatchback",
    "muv",
    "ev",
    "electric",
)


@dataclass(slots=True)
class Citation:
    document_id: str
    title: str
    chunk_id: str
    snippet: str
    locator: str
    untrusted: bool = False
    confidence: float = 0.0
    collection: str = "general"


def _hash_embed(text: str, dims: int) -> list[float]:
    digest = hashlib.sha256(text.encode("utf-8")).digest()
    values: list[float] = []
    while len(values) < dims:
        digest = hashlib.sha256(digest).digest()
        for byte in digest:
            values.append((byte / 255.0) * 2 - 1)
            if len(values) >= dims:
                break
    return values


def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    na = sum(x * x for x in a) ** 0.5
    nb = sum(y * y for y in b) ** 0.5
    return dot / (na * nb) if na and nb else 0.0


def _clip_confidence(score: float) -> float:
    return max(0.0, min(1.0, (score + 1.0) / 2.0))


def infer_collection(title: str, filename: str, explicit: str | None = None) -> str:
    if explicit and explicit in COLLECTIONS:
        return explicit
    blob = f"{title} {filename}".casefold()
    if "catalog" in blob:
        return "product_catalogs"
    if "policy" in blob or "policies" in blob:
        return "policies"
    if "market" in blob or "research" in blob:
        return "market_research"
    if "dealer" in blob:
        return "dealer_reports"
    if "sales" in blob:
        return "sales_reports"
    return "general"


def extract_entities(text: str) -> list[str]:
    found: list[str] = []
    low = text.casefold()
    for term in _ENTITY_TERMS:
        if re.search(rf"\b{re.escape(term)}\b", low):
            found.append(term)
    for match in re.findall(r"\b([A-Z][a-z]{2,}(?:\s+[A-Z][a-z]{2,})?)\b", text):
        key = match.casefold()
        if key not in found and len(key) >= 3:
            found.append(key)
    seen: set[str] = set()
    out: list[str] = []
    for item in found:
        if item not in seen:
            seen.add(item)
            out.append(item)
    return out[:24]


def suggested_questions_for(collection: str) -> list[str]:
    common = [
        "What are the key findings?",
        "What concerns or risks are mentioned?",
        "Which models or products are mentioned?",
        "What recommendations does the document make?",
    ]
    extras = {
        "dealer_reports": ["Which dealers or regions are highlighted?"],
        "market_research": ["What market trends are described?"],
        "product_catalogs": ["Which models are in the catalog?"],
        "sales_reports": ["What sales issues or wins are called out?"],
        "policies": ["What policy rules are stated?"],
    }
    return common + extras.get(collection, [])


def chunk_text(text: str, *, max_chars: int, min_chars: int, overlap: int) -> list[str]:
    cleaned = re.sub(r"\s+", " ", text).strip()
    if not cleaned:
        return []
    if len(cleaned) <= max_chars:
        return [cleaned]
    chunks: list[str] = []
    start = 0
    while start < len(cleaned):
        end = min(len(cleaned), start + max_chars)
        piece = cleaned[start:end].strip()
        if len(piece) >= min_chars or end >= len(cleaned):
            chunks.append(piece)
        if end >= len(cleaned):
            break
        start = max(end - overlap, start + 1)
    return chunks


def _serialize_document(doc: KnowledgeDocument) -> dict[str, Any]:
    return {
        "id": str(doc.id),
        "title": doc.title,
        "filename": doc.filename,
        "chunkCount": doc.chunk_count,
        "createdAt": doc.created_at.isoformat() if doc.created_at else None,
        "updatedAt": doc.updated_at.isoformat() if doc.updated_at else None,
        "indexedAt": doc.indexed_at.isoformat() if doc.indexed_at else None,
        "version": doc.version,
        "collection": doc.collection,
        "status": doc.status,
        "statusMessage": doc.status_message,
        "byteSize": doc.byte_size,
        "contentType": doc.content_type,
        "visibility": doc.visibility,
        "regionZones": list(doc.region_zones or []),
        "isActive": doc.is_active,
        "uploaderUserId": str(doc.created_by_user_id) if doc.created_by_user_id else None,
        "suggestedQuestions": list(doc.suggested_questions or []),
        "entities": list(doc.entities or []),
        "embeddingModelId": doc.embedding_model_id,
        "embeddingDimension": doc.embedding_dimension,
        "qdrantPointCount": doc.qdrant_point_count,
        "supersededById": str(doc.superseded_by_id) if doc.superseded_by_id else None,
        "replacesDocumentId": (
            str(doc.replaces_document_id) if doc.replaces_document_id else None
        ),
    }


class KnowledgeService:
    def __init__(
        self,
        settings: Settings,
        industry: Industry,
        session: AsyncSession | None = None,
        *,
        embedding_client: EmbeddingClient | None = None,
        qdrant: QdrantIndex | None = None,
    ) -> None:
        self._settings = settings
        self._industry = industry
        self._session = session
        self._store = KnowledgeStore(settings, industry)
        self._embedding_client = embedding_client
        self._qdrant = qdrant

    def _require_session(self) -> AsyncSession:
        if self._session is None:
            raise ValidationError("Database session is required when RAG is enabled.")
        return self._session

    def list_documents(self) -> list[dict[str, Any]]:
        """Legacy filesystem listing (RAG off)."""
        return self._store.list_documents()

    async def list_documents_authorized(
        self,
        *,
        user: User,
        region_scope: RegionScope | None,
    ) -> list[dict[str, Any]]:
        if not rag_enabled(self._settings):
            return self.list_documents()
        session = self._require_session()
        repo = KnowledgeDocumentRepository(session)
        if user.role is Role.ADMIN:
            docs = await repo.list_for_admin(self._industry.value)
            return [_serialize_document(doc) for doc in docs]
        allowed = await authorized_document_ids(
            session,
            RetrievalPrincipal(
                user=user, industry=self._industry.value, region_scope=region_scope
            ),
        )
        # Also show the user's own in-progress uploads (not yet INDEXED).
        all_industry = await repo.list_for_admin(self._industry.value)
        visible: list[KnowledgeDocument] = []
        for doc in all_industry:
            if doc.status == KnowledgeDocumentStatus.SUPERSEDED.value:
                continue
            if doc.status == KnowledgeDocumentStatus.DELETED.value:
                continue
            if doc.id in allowed:
                visible.append(doc)
                continue
            if (
                doc.created_by_user_id == user.id
                and doc.status != KnowledgeDocumentStatus.INDEXED.value
            ):
                visible.append(doc)
        return [_serialize_document(doc) for doc in visible]

    def ingest_text(
        self,
        *,
        title: str,
        text: str,
        filename: str,
        collection: str | None = None,
    ) -> dict[str, Any]:
        if rag_enabled(self._settings):
            raise ValidationError(
                "Legacy ingest_text is unavailable when ASK_ME_RAG_ENABLED=true."
            )
        suffix = Path(filename).suffix.lower() or ".txt"
        allowed = {ext.lower() for ext in self._settings.upload_allowed_extensions}
        if suffix not in allowed and suffix not in {".txt", ".md", ".html"}:
            raise ValidationError(f"Unsupported upload type '{suffix}'.")
        if len(text.encode("utf-8")) > self._settings.upload_max_bytes:
            raise ValidationError("Upload exceeds the configured size limit.")
        content_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()
        existing = self._store.find_by_hash(content_hash)
        if existing is not None:
            return {**existing, "deduped": True}
        chosen = infer_collection(title, filename, collection)
        doc_id = content_hash[:16]
        pieces = chunk_text(
            text,
            max_chars=self._settings.rag_chunk_max_chars,
            min_chars=self._settings.rag_chunk_min_chars,
            overlap=self._settings.rag_chunk_overlap_chars,
        )
        doc_entities = extract_entities(f"{title} {text[:4000]}")
        chunks = [
            {
                "id": f"{doc_id}:{index}",
                "text": piece,
                "embedding": _hash_embed(piece, self._settings.qdrant_vector_size),
                "locator": f"chunk-{index + 1}",
                "entities": extract_entities(piece) or doc_entities,
            }
            for index, piece in enumerate(pieces)
        ]
        return self._store.save_document(
            title=title or filename,
            filename=filename,
            content_hash=content_hash,
            raw_text=text,
            chunks=chunks,
            collection=chosen,
            suggested_questions=suggested_questions_for(chosen),
            entities=doc_entities,
        )

    def ingest_bytes(
        self,
        *,
        title: str,
        raw: bytes,
        filename: str,
        collection: str | None = None,
    ) -> dict[str, Any]:
        if rag_enabled(self._settings):
            raise ValidationError(
                "Use async upload_document when ASK_ME_RAG_ENABLED=true."
            )
        if len(raw) > self._settings.upload_max_bytes:
            raise ValidationError("Upload exceeds the configured size limit.")
        suffix = Path(filename).suffix.lower()
        if suffix not in {ext.lower() for ext in self._settings.upload_allowed_extensions}:
            raise ValidationError(f"Unsupported upload type '{suffix or '(none)'}'.")
        return self.ingest_text(
            title=title,
            text=extract_text(filename, raw),
            filename=filename,
            collection=collection,
        )

    async def upload_document(
        self,
        *,
        user: User,
        title: str,
        raw: bytes,
        filename: str,
        content_type: str | None = None,
        collection: str | None = None,
        visibility: str = KnowledgeVisibility.INDUSTRY_WIDE.value,
        region_zones: list[str] | None = None,
        replaces_document_id: uuid.UUID | None = None,
    ) -> dict[str, Any]:
        if not rag_enabled(self._settings):
            raise AuthorizationError("RAG mutations are disabled.")
        if user.role is not Role.ADMIN:
            raise AuthorizationError("Only administrators may upload documents.")
        session = self._require_session()
        repo = KnowledgeDocumentRepository(session)
        content_hash = hashlib.sha256(raw).hexdigest()
        existing = await repo.find_active_by_hash(
            industry=self._industry.value, content_hash=content_hash
        )
        if existing is not None and replaces_document_id is None:
            return {**_serialize_document(existing), "deduped": True}

        version = 1
        if replaces_document_id is not None:
            previous = await repo.get(replaces_document_id)
            if previous is None or previous.industry != self._industry.value:
                raise NotFoundError("Document to replace was not found.")
            if previous.status in {
                KnowledgeDocumentStatus.DELETED.value,
                KnowledgeDocumentStatus.SUPERSEDED.value,
            }:
                raise ValidationError("Cannot replace a deleted or superseded document.")
            version = int(previous.version) + 1

        document_id = uuid.uuid4()
        blobs = DocumentBlobStore(self._settings, self._industry)
        stored = blobs.write_original(
            document_id=document_id,
            filename=filename,
            raw=raw,
            declared_content_type=content_type,
        )
        chosen = infer_collection(title, stored.safe_filename, collection)
        doc = await repo.create_pending(
            industry=self._industry.value,
            title=title or stored.safe_filename,
            filename=stored.safe_filename,
            content_type=stored.content_type,
            byte_size=stored.byte_size,
            content_hash=content_hash,
            collection=chosen,
            storage_key=stored.storage_key,
            storage_backend=self._settings.rag_storage_backend,
            created_by_user_id=user.id,
            visibility=visibility,
            region_zones=region_zones,
            replaces_document_id=replaces_document_id,
            version=version,
            suggested_questions=suggested_questions_for(chosen),
            grant_all_users=visibility == KnowledgeVisibility.INDUSTRY_WIDE.value,
            document_id=document_id,
        )
        await repo.enqueue_job(
            document_id=doc.id,
            job_type=KnowledgeJobType.INGEST,
            idempotency_key=f"ingest:{doc.id}:v{doc.version}",
            max_attempts=self._settings.rag_job_max_attempts,
        )
        await session.commit()
        return _serialize_document(doc)

    async def delete_document_rag(self, *, user: User, document_id: str) -> None:
        if user.role is not Role.ADMIN:
            raise AuthorizationError("Only administrators may delete documents.")
        session = self._require_session()
        repo = KnowledgeDocumentRepository(session)
        try:
            doc_uuid = uuid.UUID(document_id)
        except ValueError as exc:
            raise NotFoundError("Document not found.") from exc
        doc = await repo.get(doc_uuid)
        if doc is None or doc.industry != self._industry.value:
            raise NotFoundError("Document not found.")
        await repo.soft_delete(doc_uuid)
        await repo.cancel_jobs_for_document(
            doc_uuid,
            except_types={KnowledgeJobType.DELETE_VECTORS.value},
        )
        await repo.enqueue_job(
            document_id=doc_uuid,
            job_type=KnowledgeJobType.DELETE_VECTORS,
            idempotency_key=f"delete-vectors:{doc_uuid}:{uuid.uuid4().hex[:8]}",
            max_attempts=self._settings.rag_job_max_attempts,
        )
        await session.commit()

    def delete_document(self, document_id: str) -> None:
        if rag_enabled(self._settings):
            raise ValidationError("Use async delete_document_rag when RAG is enabled.")
        self._store.delete_document(document_id)

    def search(
        self,
        query: str,
        *,
        top_k: int | None = None,
        user_id: str | None = None,
        collection: str | None = None,
        entities: list[str] | None = None,
    ) -> list[Citation]:
        if rag_enabled(self._settings):
            raise ValidationError(
                "Legacy hash search is unavailable when ASK_ME_RAG_ENABLED=true. "
                "Use search_authorized."
            )
        query = query.strip()
        if not query:
            raise ValidationError("Query is required.")
        query_vector = _hash_embed(query, self._settings.qdrant_vector_size)
        wanted = {item.casefold() for item in (entities or []) if item}
        rows = self._store.iter_chunks(collection=collection)
        if wanted:
            filtered = [
                (meta, chunk)
                for meta, chunk in rows
                if _chunk_mentions(meta, chunk, wanted)
            ]
            if filtered:
                rows = filtered
        scored: list[tuple[float, Citation]] = []
        for meta, chunk in rows:
            score = _cosine(query_vector, chunk["embedding"])
            scored.append(
                (
                    score,
                    Citation(
                        document_id=meta["id"],
                        title=meta["title"],
                        chunk_id=chunk["id"],
                        snippet=chunk["text"][:400],
                        locator=chunk["locator"],
                        confidence=_clip_confidence(score),
                        collection=str(meta.get("collection") or "general"),
                    ),
                )
            )
        scored.sort(key=lambda item: item[0], reverse=True)
        hits = [citation for _, citation in scored[: top_k or self._settings.rag_top_k]]
        self._store.append_retrieval_audit(
            query,
            [
                {
                    "documentId": hit.document_id,
                    "chunkId": hit.chunk_id,
                    "locator": hit.locator,
                    "confidence": hit.confidence,
                }
                for hit in hits
            ],
            user_id,
        )
        return hits

    async def search_authorized(
        self,
        query: str,
        *,
        user: User,
        region_scope: RegionScope | None,
        top_k: int | None = None,
        collection: str | None = None,
        entities: list[str] | None = None,
    ) -> list[Citation]:
        """Centralized ACL-aware retrieval used by Hub search, knowledge chat and hybrid."""
        query = query.strip()
        if not query:
            raise ValidationError("Query is required.")
        if not rag_enabled(self._settings):
            return self.search(
                query,
                top_k=top_k,
                user_id=str(user.id),
                collection=collection,
                entities=entities,
            )

        session = self._require_session()
        allowed = await authorized_document_ids(
            session,
            RetrievalPrincipal(
                user=user, industry=self._industry.value, region_scope=region_scope
            ),
        )
        if not allowed:
            return []

        client = self._embedding_client or build_embedding_client(self._settings)
        identity = verify_embedding_identity(self._settings, client)
        collection_name = collection_name_for(
            self._settings, industry=self._industry.value, identity=identity
        )
        index = self._qdrant or QdrantIndex(self._settings)
        query_vector = client.embed_query(query)
        points = index.query(
            collection_name=collection_name,
            query_vector=query_vector,
            allowed_document_ids=[str(item) for item in allowed],
            top_k=top_k or self._settings.rag_top_k,
            collection_filter=collection,
        )

        # Permission re-check before returning content to callers / LLM.
        allowed_str = {str(item) for item in allowed}
        hits: list[Citation] = []
        for point in points:
            if point.document_id not in allowed_str:
                continue
            if entities:
                wanted = {item.casefold() for item in entities if item}
                blob = f"{point.text} {point.title}".casefold()
                if wanted and not any(term in blob for term in wanted):
                    continue
            hits.append(
                Citation(
                    document_id=point.document_id,
                    title=point.title,
                    chunk_id=point.chunk_id,
                    snippet=point.text[:400],
                    locator=point.locator,
                    confidence=_clip_confidence(point.score),
                    collection=point.collection,
                )
            )
        self._store.append_retrieval_audit(
            query,
            [
                {
                    "documentId": hit.document_id,
                    "chunkId": hit.chunk_id,
                    "locator": hit.locator,
                    "confidence": hit.confidence,
                }
                for hit in hits
            ],
            str(user.id),
        )
        return hits

    def reindex(self) -> dict[str, int]:
        if rag_enabled(self._settings):
            raise ValidationError("Use async reindex_rag when RAG is enabled.")
        count = 0
        for meta in self._store.list_documents():
            text = self._store.read_text(meta["id"])
            if not text:
                continue
            pieces = chunk_text(
                text,
                max_chars=self._settings.rag_chunk_max_chars,
                min_chars=self._settings.rag_chunk_min_chars,
                overlap=self._settings.rag_chunk_overlap_chars,
            )
            self._store.replace_chunks(
                meta["id"],
                [
                    {
                        "id": f"{meta['id']}:{index}",
                        "text": piece,
                        "embedding": _hash_embed(
                            piece, self._settings.qdrant_vector_size
                        ),
                        "locator": f"chunk-{index + 1}",
                        "entities": extract_entities(piece),
                    }
                    for index, piece in enumerate(pieces)
                ],
            )
            count += 1
        return {"documents": count}

    def reindex_all(self) -> dict[str, int]:
        return self.reindex()

    async def reindex_rag(self, *, user: User) -> dict[str, int]:
        if user.role is not Role.ADMIN:
            raise AuthorizationError("Only administrators may reindex documents.")
        session = self._require_session()
        repo = KnowledgeDocumentRepository(session)
        docs = await repo.list_for_admin(self._industry.value)
        queued = 0
        for doc in docs:
            if doc.status in {
                KnowledgeDocumentStatus.DELETED.value,
                KnowledgeDocumentStatus.SUPERSEDED.value,
            }:
                continue
            await repo.enqueue_job(
                document_id=doc.id,
                job_type=KnowledgeJobType.REINDEX,
                idempotency_key=f"reindex:{doc.id}:{uuid.uuid4().hex[:8]}",
                max_attempts=self._settings.rag_job_max_attempts,
            )
            queued += 1
        await session.commit()
        return {"documents": queued}

    async def retry_document(self, *, user: User, document_id: str) -> dict[str, Any]:
        if user.role is not Role.ADMIN:
            raise AuthorizationError("Only administrators may retry ingestion.")
        session = self._require_session()
        repo = KnowledgeDocumentRepository(session)
        try:
            doc_uuid = uuid.UUID(document_id)
        except ValueError as exc:
            raise NotFoundError("Document not found.") from exc
        doc = await repo.get(doc_uuid)
        if doc is None or doc.industry != self._industry.value:
            raise NotFoundError("Document not found.")
        if doc.status in {
            KnowledgeDocumentStatus.DELETED.value,
            KnowledgeDocumentStatus.SUPERSEDED.value,
        }:
            raise ValidationError("Cannot retry a deleted or superseded document.")
        await repo.transition_status(doc_uuid, KnowledgeDocumentStatus.PENDING, message="Retry queued")
        await repo.enqueue_job(
            document_id=doc_uuid,
            job_type=KnowledgeJobType.INGEST,
            idempotency_key=f"retry:{doc_uuid}:{uuid.uuid4().hex[:8]}",
            max_attempts=self._settings.rag_job_max_attempts,
        )
        await session.commit()
        refreshed = await repo.get(doc_uuid)
        assert refreshed is not None
        return _serialize_document(refreshed)



def _chunk_mentions(
    meta: dict[str, Any], chunk: dict[str, Any], wanted: set[str]
) -> bool:
    tags = [str(item).casefold() for item in (chunk.get("entities") or meta.get("entities") or [])]
    blob = f"{chunk.get('text', '')} {meta.get('title', '')}".casefold()
    return any(term in tags or term in blob for term in wanted)
