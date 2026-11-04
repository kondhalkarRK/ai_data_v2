# Ask Me — AI-Augmented Dashboard implementation plan

Prepared and implementation reviewed 2026-11-04. Proposed latency/usability targets below remain acceptance targets, not live measurements. See section 13 for delivered behavior and outstanding release checks.

## 1. Product outcome

A leader should quickly answer four questions: How are we doing? What changed? Which segments contributed? What should I investigate next?

Recommended first release: upgrade the existing Executive Intelligence dashboard with an executive briefing, evidence-backed highlights, a focused change-analysis drawer and contextual AI. Preserve existing governed calculations and chart interactions. AI augmentation should work in Light, Dark and AI themes; the theme is a visual preference, not an access gate for functionality.

Start with automotive as the implementation pilot because its cockpit already assembles grouped KPI and chart data. Add an insurance adapter before declaring cross-domain completion. Keep both existing dashboards usable throughout rollout.

## 2. What to learn from ThoughtSpot

ThoughtSpot’s useful patterns are governed visual analysis, highlights that identify important movements, change-contributor analysis, contextual conversation and a path from an insight to a follow-up action. Apply those patterns to Ask Me’s domain semantics and Data Trust experience.

Public product pages describe the broad suite. Availability is experience-specific: the 26.11 Liveboard side-panel documentation lists limits including change analysis and sharing within that experience. This plan combines selected design ideas for Ask Me; it does not claim a single ThoughtSpot screen currently delivers every proposed feature.

Official references:
https://www.thoughtspot.com/product/visualize
https://www.thoughtspot.com/product/augmented-analytics
https://docs.thoughtspot.com/cloud/26.11.0.cl/spotter-liveboard-experience

This review used public documentation and actual Ask Me code, not a logged-in ThoughtSpot trial or live warehouse benchmark.

## 3. The leader’s dashboard

A. Persistent context bar: industry, selected period, comparison period, active filter chips, refresh status and data-as-of. Make the selected scope visible before asking users to trust a number. Display the scope of retained results while a new selection is loading.

B. Executive briefing: two or three short sentences stating the main movement, the most important supported contributor and a relevant data caveat. Include a “View evidence” action. Prefer “Investigate dealer mix” over unsupported prescriptions such as changing targets or prices.

C. KPI strip: four to six prioritized metrics, each with current value, comparable-period change, units, trend and a clear “Explain” action. Reuse the existing restrained number animations. Ratios show percentage-point changes where appropriate. Missing data stays distinct from zero.

D. Focused chart area: show the main trend plus the most relevant breakdown or target comparison. Retain additional current charts in an Explore section instead of deleting them. Provide accessible legends, table equivalents, unit labels and filter breadcrumbs. Every chart can offer Explore, Explain and View data where supported.

E. “Needs attention” highlights: at most three ranked items with observed movement, affected segment, evidence, limitation and a next investigative step. Include positive opportunities when supported. If nothing material changed, say so instead of manufacturing a risk.

F. One contextual drawer: “Explain this change” opens a driver view; “Ask about this” opens the AI conversation in that same drawer. Keep the board visible. At tablet widths use an accessible overlay with a clear close/back action. Preserve focus, scroll and filter state.

## 4. A simple, meaningful interaction

1. Open the dashboard. KPIs and existing charts appear first; a concise summary follows from the same governed results.
2. Choose a period or select a chart segment. The context bar updates immediately and marks results as updating; the previous result remains clearly associated with its previous scope until the replacement arrives.
3. Select Explain on a metric. The drawer shows the exact metric definition and comparison, then ranks supported contributions by region, product/model or dealer/agent.
4. Select a contributor to filter the board, or ask a follow-up such as “Which models contributed most?” The user does not need to repeat the selected period and region.
5. Inspect evidence: definition, source tables, relevant SQL, data-as-of and trust caveats. Return to the overview without losing context.
6. In a later release, save the analysis, pin it to a personal board or follow the KPI. Notifications and external delivery need a separate authorized workflow.

If the user changes filters while a question is running, mark its result as belonging to the prior context. Offer to rerun against the new selection. Never silently reinterpret an in-flight question.

## 5. One validated dashboard context

Introduce an additive DashboardContext contract shared by the UI, explanation requests and contextual chat. It contains industry, canonical metric/definition IDs, explicit current and comparison periods, normalized filters, selected chart/segment references, semantic revision, result/context identity and data watermarks.

