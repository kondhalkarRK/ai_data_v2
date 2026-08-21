# ASK-DB — PostgreSQL Setup Steps (Local)

Use these steps after PostgreSQL 17 is installed. Migration files live in `db/migrations/`.

---

## Before you start

| Check | Why |
|---|---|
| PostgreSQL Windows service is **Running** | App cannot connect otherwise |
| You know the **postgres** (superuser) password | Needed to create DB + role |
| Port is **5432** (default) | Matches secrets.toml |
| pgAdmin 4 opens and can connect | Easiest way to run SQL on Windows |
| Do **not** put real passwords in git | Keep them only in local `secrets.toml` |

---

## Step 1 — Install / start PostgreSQL

1. Install PostgreSQL 17 (or confirm it is installed).
2. Open **Services** (`services.msc`) and start `postgresql-x64-17` (name may vary).
3. Open **pgAdmin 4**.
4. Connect to **Servers → PostgreSQL 17** with the `postgres` password.

---

## Step 2 — Create database and app role

1. In pgAdmin, open **Query Tool** connected to the default database named **`postgres`**.
2. Open file: `db/migrations/000_create_database_and_role.sql`.
3. **Replace** `REPLACE_WITH_A_STRONG_LOCAL_PASSWORD` with a strong password you will remember.
4. Run the script.

What it creates:

- Role: `askdb_app` (login, no superuser, no create DB)
- Database: `askdb_dev`

### Important

- If you get `role "askdb_app" already exists`, skip the `CREATE ROLE` line or use `DROP ROLE` only if you know nothing else depends on it.
- If you get `database "askdb_dev" already exists`, skip `CREATE DATABASE` and continue to Step 3.
- Save the password somewhere private — you need the **same** password in Streamlit secrets.

---

## Step 3 — Create insurance schema and tables

1. In pgAdmin, **disconnect** from `postgres` and open Query Tool on **`askdb_dev`**.
2. Open and run: `db/migrations/001_insurance_schema.sql`.

What it creates:

- Schema: `insurance`
- Tables: `dim_product`, `dim_agent`, `dim_region`, `dim_policy`, `fact_claims`, `fact_policy_monthly`, `fact_operating_expense_monthly`
- View: `insurance.v_claims_enriched`
- Indexes on join/filter columns
- `GRANT SELECT` to `askdb_app` (if the role exists)

### Important

- Run this as an **owner/admin** user (usually `postgres`), not as `askdb_app`.
- `askdb_app` is **read-only** — it cannot create tables.
- Do not load claim premium into claim rows for loss ratio; premium lives in `fact_policy_monthly`.

---

## Step 4 — Load data (after tables exist)

Load order (respect foreign keys):

1. `dim_product`
2. `dim_agent`
3. `dim_region`
4. `dim_policy`
5. `fact_policy_monthly`
6. `fact_claims`
7. `fact_operating_expense_monthly` (optional)

In pgAdmin: right-click table → **Import/Export Data** → CSV, header = Yes, UTF-8.

Or with `psql` (if on PATH):

```sql
\copy insurance.dim_product FROM 'C:/path/dim_product.csv' CSV HEADER
```

### Important

- Start with a **small sample** (1k–50k rows) before 1M claims.
- After load:

```sql
SELECT COUNT(*) FROM insurance.fact_claims;
SELECT COUNT(*) FROM insurance.fact_policy_monthly;
ANALYZE insurance.fact_claims;
ANALYZE insurance.fact_policy_monthly;
```

---

## Step 5 — Verify read-only app user

In pgAdmin, connect as **`askdb_app`** to **`askdb_dev`**, then run:

```sql
-- Should work
SELECT COUNT(*) FROM insurance.fact_claims;

-- Should FAIL (permission denied) — that is good
INSERT INTO insurance.dim_region (region_code, region_name)
VALUES ('ZZ', 'ShouldFail');
```

---

## Step 6 — Configure Streamlit secrets

1. Copy `.streamlit/secrets.example.toml` → `.streamlit/secrets.toml` (if you do not already have one).
2. Set:

```toml
DATA_BACKEND = "postgres"
INDUSTRY_PACK = "insurance"

CAPGEMINI_LLM_API_KEY = "your-real-key"

[postgres]
host = "localhost"
port = 5432
database = "askdb_dev"
user = "askdb_app"
password = "THE_SAME_PASSWORD_AS_STEP_2"
schema = "insurance"
sslmode = "prefer"
connect_timeout_seconds = 10
statement_timeout_seconds = 30
max_result_rows = 1000
```

### Important

- `.streamlit/secrets.toml` must stay **out of git**.
- Keep `DATA_BACKEND = "csv_duckdb"` until Steps 2–5 succeed.
- Restart Streamlit after changing secrets.

---

## Step 7 — Start the app and check connection

```powershell
cd E:\ai_data_rag\ai_data_v2
streamlit run app.py
```

Expect in sidebar:

- **PostgreSQL → CONNECTED**
- Table count > 0
- No “Upload CSV to get started” gate

Then:

- **Data Preview** → pick a table → limited preview
- **KPI Summary** → insurance KPI cards (needs loaded data)
- **Chat** → ask a simple count/loss-ratio question

---

## Step 8 — Index CFO PowerPoint RAG docs

1. Confirm files exist under `doc/business_knowledge/insurance/`:
   - `INS-CFO-Q1-2026_Quarterly_Insurance_Results.pptx`
   - `INS-CFO-Q2-2026_Quarterly_Insurance_Results.pptx`
2. In sidebar → **Industry pack** → switch to **Insurance** (if not already).
3. **Knowledge base → INDEX ACTIVE PACK**.
4. Ask:

> What did the CFO report for Q2 loss ratio and what action was recommended?

Expect slide citations from the Q2 deck.

---

## Information to capture while executing

Write these down as you go:

| Item | Your value |
|---|---|
| PostgreSQL version | e.g. 17.5 |
| Install path | e.g. `C:\Program Files\PostgreSQL\17` |
| Superuser password | (private) |
| `askdb_app` password | (private) |
| Port | 5432 |
| Database | `askdb_dev` |
| Schema | `insurance` |
| Claim row count after load | |
| Policy-month row count | |
| First successful Chat question | |
| Any errors / screenshots | |

---

## Common errors

| Error | Fix |
|---|---|
| `password authentication failed` | Wrong password in secrets vs role |
| `connection refused` | Service not running / wrong port |
| `permission denied for schema insurance` | Re-run grants in `001_...sql` as `postgres` |
| `relation does not exist` | Connected to wrong DB, or Step 3 not run |
| App still asks for CSV upload | `DATA_BACKEND` still `csv_duckdb` or secrets not loaded |
| KPI tab empty | Tables empty — load data first |
| RAG has no citations | Index not run, or wrong industry pack |

---

## Safety rules

1. Never grant `askdb_app` INSERT/UPDATE/DELETE/CREATE.
2. Never commit passwords.
3. Never load 1M rows into Streamlit/Pandas — keep execution in PostgreSQL.
4. Numbers come from SQL; CFO PPTX is **synthetic demo** commentary only.
5. Keep CSV/DuckDB mode available for automotive demos by switching `DATA_BACKEND` back.
