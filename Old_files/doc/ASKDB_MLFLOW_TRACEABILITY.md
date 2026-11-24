# ASK-DB LLMOps traceability (leadership demo)

Observability does **not** make the model faster. It shows **where time went**: LLM SQL vs PostgreSQL vs narration.

For a plain-language walkthrough (p50 / p90 / p95, stages, MLflow vs in-app), see
[`ASKDB_LLMOPS_SIMPLE_GUIDE.md`](./ASKDB_LLMOPS_SIMPLE_GUIDE.md).

## What to show in a meeting

1. Ask any insurance question in Chat.
2. Open **Details · trust, context, SQL** on the answer — **Pipeline trace**.
3. Open the sidebar expander **LLMOps trace** — p50/p95, SQL retry rate, last spans.

In-app pipeline timings are **always on** (no extra model wait).

MLflow persistence is **opt-in** so Chat does not pay a multi-second library import on every session:

- Sidebar → **LLMOps trace** → **Persist traces to MLflow**
- Or set `ASKDB_MLFLOW=1` then restart

Local store (MLflow 3.x): SQLite file `mlflow.db` in the project root.

Then:

```bash
mlflow ui --backend-store-uri sqlite:///./mlflow.db --port 5000
```

Open http://127.0.0.1:5000 → experiment **askdb-insurance-chat**.

Talking point: *“Every question is a governed run: prompt size, LLM ms, warehouse ms, retry flag, tokens. Same discipline as classical ML experiment tracking.”*

## Pipeline spans

| Span | Meaning |
|------|---------|
| `pg.health` | Cached connectivity check (60s TTL) |
| `prompt.build` | Semantic YAML + schema (catalog cached 120s) |
| `llm.sql` | First SQL generation |
| `llm.sql_retry` | Auto-repair if SQL failed |
| `pg.execute` | Warehouse time |
| `insight` | BI insights (0 LLM) or LLM narration |
| `llm.narration` | Extra LLM only when Narration chip is on |

If **LLM ms ≈ total**, the wait is the model (prompt size / retries / narration). If **db ms** dominates, tune SQL/indexes.

## Latency work already in the app (Phase 0)

- PostgreSQL `information_schema` catalog cached 2 minutes (schema + fingerprint).
- Health check cached 60 seconds.
- Postgres prompt trimmed (static semantic cached, schema cap ~4.5k chars).
- Default Full mode still skips LLM narration.

## Files

- [`core/observability.py`](../core/observability.py)
- [`core/llm_client.py`](../core/llm_client.py)
- [`core/nlq_engine.py`](../core/nlq_engine.py)
- [`core/data_backend/postgres.py`](../core/data_backend/postgres.py)
- [`ui/sidebar.py`](../ui/sidebar.py) — LLMOps panel
- [`ui/tab_query.py`](../ui/tab_query.py) — per-answer pipeline table
