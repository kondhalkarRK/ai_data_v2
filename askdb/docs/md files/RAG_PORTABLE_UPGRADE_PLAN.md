# AskMe portable RAG upgrade plan

Date: 2026-11-15. Status: proposal for review; no application changes or dependency installation.

## 1. Recommendation and constraints

Use SQLite + sqlite-vec as the first candidate for the office-laptop deployment, behind a provider-neutral VectorIndex interface. It stores vectors in an application-owned file and does not need a database service, Docker, Hugging Face models, PyTorch, or SentenceTransformers. This recommendation is conditional on a small Windows compatibility spike: the approved Python distribution must load the packaged native extension, and office endpoint controls must allow that DLL. Pin a verified stable release; do not adopt the alpha shown by the documentation automatically.

Chroma PersistentClient is the alternative if the organization accepts its dependency footprint. Supply our own embeddings and disable its embedding function explicitly. Chroma is not a zero-dependency replacement: its default embedding function can download a local model, and its Python dependency tree includes ONNX/tokenizer/native components. Resolve and inspect the exact pinned release before choosing it.

Keep existing Qdrant as an optional rollback adapter, not a required installation. The current code already implements embedded Qdrant, so the office failure cannot be attributed to missing server software without diagnostics. Its actual error remains unknown.

Interpret 'no external impact' as no additional local services or downloaded ML models. Semantic embeddings and generated narration will still use an approved API endpoint, as the application does today. If API calls are also prohibited, offer explicitly labeled lexical retrieval and extractive answers; that is a different, lower-capability mode, not equivalent semantic RAG. A chat model does not automatically expose an embeddings API.

The existing PostgreSQL application database remains responsible for authentication, ACLs, document metadata and durable jobs. Replacing the vector store does not make the entire application independent of PostgreSQL. SQLite is the derived vector/text index only.

## 2. Reviewed implementation and findings

Reviewed the RAG modules, KnowledgeService, document HTTP routes, metadata models/repository integration, chat routing and generation, Knowledge Hub UI, readiness references, dependency declarations, documentation, and existing RAG test definitions. This is source review, not live office-laptop verification.

- `app/rag/qdrant_index.py`: hardwired adapter supports server/local/memory. Consumers construct clients independently; introduce an application-lifetime factory with explicit close and shared ownership. Local file locking and readiness probes need coordination.
- `app/rag/embeddings.py`: HTTP OpenAI-compatible embeddings already exist. Local SentenceTransformers are explicitly rejected. Keep that boundary; validate every batch for dimensions, finite values, completeness and stable model identity.
- `app/rag/parsers.py`: PDF pages are concatenated with newlines, while chunking expects page markers. Accurate page provenance is therefore lost on ordinary PDFs. DOCX reads paragraphs only, omitting tables. Legacy `.doc` is unsupported.
- `app/rag/chunking.py`: overlapping windows and locators exist, but need structured parser blocks, real page/heading locators, table handling and versioned extraction/chunking recipes.
- `app/rag/job_processor.py`: useful durable jobs, leases, staged processing, count verification and version replacement already exist. Preserve them. Audit the early terminal-document return: it currently precedes DELETE_VECTORS / SUPERSEDE_CLEANUP dispatch, which can skip physical cleanup for those states. Delete errors are also swallowed by the Qdrant adapter; successful cleanup must be verified before marking a cleanup job complete.
- In-process ingest/retrieval currently calls synchronous parsing, embedding HTTP and vector operations from async paths. Move blocking work off the API event loop, use bounded execution and renew leases throughout long stages.
- `app/services/knowledge.py`: one authorized search path is a good base. It filters allowed document IDs at vector query time and checks membership afterward. The second membership check reuses the earlier allowed set, rather than querying fresh permissions. Revalidate current permissions/status before sending final evidence. Entity filtering after top-k can discard useful results without replenishing them.
- Returned text is clipped to 400 characters. Separate UI previews from the larger, bounded evidence passages used for generation. The existing transformed cosine value is a similarity indicator, not a calibrated answer-confidence probability.
- `app/services/chat/query_router.py`: document/SQL/hybrid routing exists, including why/driver cues, but substring heuristics are not enough for varied what/how/follow-up questions. Corpus availability at one routing site uses the legacy filesystem list even with modern RAG enabled; use authorized modern metadata instead.
- `app/services/chat/service.py`: document-only grounded generation exists. Hybrid currently retrieves at most two snippets and merges them into insights; implement a shared evidence-aware narration step for genuine SQL + document explanations.
- `app/rag/generation.py`: evidence-only instructions and extractive fallback exist; add validated citation IDs, claim/source separation, explicit untrusted-document boundaries and contradiction handling.
- Knowledge Hub already supports admin upload/retry/reindex/delete and status display. Preserve the page and improve the lifecycle instead of building a second library.
- Models, repository methods, API serialization and readiness use Qdrant-specific names. Decouple them additively, retaining legacy compatibility during transition.

