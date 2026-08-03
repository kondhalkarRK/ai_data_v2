# features/okf_knowledge/__init__.py
"""Open Knowledge Format (OKF) — business document RAG for narratives & policy Q&A."""

__all__ = [
    "get_relevant_context",
    "get_relevant_snippets",
    "reindex_all",
    "indexed_concept_count",
    "bootstrap_business_knowledge",
]


def __getattr__(name: str):
    if name in ("get_relevant_context", "get_relevant_snippets", "reindex_all", "indexed_concept_count"):
        from features.okf_knowledge import okf_retriever as m
        return getattr(m, name)
    if name == "bootstrap_business_knowledge":
        from features.okf_knowledge.okf_bootstrap import bootstrap_business_knowledge
        return bootstrap_business_knowledge
    raise AttributeError(name)
