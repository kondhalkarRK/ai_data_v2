"""Knowledge / RAG: parse, chunk, hash-embed, store, retrieve with citations."""

from __future__ import annotations

import hashlib
import json
import re
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.core.config import APP_ROOT, Industry, Settings
from app.core.exceptions import NotFoundError, ValidationError


@dataclass(slots=True)
class Citation:
    document_id: str
    title: str
    chunk_id: str
    snippet: str
    locator: str


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
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


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
        self._industry = industry
        self._root = APP_ROOT / "data" / "knowledge" / industry.value
        self._root.mkdir(parents=True, exist_ok=True)

    def list_documents(self) -> list[dict[str, Any]]:
        docs = []
        for path in sorted(self._root.glob("*.meta.json")):
            docs.append(json.loads(path.read_text(encoding="utf-8")))
        return docs

    def ingest_text(self, *, title: str, text: str, filename: str) -> dict[str, Any]:
        allowed = {ext.lower() for ext in self._settings.upload_allowed_extensions}
        suffix = Path(filename).suffix.lower() or ".txt"
        if suffix not in allowed and suffix not in {".txt", ".md", ".html"}:
            raise ValidationError(f"Unsupported upload type '{suffix}'.")
        if len(text.encode("utf-8")) > self._settings.upload_max_bytes:
            raise ValidationError("Upload exceeds the configured size limit.")

        doc_id = str(uuid.uuid4())
        chunks = chunk_text(
            text,
            max_chars=self._settings.rag_chunk_max_chars,
            min_chars=self._settings.rag_chunk_min_chars,
            overlap=self._settings.rag_chunk_overlap_chars,
        )
        embedded = [
            {
                "id": f"{doc_id}:{index}",
                "text": chunk,
                "embedding": _hash_embed(chunk, self._settings.qdrant_vector_size),
                "locator": f"chunk-{index + 1}",
            }
            for index, chunk in enumerate(chunks)
        ]
        meta = {
            "id": doc_id,
            "title": title or filename,
            "filename": filename,
            "industry": self._industry.value,
            "chunkCount": len(embedded),
            "createdAt": datetime.now(UTC).isoformat(),
            "bytes": len(text.encode("utf-8")),
        }
        (self._root / f"{doc_id}.meta.json").write_text(
            json.dumps(meta, indent=2), encoding="utf-8"
        )
        (self._root / f"{doc_id}.chunks.json").write_text(json.dumps(embedded), encoding="utf-8")
        return meta

    def delete_document(self, document_id: str) -> None:
        meta = self._root / f"{document_id}.meta.json"
        chunks = self._root / f"{document_id}.chunks.json"
        if not meta.exists():
            raise NotFoundError("Document not found.")
        meta.unlink(missing_ok=True)
        chunks.unlink(missing_ok=True)

    def search(self, query: str, *, top_k: int | None = None) -> list[Citation]:
        query = query.strip()
        if not query:
            raise ValidationError("Query is required.")
        q_vec = _hash_embed(query, self._settings.qdrant_vector_size)
        scored: list[tuple[float, Citation]] = []
        for meta_path in self._root.glob("*.meta.json"):
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            chunk_path = self._root / f"{meta['id']}.chunks.json"
            if not chunk_path.exists():
                continue
            for chunk in json.loads(chunk_path.read_text(encoding="utf-8")):
                score = _cosine(q_vec, chunk["embedding"])
                scored.append(
                    (
                        score,
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
        limit = top_k or self._settings.rag_top_k
        return [citation for _, citation in scored[:limit]]
