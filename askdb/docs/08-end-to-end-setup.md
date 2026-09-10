# End-to-end local setup guide

Step-by-step instructions to create the databases, apply schemas, seed sample data,
connect the FastAPI backend, and run the Next.js frontend so you can sign in and test
NQL Insight on your machine.

**Audience.** Windows (PowerShell). macOS/Linux notes appear where commands differ.

**Docker Desktop is optional.** This guide uses a native PostgreSQL 16 install. If you
prefer Docker, see [Option B](#option-b--postgres-with-docker-compose) after step 1.

Related files:

| File | Role |
| --- | --- |
| [`../.env.example`](../.env.example) | Copy to `.env` at repo root |
| [`../database/app/00_bootstrap.sql`](../database/app/00_bootstrap.sql) | Creates DBs + roles |
| [`../scripts/migrate.py`](../scripts/migrate.py) | Alembic wrapper (app / automotive / insurance) |
| [`../scripts/seed_automotive.py`](../scripts/seed_automotive.py) | Automotive fact seed |
| [`../scripts/seed_insurance.py`](../scripts/seed_insurance.py) | Insurance claims seed |
| [`../scripts/create_admin.py`](../scripts/create_admin.py) | First login account |
| [`../scripts/dev.ps1`](../scripts/dev.ps1) | Start API + web together |
| [`05-automotive-schema-proposal.md`](05-automotive-schema-proposal.md) | Automotive DDL decisions |

---

## Architecture (what you are wiring)

```
Browser  →  Next.js (:3000)  →  FastAPI (:8000)  →  PostgreSQL (:5432)
                                      │
              ┌───────────────────────┼───────────────────────┐
              ▼                       ▼                       ▼
         askdb_app            askdb_automotive         askdb_insurance
      (auth, history)         (analytics + seed)       (analytics + seed)
```

- **Vercel later** hosts only the frontend. It cannot use Postgres on your laptop.
  For local testing, keep everything on `localhost` as below.
- **MongoDB / Qdrant** are optional for a first test. Skip them until you need full RAG.

---

## 0. Checklist of software to install

| # | Software | Version | Required? | Download |
| --- | --- | --- | --- | --- |
| 1 | Node.js | 20.11+ | Yes | https://nodejs.org/ |
| 2 | Python | 3.12.x | Yes | https://www.python.org/downloads/ (tick **Add to PATH**) |
| 3 | PostgreSQL | 16 | Yes (if no Docker) | https://www.postgresql.org/download/windows/ |
| 4 | Docker Desktop | latest | No | Only if you skip native Postgres |
| 5 | Git | any | Optional | — |

During the PostgreSQL installer:

- Remember the **`postgres` superuser password**.
- Keep port **5432**.
- Ensure **Command Line Tools** / `psql` are installed.

Verify in a **new** PowerShell window:

```powershell
node -v
python --version
psql --version
```

If `psql` is not found, add to PATH (adjust version folder if needed):

`C:\Program Files\PostgreSQL\16\bin`

---

## 1. Open the project

```powershell
cd E:\ai_data_rag\ai_data_v2\askdb
```

All later paths are relative to this folder (`askdb/`).

---

## 2. Create `.env` (API + databases)

```powershell
Copy-Item .env.example .env
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

Edit `.env`:

1. Set `JWT_SECRET_KEY` to the printed string (must be **≥ 32** characters).
2. For local native Postgres with the bootstrap defaults, use:

```env
APP_DATABASE_URL=postgresql+psycopg://askdb_app:askdb_app@localhost:5432/askdb_app
AUTOMOTIVE_DATABASE_URL=postgresql+psycopg://askdb_reader:askdb_reader@localhost:5432/askdb_automotive
INSURANCE_DATABASE_URL=postgresql+psycopg://askdb_reader:askdb_reader@localhost:5432/askdb_insurance
AUTOMOTIVE_MIGRATE_DATABASE_URL=postgresql+psycopg://askdb_owner:askdb_owner@localhost:5432/askdb_automotive
INSURANCE_MIGRATE_DATABASE_URL=postgresql+psycopg://askdb_owner:askdb_owner@localhost:5432/askdb_insurance

DEFAULT_INDUSTRY=insurance
CORS_ALLOWED_ORIGINS=http://localhost:3000
TRUSTED_HOSTS=localhost,127.0.0.1
COOKIE_SECURE=false
```

3. Leave `LLM_API_KEY` empty until you have a key (chat templates still work).
4. You can leave `MONGODB_URI` / `QDRANT_URL` as-is; `/ready` may report them as not configured.

**Do not commit `.env`.**

---

## 3. Create frontend env

```powershell
@"
NEXT_PUBLIC_API_BASE_URL=http://localhost:8000
NEXT_PUBLIC_APP_NAME=NQL Insight
"@ | Set-Content -Path apps\web\.env.local -Encoding utf8
```

This is how the browser finds the API. Wrong URL = login/API calls fail even if Postgres is fine.

---

## 4. Create databases and roles (Postgres)

### Option A — Native PostgreSQL (no Docker)

```powershell
cd E:\ai_data_rag\ai_data_v2\askdb
$env:PGPASSWORD = "YOUR_POSTGRES_SUPERUSER_PASSWORD"
psql -U postgres -h localhost -f database\app\00_bootstrap.sql
```

What this creates:

| Object | Purpose |
| --- | --- |
| Role `askdb_app` | Owns / uses `askdb_app` (auth, activity) |
| Role `askdb_owner` | Migrations + seeds on analytics DBs |
| Role `askdb_reader` | SELECT-only at runtime |
| DB `askdb_app` | Application database |
| DB `askdb_automotive` | Automotive warehouse |
| DB `askdb_insurance` | Insurance warehouse |

Dev passwords in `00_bootstrap.sql` match the usernames (`askdb_app`, `askdb_owner`, `askdb_reader`). Change them for any shared or production environment.

Quick check:

```powershell
psql -U postgres -h localhost -c "\l" | Select-String askdb
psql -U postgres -h localhost -c "\du" | Select-String askdb
```

### Option B — Postgres with Docker Compose

Only if Docker Desktop is installed:

```powershell
docker compose up -d postgres
```

Compose mounts `database/app/00_bootstrap.sql` on first empty data volume. Then continue from step 5. You still need the same `.env` URLs pointing at `localhost:5432` (port is published on the host).

---

## 5. Install the API (Python)

```powershell
cd E:\ai_data_rag\ai_data_v2\askdb\apps\api
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -U pip
pip install -e ".[dev]"
```

macOS/Linux: `source .venv/bin/activate` instead of `Activate.ps1`.

If PowerShell blocks scripts:

```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```

---

## 6. Apply schemas (migrations)

With `apps/api` venv **activated**, from `askdb/`:

```powershell
cd E:\ai_data_rag\ai_data_v2\askdb

# App DB (users, sessions, history, saved questions, …)
python scripts\migrate.py app upgrade head

# Analytics schemas
python scripts\migrate.py automotive upgrade head
python scripts\migrate.py insurance upgrade head
```

Notes:

- Always use `scripts/migrate.py` for automotive/insurance (plain `alembic -x` is not enough for version locations).
- App migrations can also be run as `cd apps/api; alembic upgrade head` — the wrapper above is consistent for all three.

Verify tables exist (example):

```powershell
$env:PGPASSWORD = "askdb_owner"
psql -U askdb_owner -h localhost -d askdb_automotive -c "\dn"
psql -U askdb_owner -h localhost -d askdb_automotive -c "\dt automotive.*"
```

---

## 7. Seed analytics data

Start **small** for a first successful test, then scale up.

```powershell
cd E:\ai_data_rag\ai_data_v2\askdb
# venv still activated

python scripts\seed_automotive.py --rows 10000 --replace
python scripts\seed_insurance.py --claims 10000 --replace
```

Full volume (slower; several minutes+):

```powershell
python scripts\seed_automotive.py --rows 1000000 --replace
python scripts\seed_insurance.py --claims 1000000 --replace
```

Optional smoke checks:

```powershell
python scripts\smoke_automotive_plans.py
python scripts\smoke_insurance_plans.py
```

---

## 8. Create the first admin user

There is **no** self-service sign-up and **no** default password.

```powershell
cd E:\ai_data_rag\ai_data_v2\askdb
python scripts\create_admin.py --email you@company.com --name "Your Name" --generate
```

- Save the printed password.
- Or omit `--generate` and enter a password at the prompts.
- Unattended: set env `NQL_ADMIN_PASSWORD` then run without `--generate`.

---

## 9. Install the frontend

```powershell
cd E:\ai_data_rag\ai_data_v2\askdb
npm install
```

---

## 10. Run API + frontend

### One command (Windows)

```powershell
cd E:\ai_data_rag\ai_data_v2\askdb
.\scripts\dev.ps1
```

### Two terminals

**Terminal 1 — API**

```powershell
cd E:\ai_data_rag\ai_data_v2\askdb\apps\api
.\.venv\Scripts\Activate.ps1
python -m uvicorn app.main:app --reload --port 8000
```

**Terminal 2 — Web**

```powershell
cd E:\ai_data_rag\ai_data_v2\askdb
npm run dev
```

Open:

| URL | What |
| --- | --- |
| http://localhost:3000 | Application UI |
| http://localhost:8000/docs | OpenAPI / Swagger |
| http://localhost:8000/health | Liveness |
| http://localhost:8000/ready | Readiness (DB connectivity) |

Sign in at `/login` with the admin email/password from step 8.

---

## 11. What to click after login (smoke path)

1. Confirm shell loads (sidebar + top bar) and theme toggle works.
2. Switch industry (insurance ↔ automotive) if available in the UI.
3. **Data Preview** — tables load with rows.
4. **Data Quality** — scores/rules appear for seeded tables.
5. **Dashboard** — KPIs render (empty or error usually means seed/migration skipped).
6. **Chat** — template/ask flow; full LLM SQL needs `LLM_API_KEY` in `.env`.
7. **Knowledge** — basic local path may work without Mongo/Qdrant; advanced RAG needs those services later.

---

## 12. Connecting the pieces (mental model)

| Layer | Config | Must match |
| --- | --- | --- |
| Postgres | `00_bootstrap.sql` roles/DBs | Passwords in `.env` URLs |
| Alembic / seeds | `*_MIGRATE_DATABASE_URL` (`askdb_owner`) | Owner can DDL + insert |
| API runtime queries | `AUTOMOTIVE_` / `INSURANCE_DATABASE_URL` (`askdb_reader`) | Reader can SELECT |
| Auth / history | `APP_DATABASE_URL` (`askdb_app`) | Admin user created here |
| Browser → API | `apps/web/.env.local` → `NEXT_PUBLIC_API_BASE_URL` | `http://localhost:8000` |
| API → browser CORS | `CORS_ALLOWED_ORIGINS` | `http://localhost:3000` |

If the UI loads but login fails: check API logs, `/ready`, and `APP_DATABASE_URL`.  
If login works but dashboards are empty: re-run seeds and industry switch.

---

## 13. Day-2 commands (cheat sheet)

```powershell
cd E:\ai_data_rag\ai_data_v2\askdb
.\apps\api\.venv\Scripts\Activate.ps1

# Re-apply migrations after pulling new code
python scripts\migrate.py app upgrade head
python scripts\migrate.py automotive upgrade head
python scripts\migrate.py insurance upgrade head

# Re-seed
python scripts\seed_automotive.py --rows 10000 --replace
python scripts\seed_insurance.py --claims 10000 --replace

# New user
python scripts\create_admin.py --email other@company.com --name "Other" --generate

# Start
.\scripts\dev.ps1
```

---

## 14. Optional later

### LLM (richer chat)

Set in `.env`:

```env
LLM_API_KEY=your-key
LLM_BASE_URL=...
LLM_DEFAULT_MODEL=...
```

Restart the API.

### MongoDB + Qdrant (full RAG)

Install or run via `docker compose up -d mongo qdrant`, keep URIs in `.env`, restart API.
Not required for login, preview, DQ, or KPI smoke tests.

### Deploying online (not this guide)

- Frontend → Vercel (`NEXT_PUBLIC_API_BASE_URL` = public API URL).
- API → separate host (container/VM).
- Postgres → **cloud** database (Neon, Supabase, RDS, etc.).
- Local desktop Postgres **cannot** back a Vercel production site.

---

## 15. Troubleshooting

| Symptom | Likely cause | Fix |
| --- | --- | --- |
| `psql` not recognized | PATH | Add PostgreSQL `bin` to PATH; new shell |
| Bootstrap fails password | Wrong `PGPASSWORD` | Use the installer superuser password |
| API exits on start: JWT | Short/default secret | Regenerate `JWT_SECRET_KEY` (≥ 32 chars) |
| `connection refused` :5432 | Postgres not running | Start PostgreSQL Windows service |
| Migration permission error | Using reader URL for migrate | Use `*_MIGRATE_DATABASE_URL` / `askdb_owner` |
| Frontend cannot reach API | Wrong `.env.local` | `NEXT_PUBLIC_API_BASE_URL=http://localhost:8000` |
| CORS errors in browser | Origin mismatch | `CORS_ALLOWED_ORIGINS=http://localhost:3000` |
| Empty analytics UI | No seed | Run seed scripts with `--replace` |
| Chat weak / no SQL | No LLM key | Optional; set `LLM_API_KEY` |
| `dev.ps1` blocked | Execution policy | `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` |

Reset analytics data (destructive):

```powershell
python scripts\seed_automotive.py --rows 10000 --replace
python scripts\seed_insurance.py --claims 10000 --replace
```

---

## 16. Success criteria

You are done with local setup when all of the following are true:

- [ ] `psql` can list the three `askdb_*` databases
- [ ] Migrations applied for app, automotive, insurance
- [ ] Seeds completed (at least 10k rows each)
- [ ] Admin user created
- [ ] http://localhost:8000/health returns OK
- [ ] http://localhost:3000 loads and login succeeds
- [ ] Data Preview or Dashboard shows seeded numbers

---

## Order of operations (summary)

```
Install Node + Python 3.12 + PostgreSQL 16
        ↓
Copy .env + apps/web/.env.local
        ↓
Run database/app/00_bootstrap.sql
        ↓
pip install API + migrate app/automotive/insurance
        ↓
Seed (10k first) + create_admin
        ↓
npm install + scripts/dev.ps1
        ↓
Open :3000 and test
```
