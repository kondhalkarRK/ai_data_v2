"""Optional legacy filesystem → Traditional RAG backfill utility.

Safe to re-run: skips duplicates by content hash. Does not run when RAG is disabled
unless ``--force`` is passed (still requires ASK_ME_RAG_ENABLED for enqueue).

Usage::

    python -m app.rag.backfill --industry insurance
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import logging
import uuid
from pathlib import Path

from app.core.config import Industry, Settings, get_settings
from app.db.session import DatabaseRegistry
from app.models.enums import Role
from app.models.knowledge import KnowledgeJobType
from app.models.user import User
from app.rag.feature import rag_enabled
from app.rag.storage import DocumentBlobStore
from app.rag.store import KnowledgeStore
from app.repositories.knowledge_documents import KnowledgeDocumentRepository
from app.services.knowledge import infer_collection, suggested_questions_for
from sqlalchemy import select

logger = logging.getLogger(__name__)


async def backfill_industry(
    settings: Settings,
    industry: Industry,
    *,
    dry_run: bool = False,
) -> dict[str, int]:
    if not rag_enabled(settings):
        raise RuntimeError("ASK_ME_RAG_ENABLED must be true to backfill into Traditional RAG.")

    store = KnowledgeStore(settings, industry)
    legacy_docs = store.list_documents()
    stats = {"success": 0, "skipped": 0, "failed": 0}

    registry = DatabaseRegistry(settings)
    await registry.start()
    try:
        async with registry.app_session() as session:
            repo = KnowledgeDocumentRepository(session)
            admin = (
                await session.execute(select(User).where(User.role == Role.ADMIN).limit(1))
            ).scalar_one_or_none()
            blobs = DocumentBlobStore(settings, industry)
            for meta in legacy_docs:
                try:
                    content_hash = str(meta.get("contentHash") or "")
                    if not content_hash:
                        text = store.read_text(str(meta["id"]))
                        content_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()
                    existing = await repo.find_active_by_hash(
                        industry=industry.value, content_hash=content_hash
                    )
                    if existing is not None:
                        stats["skipped"] += 1
                        continue
                    text = store.read_text(str(meta["id"]))
                    raw = text.encode("utf-8")
                    document_id = uuid.uuid4()
                    if dry_run:
                        stats["success"] += 1
                        continue
                    filename = str(meta.get("filename") or f"{meta.get('title', 'legacy')}.txt")
                    stored = blobs.write_original(
                        document_id=document_id,
                        filename=filename if Path(filename).suffix else f"{filename}.txt",
                        raw=raw,
                        declared_content_type="text/plain",
                    )
                    collection = infer_collection(
                        str(meta.get("title") or filename),
                        stored.safe_filename,
                        str(meta.get("collection") or "general"),
                    )
                    doc = await repo.create_pending(
                        industry=industry.value,
                        title=str(meta.get("title") or stored.safe_filename),
                        filename=stored.safe_filename,
                        content_type=stored.content_type,
                        byte_size=stored.byte_size,
                        content_hash=content_hash,
                        collection=collection,
                        storage_key=stored.storage_key,
                        storage_backend=settings.rag_storage_backend,
                        created_by_user_id=admin.id if admin else None,
                        version=int(meta.get("version") or 1),
                        suggested_questions=list(meta.get("suggestedQuestions") or [])
                        or suggested_questions_for(collection),
                        document_id=document_id,
                    )
                    await repo.enqueue_job(
                        document_id=doc.id,
                        job_type=KnowledgeJobType.INGEST,
                        idempotency_key=f"backfill:{doc.id}",
                        max_attempts=settings.rag_job_max_attempts,
                    )
                    stats["success"] += 1
                except Exception:
                    logger.exception("Backfill failed for %s", meta.get("id"))
                    stats["failed"] += 1
            await session.commit()
    finally:
        await registry.stop()
    return stats


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    parser = argparse.ArgumentParser(description="Backfill legacy Knowledge Hub docs into RAG")
    parser.add_argument("--industry", choices=[i.value for i in Industry], required=True)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    settings = get_settings()
    stats = asyncio.run(
        backfill_industry(settings, Industry(args.industry), dry_run=args.dry_run)
    )
    print(stats)


if __name__ == "__main__":
    main()
