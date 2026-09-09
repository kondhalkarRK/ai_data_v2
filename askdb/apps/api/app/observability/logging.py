"""Structured logging.

Carries over the intent of the legacy ``utils/logger.py`` (query, error and performance
channels, plus a per-query tracker) without the Streamlit-rerun handling. Records are
emitted as single-line JSON so a log shipper can parse them, and every record passes
through the redaction filter.
"""

from __future__ import annotations

import json
import logging
import logging.config
import sys
import time
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Any

from app.core.context import current_request_id
from app.observability.redaction import redact, redact_text

_RESERVED = frozenset(
    logging.LogRecord("", 0, "", 0, "", None, None).__dict__.keys()
    | {"message", "asctime", "taskName"}
)


class RedactionFilter(logging.Filter):
    """Redacts the formatted message and any structured extras."""

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            record.msg = redact_text(record.msg)
        if record.args:
            if isinstance(record.args, dict):
                record.args = redact(record.args)
            else:
                record.args = tuple(redact(arg) for arg in record.args)
        return True


class RequestContextFilter(logging.Filter):
    """Stamps every record with the current request id."""

    def filter(self, record: logging.LogRecord) -> bool:
        if not hasattr(record, "request_id"):
            record.request_id = current_request_id()
        return True


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "request_id": getattr(record, "request_id", "-"),
        }

        extras = {
            key: value
            for key, value in record.__dict__.items()
            if key not in _RESERVED and not key.startswith("_")
        }
        if extras:
            payload["context"] = redact(extras)

        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)

        return json.dumps(payload, default=str, ensure_ascii=False)


def configure_logging(level: str = "INFO", *, json_output: bool = True) -> None:
    handler = logging.StreamHandler(stream=sys.stdout)
    handler.setFormatter(
        JsonFormatter()
        if json_output
        else logging.Formatter(
            "%(asctime)s %(levelname)-7s [%(request_id)s] %(name)s: %(message)s"
        )
    )
    handler.addFilter(RequestContextFilter())
    handler.addFilter(RedactionFilter())

    root = logging.getLogger()
    # Replace rather than append, so repeated calls (reload, tests) do not duplicate output.
    for existing in list(root.handlers):
        root.removeHandler(existing)
    root.addHandler(handler)
    root.setLevel(level)

    # Uvicorn installs its own handlers; route them through ours instead.
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        uvicorn_logger = logging.getLogger(name)
        uvicorn_logger.handlers = []
        uvicorn_logger.propagate = True

    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)


# ---------------------------------------------------------------------------
# Per-request execution tracking (port of utils/logger.QueryExecutionTracker)
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class StageTiming:
    name: str
    duration_ms: int
    ok: bool = True


@dataclass(slots=True)
class ExecutionTracker:
    """Accumulates timing and counters for one logical operation."""

    operation: str
    started_at: float = field(default_factory=time.perf_counter)
    stages: list[StageTiming] = field(default_factory=list)
    api_calls: int = 0
    db_calls: int = 0
    rows: int = 0
    succeeded: bool | None = None
    error: str | None = None

    def record_stage(self, name: str, duration_ms: int, *, ok: bool = True) -> None:
        self.stages.append(StageTiming(name=name, duration_ms=duration_ms, ok=ok))

    def note_api_call(self, count: int = 1) -> None:
        self.api_calls += count

    def note_db_call(self, count: int = 1) -> None:
        self.db_calls += count

    @property
    def elapsed_ms(self) -> int:
        return int((time.perf_counter() - self.started_at) * 1000)

    def summary(self) -> dict[str, Any]:
        return {
            "operation": self.operation,
            "total_ms": self.elapsed_ms,
            "api_calls": self.api_calls,
            "db_calls": self.db_calls,
            "rows": self.rows,
            "succeeded": self.succeeded,
            "error": self.error,
            "stages": [
                {"name": stage.name, "ms": stage.duration_ms, "ok": stage.ok}
                for stage in self.stages
            ],
        }


_tracker: ContextVar[ExecutionTracker | None] = ContextVar("nql_tracker", default=None)


def get_tracker() -> ExecutionTracker | None:
    return _tracker.get()


@contextmanager
def track_execution(operation: str) -> Iterator[ExecutionTracker]:
    tracker = ExecutionTracker(operation=operation)
    token = _tracker.set(tracker)
    logger = logging.getLogger("nql.performance")
    try:
        yield tracker
        if tracker.succeeded is None:
            tracker.succeeded = True
    except Exception as exc:
        tracker.succeeded = False
        tracker.error = f"{type(exc).__name__}: {exc}"
        raise
    finally:
        _tracker.reset(token)
        logger.info("execution finished", extra=tracker.summary())


@contextmanager
def performance_stage(name: str) -> Iterator[None]:
    """Time a named stage and attach it to the active tracker."""
    started = time.perf_counter()
    ok = True
    try:
        yield
    except Exception:
        ok = False
        raise
    finally:
        tracker = _tracker.get()
        if tracker is not None:
            tracker.record_stage(name, int((time.perf_counter() - started) * 1000), ok=ok)
