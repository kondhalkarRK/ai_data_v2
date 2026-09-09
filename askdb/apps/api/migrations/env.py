"""Alembic environment.

Targets are selected with ``-x target=<name>``:

- ``app`` → ``askdb_app`` (ORM models under ``app.models``)
- ``automotive`` → ``askdb_automotive`` (SQL migrations, no ORM metadata)
- ``insurance`` → ``askdb_insurance`` (SQL migrations, no ORM metadata)
"""

from __future__ import annotations

import asyncio
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from app.core.config import Industry, get_settings
from app.models import Base

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

MIGRATIONS_ROOT = Path(__file__).resolve().parent


def _target_name() -> str:
    return context.get_x_argument(as_dictionary=True).get("target", "app")


def _version_locations() -> list[str]:
    target = _target_name()
    if target == "app":
        return [str(MIGRATIONS_ROOT / "versions")]
    if target in {member.value for member in Industry}:
        return [str(MIGRATIONS_ROOT / target / "versions")]
    valid = ", ".join(["app", *[member.value for member in Industry]])
    raise SystemExit(f"Unknown -x target={target!r}. Expected one of: {valid}.")


def _database_url() -> str:
    """Resolve the URL from settings, never from alembic.ini."""
    settings = get_settings()
    target = _target_name()
    if target == "app":
        return settings.app_database_url
    try:
        # Analytics DDL/seed must use the owner role, not the SELECT-only reader.
        return settings.analytics_migrate_database_url(Industry(target))
    except ValueError as exc:
        valid = ", ".join(["app", *[member.value for member in Industry]])
        raise SystemExit(f"Unknown -x target={target!r}. Expected one of: {valid}.") from exc


def _target_metadata():
    # Analytics trees are pure SQL and must not try to diff against the app ORM.
    return Base.metadata if _target_name() == "app" else None


def run_migrations_offline() -> None:
    context.configure(
        url=_database_url(),
        target_metadata=_target_metadata(),
        version_locations=_version_locations(),
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        compare_server_default=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=_target_metadata(),
        version_locations=_version_locations(),
        compare_type=True,
        compare_server_default=True,
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    configuration = config.get_section(config.config_ini_section, {})
    configuration["sqlalchemy.url"] = _database_url()

    engine = async_engine_from_config(configuration, prefix="sqlalchemy.", poolclass=pool.NullPool)
    async with engine.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await engine.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
