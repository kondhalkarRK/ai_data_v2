# semantic/semantic_vector_search.py
# Lightweight in-memory semantic vector search over semantic metadata.
# Uses sentence-transformers for embeddings — NO document RAG.
# Capgemini AI Data Platform V10

from __future__ import annotations

import os
import re
import numpy as np
from typing import Optional

_USE_HF_EMBEDDINGS = os.getenv("ASKDB_USE_HF_EMBEDDINGS", "0").strip().lower() in {
    "1",
    "true",
    "yes",
    "on",
}

# ── Try to import sentence-transformers ─────────────────────────
# Falls back to TF-IDF cosine similarity if not available.
# Default is OFF to avoid external model downloads during app startup.
try:
    if _USE_HF_EMBEDDINGS:
        from sentence_transformers import SentenceTransformer
        _ST_AVAILABLE = True
    else:
        _ST_AVAILABLE = False
except ImportError:
    _ST_AVAILABLE = False

from semantic.semantic_loader import get_semantic_loader


# ════════════════════════════════════════════════════════════════
# TF-IDF FALLBACK VECTORIZER
# Used when sentence-transformers is not installed
# ════════════════════════════════════════════════════════════════

class _TFIDFFallback:
    """
    Lightweight character-level TF-IDF vectorizer.
    Used as fallback when sentence-transformers is unavailable.
    Provides good synonym matching for short business terms.
    """

    def __init__(self):
        self._vocab:   dict[str, int] = {}
        self._idf:     np.ndarray     = np.array([])
        self._fitted:  bool           = False

    def _tokenize(self, text: str) -> list[str]:
        """Tokenize into unigrams + bigrams for richer matching."""
        text  = text.lower().strip()
        words = re.findall(r'[a-z0-9]+', text)
        bigrams = [
            f"{words[i]}_{words[i+1]}"
            for i in range(len(words) - 1)
        ]
        return words + bigrams

    def fit(self, texts: list[str]) -> None:
        """Build vocabulary and IDF weights from corpus."""
        tokenized = [self._tokenize(t) for t in texts]

        # Build vocabulary
        vocab: dict[str, int] = {}
        for tokens in tokenized:
            for tok in tokens:
                if tok not in vocab:
                    vocab[tok] = len(vocab)
        self._vocab = vocab

        # Compute IDF
        n_docs  = len(texts)
        idf     = np.zeros(len(vocab))
        for tokens in tokenized:
            unique_toks = set(tokens)
            for tok in unique_toks:
                if tok in vocab:
                    idf[vocab[tok]] += 1

        # Smooth IDF to avoid division by zero
        self._idf    = np.log((n_docs + 1) / (idf + 1)) + 1.0
        self._fitted = True

    def encode(self, texts: list[str]) -> np.ndarray:
        """Encode list of texts into TF-IDF vectors."""
        if not self._fitted:
            raise RuntimeError("TFIDFFallback must be fitted before encoding.")

        vectors = np.zeros((len(texts), len(self._vocab)))
        for i, text in enumerate(texts):
            tokens = self._tokenize(text)
            tf: dict[str, int] = {}
            for tok in tokens:
                tf[tok] = tf.get(tok, 0) + 1
            for tok, count in tf.items():
                if tok in self._vocab:
                    idx = self._vocab[tok]
                    vectors[i, idx] = (count / max(len(tokens), 1)) * self._idf[idx]

            # L2 normalise
            norm = np.linalg.norm(vectors[i])
            if norm > 0:
                vectors[i] /= norm

        return vectors


# ════════════════════════════════════════════════════════════════
# SEMANTIC VECTOR SEARCH ENGINE
# ════════════════════════════════════════════════════════════════