The frontend sends references and filters, never authoritative computed values or access rules. The API validates the contract, applies current server-side user/region policy and resolves metrics through approved semantics. Personal preferences and follow-ups cannot relax mandatory access restrictions.

Use a small adapter for each current dashboard. Automotive continues to call the cockpit service; insurance continues to use its existing KPI/intelligence service. Do not force one domain’s metric names, periods or ratios into the other’s formulas.

A context/result ID identifies which results an explanation belongs to; it does not establish a transactional database snapshot by itself. Validate freshness against server-held metadata. When newer data is used for a drilldown, disclose that and offer refresh rather than pretending it exactly reconciles with an older board.

## 6. Evidence-backed explanation engine

Layer 1 — Facts: derive movements and summaries directly from existing API aggregates. No LLM is needed to calculate a value, choose the applicable definition or state a known comparison.

Layer 2 — Drivers: extend existing grouped cockpit data and Builder driver/narration logic. Prefer reusable aggregates. Run a bounded governed query only when a requested breakdown is not already present. Compare aligned periods and include an “other” residual where only top contributors are shown.

Layer 3 — Narrative: optionally use the LLM to summarize verified evidence. Pass structured facts and explicit limitations. Check referenced numbers and entities against that evidence; fall back to deterministic prose if validation fails or the provider is unavailable. Do not repeatedly invoke the LLM on hover or ordinary rerenders.

Layer 4 — Next steps: suggest a relevant drilldown or question supported by available dimensions. A recommendation is a proposed investigation, not a causal conclusion or an automated business action.

For additive metrics, segment contributions plus residual must reconcile to the total delta. Never add overlapping breakdowns from different dimensions. For ratios, use governed numerator/denominator analysis; do not add percentage changes. Missing prior values, zero denominators, reversals in direction, incomplete periods and sparse samples require explicit handling.

Start with supported metric families: automotive revenue, units and orders; insurance premium, claim count and an explicitly implemented loss-ratio decomposition. Expose a capability matrix. Unsupported explanations show available alternatives and never fall back to invented reasons. Association should be described as “contributed to the change,” not proof of causality.

## 7. Smooth and predictable processing

Fast path: normalized context → scoped cache or bounded read-only queries → current KPI/chart response → immediate deterministic highlights. The base dashboard never waits for optional AI prose.

Deep path, only on demand: Explain request → validate context and capability → reuse aggregates or run a bounded driver query → return structured evidence → optionally enrich the wording. A failure in this path does not remove the dashboard.

On the frontend, debounce bursty filter changes, deduplicate identical requests, cancel obsolete fetches and reject late responses by context identity. Update labels, values, charts and briefing coherently. Retain prior data with an explicit updating state; do not show old results beneath new filter labels as though they are current.

Cache by industry, normalized filters, periods, semantic revision, current access scope/policy revision and data watermark. Keep template factual analysis separate from optional provider-specific narrative. A region or definition change must invalidate incompatible entries. A five-minute TTL is not a substitute for these checks.

Maintain a bounded query/concurrency budget. The existing services use a shared analytics connection per request: do not run concurrent SQL operations on that same connection. Parallel work, if profiling justifies it, needs separately scoped pooled connections with an explicit overall limit. Avoid one query per tile and full-table downloads.

Use component-level error states and retries. Keep charts useful during an LLM timeout. Check quotas before invoking paid model work. Abort an obsolete request where possible; request cancellation must not be presented as proof that a database statement was terminated.

For on-demand chat, reuse a verified streaming path if the deployment supports it. The current main chat uses ask-sync; it cannot deliver genuine intermediate server stages as they happen. Use honest stage events when streaming works, or a bounded request with an honest status/elapsed indicator. Add durable jobs/polling only if measured workloads require them. Never show fabricated progress percentages.

## 8. Proposed responsiveness and usability gates

These are proposed acceptance targets to benchmark, not measured performance claims:

• Visible feedback to a selection within 100 ms; keep the interface responsive while work continues.
• Warm-cache core KPI/chart data at p95 ≤ 2 seconds; cold-path core data at p95 ≤ 5 seconds on an agreed pilot dataset, query mix and concurrency profile.
• Initial deterministic highlights add no model call and no additional warehouse scan when current aggregates suffice.
• A supported cached explanation should open immediately; target p95 ≤ 5 seconds for a bounded uncached driver analysis. Use an explicit timeout with retained base results.
• Optional narrative must not delay the dashboard; choose its bounded timeout using current provider configuration and pilot measurements.
• No stale response overwrites a newer filter selection. No silent region/industry scope change. No numeric contradictions between briefing and evidence.
• In a moderated pilot, leaders identify the main movement and reach its evidence without a tutorial; target finding the main issue within 30 seconds. Validate the target with users rather than assuming adoption.

