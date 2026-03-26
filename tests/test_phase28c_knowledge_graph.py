"""Tests for Phase 28C - Three-Tier Memory Architecture (Embedded Vector DB).

Covers:
- VectorMemory injection into KnowledgeGraph
- generate_entity_summaries ingesting into VectorMemory
- get_entity_context using VectorMemory for semantic search
"""

import json
import pytest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

from nanobot.agent.knowledge_graph import KnowledgeGraph
from nanobot.agent.vector_store import VectorMemory
from nanobot.providers.base import LLMProvider


@pytest.fixture
def workspace(tmp_path):
    return tmp_path


@pytest.fixture
def mock_vector_memory():
    vm = MagicMock(spec=VectorMemory)
    vm.ingest_text = MagicMock()
    vm.search = MagicMock(return_value=[])
    return vm


@pytest.fixture
def kg(workspace, mock_vector_memory):
    return KnowledgeGraph(workspace, vector_memory=mock_vector_memory)


class TestPhase28cVectorDbIntegration:

    @pytest.mark.asyncio
    async def test_generate_entity_summaries_ingests_to_vector_memory(self, kg, mock_vector_memory):
        """Entity summaries should be ingested into VectorMemory if available."""
        kg._add_triple("David", "works for", "Salesforce")
        kg.rebuild_entity_index()

        mock_provider = AsyncMock(spec=LLMProvider)
        mock_response = MagicMock()
        mock_response.content = json.dumps({
            "David": "David works at Salesforce."
        })
        mock_provider.chat.return_value = mock_response

        await kg.generate_entity_summaries(mock_provider, "test_model")

        # Verify VectorMemory was called
        mock_vector_memory.ingest_text.assert_called_once_with(
            text="David: David works at Salesforce.",
            source="kg_entity:David",
            metadata={"entity": "David", "type": "kg_summary"}
        )

    def test_get_entity_context_uses_vector_memory(self, kg, mock_vector_memory):
        """get_entity_context should blend semantic search scores with exact match scores."""
        kg._add_triple("David", "works for", "Salesforce")
        kg._add_triple("Alice", "likes", "Salesforce")
        kg.rebuild_entity_index()
        kg._entities["David"]["summary"] = "David is an engineer at Salesforce."
        kg._entities["Alice"]["summary"] = "Alice is a designer who likes Salesforce."
        kg._save()

        # Mock semantic search returning Alice with high score for a query that doesn't string match Alice
        # Query: "Who designs things?"
        mock_vector_memory.search.return_value = [
            {"metadata": {"entity": "Alice"}, "score": 0.9}
        ]

        context = kg.get_entity_context("Who designs things?")
        
        # Verify vector memory search was called
        mock_vector_memory.search.assert_called_once_with("Who designs things?", top_k=5, source_filter="kg_entity")
        
        # Alice should be in the context because of the semantic boost (0.9 * 3 = 2.7 score)
        assert "Alice" in context
        assert "designer" in context
        # David shouldn't normally be included as he has no string match and no semantic boost
        assert "David" not in context

    def test_get_entity_context_without_vector_memory(self, workspace):
        """get_entity_context should still work using string matching when VectorMemory is None."""
        kg_no_vec = KnowledgeGraph(workspace, vector_memory=None)
        kg_no_vec._add_triple("David", "works for", "Salesforce")
        kg_no_vec.rebuild_entity_index()
        kg_no_vec._entities["David"]["summary"] = "David is an engineer at Salesforce."
        kg_no_vec._save()

        # String match should find David
        context = kg_no_vec.get_entity_context("Tell me about David")
        assert "David" in context
        assert "engineer" in context

        # Non-matching string shouldn't find David
        context2 = kg_no_vec.get_entity_context("Tell me about Alice")
        # Falls back to 1hop context which is empty
        assert context2 == ""
