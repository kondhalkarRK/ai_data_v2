# NQL Insight — Architecture

## 1. System shape

```
                    ┌──────────────────────────────┐
   Browser  ───────▶│  apps/web  (Next.js, Vercel) │
                    │  App Router · RSC + client   │
                    │  Tailwind · shadcn/ui        │
                    │  TanStack Query · Zustand    │
                    │  React Flow · ECharts        │
                    └──────────────┬───────────────┘
                                   │ HTTPS + HttpOnly cookies
                                   │ JSON + text/event-stream
                    ┌──────────────▼───────────────┐
                    │  apps/api  (FastAPI, Docker) │
                    │  Pydantic v2 · SQLAlchemy 2  │
                    │  Preserved Python engines    │
                    └───┬───────┬───────┬──────┬───┘
                        │       │       │      │
        ┌───────────────▼┐ ┌────▼─────┐ ┌▼─────▼──────┐ ┌──────────┐
        │ askdb_app      │ │askdb_auto│ │ askdb_ins   │ │ MongoDB  │
        │ auth, history, │ │ motive   │ │ urance      │ │ Qdrant   │
        │ cost, saved Qs │ │(4 schemas)│ │(insurance)  │ │ LLM API  │
        └────────────────┘ └──────────┘ └─────────────┘ └──────────┘
```

Three PostgreSQL databases, not one. `askdb_app` holds application state (users, refresh
tokens, audit, query history, LLM usage, saved questions). `askdb_automotive` and
`askdb_insurance` are analytics databases, connected through **separate read-only pools**.

## 2. Non-negotiable boundaries

1. **The frontend never generates SQL, never executes queries, never holds an LLM key.**
   `apps/web` talks only to `apps/api`. Every credential lives server-side.
2. **Numerical truth comes from PostgreSQL.** RAG documents and web results may narrate and
   explain; they may never supply a number presented as a calculated result. Responses carry
   four separately labelled sections: *Data result*, *Document context*, *Web context*,
   *Model interpretation*.
3. **Semantic truth comes from YAML.** The packs under `apps/api/semantic/packs/` are the only
   source for entities, columns, relationships, metrics and glossary. The ontology snapshot is
   compiled from them; clicking an ontology node never touches PostgreSQL.
4. **Analytics connections are read-only.** Every analytics session opens with
   `SET TRANSACTION READ ONLY`, a `statement_timeout`, and a hard `LIMIT` applied by the
   guardrail layer. Full fact tables are never materialised in Python or shipped to the browser.
5. **Vercel runs the frontend only.** No long-lived pool, no ingestion job, no FastAPI process
   in a serverless function. `vercel.json` sets `apps/web` as the project root.

## 3. Backend layering

```
app/
├── api/              HTTP layer. Routers, dependencies, SSE. No business logic.
├── auth/             Argon2 hashing, JWT issue/verify, refresh rotation, RBAC, rate limit.
├── core/             Settings, constants, exceptions, LLM catalog, caching primitives.
├── schemas/          Pydantic v2 request/response models. The API contract.
├── models/           SQLAlchemy 2 ORM models for askdb_app.
├── repositories/     Data access. Analytics backends, app-DB repos, Mongo, Qdrant.
├── semantic/         YAML loader, pack registry, context builder, ontology compiler.
├── rag/              Parsers, chunking, embeddings, vector store, retrieval, web fetch.
├── services/         The preserved engines, wrapped in typed services.
└── observability/    Structured logging, tracing, redaction, metrics.
```

Dependency direction is strictly downward: `api → services → repositories`. `services` return
Pydantic models; a router never sees a DataFrame and never sees a raw psycopg row.

### The eleven services (spec §3)

| Service | Backed by |
| --- | --- |
| `NLQService` | `nlq_engine`, `question_normaliser`, `intent_resolver`, `semantic_resolver`, `sql_compiler`, `sql_guardrails`, `evidence_builder` |
| `KPIService` | `kpi_engine` (SQL-ported), `insurance_kpi_engine` |
| `DataPreviewService` | `data_backend/postgres` with keyset pagination |
| `DataQualityService` | `postgres_dq_engine`, `data_quality_engine` |
| `SemanticService` | `semantic_loader`, `semantic_context_builder`, `semantic_joins`, `metric_registry` |
| `OntologyService` | ontology snapshot compiler over the semantic packs |
| `RAGService` | parsers, chunker, embeddings, Qdrant, MongoDB, web retrieval |
| `ConversationService` | `conversation_state` semantics, persisted in MongoDB |
| `CostAnalyticsService` | `llm_usage` table + configuration-driven pricing |
| `LoggingService` | `utils/logger` + `observability/tracing` |
| `ExportService` | brief/PDF/PPTX/CSV generation from `decision_share` |

## 4. Request context replaces session state

The single largest refactor. Legacy code threads state through `st.session_state`; the new
code threads an explicit immutable context.

```python
@dataclass(frozen=True, slots=True)
class RequestContext:
    request_id: str
    user_id: UUID
    role: Role
    industry: Industry
    conversation_id: str | None
    trace: PipelineTrace
    usage: UsageAccumulator
```

