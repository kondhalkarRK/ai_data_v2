# Parity checklist (Phase 7)

Sign off before retiring the legacy Streamlit app.

## Functional

| Area | Legacy source | NQL Insight | Status |
| --- | --- | --- | --- |
| Auth | Streamlit login | JWT cookies + roles | Done |
| Semantic packs | YAML packs | Validated packs + ontology | Done |
| Automotive warehouse | CSV/DuckDB | Postgres `automotive` + 1M seed | Done (needs local seed run) |
| Insurance warehouse | `askdb_dev` | Postgres `insurance` + 1M seed | Done (needs local seed run) |
| Data preview | `tab_preview` | `/data-preview` + keyset API | Done |
| Data quality score | `data_quality_engine` | `/data-quality` + fixture tests | Done |
| Insurance KPIs | `insurance_kpi_engine` | `/api/v1/kpis/summary` | Done (SQL port) |
| Automotive KPIs | `kpi_engine` | `/api/v1/kpis/summary` | Done (SQL port) |
| Scenario / what-if | `whatif_engine` | Forecast table + `/kpis/scenario` when seeded | Done (unlocks after 0002 migrate + seed) |
| Dashboard compare / cross-filter / export / presenter | Streamlit dashboard | Period delta, clickable breakdowns, CSV export, presenter chrome | Done |
| Materialized views | — | `mv_claims_monthly` / `mv_sales_monthly` | Done (migration 0002) |
| NLQ chat | `tab_query` | SSE + templates + OOB/clarify/surprise/what-if/follow-up/cancel | Partial (live golden SQL still needs LLM/warehouse) |
| Trust score | four components | `compute_trust_score` | Done |
| Saved questions / history / cost | session + llm log | APIs + pages | Done |
| RAG citations | OKF/Chroma | Filesystem + optional Mongo/Qdrant; PDF/DOCX; web allowlist | Partial (hash embed default; `[rag]` extras for parsers/clients) |

## Performance (§19)

| Target | Approach | Status |
| --- | --- | --- |
| No full fact DataFrames | SQL KPIs + capped preview | Done |
| Statement timeout + row cap | settings + pool options | Done |
| Keyset pagination | preview cursors | Done |
| First SSE frame before LLM | `stage: accepted` | Done |
| Theme toggle &lt; 50ms | client-only | Done Phase 1 |
| Ontology drawer no refetch | cached snapshot | Done Phase 2 |

## Deployment

| Item | Artifact |
| --- | --- |
| API container | `apps/api/Dockerfile` |
| Compose | `docker-compose.yml` (Postgres, Mongo, Qdrant, API) |
| Frontend | `vercel.json` → `apps/web` |

## Sign-off

- [ ] Both analytics DBs migrated and seeded on the target environment
- [ ] Golden insurance NLQ set reviewed against live warehouse
- [ ] Security checklist reviewed for production env vars
- [ ] Accessibility spot-check on dashboard, chat, ontology
- [ ] Legacy Streamlit retirement approved
