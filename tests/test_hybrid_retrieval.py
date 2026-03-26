from unittest.mock import MagicMock
from nanobot.agent.knowledge_workflow import KnowledgeWorkflow
from nanobot.agent.hybrid_retriever import hybrid_retrieve

def test_hybrid_match_knowledge_no_dense():
    """Test BM25/Jaccard fallback when no dense vector scores are available.
    
    Note: We call hybrid_retrieve() directly because match_knowledge()
    has earlier passes (exact/substring) that short-circuit before
    reaching hybrid retrieval. The no_dense_penalty (0.5) halves
    Jaccard scores, so we use a lower threshold to match real behavior.
    """
    # Task 1 matches the key well via word overlap
    task1 = {"key": "test task one", "triggers": ["trigger one"]}
    # Task 2 matches partially
    task2 = {"key": "completely different", "triggers": ["test"]}
    
    # Jaccard for task1: query_words=[test,task,one,slightly]
    #   task1 words=[test,task,one,trigger] → common=3, union=5 → 0.6
    #   After no_dense_penalty (×0.5) → 0.30
    # So threshold must be <= 0.30 to match without dense scores
    best, score = hybrid_retrieve(
        query="test task one slightly",
        candidates=[task1, task2],
        text_field="key",
        extra_text_field="triggers",
        threshold=0.25,  # Accounts for no_dense_penalty=0.5 halving scores
    )
    
    assert best is not None, "Should fall back to BM25/Jaccard and match task1"
    assert best["key"] == task1["key"]
    assert score > 0.0


def test_hybrid_match_knowledge_with_dense():
    # Provide a mock vector memory
    mock_vector = MagicMock()
    # It returns dense search results
    mock_vector.search.return_value = [
        {"metadata": {"key": "very unique task"}, "score": 0.9}
    ]
    
    kw = KnowledgeWorkflow(vector_memory=mock_vector)
    kw.knowledge_store = MagicMock()
    
    task1 = {"key": "standard task"} 
    task2 = {"key": "very unique task"} # matches semantically but not exactly lexically
    kw.knowledge_store.get_all_tasks.return_value = [task1, task2]
    kw.knowledge_store.find_task.return_value = task2
    
    # Query has NO word overlap to bypass Pass 1, Pass 2, and Pass 3 BM25
    match = kw.match_knowledge("completely different request but semantically similar")
    
    # Wait, the hybrid logic iterates over `get_all_tasks`. BM25 will score 0.
    # Dense will score 0.9 for "very unique task".
    # Combined = 0.9 * 0.7 = 0.63 > 0.6
    assert match is not None
    assert match == task2
