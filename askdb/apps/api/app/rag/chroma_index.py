"""Embedded Chroma adapter. Embeddings are always supplied by Soci."""

from __future__ import annotations

import math
import threading
from pathlib import Path
from typing import Any

from app.core.config import APP_ROOT, Settings
from app.core.exceptions import DependencyUnavailableError, ValidationError
from app.rag.embeddings import EmbeddingIdentity
from app.rag.qdrant_index import RetrievedPoint


class ChromaIndex:
    def __init__(self, settings: Settings | str) -> None:
        raw_path = settings if isinstance(settings, str) else settings.rag_chroma_path
        self.path = str(Path(raw_path or APP_ROOT / "data" / "chroma_local").resolve())
        self._client: Any = None
        self._lock = threading.RLock()

    @property
    def client(self) -> Any:
        with self._lock:
            if self._client is None:
                try:
                    import chromadb
                    from chromadb.config import Settings as ChromaSettings
                except ImportError as exc:
                    raise DependencyUnavailableError(
                        "Install the rag-chroma extra to enable Chroma."
                    ) from exc
                self._client = chromadb.PersistentClient(
                    path=self.path, settings=ChromaSettings(anonymized_telemetry=False)
                )
            return self._client

    def ensure_collection(self, name: str, identity: EmbeddingIdentity) -> None:
        with self._lock:
            collection = self.client.get_or_create_collection(
                name=name,
                embedding_function=None,
                metadata={
                    "provider": identity.provider,
                    "model": identity.model_id,
                    "dimension": identity.dimension,
                },
                configuration={"hnsw": {"space": "cosine"}},
            )
            expected = {
                "provider": identity.provider,
                "model": identity.model_id,
                "dimension": identity.dimension,
            }
            if collection.metadata != expected:
                raise ValidationError("Embedding identity mismatch; reindex into a new namespace.")

    def _collection(self, name: str) -> Any:
        return self.client.get_collection(name, embedding_function=None)

    def upsert_chunks(
        self,
        *,
        collection_name: str,
        identity: EmbeddingIdentity,
        document_id: str,
        industry: str,
        title: str,
        doc_collection: str,
        version: int,
        region_zones: list[str] | None,
        chunks: list[dict[str, Any]],
        vectors: list[list[float]],
    ) -> list[str]:
        if len(chunks) != len(vectors) or not chunks:
            raise ValidationError("Chunk/vector count mismatch or empty batch.")
        for vector in vectors:
            if len(vector) != identity.dimension or not all(math.isfinite(v) for v in vector):
                raise ValidationError("Invalid vector dimension or nonfinite value.")
        self.ensure_collection(collection_name, identity)
        ids = [str(c["id"]) for c in chunks]
        collection = self._collection(collection_name)
        for start in range(0, len(ids), 64):
            part = chunks[start : start + 64]
            collection.upsert(
                ids=ids[start : start + 64],
                embeddings=vectors[start : start + 64],
                documents=[str(c["text_content"]) for c in part],
                metadatas=[
                    {
                        "documentId": document_id,
                        "chunkId": str(c["id"]),
                        "industry": industry,
                        "title": title,
                        "locator": str(c["locator"]),
                        "collection": doc_collection,
                        "version": version,
                    }
                    for c in part
                ],
            )
        return ids

    def count_points_for_document(self, collection_name: str, document_id: str) -> int:
        return len(
            self._collection(collection_name).get(where={"documentId": document_id}, include=[])[
                "ids"
            ]
        )

    def delete_document_points(self, collection_name: str, document_id: str) -> None:
        # Missing namespace during first ingestion is harmless; other failures propagate.
        if collection_name not in {c.name for c in self.client.list_collections()}:
            return
        self._collection(collection_name).delete(where={"documentId": document_id})

    def query(
        self,
        *,
        collection_name: str,
        query_vector: list[float],
        allowed_document_ids: list[str],
        top_k: int,
        collection_filter: str | None = None,
    ) -> list[RetrievedPoint]:
        if not allowed_document_ids:
            return []
        if collection_name not in {c.name for c in self.client.list_collections()}:
            return []
        if not query_vector or not all(math.isfinite(v) for v in query_vector):
            raise ValidationError("Invalid query embedding.")
        filters: list[dict[str, Any]] = [{"documentId": {"$in": allowed_document_ids}}]
        if collection_filter:
            filters.append({"collection": collection_filter})
        result = self._collection(collection_name).query(
            query_embeddings=[query_vector],
            n_results=top_k,
            where=filters[0] if len(filters) == 1 else {"$and": filters},
            include=["metadatas", "documents", "distances"],
        )
        hits = []
        for meta, text, distance in zip(
            result["metadatas"][0], result["documents"][0], result["distances"][0], strict=True
        ):
            if meta["documentId"] not in allowed_document_ids:
                continue
            hits.append(
                RetrievedPoint(
                    document_id=meta["documentId"],
                    chunk_id=meta["chunkId"],
                    title=meta["title"],
                    text=text,
                    locator=meta["locator"],
                    collection=meta["collection"],
                    score=1.0 - float(distance),
                    version=meta["version"],
                )
            )
        return hits

    def ping(self) -> tuple[bool, str]:
        try:
            self.client.heartbeat()
            return True, "Embedded Chroma available"
        except Exception:
            return False, "Chroma unavailable; consult restricted server diagnostics."
