"""
features/rag_query_memory/embedder.py
Local deterministic embeddings with an optional Hugging Face override.
"""
import math
import os
import re

import streamlit as st

_USE_HF_EMBEDDINGS = os.getenv("ASKDB_USE_HF_EMBEDDINGS", "0").strip().lower() in {
    "1",
    "true",
    "yes",
    "on",
}


def _fallback_embedding(text: str) -> list[float]:
    """Simple local embedding that avoids any external model download."""
    cleaned = (text or "").lower()
    tokens = re.findall(r"[a-z0-9]+", cleaned)
    if not tokens:
        return []

    dims = 128
    vec = [0.0] * dims
    for index, token in enumerate(tokens[:20]):
        bucket = abs(hash(token)) % dims
        vec[bucket] += 1.0 / (1 + index)

    norm = math.sqrt(sum(v * v for v in vec))
    if norm == 0:
        return vec
    return [v / norm for v in vec]


@st.cache_resource
def get_embedder():
    """Return a Hugging Face model only when explicitly enabled."""
    if not _USE_HF_EMBEDDINGS:
        return None
    from sentence_transformers import SentenceTransformer
    return SentenceTransformer("all-MiniLM-L6-v2")


def embed_text(text: str) -> list[float]:
    """Embed a single text string; returns a local fallback vector on failure."""
    try:
        if not text or not text.strip():
            return []
        model = get_embedder()
        if model is None:
            return _fallback_embedding(text.strip())
        vector = model.encode(text.strip())
        return vector.tolist()
    except Exception:
        return _fallback_embedding(text or "")


def truncate_text(text: str, max_len: int) -> str:
    """Truncate text with ellipsis when longer than max_len."""
    text = (text or "").strip()
    if len(text) <= max_len:
        return text
    return text[: max_len - 3] + "..."
