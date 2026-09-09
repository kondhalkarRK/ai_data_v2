"""Application-level TTL caching.

Replaces ``@st.cache_data`` from the legacy app. Streamlit's cache was keyed implicitly by
function arguments and scoped to a server process with no eviction policy; this one is
explicit about its key, its TTL and its size bound, and it is safe to use from async code.
"""

from __future__ import annotations

import asyncio
import time
from collections import OrderedDict
from collections.abc import Awaitable, Callable, Hashable
from dataclasses import dataclass
from typing import Generic, TypeVar

T = TypeVar("T")


@dataclass(slots=True)
class _Entry(Generic[T]):
    value: T
    expires_at: float


class TTLCache(Generic[T]):
    """A bounded, least-recently-used cache with per-entry expiry.

    Not shared between processes. Anything that must survive a restart or be consistent
    across replicas belongs in PostgreSQL, not here.
    """

    def __init__(self, *, ttl_seconds: float, max_entries: int = 512) -> None:
        if ttl_seconds <= 0:
            raise ValueError("ttl_seconds must be positive")
        if max_entries <= 0:
            raise ValueError("max_entries must be positive")
        self._ttl = ttl_seconds
        self._max_entries = max_entries
        self._entries: OrderedDict[Hashable, _Entry[T]] = OrderedDict()
        self._lock = asyncio.Lock()
        self.hits = 0
        self.misses = 0

    def _evict_if_needed(self) -> None:
        while len(self._entries) > self._max_entries:
            self._entries.popitem(last=False)

    def get(self, key: Hashable) -> T | None:
        entry = self._entries.get(key)
        if entry is None:
            self.misses += 1
            return None
        if entry.expires_at <= time.monotonic():
            del self._entries[key]
            self.misses += 1
            return None
        self._entries.move_to_end(key)
        self.hits += 1
        return entry.value

    def set(self, key: Hashable, value: T) -> None:
        self._entries[key] = _Entry(value=value, expires_at=time.monotonic() + self._ttl)
        self._entries.move_to_end(key)
        self._evict_if_needed()

    def invalidate(self, key: Hashable) -> None:
        self._entries.pop(key, None)

    def clear(self) -> None:
        self._entries.clear()

    async def get_or_set(self, key: Hashable, factory: Callable[[], Awaitable[T]]) -> T:
        """Return the cached value, computing it at most once per key.

        The lock makes concurrent misses for the same key wait for a single computation
        instead of stampeding the database or the model provider.
        """
        cached = self.get(key)
        if cached is not None:
            return cached
        async with self._lock:
            cached = self.get(key)
            if cached is not None:
                return cached
            value = await factory()
            self.set(key, value)
            return value

    @property
    def stats(self) -> dict[str, int | float]:
        total = self.hits + self.misses
        return {
            "entries": len(self._entries),
            "hits": self.hits,
            "misses": self.misses,
            "hit_rate": round(self.hits / total, 4) if total else 0.0,
        }
