"""Hybrid Retriever — Dense + BM25 scoring engine.

Shared by match_knowledge() and match_experience() in KnowledgeWorkflow to
eliminate code duplication.  The module provides a single function that
takes a query, a list of candidate items, and optional vector memory, then
returns the best match above a configurable threshold.
"""

from __future__ import annotations

__all__ = ["hybrid_retrieve"]

from typing import Any

from loguru import logger

from nanobot.agent.task_knowledge import tokenize_key


def hybrid_retrieve(
    query: str,
    candidates: list[dict[str, Any]],
    *,
    text_field: str = "key",
    extra_text_field: str | None = "triggers",
    match_key_field: str = "key",
    vector_memory: Any = None,
    vector_source_filter: str = "knowledge",
    threshold: float = 0.6,
    dense_weight: float = 0.7,
    bm25_weight: float = 0.3,
    no_dense_penalty: float = 0.5,
) -> tuple[dict[str, Any] | None, float]:
    """Score candidates using BM25 + Dense vector hybrid retrieval.

    Args:
        query: The search query text.
        candidates: List of candidate dicts to score.
        text_field: Primary field in each candidate to tokenize for BM25.
        extra_text_field: Optional extra field (e.g. "triggers") to append to BM25 text.
            If the field value is a list, items are joined with spaces.
        match_key_field: Field used to look up dense vector scores.
        vector_memory: Optional VectorMemory instance for dense scoring.
        vector_source_filter: Source filter for vector search.
        threshold: Minimum combined score to qualify as a match.
        dense_weight: Weight for the dense score component (0-1).
        bm25_weight: Weight for the BM25 score component (0-1).
        no_dense_penalty: Multiplier applied to BM25 score when no dense score is available.

    Returns:
        Tuple of (best_match_dict_or_None, best_score).
    """
    query_lower = query.lower().strip()
    query_words = tokenize_key(query_lower)
    if not query_words:
        return None, 0.0

    # ── 1. Build BM25 Corpus ──
    corpus_words: list[list[str]] = []
    valid_items: list[dict[str, Any]] = []

    for item in candidates:
        text = item.get(text_field, "").lower().strip()
        if extra_text_field:
            extra = item.get(extra_text_field, [])
            if isinstance(extra, list):
                extra = " ".join(extra)
            text = f"{text} {extra}"
        words = tokenize_key(text)
        if words:
            corpus_words.append(words)
            valid_items.append(item)

    if not valid_items:
        return None, 0.0

    # ── 2. Compute BM25 Scores ──
    bm25_scores = [0.0] * len(valid_items)
    if corpus_words:
        try:
            from rank_bm25 import BM25Okapi
            bm25 = BM25Okapi(corpus_words)
            raw_scores = bm25.get_scores(query_words)
            # Clamp negatives (BM25 can return negative for exact matches
            # in small corpora where IDF→0), then normalize (heuristic max ~5.0)
            bm25_scores = [min(max(s, 0.0) / 5.0, 1.0) for s in raw_scores]
        except ImportError:
            pass

        # Fallback to Jaccard if BM25 produced all zeros (e.g. single-doc corpus)
        if not any(s > 0 for s in bm25_scores):
            for i, t_words in enumerate(corpus_words):
                common = set(query_words) & set(t_words)
                union = set(query_words) | set(t_words)
                bm25_scores[i] = len(common) / len(union) if union else 0.0

    # ── 3. Compute Dense Vector Scores ──
    dense_scores_map: dict[str, float] = {}
    if vector_memory:
        try:
            results = vector_memory.search(
                query=query, top_k=5, source_filter=vector_source_filter,
            )
            for res in results:
                matched = res.get("metadata", {}).get(match_key_field, "")
                score = res.get("score", 0.0)
                if matched:
                    m_lower = matched.lower()
                    if m_lower not in dense_scores_map or score > dense_scores_map[m_lower]:
                        dense_scores_map[m_lower] = score
        except Exception as e:
            logger.warning(f"HybridRetriever: dense search failed: {e}")

    # ── 4. Combine Scores ──
    best_match: dict[str, Any] | None = None
    best_score = 0.0

    for i, item in enumerate(valid_items):
        item_key = item.get(match_key_field, "").lower().strip()
        dense_score = dense_scores_map.get(item_key, 0.0)

        if not dense_score:
            combined = bm25_scores[i] * no_dense_penalty
        else:
            combined = (dense_score * dense_weight) + (bm25_scores[i] * bm25_weight)

        if combined > best_score:
            best_score = combined
            best_match = item

    if best_match and best_score >= threshold:
        return best_match, best_score

    return None, best_score
