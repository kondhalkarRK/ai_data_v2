# Ask Me — verified codebase context

Verified against implementation on 2026-11-06. This describes code, not a claim that
the configured warehouse, LLM providers or hosted deployment were tested live.

## Architecture

AskBI now takes precedence for automotive when `ASK_ME_ASKBI_ENABLED` (API) and
`NEXT_PUBLIC_ASK_ME_ASKBI_ENABLED` (frontend build) are enabled. Both default off.
It restores Custom Report / Auto Report · AskBI, preserving Custom, insurance and
general AI Chat. `components/analytics-builder/askbi/` calls `/analytics/bi/*`;
`app/services/analytics/bi/` owns finite interpretation, clarification, semantic
validation, execution and signed-evidence narration. `BiReportRecord` stores
owner/scope-bound reports and revisions through additive migration
`0014_bi_reports`. Variable one-to-six-panel plans replace fixed board recipes.
Day/week calendar compilation is opt-in; chart-only edits reuse results.
The separately gated advanced path supports only validated z-score/index-to-average
benchmarks, not unrestricted SQL. SQLGlot is the only added runtime dependency;
no agents were added. See `ASKBI_IMPLEMENTATION.md` for verified checks,
deployment precedence, rollback and outstanding live/advanced-coverage limits.
An exact undated metric-by-breakdown request such as “total sales by region”
uses the last completed calendar month with an explicit assumption, avoiding
an LLM call for that supported request. Six exact automotive leadership
starter prompts now produce distinct reports. The first five display two KPIs
and four charts. The sixth, Revenue Lift, displays two KPIs and three charts,
with an additional governed regional comparison query. Its prior aligned
revenue and region results support a local
5–30% target slider and reconciled observed regional changes without extra LLM
calls. The refreshed report canvas shows the originating question, one title,
metric-consistent chart accents, a wide primary chart, compact panel options,
dates, make, evidence briefing and grouped charts. A
server-validated year/month/week/make filter updates all panels without an LLM
call; the region/dealer report can also narrow to a permitted region. Current
and previous results remain distinct. Browser Save as PDF uses a report-only
light paper layout, then restores the active screen theme.
Optional `outlook-draft.ts` uses a configured Entra SPA and delegated Graph
`Mail.ReadWrite` to create an unsent draft with current KPIs, up to three inline
chart images, the full PDF and an owner-scoped saved-report link. Manual mailto
remains available. See `ASKBI_LEADERSHIP_REPORT_PLAN.md` for office QA limits.

Unified Analytics Builder is implemented behind disabled-by-default
`ASK_ME_ANALYTICS_WORKSPACE_ENABLED` / `NEXT_PUBLIC_ASK_ME_ANALYTICS_WORKSPACE_ENABLED`.
The automotive-only plan endpoint uses strict response contracts and semantic
catalog validation; the experimental `analytics-workspace.tsx` renders variable
panels through the existing governed runner, including daily automotive trends.
Owner-scoped saved workspaces and conversation turns use the additive
`0013_analytics_workspaces` migration. Existing analyses and Auto boards can be
imported without changing originals. Narration uses signed evidence and bounded
LLM curation; core results never wait for it. No agents/dependencies were added.
Live deployment acceptance remains blocked by failed configured application and
automotive database connections; the migration was not applied to those databases.
See `UNIFIED_ANALYTICS_BUILDER_IMPLEMENTATION.md` for verified scope and rollback.

- `apps/web`: Next.js 16 App Router, React 19, TypeScript, Tailwind 4, Radix,
  TanStack Query for server state, Zustand for browser UI preferences, next-themes.
  Charts are custom SVG; ontology uses React Flow and graph layout helpers.
- `apps/api`: FastAPI, Pydantic 2, async SQLAlchemy/psycopg and Alembic.
  `app/api/router.py` assembles versioned routes; `app/services/` owns orchestration.
- `packages/shared-types/src/index.ts`: TypeScript API contracts mirrored from
  backend schemas. Keep both sides aligned when changing contracts.
