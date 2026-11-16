"""Offline contract tests for the first portable-RAG slice."""
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.api.deps import get_optional_scoped_analytics
from app.api.routes.chat import AskRequest
from app.core.config import Settings
from app.core.exceptions import ValidationError
from app.rag.chroma_index import ChromaIndex
from app.rag.embeddings import EmbeddingIdentity, collection_name_for
from app.rag.chunking import chunk_document_text
from app.services.chat.query_router import explicit_document_question, route_question


@pytest.mark.parametrize('question, expected', [
    ('How do I escalate a delayed delivery?', True),
    ('What compensation does the policy guarantee?', True),
    ('What does the West memo say?', True),
    ('How many units were sold?', False),
    ('What was October revenue?', False),
    ('Create a sales report by region', False),
])
def test_evidence_routing(question: str, expected: bool) -> None:
    assert explicit_document_question(question) is expected
    if expected:
        assert route_question(question, None).route == 'knowledge'


def test_mode_is_opt_in() -> None:
    assert AskRequest(question='How do I escalate?').use_documents is False
    assert AskRequest(question='How do I escalate?', useDocuments=True).use_documents is True


def test_demo_policy_is_real_chunking_fixture() -> None:
    path = Path(__file__).resolve().parents[3] / 'docs/rag-demo/01_DEMO_AUTOMOTIVE_DELIVERY_POLICY.md'
    pieces = chunk_document_text(path.read_text(encoding='utf-8'), max_chars=1400, min_chars=40, overlap=180)
    assert any('two business days' in piece.text for piece in pieces)
    assert any('five business days' in piece.text for piece in pieces)
    assert all(piece.locator for piece in pieces)


def test_chroma_never_searches_empty_grant(tmp_path: Path) -> None:
    index = ChromaIndex(str(tmp_path))
    assert index.query(collection_name='test', query_vector=[1, 0], allowed_document_ids=[], top_k=2) == []
    assert index._client is None


def test_chroma_applies_acl_and_normalizes_cosine_distance(tmp_path: Path) -> None:
    index = ChromaIndex(str(tmp_path))
    client = MagicMock()
    index._client = client
    client.list_collections.return_value = [SimpleNamespace(name='test')]
    collection = client.get_collection.return_value
    meta = dict(documentId='allowed', chunkId='chunk', title='Demo', locator='section-2', collection='policies', version=2)
    collection.query.return_value = dict(metadatas=[[meta]], documents=[['two business days']], distances=[[.1]])
    result = index.query(collection_name='test', query_vector=[1, 0], allowed_document_ids=['allowed'], top_k=1)
    assert result[0].score == pytest.approx(.9)
    assert collection.query.call_args.kwargs['where'] == {'documentId': {'$in': ['allowed']}}
    assert client.get_collection.call_args.kwargs['embedding_function'] is None


def test_chroma_rejects_mismatched_vectors_before_open(tmp_path: Path) -> None:
    index = ChromaIndex(str(tmp_path))
    with pytest.raises(ValidationError):
        index.upsert_chunks(collection_name='test', identity=EmbeddingIdentity('api', 'test', 2), document_id='a', industry='automotive', title='a', doc_collection='policies', version=1, region_zones=None, chunks=[{'id':'x'}], vectors=[[float('nan'), 0]])
    assert index._client is None


def test_chroma_namespace_separates_embedding_endpoints() -> None:
    a = Settings(rag_vector_backend='chroma', rag_embedding_base_url='https://a.example/v1')
    b = a.model_copy(update={'rag_embedding_base_url': 'https://b.example/v1'})
    identity = EmbeddingIdentity('openai_compatible', 'embed', 3)
    assert collection_name_for(a, industry='automotive', identity=identity) != collection_name_for(b, industry='automotive', identity=identity)

@pytest.mark.asyncio
async def test_document_only_chat_allows_missing_analytics_connection() -> None:
    registry = MagicMock()
    registry.analytics_connection.side_effect = RuntimeError('warehouse unavailable')

    async def _run() -> None:
        async for _ in get_optional_scoped_analytics(
            industry=Settings().default_industry,
            registry=registry,
            scope=SimpleNamespace(),
        ):
            pass

    await _run()

@pytest.mark.parametrize('enabled, requested', [(True, False), (False, True), (False, False)])
def test_document_off_gate_precedes_retrieval(monkeypatch, enabled: bool, requested: bool) -> None:
    import asyncio
    asyncio.run(_off_gate(monkeypatch, enabled, requested))


async def _off_gate(monkeypatch, enabled: bool, requested: bool) -> None:
    import uuid
    from unittest.mock import AsyncMock
    import app.services.chat.service as module
    from app.models.enums import Role
    from app.services.chat.conversation_memory import SessionMemory
    from app.services.security.region_scope import RegionScope

    user = SimpleNamespace(id=uuid.uuid4(), role=Role.USER)
    scope = RegionScope.all_regions(user)
    monkeypatch.setattr(module, 'load_region_scope', AsyncMock(return_value=scope))
    knowledge = MagicMock()
    monkeypatch.setattr(module, 'KnowledgeService', knowledge)
    service = module.ChatService(app_session=AsyncMock(), analytics=MagicMock(), settings=Settings(ask_me_rag_enabled=enabled), user=user, industry=module.Industry.AUTOMOTIVE, semantic_service=MagicMock(), region_scope=scope)
    conversation = SimpleNamespace(id=uuid.uuid4())
    service._ensure_conversation = AsyncMock(return_value=conversation)
    service._load_session_memory = AsyncMock(return_value=SessionMemory(version=1, user_id=str(user.id), conversation_id=str(conversation.id)))
    service._create_running_history = AsyncMock(return_value=SimpleNamespace())
    frames = [frame async for frame in service.ask_stream('How do I escalate a delayed delivery?', None, use_documents=requested)]
    assert 'Knowledge documents are off or unavailable' in ''.join(frames)
    knowledge.assert_not_called()
