# features/okf_knowledge/okf_retriever.py
#
# Retrieval layer for OKF concept bundles. Zero LLM cost: uses the
# same local sentence-transformer embedder already used elsewhere in
# this app (features/rag_query_memory/embedder.py) plus a dedicated
# ChromaDB collection, reusing the same persistent client already
# used by features/rag_query_memory/vector_store.py.
#
# Nothing in this file modifies embedder.py or vector_store.py — it
# only imports their existing public functions.
#
# New, additive module.

from __future__ import annotations

from features.rag_query_memory.embedder import embed_text
from features.rag_query_memory.vector_store import get_chroma_client
from features.okf_knowledge.okf_store import read_all_concepts

_COLLECTION_OKF = "okf_knowledge"

_MAX_CONTEXT_CHARS_DEFAULT = 800   # keep the injected context small -> minimal token impact
_SNIPPET_CHARS_DEFAULT     = 320   # per-concept excerpt length


def get_okf_collection():
    """Get or create the dedicated OKF ChromaDB collection; None on failure."""
    try:
        client = get_chroma_client()
        return client.get_or_create_collection(_COLLECTION_OKF)
    except Exception:
        return None


def reindex_all() -> int:
    """
    Re-embed and re-index every concept currently stored on disk
    (features/okf_knowledge/okf_store.py) into the OKF Chroma
    collection. Safe to call repeatedly (upserts by concept_id).

    Returns the number of concepts indexed.
    """
    collection = get_okf_collection()
    if collection is None:
        return 0

    concepts = read_all_concepts()
    if not concepts:
        return 0

    indexed = 0
    for concept in concepts:
        text = f"{concept['title']}\n{concept['body']}"
        embedding = embed_text(text)
        if not embedding:
            continue
        try:
            collection.upsert(
                ids=[concept["concept_id"]],
                documents=[concept["body"]],
                embeddings=[embedding],
                metadatas=[{
                    "title": concept["title"],
                    "source_doc": concept["source_doc"],
                    "source_page": str(concept["source_page"]),
                }],
            )
            indexed += 1
        except Exception:
            continue

    return indexed


def indexed_concept_count() -> int:
    """Return how many concepts are currently indexed (0 on failure)."""
    try:
        collection = get_okf_collection()
        if collection is None:
            return 0
        return collection.count()
    except Exception:
        return 0


def get_relevant_context(
    question: str,
    top_k: int = 3,
    max_context_chars: int = _MAX_CONTEXT_CHARS_DEFAULT,
) -> str:
    """
    Given a natural-language question, return a small, ready-to-inject
    text block with the most relevant OKF concept snippets — capped at
    max_context_chars so token impact on the LLM prompt stays minimal
    (roughly max_context_chars / 4 tokens, e.g. ~200 tokens at the
    default 800-char cap).

    Returns "" if no knowledge base is indexed or nothing relevant is
    found — safe to always call and concatenate.
    """
    collection = get_okf_collection()
    if collection is None:
        return ""

    try:
        if collection.count() == 0:
            return ""

        embedding = embed_text(question)
        if not embedding:
            return ""

        results = collection.query(
            query_embeddings=[embedding],
            n_results=min(top_k, collection.count()),
        )
    except Exception:
        return ""

    docs  = (results or {}).get("documents", [[]])[0]
    metas = (results or {}).get("metadatas", [[]])[0]

    if not docs:
        return ""

    parts = []
    used_chars = 0

    for doc, meta in zip(docs, metas):
        snippet = (doc or "").strip()[:_SNIPPET_CHARS_DEFAULT]
        if not snippet:
            continue

        title = (meta or {}).get("title", "")
        source = (meta or {}).get("source_doc", "")
        page = (meta or {}).get("source_page", "")

        entry = f"- ({source}, p.{page} — {title}): {snippet}"

        if used_chars + len(entry) > max_context_chars:
            break

        parts.append(entry)
        used_chars += len(entry)

    if not parts:
        return ""

    return "Relevant knowledge base excerpts:\n" + "\n".join(parts)
