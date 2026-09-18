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

COLLECTIONS = (
    "dealer_reports",
    "market_research",
    "product_catalogs",
    "sales_reports",
    "policies",
    "general",
)

_ENTITY_TERMS = (
    "hyundai",
    "toyota",
    "suzuki",
    "honda",
    "tata",
    "kia",
    "mahindra",
    "mumbai",
    "delhi",
    "pune",
    "bengaluru",
    "bangalore",
    "chennai",
    "hyderabad",
    "kolkata",
    "suv",
    "sedan",
    "hatchback",
    "muv",
    "ev",
    "electric",
)


@dataclass(slots=True)
class Citation:
    document_id: str
    title: str
    chunk_id: str
    snippet: str
    locator: str
    untrusted: bool = False
    confidence: float = 0.0
    collection: str = "general"


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


def _clip_confidence(score: float) -> float:
    return max(0.0, min(1.0, (score + 1.0) / 2.0))


def infer_collection(title: str, filename: str, explicit: str | None = None) -> str:
    if explicit and explicit in COLLECTIONS:
        return explicit
    blob = f"{title} {filename}".casefold()
    if "catalog" in blob:
        return "product_catalogs"
    if "policy" in blob or "policies" in blob:
        return "policies"
    if "market" in blob or "research" in blob:
        return "market_research"
    if "dealer" in blob:
        return "dealer_reports"
    if "sales" in blob:
        return "sales_reports"
    return "general"


def extract_entities(text: str) -> list[str]:
    found: list[str] = []
    low = text.casefold()
    for term in _ENTITY_TERMS:
        if re.search(rf"\b{re.escape(term)}\b", low):
            found.append(term)
    for match in re.findall(r"\b([A-Z][a-z]{2,}(?:\s+[A-Z][a-z]{2,})?)\b", text):
        key = match.casefold()
        if key not in found and len(key) >= 3:
            found.append(key)
    seen: set[str] = set()
    out: list[str] = []
    for item in found:
        if item not in seen:
            seen.add(item)
            out.append(item)
    return out[:24]


def suggested_questions_for(collection: str) -> list[str]:
    common = [
        "What are the key findings?",
        "What concerns or risks are mentioned?",
        "Which models or products are mentioned?",
        "What recommendations does the document make?",
    ]
    extras = {
        "dealer_reports": ["Which dealers or regions are highlighted?"],
        "market_research": ["What market trends are described?"],
        "product_catalogs": ["Which models are in the catalog?"],
        "sales_reports": ["What sales issues or wins are called out?"],
        "policies": ["What policy rules are stated?"],
    }
    return common + extras.get(collection, [])


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

    def ingest_text(
        self,
        *,
        title: str,
        text: str,
        filename: str,
        collection: str | None = None,
    ) -> dict[str, Any]:
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
        chosen = infer_collection(title, filename, collection)
        doc_id = content_hash[:16]
        pieces = chunk_text(
            text,
            max_chars=self._settings.rag_chunk_max_chars,
            min_chars=self._settings.rag_chunk_min_chars,
            overlap=self._settings.rag_chunk_overlap_chars,
        )
        doc_entities = extract_entities(f"{title} {text[:4000]}")
        chunks = [
            {
                "id": f"{doc_id}:{index}",
                "text": piece,
                "embedding": _hash_embed(piece, self._settings.qdrant_vector_size),
                "locator": f"chunk-{index + 1}",
                "entities": extract_entities(piece) or doc_entities,
            }
            for index, piece in enumerate(pieces)
        ]
        return self._store.save_document(
            title=title or filename,
            filename=filename,
            content_hash=content_hash,
            raw_text=text,
            chunks=chunks,
            collection=chosen,
            suggested_questions=suggested_questions_for(chosen),
            entities=doc_entities,
        )

    def ingest_bytes(
        self,
        *,
        title: str,
        raw: bytes,
        filename: str,
        collection: str | None = None,
    ) -> dict[str, Any]:
        if len(raw) > self._settings.upload_max_bytes:
            raise ValidationError("Upload exceeds the configured size limit.")
        suffix = Path(filename).suffix.lower()
        if suffix not in {ext.lower() for ext in self._settings.upload_allowed_extensions}:
            raise ValidationError(f"Unsupported upload type '{suffix or '(none)'}'.")
        return self.ingest_text(
            title=title,
            text=extract_text(filename, raw),
            filename=filename,
            collection=collection,
        )

    def delete_document(self, document_id: str) -> None:
        self._store.delete_document(document_id)

    def search(
        self,
        query: str,
        *,
        top_k: int | None = None,
        user_id: str | None = None,
        collection: str | None = None,
        entities: list[str] | None = None,
    ) -> list[Citation]:
        query = query.strip()
        if not query:
            raise ValidationError("Query is required.")
        query_vector = _hash_embed(query, self._settings.qdrant_vector_size)
        wanted = {item.casefold() for item in (entities or []) if item}
        rows = self._store.iter_chunks(collection=collection)
        if wanted:
            filtered = [
                (meta, chunk)
                for meta, chunk in rows
                if _chunk_mentions(meta, chunk, wanted)
            ]
            if filtered:
                rows = filtered
        scored: list[tuple[float, Citation]] = []
        for meta, chunk in rows:
            score = _cosine(query_vector, chunk["embedding"])
            scored.append(
                (
                    score,
                    Citation(
                        document_id=meta["id"],
                        title=meta["title"],
                        chunk_id=chunk["id"],
                        snippet=chunk["text"][:400],
                        locator=chunk["locator"],
                        confidence=_clip_confidence(score),
                        collection=str(meta.get("collection") or "general"),
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
                    "confidence": hit.confidence,
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
                        "entities": extract_entities(piece),
                    }
                    for index, piece in enumerate(pieces)
                ],
            )
            count += 1
        return {"documents": count}

    def reindex_all(self) -> dict[str, int]:
        return self.reindex()


def _chunk_mentions(
    meta: dict[str, Any], chunk: dict[str, Any], wanted: set[str]
) -> bool:
    tags = [str(item).casefold() for item in (chunk.get("entities") or meta.get("entities") or [])]
    blob = f"{chunk.get('text', '')} {meta.get('title', '')}".casefold()
    return any(term in tags or term in blob for term in wanted)
