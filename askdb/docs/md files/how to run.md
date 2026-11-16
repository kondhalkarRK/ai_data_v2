# Embedding configuration update — 2026-11-06

Local Hugging Face/SentenceTransformer loading has been removed. Historical
instructions below mentioning `sentence-transformers` installation or MiniLM
configuration are superseded. Use `RAG_EMBEDDING_PROVIDER=openai_compatible` with
an explicitly configured embeddings API/model, or `ASK_ME_RAG_ENABLED=false` when
document RAG is unnecessary. See `traditional-rag.md`. AskBI requires no local
embedding model. Do not disable TLS verification to work around model downloads.

Qeusion  : can guide me detailed setup for RAG, will excute below stuff but i need to run and install,
# apps/api
alembic upgrade head
# askdb/.env
ASK_ME_RAG_ENABLED=true
RAG_EMBEDDING_PROVIDER=sentence_transformers   # or openai_compatible
RAG_EMBEDDING_MODEL=all-MiniLM-L6-v2
# ensure Qdrant is up; install optional: pip install -e ".[rag]" (+ sentence-transformers if needed)

along with can you can one pdf and one other file which has some automobile studd and i can upload it on application and test if rag is running perfectly or not,  also give me set of question to test this update

Cursr reponse below
---

## 0. What you have today

| Item | Status |
|---|---|
| `askdb/.env` | Exists, but **no** `ASK_ME_RAG_ENABLED` yet |
| API venv | Present at `apps/api/.venv` |
| RAG packages (`qdrant-client`, `pypdf`, `sentence-transformers`) | **Not installed** |
| Docker | **Not in PATH** (install Docker Desktop, or run Qdrant another way) |

Sample uploads created here:

- `E:\ai_data_rag\ai_data_v2\askdb\samples\rag-test\automotive_warranty_rebate_policy.pdf`
- `E:\ai_data_rag\ai_data_v2\askdb\samples\rag-test\automotive_dealer_performance_q3.md`

---

## 1. Start Qdrant (required)

Traditional RAG needs Qdrant on `http://localhost:6333`.

### Option A — Docker Desktop (recommended)

