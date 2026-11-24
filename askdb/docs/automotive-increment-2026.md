# Automotive September-November 2026 increment

As of 24 November 2026. **No live database load has been performed.**

The prepared files are a market-informed **synthetic dealer-network sample**, not actual
customer transactions or national market totals. Existing history is retained.

## Current evidence and review

The user confirmed that PostgreSQL runs only on the office laptop. Read-only inspection
from this environment therefore could not connect. No credentials or server diagnostics were printed.
The checked-in CSV files cannot establish the current office database's coverage.

The checked-in CSV snapshot contradicts the assumption of only a few September rows:

| Month | Existing orders | Existing units | Existing revenue, INR |
| --- | ---: | ---: | ---: |
| June 2026 | 18,498 | 19,225 | 23,168,069,400 |
| July 2026 | 18,606 | 19,276 | 23,345,872,200 |
| August 2026 | 19,477 | 20,296 | 24,476,530,000 |
| September 2026 | 17,658 | 18,368 | 22,139,167,500 |
| October 2026 | 378 | 392 | 468,787,800 |

All those rows were preserved in the candidate. They were not assumed to be manual rows.
The live database must be exported and the increment restaged before load approval.

Review files are in `database/data_csv_files/india_auto_increment_final_20261124/`:

- `review.html`: monthly before/after units and a daily festive chart.
- `coverage_before.json`: monthly orders, units, revenue, makes/models, fuels, regions,
  daily coverage and sparse-day flags. Sparse does not mean invalid.
- `monthly_after.csv`, `daily_after.csv`: exact proposed combined totals.
- `benchmark_comparison.csv`: synthetic make/fuel shares against applicable published
  references; November has no published full-month actual in this plan.
- `bucket_conflicts.json`: existing model allocations above the nominal plan, retained.
- `sources.json`, `reference_model_calendar.csv`: source evidence and availability assumptions.
- `dim_carline.csv`, `fact_sales.csv`: additions only; no replacement historical files.
- `validation.json`, `manifest.json`: checks, seed, batch ID, protected-history fingerprints,
  baseline inventory, target identity where available and file checksums.

CSV-based candidate totals:

| Month | Before units | Added units | After units | Coverage |
| --- | ---: | ---: | ---: | --- |
| September | 18,368 | 2,537 | 20,905 | Complete synthetic month |
| October | 392 | 24,455 | 24,847 | Complete synthetic month |
| November | 0 | 24,416 | 24,416 | Synthetic MTD through 23 November |

The increment contains **48,992 new orders / 51,408 units**, retaining original quantities
rather than treating order count as unit count. Numbers will differ after restaging against
the live database if its inventory differs. The combined daily sample peaks on **7 November**,
inside the 4-9 November festive window. This is a generated assumption, not a published
daily retail figure. Diwali is 8 November and Dhanteras is modelled around 6 November.

## Sources, assumptions and limitations

Pinned configuration: `database/automotive/refresh_2026_sources.json`.

