# AskMe Chroma RAG and AI Chat design

Date: 2026-11-15. Proposal for review, not implementation. This supersedes the backend preference in RAG_PORTABLE_UPGRADE_PLAN.md for the Chroma option; its source-review findings remain applicable.

## 1. Decision and boundaries

Proposed stack: existing FastAPI + PostgreSQL application metadata/jobs + Chroma PersistentClient for dense vectors + PostgreSQL native full-text search for lexical candidates + approved HTTP embedding API + existing governed LLM for narration. No additional SQLite vector database, Qdrant server, agents, LangChain or LlamaIndex.

Chroma runs inside the backend process with a durable local directory; the Next.js frontend only talks to authenticated FastAPI routes. Start with one API worker and its existing in-process ingestion worker. Embedded Chroma is not safe for concurrent writers in different processes sharing the same path. A standalone ingestion process must not share that embedded path with a writing API process. Future scale-out requires a separately owned Chroma server or replacement vector backend.

Chroma is one component of RAG, not the parser, embedding model, reasoning model, permission system or full document-management system. Persisted vectors do not mean all answers work offline: new semantic queries need an embedding API; generated answers need the LLM API.

### Correction to earlier advice: no Hugging Face models vs no packages

Explicit embedding_function=None plus supplied embeddings avoids Chroma's default model generation/download behavior. It does not remove installed transitive dependencies. Upstream Chroma declares onnxruntime and tokenizers; upstream tokenizers declares huggingface_hub. Inspect the exact pinned release's fully resolved Windows dependency report before selecting a package version.

If 'no Hugging Face modules' literally forbids those installed packages, standard embedded chromadb may not satisfy the requirement. Do not bypass dependencies with pip --no-deps or promise an unsupported stripped installation. A Chroma server hosted in an approved environment plus a thin HTTP client is an alternative, but introduces the separate service the user wants to avoid. The compatibility phase must expose this tradeoff for a decision; it must not silently relax the requirement.

### Current vendor status

Official notice published 2026-10-23 says existing Chroma Cloud writes stop 2026-12-07 and reads stop 2026-12-22; open-source ChromaDB continues under Apache 2.0. Use local open-source Chroma only in this proposal. Do not build a future migration around that retiring managed service. Pin/test supported releases and retain our own index abstraction.

## 2. What stays and what changes

Keep authentication, user/admin roles, CSRF, industry selection, regional access, existing business SQL/semantic definitions, PostgreSQL document records/ACLs/jobs, original-file storage and the existing AI Chat event contract.

Replace direct Qdrant construction with a VectorIndex interface and Chroma adapter. Improve structured extraction, job reliability, retrieval and generation rather than replacing Knowledge Hub wholesale.

Source review found these concrete gaps:

- PDF extraction joins pages without markers, so current chunk locators cannot reliably preserve page numbers.
- DOCX extraction reads paragraphs only; tables and content order need explicit handling.
- Existing .doc uploads are unsupported; scanned images need OCR.
- Evidence snippets returned from KnowledgeService are limited to 400 characters, too short for many explanations.
- Modern RAG routing at one chat site still checks legacy filesystem corpus availability.
- Hybrid questions retrieve at most two snippets and merge them into existing insights rather than use a complete mixed-evidence narration contract.
- Blocking parsing, embedding HTTP and index calls occur inside async workflows.
- Early deleted/superseded-state handling can skip vector cleanup jobs; adapter delete errors can be swallowed. Fix dispatch and verified retries.
- Qdrant-specific persisted/API names need additive compatibility handling.

## 3. End-to-end architecture

UPLOAD:
Admin -> existing /documents upload -> validate/stream/store original -> PostgreSQL PENDING + job -> extract blocks -> chunk -> embedding API -> Chroma staged generation -> verify IDs/count/content checks -> activate PostgreSQL generation -> INDEXED.

CHAT:
Question + current conversation + industry/region -> route -> governed SQL and/or authorized retrieval -> evidence bundle -> bounded narrator -> reference/support validation -> existing chat response with citation cards.

STORES:
- Analytics PostgreSQL pools: authoritative measured metrics, read-only governed queries.
- Application PostgreSQL: users, access rules, document versions/chunks, job leases, active index generations, conversation history, audit and native full-text index.
- Chroma: derived vectors and minimal provenance metadata (optionally passage text if justified). Canonical evidence text is fetched from authorized PostgreSQL chunks.
- Private file directory/blob backend: original uploads and structured extraction artifacts.

