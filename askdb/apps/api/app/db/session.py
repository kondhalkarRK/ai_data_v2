"""Async engine and session management.

Three separate engines: one read/write engine for the application database, and one
read-only engine per analytics industry. Engines are created during application startup
and disposed on shutdown, which is the replacement for the legacy ``@st.cache_resource``
decorated backend factory.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy import event, text
from sqlalchemy.engine import Engine
from sqlalchemy.ext.asyncio import (
    AsyncConnection,
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import Industry, Settings
from app.core.exceptions import DependencyUnavailableError

logger = logging.getLogger(__name__)


class DatabaseRegistry:
    """Owns every database engine for the process lifetime."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._app_engine: AsyncEngine | None = None
        self._app_sessionmaker: async_sessionmaker[AsyncSession] | None = None
        self._analytics_engines: dict[Industry, AsyncEngine] = {}

    # --- lifecycle ---------------------------------------------------------

    async def start(self) -> None:
        settings = self._settings

        self._app_engine = create_async_engine(
            settings.app_database_url,
            pool_size=settings.db_pool_max_size,
            max_overflow=0,
            pool_pre_ping=True,
            pool_recycle=1800,
            connect_args={"connect_timeout": settings.db_connect_timeout_seconds},
            echo=False,
        )
        self._app_sessionmaker = async_sessionmaker(
            self._app_engine, expire_on_commit=False, autoflush=False
        )

        for industry in Industry:
            engine = create_async_engine(
                settings.analytics_database_url(industry),
                pool_size=settings.db_pool_max_size,
                max_overflow=0,
                pool_pre_ping=True,
                pool_recycle=1800,
                connect_args={
                    "connect_timeout": settings.db_connect_timeout_seconds,
                    # Applied to every connection in this pool, so no analytics query can
                    # outlive the timeout even if a caller forgets to set it.
                    "options": (
                        f"-c statement_timeout={settings.sql_statement_timeout_seconds * 1000}"
                        " -c default_transaction_read_only=on"
                        " -c idle_in_transaction_session_timeout=60000"
                    ),
                },
                echo=False,
            )
            _register_readonly_guard(engine.sync_engine)
            self._analytics_engines[industry] = engine

        logger.info(
            "database registry started",
            extra={"industries": [industry.value for industry in Industry]},
        )

    async def stop(self) -> None:
        if self._app_engine is not None:
            await self._app_engine.dispose()
            self._app_engine = None
            self._app_sessionmaker = None
        for engine in self._analytics_engines.values():
            await engine.dispose()
        self._analytics_engines.clear()
        logger.info("database registry stopped")

    # --- accessors ---------------------------------------------------------

    @property
    def app_engine(self) -> AsyncEngine:
        if self._app_engine is None:
            raise DependencyUnavailableError("The application database is not initialised.")
        return self._app_engine

    def analytics_engine(self, industry: Industry) -> AsyncEngine:
        engine = self._analytics_engines.get(industry)
        if engine is None:
            raise DependencyUnavailableError(
                f"No analytics engine configured for industry '{industry.value}'."
            )
        return engine

    @asynccontextmanager
    async def app_session(self) -> AsyncIterator[AsyncSession]:
        """Read/write session against ``askdb_app``, committed on clean exit."""
        if self._app_sessionmaker is None:
            raise DependencyUnavailableError("The application database is not initialised.")
        session = self._app_sessionmaker()
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()

    @asynccontextmanager
    async def analytics_connection(self, industry: Industry) -> AsyncIterator[AsyncConnection]:
        """Read-only analytics connection.

        The transaction is explicitly marked read only in addition to the pool-level
        ``default_transaction_read_only``, so a misconfigured DSN still cannot write.
        """
        engine = self.analytics_engine(industry)
        async with engine.connect() as connection:
            await connection.execute(text("SET TRANSACTION READ ONLY"))
            yield connection
            # No commit: the connection is read only and is returned to the pool.
            await connection.rollback()

    # --- health ------------------------------------------------------------

    async def check_app_database(self) -> tuple[bool, str]:
        try:
            async with self.app_engine.connect() as connection:
                await connection.execute(text("SELECT 1"))
        except Exception as exc:
            logger.warning("app database health check failed: %s", exc)
            return False, type(exc).__name__
        return True, "ok"

    async def check_analytics_database(self, industry: Industry) -> tuple[bool, str]:
        try:
            async with self.analytics_connection(industry) as connection:
                await connection.execute(text("SELECT 1"))
        except Exception as exc:
            logger.warning(
                "analytics database health check failed for %s: %s", industry.value, exc
            )
            return False, type(exc).__name__
        return True, "ok"


def _register_readonly_guard(sync_engine: Engine) -> None:
    """Belt-and-braces protection against writes on an analytics pool.

    The DSN role should already be SELECT-only and the transaction is read only. This
    listener adds a third, application-level check so a mistake in any one layer is not
    sufficient to mutate analytics data.
    """

    forbidden = (
        "insert",
        "update",
        "delete",
        "drop",
        "truncate",
        "alter",
        "create",
        "grant",
        "revoke",
        "copy",
        "vacuum",
        "call",
        "do",
    )

    @event.listens_for(sync_engine, "before_cursor_execute")
    def _reject_writes(  # type: ignore[no-untyped-def]
        conn, cursor, statement, parameters, context, executemany
    ) -> None:
        head = statement.lstrip().lower()
        # Allow the session-configuration statements the pool itself issues.
        if head.startswith(("set ", "show ", "begin", "commit", "rollback")):
            return
        if head.startswith(forbidden):
            raise PermissionError(
                "Write statement rejected on a read-only analytics connection."
            )
