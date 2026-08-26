"""
core/observability.py
LLMOps traces for ASK-DB: in-app pipeline timings + optional MLflow.

Does not speed the model. It attributes wall-clock to llm.sql / pg.execute /
narration so leadership can see where 15s went.
"""
from __future__ import annotations

import os
import time
import uuid
from contextlib import contextmanager
from typing import Any, Iterator

_MLFLOW_OK = False
_MLFLOW_INIT = False
_mlflow = None

EXPERIMENT_NAME = "askdb-insurance-chat"


def _session_safe() -> dict[str, Any] | None:
    try:
        import streamlit as st

        return st.session_state
    except Exception:
        return None


def _mlflow_wanted() -> bool:
    if os.environ.get("ASKDB_MLFLOW", "").strip() in {"1", "true", "yes", "on"}:
        return True
    ss = _session_safe()
    if ss is not None and ss.get("askdb_mlflow_on"):
        return True
    return False


def _ensure_mlflow() -> bool:
    global _MLFLOW_OK, _MLFLOW_INIT, _mlflow
    if not _mlflow_wanted():
        return False
    if _MLFLOW_INIT:
        return _MLFLOW_OK
    _MLFLOW_INIT = True
    try:
        import mlflow

        _mlflow = mlflow
        uri = os.environ.get("MLFLOW_TRACKING_URI") or os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "mlruns",
        )
        mlflow.set_tracking_uri(uri)
        mlflow.set_experiment(EXPERIMENT_NAME)
        _MLFLOW_OK = True
    except Exception:
        _MLFLOW_OK = False
        _mlflow = None
    return _MLFLOW_OK


def mlflow_status() -> dict[str, Any]:
    ok = _ensure_mlflow()
    uri = ""
    if ok and _mlflow is not None:
        try:
            uri = str(_mlflow.get_tracking_uri())
        except Exception:
            uri = ""
    return {
        "enabled": ok,
        "tracking_uri": uri,
        "experiment": EXPERIMENT_NAME if ok else None,
    }


class PipelineTrace:
    """One Chat question: nested spans + summary for UI / MLflow."""

    def __init__(self, question: str, *, tags: dict[str, Any] | None = None):
        self.trace_id = uuid.uuid4().hex[:12]
        self.question = (question or "")[:400]
        self.tags = dict(tags or {})
        self.spans: list[dict[str, Any]] = []
        self.t0 = time.perf_counter()
        self._active: list[tuple[str, float, dict]] = []
        self._mlflow_run = None
        self._mlflow_cm = None
        if _ensure_mlflow() and _mlflow is not None:
            try:
                self._mlflow_cm = _mlflow.start_run(
                    run_name=f"q-{self.trace_id}",
                    tags={
                        "askdb.trace_id": self.trace_id,
                        "askdb.backend": str(self.tags.get("backend") or ""),
                        "askdb.mode": str(self.tags.get("answer_mode") or ""),
                    },
                )
                self._mlflow_run = self._mlflow_cm.__enter__()
                _mlflow.log_param("question", self.question[:250])
                for k, v in self.tags.items():
                    if v is None:
                        continue
                    _mlflow.log_param(str(k)[:250], str(v)[:250])
            except Exception:
                self._mlflow_run = None
                self._mlflow_cm = None

    @contextmanager
    def span(self, name: str, **attrs: Any) -> Iterator[dict[str, Any]]:
        rec: dict[str, Any] = {
            "name": name,
            "ok": True,
            "error": None,
            "attrs": {k: v for k, v in attrs.items() if v is not None},
        }
        t1 = time.perf_counter()
        parent = None
        if _ensure_mlflow() and _mlflow is not None and self._mlflow_run is not None:
            try:
                start_span = getattr(_mlflow, "start_span", None)
                if callable(start_span):
                    parent = start_span(name=name)
                    parent.__enter__()
            except Exception:
                parent = None
        try:
            yield rec
        except Exception as exc:
            rec["ok"] = False
            rec["error"] = str(exc)[:300]
            raise
        finally:
            rec["latency_ms"] = int((time.perf_counter() - t1) * 1000)
            self.spans.append(rec)
            if parent is not None:
                try:
                    parent.__exit__(None, None, None)
                except Exception:
                    pass
            if _mlflow is not None and self._mlflow_run is not None:
                try:
                    _mlflow.log_metric(f"span.{name.replace('.', '_')}_ms", rec["latency_ms"])
                    if rec.get("attrs", {}).get("prompt_chars"):
                        _mlflow.log_metric(
                            f"span.{name.replace('.', '_')}_prompt_chars",
                            float(rec["attrs"]["prompt_chars"]),
                        )
                    if rec.get("attrs", {}).get("tokens"):
                        _mlflow.log_metric(
                            f"span.{name.replace('.', '_')}_tokens",
                            float(rec["attrs"]["tokens"]),
                        )
                except Exception:
                    pass

    def finish(self) -> dict[str, Any]:
        total_ms = int((time.perf_counter() - self.t0) * 1000)
        by_name = {s["name"]: s["latency_ms"] for s in self.spans}
        summary = {
            "trace_id": self.trace_id,
            "question": self.question,
            "tags": self.tags,
            "total_ms": total_ms,
            "llm_ms": sum(
                s["latency_ms"]
                for s in self.spans
                if str(s.get("name") or "").startswith("llm.")
            ),
            "db_ms": sum(
                s["latency_ms"]
                for s in self.spans
                if str(s.get("name") or "").startswith("pg.")
                or str(s.get("name") or "").startswith("db.")
            ),
            "prompt_ms": by_name.get("prompt.build", 0),
            "narration_ms": by_name.get("insight") or by_name.get("llm.narration") or 0,
            "retried_sql": any(s.get("name") == "llm.sql_retry" for s in self.spans),
            "spans": self.spans,
            "mlflow": mlflow_status(),
        }
        if _mlflow is not None and self._mlflow_run is not None:
            try:
                _mlflow.log_metric("total_ms", total_ms)
                _mlflow.log_metric("llm_ms", summary["llm_ms"])
                _mlflow.log_metric("db_ms", summary["db_ms"])
                _mlflow.log_param("sql_retry", str(summary["retried_sql"]))
            except Exception:
                pass
            try:
                if self._mlflow_cm is not None:
                    self._mlflow_cm.__exit__(None, None, None)
            except Exception:
                pass
        self._store(summary)
        return summary

    def _store(self, summary: dict[str, Any]) -> None:
        ss = _session_safe()
        if ss is None:
            return
        ss["last_pipeline_trace"] = summary
        hist = list(ss.get("pipeline_trace_log") or [])
        hist.append(
            {
                "trace_id": summary["trace_id"],
                "question": summary["question"][:80],
                "total_ms": summary["total_ms"],
                "llm_ms": summary["llm_ms"],
                "db_ms": summary["db_ms"],
                "retried_sql": summary["retried_sql"],
                "ts": time.time(),
            }
        )
        ss["pipeline_trace_log"] = hist[-50:]