Record frontend paint/interaction time separately from API, warehouse, cache and LLM time. Use request/context IDs for correlation. Measure latency and correctness per domain and restricted-user scope, including cold cache and concurrent users. Adjust indexing, aggregation or scope before committing unsupported latency promises.

## 9. Implementation sequence and exit gates

Phase 0 — Baseline and design contract
Inventory both active dashboard paths, record latency/query counts, approve metric capability and comparison rules, define context/evidence schemas and review a responsive wireframe. No chart engine replacement.
Exit: each proposed highlight and explanation has a known source, supported calculation and testable behavior.

Phase 1 — Coherent dashboard foundation
Add domain context adapters, result identity/freshness, coherent refetch states and an executive briefing derived from existing results. Preserve chart calculations and theme behavior.
Exit: same context gives matching KPI/chart/briefing values; rapid filter changes, loading, empty, error and access-denied states are covered in both industries.

Phase 2 — Explain this change
Add structured driver evidence, metric-specific capability checks, a right-side drawer, evidence view and “apply segment filter” interaction. Reuse existing analysis components.
Exit: additive contributions reconcile; ratios and partial periods pass domain-specific tests; unauthorized segments cannot appear.

Phase 3 — Contextual AI
Wire a shared AI drawer to validated DashboardContext, scoped conversation memory, readable interpretation and optional narrative. The existing AskDashboardAi component is currently unreferenced and should be assessed before reuse; its present payload lacks dashboard filters.
Exit: follow-ups preserve allowed context; changing filters/industry does not leak prior scope; no LLM, quota, provider timeout and invalid response paths remain useful.

Phase 4 — Pilot and polish
Test leadership and analyst tasks, keyboard/screen-reader use, desktop/tablet, reduced motion, all three themes, exports, SQL safety and region restrictions. Profile concurrent/cold-cache scenarios and tune real bottlenecks. Release behind a reversible feature flag; keep the current dashboard available for rollback.
Exit: agreed correctness/security/usability gates pass and any performance exceptions are documented.

Phase 5 — Expand only after the core works
Reusable Answers, private boards, watchlists and durable threshold alerts. Then reviewed AI-generated board drafts, scheduled reports or advanced forecasting if validated user needs justify them. These are follow-on modules, not prerequisites for the first augmented dashboard.

## 10. Implementation map

Existing UI entry points:
apps/web/app/(workspace)/dashboard/page.tsx — automotive/insurance branch and classic dashboard.
apps/web/components/executive/cockpit/executive-cockpit.tsx — automotive filter state, data and chart composition.
apps/web/components/executive/cockpit/chart-frame.tsx — shared chart chrome/exports.
apps/web/components/executive/ai-intelligence.tsx — current insight presentation and feedback.
apps/web/components/executive/ask-dashboard-ai.tsx — currently unreferenced chat component; missing board context.
apps/web/components/executive/progressive-explorer.tsx — reusable drilldown interactions.
apps/web/hooks/use-count-up.ts and components/ui/animated-number.tsx — shared metric transitions.

Existing API/computation:
apps/api/app/api/routes/executive.py and chat.py — request boundaries.
apps/api/app/services/executive/cockpit.py — grouped automotive calculations and deterministic insights.
apps/api/app/services/executive/__init__.py and insights.py — classic industry bundle and grounded rule-based insights.
apps/api/app/services/analytics/runner.py and insights.py — governed driver queries/narration patterns.
apps/api/app/services/chat/ — validated plans, follow-ups, SQL and conversation handling.
apps/api/app/services/security/region_scope.py — mandatory scoped execution.
packages/shared-types/src/index.ts — mirrored frontend contracts.

Proposed additive units, names to confirm during implementation: dashboard context adapters, structured evidence schemas, an explanation service and Dashboard AI drawer. Preserve current APIs; introduce optional fields or dedicated endpoints after inspecting compatibility. Do not invent support for arbitrary driver dimensions without compiler coverage.

## 11. Verification before release

Numerical: current/prior comparisons, negative values, zero denominators, percentage points, residuals, nonadditive ratios, sparse history and partial-period handling.

