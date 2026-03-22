import pytest
from unittest.mock import AsyncMock, MagicMock
from pathlib import Path

from nanobot.agent.knowledge_workflow import KnowledgeWorkflow
from nanobot.agent.task_knowledge import TaskKnowledgeStore
from nanobot.bus.events import InboundMessage
from nanobot.session.manager import Session


@pytest.fixture
def mock_provider():
    provider = MagicMock()
    # Provide an async chat method that returns a mock response
    async def mock_chat(messages, model, temperature, max_tokens):
        response = MagicMock()
        # Simple routing based on the prompt content
        prompt = messages[0]["content"]
        if "Extract a concise task description" in prompt:
            # For extract_key
            if "Recent conversation history" in prompt:
                response.content = "extracted_with_history"
            else:
                response.content = "extracted_without_history"
        elif "Adapt this generic workflow" in prompt:
            # For adapt_knowledge
            if "Recent conversation history" in prompt:
                response.content = "adapted_with_history"
            else:
                response.content = "adapted_without_history"
        else:
            response.content = "mock_response"
        return response
    
    provider.chat = mock_chat
    return provider


@pytest.fixture
def kw_with_mock(mock_provider):
    return KnowledgeWorkflow(provider=mock_provider, model="mock-model", workspace=Path("/tmp/mock"))


class TestRetrievalEnhancement:
    @pytest.mark.asyncio
    async def test_extract_key_with_history(self, kw_with_mock):
        """Test that extract_key includes history in the LLM prompt."""
        history = [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi"}
        ]
        key = await kw_with_mock.extract_key("do it again", history=history)
        # Our mock returns 'extracted_with_history' if the prompt contains history
        assert key == "extracted_with_history"

    @pytest.mark.asyncio
    async def test_extract_key_without_history(self, kw_with_mock):
        """Test that extract_key works without history."""
        key = await kw_with_mock.extract_key("do this task")
        assert key == "extracted_without_history"

    @pytest.mark.asyncio
    async def test_adapt_knowledge_with_history(self, kw_with_mock):
        """Test that adapt_knowledge includes history when rewriting."""
        match = {
            "key": "test_task",
            "steps": [{"tool": "test_tool", "args": {"param": "val"}}],
            "result_summary": "Done"
        }
        history = [
            {"role": "user", "content": "Some context"}
        ]
        adapted = await kw_with_mock.adapt_knowledge(match, current_request="do it", history=history)
        
        # It prepends '## Contextual Reference: Adapted from ...'
        assert "Contextual Reference" in adapted
        assert "adapted_with_history" in adapted

    @pytest.mark.asyncio
    async def test_adapt_knowledge_without_history(self, kw_with_mock):
        """Test that adapt_knowledge works without history."""
        match = {
            "key": "test_task",
            "steps": [{"tool": "test_tool", "args": {"param": "val"}}],
            "result_summary": "Done"
        }
        adapted = await kw_with_mock.adapt_knowledge(match, current_request="do it", history=None)
        
        assert "Contextual Reference" in adapted
        assert "adapted_without_history" in adapted
        
    @pytest.mark.asyncio
    async def test_adapt_knowledge_fallback(self):
        """Test that adapt_knowledge falls back to static prompt if no provider exists."""
        kw_no_provider = KnowledgeWorkflow(provider=None, model=None, workspace=None)
        match = {
            "key": "test_fallback",
            "steps": [{"tool": "fallback_tool", "args": {}}],
        }
        adapted = await kw_no_provider.adapt_knowledge(match, current_request="request")
        # Should fallback to format_few_shot_prompt which outputs '## Reference: Previously successful execution of ...'
        assert "Reference: Previously successful execution" in adapted
        assert "test_fallback" in adapted
