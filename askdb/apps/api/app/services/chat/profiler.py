"""Rolling NLQ query profiler — last 100 executions + stage aggregates."""

from __future__ import annotations

import threading
import time
from collections import deque
from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class QueryProfile:
    question: str
    industry: str
    started_at: float
    ended_at: float | None = None
    duration_ms: int | None = None
    sql: str | None = None
    tables: list[str] = field(default_factory=list)
    llm_calls: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    row_count: int = 0
    error_category: str | None = None
    error_reason: str | None = None
    path: str | None = None
    timings: dict[str, int] = field(default_factory=dict)
    explain_plan: str | None = None
    cache_hit: bool = False
    history_id: str | None = None

    def finish(self) -> None:
        self.ended_at = time.time()
        if self.started_at:
            self.duration_ms = int((self.ended_at - self.started_at) * 1000)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class QueryProfiler:
    """Process-local ring buffer (POC). Production should export to a metrics store."""

    def __init__(self, capacity: int = 100) -> None:
        self._capacity = capacity
        self._lock = threading.Lock()
        self._items: deque[QueryProfile] = deque(maxlen=capacity)

    def record(self, profile: QueryProfile) -> None:
        profile.finish()
        with self._lock:
            self._items.appendleft(profile)

    def recent(self, limit: int = 50) -> list[dict[str, Any]]:
        with self._lock:
            return [item.to_dict() for item in list(self._items)[:limit]]

    def stage_percentiles(self) -> dict[str, dict[str, float]]:
        """p50/p95/p99 per timing key across the ring buffer."""
        with self._lock:
            buckets: dict[str, list[float]] = {}
            for item in self._items:
                for key, value in (item.timings or {}).items():
                    buckets.setdefault(key, []).append(float(value))
                if item.duration_ms is not None:
                    buckets.setdefault("totalMs", []).append(float(item.duration_ms))
        out: dict[str, dict[str, float]] = {}
        for key, values in buckets.items():
            if not values:
                continue
            values = sorted(values)
            out[key] = {
                "count": float(len(values)),
                "p50": _percentile(values, 50),
                "p95": _percentile(values, 95),
                "p99": _percentile(values, 99),
            }
        return out

    def error_rates(self) -> dict[str, int]:
        with self._lock:
            counts: dict[str, int] = {"ok": 0}
            for item in self._items:
                if item.error_category:
                    counts[item.error_category] = counts.get(item.error_category, 0) + 1
                else:
                    counts["ok"] += 1
            return counts


def _percentile(sorted_values: list[float], pct: float) -> float:
    if not sorted_values:
        return 0.0
    if len(sorted_values) == 1:
        return sorted_values[0]
    rank = (pct / 100.0) * (len(sorted_values) - 1)
    low = int(rank)
    high = min(low + 1, len(sorted_values) - 1)
    frac = rank - low
    return round(sorted_values[low] * (1 - frac) + sorted_values[high] * frac, 1)


PROFILER = QueryProfiler(capacity=100)
