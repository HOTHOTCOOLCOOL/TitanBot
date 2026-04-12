"""Tests for Phase 46A: Fallback-Driven Query Expansion.

Verifies that query_expansion_fallback() correctly:
- Calls LLM to infer implicit concept words when all 3 layers miss
- Respects 3s timeout circuit breaker
- Gracefully handles provider=None
- Marks matches with _match_method="query_expansion"
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from nanobot.agent.knowledge_workflow import KnowledgeWorkflow


def _make_kw(tasks=None, provider=None, model="test-model", vector_memory=None):
    """Create a KnowledgeWorkflow with mock dependencies."""
    kw = KnowledgeWorkflow(provider=provider, model=model)
    kw.knowledge_store = MagicMock()
    kw.knowledge_store.get_all_tasks.return_value = tasks or []
    kw.vector_memory = vector_memory
    return kw


def _mock_vector_memory(key_score_map):
    """Create a mock vector memory that returns scores for given keys."""
    vm = MagicMock()
    def search(query, top_k=5, source_filter=None):
        results = []
        for key, score in key_score_map.items():
            results.append({"metadata": {"key": key}, "score": score})
        return results
    vm.search = search
    return vm


def _mock_provider(response_text):
    """Create a mock provider that returns the given text."""
    provider = MagicMock()
    response = MagicMock()
    response.content = response_text
    provider.chat = AsyncMock(return_value=response)
    return provider


# -------------------------------------------------------------------
# Test 1: Expansion succeeds when LLM returns matching concept words
# -------------------------------------------------------------------
@pytest.mark.asyncio
async def test_expansion_returns_match_on_implicit_concept():
    """LLM expands implicit query → KB match found via hybrid retrieval."""
    tasks = [
        {"key": "SSRS weekly report export", "triggers": ["report", "SSRS", "weekly"]},
        {"key": "send email to zhang", "triggers": ["email"]},
    ]
    provider = _mock_provider('["SSRS weekly report", "report export"]')
    vm = _mock_vector_memory({"SSRS weekly report export": 0.85})

    kw = _make_kw(tasks=tasks, provider=provider, vector_memory=vm)

    with patch("nanobot.config.loader.get_config") as mock_cfg:
        mock_cfg.return_value.agents.workflow_models = {}
        result = await kw.query_expansion_fallback("that table from yesterday")

    assert result is not None
    assert "SSRS" in result.get("key", "")
    assert result.get("_match_method") == "query_expansion"
    assert "_match_confidence" in result
    provider.chat.assert_awaited_once()


# -------------------------------------------------------------------
# Test 2: 3s timeout returns None silently
# -------------------------------------------------------------------
@pytest.mark.asyncio
async def test_expansion_timeout_returns_none():
    """Mock LLM hangs for >3s → circuit breaker fires, returns None."""
    tasks = [{"key": "some task", "triggers": []}]

    provider = MagicMock()

    async def slow_chat(**kwargs):
        await asyncio.sleep(10)  # way beyond 3s timeout

    provider.chat = slow_chat

    kw = _make_kw(tasks=tasks, provider=provider)

    with patch("nanobot.config.loader.get_config") as mock_cfg:
        mock_cfg.return_value.agents.workflow_models = {}
        result = await kw.query_expansion_fallback("any query")

    assert result is None


# -------------------------------------------------------------------
# Test 3: provider=None → no LLM call, returns None
# -------------------------------------------------------------------
@pytest.mark.asyncio
async def test_expansion_no_provider_returns_none():
    """Without a provider, expansion should silently return None."""
    kw = _make_kw(tasks=[{"key": "task1", "triggers": []}], provider=None)

    result = await kw.query_expansion_fallback("any query")

    assert result is None


# -------------------------------------------------------------------
# Test 4: All expanded terms miss → returns None
# -------------------------------------------------------------------
@pytest.mark.asyncio
async def test_expansion_all_expanded_miss_returns_none():
    """LLM returns terms that don't match any KB entry → None."""
    tasks = [{"key": "compile rust project", "triggers": ["rust"]}]
    provider = _mock_provider('["quantum physics", "dark matter"]')

    kw = _make_kw(tasks=tasks, provider=provider)

    with patch("nanobot.config.loader.get_config") as mock_cfg:
        mock_cfg.return_value.agents.workflow_models = {}
        result = await kw.query_expansion_fallback("something unrelated")

    assert result is None


# -------------------------------------------------------------------
# Test 5: Successful match has _match_method="query_expansion"
# -------------------------------------------------------------------
@pytest.mark.asyncio
async def test_expansion_marks_match_method():
    """Verify the _match_method field is correctly set on expansion matches."""
    tasks = [
        {"key": "weather forecast report", "triggers": ["forecast", "weather", "report"]},
    ]
    provider = _mock_provider('["weather forecast"]')
    vm = _mock_vector_memory({"weather forecast report": 0.9})

    kw = _make_kw(tasks=tasks, provider=provider, vector_memory=vm)

    with patch("nanobot.config.loader.get_config") as mock_cfg:
        mock_cfg.return_value.agents.workflow_models = {}
        result = await kw.query_expansion_fallback("what is the climate like")

    assert result is not None
    assert result["_match_method"] == "query_expansion"
    assert 0 < result["_match_confidence"] <= 1.0
