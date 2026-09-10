# NQL Insight

Enterprise natural-language analytics over PostgreSQL with a governed semantic layer.
Numbers come from SQL; documents add context and are always cited.

This is a standalone application. It shares no files, imports or configuration with the
previous Streamlit app in the parent directory and can be committed, installed, run and
deployed on its own.

## What is built today

Phases 1–7 are scaffolded and largely implemented: foundation, semantic core, analytics
databases with preview/DQ, executive dashboard KPIs, SSE chat, knowledge retrieval, and
hardening checklists. Live warehouse/LLM verification still depends on local Postgres and
optional `LLM_API_KEY`.

| Area | State |
| --- | --- |
| Authentication | Email and password, Argon2id, JWT access token plus rotating refresh family, three roles, rate limiting, audit trail |
| API foundation | Settings, structured logging with redaction, request context, security headers, `/health` and `/ready` |
| Database | App + automotive + insurance Alembic; 1M seed scripts; activity tables for chat/history |
| Frontend | Shell, Data Preview/Quality, Dashboard, Chat, Knowledge, History, Saved Questions, Cost |
| Semantic Core | Typed packs, ontology browser |
| KPIs | Insurance + automotive SQL summaries, series, breakdowns; Scenario Mode gated |
| Chat | SSE `/chat/ask`, templates without LLM, optional LLM SQL, trust score |
| RAG | Upload/chunk/hash-embed/search with citations (Qdrant/Mongo optional later) |
| Hardening | `docs/06-security-checklist.md`, `docs/07-parity-checklist.md` |

See [`docs/03-phased-plan.md`](docs/03-phased-plan.md), [`docs/06-security-checklist.md`](docs/06-security-checklist.md) and [`docs/07-parity-checklist.md`](docs/07-parity-checklist.md).

## Layout

```
askdb/
├── apps/
│   ├── api/            FastAPI service (Python 3.12, Poetry)
│   └── web/            Next.js App Router frontend
├── packages/
│   └── shared-types/   TypeScript mirror of the Pydantic contracts
├── database/app/       Cluster bootstrap SQL
├── docs/               Migration inventory, architecture, phased plan
├── scripts/            Admin CLI and local startup
├── docker-compose.yml  Postgres, MongoDB, Qdrant and the API
└── vercel.json         Frontend deployment
```

## Requirements

- Node.js 20.11 or later
- Python 3.12
- Docker, or a local PostgreSQL 16

## Running locally

**1. Configure.**

```bash
cp .env.example .env
```

Set `JWT_SECRET_KEY` to at least 32 random characters. The API refuses to start with a
short or default key.

```bash
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

**2. Start the data stores.**

```bash
docker compose up -d postgres mongo qdrant
```

MongoDB and Qdrant are only needed from Phase 6; `/ready` reports them as
`not_configured` until then rather than pretending they are healthy, so
`docker compose up -d postgres` alone is enough for Phases 1 to 5.

**3. Install the API and migrate.**

```bash
cd apps/api
python -m venv .venv
.venv/Scripts/activate          # Windows;  source .venv/bin/activate elsewhere
pip install -e ".[dev]"
alembic upgrade head
python ../../scripts/migrate.py automotive upgrade head
python ../../scripts/migrate.py insurance upgrade head
```

The project uses a standard PEP 621 `pyproject.toml`, so pip is enough; Poetry is not
required. Add `.[rag]` from Phase 6 onward and `.[analytics]` if you want the optional
pandas and DuckDB extras.

Seed the automotive star schema (1M sales rows by default; takes a few minutes):

```bash
# from askdb/, with apps/api/.venv activated
python scripts/seed_automotive.py --rows 1000000 --replace
python scripts/smoke_automotive_plans.py
python scripts/migrate.py insurance upgrade head
python scripts/seed_insurance.py --claims 1000000 --replace
python scripts/smoke_insurance_plans.py
```

**4. Create the first administrator.** There is no self-service sign-up and no default
account, so this step is required before anyone can sign in.

```bash
python ../../scripts/create_admin.py --email you@company.com --full-name "Your Name"
```

The password is read from a hidden prompt, or from `ADMIN_PASSWORD` for unattended use.

**5. Run both services.**

```bash
# from askdb/
./scripts/dev.ps1        # Windows
./scripts/dev.sh         # macOS and Linux
```

Or separately:

```bash
cd apps/api && .venv/Scripts/uvicorn app.main:app --reload --port 8000
npm run dev              # from askdb/, serves the frontend on :3000
```

The API is on <http://localhost:8000> with OpenAPI at `/docs`; the frontend is on
<http://localhost:3000>.

## Checks

```bash
npm run typecheck                          # frontend and shared types
npm run lint --workspace apps/web
npm run test --workspace apps/web          # vitest
npm run test:e2e --workspace apps/web      # playwright, needs both services running

cd apps/api                                # with .venv activated
ruff check .
mypy app                                   # strict
pytest
```

All of the above are currently clean: 55 backend tests, 18 frontend unit tests, `mypy
--strict` across 44 modules, and a production `next build`.

The Playwright suite skips itself unless `E2E_EMAIL` and `E2E_PASSWORD` name a seeded
account, so a fresh checkout does not fail on missing fixtures.

## Deployment

The frontend deploys to Vercel from `vercel.json`, with `apps/web` as the project root.
Set `NEXT_PUBLIC_API_BASE_URL` to the public API origin.

The backend is a container built from `apps/api/Dockerfile`. In production set
`COOKIE_SECURE=true`, list the exact frontend origin in `CORS_ALLOWED_ORIGINS`, and set
`TRUSTED_HOSTS`; wildcards are rejected outside development.

## Outstanding inputs

Two things are needed from you before the remaining phases can be finished as specified.

**The logo.** Not supplied, so the brand mark is currently a plain typographic wordmark.
The animation described in the specification is built and waiting for the asset — see
[`apps/web/public/brand/README.md`](apps/web/public/brand/README.md) for the file list and
the one-line switch that activates it. Per the specification the mark has not been
invented or redrawn.

**Automotive schema.** Implemented per
[`docs/05-automotive-schema-proposal.md`](docs/05-automotive-schema-proposal.md): schema
`automotive`, required `dealer_id` on `fact_sales`, first-of-month targets, India-focused
makes, and a deterministic **1M**-row seed
(`scripts/seed_automotive.py`). Scale to 2M later with `--rows`.

The RAISE screenshots referenced by the specification were also not provided. The shell
follows the layout described in the text: fixed left sidebar with grouped sections,
persistent top bar, and three main workspace tabs.

## Documents

- [**End-to-end local setup**](docs/08-end-to-end-setup.md) — install Postgres, create DBs/schemas, seed, connect frontend, run and test (no Docker required)
- [Migration inventory](docs/01-migration-inventory.md) — every legacy file marked keep, adapt or retire
- [Architecture](docs/02-architecture.md) — boundaries, request context, industry switching, security
- [Phased plan](docs/03-phased-plan.md) — scope and acceptance criteria per phase
- [API reference](docs/04-api.md) — conventions, auth model, error shape, current endpoints
- [Automotive schema](docs/05-automotive-schema-proposal.md) — approved DDL, indexes, 1M seed