class SemanticVectorSearch:
    """
    In-memory semantic vector search over semantic metadata.

    Builds embeddings for:
    - Measure names and synonyms
    - Dimension names and synonyms
    - Business glossary terms and synonyms
    - Table attribute display names

    Resolves user query terms to canonical semantic concepts
    before SQL generation.

    Example:
        "top sellers by turnover"
        -> sellers   resolved to: Salesperson (dimension)
        -> turnover  resolved to: Revenue (measure)
    """

    # Sentence-transformer model — small & fast
    _ST_MODEL_NAME = "all-MiniLM-L6-v2"

    def __init__(self):
        self._terms:      list[dict]         = []
        self._texts:      list[str]          = []
        self._embeddings: Optional[np.ndarray] = None
        self._model                          = None
        self._fallback: Optional[_TFIDFFallback] = None
        self._built:    bool                 = False

    def build_index(self) -> None:
        """
        Build the semantic vector index from YAML metadata.
        Called once at startup.
        """
        loader = get_semantic_loader()
        self._terms = loader.get_all_semantic_terms()
        self._texts = [t["text"].lower().strip() for t in self._terms]

        if not self._texts:
            return

        # ── Try sentence-transformers first ─────────────────────
        if _ST_AVAILABLE:
            try:
                self._model      = SentenceTransformer(self._ST_MODEL_NAME)
                self._embeddings = self._model.encode(
                    self._texts,
                    convert_to_numpy=True,
                    show_progress_bar=False,
                    normalize_embeddings=True,
                )
                self._built = True
                return
            except Exception:
                pass

        # ── Fallback to TF-IDF ──────────────────────────────────
        self._fallback = _TFIDFFallback()
        self._fallback.fit(self._texts)
        self._embeddings = self._fallback.encode(self._texts)
        self._built = True

    def _encode_query(self, query: str) -> np.ndarray:
        """Encode a single query string to a vector."""
        query = query.lower().strip()

        if _ST_AVAILABLE and self._model is not None:
            vec = self._model.encode(
                [query],
                convert_to_numpy=True,
                show_progress_bar=False,
                normalize_embeddings=True,
            )
            return vec[0]

        if self._fallback is not None:
            return self._fallback.encode([query])[0]

        raise RuntimeError("No encoder available.")

    def _cosine_similarity(
        self,
        query_vec: np.ndarray,
        matrix:    np.ndarray,
    ) -> np.ndarray:
        """Compute cosine similarity between query and all index vectors."""
        # Vectors are already L2 normalised
        # cosine_sim = dot product when normalised
        scores = matrix @ query_vec
        return scores

    def search(
        self,
        query_term: str,
        top_k:      int   = 3,
        threshold:  float = 0.30,
    ) -> list[dict]:
        """
        Search semantic index for closest matches to a query term.

        Args:
            query_term: Single word or phrase to resolve
            top_k:      Number of top results to return
            threshold:  Minimum similarity score (0.0 - 1.0)

        Returns:
            List of dicts with keys:
                text, canonical, type, key, score
        """
        if not self._built or self._embeddings is None:
            return []

        try:
            query_vec = self._encode_query(query_term)
            scores    = self._cosine_similarity(query_vec, self._embeddings)

            # Get top_k indices above threshold
            top_indices = np.argsort(scores)[::-1][:top_k * 3]

            results = []
            seen_canonical: set[str] = set()

            for idx in top_indices:
                score = float(scores[idx])
                if score < threshold:
                    continue
                term = self._terms[idx]
                canonical = term["canonical"]

                # Deduplicate by canonical concept
                if canonical in seen_canonical:
                    continue
                seen_canonical.add(canonical)

                results.append({
                    "text":      term["text"],
                    "canonical": canonical,
                    "type":      term["type"],
                    "key":       term["key"],
                    "score":     round(score, 4),
                })

                if len(results) >= top_k:
                    break

            return results

        except Exception:
            return []

    def resolve_query_terms(self, question: str) -> dict:
        """
        Tokenize a natural language question and resolve
        each meaningful term to its semantic concept.

        Args:
            question: Full natural language question

        Returns:
            dict with keys:
                resolved_measures   : list of canonical measure names
                resolved_dimensions : list of canonical dimension names
                resolved_attributes : list of canonical attribute names
                resolution_map      : {original_term -> canonical_name}
                all_resolutions     : full list of resolution dicts
        """
        if not self._built:
            return {
                "resolved_measures":   [],
                "resolved_dimensions": [],
                "resolved_attributes": [],
                "resolution_map":      {},
                "all_resolutions":     [],
            }

        # ── Tokenize question into meaningful terms ──────────────
        # Extract individual words AND multi-word phrases (bigrams)
        words   = re.findall(r'[a-zA-Z0-9]+', question.lower())

        # Filter out stop words
        stop_words = {
            "the", "a", "an", "by", "for", "of", "in", "on",
            "at", "to", "and", "or", "is", "are", "was", "were",
            "what", "which", "who", "how", "show", "me", "give",
            "list", "get", "find", "top", "bottom", "best", "worst",
            "highest", "lowest", "per", "each", "all", "with",
            "from", "where", "when", "between", "vs", "versus",
            "compare", "total", "number", "count", "do", "did",
            "their", "my", "our", "this", "that", "than", "then",
        }

        # Build search tokens (unigrams + bigrams)
        filtered_words = [w for w in words if w not in stop_words and len(w) > 2]
        bigrams        = [
            f"{filtered_words[i]} {filtered_words[i+1]}"
            for i in range(len(filtered_words) - 1)
        ]
        search_tokens  = filtered_words + bigrams

        # ── Search each token ────────────────────────────────────
        resolved_measures:   list[str]  = []
        resolved_dimensions: list[str]  = []
        resolved_attributes: list[str]  = []
        resolution_map:      dict       = {}
        all_resolutions:     list[dict] = []

        seen_canonical: set[str] = set()

        for token in search_tokens:
            results = self.search(token, top_k=1, threshold=0.35)
            if not results:
                continue

            best    = results[0]
            canon   = best["canonical"]
            r_type  = best["type"]

            if canon in seen_canonical:
                continue
            seen_canonical.add(canon)

            resolution_map[token] = canon
            all_resolutions.append({
                "original": token,
                **best,
            })

            if r_type == "measure":
                if canon not in resolved_measures:
                    resolved_measures.append(canon)
            elif r_type == "dimension":
                if canon not in resolved_dimensions:
                    resolved_dimensions.append(canon)
            elif r_type == "attribute":
                if canon not in resolved_attributes:
                    resolved_attributes.append(canon)
            elif r_type == "glossary":
                # Map glossary term to measure or dimension
                loader = get_semantic_loader()
                glossary = loader.get_glossary()
                term_data = glossary.get(canon, {})
                if "maps_to_measure" in term_data:
                    measures = loader.get_measures()
                    measure_key = term_data["maps_to_measure"]
                    if measure_key in measures:
                        display = measures[measure_key].get(
                            "display_name", measure_key
                        )
                        if display not in resolved_measures:
                            resolved_measures.append(display)
                elif "maps_to_dimension" in term_data:
                    dims = loader.get_dimensions()
                    dim_key = term_data["maps_to_dimension"]
                    if dim_key in dims:
                        display = dims[dim_key].get(
                            "display_name", dim_key
                        )
                        if display not in resolved_dimensions:
                            resolved_dimensions.append(display)

        return {
            "resolved_measures":   resolved_measures,
            "resolved_dimensions": resolved_dimensions,
            "resolved_attributes": resolved_attributes,
            "resolution_map":      resolution_map,
            "all_resolutions":     all_resolutions,
        }


# ── Module-level singleton ───────────────────────────────────────
_search_instance: SemanticVectorSearch | None = None


def get_vector_search() -> SemanticVectorSearch:
    """
    Returns singleton SemanticVectorSearch instance.
    Builds index on first call.
    """
    global _search_instance
    if _search_instance is None:
        _search_instance = SemanticVectorSearch()
        _search_instance.build_index()
    return _search_instance