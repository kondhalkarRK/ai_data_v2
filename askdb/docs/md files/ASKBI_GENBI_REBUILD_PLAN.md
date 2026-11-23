# AskBI GenBI rebuild — implementation tracker

The detailed proposal was reviewed in the preceding conversation on 2026-11-05.
That file was absent from this checkout when implementation began; this tracker
restores its requirements and records implementation/verification separately.

## Required release

- Automotive only; preserve insurance, Custom reports and general AI Chat.
- Restore Custom Report / Auto Report · AskBI. Use a report canvas with one
  responsive conversation sidebar, supported chart editing, evidence and exports.
- LLM-led interpretation, contextual follow-ups and evidence-based narration;
  governed metric definitions and exact template fast paths save tokens.
- No fixed four-chart default; single KPI, chart, table or bounded report.
- Server-owned conversation/clarification state, optimistic revisions, typed
  errors, idempotent turns, Undo, saved/imported reports and explicit refresh.
- Semantic catalog/glossary/value retrieval, deterministic SQL compilation,
  explicit day/week periods, weighted ratios and missing/partial period handling.
- Independently gated advanced analysis; generated SQL must pass structural,
  scope and intent validation. Never silently enable unrestricted SQL.
- Scoped evidence, validated narrative references and deterministic fallback.
- Bounded requests, query reuse, up to two independent panel requests, optional
  narration after results, stale-response protection, honest usage reporting.
- Reversible rollout and visible frontend/API capability mismatches.
- No agents, tool calling, autonomous loops or agent dependencies.

## Delivery phases

0. Baseline: inspect current code; office failures/build/logs remain unavailable.
1. Restore modes and report shell; keep legacy route/data compatibility.
2. Typed conversation, clarification, semantic planning and validation.
3. Governed execution, calendar grains, evidence and independent panel results.
4. Bounded advanced query coverage and structural validation gate.
5. Grounded narration, edits/Undo, persistence and legacy imports.
6. Local correctness/flow checks and build; office-only PostgreSQL/provider
   acceptance and latency measurements deferred, never implied by mock tests.

## Acceptance requirements

Totals; daily last-week sales; focused reports; explicit chart counts; short
clarification answers; contextual regional filters; selected-chart presentation
edits without SQL; aligned period comparisons; top-N per group; weighted ASP;
seven-day calendar moving average; rejection of incompatible target grain;
full-scope contribution denominators; qualified driver analysis; unsupported
profit/discount requests; ambiguous second-week dates; malformed/empty/provider
failures; partial/no-data/null/truncated results; rapid updates; save/import/Undo
and revision conflicts; prompt injection and cross-region/owner access; rollout
flag/build mismatches. Test behavior and numerical/security invariants rather
than fonts or other low-impact styling.

## Budgets and release gates

No per-panel LLM loops. Typical request: one interpretation and one optional
narration call; core maximum three calls including one shared correction.
Six distinct data queries per turn, no mandatory composition. Data edits rerun
only affected specifications; presentation edits reuse compatible data.
Initial target p95 first result: templates 3s, novel analyses 8s; reports 15s.
These are targets, not measured results. Include auxiliary query counts.

Live services are absent on this laptop. Do not run local PostgreSQL or provider
connectivity tests. Use fixed-clock numerical fixtures, mocked providers, local
SQLite persistence, UI flow tests, typecheck, lint and build. A complete live
acceptance requires the office environment; report incomplete gates explicitly.

## References

Reviewed WrenAI main tree: 548eee3e864b11e7f11eee15ae82be178a295f22;
Classic tree: ce9ed54c86acb8a0b6ff5d5fea23ed60f057acfc. Adopt semantic context,
explicit states, bounded validation/repair and separate chart refinement;
do not install the agent platform or frozen Classic application.

- [WrenAI](https://github.com/Canner/WrenAI)
- [Classic ask pipeline](https://github.com/Canner/WrenAI/blob/legacy/v1/wren-ai-service/src/web/v1/services/ask.py)
- [Chart generation](https://github.com/Canner/WrenAI/blob/legacy/v1/wren-ai-service/src/pipelines/generation/chart_generation.py)
- [ThoughtSpot report editing](https://docs.thoughtspot.com/cloud/26.10.0.cl/spotter-viz)

## Implementation status — 2026-11-05

Phases 1–3 and 5 have an implemented, offline-verified foundation: restored modes,
conversation state, semantic planning, scoped execution, calendar grains,
evidence/narration, edits and persistence. Legacy imports have documented
compatibility limits. Phase 0 inspected the local code; actual office failure
logs/data remain unavailable. Phase 4 is intentionally narrower than general GenBI:
only z-score and index-to-average benchmark SQL is implemented behind the separate
advanced flag. Broader generated-query/driver coverage remains open.

Phase 6 has passing local numerical/security/flow tests and fixture-based browser
checks. Live PostgreSQL/provider acceptance, migration application and measured
latency targets remain pending on the office laptop. No trivial cosmetic tests
were added. See `ASKBI_IMPLEMENTATION.md` for exact checks, activation, rollback
and remaining limits; this tracker is not a claim of complete WrenAI parity.
