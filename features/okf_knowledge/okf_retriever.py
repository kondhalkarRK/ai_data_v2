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


def clear_index() -> int:
    """Remove all concepts from the OKF vector index. Returns count cleared."""
    collection = get_okf_collection()
    if collection is None:
        return 0
    try:
        count = collection.count()
        if count <= 0:
            return 0
        data = collection.get()
        ids = data.get("ids") or []
        if ids:
            collection.delete(ids=ids)
        return count
    except Exception:
        try:
            client = get_chroma_client()
            client.delete_collection(_COLLECTION_OKF)
        except Exception:
            pass
        return 0


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
        clear_index()
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
                    "doc_code": concept.get("doc_code") or "",
                    "doc_type": concept.get("doc_type") or "sop",
                    "source_locator": concept.get("source_locator") or (
                        f"page {concept['source_page']}"
                    ),
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


def get_relevant_snippets(
    question: str,
    top_k: int = 3,
    max_context_chars: int = _MAX_CONTEXT_CHARS_DEFAULT,
) -> list[dict]:
    """
    Return structured OKF hits for UI citations / narration enrichment.

    Each item: {title, source_doc, source_page, snippet, entry}
    """
    collection = get_okf_collection()
    if collection is None:
        return []

    try:
        if collection.count() == 0:
            return []
        embedding = embed_text(question)
        if not embedding:
            return []
        results = collection.query(
            query_embeddings=[embedding],
            n_results=min(top_k, collection.count()),
        )
    except Exception:
        return []

    docs = (results or {}).get("documents", [[]])[0]
    metas = (results or {}).get("metadatas", [[]])[0]
    distances = (results or {}).get("distances", [[]])[0]
    if not docs:
        return []

    out: list[dict] = []
    used = 0
    for index, (doc, meta) in enumerate(zip(docs, metas)):
        snippet = (doc or "").strip()[:_SNIPPET_CHARS_DEFAULT]
        if not snippet:
            continue
        title = (meta or {}).get("title", "")
        source = (meta or {}).get("source_doc", "")
        page = (meta or {}).get("source_page", "")
        locator = (meta or {}).get("source_locator") or f"page {page}"
        entry = f"- ({source}, {locator} — {title}): {snippet}"
        if used + len(entry) > max_context_chars:
            break
        out.append({
            "title": title,
            "source_doc": source,
            "source_page": page,
            "snippet": snippet,
            "entry": entry,
            "doc_code": (meta or {}).get("doc_code", ""),
            "doc_type": (meta or {}).get("doc_type", "sop"),
            "source_locator": locator,
            "distance": distances[index] if index < len(distances) else None,
        })
        used += len(entry)
    return out


def get_relevant_context(
    question: str,
    top_k: int = 3,
    max_context_chars: int = _MAX_CONTEXT_CHARS_DEFAULT,
) -> str:
    """
    Given a natural-language question, return a small, ready-to-inject
    text block with the most relevant OKF concept snippets — capped at
    max_context_chars so token impact on the LLM prompt stays minimal.

    Returns "" if no knowledge base is indexed or nothing relevant is
    found — safe to always call and concatenate.
    """
    snippets = get_relevant_snippets(question, top_k=top_k, max_context_chars=max_context_chars)
    if not snippets:
        return ""
    return "Relevant knowledge base excerpts:\n" + "\n".join(s["entry"] for s in snippets)

