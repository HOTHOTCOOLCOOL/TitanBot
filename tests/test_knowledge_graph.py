import pytest
import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock
from nanobot.agent.knowledge_graph import KnowledgeGraph
from nanobot.providers.base import LLMProvider

@pytest.fixture
def workspace(tmp_path):
    return tmp_path

@pytest.fixture
def knowledge_graph(workspace):
    return KnowledgeGraph(workspace)

def test_add_and_load_triple(knowledge_graph, workspace):
    knowledge_graph._add_triple("David", "works for", "Salesforce")
    # Phase 25: _add_triple no longer auto-saves; callers must call _save() explicitly
    knowledge_graph._save()
    
    file_path = workspace / "memory" / "graph.json"
    assert file_path.exists()
    
    data = json.loads(file_path.read_text())
    assert len(data["triples"]) == 1
    assert data["triples"][0]["subject"] == "David"
    assert data["triples"][0]["predicate"] == "works for"
    assert data["triples"][0]["object"] == "Salesforce"
    
    kg2 = KnowledgeGraph(workspace)
    assert len(kg2._triples) == 1
    assert kg2._triples[0]["subject"] == "David"

def test_add_duplicate_triple(knowledge_graph):
    knowledge_graph._add_triple("David", "works for", "Salesforce")
    knowledge_graph._add_triple("David", "WORKS FOR", "salesforce")
    assert len(knowledge_graph._triples) == 1

def test_get_1hop_context(knowledge_graph):
    knowledge_graph._add_triple("David", "works for", "Salesforce")
    knowledge_graph._add_triple("Backend", "uses", "Python")
    knowledge_graph._add_triple("David", "likes", "coffee")
    
    context = knowledge_graph.get_1hop_context("Where does David work?")
    assert "Salesforce" in context
    assert "coffee" in context
    assert "Python" not in context
    
    context2 = knowledge_graph.get_1hop_context("Tell me about backend.")
    assert "Python" in context2
    assert "Salesforce" not in context2

@pytest.mark.asyncio
async def test_extract_triples(knowledge_graph):
    mock_provider = AsyncMock(spec=LLMProvider)
    mock_response = MagicMock()
    mock_response.content = '''
    [
        {"subject": "System", "predicate": "runs on", "object": "Linux"},
        {"subject": "User", "predicate": "prefers", "object": "Dark mode"}
    ]
    '''
    mock_provider.chat.return_value = mock_response
    
    await knowledge_graph.extract_triples(mock_provider, "test_model", "System runs on Linux. User prefers dark mode.")
    
    assert len(knowledge_graph._triples) == 2
    assert knowledge_graph._triples[0]["subject"] == "System"
    assert knowledge_graph._triples[1]["object"] == "Dark mode"
