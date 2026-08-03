"""
features/rag_query_memory/query_memory.py
Few-shot query memory via local vector retrieval - no LLM calls.
"""
import hashlib

from features.rag_query_memory import embedder, vector_store

_MAX_PROMPT_CHARS = 600  # ~150 tokens for examples block

# Golden few-shots — overwrite bad truncated/hallucinated examples after cleanup
_GOLDEN_QUERIES = [
    (
        "Which make gained the most units between 2021 and 2025",
        """SELECT make,
  SUM(CASE WHEN CAST(strftime('%Y', sales_date) AS INTEGER) = 2021 THEN order_qty ELSE 0 END) AS units_2021,
  SUM(CASE WHEN CAST(strftime('%Y', sales_date) AS INTEGER) = 2025 THEN order_qty ELSE 0 END) AS units_2025,
  (SUM(CASE WHEN CAST(strftime('%Y', sales_date) AS INTEGER) = 2025 THEN order_qty ELSE 0 END)
   - SUM(CASE WHEN CAST(strftime('%Y', sales_date) AS INTEGER) = 2021 THEN order_qty ELSE 0 END)) AS units_gained
FROM df
WHERE CAST(strftime('%Y', sales_date) AS INTEGER) IN (2021, 2025)
GROUP BY make
ORDER BY units_gained DESC
LIMIT 10""",
    ),
    (
        "Compare units sold by make for 2019 versus 2020",
        """SELECT make,
  SUM(CASE WHEN CAST(strftime('%Y', sales_date) AS INTEGER) = 2019 THEN order_qty ELSE 0 END) AS units_2019,
  SUM(CASE WHEN CAST(strftime('%Y', sales_date) AS INTEGER) = 2020 THEN order_qty ELSE 0 END) AS units_2020,
  (SUM(CASE WHEN CAST(strftime('%Y', sales_date) AS INTEGER) = 2020 THEN order_qty ELSE 0 END)
   - SUM(CASE WHEN CAST(strftime('%Y', sales_date) AS INTEGER) = 2019 THEN order_qty ELSE 0 END)) AS units_diff
FROM df
WHERE CAST(strftime('%Y', sales_date) AS INTEGER) IN (2019, 2020)
GROUP BY make
ORDER BY units_diff DESC
LIMIT 10""",
    ),
]


def seed_golden_queries_once() -> None:
    """Upsert certified comparison SQL examples into query memory."""
    try:
        for question, sql in _GOLDEN_QUERIES:
            store_successful_query(question, sql, max_len=900)
    except Exception:
        pass


def store_successful_query(question: str, sql: str, max_len: int = 700) -> None:
    """Persist a successful question/SQL pair for future few-shot retrieval."""
    try:
        if not question or not sql:
            return
        if sql.strip().startswith("-- served from materialized view --"):
            return
        sql_trunc = embedder.truncate_text(sql, max_len)
        embedding = embedder.embed_text(question)
        if not embedding:
            return
        collection = vector_store.get_query_memory_collection()
        doc_id = hashlib.sha256(f"{question}|{sql_trunc}".encode("utf-8")).hexdigest()[:32]
        vector_store.add_to_collection(
            collection,
            doc_id,
            question,
            embedding,
            {"question": question, "sql": sql_trunc},
        )
    except Exception:
        pass


def retrieve_similar_queries(question: str, k: int = 2) -> list[dict]:
    """Return up to k similar past queries; empty list on any failure."""
    try:
        # LOCAL EMBEDDING - ZERO LLM COST
        embedding = embedder.embed_text(question)
        if not embedding:
            return []
        collection = vector_store.get_query_memory_collection()
        results = vector_store.query_collection(collection, embedding, k)
        if not results:
            return []
        documents = results.get("documents") or [[]]
        metadatas = results.get("metadatas") or [[]]
        if not documents or not documents[0]:
            return []
        examples = []
        for doc, meta in zip(documents[0], metadatas[0]):
            meta = meta or {}
            examples.append({
                "question": meta.get("question") or doc or "",
                "sql": embedder.truncate_text(meta.get("sql") or "", 700),
            })
        return examples[:k]
    except Exception:
        return []


def format_examples_for_prompt(examples: list[dict]) -> str:
    """Format few-shot examples for prompt injection; empty string if none."""
    if not examples:
        return ""
    lines = ["FEW-SHOT EXAMPLES:"]
    for i, ex in enumerate(examples[:2], 1):
        q = (ex.get("question") or "").strip()
        s = (ex.get("sql") or "").strip()
        if not q or not s:
            continue
        lines.append(f"Q{i}: {q}")
        lines.append(f"SQL{i}: {s}")
    if len(lines) <= 1:
        return ""
    block = "\n".join(lines)
    if len(block) > _MAX_PROMPT_CHARS:
        block = block[: _MAX_PROMPT_CHARS - 3] + "..."
    return block + "\n"
