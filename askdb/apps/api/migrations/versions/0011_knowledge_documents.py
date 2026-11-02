"""Traditional RAG document metadata, ACL, chunks and ingest jobs.

Revision ID: 0011_knowledge_documents
Revises: 0010_conversation_session_memory
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0011_knowledge_documents"
down_revision: str | None = "0010_conversation_session_memory"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "knowledge_documents",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("industry", sa.String(length=32), nullable=False),
        sa.Column("title", sa.String(length=500), nullable=False),
        sa.Column("filename", sa.String(length=500), nullable=False),
        sa.Column("content_type", sa.String(length=128), nullable=False),
        sa.Column("byte_size", sa.Integer(), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("collection", sa.String(length=64), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("replaces_document_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("superseded_by_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("status_message", sa.Text(), nullable=True),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("visibility", sa.String(length=32), nullable=False),
        sa.Column("region_zones", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("storage_key", sa.String(length=1024), nullable=False),
        sa.Column("storage_backend", sa.String(length=32), nullable=False),
        sa.Column("embedding_provider", sa.String(length=64), nullable=True),
        sa.Column("embedding_model_id", sa.String(length=128), nullable=True),
        sa.Column("embedding_dimension", sa.Integer(), nullable=True),
        sa.Column("qdrant_collection", sa.String(length=128), nullable=True),
        sa.Column("qdrant_point_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("chunk_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "suggested_questions", postgresql.JSONB(astext_type=sa.Text()), nullable=True
        ),
        sa.Column("entities", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("indexed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"],
            ["auth_users.user_id"],
            name="fk_knowledge_documents_created_by_user_id_auth_users",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["replaces_document_id"],
            ["knowledge_documents.id"],
            name="fk_knowledge_documents_replaces_document_id_knowledge_documents",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["superseded_by_id"],
            ["knowledge_documents.id"],
            name="fk_knowledge_documents_superseded_by_id_knowledge_documents",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_knowledge_documents"),
    )
    op.create_index(
        "ix_knowledge_documents_industry_status",
        "knowledge_documents",
        ["industry", "status"],
    )
    op.create_index("ix_knowledge_documents_content_hash", "knowledge_documents", ["content_hash"])
    op.create_index(
        "ix_knowledge_documents_collection_industry",
        "knowledge_documents",
        ["collection", "industry"],
    )
    op.create_index(
        "ix_knowledge_documents_active_industry",
        "knowledge_documents",
        ["industry", "is_active"],
    )

    op.create_table(
        "knowledge_document_chunks",
        sa.Column("id", sa.String(length=80), nullable=False),
        sa.Column("document_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("locator", sa.String(length=255), nullable=False),
        sa.Column("text_preview", sa.Text(), nullable=False),
        sa.Column("text_content", sa.Text(), nullable=False),
        sa.Column("embedding_model_id", sa.String(length=128), nullable=True),
        sa.Column("qdrant_point_id", sa.String(length=64), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["knowledge_documents.id"],
            name="fk_knowledge_document_chunks_document_id_knowledge_documents",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_knowledge_document_chunks"),
        sa.UniqueConstraint(
            "document_id", "ordinal", name="uq_knowledge_chunks_doc_ordinal"
        ),
    )
    op.create_index(
        "ix_knowledge_document_chunks_document_id",
        "knowledge_document_chunks",
        ["document_id"],
    )

    op.create_table(
        "knowledge_document_acl",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("document_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("principal_type", sa.String(length=32), nullable=False),
        sa.Column("principal_id", sa.String(length=128), nullable=True),
        sa.Column("can_read", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["knowledge_documents.id"],
            name="fk_knowledge_document_acl_document_id_knowledge_documents",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_knowledge_document_acl"),
        sa.UniqueConstraint(
            "document_id",
            "principal_type",
            "principal_id",
            name="uq_knowledge_acl_principal",
        ),
    )
    op.create_index(
        "ix_knowledge_document_acl_document_id",
        "knowledge_document_acl",
        ["document_id"],
    )

    op.create_table(
        "knowledge_ingest_jobs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("document_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("job_type", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("idempotency_key", sa.String(length=191), nullable=False),
        sa.Column("locked_by", sa.String(length=128), nullable=True),
        sa.Column("locked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("max_attempts", sa.Integer(), nullable=False, server_default="5"),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["knowledge_documents.id"],
            name="fk_knowledge_ingest_jobs_document_id_knowledge_documents",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_knowledge_ingest_jobs"),
        sa.UniqueConstraint("idempotency_key", name="uq_knowledge_ingest_jobs_idempotency_key"),
    )
    op.create_index(
        "ix_knowledge_ingest_jobs_status_next",
        "knowledge_ingest_jobs",
        ["status", "next_attempt_at"],
    )
    op.create_index(
        "ix_knowledge_ingest_jobs_document_id",
        "knowledge_ingest_jobs",
        ["document_id"],
    )
    op.execute(
        """
        CREATE INDEX ix_knowledge_ingest_jobs_claimable
        ON knowledge_ingest_jobs (status, next_attempt_at)
        WHERE status IN ('QUEUED', 'RUNNING')
           OR (status = 'FAILED' AND next_attempt_at IS NOT NULL)
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_knowledge_ingest_jobs_claimable")
    op.drop_index("ix_knowledge_ingest_jobs_document_id", table_name="knowledge_ingest_jobs")
    op.drop_index("ix_knowledge_ingest_jobs_status_next", table_name="knowledge_ingest_jobs")
    op.drop_table("knowledge_ingest_jobs")
    op.drop_index("ix_knowledge_document_acl_document_id", table_name="knowledge_document_acl")
    op.drop_table("knowledge_document_acl")
    op.drop_index(
        "ix_knowledge_document_chunks_document_id", table_name="knowledge_document_chunks"
    )
    op.drop_table("knowledge_document_chunks")
    op.drop_index("ix_knowledge_documents_active_industry", table_name="knowledge_documents")
    op.drop_index(
        "ix_knowledge_documents_collection_industry", table_name="knowledge_documents"
    )
    op.drop_index("ix_knowledge_documents_content_hash", table_name="knowledge_documents")
    op.drop_index("ix_knowledge_documents_industry_status", table_name="knowledge_documents")
    op.drop_table("knowledge_documents")
