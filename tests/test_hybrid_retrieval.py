from unittest.mock import MagicMock
from nanobot.agent.knowledge_workflow import KnowledgeWorkflow

def test_hybrid_match_knowledge_no_dense():
    kw = KnowledgeWorkflow()
    # Mock store
    kw.knowledge_store = MagicMock()
    
    # Task 1 matches the key exactly
    task1 = {"key": "test task one", "triggers": ["trigger one"]}
    # Task 2 matches partially
    task2 = {"key": "completely different", "triggers": ["test"]}
    
    kw.knowledge_store.get_all_tasks.return_value = [task1, task2]
    
    # To pass Jaccard threshold (>= 0.6), intersection / union must be >= 0.6
    # "test task one" -> [test, task, one]
    # "test task one slightly" -> [test, task, one, slightly]
    # Union=4, Common=3 -> Jaccard = 0.75 > 0.6
    match = kw.match_knowledge("test task one slightly")
    
    # "test task one" is a strong match.
    assert match is not None, "Should fall back to BM25/Jaccard and match task1"
    assert match == task1


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