- [FADA October report](https://www.fada.in/images/press-release/16aed49cca8e14FADA_Press_Release_Oct_26.pdf):
  September PV retail 427,213; October 507,768. The sample uses their ratio for the
  October/September volume relationship. This is not OEM wholesale or export data.
- [FADA festive report, 23 November](https://fada.in/images/press-release/16b03c447ab70cFADA_Press_Release_42%20Days%20Festive%20Vehicle%20Retail%20Data%202026_FINAL.pdf):
  supports festive timing/context, not a complete November monthly total.
- [Government holiday calendar](https://www.indiapost.gov.in/holidays-list): Diwali date.
- [Renault announcement](https://cdn.group.renault.com/ren/in/pressrelease2026/september/Press%20release.pdf.asset.pdf/1790597861979.pdf):
  Triber 100PS launched 28 September. Existing Triber model identity stays unchanged;
  the new turbo carline is distinct. Synthetic availability begins 1 October.
- [Hyundai announcement](https://org3.hyundai.com/in/en/hyundai-story/media-center/press-release/hmi-launches-hyundai-bayon-price):
  Bayon launched 26 October with a 1.5L petrol engine. Synthetic availability begins
  1 November. Exact first-delivery dates were not verified for either addition.

September's sample total assumes 3% above August. November's hypothetical full-month
scenario assumes 15% above October, then weights only completed days through 23 November.
Neither factor is claimed as a published market actual. Daily, regional, model and price
allocations are synthetic. Transaction prices use existing sample means with assumed
0.2% monthly drift and bounded variation; new means are explicit assumptions. Ex-showroom
launch prices are not represented as verified realised revenue.

The schema accepts Petrol, Diesel, Hybrid and Electric only. FADA's CNG/LPG share is
therefore not represented: remaining fuel shares are renormalised as a conditional sample.
This is **not** full-market fuel coverage. Combined OEM groups lacking an unambiguous
mapping retain a sample-based prior; no precise split is invented. Existing allocations
that exceed nominal buckets are preserved, so the sample need not match every benchmark.

Kia Sorento and Duster hybrid were considered but not assigned speculative sales: their
completed source/specification/delivery evidence needs further verification in this review.
The new rows use existing active dealers, salespeople and colours; no new people or real
customer PII is introduced. Targets and forecasts remain unchanged and separate.

## How staging and loading work

1. Stream all eight source tables using the existing generator's column contract.
2. Fingerprint all baseline rows and separately fingerprint protected sales through
   **31 August 2026**. Fingerprints preserve row multiplicity and are order-independent.
3. Account for September-onward existing units before generating additions. Preserve
   overshoots; never generate negative adjustments or deduplicate by date/model/price.
4. Reuse the original model calendars and observed make/dealer/salesperson relationships.
   Match existing carlines by identity, not assumed historical numeric IDs.
5. Stage new carline and fact rows, checksums, conflicts, coverage, chart and validation.
6. At approved load time, confirm the target database identity, take write-blocking table
   locks and recheck the complete baseline. A concurrent/manual change requires restaging.
7. Insert additions and a persistent `automotive.demo_increment_batches` journal in one
   transaction. Verify stored rows, protected history and refresh the monthly materialised
   view. A constraint/check failure rolls the data transaction back.
8. A repeat application of the identical batch verifies its rows and inserts zero facts.
   Modified artifacts or a partial/changed previously loaded batch cause a refusal.

The CLI creates the data-operation journal only during an approved load; no application
database Alembic migration is needed. It needs the configured migration/owner connection
for writes and the reader connection for inspection. It never uses TRUNCATE, drops indexes,
removes constraints or rewrites targets/forecasts. Schema drift is reported before export.

## Office execution and approval steps

Run from `E:\ai_data_rag\ai_data_v2\askdb`, using the existing API virtual environment.
Do not reinstall packages or recreate the database. Confirm PostgreSQL is running and the
Automotive reader/owner URLs in this project's `.env` point to the intended demo database.

### A. Export live coverage, without changing the database

```powershell
.\apps\api\.venv\Scripts\python.exe scripts/refresh_automotive_increment.py --snapshot-db data/staging/automotive_live_20261124
```

Use a fresh output directory if retrying an interrupted export. Inspect `coverage.json`
and `snapshot.json`. Exports may contain existing employee information; keep the directory
private. Do not publish office snapshots or credentials to Git.

### B. Stage against that exact live snapshot

```powershell
.\apps\api\.venv\Scripts\python.exe scripts/refresh_automotive_increment.py --stage-from data/staging/automotive_live_20261124 --out data/staging/automotive_review_20261124 --as-of 2026-11-24
```

Open the new `review.html` and inspect the manifest, new rows, conflicts and validation.
The tool refuses dates after its research as-of date; refresh source evidence before
preparing a later period. Do not reuse the CSV candidate as a live batch.

### C. Back up and approve the concrete live increment

After confirming host, user and database against the live snapshot, create a backup.
Example for the usual local demo database (adjust connection identifiers if different):

```powershell
pg_dump --host localhost --port 5432 --username askdb_owner --dbname askdb_automotive --schema automotive --format custom --file data/staging/automotive_before_increment.dump
```

Use the password prompt or a protected PostgreSQL password file. Do not put a password
in command history. Check the exit status and inspect the archive with `pg_restore --list`.
Review the exact batch ID and rows with the user before proceeding to D.

### D. Apply only after approval

```powershell
.\apps\api\.venv\Scripts\python.exe scripts/refresh_automotive_increment.py --apply data/staging/automotive_review_20261124 --approve-batch <EXACT_REVIEWED_BATCH_ID>
```

Use the ID in the **live** manifest. Do not use the candidate's ID.
The loader refreshes `mv_sales_monthly`, then runs the existing Automotive Entity Catalog
and Data Trust services. It makes no LLM calls. The metadata refresh writes only the
application catalog/trust records for Automotive; Insurance is not refreshed.

**Restart all API workers after loading** to discard each worker's in-memory caches.
A separate CLI cannot invalidate caches in other running processes. Check `post_refresh.json`,
then test new values and report results in the app. Review any Data Trust incidents rather
than treating a completed check run as proof of healthy data.

If data committed but metadata refresh failed, the command exits with a separate
`metadata_refresh_failed` status. Do not use a replacement loader. Fix connectivity/schema
and retry only metadata:

```powershell
.\apps\api\.venv\Scripts\python.exe scripts/refresh_automotive_increment.py --refresh-metadata data/staging/automotive_review_20261124 --approve-batch <EXACT_REVIEWED_BATCH_ID>
```

### E. Scoped rollback, only if needed and approved

```powershell
.\apps\api\.venv\Scripts\python.exe scripts/refresh_automotive_increment.py --rollback data/staging/automotive_review_20261124 --approve-batch <EXACT_REVIEWED_BATCH_ID>
```

Rollback verifies that the batch rows have not changed, removes only its fact IDs and new
carline IDs, marks the journal and refreshes dependent metadata. If later data references
those new carlines, the foreign key blocks deletion and the whole rollback aborts.
Restart API workers after a successful rollback too. A full backup restore is a separate,
potentially destructive recovery action and is not automated here.

## Verification and remaining acceptance

Automated tests cover quantity versus order count, protected inventory immutability,
deterministic staging, no-overwrite guards, launch dates, foreign keys, roster relationships,
overshoots, festive variation, stale research, checksum tampering and refusal to write CSV
candidates or unapproved batches. Original generator tests are also rerun. The combined
increment, original generator, entity catalog, semantic grounding and governed planner
suite passed **49 tests**. Vehicle-name checks validate the new model and variant filters
and generated SQL without a provider call. These are fixture checks, not live acceptance.

Live PostgreSQL transaction/locking/COPY behaviour, repeat-load and rollback acceptance,
database permissions, metadata services, office gateway and the four application screens
still need live acceptance because PostgreSQL could not be reached here. Do not describe
fixture tests as live database or UI verification.

After the approved load, check Chat comparisons and new models, KPI periods, Analytics
Builder, Executive Intelligence, regional restrictions, actual-versus-target, November MTD
labelling and SQL/result consistency. Verify that source/model/forecast labels stay clear.

The old `20_daily_refresh_small.sql` is now an explicit no-write refusal: copying yesterday's
orders is not a reliable market refresh and can conflict with approved increments.

## Changed files in this refresh

- `apps/api/app/analytics/automotive_increment.py`: incremental generation and review artifacts.
- `scripts/refresh_automotive_increment.py`: snapshot, approval-gated load, refresh and rollback.
- `apps/api/tests/test_automotive_increment.py`: incremental and new-vehicle semantic checks.
- `database/automotive/refresh_2026_sources.json`: dated references and modelling assumptions.
- `database/automotive/20_daily_refresh_small.sql`: retired unsafe daily cloning.
- `database/automotive/README.md` and this runbook: incremental execution instructions.
- `apps/api/semantic/packs/automotive/semantic_model.yaml`: variant domain and new aliases.
- `apps/api/semantic/packs/automotive/entity_catalog.yaml`: vehicle-variant catalog grouping.
- `database/data_csv_files/india_auto_increment_final_20261124/`: review-only CSV candidate.
- `.gitignore`: private office snapshots and backups under `data/staging/`.

No application migration is required. The approved loader creates its own Automotive
batch journal transactionally. Insurance, agentic code and original source CSVs are untouched.
