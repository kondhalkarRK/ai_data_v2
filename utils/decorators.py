"""
utils/decorators.py

Reusable decorators for ASK-DB performance / query / error logging.
Designed for minimal invasive wrapping of existing functions.
"""
from __future__ import annotations

import functools
from typing import Any, Callable, TypeVar, cast

from utils.logger import (
    get_current_tracker,
    init_logging,
    log_error,
    performance_stage,
)

F = TypeVar("F", bound=Callable[..., Any])


def log_execution_time(stage_name: str | None = None) -> Callable[[F], F]:
    """
    Measure wall-clock duration of a function and write to performance logs.
    Also attaches the stage to the active QueryExecutionTracker when present.
    """

    def decorator(func: F) -> F:
        name = stage_name or f"{func.__module__}.{func.__qualname__}"

        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            init_logging()
            with performance_stage(name):
                return func(*args, **kwargs)

        return cast(F, wrapper)

    return decorator


def log_query_execution(func: F) -> F:
    """
    Wrap a function that takes a user question (first str arg or `question=`).
    Opens a QueryExecutionTracker for the call duration.
    Prefer using `track_query_execution` explicitly in chat orchestration;
    this decorator is for standalone entry points.
    """

    @functools.wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        from utils.logger import track_query_execution

        question = kwargs.get("question")
        if question is None and args:
            # Heuristic: first string-like positional after self/cls
            for arg in args:
                if isinstance(arg, str) and len(arg.strip()) > 0:
                    question = arg
                    break
        question = question or "(unknown question)"

        # Nested calls reuse the outer tracker
        if get_current_tracker() is not None:
            return func(*args, **kwargs)

        with track_query_execution(str(question)) as tracker:
            try:
                result = func(*args, **kwargs)
                # Best-effort row detection for DataFrame / tuple results
                rows = _infer_rows(result)
                if rows is not None:
                    tracker.set_rows(rows)
                if not tracker._closed:
                    tracker.mark_success(rows=rows)
                return result
            except Exception as exc:
                if not tracker._closed:
                    tracker.mark_failure(exc)
                raise

    return cast(F, wrapper)


def log_errors(func: F) -> F:
    """Log exceptions with module/function/stack; re-raise unchanged."""

    @functools.wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        try:
            return func(*args, **kwargs)
        except Exception as exc:
            tracker = get_current_tracker()
            question = None
            if tracker is not None:
                question = tracker.question
            else:
                question = kwargs.get("question")
                if question is None:
                    for arg in args:
                        if isinstance(arg, str) and "?" not in arg[:1]:
                            # Prefer longer question-like strings
                            if len(arg) > 8:
                                question = arg
                                break
            log_error(
                message=str(exc),
                query_id=tracker.query_id if tracker else None,
                question=str(question) if question else None,
                module_name=func.__module__,
                function_name=func.__qualname__,
                exc=exc,
            )
            raise

    return cast(F, wrapper)


def _infer_rows(result: Any) -> int | None:
    if result is None:
        return None
    try:
        import pandas as pd

        if isinstance(result, pd.DataFrame):
            return len(result)
    except Exception:
        pass
    if isinstance(result, (list, tuple)):
        # Common ASK-DB pattern: (df, sql, err, evidence)
        if result and hasattr(result[0], "__len__"):
            try:
                import pandas as pd

                if isinstance(result[0], pd.DataFrame):
                    return len(result[0])
            except Exception:
                pass
        # err in tuple → failure path handled by caller
    return None
