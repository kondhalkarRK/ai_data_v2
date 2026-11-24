"""
features/rag_query_memory/vector_store.py
ChromaDB persistent vector store wrapper - all calls fail silently.
"""
import streamlit as st

_COLLECTION_QUERY_MEMORY = "query_memory"
_COLLECTION_GLOSSARY = "glossary"
_CHROMA_PATH = "rag_storage/chroma_db"


@st.cache_resource
def get_chroma_client():
    """Return a persistent ChromaDB client (created once per session)."""
    import chromadb
    return chromadb.PersistentClient(path=_CHROMA_PATH)


def get_query_memory_collection():
    """Get or create the query_memory collection; returns None on failure."""
    try:
        client = get_chroma_client()
        return client.get_or_create_collection(_COLLECTION_QUERY_MEMORY)
    except Exception:
        return None


def get_glossary_collection():
    """Get or create the glossary collection; returns None on failure."""
    try:
        client = get_chroma_client()
        return client.get_or_create_collection(_COLLECTION_GLOSSARY)
    except Exception:
        return None


def collection_count(collection) -> int:
    """Return item count for a collection, or 0 on failure."""
    try:
        if collection is None:
            return 0
        return collection.count()
    except Exception:
        return 0


def add_to_collection(collection, doc_id: str, text: str, embedding: list[float], metadata: dict) -> bool:
    """Add one document to a collection; returns False on failure."""
    try:
        if collection is None or not embedding:
            return False
        collection.add(
            ids=[doc_id],
            documents=[text],
            embeddings=[embedding],
            metadatas=[metadata],
        )
        return True
    except Exception:
        return False


def query_collection(collection, embedding: list[float], k: int) -> dict | None:
    """Query a collection by embedding; returns None on failure."""
    try:
        if collection is None or not embedding:
            return None
        count = collection.count()
        if count == 0:
            return None
        return collection.query(
            query_embeddings=[embedding],
            n_results=min(k, count),
        )
    except Exception:
        return None
