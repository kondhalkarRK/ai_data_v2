# AskBI implementation and deployment

Verified 2026-11-05. Automotive only. This records implemented code and offline
checks; it does not certify a live PostgreSQL/LLM deployment or WrenAI parity.

## What changed

Analytics Builder now offers **Custom Report** and **Auto Report · AskBI** when
the new feature flag is enabled. Custom remains the default. Insurance and general
AI Chat keep their existing paths. A report canvas and one responsive conversation
sidebar replace the fixed AskWiz composition for the new Auto mode.

AskBI supports a single value, chart, table or report with one to six panels;
there is no mandatory four-chart layout. The existing LLM interprets novel
questions and contextual follow-ups into governed specifications. Exact supported
initial requests reuse templates, and local chart presentation edits reuse data.
Metric definitions remain in the semantic catalog, not model-generated formulas.

Four exact leadership starter questions now appear on the empty Auto Report
canvas. Send creates a fixed two-KPI/four-chart automotive report for CFO, CEO,
regional or sales leadership, with last completed week/month dates and governed
metric definitions. The CFO question also accepts “monthly” in place of “weekly”.
The LLM remains available for novel follow-ups and optional evidence narration.
The report groups KPI cards, trend and ranked breakdowns for readable alignment.
“Export PDF” opens the browser print dialog only after all panels have current
results; choose Save as PDF. “Email draft” opens the default mail application
with a subject and period and instructs the user to attach that PDF. This is a
manual handoff, not automatic Outlook delivery or an attached message. The
authenticated Microsoft Graph integration needed for automatic delivery remains
unimplemented. See `ASKBI_LEADERSHIP_REPORT_PLAN.md`.

Server-owned state preserves clarification questions and answers, selected-panel
context, report revisions and recent conversation. Typed failures retain the
report. Idempotency receipts prevent duplicate mutations; stale revisions conflict
instead of silently overwriting edits. Save/open, rename, reorder, remove, refresh
and one-step Undo are available. Legacy reports can be imported without changing
their originals, subject to the limitations below.

Results load independently, with at most two concurrent panel requests. Narration
starts after core results and cannot prevent charts from being used. Evidence is
signed against user, permission scope, report revision, semantic revision and query
specification. Narration can reference only validated facts; deterministic text
remains available when the provider fails. Previous results, updating panels and
failed panels have distinct states. Request sequencing prevents old responses from
replacing a newer report.

## Code map and flow

- Frontend entry: `apps/web/components/analytics-builder/builder-modes.tsx`.
- AskBI UI/state: `apps/web/components/analytics-builder/askbi/`; existing
  `analytics-workspace.tsx` exports its panel renderer for reuse.
- HTTP endpoints: `apps/api/app/api/routes/analytics.py`, `/analytics/bi/*`.
  Capabilities, owned report create/list/get, turns, panel execution and narration.
- Contracts: `apps/api/app/schemas/bi.py` and
  `packages/shared-types/src/index.ts`.
- Backend: `apps/api/app/services/analytics/bi/`: `repository.py` owns scope and
  persistence; `service.py` coordinates finite turns; `planning.py` validates
  semantic plans; `calendar.py` handles calendar grains; `advanced.py` validates
  bounded benchmark SQL; `execution.py` runs queries and signs facts; `llm.py`
  enforces quotas and records usage.
- Persistence: `app/models/bi_report.py`, migration `0014_bi_reports` after
  `0013_analytics_workspaces`. New table; existing report tables are preserved.

Question -> authenticated automotive context -> owned report/revision -> exact
template or bounded LLM interpretation -> semantic/date/scope/value validation ->
persisted plan -> governed read-only compiler/runner -> individual panel results
and signed facts -> optional bounded narration. No agents, tool calling or
autonomous planning loops were introduced.

Day/week grains are opt-in for AskBI. Calendar moving averages preserve missing
observations and return unavailable windows instead of inventing zero sales.
Ratios reuse catalog formulas. Comparisons validate requested date scope, and
current-day results disclose incomplete-day limitations. Advanced benchmarks
compute over the full governed aggregate before applying display limits.

## Enable on the office laptop

1. Update the checkout and API environment dependencies using the normal project
   install process. The only new runtime dependency is `sqlglot>=30,<31`.
2. From `apps/api`, activate the project environment, then run:

   ```powershell
   python -m alembic upgrade head
   python -m alembic current
   ```

   The application database should report `0014_bi_reports`. This migration was
   **not applied on the development laptop**.
3. Set the API environment:

   ```dotenv
   ASK_ME_ASKBI_ENABLED=true
   ASK_ME_ASKBI_ADVANCED_ENABLED=false
   ```

4. Set the frontend build environment, normally `apps/web/.env.local`:

   ```dotenv
   NEXT_PUBLIC_ASK_ME_ASKBI_ENABLED=true
   ```

   Do not assume a root `.env` is automatically loaded by Next.js. Public flags
   are compiled into the browser bundle. Restart the API and rebuild/restart web.
   `.env.example` is a template and is never loaded as runtime configuration.
   It contains all setting names from the local root `.env`, with safe example
   values; credentials must stay in the ignored environment files. Seeing
   **Auto · AskWiz** means the frontend selected its legacy flag branch. Check
   `apps/web/.env.local` and restart/rebuild the actual running web checkout.
