# NQL Insight — Phased Delivery Plan

Each phase is validated before the next begins. The legacy Streamlit application stays
untouched and runnable until Phase 7 parity passes.

---

## Phase 1 — Foundation

**Scope.** Standalone monorepo, authentication, API foundation, shared design system,
RAISE-inspired shell, health endpoints.

Backend: settings, async engines for three databases, `askdb_app` schema (users, refresh
tokens, auth audit), Argon2id hashing, JWT access + rotating refresh with reuse detection,
role model, login rate limiting, security headers, CORS allowlist, structured logging with
secret redaction, `/health`, `/ready`, protected `/api/v1/diagnostics/*`, Alembic baseline,
`scripts/create_admin.py`.

Frontend: Next.js App Router with TypeScript strict, Tailwind design tokens for light and dark,
shadcn/ui primitives, TanStack Query + Zustand providers, login page, authenticated shell with
left sidebar / top bar / main tabs, theme toggle, loading system with skeletons and rotating
status messages, error and empty states.

**Acceptance.** `npm run typecheck` and `ruff` + `mypy --strict` clean. Login with a
CLI-seeded admin returns cookies; refresh rotates; reuse of a rotated token revokes the
family. Six failed logins in a minute are rate-limited. `/ready` reports every dependency.
Unauthenticated access to any `/api/v1` route except auth returns 401. Theme toggle measured
under 50 ms. Playwright covers login, logout and theme.

**Blocked on.** Brand assets — see "Open blockers" below.

---

## Phase 2 — Semantic layer

**Scope.** Pack registry loaded from YAML at startup, `SemanticService`, ontology snapshot
compiler, `/semantic` capability hub, Ontology Browser, industry switching end to end.

**Acceptance.** Snapshot for both industries validates against the `{nodes, edges, clusters,
metadata}` schema. Snapshot parse plus force layout for 500 nodes / 2000 edges stays under
200 ms in the worker benchmark. Node drawer opens with zero network requests. Force,
centrality and hierarchy layouts all render, with search, filter, zoom, fit, reset, cluster
chips, egonet focus, edge tracing and drag. Switching industry updates pack, ontology, KPI
registry, glossary, suggested questions and RAG filter in one transition, with no file
mutation on disk.

---

## Phase 3 — Analytics databases

**Scope.** Alembic migrations for `askdb_automotive` (schema `automotive` star schema)
and `askdb_insurance`; seed generators at **1M** rows now (raise to 2M later); industry routing;
Data Preview; Data Quality.

**Acceptance.** Both databases migrate from empty. Primary and foreign keys, date and join-key
indexes present. Every generated query is schema-qualified. Analytics sessions are read-only
with a statement timeout and a row cap; a `DELETE` attempt is rejected by guardrails *and* by
the transaction mode. Data Preview paginates server-side and never returns more than the cap.
`EXPLAIN` smoke tests on 2 M rows show index usage on date and join predicates. Data Quality
reproduces the legacy scoring formula exactly on a fixture.

---

## Phase 4 — Executive Dashboard

**Scope.** Industry metric registries, KPI cards, charts, filters, drill-down, cross-filtering,
period comparison, export, presenter mode, materialized views for expensive metrics, and
Scenario Mode kept strictly separate from actual reporting.

**Acceptance.** Every insurance KPI matches the legacy `insurance_kpi_engine` output on a
fixed window. Every automotive KPI matches the legacy `kpi_engine` pandas formula on the same
data, now computed in SQL. Scenario Mode is visible only when forecast data exists, is labelled,
never overwrites actual metrics, shows Actual versus Scenario, and has a reset.

---

## Phase 5 — AI Chat

**Scope.** SSE chat with full parity against `ui/tab_query.py`, SQL drawer, trust score,
result table and chart, follow-ups, cancel, retry, saved questions, query history, cost
analytics.

**Acceptance.** The golden NLQ question set from `tools/golden_insurance_nlq_smoke.py` and
`doc/insurance_test_questions.md` produces equivalent SQL and identical numbers. The first SSE
frame arrives before the LLM call. Cancellation stops generation and persists a cancelled
record. Trust score reproduces the legacy four-component calculation. Token and cost figures
reconcile with `llm_usage`.

---

## Phase 6 — RAG

**Scope.** MongoDB collections, Qdrant collections, authenticated ingestion, parsing,
chunking, embedding, hybrid retrieval, deduplication, citations, versioning, reindex and
delete, retrieval audit, and opt-in web retrieval.

**Acceptance.** Upload → parse → chunk → embed → upsert → retrieve → cite works for PDF,
DOCX, TXT, Markdown and HTML. Industry filtering never leaks documents across industries.
Every RAG claim carries a citation. Web retrieval is off by default, requires explicit
per-query opt-in, honours the domain allowlist, rejects private addresses, and its content is
labelled untrusted. A prompt-injection corpus fails to alter system behaviour. Numbers still
come only from PostgreSQL.

---

## Phase 7 — Hardening and deployment

**Scope.** Performance validation against §19, security checklist, accessibility pass, Vercel
deployment, containerised API deployment, full parity validation.

**Acceptance.** All §19 targets measured and met or documented. Security checklist complete.
`askdb/` contains no Streamlit dependency and no import from the parent directory. Parity
checklist signed off. Only then may the legacy application be retired.

---

## Open blockers

These are reported rather than guessed, per §24.

1. **Logo asset.** Spec §8 requires replacing the ASK-DB logo with the logo attached to the
   implementation request and says to stop before branding implementation if it is absent.
   No logo file is attached. The only images in the repository are
   `assets/ask_db_logo.png` (the old ASK-DB mark) and `1.png` (a screenshot of the existing
   Streamlit LLMOps panel). Nothing will be invented or redrawn.
2. **RAISE screenshots.** Spec §9 and §11 reference attached RAISE screenshots as alignment
   references. They are not attached. The shell is being built to the written specification —
   sidebar items, top bar, main tabs, spacing and card treatment — and can be realigned once
   the screenshots arrive.
3. **Automotive analytics data.** Implemented: schema `automotive`, required `dealer_id`,
   1M-row deterministic seed. Insurance schema and 1M-claim seed are also in place.
4. **Infrastructure.** `docker`, `psql` and `git` may not be on PATH on every machine, so
   migrations, seeds and container builds need a reachable PostgreSQL (and later MongoDB /
   Qdrant). Everything is written to be runnable with Windows scripts.
5. **LLM credentials.** No `LLM_API_KEY` is available in this environment. Phases 5 and 6
   need one to run end to end; no credential will be fabricated or hard-coded.
