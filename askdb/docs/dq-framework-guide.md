# Data Quality (DQ) Framework Guide

Scope: the DQ framework as currently implemented in `askdb/apps/api` (backend) and the
Data Trust Center UI in `askdb/apps/web`. There are **no DQ-specific YAML, JSON or SQL
files**: all thresholds, weights and SLAs are Python constants. Table lists come from
the semantic pack (`semantic/packs/{industry}/semantic_model.yaml`), which DQ only reads.

## 1. Files

| Layer | File | Responsibility |
|---|---|---|
| Engine | `app/analytics/data_quality.py` | `compute_data_quality(rows)`: runs every check on a row sample and computes the **health score** |
| Engine | `app/services/data_quality.py` | `DataQualityService.evaluate()`: resolves the table from the pack, samples the latest rows, calls the engine |
| Trust | `app/services/trust/config.py` | Trust dimension weights, per-table freshness SLAs, notification rules |
| Trust | `app/services/trust/scoring.py` | Dimension scores, weighted Trust Score, status labels, incidents, rules |
| Trust | `app/services/trust/__init__.py` | `DataTrustService.get_center()`: orchestrates everything; freshness probe, schema drift, steward text, cache, rule threshold overrides |
| API | `app/api/routes/trust.py` | `GET /trust/center`, `GET /trust/snapshot`, `PATCH /trust/rules/{id}`, `POST /trust/steward/feedback` |
| API | `app/api/routes/data.py` | `GET /data/quality/{table}`: raw report for one table |
| Schemas | `app/schemas/data.py` (`DataQualityReport`), `app/schemas/trust.py` | Response models |
| Executive | `app/services/executive/__init__.py` (`_data_quality_notice`, `_null_pct`), `executive/domain_config.py` (`dqTables`) | Separate, simplified DQ banner on the Executive dashboard |
| UI | `apps/web/app/(workspace)/data-quality/page.tsx`, `components/trust/*`, `hooks/use-trust-snapshot.ts` | Data Trust Center page; trust badge on the dashboard, home page and chat cards |
| Tests | `tests/test_data_phase3.py`, `tests/test_data_trust.py` | Engine score and dimension, incident and rule tests |

## 2. Available checks (engine)

`compute_data_quality` runs on a sample of the **latest rows** of each table: up to
2,000 rows for the Trust Center, and up to 5,000 (capped by `sql_max_result_rows`) for `/data/quality`.

| Check | Rule | Output |
|---|---|---|
| Nulls | Null cells per column and overall | `null_summary`, `total_null_pct` |
| Duplicates | Fully identical rows | `duplicate_count`, `duplicate_pct` |
| Outliers | Values outside Q1 − 3×IQR … Q3 + 3×IQR, only on "metric-like" numeric columns (name heuristics, ≥ 10 values, IDs and keys excluded) | `outliers` |
| Type issues | Text column where ≥ 85% of values parse as numbers | `type_issues` |
| Cardinality | Text column with >95% unique values (and >100 distinct), a single constant value, or all values unique (>50 rows) | `cardinality_flags` |
| Date gaps | Missing calendar months between the first and last month of the detected date column (needs ≥ 3 months; up to 12 reported) | `date_gaps`, `date_col` |
| Freshness (Trust layer) | Hours since `MAX(date_col)` compared with the table's SLA | `freshness` dimension |
| Schema drift (Trust layer) | Hash of the table's column list in YAML versus the last hash seen by this process | `schema_changes` |

## 3. Scoring

### 3.1 Table health score (engine, 0–100)

```
100 − min(null% × 1.5, 25)
    − min(duplicate% × 2, 20)
    − min(outlier columns × 3, 15)
    − min(type issues × 4, 16)
    − min(cardinality flags × 2, 10)
    − min(missing months × 1, 10)
```
Shown on each dataset card. A fact table with a score of at least 90 is marked "certified".

### 3.2 Trust dimensions (per table, 0–100): `scoring.dimension_scores`

| Dimension | Formula | Why it matters |
|---|---|---|
| **Completeness** | 100 − null% × 1.5 | Missing values silently shrink totals and averages. |
| **Uniqueness** | 100 − duplicate% × 2 | Duplicate rows double-count revenue and units. |
| **Validity** | 100 − min(type issues × 8, 40) − min(outlier cols × 4, 20) | Wrong types break aggregation; extreme values distort KPIs. |
| **Consistency** | 100 − min(cardinality flags × 5, 30) − min(date gaps × 4, 20) | Missing months break trends; odd cardinality signals mis-modelled columns. |
| **Freshness** | 100 if age ≤ SLA; otherwise 100 − (overdue ÷ SLA) × 40; **fixed 70** when the age or SLA is unknown | Stale data gives correct SQL but outdated answers. |
| **Schema stability** | 100 − min(type issues × 10, 50) (proxy: there is no schema history) | Column changes can break semantic mappings and KPIs. |
| **DQ rule success** | % of 5 soft checks passing: nulls < 5%, duplicates < 1%, no type issues, no date gaps, no outliers | A single pass-rate summary of rule health. |

