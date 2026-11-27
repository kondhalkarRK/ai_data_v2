"""Application-database-only response history and feedback; never runs analytics or a model."""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AuthorizationError, ConflictError, NotFoundError
from app.models import BiReportRecord, ChatRating, QueryHistory
from app.rag.acl import RetrievalPrincipal, authorized_document_ids


def scope_key(user, scope) -> str:
    return f"{user.role.value}:{scope.cache_key()}"


def snapshot_report(snapshot):
    report = snapshot.get("report")
    if not report:
        event = next(
            (e["data"] for e in snapshot.get("events", []) if e.get("event") == "report"), None
        )
        if event:
            report = {"id": event.get("reportId"), "revision": event.get("revision")}
    if report:
        try:
            uuid.UUID(report["id"])
            if type(report["revision"]) is not int or report["revision"] < 1:
                raise ValueError("Invalid revision")
        except (KeyError, ValueError, TypeError, AttributeError) as exc:
            raise AuthorizationError("This saved report reference is unavailable.") from exc
    return report


async def owned_response(session, response_id, user, industry):
    row = await session.scalar(
        select(QueryHistory).where(
            QueryHistory.id == response_id,
            QueryHistory.user_id == user.id,
            QueryHistory.industry == industry.value,
        )
    )
    if row is None:
        raise NotFoundError("This response is not available.")
    return row


async def check_access(session, row, user, industry, scope, settings):
    snapshot = row.response_snapshot or {}
    if snapshot and snapshot.get("scope") != scope_key(user, scope):
        raise AuthorizationError(
            "This saved response belongs to a different access scope. Ask again with your current access."
        )
    documents = set(snapshot.get("documents", []))
    if documents:
        allowed = (
            await authorized_document_ids(
                session, RetrievalPrincipal(user=user, industry=industry.value, region_scope=scope)
            )
            if settings.ask_me_rag_enabled
            else set()
        )
        if not documents <= {str(item) for item in allowed}:
            raise AuthorizationError(
                "Document evidence for this response is no longer available to you."
            )
    report = snapshot_report(snapshot)
    if report:
        saved = await session.get(BiReportRecord, uuid.UUID(report["id"]))
        if saved is None or saved.user_id != user.id or saved.scope_key != scope_key(user, scope):
            raise AuthorizationError("This report is no longer available to you.")


def rating_payload(row):
    return (
        None
        if row is None
        else {
            "rating": row.rating,
            "reason": row.reason,
            "note": row.note,
            "reportId": str(row.report_id) if row.report_id else None,
            "reportRevision": row.report_revision,
        }
    )


async def save_rating(session: AsyncSession, row, user, body):
    if row.status == "running":
        raise ConflictError("Wait for the response to finish before rating it.")
    # A composite primary key plus an atomic upsert handles concurrent tabs.
    if session.get_bind().dialect.name == "postgresql":
        from sqlalchemy.dialects.postgresql import insert
    else:
        from sqlalchemy.dialects.sqlite import insert
    from sqlalchemy import func

    report = snapshot_report(row.response_snapshot or {}) or {}
    values = {
        "rating": body.rating,
        "reason": body.reason if body.rating == "down" else None,
        "note": body.note.strip() or None if body.rating == "down" and body.note else None,
        "report_id": uuid.UUID(report["id"]) if report else None,
        "report_revision": report.get("revision"),
    }
    statement = insert(ChatRating).values(response_id=row.id, user_id=user.id, **values)
    await session.execute(
        statement.on_conflict_do_update(
            index_elements=[ChatRating.response_id, ChatRating.user_id],
            set_={**values, "updated_at": func.now()},
        )
    )
    await session.commit()
    return rating_payload(await session.get(ChatRating, (row.id, user.id), populate_existing=True))
