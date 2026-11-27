"""Feedback/history HTTP acceptance over an isolated app DB, no warehouse or provider."""

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import func, select

from app.api.deps import get_current_user, get_scoped_analytics
from app.core.config import Industry
from app.models import BiReportRecord, ChatRating, Conversation, QueryHistory, Role, User


@pytest.fixture
async def chat_feedback(client, db_session):
    user = User(
        id=uuid.uuid4(),
        username="soci-owner",
        email="owner@example.test",
        email_normalized="owner@example.test",
        full_name="Anita Sharma",
        password_hash="test",
        role=Role.ADMIN,
        default_industry=Industry.AUTOMOTIVE,
        is_active=True,
    )
    db_session.add(user)
    await db_session.flush()
    conversation = Conversation(
        id=uuid.uuid4(), user_id=user.id, industry="automotive", title="Sales"
    )
    db_session.add(conversation)
    await db_session.flush()
    row = QueryHistory(
        id=uuid.uuid4(),
        user_id=user.id,
        conversation_id=conversation.id,
        industry="automotive",
        question="Revenue last month",
        status="completed",
        sql_text="SELECT protected_value",
        response_snapshot={
            "scope": "admin:all",
            "events": [{"event": "token", "data": {"token": "Verified answer"}}],
            "documents": [],
        },
    )
    db_session.add(row)
    await db_session.commit()
    principal = SimpleNamespace(user=user)
    app = client._transport.app
    app.dependency_overrides[get_current_user] = lambda: principal.user
    client.headers.update(
        {"authorization": "Bearer test-auth-override", "x-industry": "automotive"}
    )
    return SimpleNamespace(
        client=client,
        app=app,
        user=user,
        principal=principal,
        row=row,
        conversation=conversation,
        session=db_session,
        url=f"/api/v1/chat/responses/{row.id}/rating",
    )


async def test_feedback_create_edit_clear_and_history_restore(chat_feedback):
    e = chat_feedback
    # The registry cannot supply analytics; these requests must not need a warehouse.
    assert (await e.client.put(e.url, json={"rating": "up"})).status_code == 200
    down = await e.client.put(
        e.url, json={"rating": "down", "reason": "incorrect", "note": "Check the period"}
    )
    assert down.json()["feedback"]["note"] == "Check the period"
    assert (await e.client.get(e.url)).json()["feedback"]["rating"] == "down"
    saved = await e.client.get(f"/api/v1/chat/conversations/{e.conversation.id}")
    turn = saved.json()["turns"][0]
    assert turn["responseId"] == str(e.row.id) and turn["rating"]["reason"] == "incorrect"
    assert turn["events"][0]["data"]["token"] == "Verified answer"
    assert await e.session.scalar(select(func.count()).select_from(ChatRating)) == 1
    assert (await e.client.delete(e.url)).status_code == 200
    assert (await e.client.get(e.url)).json()["feedback"] is None
    assert await e.session.scalar(select(func.count()).select_from(ChatRating)) == 0


@pytest.mark.parametrize(
    "body",
    [
        {"rating": "wrong"},
        {"rating": "down", "reason": "secret"},
        {"rating": "down", "note": "x" * 2001},
        {"rating": "up", "userId": "someone-else"},
        {"rating": "up", "reportId": str(uuid.uuid4())},
    ],
)
async def test_invalid_feedback_and_identity_injection_rejected(chat_feedback, body):
    assert (await chat_feedback.client.put(chat_feedback.url, json=body)).status_code == 422


async def test_owner_and_industry_enforced_even_for_admin(chat_feedback):
    e = chat_feedback
    e.client.headers["x-industry"] = "insurance"
    assert (await e.client.get(e.url)).status_code == 404
    assert (
        await e.client.get(f"/api/v1/chat/conversations/{e.conversation.id}")
    ).status_code == 404
    e.client.headers["x-industry"] = "automotive"
    other = User(
        id=uuid.uuid4(),
        username="other",
        email="other@example.test",
        email_normalized="other@example.test",
        full_name="Other User",
        password_hash="test",
        role=Role.ADMIN,
        default_industry=Industry.AUTOMOTIVE,
        is_active=True,
    )
    e.session.add(other)
    await e.session.commit()
    e.principal.user = other
    for method in (e.client.get, e.client.delete):
        assert (await method(e.url)).status_code == 404
    assert (await e.client.put(e.url, json={"rating": "up"})).status_code == 404
    assert (await e.client.get("/api/v1/chat/conversations")).json()["items"] == []


async def test_revoked_scope_hides_saved_answer_and_blocks_rating(chat_feedback):
    e = chat_feedback
    e.row.response_snapshot = {**e.row.response_snapshot, "scope": "user:North"}
    await e.session.commit()
    assert (await e.client.get(e.url)).status_code == 403
    history = (await e.client.get(f"/api/v1/chat/conversations/{e.conversation.id}")).json()
    assert not history["turns"][0]["canRate"]
    assert "Verified answer" not in str(history) and "protected_value" not in str(history)
    assert (await e.client.put(e.url, json={"rating": "up"})).status_code == 403