## 3. Store comparison

| Option | Separate service | Local model required | Fit and limits |
| --- | --- | --- | --- |
| SQLite + sqlite-vec | No | No; supply vectors | Preferred lightweight candidate; native extension approval and Windows wheel compatibility are gates; benchmark filtered search and corpus size |
| Chroma PersistentClient | No | No when explicit embeddings are supplied | Convenient embedded alternative; larger dependency tree and native components; disable default embedding/model downloads |
| Existing Qdrant local | No | No when explicit vectors are supplied | Lowest code churn, but existing lock/client lifecycle needs correction; does not resolve a blocked Python package/DLL automatically |

Do not promise that any library bypasses company installation policy. Package installation, DLL execution and writable storage are distinct constraints. A minimal stdlib SQLite + exact Python cosine adapter can be an explicitly selected small-corpus fallback if all extensions are blocked; it needs a strict corpus cap and benchmarks, and must not be silently selected.

## 4. Proposed architecture

Ingestion:

Admin upload -> bounded format validation -> immutable original -> PostgreSQL metadata/job -> structured PDF/DOCX extraction -> provenance-preserving chunks -> approved embeddings API -> staged SQLite vector + lexical index -> verify -> atomically activate metadata generation.

Question answering:

Question + conversation context + authorized industry/region -> intent route -> governed SQL and/or authorized retrieval -> evidence bundle -> grounded narrator -> validated citations + limitations -> existing chat events/UI.

Core modules proposed:

- `rag/index.py`: VectorIndex protocol and generic hit/namespace types; upsert, filtered query, delete, count, health and close.
- `rag/index_factory.py`: backend selection and application-scoped lifecycle.
- `rag/sqlite_index.py`: sqlite-vec vectors plus lexical text index; transactions, persistence, locks and namespace checks.
- Existing `rag/qdrant_index.py`: compatibility adapter; Chroma adapter only if selected after the spike.
- `rag/parsers.py`: ParsedDocument / blocks with page or section/table provenance.
- `rag/retrieval.py`: authorization, query construction, dense/lexical fusion, deduplication and context assembly.
- `rag/evidence.py`: immutable evidence bundle and citation/source contracts.
- `rag/generation.py`: common grounded document and hybrid narration.
- Existing KnowledgeService, repository, worker, routes and UI retain their responsibilities.

No agent framework, LangChain, LlamaIndex, local neural reranker or model training is needed.

## 5. Document support

First release: text-based PDF, DOCX (body paragraphs, headings and tables), TXT, Markdown and existing HTML compatibility.

PDF extraction must preserve physical page numbers including empty pages. DOCX references use headings/paragraphs/tables; do not invent page numbers because pagination depends on Word rendering. Keep table header context across chunks. Complex PDF tables receive explicit extraction limitations until validated.

Scanned PDFs need OCR; pypdf alone cannot read text inside images. Under the no-additional-engine constraint, detect image-only/partially scanned pages and report 'OCR required' or a visible partial-extraction warning. Optional organization-approved OCR is a later, separate capability.

Old binary `.doc` files need a converter/parser beyond python-docx. First release should ask users to save as `.docx` or text PDF; do not silently claim support. If `.doc` is mandatory, approve and evaluate a conversion dependency as a separate scope item.

Enforce streamed upload byte caps before reading all bytes, page/decompression/text limits, parser deadlines and safe failure messages. Keep originals private. Reject encrypted/unreadable files with actionable guidance.

## 6. Retrieval and evidence

