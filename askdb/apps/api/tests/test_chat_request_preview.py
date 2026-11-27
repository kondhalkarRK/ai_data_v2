"""Gated preview HTTP acceptance. No warehouse dependency and no live provider."""

import json
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from sqlalchemy import select

from app.api import deps
from app.api.routes import chat
from app.core.config import Industry
from app.core.exceptions import RateLimitedError
from app.models import LlmUsage, Role, User
from app.semantic.service import SemanticService
from app.services.chat import request_interpreter
from app.services.chat.request_context import RequestPrincipal, ScopedCatalog
from app.services.chat.value_dictionary import BusinessValue, ValueDictionarySnapshot
from app.services.llm import LlmResult
from app.services.security.region_scope import RegionScope


@pytest.mark.asyncio
@pytest.mark.parametrize("endpoint", ["ask", "ask-sync"])
@pytest.mark.parametrize("empty", [False, True])
async def test_gated_typed_chat_transports_keep_sql_and_all_measures(
    preview_api, monkeypatch, endpoint, empty
):
    """Real endpoints/shared service/persistence; warehouse and provider remain fixtures."""
    from app.services.chat import request_runtime

    e = preview_api
    e.settings.chat_typed_execution_enabled = True
    result = Mock()
    result.mappings.return_value.all.return_value = (
        [] if empty else [{"revenue": 5600, "units_sold": 36, "__total_groups": 1}]
    )
    result.keys.return_value = ["revenue", "units_sold", "__total_groups"]
    result.fetchall.return_value = [("Fixture explain",)]
    analytics = AsyncMock()
    analytics.execute.return_value = result
    e.app.dependency_overrides[deps.get_optional_scoped_analytics] = lambda: analytics
    principal = RequestPrincipal(e.user.id, RegionScope.all_regions(e.user), Industry.AUTOMOTIVE)
    catalog = ScopedCatalog(principal.binding, ValueDictionarySnapshot(Industry.AUTOMOTIVE, ()))
    monkeypatch.setattr(request_runtime, "scoped_catalog", AsyncMock(return_value=(catalog, None)))
    e.llm.return_value.content = json.dumps(
        {
            "outcome": "analytics",
            "summary": "Revenue and units January 2026",
            "measures": [{"id": "revenue"}, {"id": "units_sold"}],
            "period": {"label": "Jan 2026", "start": "2026-01-01", "end_exclusive": "2026-02-01"},
        }
    )
    response = await e.client.post(
        f"/api/v1/chat/{endpoint}", json={"question": "Revenue and units January 2026"}
    )
    assert response.status_code == 200, response.text
    events = (
        response.json()["events"]
        if endpoint == "ask-sync"
        else chat._sse_events_from_frames(response.text.split("\n\n"))
    )
    sql = next(item for item in events if item["event"] == "sql")
    assert "SUM(f.total_sales)" in sql["data"]["sql"]
    rows = next(item for item in events if item["event"] == "rows")
    assert rows["data"]["rows"] == ([] if empty else [{"revenue": 5600, "units_sold": 36}])
    assert e.llm.await_count == 1


@pytest.fixture
async def preview_api(client, db_session, settings, monkeypatch):
    user = User(
        id=uuid.uuid4(),
        username="preview-admin",
        email="preview@example.test",
        email_normalized="preview@example.test",
        full_name="Anita Sharma",
        password_hash="test",
        role=Role.ADMIN,
        default_industry=Industry.AUTOMOTIVE,
        is_active=True,
    )
    db_session.add(user)
    await db_session.commit()
    app = client._transport.app
    scope = RegionScope.all_regions(user)
    pack = SemanticService(settings)._load_pack(Industry.AUTOMOTIVE)
    service = SimpleNamespace(get_pack=AsyncMock(return_value=pack))
    app.dependency_overrides[deps.get_current_user] = lambda: user
    app.dependency_overrides[deps.get_region_scope] = lambda: scope
    app.dependency_overrides[deps.get_semantic_service] = lambda: service
    forbidden = Mock(side_effect=AssertionError("Warehouse dependency reached"))
    app.dependency_overrides[deps.get_scoped_analytics] = forbidden
    app.dependency_overrides[deps.get_optional_scoped_analytics] = forbidden
    configured = settings.model_copy(update={"chat_request_preview_enabled": True})
    app.dependency_overrides[deps.get_app_settings] = lambda: configured
    prepared = AsyncMock()
    monkeypatch.setattr(chat, "_prepare_question", prepared)
    monkeypatch.setattr(request_interpreter, "llm_configured", lambda _: True)
    llm = AsyncMock(
        return_value=LlmResult(
            sql=None,
            narrative="",
            model="fixture-model",
            prompt_tokens=321,
            completion_tokens=45,
            content=json.dumps(
                {
                    "outcome": "definition",
                    "summary": "Revenue definition",
                    "definition_terms": ["revenue"],
                }
            ),
        )
    )
    monkeypatch.setattr(request_interpreter, "complete_text", llm)
    cache = Mock(
        return_value=ValueDictionarySnapshot(
            Industry.AUTOMOTIVE,
            (BusinessValue("Model", "automotive.dim_carline.model", "Private Regional Model"),),
        )
    )
    monkeypatch.setattr(chat, "cached_value_dictionary", cache)
    yield SimpleNamespace(
        client=client,
        app=app,
        user=user,
        settings=configured,
        llm=llm,
        service=service,
        prepared=prepared,
        forbidden=forbidden,
        cache=cache,
        session=db_session,
    )