Avoid putting document corpus files or Chroma directories under Next.js public assets, Git, cloud-sync folders or ephemeral frontend hosting storage. Use persistent storage on the backend host. Chroma remains rebuildable from canonical chunks/originals.

## 4. Ingestion design

### Supported formats

Release 1: text PDF, DOCX paragraphs/headings/tables, TXT/MD/HTML compatibility. Preserve PDF physical pages including empty pages. DOCX uses section/paragraph/table locators, not fabricated page numbers. Parse paragraphs and tables in document order and handle nested tables explicitly. State unsupported content such as text boxes/embedded objects rather than silently presenting extraction as complete.

Image-only PDF: detect and explain OCR requirement. Mixed PDF: show partial extraction warning listing affected pages. Optional approved OCR API is later scope. Old .doc: require conversion to .docx or a text PDF initially; automated conversion adds another dependency.

### Safe extraction and chunking

Stream uploads with an enforced byte cap before materializing all bytes. Validate format and ZIP expansion for DOCX, set page/text/runtime limits and never execute macros. Sanitize parser errors. Extract in an isolated bounded worker where hard parser deadlines can be enforced; cancelling a thread is not a hard kill.

Represent extracted blocks with text, physical page or DOCX section locator, heading path, table identity and block order. Preserve heading and table-header context. Start chunk tuning near 350-600 approximate tokens and 50-100 overlap, bounded by the embedding model's actual limits. These are initial tuning values, not universal guarantees. Avoid adding Hugging Face tokenizers just to count chunks; use conservative sizing/provider guidance and validate request limits.

Use deterministic chunk IDs including document version + index generation + ordinal. Record content hash, parser/chunker version, embedding provider, endpoint fingerprint, model/revision, dimension and distance metric. Changed models/recipes require a new generation.

### Reliability

Persist observable stage progress in short PostgreSQL transactions, without holding a transaction during long embedding calls. Heartbeat job leases using an independent session; serialize status writes and guard activation with job ownership/generation checks. Retry network failures with bounded backoff and provider rate-limit support. Partial embeddings never activate a document.

An unchanged file can reuse previously validated extraction/vectors only within compatible identity and authorized lifecycle rules; never merge ACLs merely because hashes match.

## 5. Chroma adapter design

New protocol: ensure_namespace, upsert_chunks, query, get_ids, delete_generation, verify_generation, health and resource shutdown. One application-owned client; lazy startup only when RAG is enabled. Preserve Qdrant adapter temporarily for rollback.

Create collections with explicit embedding_function=None and explicit cosine distance where supported by the selected pinned version. Always pass embeddings on writes and query_embeddings on search. Assert configuration on reopen; reject mismatched identity. Do not depend on defaults or let a collection automatically call an embedding service.

Namespace per industry and embedding/index identity, not per user. Record IDs bind a chunk to its generation. Scalar metadata includes document ID, version, generation, industry and ordinal. PostgreSQL determines which generation IDs are eligible. Avoid storing credentials, connection strings or unnecessary user data in metadata.

Convert returned cosine distance into clearly named similarity only where needed. Never label raw vector similarity as a probability that an answer is correct. HNSW search is approximate; tune recall/latency on representative data.

Use API-compatible batch sizes discovered/validated for the selected release; do not hardcode a vendor-wide maximum. Verify complete expected IDs and counts per generation, not count alone. Treat successful writes as insufficient until verification passes.

## 6. Permission-safe hybrid retrieval

1. Resolve user/industry/region using existing backend dependencies.
2. Query active, permitted document versions/generations in PostgreSQL. An empty grant returns no evidence, with no unfiltered query fallback.
3. Resolve selected documents and contextual follow-ups inside the authorized set. Do not load another user's memory or treat previous generated text as fresh source evidence.
4. Generate one query embedding using the approved endpoint.
5. In parallel where safe, get dense candidates from Chroma with a server-built permitted-generation filter, and lexical candidates from PostgreSQL full-text search with the same ACL predicates.
6. Fuse rankings in application code using reciprocal rank fusion, then deduplicate and apply bounded date/entity relevance and diversity. PostgreSQL full-text ranking is not claimed to be BM25.
7. Fetch canonical passage text, nearby chunks and real locators from PostgreSQL after a fresh permission/status check. Supply only permitted context to any reranker/narrator.
8. Stop below tested support thresholds; return an honest no-evidence or partial answer.