async def test_deleted_document_evidence_not_replayed(chat_feedback):
    e = chat_feedback
    e.row.response_snapshot = {**e.row.response_snapshot, "documents": [str(uuid.uuid4())]}
    await e.session.commit()
    assert (await e.client.get(e.url)).status_code == 403
    history = (await e.client.get(f"/api/v1/chat/conversations/{e.conversation.id}")).json()
    assert "Verified answer" not in str(history)


async def test_legacy_response_reuses_history_id_without_fabricating_content(chat_feedback):
    e = chat_feedback
    e.row.response_snapshot = None
    await e.session.commit()
    saved = (await e.client.get(f"/api/v1/chat/conversations/{e.conversation.id}")).json()
    assert saved["turns"][0]["responseId"] == str(e.row.id)
    assert "no saved answer content" in str(saved) and "protected_value" not in str(saved)
    assert (await e.client.put(e.url, json={"rating": "up"})).status_code == 200


async def test_linked_report_checked_and_revision_is_server_owned(chat_feedback):
    e = chat_feedback
    report = BiReportRecord(
        id=uuid.uuid4(),
        user_id=e.user.id,
        title="Report",
        revision=3,
        scope_key="admin:all",
        semantic_revision="fixture",
        state={},
        requests=[],
    )
    e.session.add(report)
    e.row.response_snapshot = {
        **e.row.response_snapshot,
        "report": {"id": str(report.id), "revision": 2},
    }
    await e.session.commit()
    rated = await e.client.put(e.url, json={"rating": "up"})
    assert rated.json()["feedback"]["reportId"] == str(report.id)
    assert rated.json()["feedback"]["reportRevision"] == 2
    report.scope_key = "user:West"
    await e.session.commit()
    assert (await e.client.get(e.url)).status_code == 403


async def test_running_response_not_rateable(chat_feedback):
    e = chat_feedback
    e.row.status = "running"
    await e.session.commit()
    assert (await e.client.put(e.url, json={"rating": "up"})).status_code == 409


@pytest.mark.parametrize("transport", ["ask", "ask-sync"])
async def test_both_transports_persist_the_same_response_identity(
    chat_feedback, monkeypatch, transport
):
    from app.api.routes.chat import _sse_events_from_frames
    from app.services.chat.service import ChatService, _sse

    e = chat_feedback
    warehouse = AsyncMock()
    warehouse.execute.side_effect = AssertionError("No analytics permitted in this check")

    async def analytics():
        yield warehouse

    e.app.dependency_overrides[get_scoped_analytics] = analytics

    async def frames(service, *args, **kwargs):
        row = QueryHistory(
            id=uuid.uuid4(),
            user_id=e.user.id,
            conversation_id=e.conversation.id,
            industry="automotive",
            question="Hello",
            status="completed",
        )
        service._app.add(row)
        service.last_history = row
        await service._app.commit()
        yield _sse("stage", {"stage": "accepted", "historyId": str(row.id)})
        yield _sse("token", {"token": "Hello Anita"})
        yield _sse("meta", {"rowCount": 0})
        yield _sse("done", {"historyId": str(row.id), "conversationId": str(e.conversation.id)})

    monkeypatch.setattr(ChatService, "ask_stream", frames)
    response = await e.client.post(f"/api/v1/chat/{transport}", json={"question": "Hello"})
    assert response.status_code == 200, response.text
    events = (
        response.json()["events"]
        if transport == "ask-sync"
        else _sse_events_from_frames(response.text.split("\n\n"))
    )
    response_id = next(x["data"]["historyId"] for x in events if x["event"] == "done")
    url = f"/api/v1/chat/responses/{response_id}/rating"
    assert (await e.client.put(url, json={"rating": "up"})).status_code == 200
    saved = (await e.client.get(f"/api/v1/chat/conversations/{e.conversation.id}")).json()
    turn = next(t for t in saved["turns"] if t["responseId"] == response_id)
    assert turn["events"][0]["data"]["token"] == "Hello Anita"
    warehouse.execute.assert_not_awaited()


async def test_authentication_required(chat_feedback):
    e = chat_feedback
    e.app.dependency_overrides.pop(get_current_user)
    e.client.headers.pop("authorization")
    assert (await e.client.get(e.url)).status_code == 401


async def test_old_report_events_still_enforce_report_ownership(chat_feedback):
    e = chat_feedback
    e.row.response_snapshot = {
        "scope": "admin:all",
        "events": [
            {
                "event": "report",
                "data": {
                    "reportId": str(uuid.uuid4()),
                    "revision": 2,
                    "panels": [{"secret": "protected report value"}],
                },
            }
        ],
    }
    await e.session.commit()
    assert (await e.client.get(e.url)).status_code == 403
    history = (await e.client.get(f"/api/v1/chat/conversations/{e.conversation.id}")).json()
    assert "protected report value" not in str(history)