- PostgreSQL application state is separate from automotive and insurance analytics
  pools. Analytics transactions are read-only, limited and timed out.
  App state includes auth, conversations, history, saved analyses, governance,
  reliability, document metadata and durable ingestion jobs.
- `apps/api/semantic/packs/{automotive,insurance}`: governed YAML models,
  glossary, chat vocabulary and entity catalog. Semantic snapshots are cached.
- `database/`, API `migrations/`, and `scripts/` contain bootstrap, migration,
  seeding and local startup tooling. Docker Compose includes PostgreSQL, MongoDB,
  Qdrant and API. Next.js/Vercel is the frontend deployment boundary.

## Modules and API connections

- AI Chat: `components/chat/`, `hooks/use-chat-ask.ts` -> `/chat/*`.
  Classic and optional New Chat currently call `ask-sync`, receiving an array
  of backend events. SSE `ask` and a Next.js streaming proxy also exist.
- Executive Intelligence: `components/executive/`, particularly `cockpit/` ->
  `/executive/*`, `/kpis/*`: domain KPIs, trends, comparisons, geographic and
  dealer/model exploration, insights and scenario functionality.
- Analytics Builder: `components/analytics-builder/`, `hooks/use-analytics.ts`
  -> `/analytics/*` -> backend catalog, compiler and runner. Structured specs
  are validated, compiled and executed; analyses can be saved and duplicated.
  AskBI is the newest optional automotive Auto mode, described above. With its
  flag disabled, legacy precedence and implementations remain available.
  Automotive has optional Auto / Custom modes (`builder-modes.tsx`). Custom
  is unchanged/default; insurance retains its original Builder. Auto (`askwiz.tsx`)
  generates sales boards from predefined KPI recipes and bounded LLM intent,
  with AskChart edits and separate evidence-curated LLM narration. New
  `/analytics/auto/*` routes use `services/analytics/askwiz.py` and owner-scoped
  `auto_dashboards` specifications (migration `0012_auto_dashboards`, not applied
  during development). Daily compilation is explicitly opt-in for automotive
  Auto; existing compiler/runner defaults remain unchanged. No agents/dependencies.
  See `docs/ASKWIZ_IMPLEMENTATION.md` for activation, flags, query budgets,
  cache/deployment limits and verification evidence.
- Data Trust: `components/reliability/` -> `/trust/reliability*`: scoring,
  dimensions, rules, monitors, alerts, freshness, drift and trends. Older trust
  endpoints/components coexist with the current reliability experience.
- Semantic Atlas: `components/semantic/` -> `/semantic/pack`; business and
  technical views use the same pack. `components/ontology/` uses the compiled
  `/semantic/ontology` snapshot. This is not a separate graph database.
- Knowledge Hub: `/knowledge` -> `/documents/*` -> `services/knowledge.py` and
  `app/rag/`. Enabled RAG uses PostgreSQL metadata/jobs, blob storage, real
  embeddings, Qdrant and ACL filtering. Legacy filesystem/hash retrieval also
  exists. Document mutations require `ASK_ME_RAG_ENABLED`.
  Local Hugging Face/SentenceTransformer loading was removed on 2026-11-06.
  Traditional RAG requires an explicitly configured OpenAI-compatible embeddings
  API and model; old `sentence_transformers` settings fail with migration guidance.
  Readiness runs blocking vector/embedding probes in threads with bounded waits.
- Admin: `components/admin/` -> `/admin/*`, `/catalog/*`: LLM settings,
  governance, usage/cost, trust, semantic/catalog refresh and audit.
- Supporting pages: Home/readiness, Data Preview/export, Query History, Saved
  Questions and personal AI usage. Legacy Data Sources, System Logs, LLM
  Observability and Cost Analytics routes redirect to consolidated pages.

## Question pipeline and security

Input -> session, industry, region and quota checks -> conversation memory ->
route classification -> spelling/glossary/entity/value/period resolution ->
semantic plan -> governed SQL or validated LLM drafting/repair/fallback -> SQL
safety, plan/schema coverage, EXPLAIN, region enforcement, limit and timeout ->
read-only execution -> chart/narrative/trust/citations/follow-ups -> history,
memory and usage persistence -> frontend event folding.