Context/security: restricted regions, changed/revoked access, forged chart/metric references, industry switches, expired result identities, cached results and scoped conversational memory.

Resilience: rapid filter changes, request deduplication, out-of-order responses, connection exhaustion, SQL timeouts, stale data, no LLM, provider failure, quota exhaustion and narrative/evidence mismatch.

UX: leadership tasks and analyst evidence tasks; keyboard/escape/focus return; screen-reader labels; tablet overlays; Light/Dark/AI; reduced motion; formatted INR/percentages and export readability.

Relevant existing suites: test_executive_cockpit.py, test_executive_intelligence.py, test_kpi_parity.py, unit/test_analytics_builder_v2.py, unit/test_region_rls.py, unit/test_scope_enforcement.py and conversation tests. Extend frontend component tests and add end-to-end scenarios with a running API. Do not treat SQLite/mocked tests as proof of live PostgreSQL behavior.

Product measures: verified answer correctness, time to evidence, useful explanation rate, user feedback, return usage and cost per successful explanation. Establish a baseline before claiming an improvement.

## 12. Scope recommendation

Approve Phases 0–4 as the first AI-Augmented Dashboard initiative. The initial experience is a focused upgrade to Executive Intelligence: briefing + supported Explain actions + contextual AI drawer. Preserve Data Trust as evidence that qualifies the result and links to deeper investigation.

Do not bundle automatic business actions, external sends, writeback, arbitrary generated dashboards, notebook execution or a connector marketplace into this first release. Adding those would obscure whether the core leader experience actually works.

Assumptions: internal business users and leaders are the initial audience; existing automotive/insurance PostgreSQL data remains the source; no new analytics vendor or model is required. Confirm pilot stakeholders, deployment/concurrency expectations, comparison definitions and the first metric families before committing dates.

Status: Phases 0–3 implemented for the bounded metric families below; Phase 4 automated checks and visual polish completed, live performance and leadership pilot gates still open. No agent integration, new dependency or database migration was introduced.

## 13. Implementation and verification — 2026-11-04

Delivered: up to three deterministic executive observations, KPI/chart Explain controls, one accessible contextual drawer, ranked contributors with current/prior amounts and reconciled residuals, SQL/parameter evidence, metric definitions, supported segment application and a Data Trust entry link. Existing chart components, exports, drilldowns and number utilities remain in place. Data Trust navigation opens the existing overview; it does not claim a metric-specific quality score.

Supported adapters:

- Automotive cockpit: revenue, units and orders; zone, make and model breakdowns. Initial highlights and explanations reuse its existing grouped scan, including prior-only contributors. No extra warehouse query or LLM call for initial augmentation.
- Insurance: written premium, earned premium and claim count by region/line of business, with one on-demand aggregate SELECT (plus statement-timeout configuration). Loss ratio uses captured claims-incurred/earned-premium totals and a symmetric two-factor decomposition in percentage points; it is not the sum of segment ratios. Other metrics/charts retain their existing exploration without an unsupported Explain promise.
- Comparison dates come from the existing domain services. Partial-period caveats are exposed; missing comparisons and undefined ratios are not invented. Contributors describe arithmetic effects, not proven causes. Insurance on-demand queries are timestamped, check captured totals, and warn that equal totals cannot prove unchanged distributions.

Implementation paths:

- `apps/api/app/schemas/dashboard.py`, `app/services/executive/dashboard.py`, `app/api/routes/dashboard.py`: typed context, signed result handles, bounded evidence and contextual questions. Existing executive endpoints add optional `augmentation`; new POST `/api/v1/executive/explain` and `/api/v1/executive/ask` use existing auth, CSRF, scope enforcement and read-only analytics. Ask persists scoped conversation/audit/usage and applies existing quota checks. Explain remains available without paid AI quota.
- `apps/web/components/executive/dashboard-intelligence.tsx`, `lib/executive/dashboard.ts`, `hooks/use-debounced-value.ts`, `hooks/use-retained-query-data.ts`: shared drawer, actions, supported filter merging, abortable/debounced queries and explicit previous/updating/failed/current states. A captured drawer never silently adopts a newer filter context; users choose Use current selection. Query-key isolation and cancellation prevent old requests replacing newer results.
- Inspected `AskDashboardAi`: it posts to general chat without dashboard filters and assumes SSE. It remains unreferenced; wiring it unchanged would lose context. The new drawer reuses the API client, Radix primitives, themes, existing LLM service and governed execution boundary. It does not run the general NLQ/tool loop or generate SQL. Ordinary allowlisted calculations replace unrestricted planning; existing generic planners remain unchanged.
- Optional AI is one bounded existing `complete_text` classification for unrecognized phrasing, returning only allowlisted metric/dimension/operation. Known questions and all numerical narration are deterministic. Missing provider, timeout and malformed output return supported alternatives; core dashboards never await this work.