Starting evaluation settings: 15-25 candidates per retrieval path, 5-8 final passages, approximately 4k-8k evidence tokens if the configured model budget permits. Tune against document types and costs. Large permitted-ID filters need chunking/partitioning with bounded merging or a corpus partitioning strategy; test before claiming large-corpus performance.

Chroma local where_document contains/regex filters are useful filters, not a replacement for ranked lexical search. The advanced Search API is currently distributed/hosted-only in source; do not depend on it in PersistentClient. We already have PostgreSQL, so its native full-text search supplies lexical retrieval without another service.

Optional later: one bounded approved API reranking call only if evaluation shows material improvement. No local cross-encoder model download.

## 7. AI Chat integration

Reuse /chat/ask-sync, existing SSE-compatible response events and current conversation persistence. Both Classic and New Chat must receive consistent citation and failure contracts; the current frontend's sync request means stage labels are not necessarily rendered live. Genuine progressive document retrieval/token streaming requires a separate bounded transport improvement and cancellation wiring, not a claim based on the existence of an SSE endpoint.

Use three internal routes:

| Route | Examples | Sources |
| --- | --- | --- |
| Analytics | What were sales in October? How many claims? | Governed SQL |
| Documents | What does this policy cover? How do I escalate a claim? | Authorized document evidence |
| Hybrid | Why did West sales fall? What factors explain the change? | Governed SQL evidence + relevant dated document context |

Use intent/context, not the presence of what/why/how alone. Ambiguous procedure vs analytics questions ask one targeted clarification. Deterministic routing first; at most one bounded existing classifier call when needed. An optional 'Use knowledge documents' control is a preference, never an ACL override. Selected-document chat is useful but existing uploads remain admin-only in release 1; personal user uploads need a separate permission/storage lifecycle.

Follow-ups retain topic, document IDs, period and selected business filters, but rerun authorization. 'What does section 4 mean?' stays document-scoped; 'and in South?' requires region authorization and an appropriate SQL/document refresh.

### Shared evidence contract

SQL facts: metric, units, values, current/prior dates, permitted filters, computation description, source/result reference.
Document facts: evidence ID, canonical document/version/chunk ID, full bounded passage, source locator, document date/effective date if known, extraction warnings.
Answer: short answer, measured findings, documented context, recommendations if requested, cited evidence IDs and limitations. Missing sections should be omitted.

The LLM may select/connect supported facts but cannot edit numeric facts or infer proven causes from mere co-occurrence. Validate evidence IDs and attribution before emitting. Claim support needs evaluation and conservative templates; citation IDs alone do not prove entailment. Document statements never override warehouse results, and old policy versions are not presented as current without support.

Example: SQL establishes an 8% decline; a matching memo reports delivery delays. Say that the memo reports delays during the period, not that delays explain exactly 8% unless evidence actually supports that attribution.

Reject document prompt injection as untrusted source content. No document instruction can alter access, invoke tools, issue SQL or change system behavior. Follow existing quota/audit/usage controls for every optional model call. Scoped cache keys include identity/access, industry, document generations, embedding identity and query context; recheck ACLs on cache hits.

## 8. User features and release priority

Release 1:
- Existing Knowledge Hub with reliable upload/progress/retry/replace/delete.
- Ask a selected document or search the authorized library from AI Chat.
- Cited policy/procedure/definition answers and summaries of supported sections.
- Hybrid analytics explanations with measured facts separated from document context.
- Source cards with PDF page or DOCX section/table locator and an authorized preview endpoint.
- Visible no-evidence, OCR-needed, partial-extraction, provider-unavailable and conflicting-source states.

Next release:
- Multi-document comparisons with a claim/evidence table.
- Full-document summaries using bounded section coverage; top-k retrieval alone is not a complete summary. Hierarchical summaries need their own jobs/cost budgets and source links.
- Related questions, source-date filters and admin effective-date/supersedes metadata.
- Optional document-backed AskBI/Executive briefing, preserving signed metric facts and independent chart loading.
- Corpus quality dashboard: parsing failures, stale versions, unanswered topics and retrieval feedback.

Later, independently scoped:
- Approved OCR, automated .doc conversion, multilingual evaluation and approved API reranking.
- Office-friendly dependency wheelhouse and one-command diagnostics/backup/restore.
- True incremental chat streaming and coherent cancellation.