Key files: `app/services/chat/service.py`, `pipeline.py`, `decision_engine.py`,
`semantic_query_planner.py`, `semantic_context.py`, `llm_assist.py`,
`app/analytics/sql_guardrails.py`, `app/services/security/region_scope.py`.

Authentication uses Argon2 passwords, JWT access cookies, rotating refresh
families, CSRF and audit. Actual roles are `user` and `admin`; older README
claims about three roles are stale. Backend dependencies enforce access; frontend
navigation hiding is not the security boundary. Region scope also constrains
SQL execution, retrieval and conversational context.

## UI, themes and metric transitions

`app/(workspace)/` owns routes; `lib/navigation.ts` owns navigation;
`components/shell/` and `components/ui/` supply shared chrome/primitives.
`app/globals.css`, `lib/surface.ts`, `lib/design.ts` and `lib/chart-colors.ts`
define shared tokens and presentation. `app/providers.tsx` maps Light, Dark and
AI to `light`, `dark`, `theme-ai`; persistence key is `nql-theme`.
Tailwind `dark:` matches both Dark and AI.

November 3 redesign reports mark phases complete, but their palette claims
predate current CSS. On November 4, AI surfaces were softened to restrained
indigo with violet/cyan accents and reduced glow. AI chart tokens are distinct
from Dark. Cockpit fixed colors now use AI-only CSS overrides with original
Light/Dark fallbacks; SVG export resolves computed paints and gradient stops.
`tint()` accepts token-based colors as well as hex.

`hooks/use-count-up.ts` defaults to 700 ms easing, runs once on viewport entry,
then transitions from its current value on numeric changes. It cancels interrupted
frames, settles on reduced motion and does not restart for unrelated renders.
`components/ui/animated-number.tsx` keeps the final formatted value available to
assistive technology and marks animated text decorative. Missing/nonfinite values
remain an em dash. Existing INR/percentage formatters remain in use.
Dashboard KPI grids and Data Trust score/dimension/summary tiles use these shared
utilities. Executive filter refetches retain previous values within an industry;
the application does not invent intermediate datasets or change calculations.

## Configuration, validation and risks

### Development environment constraint (user confirmed)

This laptop is a code-development environment without a local PostgreSQL or LLM
service setup. Do not attempt live PostgreSQL connectivity, apply database
migrations, or call live LLM providers during routine development verification
unless the user explicitly requests those checks or supplies a configured test
environment. Their absence is expected, not a code defect or a reason to hold up
implementation. Continue mocked LLM tests, SQLite persistence tests, semantic
compiler/numerical/security tests, frontend/component tests, typecheck, lint and
builds. Report live integration checks as not applicable to this environment;
never claim they passed. Keep migrations ready for the configured deployment.

### AI-Augmented Executive Intelligence (2026-11-04)

Both active dashboard paths now wrap existing charts/KPIs with
`components/executive/dashboard-intelligence.tsx`: three deterministic briefing
observations at most, supported Explain actions, one contextual question/evidence
drawer and segment application. Automotive supports revenue/units/orders by
zone/make/model using the existing grouped scan. Insurance supports premium and
claim-count drivers by region/LOB with one bounded on-demand SELECT; loss ratio
uses captured numerator/denominator effects in percentage points. Existing chart
engines, exports, metric formulas and animation utilities are retained.

`app/schemas/dashboard.py`, `app/services/executive/dashboard.py` and
`app/api/routes/dashboard.py` implement optional executive `augmentation` metadata,
POST `/executive/explain` and POST `/executive/ask`. The server binds result
handles to user/role/industry/region scope/semantic revision, rechecks access and
does not accept client numeric facts or SQL. Current/prior dates come from the
domain services. Residuals reconcile additive effects; ratio effects use a
symmetric decomposition. On-demand insurance evidence exposes its timestamp and
warns when totals changed. A Data Trust link opens its existing overview, not a
new metric-specific quality endpoint.

