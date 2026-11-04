# AskWiz — automotive Auto Analytics Builder

Implemented 2026-11-04. Automotive only. Insurance keeps the existing Builder;
Custom remains the initial mode and keeps its existing assistance, charts,
saved analyses, exports and interactions. No agent integration or new dependency.

## User flow

Choose **Analytics Builder → Auto · AskWiz**. Ask “Generate a report of last week
on daily sales”, or choose a starter recipe. Up to six distinct charts plus the
three governed headline KPIs (revenue, units, orders) are generated. Exact dates,
prior dates, timezone, filters, freshness, SQL and underlying data are visible.
AskChart can change a selected/numbered chart, add/remove supported views, apply
board-wide date/filter changes, or request evidence. Undo swaps the most recent
definition. Save/reopen persists fixed dates, never silently rolls “last week”.

## Processing and cost

- Five versioned automotive recipes: sales, weekly, models, regions and growth.
  Charts use allowed metrics/dimensions and are validated together before SQL.
  These are governed specifications, never canned result data.
- Free-form creation uses at most one existing `complete_text` call to interpret
  a constrained JSON intent. Template buttons bypass interpretation. Simple chart
  type/removal/board-period edits are deterministic. Invalid model output is not
  executed. An unrecognized filter never silently disappears in offline fallback.
  Successfully parsed intents have a bounded 128-entry, ten-minute cache keyed
  by user/role/scope, semantic revision, instruction and existing board context;
  every reused proposal is still validated before execution.
- The ordinary Analytics Builder catalog/compiler/runner executes the analyses.
  Daily grain is an opt-in automotive extension of compilation; Custom and
  insurance keep their previous capabilities. Optional driver queries are off.
- Queries execute serially on the existing region-scoped read-only connection.
  Savepoints isolate failures; the default board execution budget is 20 seconds,
  in addition to existing SQL statement timeouts. Successful charts survive a
  failed chart. Cancellation does not claim proof of immediate warehouse stop.
- Four distinct charts normally use six result SELECTs (including two shared
  current/prior aggregate queries) plus six freshness SELECTs and two transaction/
  timeout configuration calls: 14 application `execute` calls. Six-chart boards
  have at most eight unique result SELECTs plus their freshness checks. Implicit
  transaction/savepoint protocol SQL is not counted by that meter.
- Five-minute, 256-entry process-local results cache includes owner, role,
  permission scope, semantic revision, resolved dates, filters, metric and grain.
  Visualization type is excluded. Unchanged results and presentation edits use
  zero warehouse calls on cache hits. Cold/evicted entries safely rerun; zero
  calls are not promised after eviction or on another worker.
- Charts return before the separate optional narration request. The LLM selects
  and orders up to three evidence statements; exact factual wording comes from
  governed calculations. This is **AI-curated narration**, not unrestricted model
  prose or causal analysis. No raw dataset is sent to the LLM. Narration is cache
  only and cannot launch more warehouse queries. Matching evidence/definitions
  reuse a bounded narration cache. Multiworker cache misses can omit narration;
  shared result storage is needed for reliable cross-worker reuse.
- Model calls/tokens are recorded in `LlmUsage` with purpose `askwiz`; existing
  quotas apply to model work. Costs are catalog estimates, falling back to the
  existing governance per-token estimate when the model lacks a catalog match.
  Templates, cached results and compatible deterministic edits remain available
  without a working provider. No live token-cost reduction percentage is claimed.

## Security, storage and activation

Every new endpoint enforces automotive eligibility and feature flag checks.
Existing authentication, CSRF and scoped analytics dependencies remain the
boundary. Clients send board/revision references and instructions, not SQL or
authoritative numbers. Owner checks, scope rechecks and conditional revision
updates protect reopen/edits; access changes require a new board.

New table `auto_dashboards` stores owner-scoped versioned definitions and one
undo definition. It is separate from single-analysis storage. No warehouse rows
are persisted there. **Apply Alembic migration `0012_auto_dashboards` before
using Auto.** Migration SQL generation and the revision chain were verified;
the migration was not applied to the configured database during development.

