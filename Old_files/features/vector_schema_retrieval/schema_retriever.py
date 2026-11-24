"""
features/vector_schema_retrieval/schema_retriever.py
Retrieve question-relevant columns via local embedding search.
Falls back to full column list on any failure - no LLM calls.
"""
import pandas as pd

from core.schema_builder import build_rich_schema
from features.rag_query_memory import embedder
from features.rag_query_memory.vector_store import query_collection
from features.vector_schema_retrieval.schema_indexer import get_schema_collection


def retrieve_relevant_columns(question: str, all_columns: list[str], k: int = 12) -> list[str]:
    """Return up to k columns relevant to the question; full list on failure."""
    try:
        # LOCAL EMBEDDING - ZERO LLM COST
        if not all_columns:
            return all_columns
        embedding = embedder.embed_text(question)
        if not embedding:
            return all_columns
        collection = get_schema_collection()
        if collection is None:
            return all_columns
        if collection.count() == 0:
            return all_columns
        results = query_collection(collection, embedding, k)
        if not results:
            return all_columns
        metadatas = results.get("metadatas") or [[]]
        if not metadatas or not metadatas[0]:
            return all_columns
        col_set = set(all_columns)
        relevant = []
        for meta in metadatas[0]:
            col = (meta or {}).get("column", "")
            if col in col_set and col not in relevant:
                relevant.append(col)
        if not relevant:
            return all_columns
        return relevant[:k]
    except Exception:
        return all_columns


def build_trimmed_schema_text(df: pd.DataFrame, relevant_columns: list[str]) -> str:
    """Build schema text for a column subset using shared build_rich_schema logic."""
    return build_rich_schema(df, columns_subset=relevant_columns)
