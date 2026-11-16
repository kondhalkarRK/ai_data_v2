# NLQ Analytics Query Model — Architecture Recommendation

## Pipeline (measured stages)

```text
User Question
→ Understanding / clarification / entity match
→ Semantic + glossary (templates)  [cached pack]
→ LLM SQL (only if no template)    [8s budget, retry + circuit + fallback]
→ SQL validation (EXPLAIN dry-run)
→ Database execution               [10s NLQ statement_timeout]
→ Progressive stream: table → chart → summary
→ Profiler record (last 100 + EXPLAIN plan)
```

Trust shown in chat is **Dataset Trust** from Data Trust Center (`TrustIndicators`),
never a bare invented confidence %.

## Step 6 — Options A / B / C

| Option | Approach | Pros | Cons |
|--------|----------|------|------|
| **A** Current relational | Join at query time (`fact_*` + dims) | Accurate, maintainable, matches semantic pack | Multi-join cost on cold cache |
| **B** Precomputed analytics tables | Curated SalesAnalytics / ClaimAnalytics | Fast for common KPIs | Drift vs source; ETL ownership |
| **C** Materialized semantic views | `vw_vehicle_sales`, `vw_claim_analysis`, … | AI targets stable shapes; refresh controllable | Refresh lag; view sprawl |

### Recommendation (POC → production)

1. **Keep Option A as source of truth** for governed templates and LLM generation.
2. **Add Option C selectively** for the hottest NLQ paths (e.g. vehicle sales rollup,
   claims by status/region) once EXPLAIN plans show sequential scans or high join cost
   in the profiler (`GET /api/v1/chat/profiler`).
3. **Do not** flatten into one giant denormalized table unless benchmarks prove both
   latency and maintainability wins — Option B only for executive KPI cards that already
   tolerate daily refresh.

Indexes already present on `fact_sales(region_id, sales_date)`, dealer/region FKs, and
claim date columns should be verified after each schema change via profiler EXPLAIN output.

Connection pooling is already enabled (`db_pool_max_size`); interactive NLQ uses a tighter
`nlq_sql_timeout_seconds` (default 10) than batch warehouse jobs.
