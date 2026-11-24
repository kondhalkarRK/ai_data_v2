# ASK-DB — Semantic coverage & Streamlit snappiness

## 1) Why trust semantic was 0/25

On PostgreSQL, glossary matches were used in the SQL prompt but **not saved** to `last_glossary_matches`, so Data Trust Score always scored semantic as **0**.

Also, business language like *sale / selling / top selling / across year* was missing from the insurance glossary.

**Fixed**
- Persist glossary matches on the Postgres NLQ path (feeds semantic + glossary trust components).
- Expanded `semantic/packs/insurance/business_glossary_postgres.yaml` + model synonyms.
- Normalized `domain_rules` to dict (`always_rules` / `never_rules` / `default_behaviours`) so base semantic context injects again.
- Pack YAML auto-reloads when glossary file mtime changes.

Example: **“top selling policy across year”** now matches Top Selling + GWP + Accounting Year (+ Policy) → semantic should land **25/25** (2+ matches).

## 2) Stronger semantic without loading the full warehouse

Do **not** pull 1.5M rows into pandas to “guess questions.” Use:

| Source | What we use |
|--------|-------------|
| Column catalog | roles: measure / date / dimension |
| Glossary synonyms | user language → SQL expression |
| SQL patterns | ranking / year / LOB templates |
| Sample question bank | coverage audit |

Run:

```bash
python tools/audit_insurance_semantic_coverage.py
python tools/audit_insurance_semantic_coverage.py --probe-db
```

Add missing synonyms to the pack YAML, restart (or let mtime auto-activate), re-ask.

Faster LLM execution comes from **smaller, sharper prompts** (matched measures + rules), fewer SQL retries — not from dumping all data into context.

## 3) Streamlit lag (tabs / expanders)

Root cause: every click re-ran **Preview + KPI + full Chat** (and expanders still execute Python when collapsed).

**Fixed**
- **One active view** (radio) instead of `st.tabs` that always ran all three.
- TTL cache for Postgres `list_relations` / `table_row_counts` (120s).
- Preview: DQ + joined SQL only when you check **Load**.
- Chat: render last **12** messages; “Show earlier” for the rest.
- Boot splash only on first semantic load.

Restart Streamlit to pick up changes.