Known questions are deterministic. Unrecognized wording may use one bounded
existing LLM classification into allowlisted metric/dimension/operation; no
agents, tool calling, generated SQL or new dependencies. Ask uses existing
quota/audit/usage/conversation tables, with dashboard-scoped memory. Explain works
without AI quota. The old unreferenced `AskDashboardAi` was reviewed and remains
unused because its general-chat payload lacks dashboard filters.

`hooks/use-debounced-value.ts`, `hooks/use-retained-query-data.ts` and
`lib/executive/dashboard.ts` coordinate selection changes and supported filter
merging. Requests are abortable and key-isolated; prior results remain labelled
during updates/failures. The drawer retains its captured scope until the user
explicitly adopts a current selection. Core charts never await optional AI.

Rollback: set `ASK_ME_AUGMENTED_DASHBOARD_ENABLED=false` server-side and
`NEXT_PUBLIC_ASK_ME_AUGMENTED_DASHBOARD_ENABLED=false` for the frontend build.
Both default true. No schema migration. Handles currently live in a bounded
process-local store (256, 10-minute TTL); single-worker or sticky routing is
required. Restart/expiry/eviction asks for refresh. Non-sticky multiworker rollout
needs shared storage.

Executive augmentation checkpoint: 118 selected backend tests, 24 frontend files / 130 tests,
TypeScript, changed-frontend lint and targeted strict mypy passed. Isolated
Chromium used synthetic API fixtures across both industries/three themes and
tablet; it was not live end-to-end verification. Local 100-run assembly/handle
benchmark p95 2.858 ms excludes database/network/LLM work. The current production
build was then unverified (font DNS, then offline-mocked prerender EPERM; escalation
declined). Subsequent AskWiz verification passed a full production webpack build
outside the sandbox, along with 127 selected backend cases and 135 frontend tests.
See `docs/AI_AUGMENTED_DASHBOARD_PLAN.md` section 13 for exact delivery scope,
verification limitations and outstanding Phase 4 live/pilot gates.

- `app/core/config.py`, `.env.example`, `apps/web/next.config.ts` define settings.
  Important switches: auth bypass (development only on API), New Chat UI, RAG,
  chat router/classifier/general knowledge, LLM reasoning mode and web retrieval.
- Admin-governed LLM settings feed HTTP chat completions with timeouts, retries,
  fallback and circuit breaker. Default provider/model/pricing catalog path is
  outside this application: `../config/llm_catalog.py`; portability must account
  for it. Credentials stay server-side.
- API startup performs schema repairs and catalog refreshes; starting it is not
  read-only. Do not use it for casual inspection of a shared database.
- Frontend Vitest covers UI, routing, graphs, formatting, SSE and API helpers.
  Animation regression tests cover interruptions, reduced motion, formatting,
  missing values and token tinting. Backend pytest covers auth, NLQ, memory,
  scope/RBAC, RAG, analytics and reliability; many cases use SQLite/mocks.
  Live warehouse/provider behavior needs separate integration verification.
- November 4 frontend test run: 23 files / 123 tests passed. Existing lint errors
  remain in untouched files (12 errors); lint of changed code is clean. Typecheck
  passes. Production build passes with `next build --webpack`; the default
  Turbopack attempt hit a CSS worker launch failure after an earlier font network
  failure. Isolated Chromium component checks passed across three themes,
  desktop/tablet layouts, updates, rapid updates, reduced motion, unavailable
  scores and chart PNG export. These use explicit verification fixtures, not a
  live warehouse/API session. The reference video was not available.
- High-risk boundaries: metric formulas/joins, SQL validation and regional
  rewriting, cache keys, follow-up memory, RAG ACLs, duplicated Classic/New Chat
  request flows, and shared theme tokens. Preserve all when making UI changes.
- Git metadata is in the parent repository; git was unavailable on the exploration
  PATH. Reflog names include `newui`, `recall`, `uichange`, `uiux`, `ui2`; commit
  diffs and a baseline working-tree status were not verified.