Do not promise causal inference, automatic training, unrestricted external web search, autonomous actions, every file type, charts from arbitrary PDF tables, or accurate summaries of an entire large document from a few retrieved snippets.

## 9. Lifecycle, migration and operations

Add generic backend/namespace/generation references to documents/chunks; preserve qdrant_* fields and legacy response compatibility during transition. Align Pydantic, shared TypeScript and UI contracts. Native PostgreSQL full-text indexing belongs to the application database, not changes to the read-only analytics warehouse.

Use an active-generation pointer in PostgreSQL: stage vectors -> verify -> conditional activation. There is no cross-store transaction; reconcile orphaned/incomplete generations with idempotent jobs. Old searchable content remains active until replacement succeeds. Deletion/ACL changes block immediately at retrieval even if physical Chroma deletion is delayed. Cleanup must retry errors and verify removal.

Reindex originals/canonical chunks rather than copying Qdrant data files. Build new generation manifests and validate fixture searches before switching. Keep the previous compatible index/config for rollback. Restore original files and PostgreSQL metadata consistently; rebuild Chroma if snapshots disagree. Take a quiesced full persistence-directory snapshot or a verified supported export; do not copy only Chroma's internal SQLite file or copy live files indiscriminately.

Separate readiness for vector index, parser availability, worker health, embedding configuration and provider status. Heartbeat does not prove retrieval quality. Avoid embedding provider calls on every 30-second Home refresh. Log timing and identifiers with sanitized errors; avoid raw source passages, queries and secrets in general logs. Confirm actual outbound network behavior of the pinned package. Official docs state product telemetry was removed as of 1.5.4; do not assume older-version telemetry settings apply universally.

Host local Chroma on persistent backend disk, not the Vercel frontend/serverless ephemeral filesystem. Remote users can use one centrally hosted AskMe backend without installing Chroma on each browser laptop.

## 10. Proposed configuration and code map

Proposed (not existing) settings: RAG_VECTOR_BACKEND=chroma, RAG_CHROMA_PATH, explicit retrieval limits/timeouts and RAG_DOCUMENT_CONTEXT_ENABLED. Reuse ASK_ME_RAG_ENABLED and existing RAG_EMBEDDING_* credentials; no public secrets. Embedding endpoint and model must actually support embeddings.

Files/components:
- New rag/index.py, index_factory.py, chroma_index.py, retrieval.py and evidence.py.
- Update rag/parsers.py, chunking.py, embeddings.py, job_processor.py and worker.py.
- Update services/knowledge.py, repositories/knowledge_documents.py, models/knowledge.py and additive migration.
- Update api/routes/knowledge.py and system.py; add authorized preview/source route.
- Update chat/query_router.py, service.py, generation.py and evidence/citation response contracts.
- Update Knowledge Hub page, shared-types, chat citation rendering and tests in both chat views.
- Update pyproject optional extras to isolate chroma dependencies from Qdrant/legacy Mongo dependencies; resolve exact pinned wheel compatibility without unsupported omissions.

## 11. Phased implementation and acceptance

| Phase | Deliverable | Exit gate |
| --- | --- | --- |
| 0 Compatibility | Exact pinned dependency report, Windows wheel/DLL and no-model-download test, approved embedding/narration configuration | Explicit decision on no-HF-packages requirement; persistent add/query/delete/reopen fixture succeeds |
| 1 Storage | Chroma adapter, lifecycle, generic metadata, readiness and feature flag | One process owns storage; restart and parallel-thread tests pass |
| 2 Ingestion | Structured PDF/DOCX, tables/provenance, bounded worker, leases and cleanup fixes | Real parser fixtures pass; failed replacement never removes old searchable version |
| 3 Retrieval | ACL-filtered dense + PostgreSQL lexical, fusion, evidence assembly | No unauthorized/deleted evidence; retrieval quality meets reviewed benchmark |
| 4 AI Chat | Three routes, follow-ups, grounded mixed narration, source cards | Both chat views pass; unsupported causes/numbers and malformed citations rejected |
| 5 UX and migration | Source preview, clear errors/progress, additive migration/reindex/rollback runbook | Offline suite passes; office pilot separately verifies real services and document set |
| 6 Enhancements | Whole-document summary, comparisons and optional report context | Coverage, cost and evidence controls evaluated separately |

Offline verification uses fake embeddings/LLM, actual embedded Chroma and SQLite-backed app persistence; PostgreSQL full-text behavior requires PostgreSQL integration acceptance, since SQLite cannot prove it. Do not start the configured API, apply migrations or call live providers on this development laptop without an explicit request.

