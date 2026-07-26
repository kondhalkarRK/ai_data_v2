"""
features/vector_schema_retrieval/schema_indexer.py
Index column descriptions into ChromaDB for vector-based schema retrieval.
Uses shared local embedder and Chroma client - no LLM calls.
"""
import pandas as pd

from features.rag_query_memory import embedder
from features.rag_query_memory.vector_store import get_chroma_client

_COLLECTION_SCHEMA_CONTEXT = "schema_context"


def _get_schema_collection():
    """Get or create the schema_context collection; returns None on failure."""
    try:
        client = get_chroma_client()
        return client.get_or_create_collection(_COLLECTION_SCHEMA_CONTEXT)
    except Exception:
        return None


def _column_description(col: str, series: pd.Series) -> str:
    """Build one short description line for a column."""
    s = series
    nn = s.notna().sum()
    if pd.api.types.is_numeric_dtype(s):
        mn = round(float(s.min()), 2) if nn else "N/A"
        mx = round(float(s.max()), 2) if nn else "N/A"
        return f"{col} ({s.dtype}): range=[{mn},{mx}]"
    if pd.api.types.is_datetime64_any_dtype(s):
        mn = str(s.min())[:10] if nn else "N/A"
        mx = str(s.max())[:10] if nn else "N/A"
        return f"{col} (date): range=[{mn},{mx}]"
    uniq = s.nunique()
    top = s.dropna().value_counts().head(5).index.tolist()
    return f"{col} (text,{uniq} unique): top_values={top}"


def index_schema_columns(df: pd.DataFrame, table_name: str = "df") -> None:
    """Upsert column descriptions into schema_context when df has >25 columns."""
    try:
        if df is None or df.empty or df.shape[1] <= 25:
            return
        collection = _get_schema_collection()
        if collection is None:
            return
        ids, documents, embeddings, metadatas = [], [], [], []
        for col in df.columns:
            desc = _column_description(col, df[col])
            embedding = embedder.embed_text(desc)
            if not embedding:
                continue
            ids.append(f"{table_name}::{col}")
            documents.append(desc)
            embeddings.append(embedding)
            metadatas.append({"column": col, "table_name": table_name})
        if ids:
            collection.upsert(
                ids=ids,
                documents=documents,
                embeddings=embeddings,
                metadatas=metadatas,
            )
    except Exception:
        pass
