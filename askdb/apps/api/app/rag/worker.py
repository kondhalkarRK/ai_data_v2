"""Traditional RAG worker: in-process loop for POC, CLI for production.

Usage (production)::

    python -m app.rag.worker
"""

from __future__ import annotations

import asyncio
import logging
import os
import signal
import uuid
from typing import Any

from app.core.config import Settings, get_settings
from app.db.session import DatabaseRegistry
from app.rag.feature import rag_enabled
from app.rag.job_processor import claim_and_process_one

logger = logging.getLogger(__name__)


class RagWorker:
    def __init__(self, settings: Settings, registry: DatabaseRegistry) -> None:
        self.settings = settings
        self.registry = registry
        self.worker_id = f"{os.getenv('HOSTNAME', 'local')}-{uuid.uuid4().hex[:8]}"
        self._stop = asyncio.Event()
        self._task: asyncio.Task[None] | None = None
        self.processed = 0
        self.failures = 0

    def request_stop(self) -> None:
        self._stop.set()

    async def start_background(self) -> None:
        if self._task is not None and not self._task.done():
            return
        self._stop.clear()
        self._task = asyncio.create_task(self.run_forever(), name="rag-worker")

    async def stop(self) -> None:
        self.request_stop()
        if self._task is not None:
            try:
                await asyncio.wait_for(self._task, timeout=10)
            except (asyncio.TimeoutError, asyncio.CancelledError):
                self._task.cancel()
            self._task = None

    async def run_forever(self) -> None:
        logger.info("RAG worker started id=%s", self.worker_id)
        while not self._stop.is_set():
            if not rag_enabled(self.settings):
                await asyncio.sleep(self.settings.rag_worker_poll_seconds)
                continue
            try:
                result = await self.poll_once()
                if result is None:
                    await asyncio.sleep(self.settings.rag_worker_poll_seconds)
                elif result.get("status") == "failed":
                    self.failures += 1
                else:
                    self.processed += 1
            except asyncio.CancelledError:
                raise
            except Exception:
                self.failures += 1
                logger.exception("RAG worker poll failed")
                await asyncio.sleep(self.settings.rag_worker_poll_seconds)
        logger.info("RAG worker stopped id=%s", self.worker_id)

    async def poll_once(self) -> dict[str, Any] | None:
        async with self.registry.app_session() as session:
            return await claim_and_process_one(
                session, self.settings, worker_id=self.worker_id
            )

    def health(self) -> dict[str, Any]:
        return {
            "workerId": self.worker_id,
            "running": self._task is not None and not self._task.done(),
            "processed": self.processed,
            "failures": self.failures,
        }


async def _amain() -> None:
    logging.basicConfig(level=logging.INFO)
    settings = get_settings()
    if not rag_enabled(settings):
        logger.warning("ASK_ME_RAG_ENABLED is false; worker will idle until enabled.")
    registry = DatabaseRegistry(settings)
    await registry.start()
    worker = RagWorker(settings, registry)
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, worker.request_stop)
        except NotImplementedError:
            # Windows.
            pass
    try:
        await worker.run_forever()
    finally:
        await registry.stop()


def main() -> None:
    asyncio.run(_amain())


if __name__ == "__main__":
    main()
