"""Fixed-window rate limiting.

In-process and therefore per-replica: with N API replicas the effective limit is N times
the configured value. That is acceptable for the login-throttling and abuse-damping goals
here, and the interface is deliberately narrow so a Redis-backed implementation can be
substituted without touching callers.
"""

from __future__ import annotations

import asyncio
import time
from collections import OrderedDict
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class RateLimitDecision:
    allowed: bool
    remaining: int
    retry_after_seconds: int


class FixedWindowRateLimiter:
    def __init__(self, *, limit: int, window_seconds: int = 60, max_keys: int = 20_000) -> None:
        if limit < 1:
            raise ValueError("limit must be at least 1")
        self._limit = limit
        self._window = window_seconds
        self._max_keys = max_keys
        # key -> (window_started_at, count)
        self._buckets: OrderedDict[str, tuple[float, int]] = OrderedDict()
        self._lock = asyncio.Lock()

    async def check(self, key: str) -> RateLimitDecision:
        """Consume one unit of quota for ``key``."""
        now = time.monotonic()
        async with self._lock:
            window_start, count = self._buckets.get(key, (now, 0))

            if now - window_start >= self._window:
                window_start, count = now, 0

            elapsed = now - window_start
            retry_after = max(1, int(self._window - elapsed))

            if count >= self._limit:
                self._buckets[key] = (window_start, count)
                self._buckets.move_to_end(key)
                return RateLimitDecision(
                    allowed=False, remaining=0, retry_after_seconds=retry_after
                )

            count += 1
            self._buckets[key] = (window_start, count)
            self._buckets.move_to_end(key)
            while len(self._buckets) > self._max_keys:
                self._buckets.popitem(last=False)

            return RateLimitDecision(
                allowed=True,
                remaining=self._limit - count,
                retry_after_seconds=retry_after,
            )

    async def reset(self, key: str) -> None:
        """Clear a key's quota, called after a successful login."""
        async with self._lock:
            self._buckets.pop(key, None)


def client_ip(forwarded_for: str | None, direct_host: str | None) -> str:
    """Best-effort client address.

    Only trust ``X-Forwarded-For`` when the API sits behind a proxy that sets it, which is
    why Uvicorn runs with ``--proxy-headers`` and an explicit trusted-proxy list in
    deployment.
    """
    if forwarded_for:
        first = forwarded_for.split(",")[0].strip()
        if first:
            return first
    return direct_host or "unknown"
