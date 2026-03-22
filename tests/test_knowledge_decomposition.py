"""Tests for the decomposed knowledge workflow modules.

Tests key_extractor and knowledge_judge as standalone modules,
plus verifies KnowledgeWorkflow facade delegation is correct.
"""

import pytest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

from nanobot.agent.key_extractor import extract_key, fallback_key
from nanobot.agent import knowledge_judge as kj
from nanobot.agent.knowledge_workflow import KnowledgeWorkflow
from nanobot.agent.task_knowledge import TaskKnowledgeStore


# ── Fixtures ──


@pytest.fixture
def tmp_workspace(tmp_path: Path) -> Path:
    """Create a temporary workspace with knowledge store."""
    (tmp_path / "memory").mkdir()
    return tmp_path


@pytest.fixture
def knowledge_store(tmp_workspace: Path) -> TaskKnowledgeStore:
    """Create a TaskKnowledgeStore."""
    return TaskKnowledgeStore(tmp_workspace)


@pytest.fixture
def kw(tmp_workspace: Path) -> KnowledgeWorkflow:
    """Create a KnowledgeWorkflow with no LLM provider."""
    return KnowledgeWorkflow(provider=None, model=None, workspace=tmp_workspace)


# ── key_extractor tests ──


class TestKeyExtractor:
    @pytest.mark.asyncio
    async def test_fallback_key_short_english(self):
        """Short English text returned as-is."""
        result = await extract_key("Hello world")
        assert result == "Hello world"

    @pytest.mark.asyncio
    async def test_fallback_key_chinese_truncation(self):
        """Chinese text is truncated to 50 chars."""
        long_cn = "分析" * 30  # 60 chars
        result = await extract_key(long_cn)
        assert len(result) <= 50

    @pytest.mark.asyncio
    async def test_fallback_key_english_truncation(self):
        """English text is truncated to 200 chars."""
        long_en = "analyze " * 30
        result = await extract_key(long_en)
        assert len(result) <= 200

    def test_fallback_key_function_directly(self):
        """Direct call to fallback_key works."""
        assert fallback_key("hello") == "hello"
        assert len(fallback_key("分" * 60)) <= 50

    @pytest.mark.asyncio
    async def test_extract_key_with_provider(self):
        """When provider is available, LLM is called."""
        mock_provider = AsyncMock()
        mock_response = MagicMock()
        mock_response.content = "search weather"
        mock_provider.chat.return_value = mock_response

        result = await extract_key("help me search for today's weather", provider=mock_provider, model="test")
        assert result == "search weather"
        mock_provider.chat.assert_called_once()

    @pytest.mark.asyncio
    async def test_extract_key_provider_error_fallback(self):
        """Falls back to truncation when LLM fails."""
        mock_provider = AsyncMock()
        mock_provider.chat.side_effect = Exception("LLM error")

        result = await extract_key("hello world", provider=mock_provider)
        assert result == "hello world"

    @pytest.mark.asyncio
    async def test_extract_key_with_history(self):
        """History context is included in prompt when provided."""
        mock_provider = AsyncMock()
        mock_response = MagicMock()
        mock_response.content = "weather query"
        mock_provider.chat.return_value = mock_response

        history = [
            {"role": "user", "content": "what's the weather?"},
            {"role": "assistant", "content": "It's sunny."},
        ]
        result = await extract_key("how about tomorrow?", provider=mock_provider, history=history)
        assert result == "weather query"

        # Verify history was included in the prompt
        call_args = mock_provider.chat.call_args
        messages = call_args[1].get("messages") or call_args[0][0]
        prompt_content = messages[0]["content"]
        assert "what's the weather?" in prompt_content


# ── knowledge_judge tests ──


