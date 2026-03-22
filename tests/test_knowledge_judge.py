import pytest
from pathlib import Path
from nanobot.agent.task_knowledge import TaskKnowledgeStore

@pytest.fixture
def temp_workspace(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    return workspace

@pytest.fixture
def knowledge_store(temp_workspace):
    return TaskKnowledgeStore(temp_workspace)

def test_knowledge_judge_retains_good_tasks(knowledge_store):
    knowledge_store.add_task(
        "Good task", "Does good", ["step1"], {}, "Done"
    )
    knowledge_store.record_success("Good task")
    knowledge_store.record_success("Good task")
    
    removed = knowledge_store.run_knowledge_judge(min_confidence=0.3, max_fail_rate=0.7)
    assert removed == 0
    assert knowledge_store.count() == 1

def test_knowledge_judge_discards_high_fail_rate(knowledge_store):
    knowledge_store.add_task(
        "Failing task", "Fails", ["step1"], {}, "Failed"
    )
    knowledge_store.record_failure("Failing task")
    knowledge_store.record_failure("Failing task")
    knowledge_store.record_failure("Failing task")
    knowledge_store.record_failure("Failing task") # 3 fails, 1 success (default) -> 75% fail rate
    
    # max_fail_rate is 0.5, so 0.75 should be discarded
    removed = knowledge_store.run_knowledge_judge(min_confidence=0.3, max_fail_rate=0.5)
    assert removed == 1
    assert knowledge_store.count() == 0

def test_knowledge_judge_discards_low_confidence(knowledge_store):
    knowledge_store.add_task(
        "Low conf task", "Low conf", ["step1"], {}, "Done"
    )
    
    # Manually hack confidence for testing
    task = knowledge_store.find_task("Low conf task")
    task["confidence"] = 0.1
    knowledge_store._save()
    
    removed = knowledge_store.run_knowledge_judge(min_confidence=0.3, max_fail_rate=0.7)
    assert removed == 1
    assert knowledge_store.count() == 0

from unittest.mock import AsyncMock, MagicMock
from nanobot.agent.knowledge_workflow import KnowledgeWorkflow
import pytest

@pytest.fixture
def mock_provider():
    provider = MagicMock()
    mock_response = MagicMock()
    mock_response.content = '''
    {
        "decision": "ADD",
        "triggers": ["test trigger 1", "test trigger 2"],
        "tags": ["test"],
        "anti_patterns": ["do not do this"],
        "confidence": 0.95
    }
    '''
    provider.chat = AsyncMock(return_value=mock_response)
    return provider

@pytest.mark.asyncio
async def test_evaluate_and_structure_knowledge(mock_provider):
    kw = KnowledgeWorkflow(provider=mock_provider, model="test-model")
    
    result = await kw.evaluate_and_structure_knowledge(
        key="test key",
        request="test request",
        steps=[{"tool": "test", "args": {}}],
        result="Success"
    )
    
    assert result["decision"] == "ADD"
    assert "test trigger 1" in result["triggers"]
    assert "test" in result["tags"]
    assert "do not do this" in result["anti_patterns"]
    assert result["confidence"] == 0.95
    
    # Verify the provider was called
    mock_provider.chat.assert_called_once()
    call_args = mock_provider.chat.call_args[1]
    assert "messages" in call_args
    assert "test key" in call_args["messages"][0]["content"]

@pytest.mark.asyncio
async def test_save_to_knowledge_with_judge(mock_provider, temp_workspace):
    # Mock the task_knowledge store
    kw = KnowledgeWorkflow(provider=mock_provider, workspace=temp_workspace)
    kw.knowledge_store = MagicMock()
    
    # Test ADD scenario (no existing key)
    kw.knowledge_store.find_task.return_value = None
    kw.knowledge_store.find_similar_task.return_value = None
    
    success = await kw.save_to_knowledge(
        key="new_key",
        steps=[],
        user_request="some request",
        result_summary="done"
    )
    
    assert success is True
    kw.knowledge_store.add_task.assert_called_once()
    _, kwargs = kw.knowledge_store.add_task.call_args
    assert kwargs["triggers"] == ["test trigger 1", "test trigger 2"]
    assert kwargs["confidence"] == 0.95
