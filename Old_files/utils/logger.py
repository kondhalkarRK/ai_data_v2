"""
utils/logger.py

Centralized production logging for ASK-DB query / performance / error analysis.

Daily rotating files under:
  logs/query_logs/query_YYYY_MM_DD.log
  logs/error_logs/error_YYYY_MM_DD.log
  logs/performance_logs/performance_YYYY_MM_DD.log

# TEMP_DISABLED_FOR_PERFORMANCE_ANALYSIS
# This module replaces inaccurate MLflow timelines while MLflow persistence is off.
"""
from __future__ import annotations

import logging
import os
import traceback
import uuid
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from datetime import datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any, Iterator, Optional

# ── Paths ──────────────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parent.parent
LOGS_ROOT = PROJECT_ROOT / "logs"
QUERY_LOG_DIR = LOGS_ROOT / "query_logs"
ERROR_LOG_DIR = LOGS_ROOT / "error_logs"
PERF_LOG_DIR = LOGS_ROOT / "performance_logs"

_MAX_BYTES = 10 * 1024 * 1024  # 10 MB
_BACKUP_COUNT = 30

_INITIALIZED = False

# Active query tracker for nested API/DB call counting
_CURRENT_TRACKER: ContextVar[Optional["QueryExecutionTracker"]] = ContextVar(
    "askdb_query_tracker", default=None
)


def ensure_log_dirs() -> None:
    """Create log folder tree if missing."""
    for path in (QUERY_LOG_DIR, ERROR_LOG_DIR, PERF_LOG_DIR):
        path.mkdir(parents=True, exist_ok=True)


def _daily_path(directory: Path, prefix: str) -> Path:
    stamp = datetime.now().strftime("%Y_%m_%d")
    return directory / f"{prefix}_{stamp}.log"