_CURRENT: PipelineTrace | None = None


def start_trace(question: str, **tags: Any) -> PipelineTrace:
    global _CURRENT
    _CURRENT = PipelineTrace(question, tags=tags)
    return _CURRENT


def current_trace() -> PipelineTrace | None:
    return _CURRENT


@contextmanager
def span(name: str, **attrs: Any) -> Iterator[dict[str, Any]]:
    tr = _CURRENT
    if tr is None:
        t1 = time.perf_counter()
        rec: dict[str, Any] = {"name": name, "attrs": attrs, "ok": True}
        try:
            yield rec
        finally:
            rec["latency_ms"] = int((time.perf_counter() - t1) * 1000)
        return
    with tr.span(name, **attrs) as rec:
        yield rec


def finish_trace() -> dict[str, Any] | None:
    global _CURRENT
    tr = _CURRENT
    _CURRENT = None
    if tr is None:
        return None
    return tr.finish()


def last_trace() -> dict[str, Any] | None:
    ss = _session_safe()
    if ss is None:
        return None
    val = ss.get("last_pipeline_trace")
    return val if isinstance(val, dict) else None


def trace_log() -> list[dict[str, Any]]:
    ss = _session_safe()
    if ss is None:
        return []
    return list(ss.get("pipeline_trace_log") or [])


def percentile(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    idx = min(len(ordered) - 1, max(0, int(round((p / 100.0) * (len(ordered) - 1)))))
    return float(ordered[idx])


def session_kpis() -> dict[str, Any]:
    log = trace_log()
    totals = [float(x.get("total_ms") or 0) for x in log]
    llms = [float(x.get("llm_ms") or 0) for x in log]
    retries = sum(1 for x in log if x.get("retried_sql"))
    n = len(log)
    return {
        "n": n,
        "p50_ms": percentile(totals, 50),
        "p95_ms": percentile(totals, 95),
        "llm_p50_ms": percentile(llms, 50),
        "retry_rate": (retries / n) if n else 0.0,
        "mlflow": mlflow_status(),
    }
