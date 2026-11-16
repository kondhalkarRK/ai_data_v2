# ThoughtSpot review and Ask Me upgrade plan

Reviewed: 2026-11-04 · Public product pages and official documentation; compared with actual Ask Me code.

## Recommendation

Build a connected decision workflow: **Ask → verify → explore → save → pin → monitor**. Ask Me already has semantic models, governed SQL, a Builder, executive insights, Data Trust, RAG and LLM governance. Strengthen and connect those foundations instead of attempting to clone an entire BI suite.

The first implementation should be **dashboard-aware answers plus visible, editable interpretation**, supported by a reusable Answer contract. Personal boards and business KPI alerts are the largest useful new modules. Preserve Ask Me’s explicit Data Trust and cited knowledge experience; this is a product positioning choice, not a claim of superiority over ThoughtSpot.

## Evidence and limits

- ThoughtSpot capabilities below are documented or marketed features, not a hands-on benchmark or independently verified accuracy claim. No account, paid demo, customer data or live Ask Me API was used.
- Coverage includes the main analytics/agent suite, semantics, dashboards, insights, monitoring, collaboration, modeling, connectors, security, embedding, mobile and analyst tooling. It is not a crawl of every marketing/resource page.
- ThoughtSpot documentation is version/experience-specific. The 26.11 user guide and developer guide disagree on new side-panel embedding availability. Memory defaults also vary across release notes/FAQ. Confirm target release and tenant settings before assuming availability. [User guide](https://docs.thoughtspot.com/cloud/26.11.0.cl/spotter-liveboard-experience), [developer guide](https://developers.thoughtspot.com/docs/embed-new-spotter), [release notes](https://docs.thoughtspot.com/cloud/26.11.0.cl/26-9-0-cl), [memory FAQ](https://docs.thoughtspot.com/cloud/26.10.0.cl/spotter-memory-faq).
- The new Liveboard side panel has documented gaps including conversation sharing, in-conversation drilldowns and change analysis. Do not combine all experiences into one assumed feature set.
- “Live/zero-copy” and managed cached data are different modes. Connector availability does not establish arbitrary cross-source query support.
- Size labels are relative engineering scope, not calendar promises: M = a bounded cross-layer upgrade; L = a new persistent workflow or broad integration; XL = a separate execution platform. Staffing and deployment details are not yet known.

## Major component comparison

### 1. Dashboard-aware AI

**First · Improve · Relative scope M**

- **ThoughtSpot:** Spotter can use a Liveboard and its filters as conversational context; availability differs by experience. [Official source](https://docs.thoughtspot.com/cloud/26.11.0.cl/spotter-liveboard-experience).
- **Ask Me, verified:** Partial code only: AskDashboardAi exists but no active import/use was found. Its request contains question, conversationId and industry, not board/filter context.
- **Recommended change:** Open an AI side panel from a KPI or chart; carry selected measures, chart references, periods and filters as a validated typed context.
- **Acceptance:** With West + Q2 selected, ask “why did this fall?”; interpretation, executed SQL and answer all preserve that context. Unauthorized filters remain rejected.
- **Implementation starting points:** `apps/web/components/executive/ask-dashboard-ai.tsx`, `apps/web/components/executive/cockpit/executive-cockpit.tsx`, `apps/api/app/api/routes/chat.py`.

### 2. Verifiable answers and editable intent

**First · Improve · Relative scope M**

- **ThoughtSpot:** Spotter exposes governed search tokens and query logic rather than relying on opaque free-form generation. [Official source](https://www.thoughtspot.com/product/agents/spotter).
- **Ask Me, verified:** Substantial foundation: semantic plans, validation, SQL tabs, metadata and confidence already exist; not the same architecture as ThoughtSpot.
- **Recommended change:** Show plain-language metric, aggregation, period, comparison and filter chips above each answer. Explain definitions and allow safe edits through the governed compiler.
- **Acceptance:** Changing a period chip recomputes through the governed path; visible intent agrees with SQL. Confidence is labeled as a heuristic, not a measured accuracy probability.
- **Implementation starting points:** `apps/api/app/services/chat/pipeline.py`, `apps/api/app/services/chat/semantic_query_planner.py`, `apps/api/app/services/chat/response_meta.py`, `apps/web/components/chat/response-card.tsx`.

### 3. Reusable Answer library

**First · Extend · Relative scope L**

- **ThoughtSpot:** Saved Answers are reusable analytical objects that feed Liveboards and monitoring workflows. [Official source](https://docs.thoughtspot.com/cloud/26.11.0.cl/thoughtspot-homepage).
- **Ask Me, verified:** Partial: SavedQuestion stores question/SQL; SavedAnalysis stores spec/viz/SQL snapshot. Listing and mutation are owner-scoped.
- **Recommended change:** Introduce a versioned Answer definition shared by Chat and Builder, including semantic references, filter bindings, visualization and provenance. Use an adapter for existing saved objects.
- **Acceptance:** Save from Chat or Builder, reopen and rerun with the current viewer permissions. A SQL snapshot alone never authorizes execution. Mark incompatible model revisions clearly.
- **Implementation starting points:** `apps/api/app/models/activity.py`, `apps/api/app/services/chat/service.py`, `apps/api/app/services/analytics/runner.py`, `apps/web/app/(workspace)/saved-questions/page.tsx`.

### 4. Personal boards / Liveboards

**Next · New · Relative scope L**

- **ThoughtSpot:** Liveboards organize saved visualizations into interactive dashboards with filters, tabs and exploration. [Official source](https://www.thoughtspot.com/product/visualize).
- **Ask Me, verified:** Gap: an executive cockpit and saved analyses exist, but no general persisted user-created board/layout/membership workflow was found.
- **Recommended change:** Add My Boards with pinned Answer references, simple responsive tile layouts, shared filter bindings and CSV/PNG export. Start with private boards; add sharing only after object permissions.
- **Acceptance:** Pin three answers, reorder, reload and apply a common filter. Incompatible tiles explain why a filter does not apply. Every tile executes as the viewer.
- **Implementation starting points:** `apps/web/components/executive/cockpit/chart-frame.tsx`, `apps/web/components/analytics-builder/analytics-builder-shell.tsx`, `apps/api/app/models/activity.py`.

### 5. AI-assisted board creation / SpotterViz

**Later · Extend · Relative scope L**

- **ThoughtSpot:** SpotterViz proposes dashboards and lets users refine metrics, layout and presentation conversationally. [Official source](https://www.thoughtspot.com/product/agents/spotterviz).
- **Ask Me, verified:** Partial building blocks: Builder assist, chart recommendation and governed analysis specs; no persisted multi-tile board generation workflow.
- **Recommended change:** After Boards, let a prompt draft a board specification using approved metric IDs. Preview each tile, validate it, then explicitly save the board. Do not generate arbitrary application code.
- **Acceptance:** “Build a dealer performance board” yields inspectable, individually valid tiles; unsupported measures are explained and no draft auto-publishes.
- **Implementation starting points:** `apps/api/app/services/analytics/catalog.py`, `apps/api/app/services/analytics/chart_recommend.py`, `apps/api/app/services/analytics/runner.py`, `apps/web/hooks/use-analytics.ts`.

### 6. Change analysis / AI Highlights

**Next · Improve · Relative scope M–L**

- **ThoughtSpot:** Augmented analytics surfaces changes, contributors, anomalies and forecasts; individual capabilities depend on the experience. [Official source](https://www.thoughtspot.com/product/augmented-analytics).
- **Ask Me, verified:** Partial: executive insights, anomaly metadata and Builder driver/narration logic already exist. Do not rebuild these as an unrelated insight engine.
- **Recommended change:** Add “Explain this change” from KPIs: compare aligned periods, rank segment contributions and drill into the underlying governed result. Link findings to Data Trust evidence.
- **Acceptance:** Contributions reconcile to the total delta, including residuals. Ratios use numerator/denominator-aware analysis; partial periods and insufficient history are disclosed. Avoid claiming causality.
- **Implementation starting points:** `apps/api/app/services/analytics/runner.py`, `apps/api/app/services/analytics/insights.py`, `apps/api/app/services/executive/insights.py`, `apps/api/app/services/chat/response_meta.py`.

### 7. Personal KPI watchlist

**Next · New · Relative scope M**

- **ThoughtSpot:** ThoughtSpot Home includes personal Watchlist KPIs and recent Answers/Liveboards. [Official source](https://docs.thoughtspot.com/cloud/26.11.0.cl/thoughtspot-homepage).
- **Ask Me, verified:** Gap: Home has a hero/readiness surface and saved questions, but no persisted per-user KPI watchlist was found.
- **Recommended change:** Let users follow an Answer/KPI with saved filters, current value, comparison, data freshness and a direct route to analysis.
- **Acceptance:** Users can add/remove a KPI and restore the same scoped definition after login. A stale or failed refresh is visible rather than presented as a fresh number.
- **Implementation starting points:** `apps/web/app/(workspace)/home/page.tsx`, `apps/web/components/home/connected-data-sources.tsx`, `apps/api/app/models/activity.py`.

### 8. Business KPI alerts

**Next · New · Relative scope L**

- **ThoughtSpot:** Threshold alerts monitor values or percentage changes on a schedule, with subscriber and row-level security behavior. [Official source](https://docs.thoughtspot.com/cloud/26.10.0.cl/monitor-alert-threshold).
- **Ask Me, verified:** Partial but different purpose: Data Trust rule monitors and alerts exist. A business KPI subscription, evaluator and notification-delivery workflow was not found.
- **Recommended change:** Add threshold alerts on governed Answers first; anomaly alerts later. Use durable jobs, user timezones, deduplication, cooldown, retries and an in-app notification inbox.
- **Acceptance:** West users are evaluated only against West data, including after access revocation. A persistent breach does not spam. Failed/stale checks never produce a misleading business alert.
- **Implementation starting points:** `apps/api/app/services/reliability/service.py`, `apps/api/app/models/reliability.py`, `apps/api/app/rag/worker.py`, `apps/api/app/services/security/region_scope.py`.

### 9. Scheduled reports and subscriptions

**Later · New · Relative scope L**

- **ThoughtSpot:** Liveboards can be distributed on schedules; recipient permissions and external attachments require careful handling. [Official source](https://docs.thoughtspot.com/cloud/26.10.0.cl/schedule-liveboards).
- **Ask Me, verified:** Partial: CSV/PNG exports exist. No general durable BI report scheduler or delivery/subscription service was found.
- **Recommended change:** Build on the KPI job infrastructure; start with a weekly in-app digest, then opt-in email and secure links. Avoid externally attached datasets in the first version.
- **Acceptance:** Schedules use an IANA timezone, survive restarts and are idempotent. Each recipient is reauthorized at send/open time; delivery status and unsubscribe are visible.
- **Implementation starting points:** `apps/web/components/executive/cockpit/chart-utils.ts`, `apps/api/app/services/governance/audit.py`, `apps/api/app/db/session.py`.

### 10. Governed coaching and shared memory

**First · Extend · Relative scope M–L**

- **ThoughtSpot:** Spotter distinguishes business semantics, shared/model memory and personal memory; legacy reference questions remain supported. [Official source](https://docs.thoughtspot.com/cloud/26.10.0.cl/spotter-memory-faq).
- **Ask Me, verified:** Partial: YAML vocabulary/glossary, persisted conversation memory and benchmark suites exist. No steward-reviewed shared coaching promotion flow was found.
- **Recommended change:** Capture a corrected question, intended semantic plan and rationale as a proposed reference case. Stewards approve shared rules; replay regression suites before activation. Start with explicit coaching, not hidden self-learning.
- **Acceptance:** An approved correction handles paraphrases and preserves unrelated reference cases. Personal preferences cannot alter region restrictions or global metric definitions; revisions are reversible.
- **Implementation starting points:** `apps/api/app/services/chat/conversation_memory.py`, `apps/api/app/services/chat/semantic_context.py`, `apps/api/semantic/packs`, `apps/api/tests/benchmark`, `apps/api/tests/chat_routing_eval`.

### 11. Semantic modeling assistance / SpotterModel

**Later · Extend · Relative scope L**

- **ThoughtSpot:** SpotterModel recommends tables, joins, measures and metadata, with human review before deployment. [Official source](https://www.thoughtspot.com/product/agents/spottermodel).
- **Ask Me, verified:** Strong foundation: YAML packs, business/technical views, ontology, warehouse introspection, catalog versions and drift. Missing a reviewed authoring/publish workflow.
- **Recommended change:** Extend Semantic Admin with draft metadata and join recommendations, a diff, impact preview, validation, approval and version rollback. Begin with descriptions/synonyms, then joins and measures.
- **Acceptance:** Proposals remain drafts until an authorized publish. Join cardinality and golden queries are checked; publishing invalidates dependent caches, coaching and Answer revisions correctly.
- **Implementation starting points:** `apps/api/app/services/catalog/introspect.py`, `apps/api/app/services/catalog/drift.py`, `apps/api/app/semantic/service.py`, `apps/web/components/admin/entity-catalog-admin.tsx`.

### 12. Enterprise identity and object/column permissions

**Before team rollout · Extend · Relative scope L**

- **ThoughtSpot:** ThoughtSpot documents SAML authentication and group-based row/column access; it also governs shared analytical objects. [Official source](https://docs.thoughtspot.com/cloud/26.9.0.cl/column-security-rules).
- **Ask Me, verified:** Partial: local auth, two roles, region SQL enforcement, document ACLs and audit. No SSO or general object-level/group/column policy system was found. SavedQuestion.isShared is not a sharing system.
- **Recommended change:** Before team rollout, introduce explicit viewer/editor/owner grants and policy tests; add SSO/group mapping and sensitive-column denial where required. Keep data access independent of UI visibility.
- **Acceptance:** Denied fields never appear in SQL generation, suggestions, results, export, cache or RAG. Shared links reauthorize each viewer. Region and group changes take effect on subsequent reads/jobs.
- **Implementation starting points:** `apps/api/app/api/deps.py`, `apps/api/app/models/enums.py`, `apps/api/app/services/security/region_scope.py`, `apps/api/app/rag/acl.py`.

### 13. Warehouse and business-app connectors

**Later · Extend · Relative scope L**

- **ThoughtSpot:** ThoughtSpot distinguishes live warehouse access, prepared/cached data and connectors supplying external business context. [Official source](https://www.thoughtspot.com/product/connect).
- **Ask Me, verified:** Partial: two industry-specific PostgreSQL pools and optional RAG/web retrieval; not a pluggable multi-warehouse connection/model onboarding experience.
- **Recommended change:** Add a connector interface and secure connection catalog only when a real source is selected. Pilot one source; keep SQL dialect, schema mapping, permissions, timeouts and costs explicit.
- **Acceptance:** A second source passes semantic conformance and permission tests. Secrets never enter browser state. Cross-source analysis is not implied by adding a connector.
- **Implementation starting points:** `apps/api/app/db/session.py`, `apps/api/app/core/config.py`, `apps/api/app/services/catalog/introspect.py`, `apps/api/app/services/knowledge.py`.

### 14. Embedded analytics and governed MCP

**Later · New · Relative scope L**

- **ThoughtSpot:** ThoughtSpot provides embedding SDKs, APIs, theming and MCP integration; SpotterCode assists developers building embeds. [Official source](https://developers.thoughtspot.com/).
- **Ask Me, verified:** Partial: internal REST APIs and three themes exist; no scoped embedding SDK, signed embed sessions, external client lifecycle or MCP surface was found.
- **Recommended change:** If distribution is needed, expose a narrow read-only Answer/metric API first, then scoped embed tokens or MCP tools. Preserve viewer policy and audit every external call.
- **Acceptance:** External consumers cannot execute arbitrary SQL, cross user/industry scope, or reuse expired tokens. Embeds have a deliberate CSP/auth lifecycle.
- **Implementation starting points:** `apps/api/app/api/router.py`, `apps/api/app/api/deps.py`, `apps/web/proxy.ts`, `apps/web/next.config.ts`.

### 15. Agent workflows and writeback

**Defer · New · Relative scope L**

- **ThoughtSpot:** AgentSpot and actionable analytics market connected workflows, collaboration and actions across business tools. [Official source](https://www.thoughtspot.com/product/actionable-analytics).
- **Ask Me, verified:** Gap by design: analytics is read-only. No general external action engine, writeback or collaborative agent builder was found.
- **Recommended change:** Defer broad agent orchestration and warehouse writeback. A later MVP can draft a ticket from a verified insight, with a preview and explicit authorization before external delivery.
- **Acceptance:** Read-only analytics credentials remain read-only. Any future action has a scoped credential, recipient/target preview, audit trail and retry-safe execution.
- **Implementation starting points:** `apps/api/app/db/session.py`, `apps/api/app/services/governance/audit.py`.

### 16. Analyst Studio / SQL-Python preparation

**Defer · New · Relative scope XL**

- **ThoughtSpot:** Analyst Studio combines SQL, Python and spreadsheet-style preparation; its page labels the AI prompting option coming soon. [Official source](https://www.thoughtspot.com/product/analyst-studio).
- **Ask Me, verified:** No general notebook/data-preparation workspace. Existing governed Builder and SQL inspection serve a narrower purpose.
- **Recommended change:** Defer a notebook platform. Improve safe SQL inspection and governed Builder expressions first; validate demand before adding an execution sandbox or transformation runtime.
- **Acceptance:** Any future advanced runtime needs resource isolation and a separate authorization model; it must not bypass the governed analytics path.
- **Implementation starting points:** `apps/web/components/chat/sql-viewer.tsx`, `apps/api/app/services/analytics/compiler.py`.

### 17. Focused Home and mobile experience

**Next · Improve · Relative scope M**

- **ThoughtSpot:** ThoughtSpot organizes navigation by Insights, Data, Develop and Admin, and offers focused Home and mobile analytics. [Official source](https://docs.thoughtspot.com/cloud/26.11.0.cl/thoughtspot-homepage).
- **Ask Me, verified:** Partial: role-filtered navigation, responsive pages, Home and usage widgets. Native mobile clients and personal recents/watchlists are not equivalent to current Home.
- **Recommended change:** After the Answer library, make Home task-oriented: Ask, Recent Answers, My Boards, Watchlist and trust notices. Keep Developer navigation out until there is a developer product.
- **Acceptance:** Business users can resume analysis in one click, keyboard navigation works, and key workflows fit tablet/mobile web before considering native apps.
- **Implementation starting points:** `apps/web/lib/navigation.ts`, `apps/web/app/(workspace)/home/page.tsx`, `apps/web/components/shell/command-palette.tsx`.

### 18. Query performance, freshness and observability

**First · Improve · Relative scope M**

- **ThoughtSpot:** ThoughtSpot supports direct queries and eligible model caching; documented Data Cache currently has source and configuration restrictions. [Official source](https://docs.thoughtspot.com/cloud/26.11.0.cl/data-cache).
- **Ask Me, verified:** Existing process-local scoped result cache, data-as-of invalidation, profiler and token/usage reporting. These are not a distributed data cache or measured enterprise-scale parity.
- **Recommended change:** Measure p50/p95 latency, validated-answer rate, cache hit rate, freshness and cost per successful answer. Add semantic/policy revision awareness before expanding caches.
- **Acceptance:** Cache entries cannot survive incompatible model/policy changes or leak across users/scopes. Record baseline and post-change measurements; do not claim speedups without data.
- **Implementation starting points:** `apps/api/app/services/chat/query_cache.py`, `apps/api/app/services/chat/profiler.py`, `apps/api/app/services/governance/usage.py`, `apps/api/app/services/chat/service.py`.

## Dependency-aware rollout

### 1 · Trustworthy answers

Dashboard context, editable interpretation, a common Answer definition, explicit coaching and baseline telemetry.

**Exit gate:** Chat and Builder agree for the same specification; ambiguous intent is clarified; denied regions never escape into queries, memory or caches.

### 2 · Reuse and daily engagement

Private My Boards, pinned Answers, focused Home, watchlists and contributor drilldowns. Introduce object grants before any team sharing.

**Exit gate:** The same Answer runs consistently from Chat, Builder, a board and a watchlist, always as the current viewer.

### 3 · Proactive intelligence

Durable KPI threshold evaluation, notification inbox and delivery history; then secure scheduled digests. Extend anomaly analysis after thresholds are reliable.

**Exit gate:** Permission changes, stale data, restarts, retries and persistent breaches are tested. Notifications remain accurate and nonduplicated.

### 4 · Governed expansion

Reviewed semantic authoring, prompted board drafts, one validated additional connector, then embedding/MCP if users need distribution.

**Exit gate:** Model revisions have validation, impact checks and rollback; connector/embedding additions pass the same security and semantic contract tests.

Additional suite coverage: [AgentSpot](https://www.thoughtspot.com/agentspot) is the broader connected-agent/workflow offering; [SpotterCode](https://www.thoughtspot.com/product/agents/spottercode) assists embedding developers. These are distinct from adding an AI chat panel to Ask Me. Both are covered under the integration/actions recommendations above.

## Architecture decisions before implementation

- **Canonical Answer:** persist a typed, versioned definition with metric IDs, aggregation, periods, filters, chart intent, semantic revision and provenance. Keep saved question text and SQL snapshots as evidence, not executable authority. A board pins Answer references, not copied numerical results.
- **Dashboard context:** explicitly distinguish user filters, inferred follow-up context and mandatory access policy. The server validates all context; preferences and AI suggestions cannot relax policy.
- **Background BI jobs:** borrow durable lease/retry patterns from RAG if useful, but create a separate BI job type/service. Do not couple KPI checks to document ingestion or execute reports with an administrator’s unrestricted connection.
- **Shared content:** add ownership and grants before team sharing. Recompute for each viewer/recipient. Do not turn the existing isShared boolean into public unrestricted data access.
- **Semantic change management:** one published revision must drive Chat, Builder, boards, coaching and alerts. Invalidate/revalidate dependent definitions and cache entries on changes; approval is a product workflow to implement, not a reason to edit live definitions silently.
- **Explainability:** contributor analysis is evidence of association, not causal proof. Forecasts require history checks, backtesting and uncertainty; leave sophisticated forecasting out of the first upgrade.

## Reuse and defer

**Reuse:** the existing semantic planner/compiler, structured analysis specs, chart recommendation, scoped execution, driver narration, catalog introspection, Data Trust and NLQ benchmark suites. Do not replace these with a new ungoverned text-to-SQL engine or attempt to reproduce ThoughtSpot’s proprietary search technology.

**Defer:** general autonomous agent builders, warehouse writeback, a Python notebook platform, dozens of connectors and native mobile apps. Revisit only when there is a concrete user/deployment need.

**Preserve as Ask Me’s identity:** visible Data Trust evidence, cited document context, regional business semantics, INR formatting and the clean Light/Dark/AI design system. Use ThoughtSpot as workflow inspiration rather than a branding or pixel-copy target.

## Pilot and success measures

Use the existing automotive and insurance benchmarks, plus a small stakeholder-approved set of dashboard-context, follow-up, comparison, ambiguous and denied-scope questions. Run both admin and region-restricted users. Measure verified answer correctness, security failures, time to first useful answer, saved-answer reuse, board return visits, alert usefulness and cost per successful answer. Establish a baseline before setting numerical targets; a comparison website cannot supply Ask Me’s real accuracy or latency.

## Inputs needed before committing scope

1. Main audience: internal leadership/analysts, external customers, or both.
2. First business domain and decision workflow to pilot.
3. Team/group sharing needs and identity provider; whether sensitive columns or multiple organizations are in scope.
4. Whether users actually need a second data source, scheduled external delivery or embedded analytics.
5. Hosting/worker availability and notification channels. These determine delivery scope and effort, not whether the first answer/context improvements can be designed.

**Implementation status:** review artifacts only; application code, schemas, APIs and dependencies were not changed by this review.
