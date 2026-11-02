"""Qdrant upsert, query, delete and collection compatibility checks."""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from typing import Any

from app.core.config import Settings
from app.core.exceptions import DependencyUnavailableError, ValidationError
from app.rag.embeddings import EmbeddingIdentity

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class RetrievedPoint:
    document_id: str
    chunk_id: str
    title: str
    text: str
    locator: str
    collection: str
    score: float
    version: int | None = None


class QdrantIndex:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._client: Any | None = None
        self._models: Any | None = None

    def connect(self) -> None:
        try:
            from qdrant_client import QdrantClient, models
        except ImportError as exc:
            raise DependencyUnavailableError(
                "qdrant-client is required when ASK_ME_RAG_ENABLED=true."
            ) from exc
        mode = (self.settings.rag_qdrant_mode or "server").strip().lower()
        if mode == "memory":
            # No Docker / no server — ephemeral embedded Qdrant (dev only).
            client = QdrantClient(":memory:", force_disable_check_same_thread=True)
        elif mode == "local":
            # No Docker / no server — persistent embedded Qdrant on disk.
            from pathlib import Path

            from app.core.config import APP_ROOT

            raw = (self.settings.rag_qdrant_path or "").strip()
            path = Path(raw) if raw else (APP_ROOT / "data" / "qdrant_local")
            path.mkdir(parents=True, exist_ok=True)
            client = QdrantClient(
                path=str(path),
                force_disable_check_same_thread=True,
            )
        else:
            client = QdrantClient(
                url=self.settings.qdrant_url,
                api_key=self.settings.qdrant_api_key.get_secret_value() or None,
                timeout=5.0,
            )
        client.get_collections()
        self._client = client
        self._models = models

    @property
    def client(self) -> Any:
        if self._client is None:
            self.connect()
        assert self._client is not None
        return self._client

    @property
    def models(self) -> Any:
        if self._models is None:
            self.connect()
        assert self._models is not None
        return self._models

    def ensure_collection(self, name: str, identity: EmbeddingIdentity) -> None:
        collections = {item.name for item in self.client.get_collections().collections}
        if name in collections:
            info = self.client.get_collection(name)
            vectors = info.config.params.vectors
            size = getattr(vectors, "size", None)
            if size is None and isinstance(vectors, dict):
                # Named vectors unsupported in MVP.
                raise ValidationError(
                    f"Qdrant collection '{name}' uses named vectors; Ask Me expects a single vector."
                )
            if int(size) != identity.dimension:
                raise ValidationError(
                    f"Qdrant collection '{name}' has dimension {size}, "
                    f"but embedding model '{identity.model_id}' produces {identity.dimension}. "
                    "Use a separate compatible collection; never force incompatible vectors."
                )
            return
        self.client.create_collection(
            collection_name=name,
            vectors_config=self.models.VectorParams(
                size=identity.dimension,
                distance=self.models.Distance.COSINE,
            ),
        )
        # Store collection-level identity in metadata payload schema via first upsert only;
        # also create payload indexes for ACL filtering.
        for field in ("documentId", "industry", "collection"):
            try:
                self.client.create_payload_index(
                    collection_name=name,
                    field_name=field,
                    field_schema=self.models.PayloadSchemaType.KEYWORD,
                )
            except Exception:
                logger.debug("payload index create skipped for %s.%s", name, field, exc_info=True)

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
        if len(chunks) != len(vectors):
            raise ValidationError("Chunk/vector count mismatch.")
        self.ensure_collection(collection_name, identity)
        point_ids: list[str] = []
        points = []
        for chunk, vector in zip(chunks, vectors, strict=True):
            if len(vector) != identity.dimension:
                raise ValidationError(
                    f"Vector dimension {len(vector)} incompatible with collection "
                    f"{collection_name} ({identity.dimension})."
                )
            point_id = str(uuid.uuid5(uuid.NAMESPACE_URL, str(chunk["id"])))
            point_ids.append(point_id)
            payload = {
                "documentId": document_id,
                "chunkId": chunk["id"],
                "title": title,
                "text": chunk["text_content"],
                "locator": chunk["locator"],
                "collection": doc_collection,
                "industry": industry,
                "version": version,
                "embeddingProvider": identity.provider,
                "embeddingModelId": identity.model_id,
                "embeddingDimension": identity.dimension,
                "regionZones": region_zones or [],
            }
            points.append(
                self.models.PointStruct(id=point_id, vector=vector, payload=payload)
            )
        self.client.upsert(collection_name=collection_name, points=points, wait=True)
        return point_ids

    def count_points_for_document(self, collection_name: str, document_id: str) -> int:
        result = self.client.count(
            collection_name=collection_name,
            count_filter=self.models.Filter(
                must=[
                    self.models.FieldCondition(
                        key="documentId",
                        match=self.models.MatchValue(value=document_id),
                    )
                ]
            ),
            exact=True,
        )
        return int(result.count)

    def delete_document_points(self, collection_name: str, document_id: str) -> None:
        try:
            self.client.delete(
                collection_name=collection_name,
                points_selector=self.models.FilterSelector(
                    filter=self.models.Filter(
                        must=[
                            self.models.FieldCondition(
                                key="documentId",
                                match=self.models.MatchValue(value=document_id),
                            )
                        ]
                    )
                ),
            )
        except Exception:
            logger.warning(
                "Failed deleting Qdrant points for document %s", document_id, exc_info=True
            )

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
        must = [
            self.models.FieldCondition(
                key="documentId",
                match=self.models.MatchAny(any=allowed_document_ids),
            )
        ]
        if collection_filter:
            must.append(
                self.models.FieldCondition(
                    key="collection",
                    match=self.models.MatchValue(value=collection_filter),
                )
            )
        try:
            response = self.client.query_points(
                collection_name=collection_name,
                query=query_vector,
                query_filter=self.models.Filter(must=must),
                limit=top_k,
                with_payload=True,
            )
            points = getattr(response, "points", response)
        except Exception:
            # Older qdrant-client API fallback.
            points = self.client.search(
                collection_name=collection_name,
                query_vector=query_vector,
                query_filter=self.models.Filter(must=must),
                limit=top_k,
                with_payload=True,
            )
        hits: list[RetrievedPoint] = []
        for point in points:
            payload = point.payload or {}
            hits.append(
                RetrievedPoint(
                    document_id=str(payload.get("documentId") or ""),
                    chunk_id=str(payload.get("chunkId") or ""),
                    title=str(payload.get("title") or "Document"),
                    text=str(payload.get("text") or ""),
                    locator=str(payload.get("locator") or ""),
                    collection=str(payload.get("collection") or "general"),
                    score=float(getattr(point, "score", 0.0) or 0.0),
                    version=payload.get("version"),
                )
            )
        return hits

    def ping(self) -> tuple[bool, str]:
        try:
            self.connect()
            names = [item.name for item in self.client.get_collections().collections]
            mode = (self.settings.rag_qdrant_mode or "server").strip().lower()
            return True, f"ok; mode={mode}; collections={len(names)}"
        except Exception as exc:
            return False, str(exc)[:200]