### 3.3 Overall Trust Score: `scoring.aggregate_trust_score`

Each dimension is averaged across all scored tables (up to 12, fact tables first). The
Trust Score is the weighted mean of those averages, using the weights in `config.TRUST_SCORE_WEIGHTS`:

| Freshness | Completeness | Uniqueness | Validity | Consistency | Schema stability | DQ rule success |
|---|---|---|---|---|---|---|
| 0.18 | 0.18 | 0.14 | 0.14 | 0.12 | 0.12 | 0.12 |

Labels: ≥ 90 Healthy · ≥ 75 Watch · ≥ 50 At risk · otherwise Critical (`label_for_score`).
Per-dimension flags: ≥ 90 ok · ≥ 75 warn · otherwise fail.

## 4. Rules and incidents

**Rules** (`build_rules_for_table`, 5 per table):

| Rule | Dimension | Pass condition | Editable in UI |
|---|---|---|---|
| Null percentage threshold | completeness | null% < 5 | yes |
| Duplicate row threshold | uniqueness | duplicate% < 1 | yes |
| No type/validity issues | validity | 0 type issues | no |
| No date gaps in grain | consistency | 0 gaps | no |
| Freshness within SLA | freshness | freshness score ≥ 85 | yes (has no effect, see §6) |

**Incidents** (`build_incidents_for_table`):

| Incident | Raised when | Severity |
|---|---|---|
| Freshness | Age exceeds SLA and freshness < 85 | high if the delay is at least one full SLA period, otherwise medium |
| Completeness | completeness < 80 | high if null% ≥ 10, otherwise medium |
| Validity | any type issue | medium |
| Date gaps | any missing month | low |

## 5. Execution flow

```
GET /trust/center  (Data Trust Center page, home page; cached 5 min per industry)
  └─ DataTrustService.get_center
       for each pack table (facts first, max 12):
         DataQualityService.evaluate      → SELECT * … ORDER BY pk DESC LIMIT 2000 (guarded)
         compute_data_quality             → checks + health score
         _freshness                       → SELECT MAX(date_col); compared with the SLA
         dimension_scores                 → 7 dimensions
         build_rules / build_incidents    → rules (+ in-memory threshold overrides), incidents
         _detect_schema_drift, lineage, governance records
       aggregate_trust_score → Trust Score + label → steward summary → cached response

GET /trust/snapshot   → reads the cached score (or computes it); used by dashboard, home page and chat trust badge
PATCH /trust/rules/id → stores a threshold override and clears the cache
GET /data/quality/t   → one table's raw engine report
```

## 6. Configured but not actively used (or with no effect)

| Component | Where | Status |
|---|---|---|
| Notification rules (webhook, email) | `config.DEFAULT_NOTIFICATION_RULES` | Both `enabled: False` with an empty target; there is no delivery code. They are only displayed. |
| SLA for `insurance.dim_customer` | `config.DATASET_SLA_HOURS` | The table does not exist in the insurance pack, so this entry is never used. |
| Tables with no SLA | automotive `dim_color`, `dim_salesman`, `dim_targets`; insurance `dim_policy`, `dim_agent` | Freshness is always a fixed 70, which lowers the Trust Score. The same applies to any table without a detectable date column. |
| Freshness rule threshold edit | `update_rule_threshold` + override logic in `get_center` | Overrides are only re-evaluated for `percent` rules, so editing this (`score`) rule changes the displayed number but never pass/fail. |
| Rule overrides | `_RULE_OVERRIDES` (in memory) | Lost on restart, and keyed only by table name: an override for `dim_region-…` applies to **both** industries. |
| Schema drift | `_detect_schema_drift` | Compares YAML column lists within one process, not the live database, so it effectively never fires. Timeline dates are fixed offsets (now − 2 days, now − 1 day), and `type_changes` is always empty. |
| Schema stability | `dimension_scores` | A proxy based on type issues; there is no real schema history. |
| Trend sparklines and score history | `_SCORE_HISTORY` (in memory) | Filled only by repeated evaluations in the same process; reset on restart. |
| Incident history, MTTR, root cause | `incident_history`, `time_to_*`, `rootCauseHint` | Always empty or `None` by design; no incident store exists. |
| `spikes`, `n_num`, `n_txt`, `n_date`, `n_bool`, `total_null_cells` | `compute_data_quality` output | Computed (spikes is always `{}`), then dropped: not part of `DataQualityReport`. |
| `GET /data/quality/{table}` | `routes/data.py` | Working endpoint, but no frontend page calls it. |
| Executive dashboard DQ banner | `executive._data_quality_notice` | A **separate, simpler** check: null % of one hard-coded date column (fact tables only), or a fixed 98 fallback. It does **not** use the DQ engine, so its number can differ from the Trust Center. |

Related but out of scope: the chat **answer** trust score (`services/chat/trust.py`) rates
SQL grounding (semantic, glossary, validation, joins), not data quality.
