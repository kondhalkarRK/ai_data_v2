# ASK-DB Insurance — Leadership Notes  
### One briefing: where data lives, how a question runs, what reaches Streamlit, how results appear

**Audience:** Leadership / sponsors / architecture review  
**Product:** ASK-DB (Streamlit) · Insurance pilot · PostgreSQL warehouse  
**Companion files:**  
- Test list → [`insurance_test_questions.md`](insurance_test_questions.md)  
- Flow + architecture diagrams → [`diagram/askdb_insurance_architecture.html`](diagram/askdb_insurance_architecture.html) · SVG downloads in same folder  

---

## 1. Elevator pitch (30 seconds)

Users ask insurance questions in plain English. ASK-DB uses a **semantic layer** (glossary + business model) so the LLM writes **safe PostgreSQL SQL**. The database does the heavy work on **~1.5 million claims** (plus policies and premium months). Streamlit only receives a **small result frame** (capped), then shows table, chart, and narrative. We do **not** load the warehouse into the browser or into Pandas for analysis.

---

## 2. Where the data is stored

| Layer | What | Approx. scale (pilot) | Notes |
|-------|------|------------------------|--------|
| **PostgreSQL** `askdb_dev` / schema `insurance` | Facts & dims | **~1.5M claims**; ~200k policies; ~1.4M policy-month rows | Source of truth for numbers |
| Key tables | `fact_claims`, `fact_policy_monthly`, `dim_policy`, `dim_product`, `dim_region`, `dim_agent`, … | Physical rows stay in DB | Indexes (e.g. `reported_date`) for windowed queries |
| App DB user | `askdb_app` | Read-only | Cannot INSERT/UPDATE/DELETE |
| **Semantic YAML** (repo / activated pack) | Business meaning | Small files | Measures, dimensions, domain rules, synonyms (East→region, Motor→LOB) |
| **Streamlit session** | Chat history, last SQL anchor, tiny DataFrames | Kilobytes–megabytes | Never the full 1.5M claim table |
| Optional **docs / OKF** | Policies, commentary | Separate from warehouse numbers | Narrative context — not a substitute for SQL totals |

**Leadership takeaway:** Storage and compute for analytics live in PostgreSQL. The UI is a thin, governed front door.

---

## 3. End-to-end: what happens when someone asks a question

```
User question
    → Streamlit Chat (session only)
        → Incomplete? → 2 suggestion chips (insurance-aware) → stop until user picks
        → Else NLQ engine
            → Semantic context + glossary + schema catalog
            → LLM generates one read-only PostgreSQL SELECT / WITH
            → SQL guardrails (block DML/DDL / unsafe)
            → PostgresBackend wraps: LIMIT ≤1000 (+1 for overflow detect), ~30s timeout
            → PostgreSQL aggregates / joins on warehouse
            → Small DataFrame returned to app
            → Format (dates, 1-based row index)
            → UI: Insight + Table (display ≤100) + Chart + evidence / narration
```

### Step detail (talk track)

1. **Chat intake** — Question stays in Streamlit session. Spinner: “ASK-DB is querying…” (backend-neutral).  
2. **Completeness check** — Vague asks (`East`, `show claims`) get **two** business suggestions so users refine intent.  
3. **Semantic enrichment** — Glossary maps “GWP”, “East”, “Motor”, “loss ratio” to the right tables/expressions. Domain rules tell the model: multi-column answers, premium from policy-month, ranks from 1.  
4. **LLM writes SQL** — One SELECT; no warehouse dump into the model. Schema + YAML only.  
5. **Guardrails** — Only read-only SQL proceeds.  
6. **Execute in Postgres** — Joins/aggregates run next to the data. App never `SELECT *` of 1.5M into memory for chat.  
7. **Bound the payload** — Backend allows at most **~1,000 rows** into the app.  
8. **Present** — Chat table display cap **100 rows**; expandable Insight / Table / Chart; optional narration and trust/evidence metadata.

---

## 4. How much data reaches Streamlit? (critical for leadership)