Every legacy `st.session_state.get("industry_pack_id")` becomes `ctx.industry`. Every
`st.session_state.memory[key]` becomes a lookup in the TTL cache. Every usage counter increment
becomes `ctx.usage.add(...)`, flushed to `llm_usage` when the request finishes.

Streamlit caching maps as follows:

| Legacy | Replacement |
| --- | --- |
| `@st.cache_resource` (pools, embedder, Qdrant client) | FastAPI `lifespan` singletons |
| `@st.cache_data` (KPIs, DQ, schema) | `TTLCache` keyed by `(industry, fingerprint, params)` |
| `st.session_state` conversation | MongoDB `conversations` / `messages` |
| `st.session_state` LLM budget | PostgreSQL `llm_usage` |

## 5. Industry switching

Switching industry is a pure selection, never a file mutation. The registry is built once at
startup:

```python
PackRegistry = Mapping[Industry, CompiledPack]

class CompiledPack(BaseModel, frozen=True):
    industry: Industry
    model: SemanticModel        # parsed semantic_model.yaml
    glossary: Glossary          # parsed business_glossary.yaml
    metrics: MetricRegistry
    ontology: OntologySnapshot  # nodes/edges/clusters/metadata
    suggested_questions: list[str]
```

Selecting an industry changes, in one transition: the analytics connection pool, the semantic
pack, the ontology snapshot, the KPI registry, the dashboard definition, the glossary, the
suggested questions, the RAG collection filter, and the query-history scope.

## 6. Chat execution pipeline

```
POST /api/v1/chat/messages          (SSE, text/event-stream)

 1. authenticate            JWT from HttpOnly cookie → RequestContext
 2. select industry         validate the caller may read this industry
 3. resolve semantic ctx    SemanticService.build_context(question, pack)
 4. generate guarded SQL    deterministic compiler when the contract validates,
                            otherwise LLM SQL — both pass sql_guardrails
 5. execute bounded SQL     read-only txn, statement_timeout, LIMIT, row cap
 6. retrieve RAG context    only when the question needs narrative context
 7. build narration         NarrationEngine over the bounded result
 8. stream response         SSE frames, see below
 9. persist                 query_history, llm_usage, retrieval_audit, messages
10. log performance         one trace per request with per-stage spans
```

SSE frame types: `stage` (pipeline progress), `sql`, `columns`, `rows`, `chart`, `token`
(narration delta), `citation`, `usage`, `trust`, `done`, `error`. Cancellation closes the
stream and rolls back nothing — the analytics transaction is read-only.

## 7. Ontology snapshot

Compiled server-side from YAML into the shape the spec requires:

```json
{ "nodes": [], "edges": [], "clusters": [], "metadata": {} }
```

The compiler is a Python port of the proven `ontology-browser/src/lib/yamlParser.ts` rules:
a domain node, one node per table (fact/dimension clusters), business entities, measures and
dimensions; edges from column `references` (reference), from `relationships` (relationship),
from domain (dependency) and from `source_table` (maps_to); degree computed per node; clusters
derived from node kind and table type. The snapshot is cached and ETag'd; the client fetches
it once per industry and does all layout work locally — with force and centrality layouts on a
Web Worker.

## 8. Performance strategy against the §19 targets

| Target | Mechanism |
| --- | --- |
| Navigation < 100 ms | App Router prefetch, route-level code splitting, cached snapshots |
| Theme toggle < 50 ms | CSS custom properties on `<html>`, `class` strategy, no re-render |
| Node drawer immediate | Drawer reads from the already-loaded snapshot; zero network |
| First stream event prompt | `stage` frame emitted before any LLM call |
| 2 M rows per database | SQL-only aggregation, indexed date/join keys, materialized views for executive metrics, keyset pagination, row cap, statement timeout |
| No full fact DataFrames | Enforced by the guardrail layer plus a hard `SQL_MAX_RESULT_ROWS` |
| Ontology 500+ nodes / 2000+ edges | Snapshot pre-normalised, layouts memoized, worker-computed, React Flow `onlyRenderVisibleElements` |

## 9. Security posture

Argon2id password hashing. Short-lived JWT access tokens plus rotating refresh tokens stored
hashed, with reuse detection that revokes the whole family. HttpOnly + Secure + SameSite
cookies, double-submit CSRF token for cookie-authenticated mutations. CORS allowlist. Login
rate limiting per identifier and per IP. Read-only SQL with a guardrail allowlist. Upload
content-type and magic-byte validation with a size cap. Prompt-injection defence: retrieved
content is wrapped as untrusted data and can never alter system instructions. SSRF-safe web
retrieval behind a domain allowlist with private-IP rejection. Role checks on every route.
Audit logging for authentication and data access. Secret redaction in all log sinks.
No `eval`, no unsanitised HTML.

## 10. Deployment

`apps/web` deploys to Vercel with root directory `apps/web`. `apps/api` builds from
`apps/api/Dockerfile` and runs on Railway/Render/Fly behind Uvicorn. PostgreSQL, MongoDB and
Qdrant are configured entirely by environment variable. `docker-compose.yml` brings up
PostgreSQL, MongoDB, Qdrant and the API for local development; the web app runs with
`npm run dev`. Windows startup scripts live in `scripts/`.
