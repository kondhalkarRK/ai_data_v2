# NQL Insight — Migration Inventory

Legacy source: `E:\ai_data_rag\ai_data_v2` (Streamlit "ASK-DB")
Target: `E:\ai_data_rag\ai_data_v2\askdb` (standalone Next.js + FastAPI monorepo)

The legacy tree is **read-only** for this migration. Nothing under the parent directory is
modified or deleted, and nothing under `askdb/` imports from it at runtime.

Legend:

| Verdict | Meaning |
| --- | --- |
| **KEEP** | Copy essentially verbatim into `apps/api/app/...`; only import paths change. |
| **ADAPT** | Business logic preserved; Streamlit / MLflow / session coupling removed. |
| **REPLACE** | Capability survives, implementation is rewritten for the new stack. |
| **RETIRE** | Dropped by explicit instruction (§4 of the spec) or dead code. |

---

## 1. Preserved Python files (KEEP)

These carry no Streamlit import and no presentation logic. They move into the API package
with import-path rewrites only.

| Legacy path | New path | Notes |
| --- | --- | --- |
| `core/sql_guardrails.py` | `app/rag/../core/sql_guardrails.py` → `app/services/sql/guardrails.py` | Single pure `sql_is_safe(sql) -> (bool, str)`; regex constants. |
| `core/sql_compiler.py` | `app/services/sql/compiler.py` | Deterministic contract → SQL. No callers today; wired up in Phase 5. |
| `core/pii_mask.py` | `app/services/data/pii_mask.py` | Applied on every result-serialisation path. |
| `core/metric_registry.py` | `app/semantic/metric_registry.py` | Module singleton; constructor already accepts a path. |
| `core/data_backend/base.py` | `app/repositories/data_backend/base.py` | Abstract backend contract. |
| `core/semantic_joins.py` | `app/semantic/joins.py` | Pure metadata read over the semantic loader. |
| `core/analysis_engine.py` | `app/services/analysis.py` | Only dependency is the LLM client (injected). |
| `features/business_insights.py` | `app/services/insights/business_insights.py` | Zero UI coupling. |
| `features/narration_engine.py` | `app/services/narration.py` | OKF imports removed, RAG context injected instead. |
| `features/question_cache/cache_manager.py` | `app/services/cache/question_cache.py` | Fingerprint + normalisation logic. |
| `features/question_cache/cache_triggers.py` | `app/services/cache/triggers.py` | `should_cache_result` heuristics. |
| `features/rag_query_memory/glossary_store.py` | `app/rag/memory/glossary_store.py` | Vector backend swapped to Qdrant. |
| `features/rag_query_memory/query_memory.py` | `app/rag/memory/query_memory.py` | Vector backend swapped to Qdrant. |
| `features/vector_schema_retrieval/schema_retriever.py` | `app/semantic/schema_retriever.py` | |
| `utils/logger.py` | `app/observability/logging.py` | Already `ContextVar`-based; binds to a request scope. |
| `utils/decorators.py` | `app/observability/decorators.py` | Works unchanged on async handlers after a small await-aware wrapper. |
| `semantic/semantic_loader.py` | `app/semantic/loader.py` | No Streamlit; only the global singleton becomes a per-pack registry. |
| `semantic/semantic_context_builder.py` | `app/semantic/context_builder.py` | Produces the LLM prompt context string. |
| `semantic/semantic_vector_search.py` | `app/semantic/vector_search.py` | In-memory TF-IDF / MiniLM index. |
| `semantic/packs/**/*.yaml` | `apps/api/semantic/packs/**` | **Semantic YAML remains the source of truth.** Copied verbatim. |
| `semantic/metric_registry.yaml` | `apps/api/semantic/metric_registry.yaml` | |
| `db/migrations/001_insurance_schema.sql` | `database/insurance/` + Alembic revision | Re-expressed as an Alembic revision; DDL preserved. |
| `features/okf_knowledge/pdf_extractor.py` | `app/rag/parsers/pdf.py` | Parsing layer only; OKF routing dropped. |
| `features/okf_knowledge/docx_extractor.py` | `app/rag/parsers/docx.py` | |
| `features/okf_knowledge/pptx_extractor.py` | `app/rag/parsers/pptx.py` | Slide metadata generalised. |
| `features/okf_knowledge/md_extractor.py` | `app/rag/parsers/markdown.py` + `app/rag/chunking.py` | `_clean_text` / `_split_oversized` become the shared chunker (1400/40 chars). |

---

## 2. Adapted Python files (ADAPT)

Business logic and SQL behaviour are preserved. The listed coupling is what gets removed.

