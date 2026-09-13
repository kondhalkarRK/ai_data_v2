"""NLQ result cache keyed by question + industry, invalidated by data freshness."""

from __future__ import annotations

import hashlib
import re
import threading
import time
from dataclasses import dataclass
from typing import Any


def normalize_question(question: str) -> str:
    q = re.sub(r"\s+", " ", (question or "").strip().lower())
    return q.strip(" ?!.")


@dataclass
class CachedAnswer:
    sql: str | None
    columns: list[str]
    rows: list[dict[str, Any]]
    chart: dict[str, Any] | None
    meta: dict[str, Any]
    narrative: str
    followups: list[str]
    path: str
    data_as_of: str | None
    created_at: float
    tables: list[str]


class QueryResultCache:
    def __init__(self, *, ttl_seconds: float = 300, max_entries: int = 200) -> None:
        self._ttl = ttl_seconds
        self._max = max_entries
        self._lock = threading.Lock()
        self._store: dict[str, CachedAnswer] = {}

    def _key(self, industry: str, question: str) -> str:
        raw = f"{industry}|{normalize_question(question)}"
        return hashlib.sha256(raw.encode()).hexdigest()

    def get(
        self,
        *,
        industry: str,
        question: str,
        current_data_as_of: str | None,
    ) -> CachedAnswer | None:
        key = self._key(industry, question)
        with self._lock:
            hit = self._store.get(key)
            if hit is None:
                return None
            if time.time() - hit.created_at > self._ttl:
                self._store.pop(key, None)
                return None
            # Freshness-tied invalidation (Data Trust / data-as-of), not TTL alone.
            if current_data_as_of and hit.data_as_of and current_data_as_of != hit.data_as_of:
                self._store.pop(key, None)
                return None
            return hit

    def put(self, *, industry: str, question: str, answer: CachedAnswer) -> None:
        key = self._key(industry, question)
        with self._lock:
            if len(self._store) >= self._max and key not in self._store:
                # Drop oldest
                oldest = min(self._store.items(), key=lambda item: item[1].created_at)
                self._store.pop(oldest[0], None)
            self._store[key] = answer

    def stats(self) -> dict[str, int]:
        with self._lock:
            return {"entries": len(self._store), "max": self._max}


QUERY_CACHE = QueryResultCache()
