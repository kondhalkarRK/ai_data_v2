# Applying Phase 4–6 upgrades on an existing local setup

If you already followed [`08-end-to-end-setup.md`](08-end-to-end-setup.md), run these
commands to pick up forecast/MVs, Scenario Mode, richer chat, and RAG upgrades.

## 1. Pull / sync code, reinstall API extras (optional RAG parsers)

```powershell
cd E:\ai_data_rag\ai_data_v2\askdb\apps\api
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev,rag]"
```

`[rag]` adds `pypdf`, `python-docx`, `pymongo`, `qdrant-client`. Without it, filesystem RAG
and text uploads still work; PDF/DOCX need the extras.

## 2. Apply analytics migrations (forecast + MVs)

```powershell
cd E:\ai_data_rag\ai_data_v2\askdb
python scripts\migrate.py automotive upgrade head
python scripts\migrate.py insurance upgrade head
```

## 3. Re-seed (includes forecast baseline + MV refresh)

```powershell
python scripts\seed_automotive.py --rows 10000 --replace
python scripts\seed_insurance.py --claims 10000 --replace
```

## 4. Restart API + web

```powershell
.\scripts\dev.ps1
```

## What you should see

| Area | Expectation |
| --- | --- |
| Dashboard | Period % deltas, click breakdown to filter, Export CSV, presenter hides sidebar |
| Scenario | Panel appears after forecast seed; Actual KPIs unchanged |
| Chat | Cancel, Retry, follow-up chips, clarification, surprise me, OOB, what-if |
| Knowledge | PDF/DOCX (with `[rag]`), delete, reindex, optional web retrieval checkbox |

## Still environment-blocked

- Live 1M golden NLQ SQL/number identity vs legacy needs warehouse + optional `LLM_API_KEY`
- Mongo/Qdrant hybrid storage activates when those services are up and URIs are set in `.env`