Create at least 60 curated cases across analytics/document/hybrid/ambiguous/follow-up/no-evidence/conflicting/version-restricted questions, with expected source passages reviewed by a human. Proposed pilot gates: >=90% Recall@10 on answerable retrieval cases, >=95% valid-and-supported citations, >=90% correct abstention on deliberately unsupported questions, zero unauthorized evidence and zero modified governed numeric facts in the suite. These are targets, not measured results or guarantees. Assess support manually as well as with automation; separate route accuracy from retrieval and generation quality.

Test multi-page/empty/scanned/encrypted PDF, DOCX tables/order, corrupt/large inputs, dimensions/nonfinite vectors, model change, ACL revocation, duplicate/restarted jobs, interrupted activation, delete during ingest, provider timeout, cost caps, disk-full and restore. Measure first usable SQL result separately from optional complete narration. Establish realistic retrieval, ingestion, end-to-end p50/p95 and memory/disk budgets on expected office corpus before enabling broadly.

## 12. Cons and mitigations

| Risk/cost | Practical effect | Mitigation/limit |
| --- | --- | --- |
| Dependency footprint | ONNX/tokenizers/HF transitive packages may violate office policy even unused | Dependency report and explicit go/no-go; no unsupported stripped install |
| Process constraint | Multiple API workers/standalone writers cannot safely share local path | One owner process; future server adapter when needed |
| Memory/CPU/disk | HNSW working set, embedding dimensions and document count affect laptop performance | Corpus limits, explicit thread/batch budgets, representative benchmark |
| Local/cloud feature gaps | Search API examples may not work locally | Use query/get + PostgreSQL full-text fusion; pin capabilities |
| Vendor transition | Existing managed Cloud is retiring | Local OSS, own data and portable adapter; monitor maintained releases |
| Network/cost | Embedding and narration depend on allowed APIs and quotas | Approved endpoint, batch/caching, bounded calls, honest degraded states |
| Extraction limits | Scans, legacy .doc and complex layouts reduce evidence quality | Clear support matrix and optional separately approved OCR/conversion |
| Retrieval omissions | Similar wording is not guaranteed evidence; approximate search may miss passages | Lexical+dense fusion, benchmarks, abstention and source inspection |
| Unsupported explanations | LLM may invent causes despite valid-looking citations | Evidence contracts, conservative narration, claim-support review |
| Two-store consistency | Metadata activation and vector writes are separate | Staged generations, verification/reconciliation and reversible cutover |
| Backup/upgrade burden | Embedded persistence still needs recovery and compatible upgrades | Tested full snapshots/rebuild, pinned versions, rollback drill |
| Security remains ours | Metadata filtering alone does not authenticate or authorize users | Backend ACL authority, filters before retrieval and fresh checks before narration |

## 13. Primary sources checked 2026-11-15

- PersistentClient and client/server modes: https://docs.trychroma.com/docs/run-chroma/clients
- Explicit vectors: https://docs.trychroma.com/docs/collections/add-data and https://docs.trychroma.com/docs/querying-collections/query-and-get
- Embedding defaults: https://docs.trychroma.com/docs/embeddings/embedding-functions
- HNSW/cosine configuration: https://docs.trychroma.com/docs/collections/configure
- Metadata/content filtering: https://docs.trychroma.com/docs/querying-collections/metadata-filtering and https://docs.trychroma.com/docs/querying-collections/full-text-search
- Process/memory constraints: https://cookbook.chromadb.dev/core/system_constraints/
- Local vs advanced Search API source: https://github.com/chroma-core/chroma/blob/main/chromadb/api/models/Collection.py
- PostgreSQL full-text retrieval: https://www.postgresql.org/docs/current/textsearch-intro.html
- Dependency sources (main, not a release lock): https://github.com/chroma-core/chroma/blob/main/requirements.txt and https://github.com/huggingface/tokenizers/blob/main/bindings/python/pyproject.toml
- Cloud retirement / OSS continuation: https://www.trychroma.com/cloud-wind-down
- Telemetry/version note: https://docs.trychroma.com/docs/overview/oss
- Backup guidance: https://cookbook.chromadb.dev/strategies/backup/
- DOCX API: https://python-docx.readthedocs.io/en/latest/api/document.html
- PDF extraction/OCR boundaries: https://pypdf.readthedocs.io/en/stable/user/extract-text.html
