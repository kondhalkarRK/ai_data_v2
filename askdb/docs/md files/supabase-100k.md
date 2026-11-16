# Supabase hosting — 100k automotive + 100k insurance

Ask DB expects **three logical databases**. Supabase Free gives **one Postgres per project** (and only **two projects**). Put **all three schemas in one project**:

| Schema / app DB | What it holds | Seed size |
|---|---|---|
| `public` (Alembic app) | Users, history, saved questions | tiny |
| `automotive` | Sales warehouse | **100,000** `fact_sales` rows |
| `insurance` | Claims warehouse | **100,000** `fact_claims` (+ smaller dims/monthly) |

That is well under the **500 MB Free** database cap.

Vercel still hosts **only the Next.js UI**. FastAPI must run somewhere that can reach Supabase (your PC, Railway, etc.).

## 1. Create the project

1. Sign up at [supabase.com](https://supabase.com).
2. **New project** → region close to you → save the **database password**.
3. **Project Settings → Database → Connection string → URI**.
4. Use the **direct** connection (**port 5432**, host `db.<ref>.supabase.co`), **not** the pooler (6543), for migrate and COPY seed.

Example (encode special characters in the password):

```text
postgresql+psycopg://postgres:YOUR_PASSWORD@db.xxxxx.supabase.co:5432/postgres?sslmode=require
```

## 2. Point Ask DB at that one database

# In `askdb/.env` set **the same URI** for app, reader, and owner (Free demo).
# Do **not** replace your local `.env`. Copy `.env.hosted.example` → `.env.hosted`.
#
# R&D on this PC:  `.\scripts\dev.ps1`           → local Postgres
# Manager demo:    `.\scripts\dev.ps1 -Profile hosted` → Supabase


```env
APP_DATABASE_URL=postgresql+psycopg://postgres:...@db.xxxxx.supabase.co:5432/postgres?sslmode=require
AUTOMOTIVE_DATABASE_URL=postgresql+psycopg://postgres:...@db.xxxxx.supabase.co:5432/postgres?sslmode=require
INSURANCE_DATABASE_URL=postgresql+psycopg://postgres:...@db.xxxxx.supabase.co:5432/postgres?sslmode=require
AUTOMOTIVE_MIGRATE_DATABASE_URL=postgresql+psycopg://postgres:...@db.xxxxx.supabase.co:5432/postgres?sslmode=require
INSURANCE_MIGRATE_DATABASE_URL=postgresql+psycopg://postgres:...@db.xxxxx.supabase.co:5432/postgres?sslmode=require
AUTH_BYPASS=false
```

## 3. Roles, migrate, seed 100k + 100k

From `askdb/` (Python venv with API deps, `psql` on PATH):

```powershell
# Optional: create askdb_app / askdb_reader / askdb_owner
psql "$env:SUPABASE_DIRECT_URI" -f database/supabase/00_bootstrap.sql

python scripts/migrate.py app upgrade head
python scripts/migrate.py automotive upgrade head
python scripts/migrate.py insurance upgrade head

python scripts/seed_automotive.py --rows 100000 --replace
python scripts/seed_insurance.py --claims 100000 --policies 20000 --monthly-sample 8000 --replace

python scripts/create_admin.py --email admin@example.com --name "Admin"
```

Or run `.\scripts\seed_supabase_100k.ps1` after setting `SUPABASE_DIRECT_URI`.

## 4. Confirm size

In the Supabase SQL editor:

```sql
SELECT
  (SELECT COUNT(*) FROM automotive.fact_sales) AS auto_sales,
  (SELECT COUNT(*) FROM insurance.fact_claims) AS ins_claims,
  pg_size_pretty(pg_database_size(current_database())) AS db_size;
```

Expect ~100,000 / ~100,000 and a database size **far below 500 MB**.

## 5. Run the app

API on this machine (or a host) with that `.env`. Web: local or Vercel with `API_REWRITE_TARGET` / `NEXT_PUBLIC_API_BASE_URL` pointing at the API.

Do not use `AUTH_BYPASS` in production. Free projects **pause after a week idle** — open the Supabase dashboard to wake them.