5. Select Automotive -> Analytics Builder -> **Auto Report · AskBI**. The initial
   Custom Report view is intentional. The new flag takes precedence over both the
   unified-workspace and AskWiz flags; those flags need not be changed to false.
6. Processing/deployment details should identify `askbi-v2`, schema `2` and
   expected migration `0014_bi_reports`. Capability metadata reports the expected
   migration, not a live check that the database has applied it. An API flag or
   engine mismatch produces an actionable message instead of silently loading old
   AskWiz. If the mode itself is old, check the deployed frontend build/flag.

Legacy source discovery still uses its existing endpoints and feature flags.
Keep the relevant old flags enabled if users need to browse/import those sources.

Rollback: turn off the API/public AskBI flags and rebuild web. Existing unified
workspace/AskWiz flags then determine the previous experience. To restore old
Custom/AskWiz specifically, also disable the unified-workspace public flag. Keep
the additive table; no destructive downgrade is necessary.

## Verification

- 117 offline backend tests passed across AskBI, workspace, AskWiz, builder and
  region-security suites. These use semantic/compiler fixtures, mocked providers
  and local SQLite; none require live PostgreSQL or an LLM.
- Tests cover arithmetic for weighted ratios and benchmarks, calendar SQL,
  SQL AST rejection, signed evidence, owner/revision/idempotency behavior,
  clarification and follow-ups, date/comparison consistency, CSRF and strict HTTP
  contracts. Compiled SQL arithmetic checked through SQLite is not proof of live
  PostgreSQL execution.
- Full frontend suite: 27 files / 147 tests passed. The seven AskBI tests passed
  again after the final request-state changes.
- Targeted backend Ruff and mypy checks passed. Frontend targeted ESLint and
  typecheck passed. The production webpack build passed with AskBI enabled;
  its existing Google Fonts download required network access outside the sandbox.
- `scripts/verify-askbi.mjs` runs Chrome against the real Next UI with synthetic
  HTTP fixtures. It verified clarification, presentation edits without another
  query, retained state across mode switches, all three themes at 1440/820 widths,
  reduced-motion configuration, keyboard drawer dismissal and flag mismatch;
  no browser page errors. The final run passed against the production build.
  A second fixture run after the leadership UI changes passed. The fixture uses
  a one-panel reply, so it does not visually validate the six-panel layout or
  final printed PDF. Those need office data or a dedicated six-panel fixture.
  Start web on port 3000 and run `node scripts/verify-askbi.mjs` from the repo root;
  set `ASKBI_BASE_URL` to use another local port. Screenshots were visually inspected. This is fixture
  verification, not a live end-to-end database/provider test.
- Alembic offline SQL generation passed; migration execution remains for office.
- No tests were added solely for fonts or cosmetic styling. Git was unavailable
  on PATH, so no Git-based baseline/diff verification was possible.

## Limits and remaining release gates

- Advanced SQL is deliberately restricted to `z_score` and `index_to_average`
  for one categorical breakdown, with at most one advanced panel per report.
  It is separately disabled by default. A parsed SQL AST must match the approved
  calculation over catalog-compiled input; there is no unrestricted generated SQL
  or broad Wren/NQL-equivalent analytical coverage. SQLGlot is a parser dependency,
  not an agent framework. Advanced office acceptance is required before enabling.
- Each panel has one governed metric; multiple metrics require separate panels.
  Unsupported calculations, unavailable measures and incompatible shapes return
  a limitation or clarification rather than substituting a different analysis.
- Narration curates server-generated facts with constrained connective text. It
  does not offer unrestricted prose or claim causal explanations. Generic panel
  summaries do not sum ratio or distinct-count rows into misleading totals.
- Legacy Custom imports currently require explicitly saved start/end dates and
  a compatible single-metric specification. Legacy import is not a universal
  converter for every old workspace/specification.
- Six distinct panel data queries is a composition limit, not a total database
  round-trip limit. Value validation, freshness, transaction setup and advanced
  EXPLAIN add calls. Panel counts/timing and LLM usage are exposed; turn-level
  validation query counts are returned in usage metadata. No latency target or
  token reduction percentage has been established against real services.
- No durable background jobs, streamed stage events or cross-request server result
  cache were added. Browser cancellation suppresses obsolete responses; it does
  not guarantee immediate server/database cancellation. Execution timeouts bound
  server work. Evidence expires after ten minutes.
- Office acceptance still needs real sales fixtures and provider responses for
  totals, last-week daily sales, ambiguous dates, regional follow-ups, rolling
  averages, comparisons, no-data/provider failures, save/import/refresh, and
  multi-user permissions. Measure first-result/report latency and auxiliary query
  counts there against the plan's proposed 3s/8s/15s p95 targets. Those targets
  remain unmeasured; no local connectivity tests were attempted.

The implemented foundation is ready for office acceptance behind a reversible
flag. Broad advanced-analysis parity and live operational acceptance remain open.
