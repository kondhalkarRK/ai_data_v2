"""Traditional RAG phases 1–7: schema, storage, jobs, ACL, retrieval guards."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import Industry, Settings
from app.core.exceptions import ValidationError
from app.models.enums import Role
from app.models.knowledge import (
    KnowledgeAclPrincipal,
    KnowledgeDocumentStatus,
    KnowledgeJobType,
    KnowledgeVisibility,
)
from app.models.user import User
from app.rag.acl import RetrievalPrincipal, authorized_document_ids
from app.rag.chunking import chunk_document_text
from app.rag.embeddings import FakeEmbeddingClient, collection_name_for, verify_embedding_identity
from app.rag.job_processor import process_ingest_job
from app.rag.storage import DocumentBlobStore, detect_extension_and_mime, sanitize_filename
from app.repositories.knowledge_documents import KnowledgeDocumentRepository
from app.repositories.users import UserRepository
from app.auth.passwords import hash_password
from app.services.knowledge import KnowledgeService
from app.services.security.region_scope import RegionScope


class FakeQdrant:
    def __init__(self) -> None:
        self.points: dict[str, list[dict[str, Any]]] = {}
        self.deleted: list[str] = []

    def ensure_collection(self, name: str, identity: Any) -> None:
        self.points.setdefault(name, [])

    def upsert_chunks(self, *, collection_name: str, identity: Any, document_id: str, **kwargs: Any) -> list[str]:
        chunks = kwargs["chunks"]
        vectors = kwargs["vectors"]
        self.ensure_collection(collection_name, identity)
        # Drop existing points for document first.
        self.points[collection_name] = [
            p for p in self.points[collection_name] if p["payload"]["documentId"] != document_id
        ]
        ids: list[str] = []
        for chunk, vector in zip(chunks, vectors, strict=True):
            point_id = str(uuid.uuid5(uuid.NAMESPACE_URL, chunk["id"]))
            ids.append(point_id)
            self.points[collection_name].append(
                {
                    "id": point_id,
                    "vector": vector,
                    "payload": {
                        "documentId": document_id,
                        "chunkId": chunk["id"],
                        "title": kwargs["title"],
                        "text": chunk["text_content"],
                        "locator": chunk["locator"],
                        "collection": kwargs["doc_collection"],
                        "industry": kwargs["industry"],
                        "version": kwargs["version"],
                    },
                    "score": 0.9,
                }
            )
        return ids

    def count_points_for_document(self, collection_name: str, document_id: str) -> int:
        return sum(
            1
            for p in self.points.get(collection_name, [])
            if p["payload"]["documentId"] == document_id
        )

    def delete_document_points(self, collection_name: str, document_id: str) -> None:
        self.deleted.append(document_id)
        self.points[collection_name] = [
            p for p in self.points.get(collection_name, []) if p["payload"]["documentId"] != document_id
        ]

    def query(self, *, collection_name: str, query_vector: list[float], allowed_document_ids: list[str], top_k: int, collection_filter: str | None = None):
        from app.rag.qdrant_index import RetrievedPoint

        hits = []
        for point in self.points.get(collection_name, []):
            payload = point["payload"]
            if payload["documentId"] not in allowed_document_ids:
                continue
            if collection_filter and payload.get("collection") != collection_filter:
                continue
            hits.append(
                RetrievedPoint(
                    document_id=payload["documentId"],
                    chunk_id=payload["chunkId"],
                    title=payload["title"],
                    text=payload["text"],
                    locator=payload["locator"],
                    collection=payload["collection"],
                    score=0.95,
                    version=payload.get("version"),
                )
            )
        return hits[:top_k]


@pytest.fixture
def rag_settings(tmp_path, settings: Settings) -> Settings:
    return settings.model_copy(
        update={
            "ask_me_rag_enabled": True,
            "rag_storage_root": str(tmp_path / "knowledge"),
            "rag_embedding_provider": "openai_compatible",
            "rag_embedding_model": "fake-embed",
            "rag_embedding_dimension": 8,
            "rag_worker_in_process": False,
            "rag_job_max_attempts": 3,
            "rag_job_backoff_seconds": 1,
        }
    )


async def _admin_user(session: AsyncSession) -> User:
    repo = UserRepository(session)
    user = await repo.create(
        email=f"rag-admin-{uuid.uuid4().hex[:8]}@example.com",
        full_name="RAG Admin",
        password_hash=hash_password("Vh7!kRq2$mTx9pLw"),
        role=Role.ADMIN,
        default_industry=Industry.INSURANCE,
    )
    await session.commit()
    return user


async def _regular_user(session: AsyncSession) -> User:
    repo = UserRepository(session)
    user = await repo.create(
        email=f"rag-user-{uuid.uuid4().hex[:8]}@example.com",
        full_name="RAG User",
        password_hash=hash_password("Vh7!kRq2$mTx9pLw"),
        role=Role.USER,
        default_industry=Industry.INSURANCE,
    )
    await session.commit()
    return user


def test_sanitize_filename_blocks_traversal() -> None:
    with pytest.raises(ValidationError):
        sanitize_filename("../secret.txt")
    assert sanitize_filename("report (1).pdf") == "report (1).pdf"


def test_detect_mime_rejects_mismatched_pdf() -> None:
    with pytest.raises(ValidationError):
        detect_extension_and_mime(filename="a.pdf", raw=b"not-a-pdf", declared_content_type="application/pdf")


def test_chunking_preserves_locators() -> None:
    text = "# Policy\nSettlement SLA is 7 days.\n\n# Risks\nHigh severity needs review."
    chunks = chunk_document_text(text, max_chars=200, min_chars=10, overlap=20)
    assert chunks
    assert any("page-1" in c.locator for c in chunks)


def test_collection_name_includes_dimension(rag_settings: Settings) -> None:
    client = FakeEmbeddingClient(dimension=8)
    identity = verify_embedding_identity(rag_settings, client)
    name = collection_name_for(rag_settings, industry="insurance", identity=identity)
    assert "_d8" in name
    assert "fake_embed" in name or "fake-embed" in name.replace("-", "_")


@pytest.mark.asyncio
async def test_repository_create_and_claim_job(
    rag_settings: Settings, db_session: AsyncSession
) -> None:
    admin = await _admin_user(db_session)
    repo = KnowledgeDocumentRepository(db_session)
    doc = await repo.create_pending(
        industry="insurance",
        title="Policy",
        filename="policy.txt",
        content_type="text/plain",
        byte_size=12,
        content_hash="abc",
        collection="policies",
        storage_key="insurance/files/x/original.txt",
        storage_backend="local",
        created_by_user_id=admin.id,
    )
    job = await repo.enqueue_job(
        document_id=doc.id,
        job_type=KnowledgeJobType.INGEST,
        idempotency_key=f"ingest:{doc.id}",
    )
    claimed = await repo.claim_next_job(worker_id="test-worker", lease_seconds=60)
    assert claimed is not None
    assert claimed.id == job.id
    assert claimed.status == "RUNNING"
    await db_session.commit()


@pytest.mark.asyncio
async def test_upload_store_and_process_ingest(
    rag_settings: Settings, db_session: AsyncSession
) -> None:
    admin = await _admin_user(db_session)
    fake_qdrant = FakeQdrant()
    embedder = FakeEmbeddingClient(dimension=8)
    service = KnowledgeService(
        rag_settings,
        Industry.INSURANCE,
        session=db_session,
        embedding_client=embedder,
        qdrant=fake_qdrant,  # type: ignore[arg-type]
    )
    result = await service.upload_document(
        user=admin,
        title="Claims FAQ",
        raw=b"Claims settlement SLA is 7 days for standard claims.",
        filename="claims.txt",
        content_type="text/plain",
        collection="policies",
    )
    assert result["status"] == "PENDING"
    doc_id = uuid.UUID(result["id"])
    repo = KnowledgeDocumentRepository(db_session)
    job = await repo.claim_next_job(worker_id="w1", lease_seconds=60)
    assert job is not None
    await db_session.commit()

    outcome = await process_ingest_job(
        db_session,
        rag_settings,
        job.id,
        embedding_client=embedder,
        qdrant=fake_qdrant,  # type: ignore[arg-type]
    )
    assert outcome["status"] == "indexed"
    doc = await repo.get(doc_id)
    assert doc is not None
    assert doc.status == KnowledgeDocumentStatus.INDEXED.value
    assert doc.is_active is True
    assert doc.chunk_count > 0
    assert fake_qdrant.count_points_for_document(doc.qdrant_collection or "", str(doc.id)) == doc.chunk_count


@pytest.mark.asyncio
async def test_region_restricted_fails_closed_when_unresolved(
    rag_settings: Settings, db_session: AsyncSession
) -> None:
    admin = await _admin_user(db_session)
    user = await _regular_user(db_session)
    repo = KnowledgeDocumentRepository(db_session)
    doc = await repo.create_pending(
        industry="insurance",
        title="North policy",
        filename="n.txt",
        content_type="text/plain",
        byte_size=4,
        content_hash="north",
        collection="policies",
        storage_key="insurance/files/n/original.txt",
        storage_backend="local",
        created_by_user_id=admin.id,
        visibility=KnowledgeVisibility.RESTRICTED.value,
        region_zones=["North"],
        grant_all_users=False,
    )
    await repo.set_acl(
        doc.id,
        [(KnowledgeAclPrincipal.ALL_USERS.value, None, True)],
    )
    await repo.set_indexed(
        doc.id,
        chunk_count=1,
        qdrant_collection="c",
        qdrant_point_count=1,
        embedding_provider="openai_compatible",
        embedding_model_id="fake",
        embedding_dimension=8,
    )
    await db_session.commit()

    unresolved = await authorized_document_ids(
        db_session,
        RetrievalPrincipal(user=user, industry="insurance", region_scope=None),
    )
    assert doc.id not in unresolved


@pytest.mark.asyncio
async def test_admin_chat_acl_same_as_user_for_restricted_doc(
    rag_settings: Settings, db_session: AsyncSession
) -> None:
    admin = await _admin_user(db_session)
    repo = KnowledgeDocumentRepository(db_session)
    doc = await repo.create_pending(
        industry="insurance",
        title="Secret",
        filename="s.txt",
        content_type="text/plain",
        byte_size=4,
        content_hash="secret",
        collection="policies",
        storage_key="insurance/files/s/original.txt",
        storage_backend="local",
        created_by_user_id=admin.id,
        visibility=KnowledgeVisibility.RESTRICTED.value,
        grant_all_users=False,
    )
    await repo.set_acl(doc.id, [(KnowledgeAclPrincipal.USER.value, str(uuid.uuid4()), True)])
    await repo.set_indexed(
        doc.id,
        chunk_count=1,
        qdrant_collection="c",
        qdrant_point_count=1,
        embedding_provider="openai_compatible",
        embedding_model_id="fake",
        embedding_dimension=8,
    )
    await db_session.commit()
    allowed = await authorized_document_ids(
        db_session,
        RetrievalPrincipal(
            user=admin,
            industry="insurance",
            region_scope=RegionScope.all_regions(admin),
        ),
    )
    assert doc.id not in allowed


@pytest.mark.asyncio
async def test_delete_excludes_immediately_even_before_vector_cleanup(
    rag_settings: Settings, db_session: AsyncSession
) -> None:
    admin = await _admin_user(db_session)
    fake_qdrant = FakeQdrant()
    embedder = FakeEmbeddingClient(dimension=8)
    service = KnowledgeService(
        rag_settings,
        Industry.INSURANCE,
        session=db_session,
        embedding_client=embedder,
        qdrant=fake_qdrant,  # type: ignore[arg-type]
    )
    uploaded = await service.upload_document(
        user=admin,
        title="Temp",
        raw=b"Temporary policy text for deletion test.",
        filename="temp.txt",
        content_type="text/plain",
    )
    doc_id = uuid.UUID(uploaded["id"])
    repo = KnowledgeDocumentRepository(db_session)
    job = await repo.claim_next_job(worker_id="w1", lease_seconds=60)
    assert job is not None
    await db_session.commit()
    await process_ingest_job(
        db_session,
        rag_settings,
        job.id,
        embedding_client=embedder,
        qdrant=fake_qdrant,  # type: ignore[arg-type]
    )
    await service.delete_document_rag(user=admin, document_id=str(doc_id))
    allowed = await authorized_document_ids(
        db_session,
        RetrievalPrincipal(
            user=admin,
            industry="insurance",
            region_scope=RegionScope.all_regions(admin),
        ),
    )
    assert doc_id not in allowed
    doc = await repo.get(doc_id)
    assert doc is not None
    assert doc.status == KnowledgeDocumentStatus.DELETED.value


@pytest.mark.asyncio
async def test_retry_cannot_reactivate_deleted(
    rag_settings: Settings, db_session: AsyncSession
) -> None:
    admin = await _admin_user(db_session)
    repo = KnowledgeDocumentRepository(db_session)
    blobs = DocumentBlobStore(rag_settings, Industry.INSURANCE)
    document_id = uuid.uuid4()
    stored = blobs.write_original(
        document_id=document_id,
        filename="gone.txt",
        raw=b"Gone document body.",
        declared_content_type="text/plain",
    )
    doc = await repo.create_pending(
        industry="insurance",
        title="Gone",
        filename=stored.safe_filename,
        content_type=stored.content_type,
        byte_size=stored.byte_size,
        content_hash="gone",
        collection="general",
        storage_key=stored.storage_key,
        storage_backend="local",
        created_by_user_id=admin.id,
        document_id=document_id,
    )
    await repo.soft_delete(doc.id)
    job = await repo.enqueue_job(
        document_id=doc.id,
        job_type=KnowledgeJobType.INGEST,
        idempotency_key=f"retry-deleted:{doc.id}",
    )
    await db_session.commit()
    outcome = await process_ingest_job(
        db_session,
        rag_settings,
        job.id,
        embedding_client=FakeEmbeddingClient(8),
        qdrant=FakeQdrant(),  # type: ignore[arg-type]
    )
    assert outcome["status"] == "skipped"
    refreshed = await repo.get(doc.id)
    assert refreshed is not None
    assert refreshed.status == KnowledgeDocumentStatus.DELETED.value
    assert refreshed.is_active is False


@pytest.mark.asyncio
async def test_search_authorized_never_returns_unauthorized_text(
    rag_settings: Settings, db_session: AsyncSession
) -> None:
    admin = await _admin_user(db_session)
    user = await _regular_user(db_session)
    fake_qdrant = FakeQdrant()
    embedder = FakeEmbeddingClient(dimension=8)
    service = KnowledgeService(
        rag_settings,
        Industry.INSURANCE,
        session=db_session,
        embedding_client=embedder,
        qdrant=fake_qdrant,  # type: ignore[arg-type]
    )
    uploaded = await service.upload_document(
        user=admin,
        title="Open policy",
        raw=b"Open settlement policy text visible to all users.",
        filename="open.txt",
        content_type="text/plain",
    )
    repo = KnowledgeDocumentRepository(db_session)
    job = await repo.claim_next_job(worker_id="w1", lease_seconds=60)
    assert job is not None
    await db_session.commit()
    await process_ingest_job(
        db_session,
        rag_settings,
        job.id,
        embedding_client=embedder,
        qdrant=fake_qdrant,  # type: ignore[arg-type]
    )

    # Inject an unauthorized point into the fake collection.
    collection = (await repo.get(uuid.UUID(uploaded["id"]))).qdrant_collection  # type: ignore[union-attr]
    fake_qdrant.points[collection or ""].append(
        {
            "id": "leak",
            "vector": [0.1] * 8,
            "payload": {
                "documentId": str(uuid.uuid4()),
                "chunkId": "leak:0",
                "title": "Secret",
                "text": "TOP SECRET UNAUTHORIZED CONTENT",
                "locator": "chunk-1",
                "collection": "policies",
                "industry": "insurance",
                "version": 1,
            },
            "score": 1.0,
        }
    )

    hits = await service.search_authorized(
        "settlement",
        user=user,
        region_scope=RegionScope(
            unrestricted=False,
            zones=("North", "South", "East", "West"),
            user_id=user.id,
            username=user.username,
        ),
    )
    joined = " ".join(h.snippet for h in hits)
    assert "TOP SECRET UNAUTHORIZED CONTENT" not in joined


@pytest.mark.asyncio
async def test_legacy_hash_search_blocked_when_rag_on(
    rag_settings: Settings, db_session: AsyncSession
) -> None:
    service = KnowledgeService(rag_settings, Industry.INSURANCE, session=db_session)
    with pytest.raises(ValidationError):
        service.search("hello")


@pytest.mark.asyncio
async def test_supersede_atomic_activation(
    rag_settings: Settings, db_session: AsyncSession
) -> None:
    admin = await _admin_user(db_session)
    fake_qdrant = FakeQdrant()
    embedder = FakeEmbeddingClient(dimension=8)
    service = KnowledgeService(
        rag_settings,
        Industry.INSURANCE,
        session=db_session,
        embedding_client=embedder,
        qdrant=fake_qdrant,  # type: ignore[arg-type]
    )
    first = await service.upload_document(
        user=admin,
        title="Policy v1",
        raw=b"Version one settlement is 10 days.",
        filename="p1.txt",
        content_type="text/plain",
    )
    repo = KnowledgeDocumentRepository(db_session)
    job1 = await repo.claim_next_job(worker_id="w1", lease_seconds=60)
    assert job1 is not None
    await db_session.commit()
    await process_ingest_job(
        db_session,
        rag_settings,
        job1.id,
        embedding_client=embedder,
        qdrant=fake_qdrant,  # type: ignore[arg-type]
    )
    second = await service.upload_document(
        user=admin,
        title="Policy v2",
        raw=b"Version two settlement is 7 days.",
        filename="p2.txt",
        content_type="text/plain",
        replaces_document_id=uuid.UUID(first["id"]),
    )
    job2 = await repo.claim_next_job(worker_id="w1", lease_seconds=60)
    assert job2 is not None
    await db_session.commit()
    await process_ingest_job(
        db_session,
        rag_settings,
        job2.id,
        embedding_client=embedder,
        qdrant=fake_qdrant,  # type: ignore[arg-type]
    )
    old = await repo.get(uuid.UUID(first["id"]))
    new = await repo.get(uuid.UUID(second["id"]))
    assert old is not None and new is not None
    assert old.status == KnowledgeDocumentStatus.SUPERSEDED.value
    assert old.is_active is False
    assert new.status == KnowledgeDocumentStatus.INDEXED.value
    assert new.is_active is True
