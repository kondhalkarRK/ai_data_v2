# Traditional RAG (Ask Me Knowledge Hub)

## Feature flag

| `ASK_ME_RAG_ENABLED` | Behaviour |
|---|---|
| `false` (default) | Legacy filesystem Knowledge Hub read/search + hash chat retrieval. Upload / reindex / delete return **403** `rag_disabled`. |
| `true` | PostgreSQL metadata, private original-file storage, durable ingest jobs, real embeddings, Qdrant similarity retrieval, grounded chat answers. Hash retrieval is **disabled**. |

Profile capability: `capabilities.ragEnabled` from `/api/v1/auth/me`.

## Architecture

1. **Upload (Admin)** → validate file → write immutable blob → `knowledge_documents` (`PENDING`) → enqueue `knowledge_ingest_jobs`
2. **Worker** claims job (`FOR UPDATE SKIP LOCKED`) → extract → chunk → embed → Qdrant upsert → verify point count → `INDEXED` + `is_active`
3. **Replace** creates a new version; old stays searchable until new is verified; then atomic supersede + async vector cleanup
4. **Delete** soft-deletes immediately (`DELETED`, inactive) so retrieval excludes it before async Qdrant cleanup
5. **Chat / Hub search** use one ACL-aware path (`search_authorized`); admin management privilege does **not** bypass chat ACL

## Database

Migration: `apps/api/migrations/versions/0011_knowledge_documents.py`

Tables: `knowledge_documents`, `knowledge_document_chunks`, `knowledge_document_acl`, `knowledge_ingest_jobs`

```bash
cd apps/api
alembic upgrade head
```

## Embeddings & Qdrant

- Provider: `openai_compatible`. Local Hugging Face/SentenceTransformer loading
  was removed. Set `RAG_EMBEDDING_MODEL` to an embedding model supported by your
  configured API, plus `RAG_EMBEDDING_BASE_URL` and `RAG_EMBEDDING_API_KEY`.
  Existing LLM URL/key are fallbacks, but that service must support `/embeddings`.
  A chat-only model cannot provide document embeddings. If document RAG is not
  needed, set `ASK_ME_RAG_ENABLED=false`; AskBI does not require document RAG.
  Changing embedding models requires reindexing documents into the compatible
  model/dimension collection; old vectors are not automatically converted.
- Provider, model id and dimension are recorded per document / collection
- Collection name includes model + dimension (`askme_rag_{industry}_{model}_d{dim}`)
- Never mix incompatible dimensions in one collection; never truncate vectors

### No Docker / office laptop

You do **not** need Docker Desktop. Use embedded Qdrant via the Python client:

```env
RAG_QDRANT_MODE=local
RAG_QDRANT_PATH=
```

Vectors persist under `apps/api/data/qdrant_local` (or the path you set).  
Only one API process should use that folder. For production scale, switch to `RAG_QDRANT_MODE=server` with a real Qdrant service.

## Worker

- **POC:** in-process loop when `RAG_WORKER_IN_PROCESS=true` (API lifespan)
- **Production:** `python -m app.rag.worker`

## Legacy backfill

```bash
cd apps/api
python -m app.rag.backfill --industry insurance
```

Optional in development; required before production cutover if legacy docs must remain searchable.

## Formats (MVP)

PDF, DOCX, TXT, MD, HTML. CSV and PPTX are excluded.

## Troubleshooting

| Symptom | Check |
|---|---|
| 403 `rag_disabled` | `ASK_ME_RAG_ENABLED=true` and restart API |
| Stuck `PENDING` | Worker running; `/ready` Qdrant + `rag_embeddings` |
| Dimension mismatch | Inspect provider dim; use compatible collection (do not force 384) |
| Region doc invisible | User zones assigned; unresolved region fails closed |
| Unauthorized text in answer | Must not happen — report as security bug |
