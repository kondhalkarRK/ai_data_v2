"""Knowledge persistence with a durable filesystem baseline and optional mirrors."""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from typing import Any

from app.core.config import APP_ROOT, Industry, Settings
from app.core.exceptions import NotFoundError


class KnowledgeStore:
    """Filesystem store that optionally mirrors metadata to MongoDB.

    The filesystem remains authoritative so missing optional packages or unavailable
    services never disable local RAG.
    """

    def __init__(self, settings: Settings, industry: Industry) -> None:
        self.settings = settings
        self.industry = industry
        self.root = APP_ROOT / "data" / "knowledge" / industry.value
        self.root.mkdir(parents=True, exist_ok=True)
        self.audit_root = APP_ROOT / "data" / "knowledge" / "_audit"
        self._mongo: Any | None = None
        self._qdrant: Any | None = None
        self._qdrant_models: Any | None = None
        try:
            from pymongo import MongoClient  # type: ignore[import-not-found]

            client = MongoClient(
                settings.mongodb_uri,
                serverSelectionTimeoutMS=250,
                connectTimeoutMS=250,
            )
            client.admin.command("ping")
            self._mongo = client[settings.mongodb_database]
        except Exception:
            self._mongo = None
        try:
            from qdrant_client import QdrantClient, models

            client = QdrantClient(
                url=settings.qdrant_url,
                api_key=settings.qdrant_api_key.get_secret_value() or None,
                timeout=0.25,
            )
            client.get_collections()
            self._qdrant = client
            self._qdrant_models = models
        except Exception:
            self._qdrant = None
            self._qdrant_models = None

    def list_documents(self) -> list[dict[str, Any]]:
        return [
            json.loads(path.read_text(encoding="utf-8"))
            for path in sorted(self.root.glob("*.meta.json"))
        ]

    def find_by_hash(self, content_hash: str) -> dict[str, Any] | None:
        return next(
            (doc for doc in self.list_documents() if doc.get("contentHash") == content_hash),
            None,
        )

    def save_document(
        self,
        *,
        title: str,
        filename: str,
        content_hash: str,
        raw_text: str,
        chunks: list[dict[str, Any]],
        collection: str = "general",
        suggested_questions: list[str] | None = None,
        entities: list[str] | None = None,
    ) -> dict[str, Any]:
        existing = self.find_by_hash(content_hash)
        if existing is not None:
            return {**existing, "deduped": True}
        versions = [
            int(doc.get("version", 1))
            for doc in self.list_documents()
            if str(doc.get("title", "")).casefold() == title.casefold()
        ]
        doc_id = str(uuid.uuid4())
        meta: dict[str, Any] = {
            "id": doc_id,
            "title": title,
            "filename": filename,
            "industry": self.industry.value,
            "collection": collection,
            "chunkCount": len(chunks),
            "createdAt": datetime.now(UTC).isoformat(),
            "bytes": len(raw_text.encode("utf-8")),
            "contentHash": content_hash,
            "version": max(versions, default=0) + 1,
            "deduped": False,
            "suggestedQuestions": suggested_questions or [],
            "entities": entities or [],
        }
        (self.root / f"{doc_id}.meta.json").write_text(
            json.dumps(meta, indent=2), encoding="utf-8"
        )
        (self.root / f"{doc_id}.text").write_text(raw_text, encoding="utf-8")
        (self.root / f"{doc_id}.chunks.json").write_text(
            json.dumps(chunks), encoding="utf-8"
        )
        self._mongo_write(meta, chunks)
        self._qdrant_write(meta, chunks)
        return meta

    def iter_chunks(
        self, *, collection: str | None = None
    ) -> list[tuple[dict[str, Any], dict[str, Any]]]:
        rows: list[tuple[dict[str, Any], dict[str, Any]]] = []
        for meta in self.list_documents():
            if collection and str(meta.get("collection") or "general") != collection:
                continue
            path = self.root / f"{meta['id']}.chunks.json"
            if path.exists():
                rows.extend(
                    (meta, chunk)
                    for chunk in json.loads(path.read_text(encoding="utf-8"))
                )
        return rows

    def replace_chunks(self, document_id: str, chunks: list[dict[str, Any]]) -> None:
        (self.root / f"{document_id}.chunks.json").write_text(
            json.dumps(chunks), encoding="utf-8"
        )
        meta_path = self.root / f"{document_id}.meta.json"
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        meta["chunkCount"] = len(chunks)
        meta["reindexedAt"] = datetime.now(UTC).isoformat()
        meta_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")
        self._mongo_write(meta, chunks)
        self._qdrant_write(meta, chunks)

    def read_text(self, document_id: str) -> str:
        path = self.root / f"{document_id}.text"
        return path.read_text(encoding="utf-8") if path.exists() else ""

    def delete_document(self, document_id: str) -> None:
        meta = self.root / f"{document_id}.meta.json"
        if not meta.exists():
            raise NotFoundError("Document not found.")
        for suffix in (".meta.json", ".chunks.json", ".text"):
            (self.root / f"{document_id}{suffix}").unlink(missing_ok=True)
        if self._mongo is not None:
            try:
                self._mongo.documents.delete_one({"id": document_id})
                self._mongo.chunks.delete_many({"documentId": document_id})
            except Exception:
                self._mongo = None
        if self._qdrant is not None and self._qdrant_models is not None:
            try:
                self._qdrant.delete(
                    collection_name=self._collection_name,
                    points_selector=self._qdrant_models.FilterSelector(
                        filter=self._qdrant_models.Filter(
                            must=[
                                self._qdrant_models.FieldCondition(
                                    key="documentId",
                                    match=self._qdrant_models.MatchValue(value=document_id),
                                )
                            ]
                        )
                    ),
                )
            except Exception:
                self._qdrant = None

    def append_retrieval_audit(
        self, query: str, hits: list[dict[str, Any]], user_id: str | None = None
    ) -> None:
        record = {
            "timestamp": datetime.now(UTC).isoformat(),
            "industry": self.industry.value,
            "query": query,
            "hits": hits,
            "userId": user_id,
        }
        if self._mongo is not None:
            try:
                self._mongo.retrieval_audit.insert_one(record)
                return
            except Exception:
                self._mongo = None
        self.audit_root.mkdir(parents=True, exist_ok=True)
        with (self.audit_root / "retrieval.jsonl").open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record) + "\n")

    def _mongo_write(self, meta: dict[str, Any], chunks: list[dict[str, Any]]) -> None:
        if self._mongo is None:
            return
        try:
            self._mongo.documents.replace_one({"id": meta["id"]}, meta, upsert=True)
            if chunks:
                self._mongo.chunks.delete_many({"documentId": meta["id"]})
                self._mongo.chunks.insert_many(
                    [{**chunk, "documentId": meta["id"]} for chunk in chunks]
                )
        except Exception:
            self._mongo = None

    @property
    def _collection_name(self) -> str:
        return f"nql_{self.industry.value}_chunks"

    def _qdrant_write(self, meta: dict[str, Any], chunks: list[dict[str, Any]]) -> None:
        if self._qdrant is None or self._qdrant_models is None or not chunks:
            return
        try:
            collections = {
                item.name for item in self._qdrant.get_collections().collections
            }
            if self._collection_name not in collections:
                self._qdrant.create_collection(
                    collection_name=self._collection_name,
                    vectors_config=self._qdrant_models.VectorParams(
                        size=self.settings.qdrant_vector_size,
                        distance=self._qdrant_models.Distance.COSINE,
                    ),
                )
            self._qdrant.upsert(
                collection_name=self._collection_name,
                points=[
                    self._qdrant_models.PointStruct(
                        id=str(uuid.uuid5(uuid.NAMESPACE_URL, chunk["id"])),
                        vector=chunk["embedding"],
                        payload={
                            "documentId": meta["id"],
                            "title": meta["title"],
                            "text": chunk["text"],
                            "locator": chunk["locator"],
                            "collection": meta.get("collection", "general"),
                            "entities": chunk.get("entities") or meta.get("entities") or [],
                        },
                    )
                    for chunk in chunks
                ],
            )
        except Exception:
            self._qdrant = None
