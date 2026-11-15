"""Process-scoped vector adapters; no extra clients from readiness or each request."""

from functools import lru_cache

from app.core.config import Settings
from app.rag.chroma_index import ChromaIndex
from app.rag.qdrant_index import QdrantIndex


@lru_cache(maxsize=8)
def _chroma(path: str) -> ChromaIndex:
    return ChromaIndex(path)


def vector_index(settings: Settings) -> QdrantIndex | ChromaIndex:
    if settings.rag_vector_backend == "chroma":
        return _chroma(settings.rag_chroma_path)
    return QdrantIndex(settings)