1. Install [Docker Desktop for Windows](https://www.docker.com/products/docker-desktop/), restart PowerShell.
2. Then:

```powershell
cd E:\ai_data_rag\ai_data_v2\askdb
docker compose up -d qdrant
# optional check
curl http://localhost:6333/readyz
```

### Option B — Qdrant binary (no Docker)

1. Download a Windows build from [Qdrant releases](https://github.com/qdrant/qdrant/releases).
2. Run `qdrant.exe` (default listens on `6333`).
3. Confirm: open `http://localhost:6333/dashboard` in a browser.

Postgres must already be running (same as normal Ask Me).

---

## 2. Install Python packages

Open **PowerShell**:

```powershell
cd E:\ai_data_rag\ai_data_v2\askdb\apps\api
.\.venv\Scripts\Activate.ps1

# Core RAG extras from pyproject
pip install -e ".[rag]"

# Local embeddings model (first run downloads ~90MB)
pip install "sentence-transformers>=3,<4"
```

Verify:

```powershell
python -c "import qdrant_client, pypdf, docx, sentence_transformers; print('ok')"
```

---

## 3. Update `askdb/.env`

Edit `E:\ai_data_rag\ai_data_v2\askdb\.env`. Under the `# --- RAG ---` section, set or add:

```env
ASK_ME_RAG_ENABLED=true
RAG_EMBEDDING_PROVIDER=sentence_transformers
RAG_EMBEDDING_MODEL=all-MiniLM-L6-v2
RAG_EMBEDDING_DIMENSION=0
RAG_QDRANT_COLLECTION_PREFIX=askme_rag
RAG_WORKER_IN_PROCESS=true
RAG_WORKER_POLL_SECONDS=2
RAG_JOB_LEASE_SECONDS=120
RAG_JOB_MAX_ATTEMPTS=5
RAG_STORAGE_BACKEND=local

QDRANT_URL=http://localhost:6333
```

Notes:

- Keep `LLM_API_KEY` set if you want **grounded LLM answers** in chat. Without it, Hub search still works; chat may fall back to extractive snippets.
- Leave legacy `EMBEDDINGS_PROVIDER=hash` as-is — that is only for the **flag-off** path.

---

## 4. Run the database migration

```powershell
cd E:\ai_data_rag\ai_data_v2\askdb\apps\api
.\.venv\Scripts\Activate.ps1
alembic upgrade head
```

You should see revision `0011_knowledge_documents` applied (creates document / chunk / ACL / job tables).

---

## 5. Restart API + web

Stop any running API/web, then:

```powershell
# Terminal 1 — API
cd E:\ai_data_rag\ai_data_v2\askdb\apps\api
.\.venv\Scripts\Activate.ps1
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# Terminal 2 — Web
cd E:\ai_data_rag\ai_data_v2\askdb\apps\web
npm run dev
```

Quick health checks:

```powershell
curl http://localhost:8000/health
curl http://localhost:8000/ready
```

With RAG on, `/ready` should mention **qdrant** and **rag_embeddings** (not only “not_configured”).

---

## 6. Upload the sample files

1. Open the app (usually `http://localhost:3000`).
2. Sign in as **Admin** (or auth bypass if you already use it — still need an admin user).
3. Switch industry to **Automotive** (important — samples are automotive).
4. Go to **Knowledge Hub**.
5. Confirm upload controls are visible (`capabilities.ragEnabled` must be true).
6. Upload, in this order:
   - `automotive_warranty_rebate_policy.pdf` (collection: `policies`)
   - `automotive_dealer_performance_q3.md` (collection: `dealer_reports` or `general`)
7. Wait until each document status becomes **INDEXED** (not stuck on `PENDING` / `FAILED`). Refresh the library if needed (worker runs in-process every ~2s).

If status stays `PENDING`: Qdrant down, embeddings package missing, or API not restarted after `.env` change.

---

## 7. How to confirm RAG is really on

| Check | Expected |
|---|---|
| Hub search for `warranty settlement SLA` | Hits with citations from your PDF/MD |
| Document status | `INDEXED`, chunk count &gt; 0 |
| `/api/v1/auth/me` → `capabilities.ragEnabled` | `true` |
| Upload with flag off | Would be 403 `rag_disabled` |
| Chat question below | Answer cites document title / locator, not inventing numbers |

---

## 8. Test questions

Ask these in **Knowledge Hub search** first, then again in **AI Chat** (Automotive industry).

### From the PDF / policy content

1. What NPS must Platinum dealers maintain?
2. What is the warranty claim settlement SLA for standard mechanical claims?
3. Who must review high-severity powertrain claims before payout?
4. What is the parts return window for rejected warranty claims?

### From the dealer performance brief

5. How much did West zone SUV revenue grow year over year?
6. Which models led mid-size SUV demand?
7. What happened to North zone hatchback volume, and why?
8. What is the average selling price for mid-size SUVs now?
9. What were EV inventory days on hand in Bengaluru and Pune?
10. What should be prioritized for festive season replenishment in the West zone?

### Hybrid / “should use documents” phrasing

11. Summarize the key findings from the uploaded dealer performance report.
12. What does the policy document say about warranty settlement and NPS?
13. Why might West zone need Creta inventory before the festive season?
14. What concerns or risks are mentioned for the i20 petrol line?

### Negative control (should say evidence is missing / not found)

15. What is the exact FY2026 board-approved EV margin target for Kerala?  
   *(Not in the samples — a good RAG answer refuses to invent this.)*

---

## 9. Pass / fail checklist

**Pass if:**

- Both files reach `INDEXED`
- Search returns snippets mentioning NPS 70, 7 business days, 18%, Creta/Venue, 42 days
- Chat for Q1–Q10 stays grounded and cites the docs
- Q15 does **not** invent a Kerala FY2026 margin

**Fail if:**

- Upload 403 → flag still false or API not restarted
- Stuck `PENDING` → Qdrant / `sentence-transformers` / worker
- Search empty after INDEXED → wrong industry (use Automotive) or ACL/region issue
- Answers invent numbers → LLM path without retrieval (check citations in the SSE / UI)

---

## Quick command cheat-sheet

```powershell
cd E:\ai_data_rag\ai_data_v2\askdb
docker compose up -d qdrant

cd apps\api
.\.venv\Scripts\Activate.ps1
pip install -e ".[rag]"
pip install "sentence-transformers>=3,<4"
alembic upgrade head
uvicorn app.main:app --reload --port 8000
```

Then edit `.env` as in section 3, restart API, upload the two files from `samples\rag-test\`, and run the question list.

If you want, after you finish installs I can help verify `/ready` output and the first INDEXED document from your logs.



=======
next question i aksed

below is response from cursor

You don’t need Docker. The app now supports **embedded Qdrant** (ships inside `qdrant-client` over pip).

## Use this on your office laptop

### 1. Install packages (no Docker)

```powershell
cd E:\ai_data_rag\ai_data_v2\askdb\apps\api
.\.venv\Scripts\Activate.ps1
pip install -e ".[rag]"
pip install "sentence-transformers>=3,<4"
```

### 2. Put this in `askdb/.env`

```env
ASK_ME_RAG_ENABLED=true
RAG_EMBEDDING_PROVIDER=sentence_transformers
RAG_EMBEDDING_MODEL=all-MiniLM-L6-v2
RAG_EMBEDDING_DIMENSION=0

# IMPORTANT — no Docker / no Qdrant server
RAG_QDRANT_MODE=local
RAG_QDRANT_PATH=

RAG_WORKER_IN_PROCESS=true
```

Empty `RAG_QDRANT_PATH` stores vectors under:

`apps/api/data/qdrant_local`

### 3. Migrate + restart API

```powershell
cd E:\ai_data_rag\ai_data_v2\askdb\apps\api
.\.venv\Scripts\Activate.ps1
alembic upgrade head
uvicorn app.main:app --reload --port 8000
```

Check:

```powershell
curl http://localhost:8000/ready
```

You want qdrant detail like `mode=local`.

### 4. Upload your samples + test

Same as before — use the files in `samples\rag-test\` with industry **Automotive**.

---

## What the modes mean

| `RAG_QDRANT_MODE` | Needs Docker? | Persistence | Best for |
|---|---|---|---|
| **`local`** | No | Disk folder | Your office laptop / POC |
| `memory` | No | Lost on restart | Quick throwaway tests |
| `server` | Yes (or a remote Qdrant) | Server storage | Shared / production |

---

## Other options (usually harder on locked laptops)

1. **Qdrant Cloud** (hosted) — needs outbound HTTPS + API key; set `RAG_QDRANT_MODE=server` and `QDRANT_URL` / `QDRANT_API_KEY`.
2. **Portable Qdrant `.exe`** — only if IT allows downloading binaries (still no Docker).
3. **IT-approved Docker** — often blocked, which is your case.

For you: stick with **`RAG_QDRANT_MODE=local`**.

**Caveat:** local mode is for a single API process (fine for your POC). Don’t run two uvicorn workers against the same folder.
