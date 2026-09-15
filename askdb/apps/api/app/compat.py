"""Platform compatibility shims loaded before the ASGI app starts serving."""

from __future__ import annotations

import asyncio
import sys


def configure_event_loop() -> None:
    """psycopg async cannot use Windows ProactorEventLoop.

    Uvicorn on Windows defaults to Proactor; without this policy, the first real
    DB query fails with InterfaceError while /health still looks fine.
    """
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


configure_event_loop()
