"""Bring a legacy ``llm_usage`` table up to the shape the governance dashboards read.

A database set up with ``database/app/10_auth_governance.sql`` on top of the older
activity schema keeps the original ``llm_usage`` (``id`` / ``model``, no execution mode),
because ``CREATE TABLE IF NOT EXISTS`` skips it. Every step is idempotent.
"""

from __future__ import annotations

import logging

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

logger = logging.getLogger(__name__)

_AUTH_USER_INDUSTRY_REPAIR = (
    "UPDATE auth_users "
    "SET default_industry = LOWER(default_industry) "
    "WHERE default_industry IS NOT NULL "
    "AND default_industry <> LOWER(default_industry)"
)

_COLUMNS = text(
    "SELECT column_name FROM information_schema.columns "
    "WHERE table_schema = current_schema() AND table_name = 'llm_usage'"
)
_CONSTRAINTS = text(
    "SELECT conname FROM pg_constraint WHERE conrelid = to_regclass('llm_usage')"
)

_ADD_COLUMNS = {
    "question": "ALTER TABLE llm_usage ADD COLUMN question TEXT",
    "execution_mode": (
        "ALTER TABLE llm_usage ADD COLUMN execution_mode VARCHAR(10) NOT NULL DEFAULT 'LLM'"
    ),
    "response_time_ms": "ALTER TABLE llm_usage ADD COLUMN response_time_ms INTEGER",
    "query_history_id": "ALTER TABLE llm_usage ADD COLUMN query_history_id UUID",
}


def plan_auth_user_industry_repair() -> list[str]:
    """Normalize stale uppercase values before enum coercion triggers a LookupError."""
    return [_AUTH_USER_INDUSTRY_REPAIR]


def plan_llm_usage_repair(columns: set[str], constraints: set[str]) -> list[str]:
    steps: list[str] = []
    if "usage_id" not in columns and "id" in columns:
        steps.append("ALTER TABLE llm_usage RENAME COLUMN id TO usage_id")
    if "model_name" not in columns and "model" in columns:
        steps.append("ALTER TABLE llm_usage RENAME COLUMN model TO model_name")
    steps.extend(sql for name, sql in _ADD_COLUMNS.items() if name not in columns)
    if "fk_llm_usage_user" in constraints:
        steps.append("ALTER TABLE llm_usage DROP CONSTRAINT fk_llm_usage_user")
    if "fk_llm_usage_user_id_auth_users" not in constraints:
        steps.append(
            "ALTER TABLE llm_usage ADD CONSTRAINT fk_llm_usage_user_id_auth_users "
            "FOREIGN KEY (user_id) REFERENCES auth_users (user_id) NOT VALID"
        )
    if "ck_llm_usage_execution_mode" not in constraints:
        steps.append(
            "ALTER TABLE llm_usage ADD CONSTRAINT ck_llm_usage_execution_mode "
            "CHECK (execution_mode IN ('SCHEMA', 'LLM', 'HYBRID', 'CACHE'))"
        )
    if steps:
        steps.append("ALTER TABLE llm_usage ALTER COLUMN purpose SET DEFAULT 'chat'")
        steps.append(
            "CREATE INDEX IF NOT EXISTS ix_llm_usage_user_created "
            "ON llm_usage (user_id, created_at)"
        )
        steps.append(
            "CREATE INDEX IF NOT EXISTS ix_llm_usage_mode_created "
            "ON llm_usage (execution_mode, created_at)"
        )
    return steps


async def repair_auth_user_industry_values(engine: AsyncEngine) -> list[str]:
    """Lowercase stale default_industry values that were migrated from uppercase strings."""
    if engine.dialect.name != "postgresql":
        return []
    try:
        async with engine.begin() as conn:
            result = await conn.execute(
                text(
                    "SELECT COUNT(*) FROM auth_users WHERE default_industry IS NOT NULL "
                    "AND default_industry <> LOWER(default_industry)"
                )
            )
            if result.scalar_one() == 0:
                return []
            await conn.execute(text(_AUTH_USER_INDUSTRY_REPAIR))
    except Exception:
        logger.warning("auth_users default_industry repair failed", exc_info=True)
        return []
    logger.info("auth_users default_industry repaired")
    return plan_auth_user_industry_repair()


async def repair_llm_usage(engine: AsyncEngine) -> list[str]:
    """Apply any missing steps; never raises, so startup is not blocked."""
    if engine.dialect.name != "postgresql":
        return []
    try:
        async with engine.begin() as conn:
            columns = {row[0] for row in await conn.execute(_COLUMNS)}
            if not columns:
                return []
            constraints = {row[0] for row in await conn.execute(_CONSTRAINTS)}
            steps = plan_llm_usage_repair(columns, constraints)
            for sql in steps:
                await conn.execute(text(sql))
    except Exception:
        logger.warning("llm_usage schema repair failed", exc_info=True)
        return []
    if steps:
        logger.info("llm_usage schema repaired", extra={"steps": len(steps)})
    return steps