def _build_rotating_logger(
    name: str,
    directory: Path,
    prefix: str,
    level: int = logging.INFO,
) -> logging.Logger:
    ensure_log_dirs()
    logger = logging.getLogger(name)
    logger.setLevel(level)
    logger.propagate = False

    # Avoid duplicate handlers on Streamlit reruns / reloads
    target = str(_daily_path(directory, prefix).resolve())
    for handler in list(logger.handlers):
        if getattr(handler, "baseFilename", None) == target:
            return logger
        # Drop stale day handlers when the calendar day rolls over
        if isinstance(handler, RotatingFileHandler):
            logger.removeHandler(handler)
            try:
                handler.close()
            except Exception:
                pass

    handler = RotatingFileHandler(
        filename=str(_daily_path(directory, prefix)),
        maxBytes=_MAX_BYTES,
        backupCount=_BACKUP_COUNT,
        encoding="utf-8",
    )
    handler.setLevel(level)
    handler.setFormatter(
        logging.Formatter(
            fmt="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
    )
    logger.addHandler(handler)
    return logger


def get_query_logger() -> logging.Logger:
    return _build_rotating_logger("askdb.query", QUERY_LOG_DIR, "query")


def get_error_logger() -> logging.Logger:
    return _build_rotating_logger("askdb.error", ERROR_LOG_DIR, "error", level=logging.ERROR)


def get_performance_logger() -> logging.Logger:
    return _build_rotating_logger("askdb.performance", PERF_LOG_DIR, "performance")


def get_logger(name: str = "askdb") -> logging.Logger:
    """
    General-purpose named logger (INFO+) writing to performance daily log
    so ad-hoc debug lines stay in one place during analysis.
    """
    ensure_log_dirs()
    logger = logging.getLogger(name)
    if not logger.handlers:
        # Attach to performance file for general diagnostics
        base = get_performance_logger()
        for handler in base.handlers:
            logger.addHandler(handler)
        logger.setLevel(logging.DEBUG)
        logger.propagate = False
    return logger


def init_logging() -> None:
    """Idempotent bootstrap — call once at app start."""
    global _INITIALIZED
    ensure_log_dirs()
    get_query_logger()
    get_error_logger()
    get_performance_logger()
    if not _INITIALIZED:
        get_performance_logger().info(
            "ASK-DB logging framework initialized "
            "(MLflow persistence TEMP_DISABLED_FOR_PERFORMANCE_ANALYSIS)."
        )
        _INITIALIZED = True


def log_error(
    *,
    message: str,
    query_id: str | None = None,
    question: str | None = None,
    module_name: str | None = None,
    function_name: str | None = None,
    exc: BaseException | None = None,
) -> None:
    """Write a structured error block with optional stack trace."""
    init_logging()
    logger = get_error_logger()
    stack = ""
    if exc is not None:
        stack = "".join(
            traceback.format_exception(type(exc), exc, exc.__traceback__)
        )
    elif traceback.format_exc() and traceback.format_exc() != "NoneType: None\n":
        stack = traceback.format_exc()

    block = (
        "\n====================================================\n"
        f"Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
        f"Query ID: {query_id or 'n/a'}\n"
        f"Module: {module_name or 'n/a'}\n"
        f"Function: {function_name or 'n/a'}\n"
        f"Question: {(question or '')[:400]}\n"
        f"Message: {message}\n"
        f"Stack Trace:\n{stack or '(none)'}\n"
        "===================================================="
    )
    logger.error(block)


@dataclass
class QueryExecutionTracker:
    """
    Tracks one user NLQ end-to-end: timings, API/DB call counts, rows, status.
    Use via `track_query_execution(question)` context manager.
    """

    question: str
    query_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    start_time: datetime = field(default_factory=datetime.now)
    end_time: datetime | None = None
    api_calls: int = 0
    db_calls: int = 0
    rows_returned: int = 0
    status: str = "RUNNING"
    error_message: str = ""
    stages: dict[str, float] = field(default_factory=dict)
    _t0: float = field(default_factory=lambda: __import__("time").perf_counter())
    _elapsed: float | None = None
    _closed: bool = False

    def record_api_call(self, duration_sec: float | None = None) -> None:
        self.api_calls += 1
        if duration_sec is not None:
            self.stages["LLM Processing"] = (
                self.stages.get("LLM Processing", 0.0) + float(duration_sec)
            )

    def record_db_call(
        self, duration_sec: float | None = None, rows: int | None = None
    ) -> None:
        self.db_calls += 1
        if duration_sec is not None:
            self.stages["Database Execution"] = (
                self.stages.get("Database Execution", 0.0) + float(duration_sec)
            )
        if rows is not None:
            self.rows_returned = int(rows)

    def record_stage(self, name: str, duration_sec: float) -> None:
        self.stages[name] = self.stages.get(name, 0.0) + float(duration_sec)

    def set_rows(self, rows: int) -> None:
        self.rows_returned = int(rows)

    def mark_success(self, rows: int | None = None) -> None:
        if rows is not None:
            self.rows_returned = int(rows)
        self.status = "SUCCESS"
        self._finalize()

    def mark_failure(self, error: str | BaseException) -> None:
        self.status = "FAILURE"
        self.error_message = str(error)[:800]
        self._finalize()

    def execution_seconds(self) -> float:
        import time

        if self._elapsed is not None:
            return max(0.0, self._elapsed)
        return max(0.0, time.perf_counter() - self._t0)

    def _finalize(self) -> None:
        if self._closed:
            return
        import time

        self._closed = True
        self._elapsed = time.perf_counter() - self._t0
        self.end_time = datetime.now()
        self._write_query_log()
        self._write_performance_log()
        if self.status == "FAILURE":
            log_error(
                message=self.error_message or "Query failed",
                query_id=self.query_id,
                question=self.question,
                module_name="utils.logger",
                function_name="QueryExecutionTracker._finalize",
            )

    def _write_query_log(self) -> None:
        init_logging()
        start_s = self.start_time.strftime("%Y-%m-%d %H:%M:%S")
        end_s = (self.end_time or datetime.now()).strftime("%Y-%m-%d %H:%M:%S")
        exec_s = self.execution_seconds()
        block = (
            "\n====================================================\n"
            f"Query ID: {self.query_id}\n"
            f"Question: {self.question[:500]}\n"
            f"Start Time: {start_s}\n"
            f"End Time: {end_s}\n"
            f"Execution Time: {exec_s:.2f} sec\n"
            f"API Calls: {self.api_calls}\n"
            f"Database Calls: {self.db_calls}\n"
            f"Rows Returned: {self.rows_returned}\n"
            f"Status: {self.status}\n"
            + (
                f"Error Message: {self.error_message}\n"
                if self.error_message
                else ""
            )
            + "===================================================="
        )
        get_query_logger().info(block)

    def _write_performance_log(self) -> None:
        init_logging()
        lines = [
            f"Query ID: {self.query_id}",
            f"Question: {self.question[:200]}",
        ]
        # Stable stage order for readability
        preferred = [
            "User Request Processing",
            "SQL Generation",
            "LLM Processing",
            "Database Execution",
            "Data Transformation",
            "Visualization Generation",
            "Response Formatting",
            "Insight / Narration",
        ]
        seen: set[str] = set()
        for name in preferred:
            if name in self.stages:
                lines.append(f"{name}: {self.stages[name]:.2f} sec")
                seen.add(name)
        for name, secs in self.stages.items():
            if name not in seen:
                lines.append(f"{name}: {secs:.2f} sec")
        lines.append(f"Total Request Time: {self.execution_seconds():.2f} sec")
        lines.append(f"Status: {self.status}")
        get_performance_logger().info("\n".join(lines) + "\n---")


def get_current_tracker() -> QueryExecutionTracker | None:
    return _CURRENT_TRACKER.get()


@contextmanager
def track_query_execution(question: str) -> Iterator[QueryExecutionTracker]:
    """
    Context manager for one user question.

    Usage:
        with track_query_execution(question) as tracker:
            ...
            tracker.mark_success(rows=len(df))
    """
    init_logging()
    tracker = QueryExecutionTracker(question=question or "")
    token = _CURRENT_TRACKER.set(tracker)
    get_performance_logger().info(
        f"START query_id={tracker.query_id} question={(question or '')[:120]}"
    )
    try:
        yield tracker
        if not tracker._closed:
            tracker.mark_success()
    except Exception as exc:
        if not tracker._closed:
            tracker.mark_failure(exc)
        raise
    finally:
        _CURRENT_TRACKER.reset(token)


def begin_query_tracking(question: str) -> QueryExecutionTracker:
    """
    Explicit start for Streamlit flows with many early returns.
    Pair with end_query_tracking().
    """
    init_logging()
    tracker = QueryExecutionTracker(question=question or "")
    tracker._ctx_token = _CURRENT_TRACKER.set(tracker)  # type: ignore[attr-defined]
    get_performance_logger().info(
        f"START query_id={tracker.query_id} question={(question or '')[:120]}"
    )
    return tracker


def end_query_tracking(
    tracker: QueryExecutionTracker | None,
    *,
    success: bool = True,
    rows: int | None = None,
    error: str | BaseException | None = None,
) -> None:
    """Close an explicitly started tracker (safe to call multiple times)."""
    if tracker is None:
        return
    try:
        if not tracker._closed:
            if success:
                tracker.mark_success(rows=rows)
            else:
                tracker.mark_failure(error or "Query failed")
    finally:
        token = getattr(tracker, "_ctx_token", None)
        if token is not None:
            try:
                _CURRENT_TRACKER.reset(token)
            except Exception:
                pass
            try:
                delattr(tracker, "_ctx_token")
            except Exception:
                pass


@contextmanager
def performance_stage(name: str) -> Iterator[None]:
    """Record wall time for a named pipeline stage onto the active tracker."""
    import time

    t0 = time.perf_counter()
    try:
        yield
    finally:
        elapsed = time.perf_counter() - t0
        tracker = get_current_tracker()
        if tracker is not None:
            tracker.record_stage(name, elapsed)
        else:
            init_logging()
            get_performance_logger().info(f"{name}: {elapsed:.2f} sec")


def note_api_call(duration_sec: float | None = None) -> None:
    """Increment API-call counter on the active tracker (stage ms come from spans)."""
    tracker = get_current_tracker()
    if tracker is not None:
        tracker.api_calls += 1
        # Optional: only record duration when no span mirroring is active
        if duration_sec is not None and "LLM Processing" not in tracker.stages:
            tracker.stages["LLM Processing"] = float(duration_sec)


def note_db_call(duration_sec: float | None = None, rows: int | None = None) -> None:
    """Increment DB-call counter; optionally set row count from the latest execute."""
    tracker = get_current_tracker()
    if tracker is not None:
        tracker.db_calls += 1
        if duration_sec is not None and "Database Execution" not in tracker.stages:
            tracker.stages["Database Execution"] = float(duration_sec)
        if rows is not None:
            tracker.rows_returned = int(rows)