1. Resolve identity, industry, region, document visibility, active version and selected document scope.
2. Resolve follow-ups into a bounded standalone retrieval query without widening access.
3. Search dense vectors and SQLite FTS5 lexical matches only within authorized active document IDs. Verify FTS5 availability during compatibility spike.
4. Retrieve a bounded candidate pool; fuse ranks, remove duplicates, apply useful entity/date/version signals and choose diverse passages. Do not convert scores between backends without defining distance semantics.
5. Retrieve adjacent authorized chunks where needed; retain source locators and a bounded evidence-token budget. Keep previews short while retaining complete evidence text internally.
6. Recheck live metadata and permissions before evidence reaches narration; account for replacement, deletion or scope changes during a request.
7. Below relevance/support thresholds, state insufficient evidence. Never substitute hash vectors or generate an invented explanation.

Metadata includes document/version, chunk ordinal, page/section/table locator, industry, content hash, index generation, embedding provider/endpoint identity/model/dimension, parser version and chunk recipe version. Namespace identities must prevent collisions across providers, endpoints, dimensions or changed recipes.

## 7. Answer behavior

| Question | Behavior |
| --- | --- |
| What were sales last month? | Governed SQL; document retrieval unnecessary |
| What does the warranty policy cover? | Authorized document retrieval + cited answer |
| How do I submit a claim? | Document procedure with cited steps |
| Why did West sales decline? | SQL comparison/contribution evidence plus relevant dated documents; distinguish observed drivers from reported explanations |
| How can sales improve? | Evidence-backed suggestions labeled as recommendations; no invented forecast or guaranteed uplift |
| What about the previous month? | Resolve prior metric/period, recompute SQL and retrieve matching context if needed |

Do not route every 'what' or 'how' question to RAG. Classify by requested evidence, metric and context. Prefer deterministic rules first; use at most one bounded existing LLM classification when genuinely ambiguous.

Hybrid response structure: measured result -> observed contributions -> document-supported context -> limitations. Example: 'Sales fell 8% according to the governed query. The regional memo reports stock shortages [1]. The memo is relevant context, but does not establish that shortages caused the entire decline.'

Documents are untrusted content, not instructions. Do not execute document commands, tools or SQL. Generation references allowlisted evidence IDs; validate references before rendering. Historical document numbers remain attributed to their source and cannot overwrite current warehouse metrics. Surface conflicting/dated evidence.

Document-only answers may quote supported document numbers. Analytics values must match server-provided facts. Unsupported causal claims should be removed or replaced by explicit uncertainty; citation validity alone does not prove a claim is supported.

Start integration in Knowledge Hub and AI Chat. Add opt-in document context to Executive Intelligence and AskBI narration in a later phase, preserving signed numerical evidence, independent chart loading, quotas and report/date/scope binding. No document context is allowed to change metric formulas or chart results.

## 8. Persistence and operational behavior

Use a local, non-synced application data folder with restrictive permissions. Start with one API process and one coordinated in-process ingestion worker. Do not assume a shared SQLite file is a multi-host vector service. Bound writers, busy timeouts and thread ownership; test concurrent reads and ingestion.

Index generations are staged: metadata never points at a partially built index. Across PostgreSQL and SQLite there is no single atomic transaction; use idempotent jobs, activation pointers, reconciliation and orphan cleanup. Previous searchable versions remain active until the replacement is verified. Deletes deny retrieval immediately, with physical index cleanup retried and checked afterward.

Health checks inspect index readability and worker state without creating competing clients or embedding new text on every Home poll. Separate vector-store health, embedding configuration/provider status and narration provider status. Expensive external probes should be explicit or cached with bounded TTL.

Proposed settings (new, not currently implemented): RAG_VECTOR_BACKEND=sqlite_vec, RAG_VECTOR_PATH, existing RAG_EMBEDDING_* and ASK_ME_RAG_ENABLED. No secrets in public settings or logs. Package a pinned Windows wheelhouse if office package access is restricted, subject to normal policy. Keep API embeddings and narration credentials server-side.

## 9. Delivery phases and exit gates

