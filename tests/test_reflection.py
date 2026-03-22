import pytest
import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock
from nanobot.agent.reflection import ReflectionStore
from nanobot.providers.base import LLMProvider
from nanobot.session.manager import Session

@pytest.fixture
def workspace(tmp_path):
    return tmp_path

@pytest.fixture
def reflection_store(workspace):
    return ReflectionStore(workspace)

def test_add_and_load_reflection(reflection_store, workspace):
    reflection_store.add_reflection("trigger word", "wrong tool", "use correct tool")
    
    # Verify file is written
    file_path = workspace / "memory" / "reflections.json"
    assert file_path.exists()
    
    data = json.loads(file_path.read_text())
    assert len(data["reflections"]) == 1
    assert data["reflections"][0]["trigger"] == "trigger word"
    
    # Verify load
    store2 = ReflectionStore(workspace)
    assert len(store2._reflections) == 1
    assert store2._reflections[0]["failure_reason"] == "wrong tool"

def test_search_reflections(reflection_store):
    reflection_store.add_reflection("generate report", "used read_file instead of ssrs tool", "use ssrs tool")
    reflection_store.add_reflection("send email to boss", "used message tool", "use outlook tool")
    
    # Exact substring
    results = reflection_store.search_reflections("please generate report now")
    assert len(results) == 1
    assert results[0]["trigger"] == "generate report"
    
    # Jaccard overlap (send email)
    results = reflection_store.search_reflections("send an email")
    assert len(results) == 1
    assert results[0]["trigger"] == "send email to boss"

    # No match
    results = reflection_store.search_reflections("random stuff")
    assert len(results) == 0

@pytest.mark.asyncio
async def test_generate_reflection(reflection_store):
    mock_provider = AsyncMock(spec=LLMProvider)
    
    mock_response = MagicMock()
    mock_response.content = '''
    {
        "trigger": "failed task",
        "failure_reason": "bad args",
        "corrective_action": "fix args"
    }
    '''
    mock_provider.chat.return_value = mock_response
    
    session = Session("test_session")
    session.add_message("user", "do the task")
    session.add_message("assistant", "done", tools_used=["bad_tool"])
    
    await reflection_store.generate_reflection(mock_provider, "test_model", session, "this is wrong")
    
    assert len(reflection_store._reflections) == 1
    ref = reflection_store._reflections[0]
    assert ref["trigger"] == "failed task"
    assert ref["failure_reason"] == "bad args"
    assert ref["corrective_action"] == "fix args"