Security and rollback:

- Context resolves from server-held results, never client metric values or permissions. Handles bind user, role, industry, region scope and semantic revision. Current permissions are checked again on each request. Automotive dimension-cache keys now include scope and semantic revision.
- `ASK_ME_AUGMENTED_DASHBOARD_ENABLED=false` disables backend metadata/routes. `NEXT_PUBLIC_ASK_ME_AUGMENTED_DASHBOARD_ENABLED=false` disables frontend augmentation after rebuild. Both default true; turn both off for rollback to the existing charts. New conversation/history records use existing tables and need no reverse migration.
- Result storage is bounded to 256 handles per API process for 10 minutes. Restart, eviction or expiry returns 409 with a refresh instruction. **Use a single API worker or sticky routing for this implementation.** Shared snapshot storage is required before a non-sticky multiworker rollout; this release does not claim distributed handle persistence.

Measured checks:

- 118 selected backend pytest cases passed: dashboard numerical/API/context tests, cockpit/intelligence, KPI parity, region RLS/scope, analytics compiler and conversation memory. New cases include residuals, prior-only groups, zero denominators, ratio decomposition, context tampering/expiry/scope changes, forged values, quotas/CSRF, usage auditing, malformed classifier output and mocked provider timeout.
- All frontend tests: 24 files / 130 tests passed. Typecheck passed. Targeted frontend lint and strict mypy on six changed boundary/service files passed. New backend code/tests pass Ruff; existing executive service lint findings and 12 existing frontend lint errors in untouched files remain outside this change.
- Isolated Chromium exercised the actual shared drawer and dashboard KPI/chart components with intercepted synthetic API fixtures: both industries, Light/Dark/AI, evidence, follow-up, quota failure, changed context, tablet and reduced motion. Component tests verify late-response rejection, cancellation and Escape/focus return. This is not a live authenticated end-to-end warehouse session or a screen-reader user study. Existing export code was preserved; full dashboard/export integration still needs live regression verification.
- A 100-run synthetic local benchmark of augmentation assembly plus handle registration: p50 2.333 ms, p95 2.858 ms; zero database queries and zero model calls. This excludes core API SQL, browser paint, network, concurrency and provider latency. Responses expose core application execute-call counts/warehouse time and explanation elapsed/query counts; counts exclude implicit transaction protocol statements. No live p95 target is claimed.
- Production build is **not verified**: normal build blocked on Google Fonts DNS; test-only mocked-font build compiled and passed TypeScript, then prerendering failed with EPERM on `.next/server/app/_not-found.segments/_not-found`. An outside-sandbox production build was declined. No permanent font or dependency change was made to bypass this.

Remaining Phase 4 gates: authenticated live PostgreSQL/provider end-to-end checks, cold/warm and concurrent latency/query baselines against section 8, warehouse churn during explanations, full page/export regression, screen-reader checks and a moderated leadership pilot. API startup performs schema/catalog maintenance, so it was not launched against an unreviewed shared database merely for visual checks. Pilot results and distributed-storage deployment decisions remain outstanding; do not mark these gates passed from fixture tests.

Subsequent authorized work: automotive-only AskWiz Auto mode now lives in Analytics
Builder, separately from this Executive Intelligence release. Insurance Builder
remains unchanged. See `docs/ASKWIZ_IMPLEMENTATION.md` for its exact scope,
migration, feature flags, evidence-curated LLM narration and limits. A subsequent
full production webpack build passed outside the sandbox; the earlier build
restriction recorded above describes the Executive Intelligence checkpoint.

Analytics Builder now also has a unified automotive workspace behind separate
disabled-by-default rollout flags. It supports question-dependent response shapes,
daily analysis, scoped persistence, conversational refinement and signed-evidence
narration. Existing Auto boards and analyses remain importable and untouched.
See `UNIFIED_ANALYTICS_BUILDER_IMPLEMENTATION.md` for migration 0013, activation,
rollback and verification. Configured database connectivity and live-provider
acceptance remain outstanding; this does not change Executive Intelligence gates.