class TestKnowledgeJudge:
    @pytest.mark.asyncio
    async def test_evaluate_no_provider_returns_defaults(self):
        """Without provider, returns default ADD decision."""
        result = await kj.evaluate_and_structure_knowledge(
            key="test", request="test req", steps=[], result="ok",
        )
        assert result["decision"] == "ADD"
        assert result["confidence"] == 0.8
        assert result["triggers"] == ["test"]

    @pytest.mark.asyncio
    async def test_evaluate_with_provider(self):
        """With provider, LLM is called and JSON parsed."""
        mock_provider = AsyncMock()
        mock_response = MagicMock()
        mock_response.content = '{"decision": "MERGE", "triggers": ["a"], "tags": ["b"], "anti_patterns": [], "confidence": 0.95}'
        mock_provider.chat.return_value = mock_response

        result = await kj.evaluate_and_structure_knowledge(
            key="test", request="test req", steps=[], result="ok",
            provider=mock_provider, model="test",
        )
        assert result["decision"] == "MERGE"
        assert result["confidence"] == 0.95

    @pytest.mark.asyncio
    async def test_save_new_task(self, knowledge_store: TaskKnowledgeStore):
        """Save a brand new task to knowledge base."""
        result = await kj.save_to_knowledge(
            key="new_task",
            steps=[{"tool": "exec", "args": {"cmd": "ls"}}],
            user_request="list files",
            knowledge_store=knowledge_store,
            result_summary="Listed files",
        )
        assert result is True
        found = knowledge_store.find_task("new_task")
        assert found is not None

    @pytest.mark.asyncio
    async def test_save_without_store_returns_false(self):
        """Returns False when no store available."""
        result = await kj.save_to_knowledge(
            key="anything", steps=[], user_request="test",
            knowledge_store=None,
        )
        assert result is False

    @pytest.mark.asyncio
    async def test_save_merges_existing(self, knowledge_store: TaskKnowledgeStore):
        """Saving with an existing key merges into that entry."""
        knowledge_store.add_task(
            key="existing_task",
            description="test",
            steps=[{"tool": "a"}],
            params={},
            result_summary="v1",
        )
        result = await kj.save_to_knowledge(
            key="existing_task",
            steps=[{"tool": "b"}],
            user_request="update task",
            knowledge_store=knowledge_store,
            result_summary="v2",
        )
        assert result is True

    @pytest.mark.asyncio
    async def test_adapt_no_provider_returns_generic(self):
        """Without provider, returns generic few-shot prompt."""
        match = {
            "key": "test_task",
            "steps": [{"tool": "exec"}],
            "last_steps_detail": [],
            "success_count": 5,
            "use_count": 10,
        }
        result = await kj.adapt_knowledge(match=match, current_request="do something")
        assert "test_task" in result

    @pytest.mark.asyncio
    async def test_adapt_with_provider(self):
        """With provider, LLM adapts the workflow."""
        mock_provider = AsyncMock()
        mock_response = MagicMock()
        mock_response.content = "1. Run exec with new params"
        mock_provider.chat.return_value = mock_response

        match = {
            "key": "test_task",
            "steps": [{"tool": "exec"}],
            "last_steps_detail": [{"tool": "exec", "args": {"cmd": "ls"}, "result": "ok"}],
            "result_summary": "done",
            "success_count": 5,
            "use_count": 10,
        }
        result = await kj.adapt_knowledge(
            match=match, current_request="run with different params",
            provider=mock_provider, model="test",
        )
        assert "Adapted from" in result


# ── Facade delegation tests ──


class TestFacadeDelegation:
    @pytest.mark.asyncio
    async def test_facade_extract_key_delegates(self, kw: KnowledgeWorkflow):
        """KnowledgeWorkflow.extract_key delegates to key_extractor."""
        result = await kw.extract_key("hello world")
        assert result == "hello world"

    @pytest.mark.asyncio
    async def test_facade_save_to_knowledge_delegates(self, kw: KnowledgeWorkflow):
        """KnowledgeWorkflow.save_to_knowledge delegates to knowledge_judge."""
        result = await kw.save_to_knowledge(
            key="facade_test",
            steps=[{"tool": "test"}],
            user_request="test request",
            result_summary="ok",
        )
        assert result is True
        match = kw.match_knowledge("facade_test")
        assert match is not None

    @pytest.mark.asyncio
    async def test_facade_adapt_knowledge_delegates(self, kw: KnowledgeWorkflow):
        """KnowledgeWorkflow.adapt_knowledge delegates to knowledge_judge."""
        match = {"key": "task", "steps": [{"tool": "x"}], "success_count": 1, "use_count": 1}
        result = await kw.adapt_knowledge(match, "do something")
        assert isinstance(result, str)

    @pytest.mark.asyncio
    async def test_facade_evaluate_delegates(self, kw: KnowledgeWorkflow):
        """KnowledgeWorkflow.evaluate_and_structure_knowledge delegates."""
        result = await kw.evaluate_and_structure_knowledge("key", "req", [], "res")
        assert result["decision"] == "ADD"