| Legacy path | New path | Coupling removed |
| --- | --- | --- |
| `core/nlq_engine.py` | `app/services/nlq/engine.py` | ~40 `st.session_state` reads/writes → typed `QueryContext` dataclass passed through the pipeline. Session NLQ cache → TTL cache keyed by `(pack, fingerprint, question)`. UI metadata (`last_glossary_matches`, `last_semantic_context`, …) → fields on the returned `NlqResult` Pydantic model. Returns typed model instead of a 4-tuple. |
| `core/llm_client.py` | `app/services/llm/client.py` | Budgets/usage counters in `st.session_state` → `llm_usage` rows in PostgreSQL + per-request `UsageAccumulator`. `st.error` → raised `LLMError`. `st.secrets` → `Settings`. Adds streaming for SSE. |
| `core/conversation_state.py` | `app/services/conversation/state.py` | Entire state lives in `st.session_state["conversation_state"]` → a `conversations`/`messages` row set in MongoDB plus a request-scoped `ConversationContext`. SQL-anchor and clarification semantics preserved exactly. |
| `core/data_backend/factory.py` | `app/repositories/data_backend/factory.py` | `@st.cache_resource` → FastAPI lifespan-managed pool registry, keyed by industry. Session fallback flags → `BackendStatus` model. Gains per-industry routing (automotive / insurance). |
| `core/data_backend/postgres.py` | `app/repositories/data_backend/postgres.py` | psycopg sync pool → SQLAlchemy 2 async engine + `psycopg` async pool. Adds read-only transaction mode, statement timeout, row cap and keyset pagination. |
| `core/data_backend/csv_duckdb.py` | `app/repositories/data_backend/duckdb.py` | Retained only for local development fixtures; not part of the production path. |
| `core/kpi_engine.py` | `app/services/kpi/automotive.py` | `@st.cache_data` → TTL cache. `render_kpi_tab` retired. **The pandas metric formulas are re-expressed as SQL** against the new automotive schema so no full fact table is loaded (spec §6). Formula semantics preserved 1:1 and covered by parity tests. |
| `core/insurance_kpi_engine.py` | `app/services/kpi/insurance.py` | Already SQL-first — the SQL builders (`_kpi_sql`, `_monthly_sql`, `_lob_sql`, `_region_sql`, `_status_sql`) and the FY/rolling/YTD bounds helpers move as-is. Only `render_insurance_kpi_tab` and `@st.cache_data` are dropped. |
| `core/data_quality_engine.py` | `app/services/dq/frame_rules.py` | Split compute from `render_*`. Scoring formula preserved verbatim. |
| `core/postgres_dq_engine.py` | `app/services/dq/postgres_rules.py` | Session cache dropped; becomes the primary DQ path for both industries. Scoring formula preserved. |
| `core/join_engine.py` | `app/services/joins.py` | `get_working_df()` session orchestration replaced by a request-scoped dataset registry; join scoring/auto-join algorithms preserved. |
| `core/schema_builder.py` | `app/semantic/schema_builder.py` | `@st.cache_data` → cache keyed by `(fingerprint, column_subset)`. |
| `core/chart_engine.py` | `app/services/charts.py` | `st.plotly_chart` → returns a chart **spec** (type, x, y, series) that the frontend renders with ECharts. `auto_chart_type` preserved. |
| `core/observability.py` | `app/observability/tracing.py` | **All MLflow code removed.** `PipelineTrace` / `span` kept, session store → `contextvars`. |
| `core/question_normaliser.py` | `app/services/nlq/normaliser.py` | Lazy `conversation_state` import replaced by an injected context. |
| `core/intent_resolver.py` | `app/services/nlq/intent_resolver.py` | LLM client injected. |
| `core/semantic_resolver.py` | `app/services/nlq/semantic_resolver.py` | Loader injected instead of a global singleton. |
| `core/intent_cache.py` | `app/services/cache/intent_cache.py` | Session + JSON-file store → TTL cache + PostgreSQL. |
| `core/evidence_builder.py` | `app/services/nlq/evidence.py` | Session history/stats → `retrieval_audit` / `query_history` persistence. |
| `core/incomplete_question.py` | `app/services/nlq/completeness.py` | One optional `st.session_state` read removed. |
| `features/whatif_engine.py` | `app/services/whatif.py` | `generate_interactive_result` (Streamlit sliders) retired; `parse_scenario` / `run_scenario` preserved. Per spec §13, exposed only in a clearly labelled Scenario Mode. |
| `features/anomaly_engine.py` | `app/services/insights/anomaly.py` | Runs on bounded query results, not full fact tables. |
| `features/proactive_engine.py` | `app/services/insights/proactive.py` | Session cache removed; suggestions precomputed per industry. |
| `features/question_cache/cache_store.py` | `app/services/cache/store.py` | `st.session_state["saved_questions"]` + pickle files → PostgreSQL `saved_questions` table. |
| `features/rag_query_memory/embedder.py` | `app/rag/embeddings.py` | `@st.cache_resource` → lifespan singleton. Hash fallback retained for offline dev. |
| `features/rag_query_memory/vector_store.py` | `app/rag/vector_store.py` | **Chroma → Qdrant** (`automotive_knowledge`, `insurance_knowledge`). |
| `features/vector_schema_retrieval/schema_indexer.py` | `app/semantic/schema_indexer.py` | Indexes from database catalog metadata rather than a full DataFrame. |
| `semantic/industry_packs.py` | `app/semantic/packs.py` | **Critical change.** Legacy switching copies pack YAML over the live `semantic/semantic_model.yaml` and nulls process-wide singletons — unsafe for a multi-user server. Replaced by an immutable per-industry registry loaded once at startup; switching selects a pack, it never mutates files. |
| `ui/decision_share.py` | `app/services/export.py` | Export/brief generation kept (PDF/PPTX/CSV); Streamlit popovers retired. |
| `ui/safe_display.py` | folded into `app/schemas/results.py` | PII masking enforced in the response serializer. |
| `config/settings.py` | `app/core/config.py` | `st.secrets` → `pydantic-settings` `BaseSettings`. Every variable listed in §5 below. |
| `config/constants.py` | `app/core/constants.py` | Business constants preserved. |
| `config/llm_catalog.py` | `app/core/llm_catalog.py` | Becomes configuration-driven pricing (spec §16). |