| Stage | Volume | Example |
|-------|--------|---------|
| Warehouse scanned | Up to millions of rows **inside Postgres** | All claims in 2025 for East |
| Rows returned to app | **≤ ~1,000** (`max_result_rows`) | Aggregate by region → often **4 rows** |
| Rows shown in Chat table | **≤ 100** (`RESULT_DISPLAY_LIMIT`) | User can expand; still capped |
| Preview / DQ sample | **LIMIT 100** joined preview; DQ uses **counts + windowed** tests | Not full history dump |
| KPI tab | **Small aggregate result sets** (YTD / calendar / rolling / full-history windows) | Cards + small charts |

**One sentence for the room:**  
*“Postgres does the 1.5M-row work; Streamlit only paints the answer grid — typically dozens of rows, hard-capped at a thousand into the app and a hundred on the chat table.”*

---

## 5. How results are processed and shown

| Piece | Behaviour |
|-------|-----------|
| **Table** | Business columns (e.g. region_name, claim_count, claims_incurred). Row index **1-based** for readability. PII masked on display where configured. |
| **Chart** | Auto-picked from result shape (bar/line/…); user can change axes. |
| **Insight / narration** | LLM summarises the **small result**, not the raw warehouse. |
| **Evidence** | SQL + row/col counts + resolution path (cache vs fresh semantic). |
| **Rankings** | Prompt asks for `ROW_NUMBER()` starting at **1**. |
| **Follow-ups** | Last successful SQL is an **anchor** (“only East”, “by product”) so conversation stays coherent. |

---

## 6. Business context the model is taught to understand

Examples the semantic layer encodes:

| User says | System should treat as |
|-----------|-------------------------|
| East / West / North / South | `dim_region.region_name` |
| Motor / Health / Property | `dim_product.line_of_business` |
| GWP / written premium | Sum from `fact_policy_monthly.written_premium` |
| Earned premium | From policy-month fact (never claim rows) |
| Loss ratio | Incurred claims ÷ earned premium (compatible grain) |
| Customer / policyholder | `dim_policy.customer_key` |

Analytical answers should return **dimension + metric(s)**, not a lone anonymous sum — unless the user asks for one number.

---

## 7. Parallel surfaces (same architecture rule)

| Surface | Role | Data pattern |
|---------|------|----------------|
| **Chat / Ask** | Ad-hoc NLQ | SQL → ≤1k → UI ≤100 |
| **KPI** | Executive cards | Windowed SQL aggregates |
| **Preview** | Sanity sample | Joined claims **LIMIT 100** |
| **Data Quality** | Inventory + health | Exact `COUNT(*)`; quality on rolling windows |

All of them keep heavy compute in PostgreSQL.

---

## 8. Security & trust (short)

- App DB role is **read-only**.  
- Guardrails reject mutating SQL.  
- Statement **timeout** (~30s) so bad queries fail closed instead of hanging the UI.  
- Numbers are **SQL-sourced**; documents (if used) are commentary, not substitutes for totals.

---

## 9. How to use the test question list with leaders

Walk **simple → complex** from [`insurance_test_questions.md`](insurance_test_questions.md):

1. Show clarification on `East`.  
2. Run a region claim question (multi-column).  
3. Loss ratio by region (ratio + supporting columns).  
4. Top products with **rank 1**.  
5. Optionally KPI/DQ to reinforce “warehouse stays in Postgres.”

---

## 10. Diagrams to open in the meeting

| File | Use |
|------|-----|
| [`diagram/askdb_insurance_architecture.html`](diagram/askdb_insurance_architecture.html) | Full architecture + flow (print/PDF friendly) |
| [`diagram/askdb_insurance_architecture.svg`](diagram/askdb_insurance_architecture.svg) | Drop into PowerPoint / Confluence |
| [`diagram/askdb_insurance_query_flow.svg`](diagram/askdb_insurance_query_flow.svg) | Single-path query flow |
| [`diagram/askdb_e2e_query_flow.html`](diagram/askdb_e2e_query_flow.html) | Earlier E2E pack (same story) |

---

## 11. Bottom line for decision-makers

ASK-DB is a **governed NL-to-SQL cockpit** on an insurance warehouse: semantic understanding for business language, Postgres for scale, Streamlit for conversation and visualisation — with explicit caps so the UI never becomes a million-row spreadsheet.
