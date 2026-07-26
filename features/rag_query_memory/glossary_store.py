"""
features/rag_query_memory/glossary_store.py
Domain glossary retrieval via local embeddings - no LLM calls.
"""
from features.rag_query_memory import embedder, vector_store

GLOSSARY_SEED = [
    ("active dealer", "A dealership with at least one sale or order in the last 90 days."),
    ("fleet order", "A bulk vehicle purchase placed by a corporate or government buyer."),
    ("churn", "Customers or dealers who stopped purchasing within the measurement period."),
    ("YoY growth", "Year-over-year percentage change comparing current year to prior year."),
    ("top performer", "Salesperson or dealer ranked highest by revenue or unit volume."),
    ("market share", "A brand or segment's percentage of total sales within a region."),
    ("conversion rate", "Ratio of leads or inquiries that result in a completed sale."),
]

_MAX_GLOSSARY_PROMPT_CHARS = 400  # ~100 tokens for glossary block


def _truncate(text: str, max_len: int) -> str:
    """Truncate text with ellipsis when longer than max_len."""
    text = (text or "").strip()
    if len(text) <= max_len:
        return text
    return text[: max_len - 3] + "..."


def seed_glossary_once() -> None:
    """Seed glossary collection once when empty."""
    try:
        collection = vector_store.get_glossary_collection()
        if vector_store.collection_count(collection) > 0:
            return
        for term, definition in GLOSSARY_SEED:
            text = f"{term}: {definition}"
            embedding = embedder.embed_text(text)
            if not embedding:
                continue
            doc_id = term.replace(" ", "_")
            vector_store.add_to_collection(
                collection,
                doc_id,
                text,
                embedding,
                {"term": term, "definition": definition},
            )
    except Exception:
        pass


def retrieve_glossary_terms(question: str, k: int = 2) -> list[dict]:
    """Return up to k relevant glossary terms; empty list on any failure."""
    try:
        # LOCAL EMBEDDING - ZERO LLM COST
        embedding = embedder.embed_text(question)
        if not embedding:
            return []
        collection = vector_store.get_glossary_collection()
        results = vector_store.query_collection(collection, embedding, k)
        if not results:
            return []
        metadatas = results.get("metadatas") or [[]]
        if not metadatas or not metadatas[0]:
            return []
        terms = []
        for meta in metadatas[0]:
            meta = meta or {}
            term = (meta.get("term") or "").strip()
            definition = _truncate(meta.get("definition") or "", 120)
            if term and definition:
                terms.append({"term": term, "definition": definition})
        return terms[:k]
    except Exception:
        return []


def format_glossary_for_prompt(terms: list[dict]) -> str:
    """Format glossary terms for prompt injection; empty string if none."""
    if not terms:
        return ""
    lines = ["DOMAIN GLOSSARY:"]
    for item in terms[:2]:
        term = (item.get("term") or "").strip()
        definition = (item.get("definition") or "").strip()
        if not term or not definition:
            continue
        lines.append(f"- {term}: {definition}")
    if len(lines) <= 1:
        return ""
    block = "\n".join(lines)
    if len(block) > _MAX_GLOSSARY_PROMPT_CHARS:
        block = block[: _MAX_GLOSSARY_PROMPT_CHARS - 3] + "..."
    return block + "\n"