---

## 3. Retired Streamlit / excluded files (RETIRE)

Not carried into `askdb/`. The legacy copies stay where they are as the rollback reference.

### Streamlit application shell and screens

| Legacy path | Reason |
| --- | --- |
| `app.py` | Streamlit entry point; replaced by `apps/web` routes + `apps/api` main. |
| `ui/sidebar.py` | Replaced by the React app shell. |
| `ui/tab_query.py` (102 KB) | Replaced by `/chat`; every feature is re-mapped in §4 below. |
| `ui/tab_preview.py` | Replaced by `/data-preview`. |
| `ui/tab_kpi.py` | Replaced by `/dashboard`. |
| `ui/tab_join.py` | Replaced by Semantic Core → Join Definitions. |
| `ui/kpi_flip_cards.py` | HTML-string card renderer; replaced by React KPI cards. |
| `ui/__init__.py`, `ui/safe_display.py` | Presentation only. |
| `config/styles.py` (93 KB) | Streamlit CSS injection; design tokens extracted into Tailwind theme, the rest retired. |
| `config/themes.py` (45 KB) | Same; light/dark/AI token values extracted, CSS retired. |
| `.streamlit/` | Streamlit runtime config. |
| `runtime.txt`, `requirements.txt` | Streamlit Cloud deployment descriptors. |
| `_test_features.py` | Streamlit-driven manual test harness. |

### Explicitly dropped capabilities (spec §4)

| Legacy path | Reason |
| --- | --- |
| `features/okf_knowledge/okf_answer.py` | OKF answer routing — dropped; replaced by `RAGService`. |
| `features/okf_knowledge/okf_store.py` | OKF bundle storage — replaced by MongoDB `documents` / `document_versions`. |
| `features/okf_knowledge/okf_retriever.py` | OKF Chroma retriever — replaced by Qdrant hybrid retrieval. |
| `features/okf_knowledge/okf_bootstrap.py` | OKF auto-seeding — replaced by an authenticated ingestion API. |
| `features/okf_knowledge/target_alignment.py` | Hard-coded FY2026 India-PV target logic. |
| `features/okf_knowledge/target_narration.py` | Same. |
| `features/okf_knowledge/targets_fy2026.yaml` | Same. |
| `rag_storage/okf_bundles/**` | OKF on-disk chunk bundles (78 files). |
| `rag_storage/chroma_db/` | Chroma store — replaced by Qdrant. |
| MLflow code in `core/observability.py:29-339` | MLflow removed entirely (spec §18). |
| `mlflow.db` | MLflow tracking database. |
| `doc/ASKDB_MLFLOW_TRACEABILITY.md` | MLflow documentation. |
| `requirements-okf.txt` | OKF dependency set. |
| `features/materialized_views/` | Directory does not exist; only a SQL marker string references it. Re-implemented natively as PostgreSQL materialized views (spec §6). |