| Phase | Work | Reviewable exit |
| --- | --- | --- |
| 0. Office compatibility decision | Capture sanitized existing error; identify Python/architecture; verify sqlite-vec DLL, FTS5, writable folder, dependencies and approved embedding endpoint | Backend choice justified by actual compatibility; no live-provider check unless explicitly requested |
| 1. Storage boundary | Generic adapter/factory, SQLite implementation, lifecycle, generic metadata and readiness | Persistent insert/search/delete works after restart; no local model download or separate service |
| 2. Reliable ingestion | Structured extraction, tables/page locators, bounded work, visible progress, retry/lease/cleanup fixes | PDF/DOCX fixture citations locate correct content; interrupted jobs resume safely |
| 3. Retrieval quality/security | Authorized hybrid search, evidence assembly, thresholds, fresh ACL recheck | Relevant passages retrieved; zero unauthorized/deleted/superseded text in evidence |
| 4. Chat narration | Intent routing, document Q&A, mixed SQL/document evidence, claim/citation validation | Why/what/how cases and follow-ups behave correctly; unsupported causes are qualified |
| 5. Knowledge Hub UX | Safe status/errors, preview and authorized source access, citation panel | Upload-to-answer lifecycle understandable without exposing infrastructure details |
| 6. Migration and acceptance | Reindex originals into new generations, verify counts/search, feature-flag cutover and rollback | Reviewed offline suite passes; configured office acceptance and latency measured separately |
| 7. Optional report context | Shared retrieval for dashboard/AskBI narration | Numerical evidence unchanged; optional RAG failure never blocks charts |

Preserve old columns and vectors during additive migration. Introduce backend-neutral references without destructive renames; update API/shared types together. Changing backend/model/recipe requires verified reindexing, not copying incompatible vector files. Rollback restores the prior configuration and compatible index; retain both until acceptance.

## 10. Verification and acceptance

Use existing mocked providers and SQLite persistence tests here; do not start the real API or apply migrations against a configured PostgreSQL instance during this planning work.

- Real embedded-index contract tests: dimensions, nonfinite vectors, namespace separation, filtered retrieval, restart persistence, idempotent upsert, cleanup and concurrent read/write behavior.
- Parser fixtures: multipage PDF, empty/scanned/encrypted pages, DOCX headings/tables, corrupt archives and extraction limits.
- Lifecycle tests: worker crash, expired lease, duplicate job, partial indexing, failed replacement, delete during ingest, cleanup retry and generation activation.
- Security tests: user/region/industry isolation, ACL revocation before narration, deleted versions, prompt injection, unauthorized citation/source requests and cache partitioning.
- Answer tests: numeric SQL unaffected, supported/unsupported why, procedural how, definitions, ambiguous follow-ups, contradictions, old documents, embedding/narration failures and citation validation.
- Curated evaluation set: representative documents and at least 40 reviewed question/expected-evidence cases. Record retrieval Recall@k, citation correctness/support and abstention quality. Require zero unauthorized evidence and zero changed numerical facts in the acceptance set.
- Measure ingestion throughput, memory/disk and retrieval/answer p50/p95 on actual office-scale corpora; agree thresholds after the spike rather than claiming unmeasured performance.
- Frontend tests, typecheck, changed-file lint and production build; browser review for upload/progress/citations/themes/responsive behavior.

Unresolved inputs for implementation: approved embeddings endpoint/model, whether legacy .doc or scanned PDF support is mandatory, approximate document/page volume, and whether the laptop blocks services only or also Python wheels/native DLLs. These do not prevent preparing the code, but determine compatibility and scope.

## 11. Primary research sources

Checked 2026-11-15. Exact pinned release compatibility still needs verification.

- Chroma client modes / PersistentClient: https://docs.trychroma.com/docs/run-chroma/clients
- Chroma default model behavior: https://docs.trychroma.com/docs/embeddings/embedding-functions
- Supplying precomputed Chroma embeddings: https://docs.trychroma.com/docs/collections/add-data
- Chroma dependency source (main; inspect selected release separately): https://raw.githubusercontent.com/chroma-core/chroma/main/requirements.txt
- sqlite-vec overview: https://alexgarcia.xyz/sqlite-vec/
- sqlite-vec Python install/extension loading: https://alexgarcia.xyz/sqlite-vec/python.html
- Qdrant Python client local mode: https://github.com/qdrant/qdrant-client
- PDF extraction and scanned-page limits: https://pypdf.readthedocs.io/en/stable/user/extract-text.html
