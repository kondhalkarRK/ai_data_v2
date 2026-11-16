# Runbook: Supabase project `dlrvzgweudgfpwizsegw` → Vercel

Project dashboard: https://supabase.com/dashboard/project/dlrvzgweudgfpwizsegw  
API URL (not used by Ask DB): https://dlrvzgweudgfpwizsegw.supabase.co  

Ask DB talks to **Postgres**, not the Supabase JS/REST client.

| Who | Database |
|---|---|
| You, daily | Local Postgres via `askdb/.env` → `.\scripts\dev.ps1` |
| Manager demo / Vercel | This Supabase project via `askdb/.env.hosted` |

Never paste the database password into Git. URL-encode it if it contains `@`, `#`, `%`, etc.

---

## Step 1 — Copy the database password and URI

1. Open **Project Settings → Database**.
2. Find **Database password** (the one you set when creating the project). Reset it if you forgot.
3. **Connection string → URI → Direct connection** (session, **port 5432**).  
   Host should look like: `db.dlrvzgweudgfpwizsegw.supabase.co`
4. **Database → Network / bans**: for a first load from your PC, allow your IP (or temporarily `0.0.0.0/0` if connect times out).

Direct URI shape:

```text
postgresql://postgres:YOUR_URL_ENCODED_PASSWORD@db.dlrvzgweudgfpwizsegw.supabase.co:5432/postgres?sslmode=require
```

Do **not** use port **6543** (pooler) for migrate or seed (`COPY`).

---

## Step 2 — Local file for hosted DB only

From `askdb/`:

```powershell
cd E:\ai_data_rag\ai_data_v2\askdb
Copy-Item .env.hosted.example .env.hosted
notepad .env.hosted
```

Replace `PASSWORD` and `PROJECT` so every `*_DATABASE_URL` is:

```text
postgresql+psycopg://postgres:YOUR_URL_ENCODED_PASSWORD@db.dlrvzgweudgfpwizsegw.supabase.co:5432/postgres?sslmode=require
```

Leave `askdb/.env` on **localhost**. That file is your R&D database.

---

## Step 3 — Create schemas and write 100k + 100k

```powershell
cd E:\ai_data_rag\ai_data_v2\askdb
$env:SUPABASE_DIRECT_URI = "postgresql://postgres:YOUR_URL_ENCODED_PASSWORD@db.dlrvzgweudgfpwizsegw.supabase.co:5432/postgres?sslmode=require"
.\scripts\seed_supabase_100k.ps1
python scripts/create_admin.py --email admin@example.com --name "Demo Admin"
```

`create_admin.py` uses `APP_DATABASE_URL`. For this run:

```powershell
$env:ASKDB_ENV_FILE = (Resolve-Path .env.hosted)
python scripts/create_admin.py --email admin@example.com --name "Demo Admin"
```

(or set `APP_DATABASE_URL` to the same Supabase URI in the session).

In the Supabase **SQL Editor** confirm:

```sql
SELECT
  (SELECT COUNT(*) FROM automotive.fact_sales) AS auto_sales,
  (SELECT COUNT(*) FROM insurance.fact_claims) AS ins_claims,
  pg_size_pretty(pg_database_size(current_database())) AS db_size;
```

Expect ~100000 / ~100000.

---

## Step 4 — Prove the API on your PC uses Supabase (optional)

```powershell
.\scripts\dev.ps1 -Profile hosted
```

Logs should show `hosted supabase (db.dlrvzgweudgfpwizsegw.supabase.co)`, not `local (localhost)`.

Ctrl+C when done. Next local day: `.\scripts\dev.ps1` again (local Postgres).

---

## Step 5 — Host the API (Vercel does not run FastAPI)

Pick one:

- **Railway / Render / Fly** Docker of `apps/api` (always-on showcase), or  
- **Cloudflare Tunnel** to your PC for a short demo.

API environment **secrets** (same values as `.env.hosted`, plus):

| Secret | Value |
|---|---|
| `ENVIRONMENT` | `production` |
| `APP_DATABASE_URL` | Supabase URI (`postgresql+psycopg://...sslmode=require`) |
| `AUTOMOTIVE_DATABASE_URL` | same |
| `INSURANCE_DATABASE_URL` | same |
| `AUTOMOTIVE_MIGRATE_DATABASE_URL` | same (or omit if you never migrate from the cloud API) |
| `INSURANCE_MIGRATE_DATABASE_URL` | same |
| `JWT_SECRET_KEY` | new 64-char random string (not the local one) |
| `AUTH_BYPASS` | `false` |
| `COOKIE_SECURE` | `true` |
| `COOKIE_SAMESITE` | `none` if web and API are different sites; else `lax` |
| `COOKIE_DOMAIN` | your API host or leave empty per cookie rules |
| `CORS_ALLOWED_ORIGINS` | `https://YOUR-APP.vercel.app` (and custom domain) |
| `TRUSTED_HOSTS` | API hostname |
| `LLM_API_KEY` | your LLM key |
| `LLM_BASE_URL` / `LLM_DEFAULT_MODEL` | as today |

Public API URL example: `https://askdb-api.up.railway.app`

---

## Step 6 — Vercel (frontend only) + secrets

1. Import the Git repo. **Root directory:** `askdb/apps/web` (or the monorepo setting that builds that app).
2. **Settings → Environment Variables** (Production + Preview):

| Name | Value | Secret? |
|---|---|---|
| `API_REWRITE_TARGET` | `https://YOUR-API-HOST` (no trailing slash) | not a password, but treat as prod config |
| `NEXT_PUBLIC_API_BASE_URL` | same API origin, **or leave empty** if rewrites handle `/api` | public in the browser if set |
| `NEXT_PUBLIC_APP_NAME` | `Ask DB` | no |
| `NEXT_PUBLIC_AUTH_BYPASS` | `false` | must be false |

Do **not** put the Supabase database password on Vercel. The browser never connects to Postgres.

3. Deploy. Open `https://YOUR-APP.vercel.app`, sign in with the admin you created on Supabase.

---

## Step 7 — Smoke check

- Vercel site loads.  
- Login works.  
- Industry switch: automotive and insurance both return KPIs.  
- Supabase **Table Editor** still shows ~100k sales / ~100k claims.

---

## If connect fails from Windows

- Password URL-encoded (`@` → `%40`).  
- Direct host `db.dlrvzgweudgfpwizsegw.supabase.co` port **5432**.  
- IPv6 issues: enable Supabase **IPv4 add-on** or use the **session pooler** only for the running API, never for `seed_supabase_100k.ps1`.  
- Dashboard **Database → Network** not blocking you.
