"""Admin and login audit writes (``admin_audit`` / ``login_audit``)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.governance import AdminAudit, LoginAudit


class AdminAction:
    """Action names written to ``admin_audit``; the Audit Center groups by these."""

    USER_LOGIN = "User Login"
    USER_LOGOUT = "User Logout"
    LOGIN_FAILED = "Login Failed"
    CHANGED_LLM_PROVIDER = "Changed LLM Provider"
    CHANGED_LLM_MODEL = "Changed LLM Model"
    CHANGED_TEMPERATURE = "Changed Temperature"
    CHANGED_MAX_TOKENS = "Changed Max Tokens"
    REFRESHED_DQ_RULES = "Refreshed DQ Rules"
    REFRESHED_TRUST_SCORES = "Refreshed Trust Scores"
    ENABLED_DQ_RULE = "Enabled DQ Rule"
    DISABLED_DQ_RULE = "Disabled DQ Rule"
    REFRESHED_ENTITY_CATALOG = "Refreshed Entity Catalog"
    REFRESHED_SEMANTIC_METADATA = "Refreshed Semantic Metadata"
    REFRESHED_KNOWLEDGE_GRAPH = "Refreshed Knowledge Graph"
    REFRESHED_SEMANTIC_CACHE = "Refreshed Semantic Cache"


AUDIT_CATEGORIES: dict[str, tuple[str, ...]] = {
    "logins": (AdminAction.USER_LOGIN, AdminAction.LOGIN_FAILED),
    "logouts": (AdminAction.USER_LOGOUT,),
    "llm": (
        AdminAction.CHANGED_LLM_PROVIDER,
        AdminAction.CHANGED_LLM_MODEL,
        AdminAction.CHANGED_TEMPERATURE,
        AdminAction.CHANGED_MAX_TOKENS,
    ),
    "dq": (
        AdminAction.REFRESHED_DQ_RULES,
        AdminAction.REFRESHED_TRUST_SCORES,
        AdminAction.ENABLED_DQ_RULE,
        AdminAction.DISABLED_DQ_RULE,
    ),
    "catalog": (
        AdminAction.REFRESHED_ENTITY_CATALOG,
        AdminAction.REFRESHED_SEMANTIC_METADATA,
        AdminAction.REFRESHED_SEMANTIC_CACHE,
    ),
    "graph": (AdminAction.REFRESHED_KNOWLEDGE_GRAPH,),
}


async def record_admin_action(
    session: AsyncSession, user_id: uuid.UUID | None, action: str, details: str | None = None
) -> None:
    session.add(AdminAudit(user_id=user_id, action=action, action_details=details))
    await session.flush()


async def record_login(
    session: AsyncSession, *, user_id: uuid.UUID | None, username: str, succeeded: bool
) -> None:
    session.add(
        LoginAudit(
            user_id=user_id, username=username[:320], status="SUCCESS" if succeeded else "FAILED"
        )
    )
    await record_admin_action(
        session,
        user_id,
        AdminAction.USER_LOGIN if succeeded else AdminAction.LOGIN_FAILED,
        f"Username: {username[:120]}",
    )


async def record_logout(session: AsyncSession, *, user_id: uuid.UUID, username: str) -> None:
    """Close the user's most recent open session row and log the logout."""
    latest = await session.scalar(
        select(LoginAudit.id)
        .where(
            LoginAudit.user_id == user_id,
            LoginAudit.status == "SUCCESS",
            LoginAudit.logout_time.is_(None),
        )
        .order_by(LoginAudit.login_time.desc())
        .limit(1)
    )
    if latest is not None:
        await session.execute(
            update(LoginAudit)
            .where(LoginAudit.id == latest)
            .values(logout_time=datetime.now(UTC), status="LOGOUT")
        )
    await record_admin_action(
        session, user_id, AdminAction.USER_LOGOUT, f"Username: {username[:120]}"
    )
