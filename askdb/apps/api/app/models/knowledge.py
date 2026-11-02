"""Traditional RAG document metadata (PostgreSQL system of record)."""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, JsonDocument


class KnowledgeDocumentStatus(StrEnum):
    PENDING = "PENDING"
    EXTRACTING = "EXTRACTING"
    CHUNKING = "CHUNKING"
    EMBEDDING = "EMBEDDING"
    INDEXING = "INDEXING"
    INDEXED = "INDEXED"
    FAILED = "FAILED"
    SUPERSEDED = "SUPERSEDED"
    DELETED = "DELETED"


class KnowledgeVisibility(StrEnum):
    INDUSTRY_WIDE = "INDUSTRY_WIDE"
    RESTRICTED = "RESTRICTED"


class KnowledgeJobStatus(StrEnum):
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    DONE = "DONE"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class KnowledgeJobType(StrEnum):
    INGEST = "INGEST"
    REINDEX = "REINDEX"
    DELETE_VECTORS = "DELETE_VECTORS"
    SUPERSEDE_CLEANUP = "SUPERSEDE_CLEANUP"


class KnowledgeAclPrincipal(StrEnum):
    ALL_USERS = "ALL_USERS"
    ROLE = "ROLE"
    USER = "USER"
    REGION = "REGION"


class KnowledgeDocument(Base):
    __tablename__ = "knowledge_documents"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    industry: Mapped[str] = mapped_column(String(32), nullable=False)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    filename: Mapped[str] = mapped_column(String(500), nullable=False)
    content_type: Mapped[str] = mapped_column(String(128), nullable=False)
    byte_size: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    collection: Mapped[str] = mapped_column(String(64), nullable=False, default="general")
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    replaces_document_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("knowledge_documents.id", ondelete="SET NULL"), nullable=True
    )
    superseded_by_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("knowledge_documents.id", ondelete="SET NULL"), nullable=True
    )
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default=KnowledgeDocumentStatus.PENDING.value
    )
    status_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    next_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    visibility: Mapped[str] = mapped_column(
        String(32), nullable=False, default=KnowledgeVisibility.INDUSTRY_WIDE.value
    )
    region_zones: Mapped[list[str] | None] = mapped_column(JsonDocument, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    storage_key: Mapped[str] = mapped_column(String(1024), nullable=False)
    storage_backend: Mapped[str] = mapped_column(String(32), nullable=False, default="local")
    embedding_provider: Mapped[str | None] = mapped_column(String(64), nullable=True)
    embedding_model_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    embedding_dimension: Mapped[int | None] = mapped_column(Integer, nullable=True)
    qdrant_collection: Mapped[str | None] = mapped_column(String(128), nullable=True)
    qdrant_point_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    chunk_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    suggested_questions: Mapped[list[str] | None] = mapped_column(JsonDocument, nullable=True)
    entities: Mapped[list[str] | None] = mapped_column(JsonDocument, nullable=True)
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("auth_users.user_id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
    indexed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    chunks: Mapped[list[KnowledgeDocumentChunk]] = relationship(
        back_populates="document", cascade="all, delete-orphan"
    )
    acl_rules: Mapped[list[KnowledgeDocumentAcl]] = relationship(
        back_populates="document", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("ix_knowledge_documents_industry_status", "industry", "status"),
        Index("ix_knowledge_documents_content_hash", "content_hash"),
        Index("ix_knowledge_documents_collection_industry", "collection", "industry"),
        Index("ix_knowledge_documents_active_industry", "industry", "is_active"),
    )


class KnowledgeDocumentChunk(Base):
    __tablename__ = "knowledge_document_chunks"

    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    document_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("knowledge_documents.id", ondelete="CASCADE"), nullable=False
    )
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    locator: Mapped[str] = mapped_column(String(255), nullable=False)
    text_preview: Mapped[str] = mapped_column(Text, nullable=False)
    text_content: Mapped[str] = mapped_column(Text, nullable=False)
    embedding_model_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    qdrant_point_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    document: Mapped[KnowledgeDocument] = relationship(back_populates="chunks")

    __table_args__ = (
        UniqueConstraint("document_id", "ordinal", name="uq_knowledge_chunks_doc_ordinal"),
        Index("ix_knowledge_document_chunks_document_id", "document_id"),
    )


class KnowledgeDocumentAcl(Base):
    __tablename__ = "knowledge_document_acl"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    document_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("knowledge_documents.id", ondelete="CASCADE"), nullable=False
    )
    principal_type: Mapped[str] = mapped_column(String(32), nullable=False)
    principal_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    can_read: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    document: Mapped[KnowledgeDocument] = relationship(back_populates="acl_rules")

    __table_args__ = (
        Index("ix_knowledge_document_acl_document_id", "document_id"),
        UniqueConstraint(
            "document_id",
            "principal_type",
            "principal_id",
            name="uq_knowledge_acl_principal",
        ),
    )


class KnowledgeIngestJob(Base):
    __tablename__ = "knowledge_ingest_jobs"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    document_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("knowledge_documents.id", ondelete="CASCADE"), nullable=False
    )
    job_type: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default=KnowledgeJobStatus.QUEUED.value
    )
    idempotency_key: Mapped[str] = mapped_column(String(191), nullable=False, unique=True)
    locked_by: Mapped[str | None] = mapped_column(String(128), nullable=True)
    locked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    lease_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=5)
    next_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    payload: Mapped[dict | None] = mapped_column(JsonDocument, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        Index("ix_knowledge_ingest_jobs_status_next", "status", "next_attempt_at"),
        Index("ix_knowledge_ingest_jobs_document_id", "document_id"),
    )
