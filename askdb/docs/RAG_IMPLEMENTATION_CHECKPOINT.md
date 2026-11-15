# Portable RAG implementation checkpoint

Status: first implementation slice, feature-gated; not production acceptance of the full 11-point plan.

## Implemented

- Opt-in Chroma 1.5.9 optional extra (`rag-chroma`) and process-cached adapter; automatic embeddings disabled; explicit cosine vectors, identity validation, authorized document filters, and sanitized health result.
- Existing Qdrant remains the default/rollback path. Chroma uses separate hashed embedding/endpoint namespaces. Existing qdrant_* metadata fields remain compatibility fields; no new migration was applied or added in this slice.
- Knowledge ingestion selects the configured adapter. PDF page separators and DOCX paragraph/table order are preserved. Blocking extraction/embedding/upsert work moves off the event loop. Cleanup jobs are no longer skipped solely because their documents are deleted/superseded; deletion failures propagate and counts are verified.
- Retrieval refreshes document eligibility and uses PostgreSQL canonical chunk text/locators rather than trusting returned index text. Evidence passages can be longer than UI previews. Initial minimum similarity is configurable and remains uncalibrated.
- Both Classic/New Chat send explicit useDocuments (default false), render an accessible switch and show each user turn's submitted mode. The backend gates all document-answer exits and hybrid retrieval. Legacy generated document summaries are not reused; document-enabled answers bypass SQL answer caching and are not stored there. Cache namespace changes prevent reuse of legacy mixed answers.
- Explicit delivery-policy questions route before SQL-only planning, including the synthetic demo policy. Mixed explicit procedure/metric requests currently ask for separate questions rather than executing unsafe compound plans.
- Narration instructions separate document observations from causal claims; citation numbers must refer to supplied passages or the service returns an extractive fallback. This is citation-reference validation, not proof of claim support.

## Office setup after dependency and code review

Do not copy virtual environments. In a suitable backend environment resolve/test `pip install -e ".[dev,rag-chroma]"` from apps/api. Keep Chroma's transitive dependencies subject to office approval. This checkout did not install Chroma.

Configure these API settings in the actual backend environment:

    ASK_ME_RAG_ENABLED=true
    RAG_VECTOR_BACKEND=chroma
    RAG_CHROMA_PATH=<approved absolute local folder outside OneDrive>
    RAG_WORKER_IN_PROCESS=true
    RAG_EMBEDDING_PROVIDER=openai_compatible
    RAG_EMBEDDING_MODEL=<approved embedding model>
    RAG_EMBEDDING_BASE_URL=<approved API endpoint>
    RAG_EMBEDDING_API_KEY=<server-only credential>

Use one backend process and only its in-process ingestion worker for embedded Chroma. A separately launched worker or second backend instance must not share the persistence folder. Have the normal deployment process verify the existing knowledge migration 0011 and any later application migrations; no configured database checks were performed here.

Upload docs/rag-demo/01_DEMO_AUTOMOTIVE_DELIVERY_POLICY.md through Knowledge Hub as admin in Automotive. Wait for active INDEXED state, then enable Use knowledge documents in AI Chat and ask 'How do I escalate a delayed delivery?' Expected source facts are two/five business days, attributed to the synthetic policy. OFF must not retrieve it. The document is not auto-uploaded or seeded by the implementation.

Existing Qdrant documents must be reindexed into Chroma before they are searchable through it. Do not copy Qdrant files or drop old indexes. Switching backend requires reviewing old cleanup jobs: backend-neutral per-document index ownership is not yet implemented. Roll back to the previous RAG_VECTOR_BACKEND=qdrant and compatible previous index configuration if necessary. Do not delete either store during rollout.

## Verification

34 backend tests passed across portable routing/adapter contracts, traditional RAG and feature flags, including mocked full request OFF/capability gates, existing SQLite persistence and ACL cases. The sandbox initially stalled while Windows asyncio created its local event-loop socket; the same offline suites passed outside the sandbox. No PostgreSQL/provider integration was run.

22 frontend tests passed across chat presentation helpers, mode switching and SSE folding. The document-mode hook test verifies OFF/ON request values and immutable turn snapshots. Final TypeScript and targeted frontend ESLint results are recorded in the delivery message. Chroma adapter/factory targeted strict mypy passed; final retrieval/ingest checks are recorded in the delivery message.

The adapter's actual Chroma runtime is NOT verified in this development checkout: the package is absent. Adapter tests use fakes. The user's independent office smoke test is compatibility evidence only, not this application's end-to-end validation. No production build or browser flow verification was performed in this slice. Git baseline/diff inspection failed because the parent repository could not be resolved.

## Remaining required work before broad enablement

- Combined application/Chroma dependency and actual embedded adapter integration testing.
- Backend-neutral storage references and staged index generations, independently committed lease heartbeats and consistent two-store activation/reconciliation. Current reindex/replace remains based on existing lifecycle; do not claim atomic cross-store activation.
- PostgreSQL lexical retrieval/rank fusion, strict route/classifier contracts and source labels, complete compound execution and date/source comparison validation.
- Source-scoped document follow-ups with provenance; current document summaries are deliberately not reused. General-chat short context is reset when entering document mode or after a document answer.
- Fresh regional/identity revocation checks at narration boundary, not just eligibility refresh with the request principal; authorized source preview/download and complete admin ACL grant workflow.
- Output claim-support checks, evidence sufficiency/contradiction handling and robust partial-provider failure states on hybrid paths. Existing hybrid snippet-merging behavior is retained when enabled; it is not the final shared evidence narrator.
- Upload streamed limits, hard parser isolation/deadlines, full OCR/partial-extraction UX, workload/resource benchmarks and readiness probe redesign to avoid frequent embedding calls.
- Full 150-200 held-out routing/groundedness/security cases, both chat UI browser checks, production build and configured office acceptance.

The first slice is a foundation for review, not a claim that every structured/unstructured question or all planned security gates are complete.