From `apps/api`, use the project's environment and normal migration deployment
process (`python -m alembic upgrade head`). Then restart the API/web deployment.

Configuration:

- `ASK_ME_ASKWIZ_ENABLED=true`: API eligibility; false disables all Auto endpoints.
- `NEXT_PUBLIC_ASK_ME_ASKWIZ_ENABLED=true`: frontend availability; rebuild when
  changing. False restores the original Builder-only experience.
- `ASKWIZ_TIMEZONE=Asia/Kolkata`: server calendar; weeks start Monday.
- `ASKWIZ_RUN_TIMEOUT_SECONDS=20`: bounded run budget, configurable 5–60 seconds.

Relative calendar dates use the configured current business date, not the latest
warehouse date. Week-to-date comparisons align elapsed calendar days; they are
not same-hour comparisons. “Second week” asks for clarification. Missing days
are not zero-filled. Monthly/year-to-date comparisons expose exact date ranges;
calendar lengths can differ. Current-day completeness cannot be inferred from a
date-only warehouse watermark.

## Important files

- UI: `apps/web/components/analytics-builder/builder-modes.tsx`, `askwiz.tsx`.
- API: `apps/api/app/api/routes/askwiz.py`, `app/schemas/askwiz.py`.
- Services: `apps/api/app/services/analytics/askwiz.py`; optional compiler/runner
  arguments preserve existing callers. Shared `ResultChart.hideControls` defaults
  false and is enabled only by Auto.
- Persistence: `app/models/askwiz.py`, `migrations/versions/0012_auto_dashboards.py`.
- Contracts: `packages/shared-types/src/index.ts`.
- Tests: `apps/api/tests/test_askwiz.py`,
  `apps/web/tests/unit/askwiz.test.tsx`, existing analytics/security/dashboard suites.

## Verification and remaining limits

127 selected backend cases passed, covering Auto, existing automotive/insurance
Builder behavior, executive dashboards, KPI parity and regional restrictions.
All 25 frontend files / 135 tests passed. TypeScript and targeted lint passed;
strict mypy passed on the four new backend contract/service/route/model files.
The complete production webpack build passed outside the sandbox. Sandbox
attempts hit font DNS/filesystem restrictions. Existing unrelated lint/type
findings must not be confused with new regressions.
Specifically, the shared `ResultChart` retains three pre-existing React lint
errors in its axis/type synchronization effects and pie-angle calculation;
the new optional `hideControls` prop does not change those lines. Lint of the
new Auto components, page wrapper, tests and configuration is clean.

Actual compiler/runner with synthetic database cursors: observed cold 19.560 ms,
12 execute calls with transaction setup mocked out; 20 warm runs had p50 6.811 ms,
p95 10.454 ms and zero warehouse calls. This is a local fixture measurement,
not PostgreSQL, concurrent-user or end-user latency.

Isolated Chromium used real Auto/chart components with synthetic intercepted API
responses: four charts, conversational visual edit, evidence table, Light/Dark/AI,
tablet and reduced motion. Component tests cover Custom state preservation,
insurance exclusion, clarification, narration failure and retained older results.
Live authenticated PostgreSQL/provider sessions, deployment migration execution,
screen-reader user testing and concurrent load remain unverified.

Current bounds: date/filter changes apply to the whole board after explicit
intent; chart-specific periods/filters and arbitrary rearrangement are not in
this release. Charts show at most 120 points, with full returned rows in the data
table/CSV. Narration cache availability is process-local. Board-wide PDF/export,
sharing, scheduling, forecasting, external actions and writeback are not added.

Design reference: public [ThoughtSpot SpotterViz](https://www.thoughtspot.com/product/agents/spotterviz)
patterns for governed intent, briefing and conversational refinement. No logged-in
ThoughtSpot trial was performed, and AskWiz does not reproduce its agent architecture.
