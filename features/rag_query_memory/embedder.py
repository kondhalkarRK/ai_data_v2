"""
features/rag_query_memory/embedder.py
Local sentence-transformer embeddings - no external API calls.
"""
import streamlit as st


@st.cache_resource
def get_embedder():
    """Load all-MiniLM-L6-v2 once per Streamlit session."""
    from sentence_transformers import SentenceTransformer
    return SentenceTransformer("all-MiniLM-L6-v2")


def embed_text(text: str) -> list[float]:
    """Embed a single text string; returns empty list on failure."""
    try:
        if not text or not text.strip():
            return []
        model = get_embedder()
        vector = model.encode(text.strip())
        return vector.tolist()
    except Exception:
        return []