@pytest.mark.asyncio
async def test_preview_returns_approved_definition_and_meters_only_one_call(preview_api):
    e = preview_api
    response = await e.client.post(
        "/api/v1/chat/route-preview",
        json={
            "question": "How is revenue defined?",
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["preview_only"] and not body["execution_enabled"]
    assert body["routes"] == ["glossary"]
    assert "revenue" in body["approved_definitions"]
    assert "sales" in body["approved_definitions"]["revenue"].lower()
    assert body["usage"]["calls"] == 1
    assert body["original_question"] == "How is revenue defined?"
    e.llm.assert_awaited_once()
    e.prepared.assert_awaited_once()
    e.forbidden.assert_not_called()
    usage = (await e.session.execute(select(LlmUsage))).scalars().all()
    assert len(usage) == 1
    assert usage[0].prompt_tokens == 321 and usage[0].completion_tokens == 45
    assert usage[0].question.startswith("[Routing preview]")
    assert body["request_id"] in usage[0].question


@pytest.mark.asyncio
async def test_preview_disabled_by_default(preview_api):
    e = preview_api
    e.settings.chat_request_preview_enabled = False
    response = await e.client.post("/api/v1/chat/route-preview", json={"question": "Revenue"})
    assert response.status_code == 404
    e.prepared.assert_not_called()
    e.service.get_pack.assert_not_called()
    e.llm.assert_not_called()


@pytest.mark.asyncio
async def test_preview_admin_only_and_requires_authentication(preview_api):
    e = preview_api
    e.user.role = Role.USER
    assert (
        await e.client.post("/api/v1/chat/route-preview", json={"question": "Revenue"})
    ).status_code == 403
    e.app.dependency_overrides.pop(deps.get_current_user)
    assert (
        await e.client.post("/api/v1/chat/route-preview", json={"question": "Revenue"})
    ).status_code == 401
    e.llm.assert_not_called()


@pytest.mark.asyncio
async def test_insurance_remains_outside_preview(preview_api):
    e = preview_api
    e.app.dependency_overrides[deps.resolve_industry] = lambda: Industry.INSURANCE
    assert (
        await e.client.post("/api/v1/chat/route-preview", json={"question": "Premium"})
    ).status_code == 404
    e.llm.assert_not_called()


@pytest.mark.asyncio
async def test_preview_rejects_authority_fields_and_blank_input(preview_api):
    e = preview_api
    for body in [{"question": "Revenue", "user_id": "other"}, {"question": "   "}]:
        assert (await e.client.post("/api/v1/chat/route-preview", json=body)).status_code == 422
    e.llm.assert_not_called()


@pytest.mark.asyncio
async def test_restricted_scope_does_not_read_global_catalog(preview_api):
    e = preview_api
    e.app.dependency_overrides[deps.get_region_scope] = lambda: RegionScope(
        False, ("West",), e.user.id
    )
    response = await e.client.post(
        "/api/v1/chat/route-preview", json={"question": "How is revenue defined?"}
    )
    assert response.status_code == 200
    e.cache.assert_not_called()
    prompt = e.llm.await_args.kwargs["user"]
    assert "Private Regional Model" not in prompt
    assert json.loads(prompt)["approved_context"]["catalog_available"] is False
    e.llm.reset_mock()
    response = await e.client.post(
        "/api/v1/chat/route-preview", json={"question": "Revenue in South"}
    )
    assert response.json()["status"] == "denied"
    e.llm.assert_not_called()


@pytest.mark.asyncio
async def test_preview_respects_existing_quota_before_interpretation(preview_api):
    e = preview_api
    e.prepared.side_effect = RateLimitedError("Question quota reached")
    response = await e.client.post("/api/v1/chat/route-preview", json={"question": "Revenue"})
    assert response.status_code == 429
    e.llm.assert_not_called()
