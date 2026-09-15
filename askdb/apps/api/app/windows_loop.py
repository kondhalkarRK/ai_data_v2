"""Uvicorn loop factory: force SelectorEventLoop on Windows for psycopg.

Uvicorn 0.36+ ignores asyncio policies on Windows and hard-codes ProactorEventLoop
(see uvicorn.loops.asyncio.asyncio_loop_factory). Pass this module to uvicorn via
``loop=\"app.windows_loop:selector_event_loop\"``.
"""

from __future__ import annotations

import asyncio
import selectors


def selector_event_loop() -> asyncio.AbstractEventLoop:
    return asyncio.SelectorEventLoop(selectors.SelectSelector())
