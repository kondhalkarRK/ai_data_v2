# ASK-DB LLMOps — simple guide

This page explains what you see under **LLMOps trace** and **Pipeline trace**.
It does **not** make the model faster — it shows **where time went**.

---

## Two layers (easy mental model)

| Layer | What it is | Where you see it |
|--------|------------|------------------|
| **In-app LLMOps** | Timings for each question (always on) | Sidebar + Chat → Details → Pipeline table |
| **MLflow** | Optional **save** of those timings to disk for leadership / audit | Checkbox **Persist traces to MLflow** → folder `./mlruns` → `mlflow ui` |

**Your table (`pg.health`, `prompt.build`, `llm.sql`, `pg.execute`) is LLMOps.**  
That works even when MLflow is off.

**MLflow** is only the “save a copy for later / leadership UI” step.

---

## Why you saw “MLflow not installed”

Usually that message meant:

1. The **checkbox was off** when you asked the question, **or**
2. You turned MLflow **on after** the answer — that answer was already finished.

On this machine **MLflow is already installed** (`mlflow` package).  
To persist:

1. Check **Persist traces to MLflow** in the sidebar  
2. Ask a **new** question  
3. Sidebar should show **MLflow ON**  
4. Optional leadership UI:

```bash
mlflow ui --backend-store-uri sqlite:///./mlflow.db --port 5000
```

Open http://127.0.0.1:5000 → experiment **askdb-insurance-chat**.

Runs are stored in project file `mlflow.db` (MLflow 3.x). The old `./mlruns` file store is no longer the default.

If the package were truly missing: `pip install mlflow` then **restart Streamlit**.

---

## Percentiles: p50, p90, p95 (what they mean)

Imagine you asked **100** questions and sorted their total times from fastest to slowest.

| Term | Plain English | Example |
|------|----------------|---------|
| **p50** (median) | Half of questions finished **this fast or faster** | p50 = 10s → typical experience |
| **p90** | **90%** finished this fast or faster; only ~10% slower | Catch “most users” SLA |
| **p95** | **95%** finished this fast or faster; only ~5% slower | Catch the bad tail |
| **p99** | Almost everyone; only ~1% slower | Rare worst cases |

ASK-DB sidebar shows **p50** and **p95** for total question time, plus **LLM p50** (model-only).

### Why p50 and p95 both matter

- **p50** = “normal” day  
- **p95** = “when it feels slow” for a few users  

If p50 is 3s but p95 is 20s, the average looks fine but some questions are painful (retries, big prompts, slow SQL).

With **only 1 question traced**, p50 and p95 are the **same number** — that is normal. They diverge after many questions.

---

## Pipeline stages (the table rows)

| Stage | Meaning | What “slow” usually means |
|--------|---------|---------------------------|
| **pg.health** | Quick Postgres connectivity check (often cached → **0 ms**) | DB down / wrong host |
| **prompt.build** | Build semantic + schema text for the LLM | Rarely the main cost |
| **llm.sql** | LLM writes SQL | Often the largest slice |
| **llm.sql_retry** | Second LLM call if first SQL failed | Extra wait + cost |
| **pg.execute** | Warehouse runs the SQL | Index / query shape |
| **insight** | BI-style bullets (usually **no** LLM) | — |
| **llm.narration** | Extra LLM text (only if Narration chip is on) | Adds seconds |

### Reading your example

From a typical run like:

- Total ~**10.4 s**
- LLM ~**2.4 s** (`llm.sql`)
- Database ~**0.4 s** (`pg.execute`)

So most of the **measured pipeline** is the model + DB.  
Any gap between **sum of stages** and **Total** is other app work (Streamlit UI, formatting, trust score, etc.).

---

## Other sidebar numbers

| Metric | Meaning |
|--------|---------|
| **Questions traced** | How many answers in this session have a pipeline log |
| **SQL retry rate** | Share of questions that needed a second LLM SQL fix |
| **LLM p50** | Typical time spent inside the language model only |

---

## Talking points for leadership

1. Numbers come from **SQL on the warehouse**, not from the LLM inventing figures.  
2. Every answer can show **where seconds went** (model vs database).  
3. Optional **MLflow** stores the same timings as governed runs for audit / demos.  
4. Turning MLflow on does **not** speed Chat — it only **records**.

---

## Related docs

- [`ASKDB_MLFLOW_TRACEABILITY.md`](./ASKDB_MLFLOW_TRACEABILITY.md) — how to run the MLflow UI  
- Code: `core/observability.py`, `ui/sidebar.py`, Chat Details in `ui/tab_query.py`
