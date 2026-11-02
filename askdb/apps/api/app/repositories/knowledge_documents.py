"""PostgreSQL repository for Traditional RAG documents, ACL, chunks and jobs."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any, Sequence

from sqlalchemy import Select, and_, delete, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.enums import Role
from app.models.knowledge import (
    KnowledgeAclPrincipal,
    KnowledgeDocument,
    KnowledgeDocumentAcl,
    KnowledgeDocumentChunk,
    KnowledgeDocumentStatus,
    KnowledgeIngestJob,
    KnowledgeJobStatus,
    KnowledgeJobType,
    KnowledgeVisibility,
)
from app.models.user import User


class KnowledgeDocumentRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, document_id: uuid.UUID) -> KnowledgeDocument | None:
        return await self._session.get(KnowledgeDocument, document_id)

    async def get_with_relations(self, document_id: uuid.UUID) -> KnowledgeDocument | None:
        stmt = (
            select(KnowledgeDocument)
            .where(KnowledgeDocument.id == document_id)
            .options(
                selectinload(KnowledgeDocument.acl_rules),
                selectinload(KnowledgeDocument.chunks),
            )
        )
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def find_active_by_hash(
        self, *, industry: str, content_hash: str
    ) -> KnowledgeDocument | None:
        stmt = (
            select(KnowledgeDocument)
            .where(
                KnowledgeDocument.industry == industry,
                KnowledgeDocument.content_hash == content_hash,
                KnowledgeDocument.status.notin_(
                    [
                        KnowledgeDocumentStatus.DELETED.value,
                        KnowledgeDocumentStatus.SUPERSEDED.value,
                    ]
                ),
            )
            .order_by(KnowledgeDocument.created_at.desc())
            .limit(1)
        )
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def create_pending(
        self,
        *,
        industry: str,
        title: str,
        filename: str,
        content_type: str,
        byte_size: int,
        content_hash: str,
        collection: str,
        storage_key: str,
        storage_backend: str,
        created_by_user_id: uuid.UUID | None,
        visibility: str = KnowledgeVisibility.INDUSTRY_WIDE.value,
        region_zones: list[str] | None = None,
        replaces_document_id: uuid.UUID | None = None,
        version: int = 1,
        suggested_questions: list[str] | None = None,
        entities: list[str] | None = None,
        grant_all_users: bool = True,
        document_id: uuid.UUID | None = None,
    ) -> KnowledgeDocument:
        doc = KnowledgeDocument(
            id=document_id or uuid.uuid4(),
            industry=industry,
            title=title,
            filename=filename,
            content_type=content_type,
            byte_size=byte_size,
            content_hash=content_hash,
            collection=collection,
            version=version,
            replaces_document_id=replaces_document_id,
            status=KnowledgeDocumentStatus.PENDING.value,
            visibility=visibility,
            region_zones=region_zones,
            is_active=False,
            storage_key=storage_key,
            storage_backend=storage_backend,
            created_by_user_id=created_by_user_id,
            suggested_questions=suggested_questions,
            entities=entities,
        )
        self._session.add(doc)
        await self._session.flush()
        if grant_all_users and visibility == KnowledgeVisibility.INDUSTRY_WIDE.value:
            self._session.add(
                KnowledgeDocumentAcl(
                    document_id=doc.id,
                    principal_type=KnowledgeAclPrincipal.ALL_USERS.value,
                    principal_id=None,
                    can_read=True,
                )
            )
            await self._session.flush()
        return doc

    async def transition_status(
        self,
        document_id: uuid.UUID,
        status: KnowledgeDocumentStatus | str,
        *,
        message: str | None = None,
    ) -> KnowledgeDocument | None:
        doc = await self.get(document_id)
        if doc is None:
            return None
        if doc.status in {
            KnowledgeDocumentStatus.DELETED.value,
            KnowledgeDocumentStatus.SUPERSEDED.value,
        }:
            return doc
        doc.status = status.value if isinstance(status, KnowledgeDocumentStatus) else status
        doc.status_message = message
        doc.updated_at = datetime.now(UTC)
        await self._session.flush()
        return doc

    async def set_indexed(
        self,
        document_id: uuid.UUID,
        *,
        chunk_count: int,
        qdrant_collection: str,
        qdrant_point_count: int,
        embedding_provider: str,
        embedding_model_id: str,
        embedding_dimension: int,
    ) -> KnowledgeDocument | None:
        doc = await self.get(document_id)
        if doc is None:
            return None
        if doc.status in {
            KnowledgeDocumentStatus.DELETED.value,
            KnowledgeDocumentStatus.SUPERSEDED.value,
        }:
            return doc
        doc.status = KnowledgeDocumentStatus.INDEXED.value
        doc.status_message = None
        doc.chunk_count = chunk_count
        doc.qdrant_collection = qdrant_collection
        doc.qdrant_point_count = qdrant_point_count
        doc.embedding_provider = embedding_provider
        doc.embedding_model_id = embedding_model_id
        doc.embedding_dimension = embedding_dimension
        doc.indexed_at = datetime.now(UTC)
        doc.is_active = True
        doc.updated_at = datetime.now(UTC)
        await self._session.flush()
        return doc

    async def supersede_atomically(
        self, *, old_id: uuid.UUID, new_id: uuid.UUID
    ) -> tuple[KnowledgeDocument | None, KnowledgeDocument | None]:
        """Activate ``new_id`` and mark ``old_id`` SUPERSEDED in one flush."""
        old = await self.get(old_id)
        new = await self.get(new_id)
        if old is None or new is None:
            return old, new
        if new.status != KnowledgeDocumentStatus.INDEXED.value:
            raise ValueError("Replacement must be INDEXED before superseding the old version.")
        if old.status == KnowledgeDocumentStatus.DELETED.value:
            return old, new
        old.status = KnowledgeDocumentStatus.SUPERSEDED.value
        old.is_active = False
        old.superseded_by_id = new.id
        old.updated_at = datetime.now(UTC)
        new.is_active = True
        new.updated_at = datetime.now(UTC)
        await self._session.flush()
        return old, new

    async def soft_delete(self, document_id: uuid.UUID) -> KnowledgeDocument | None:
        doc = await self.get(document_id)
        if doc is None:
            return None
        doc.status = KnowledgeDocumentStatus.DELETED.value
        doc.is_active = False
        doc.deleted_at = datetime.now(UTC)
        doc.updated_at = datetime.now(UTC)
        await self._session.flush()
        return doc

    async def replace_chunks(
        self,
        document_id: uuid.UUID,
        chunks: Sequence[dict[str, Any]],
    ) -> list[KnowledgeDocumentChunk]:
        await self._session.execute(
            delete(KnowledgeDocumentChunk).where(
                KnowledgeDocumentChunk.document_id == document_id
            )
        )
        rows: list[KnowledgeDocumentChunk] = []
        for chunk in chunks:
            row = KnowledgeDocumentChunk(
                id=str(chunk["id"]),
                document_id=document_id,
                ordinal=int(chunk["ordinal"]),
                locator=str(chunk["locator"]),
                text_preview=str(chunk["text_preview"]),
                text_content=str(chunk["text_content"]),
                embedding_model_id=chunk.get("embedding_model_id"),
                qdrant_point_id=chunk.get("qdrant_point_id"),
            )
            self._session.add(row)
            rows.append(row)
        await self._session.flush()
        return rows

    async def get_chunks(self, document_id: uuid.UUID) -> list[KnowledgeDocumentChunk]:
        stmt = (
            select(KnowledgeDocumentChunk)
            .where(KnowledgeDocumentChunk.document_id == document_id)
            .order_by(KnowledgeDocumentChunk.ordinal.asc())
        )
        return list((await self._session.execute(stmt)).scalars())

    async def set_acl(
        self,
        document_id: uuid.UUID,
        rules: Sequence[tuple[str, str | None, bool]],
    ) -> None:
        await self._session.execute(
            delete(KnowledgeDocumentAcl).where(KnowledgeDocumentAcl.document_id == document_id)
        )
        for principal_type, principal_id, can_read in rules:
            self._session.add(
                KnowledgeDocumentAcl(
                    document_id=document_id,
                    principal_type=principal_type,
                    principal_id=principal_id,
                    can_read=can_read,
                )
            )
        await self._session.flush()

    async def enqueue_job(
        self,
        *,
        document_id: uuid.UUID,
        job_type: KnowledgeJobType | str,
        idempotency_key: str,
        payload: dict[str, Any] | None = None,
        max_attempts: int = 5,
    ) -> KnowledgeIngestJob:
        existing = (
            await self._session.execute(
                select(KnowledgeIngestJob).where(
                    KnowledgeIngestJob.idempotency_key == idempotency_key
                )
            )
        ).scalar_one_or_none()
        if existing is not None:
            return existing
        job = KnowledgeIngestJob(
            document_id=document_id,
            job_type=job_type.value if isinstance(job_type, KnowledgeJobType) else job_type,
            status=KnowledgeJobStatus.QUEUED.value,
            idempotency_key=idempotency_key,
            max_attempts=max_attempts,
            next_attempt_at=datetime.now(UTC),
            payload=payload or {},
        )
        self._session.add(job)
        await self._session.flush()
        return job

    async def get_job(self, job_id: uuid.UUID) -> KnowledgeIngestJob | None:
        return await self._session.get(KnowledgeIngestJob, job_id)

    async def recover_expired_leases(self) -> int:
        now = datetime.now(UTC)
        stmt = select(KnowledgeIngestJob).where(
            KnowledgeIngestJob.status == KnowledgeJobStatus.RUNNING.value,
            KnowledgeIngestJob.lease_expires_at.is_not(None),
            KnowledgeIngestJob.lease_expires_at < now,
        )
        jobs = list((await self._session.execute(stmt)).scalars())
        for job in jobs:
            job.status = KnowledgeJobStatus.QUEUED.value
            job.locked_by = None
            job.locked_at = None
            job.lease_expires_at = None
            job.next_attempt_at = now
            job.error_message = "Lease expired; requeued."
            job.updated_at = now
        await self._session.flush()
        return len(jobs)

    async def claim_next_job(
        self,
        *,
        worker_id: str,
        lease_seconds: int,
    ) -> KnowledgeIngestJob | None:
        await self.recover_expired_leases()
        now = datetime.now(UTC)
        dialect = self._session.bind.dialect.name if self._session.bind is not None else "sqlite"
        base: Select[tuple[KnowledgeIngestJob]] = (
            select(KnowledgeIngestJob)
            .where(
                or_(
                    KnowledgeIngestJob.status == KnowledgeJobStatus.QUEUED.value,
                    and_(
                        KnowledgeIngestJob.status == KnowledgeJobStatus.FAILED.value,
                        KnowledgeIngestJob.next_attempt_at.is_not(None),
                        KnowledgeIngestJob.next_attempt_at <= now,
                        KnowledgeIngestJob.attempt_count < KnowledgeIngestJob.max_attempts,
                    ),
                ),
                or_(
                    KnowledgeIngestJob.next_attempt_at.is_(None),
                    KnowledgeIngestJob.next_attempt_at <= now,
                ),
            )
            .order_by(KnowledgeIngestJob.created_at.asc())
            .limit(1)
        )
        if dialect == "postgresql":
            base = base.with_for_update(skip_locked=True)
        job = (await self._session.execute(base)).scalar_one_or_none()
        if job is None:
            return None
        job.status = KnowledgeJobStatus.RUNNING.value
        job.locked_by = worker_id
        job.locked_at = now
        job.lease_expires_at = now + timedelta(seconds=lease_seconds)
        job.attempt_count += 1
        job.updated_at = now
        await self._session.flush()
        return job

    async def renew_lease(self, job_id: uuid.UUID, *, lease_seconds: int) -> None:
        job = await self.get_job(job_id)
        if job is None or job.status != KnowledgeJobStatus.RUNNING.value:
            return
        now = datetime.now(UTC)
        job.lease_expires_at = now + timedelta(seconds=lease_seconds)
        job.updated_at = now
        await self._session.flush()

    async def mark_job_done(self, job_id: uuid.UUID) -> None:
        job = await self.get_job(job_id)
        if job is None:
            return
        now = datetime.now(UTC)
        job.status = KnowledgeJobStatus.DONE.value
        job.completed_at = now
        job.locked_by = None
        job.lease_expires_at = None
        job.error_message = None
        job.updated_at = now
        await self._session.flush()

    async def mark_job_failed(
        self,
        job_id: uuid.UUID,
        *,
        error: str,
        backoff_seconds: int,
        cancel: bool = False,
    ) -> None:
        job = await self.get_job(job_id)
        if job is None:
            return
        now = datetime.now(UTC)
        job.error_message = error[:4000]
        job.locked_by = None
        job.lease_expires_at = None
        job.updated_at = now
        if cancel or job.attempt_count >= job.max_attempts:
            job.status = KnowledgeJobStatus.FAILED.value
            job.next_attempt_at = None
            job.completed_at = now
        else:
            job.status = KnowledgeJobStatus.FAILED.value
            delay = backoff_seconds * max(1, job.attempt_count)
            job.next_attempt_at = now + timedelta(seconds=delay)
        await self._session.flush()

    async def cancel_jobs_for_document(
        self, document_id: uuid.UUID, *, except_types: set[str] | None = None
    ) -> int:
        except_types = except_types or set()
        stmt = select(KnowledgeIngestJob).where(
            KnowledgeIngestJob.document_id == document_id,
            KnowledgeIngestJob.status.in_(
                [
                    KnowledgeJobStatus.QUEUED.value,
                    KnowledgeJobStatus.RUNNING.value,
                    KnowledgeJobStatus.FAILED.value,
                ]
            ),
        )
        jobs = list((await self._session.execute(stmt)).scalars())
        count = 0
        now = datetime.now(UTC)
        for job in jobs:
            if job.job_type in except_types:
                continue
            if job.next_attempt_at is None and job.status == KnowledgeJobStatus.FAILED.value:
                continue
            job.status = KnowledgeJobStatus.CANCELLED.value
            job.completed_at = now
            job.locked_by = None
            job.lease_expires_at = None
            job.next_attempt_at = None
            job.updated_at = now
            count += 1
        await self._session.flush()
        return count

    def _base_list_filters(self, industry: str) -> list[Any]:
        return [KnowledgeDocument.industry == industry]

    async def list_for_admin(self, industry: str) -> list[KnowledgeDocument]:
        stmt = (
            select(KnowledgeDocument)
            .where(
                *self._base_list_filters(industry),
                KnowledgeDocument.status != KnowledgeDocumentStatus.DELETED.value,
            )
            .order_by(KnowledgeDocument.created_at.desc())
        )
        return list((await self._session.execute(stmt)).scalars())

    async def list_visible_for_user(
        self,
        *,
        industry: str,
        user: User,
        allowed_ids: set[uuid.UUID],
        include_superseded: bool = False,
    ) -> list[KnowledgeDocument]:
        statuses = [
            KnowledgeDocumentStatus.INDEXED.value,
            KnowledgeDocumentStatus.PENDING.value,
            KnowledgeDocumentStatus.EXTRACTING.value,
            KnowledgeDocumentStatus.CHUNKING.value,
            KnowledgeDocumentStatus.EMBEDDING.value,
            KnowledgeDocumentStatus.INDEXING.value,
            KnowledgeDocumentStatus.FAILED.value,
        ]
        if include_superseded:
            statuses.append(KnowledgeDocumentStatus.SUPERSEDED.value)
        if not allowed_ids and user.role is not Role.ADMIN:
            return []
        conditions = [
            *self._base_list_filters(industry),
            KnowledgeDocument.status.in_(statuses),
            KnowledgeDocument.status != KnowledgeDocumentStatus.DELETED.value,
        ]
        if allowed_ids:
            conditions.append(KnowledgeDocument.id.in_(allowed_ids))
        stmt = (
            select(KnowledgeDocument)
            .where(*conditions)
            .order_by(KnowledgeDocument.created_at.desc())
        )
        docs = list((await self._session.execute(stmt)).scalars())
        if not include_superseded:
            docs = [d for d in docs if d.status != KnowledgeDocumentStatus.SUPERSEDED.value]
        return docs

    async def allowed_document_ids(
        self,
        *,
        industry: str,
        user: User,
        user_zones: set[str] | None,
        region_resolved: bool,
        for_chat: bool = True,
    ) -> set[uuid.UUID]:
        """Return document IDs the user may retrieve.

        Chat/retrieval always enforces ACL (admin included). Management listing may
        call list_for_admin separately.
        """
        stmt = (
            select(KnowledgeDocument)
            .where(
                KnowledgeDocument.industry == industry,
                KnowledgeDocument.status == KnowledgeDocumentStatus.INDEXED.value,
                KnowledgeDocument.is_active.is_(True),
            )
            .options(selectinload(KnowledgeDocument.acl_rules))
        )
        docs = list((await self._session.execute(stmt)).scalars())
        allowed: set[uuid.UUID] = set()
        for doc in docs:
            if not self._document_readable(
                doc,
                user=user,
                user_zones=user_zones,
                region_resolved=region_resolved,
                for_chat=for_chat,
            ):
                continue
            allowed.add(doc.id)
        return allowed

    def _document_readable(
        self,
        doc: KnowledgeDocument,
        *,
        user: User,
        user_zones: set[str] | None,
        region_resolved: bool,
        for_chat: bool,
    ) -> bool:
        if doc.status != KnowledgeDocumentStatus.INDEXED.value or not doc.is_active:
            return False
        if doc.region_zones:
            if not region_resolved:
                return False
            zones = {str(z) for z in doc.region_zones}
            if not user_zones or zones.isdisjoint(user_zones):
                return False
        if doc.visibility == KnowledgeVisibility.INDUSTRY_WIDE.value:
            rules = list(doc.acl_rules or [])
            if not rules:
                return True
            return self._acl_grants(rules, user)
        return self._acl_grants(list(doc.acl_rules or []), user)

    def _acl_grants(self, rules: list[KnowledgeDocumentAcl], user: User) -> bool:
        if not rules:
            return False
        for rule in rules:
            if not rule.can_read:
                continue
            if rule.principal_type == KnowledgeAclPrincipal.ALL_USERS.value:
                return True
            if (
                rule.principal_type == KnowledgeAclPrincipal.ROLE.value
                and rule.principal_id
                and rule.principal_id == user.role.value
            ):
                return True
            if (
                rule.principal_type == KnowledgeAclPrincipal.USER.value
                and rule.principal_id
                and rule.principal_id == str(user.id)
            ):
                return True
        return False

    async def count_by_status(self, industry: str | None = None) -> dict[str, int]:
        stmt = select(KnowledgeDocument.status, func.count()).group_by(KnowledgeDocument.status)
        if industry:
            stmt = stmt.where(KnowledgeDocument.industry == industry)
        rows = (await self._session.execute(stmt)).all()
        return {str(status): int(count) for status, count in rows}