Neo4j, agent catalogs, agentic orchestration, Capgemini SSO and Entra ID **do not exist in the
legacy codebase**, so there is nothing to retire — they are simply never introduced.

### Standalone app absorbed

| Legacy path | Reason |
| --- | --- |
| `ontology-browser/` (Vite SPA) | Absorbed into `apps/web/features/ontology`. `src/lib/types.ts`, `yamlParser.ts` and `layouts.ts` are ~80% portable and are carried over; `HashRouter`, `main.tsx`, `index.html`, `vite.config.ts` and `scripts/sync-yaml.mjs` are retired in favour of App Router + a server-compiled snapshot. |

---

## 4. Streamlit screen → Next.js route → API endpoint map

| Legacy screen | Next.js route | Primary API endpoints |
| --- | --- | --- |
| `app.py` shell + `ui/sidebar.py` | `app/(app)/layout.tsx` | `GET /api/v1/me`, `GET /api/v1/industries`, `POST /api/v1/industries/{id}/activate` |
| Backend status strip | shell status chip | `GET /health`, `GET /ready`, `GET /api/v1/diagnostics/backends` |
| Upload CSV dialog | *retired* — PostgreSQL is the analytics source | — |
| PostgreSQL panel | `/settings/data-sources` | `GET /api/v1/data-sources` |
| Join settings dialog | `/semantic/joins` | `GET /api/v1/semantic/joins` |
| LLM settings dialog | `/settings/llm` | `GET /api/v1/llm/catalog`, `PUT /api/v1/llm/preferences` |
| LLMOps trace panel | `/system-logs` | `GET /api/v1/logs/executions?limit=10`, `GET /api/v1/logs/traces/{id}` |
| Saved questions expander | `/saved-questions` | `GET/POST/PATCH/DELETE /api/v1/saved-questions` |
| Industry pack expander | top-bar industry selector | `GET /api/v1/industries` |
| Knowledge base (OKF) expander | `/knowledge` | `GET /api/v1/rag/documents`, `POST /api/v1/rag/documents` |
| Ontology Browser link (`localhost:5173`) | `/semantic/ontology` | `GET /api/v1/semantic/ontology/snapshot?industry=` |
| **Data Preview** tab | `/data-preview` | `GET /api/v1/preview/schemas`, `GET /api/v1/preview/tables`, `GET /api/v1/preview/rows` (server-side paginated) |
| Data Quality panel | `/data-quality` | `GET /api/v1/dq/summary`, `GET /api/v1/dq/rules`, `GET /api/v1/dq/runs`, `GET /api/v1/dq/issues` |
| **KPI** tab | `/dashboard` | `GET /api/v1/kpi/summary`, `GET /api/v1/kpi/series`, `POST /api/v1/kpi/whatif` |
| **Chat Room** tab | `/chat` | `POST /api/v1/chat/messages` (SSE), `GET /api/v1/chat/conversations`, `DELETE /api/v1/chat/conversations/{id}` |
| Chat: SQL re-run | `/chat` inline drawer | `POST /api/v1/sql/execute` |
| Chat: expand table | `/chat` dialog | `GET /api/v1/chat/messages/{id}/rows?cursor=` |
| Chat: trust + trace | `/chat` details panel | included in the message payload |
| What-if | `/dashboard` Scenario Mode | `POST /api/v1/kpi/whatif` |
| Pin / share / export | `/chat` + `/saved-questions` | `POST /api/v1/exports/{format}` |
| — (new) | `/semantic` | `GET /api/v1/semantic/overview` |
| — (new) | `/cost-analytics` | `GET /api/v1/cost/summary`, `GET /api/v1/cost/trends` |
| — (new) | `/query-history` | `GET /api/v1/history` |
| — (new) | `/login` | `POST /api/v1/auth/login`, `POST /api/v1/auth/refresh`, `POST /api/v1/auth/logout` |

Features found in `ui/tab_query.py` that must survive into `/chat`: answer-mode selector
(Full / Insights / Table / Chart), staged execution indicators, OOB guard, greeting handling,
incomplete-question clarification with two suggestions, empty-result recovery suggestions,
friendly SQL errors, "Surprise me" analysis, what-if routing, four-component trust score,
PII-masked result table, auto chart type, narration card, SQL anchor follow-up modification
banner, pin + executive brief export, per-message expand dialog, and the LLM usage caption.

`ui/tab_query.py:render_ask_mode` (lines 878-1018) is **dead code** — `render()` only calls
`render_chat_mode()`. It is not carried over.

---

## 5. Environment variables and secrets inventory

