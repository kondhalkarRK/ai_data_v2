"""Knowledge ingestion, chunking, retrieval, and citations."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.core.config import Industry, Settings
from app.core.exceptions import ValidationError
from app.rag.parsers import extract_text
from app.rag.store import KnowledgeStore


@dataclass(slots=True)
class Citation:
    document_id: str
    title: str
    chunk_id: str
    snippet: str
    locator: str
    untrusted: bool = False


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


class KnowledgeService:
    def __init__(self, settings: Settings, industry: Industry) -> None:
        self._settings = settings
        self._store = KnowledgeStore(settings, industry)

    def list_documents(self) -> list[dict[str, Any]]:
        return self._store.list_documents()

    def ingest_text(self, *, title: str, text: str, filename: str) -> dict[str, Any]:
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
        doc_id = content_hash[:16]
        pieces = chunk_text(
            text,
            max_chars=self._settings.rag_chunk_max_chars,
            min_chars=self._settings.rag_chunk_min_chars,
            overlap=self._settings.rag_chunk_overlap_chars,
        )
        chunks = [
            {
                "id": f"{doc_id}:{index}",
                "text": piece,
                "embedding": _hash_embed(piece, self._settings.qdrant_vector_size),
                "locator": f"chunk-{index + 1}",
            }
            for index, piece in enumerate(pieces)
        ]
        return self._store.save_document(
            title=title or filename,
            filename=filename,
            content_hash=content_hash,
            raw_text=text,
            chunks=chunks,
        )

    def ingest_bytes(self, *, title: str, raw: bytes, filename: str) -> dict[str, Any]:
        if len(raw) > self._settings.upload_max_bytes:
            raise ValidationError("Upload exceeds the configured size limit.")
        suffix = Path(filename).suffix.lower()
        if suffix not in {ext.lower() for ext in self._settings.upload_allowed_extensions}:
            raise ValidationError(f"Unsupported upload type '{suffix or '(none)'}'.")
        return self.ingest_text(
            title=title, text=extract_text(filename, raw), filename=filename
        )

    def delete_document(self, document_id: str) -> None:
        self._store.delete_document(document_id)

    def search(
        self, query: str, *, top_k: int | None = None, user_id: str | None = None
    ) -> list[Citation]:
        query = query.strip()
        if not query:
            raise ValidationError("Query is required.")
        query_vector = _hash_embed(query, self._settings.qdrant_vector_size)
        scored: list[tuple[float, Citation]] = []
        for meta, chunk in self._store.iter_chunks():
            scored.append(
                (
                    _cosine(query_vector, chunk["embedding"]),
                    Citation(
                        document_id=meta["id"],
                        title=meta["title"],
                        chunk_id=chunk["id"],
                        snippet=chunk["text"][:280],
                        locator=chunk["locator"],
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
                }
                for hit in hits
            ],
            user_id,
        )
        return hits

    def reindex(self) -> dict[str, int]:
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
                    }
                    for index, piece in enumerate(pieces)
                ],
            )
            count += 1
        return {"documents": count}

    def reindex_all(self) -> dict[str, int]:
        return self.reindex()
