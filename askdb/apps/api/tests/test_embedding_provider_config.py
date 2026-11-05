"""Embedding configuration must never download a local model."""

import threading
from types import SimpleNamespace

import pytest

from app.core.exceptions import ValidationError
from app.rag.embeddings import (
    EmbeddingIdentity,
    OpenAICompatibleEmbeddingClient,
    build_embedding_client,
)


def test_old_local_provider_fails_before_any_client_is_built(settings, monkeypatch):
    def forbidden(**kwargs):
        pytest.fail("An obsolete provider must not construct a client or make a request")

    monkeypatch.setattr("app.rag.embeddings.OpenAICompatibleEmbeddingClient", forbidden)
    old = settings.model_copy(update={"rag_embedding_provider": "sentence_transformers"})
    with pytest.raises(ValidationError, match="Local Hugging Face embeddings have been removed"):
        build_embedding_client(old)


def test_embedding_model_must_be_explicit():
    with pytest.raises(ValidationError, match="RAG_EMBEDDING_MODEL"):
        OpenAICompatibleEmbeddingClient(model_id="", base_url="", api_key="")


@pytest.mark.asyncio
async def test_readiness_runs_embedding_and_vector_probes_off_event_loop(settings, monkeypatch):
    from app.api.routes.system import _dependency_reports

    event_loop_thread = threading.get_ident()

    def ping(self):
        assert threading.get_ident() != event_loop_thread
        return True, "fixture"

    def identity(config):
        assert threading.get_ident() != event_loop_thread
        return EmbeddingIdentity("openai_compatible", "fixture", 8)

    async def database(*args):
        return True, "fixture"

    monkeypatch.setattr("app.rag.qdrant_index.QdrantIndex.ping", ping)
    monkeypatch.setattr("app.rag.embeddings.verify_embedding_identity", identity)
    registry = SimpleNamespace(check_app_database=database, check_analytics_database=database)
    reports = await _dependency_reports(
        registry, settings.model_copy(update={"ask_me_rag_enabled": True})
    )
    assert next(report for report in reports if report.name == "rag_embeddings").status == "ok"
