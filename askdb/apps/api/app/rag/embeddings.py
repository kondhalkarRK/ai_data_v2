"""Real embedding providers for Traditional RAG (no hash fallback on this path)."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from functools import lru_cache
from typing import Any, Protocol

import httpx

from app.core.config import Settings
from app.core.exceptions import DependencyUnavailableError, ValidationError

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class EmbeddingIdentity:
    provider: str
    model_id: str
    dimension: int


class EmbeddingClient(Protocol):
    def identity(self) -> EmbeddingIdentity: ...

    def embed_texts(self, texts: list[str]) -> list[list[float]]: ...

    def embed_query(self, text: str) -> list[float]: ...


class SentenceTransformersEmbeddingClient:
    def __init__(self, model_id: str, expected_dimension: int | None = None) -> None:
        try:
            from sentence_transformers import SentenceTransformer  # type: ignore
        except ImportError as exc:
            raise DependencyUnavailableError(
                "sentence-transformers is required for rag_embedding_provider=sentence_transformers."
            ) from exc
        self._model_id = model_id
        self._model = SentenceTransformer(model_id)
        probe = self._model.encode(["dimension-probe"], normalize_embeddings=True)
        self._dimension = int(len(probe[0]))
        if expected_dimension and expected_dimension != self._dimension:
            raise ValidationError(
                f"Embedding model '{model_id}' produces {self._dimension} dimensions, "
                f"but RAG_EMBEDDING_DIMENSION={expected_dimension}."
            )

    def identity(self) -> EmbeddingIdentity:
        return EmbeddingIdentity(
            provider="sentence_transformers",
            model_id=self._model_id,
            dimension=self._dimension,
        )

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        vectors = self._model.encode(texts, normalize_embeddings=True)
        return [list(map(float, row)) for row in vectors]

    def embed_query(self, text: str) -> list[float]:
        return self.embed_texts([text])[0]


class OpenAICompatibleEmbeddingClient:
    def __init__(
        self,
        *,
        model_id: str,
        base_url: str,
        api_key: str,
        expected_dimension: int | None = None,
        timeout_seconds: float = 60.0,
        verify: bool | str = True,
    ) -> None:
        if not base_url.strip():
            raise ValidationError("RAG_EMBEDDING_BASE_URL is required for openai_compatible.")
        if not api_key.strip():
            raise ValidationError("RAG_EMBEDDING_API_KEY (or LLM_API_KEY) is required.")
        self._model_id = model_id
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._timeout = timeout_seconds
        self._verify = verify
        probe = self.embed_texts(["dimension-probe"])
        self._dimension = len(probe[0])
        if expected_dimension and expected_dimension != self._dimension:
            raise ValidationError(
                f"Embedding model '{model_id}' produces {self._dimension} dimensions, "
                f"but RAG_EMBEDDING_DIMENSION={expected_dimension}."
            )

    def identity(self) -> EmbeddingIdentity:
        return EmbeddingIdentity(
            provider="openai_compatible",
            model_id=self._model_id,
            dimension=self._dimension,
        )

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        url = f"{self._base_url}/embeddings"
        payload: dict[str, Any] = {"model": self._model_id, "input": texts}
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        with httpx.Client(timeout=self._timeout, verify=self._verify) as client:
            response = client.post(url, json=payload, headers=headers)
            response.raise_for_status()
            data = response.json()
        items = sorted(data.get("data") or [], key=lambda row: int(row.get("index", 0)))
        vectors = [list(map(float, item["embedding"])) for item in items]
        if len(vectors) != len(texts):
            raise DependencyUnavailableError("Embedding provider returned incomplete batch.")
        return vectors

    def embed_query(self, text: str) -> list[float]:
        return self.embed_texts([text])[0]


class FakeEmbeddingClient:
    """Deterministic non-hash vectors for unit tests only."""

    def __init__(self, dimension: int = 8, model_id: str = "fake-embed") -> None:
        self._dimension = dimension
        self._model_id = model_id

    def identity(self) -> EmbeddingIdentity:
        return EmbeddingIdentity(
            provider="openai_compatible",
            model_id=self._model_id,
            dimension=self._dimension,
        )

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        out: list[list[float]] = []
        for text in texts:
            seed = sum(ord(ch) for ch in text) or 1
            vec = [((seed * (i + 1)) % 97) / 97.0 for i in range(self._dimension)]
            norm = sum(v * v for v in vec) ** 0.5 or 1.0
            out.append([v / norm for v in vec])
        return out

    def embed_query(self, text: str) -> list[float]:
        return self.embed_texts([text])[0]


def build_embedding_client(settings: Settings) -> EmbeddingClient:
    expected = settings.rag_embedding_dimension or None
    if settings.rag_embedding_provider == "sentence_transformers":
        return SentenceTransformersEmbeddingClient(
            settings.rag_embedding_model, expected_dimension=expected
        )
    api_key = (
        settings.rag_embedding_api_key.get_secret_value().strip()
        or settings.llm_api_key.get_secret_value().strip()
    )
    base_url = settings.rag_embedding_base_url.strip() or settings.llm_base_url.strip()
    return OpenAICompatibleEmbeddingClient(
        model_id=settings.rag_embedding_model,
        base_url=base_url,
        api_key=api_key,
        expected_dimension=expected,
        timeout_seconds=float(settings.llm_timeout_seconds),
        verify=settings.httpx_verify,
    )


def embed_texts_batched(
    client: EmbeddingClient, texts: list[str], *, batch_size: int
) -> list[list[float]]:
    if batch_size < 1:
        raise ValidationError("batch_size must be >= 1")
    vectors: list[list[float]] = []
    for start in range(0, len(texts), batch_size):
        batch = texts[start : start + batch_size]
        vectors.extend(client.embed_texts(batch))
    return vectors


@lru_cache(maxsize=4)
def _cached_identity(
    provider: str, model: str, dimension: int, base_url: str, key_fp: str
) -> EmbeddingIdentity:
    # Cache key only; actual client construction happens in verify_embedding_identity.
    return EmbeddingIdentity(provider=provider, model_id=model, dimension=dimension or 0)


def verify_embedding_identity(settings: Settings, client: EmbeddingClient | None = None) -> EmbeddingIdentity:
    active = client or build_embedding_client(settings)
    identity = active.identity()
    if settings.rag_embedding_dimension and settings.rag_embedding_dimension != identity.dimension:
        raise ValidationError(
            f"Configured RAG_EMBEDDING_DIMENSION={settings.rag_embedding_dimension} "
            f"does not match provider dimension {identity.dimension}."
        )
    logger.info(
        "rag embedding identity verified provider=%s model=%s dim=%s",
        identity.provider,
        identity.model_id,
        identity.dimension,
    )
    return identity


def collection_name_for(
    settings: Settings,
    *,
    industry: str,
    identity: EmbeddingIdentity,
) -> str:
    """Never mix incompatible dimensions in one collection."""
    prefix = settings.rag_qdrant_collection_prefix.strip() or "askme_rag"
    safe_model = re_sub_model(identity.model_id)
    return f"{prefix}_{industry}_{safe_model}_d{identity.dimension}"


def re_sub_model(model_id: str) -> str:
    import re

    return re.sub(r"[^a-zA-Z0-9]+", "_", model_id).strip("_").lower()[:48] or "model"