Every secret read by the legacy app, and how it is provided in the new one. No value is
committed; `.env.example` carries names and safe defaults only.

### Carried over

| Legacy name | New name | Notes |
| --- | --- | --- |
| `CAPGEMINI_LLM_API_KEY` | `LLM_API_KEY` | Provider-neutral. Server-side only. |
| `CAPGEMINI_LLM_BASE_URL` | `LLM_BASE_URL` | Default `https://openai.generative.engine.capgemini.com/v1`. |
| `CAPGEMINI_LLM_MODEL` | `LLM_DEFAULT_MODEL` | Default `openai.gpt-5.1`. |
| `POSTGRES_HOST/PORT/USER/PASSWORD` | `APP_DATABASE_URL`, `AUTOMOTIVE_DATABASE_URL`, `INSURANCE_DATABASE_URL` | Three separate DSNs (spec §6). |
| `POSTGRES_SCHEMA` | *removed* | All SQL is schema-qualified. |
| `POSTGRES_STATEMENT_TIMEOUT_SECONDS` | `SQL_STATEMENT_TIMEOUT_SECONDS` | Default 30. |
| `POSTGRES_MAX_RESULT_ROWS` | `SQL_MAX_RESULT_ROWS` | Default 1000. |
| `POSTGRES_POOL_MIN_SIZE` / `MAX_SIZE` | `DB_POOL_MIN_SIZE` / `DB_POOL_MAX_SIZE` | |
| `POSTGRES_CONNECT_TIMEOUT_SECONDS` | `DB_CONNECT_TIMEOUT_SECONDS` | |
| `POSTGRES_SSLMODE` | folded into each DSN | |
| `ASKDB_USE_HF_EMBEDDINGS` | `EMBEDDINGS_PROVIDER` | `hash` \| `sentence-transformers` \| `openai`. |
| `INDUSTRY_PACK` | `DEFAULT_INDUSTRY` | `automotive` \| `insurance`. |

### Retired

`DATA_BACKEND`, `POSTGRES_FALLBACK_CSV`, `POSTGRES_URL`/`DATABASE_URL` (single-DB),
`IS_STREAMLIT_CLOUD`, `STREAMLIT_RUNTIME_ENV`, `ASKDB_MLFLOW`, `MLFLOW_TRACKING_URI`.

### New

`JWT_SECRET_KEY`, `JWT_ACCESS_TTL_MINUTES`, `JWT_REFRESH_TTL_DAYS`, `COOKIE_DOMAIN`,
`COOKIE_SECURE`, `CORS_ALLOWED_ORIGINS`, `MONGODB_URI`, `MONGODB_DATABASE`, `QDRANT_URL`,
`QDRANT_API_KEY`, `RATE_LIMIT_LOGIN_PER_MINUTE`, `UPLOAD_MAX_BYTES`,
`WEB_RETRIEVAL_ENABLED`, `WEB_RETRIEVAL_ALLOWLIST`, `NEXT_PUBLIC_API_BASE_URL`.

---

## 6. Known gaps in the legacy data model

Carried forward as work items, not silently reproduced.

1. **There is no automotive PostgreSQL database.** Automotive today is CSV + DuckDB with seven
   unqualified tables. Spec §6 requires `askdb_automotive` with four schemas
   (`sales`, `inventory`, `claims`, `master`) and thirteen tables — of which only
   `fact_sales`, `dim_carline`, `dim_color`, `dim_salesman`, `dim_region`, `dim_targets`
   and `dim_dealer` have any legacy lineage. `fact_orders`, `fact_returns`,
   `fact_inventory_snapshot`, `fact_stock_movement`, `dim_warehouse`, `fact_warranty_claims`
   and `fact_service_tickets` are **new** and need DDL plus a generator.
2. `insurance.fact_operating_expense_monthly` exists in the DDL and in relationships but is
   missing from `semantic_model_postgres.yaml` `tables:`. Added in the new pack.
3. `dim_policy.customer_key` and `cancelled_flag` are in the DDL but not in the semantic
   column list. Added.
4. `semantic/metric_registry.yaml` is automotive-only and is not swapped on pack change.
   Becomes per-industry.
5. `doc/kpi_registry.yaml` is a retail/inventory registry never wired into the loader. Not
   migrated.
6. Legacy pack switching mutates files on disk and resets process-wide singletons — it is not
   safe for concurrent users. Replaced by an immutable registry (see §2).
7. The deterministic pipeline (`intent_resolver` → `semantic_resolver` → `sql_compiler`) is
   fully implemented but has **zero callers**. It is migrated and wired in behind a feature
   flag so guarded deterministic SQL can be preferred over free-form LLM SQL.
