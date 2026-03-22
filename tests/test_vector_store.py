"""Tests for the Vector Store (RAG) module."""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from nanobot.agent.vector_store import VectorMemory


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    """Create a temporary workspace."""
    (tmp_path / "memory").mkdir()
    return tmp_path


@pytest.fixture
def vm(workspace: Path) -> VectorMemory:
    """Create a VectorMemory instance."""
    return VectorMemory(workspace)


def test_chunk_text():
    """Verify chunking logic (first by \n\n, then \n)."""
    text = "Para 1\n\nPara 2\n\nShort\n\n"
    chunks = VectorMemory._chunk_text(text, max_chars=100)
    assert len(chunks) == 3
    assert "Para 1" in chunks
    assert "Para 2" in chunks
    assert "Short" in chunks

    long_para = "A" * 60 + "\n" + "B" * 60
    chunks = VectorMemory._chunk_text(long_para, max_chars=100)
    assert len(chunks) == 2
    assert chunks[0] == "A" * 60
    assert chunks[1] == "B" * 60


def test_format_results_for_context():
    """Verify context formatting for the LLM prompt."""
    results = [
        {"source": "history", "text": "We talked about Python.", "score": 0.85},
        {
            "source": "daily_log:2026-03-01",
            "text": "Wrote tests.",
            "score": 0.92,
            "metadata": {"date": "2026-03-01"}
        }
    ]
    formatted = VectorMemory.format_results_for_context(results)
    assert "Relevant Historical Context" in formatted
    assert "[history]** (relevance: 85%)" in formatted
    assert "[2026-03-01]** (relevance: 92%)" in formatted
    assert "We talked about Python." in formatted
    assert "Wrote tests." in formatted


class TestVectorMemoryIntegration:
    """Tests that actually use ChromaDB and the embedding model.
    Note: Initialising sentence-transformers takes a few seconds.
    """

    def test_init_and_stats(self, vm: VectorMemory):
        """Verify lazy init and collection stats."""
        assert not vm._init_done
        stats = vm.stats()
        assert stats["status"] == "ready"
        assert stats["count"] == 0
        assert vm._init_done
        assert (vm.workspace / "memory" / "vectordb").exists()

    def test_ingest_and_search(self, vm: VectorMemory):
        """Verify basic ingestion and semantic search."""
        vm.ingest_text(
            "The quick brown fox jumps over the lazy dog.",
            source="test_source",
            metadata={"category": "animal"}
        )
        vm.ingest_text(
            "Python is a high-level programming language.",
            source="test_source",
            metadata={"category": "tech"}
        )

        # Semantic search
        results = vm.search("Tell me about coding languages", top_k=1)
        assert len(results) == 1
        assert "Python" in results[0]["text"]
        assert results[0]["source"] == "test_source"
        assert results[0]["metadata"]["category"] == "tech"
        assert results[0]["score"] > 0.0  # Should be a valid score

    def test_deduplication(self, vm: VectorMemory):
        """Verify identical content is not duplicated."""
        text = "This is a repeated paragraph to test deduplication."
        vm.ingest_text(text, source="test")
        assert vm.stats()["count"] == 1

        # Ingest exactly the same again
        vm.ingest_text(text, source="test")
        assert vm.stats()["count"] == 1  # Should still be 1

    def test_ingest_history_file(self, vm: VectorMemory):
        """Verify HISTORY.md parsing and ingestion."""
        history_file = vm.workspace / "memory" / "HISTORY.md"
        history_file.write_text(
            "Conversation 1 summary.\n\nConversation 2 summary.",
            encoding="utf-8"
        )

        count = vm.ingest_history_file()
        assert count == 2
        assert vm.stats()["count"] == 2

        results = vm.search("Conversation 1")
        assert len(results) > 0
        assert "Conversation 1" in results[0]["text"]
        assert results[0]["source"] == "history"

    def test_ingest_daily_logs(self, vm: VectorMemory):
        """Verify YYYY-MM-DD.md parsing and ingestion."""
        log1 = vm.workspace / "memory" / "2026-03-01.md"
        log1.write_text("Did some refactoring today.", encoding="utf-8")
        
        log2 = vm.workspace / "memory" / "2026-03-02.md"
        log2.write_text("Fixed a major bug.", encoding="utf-8")

        count = vm.ingest_daily_logs()
        assert count == 2
        assert vm.stats()["count"] == 2

        results = vm.search("bug", top_k=1)
        assert "Fixed a major bug." in results[0]["text"]
        assert results[0]["source"] == "daily_log:2026-03-02"
        assert results[0]["metadata"]["date"] == "2026-03-02"

    def test_search_source_filter(self, vm: VectorMemory):
        """Verify the post-search source filter."""
        vm.ingest_text("Apples and oranges", source="history")
        vm.ingest_text("Bananas and grapes", source="daily_log:2026-03-01")

        # Filter by history
        results = vm.search("fruit", source_filter="history")
        assert len(results) == 1
        assert results[0]["source"] == "history"

        # Filter by daily_log
        results = vm.search("fruit", source_filter="daily_log")
        assert len(results) == 1
        assert "daily_log" in results[0]["source"]

    def test_search_no_results(self, vm: VectorMemory):
        """Verify searching an empty DB returns [] safely."""
        results = vm.search("anything")
        assert results == []

    @patch("nanobot.agent.vector_store._SentenceTransformerEmbedding._load")
    def test_graceful_failure_on_search(self, mock_load, vm: VectorMemory):
        """Verify the vector DB fails gracefully if embedding model crashes during search."""
        mock_load.side_effect = ImportError("Simulated model failure")
        
        # Searching should catch error and return empty list
        results = vm.search("query")
        assert results == []


class TestDimensionMigration:
    """Regression tests for embedding dimension migration (L7/L10 pattern)."""

    def test_numpy_ndarray_dimension_probe(self, workspace: Path):
        """Reproduce production bug: ChromaDB returns numpy ndarray for embeddings.

        Old code: `if probe and probe.get("embeddings") and len(...)` 
        fails because bool(ndarray) raises ValueError.
        Fixed code: `if embeddings is not None and len(embeddings) > 0`
        """
        import numpy as np
        from nanobot.agent.vector_store import _SentenceTransformerEmbedding

        vm = VectorMemory(workspace)

        # Mock ChromaDB client and collection
        mock_collection = MagicMock()
        mock_collection.count.return_value = 2
        # ChromaDB returns numpy ndarray, not Python list — this is the key detail
        mock_collection.get.return_value = {
            "ids": ["id1"],
            "embeddings": np.array([[0.1] * 384]),  # old 384-dim vectors
        }

        mock_client = MagicMock()
        mock_client.get_or_create_collection.return_value = mock_collection

        # Directly set the class-level dimension cache (this is what .dimension reads)
        original_dim = _SentenceTransformerEmbedding._MODEL_DIMENSION
        try:
            _SentenceTransformerEmbedding._MODEL_DIMENSION = 1024  # new model dimension
            with patch("chromadb.PersistentClient", return_value=mock_client):
                result = vm._ensure_init()
        finally:
            _SentenceTransformerEmbedding._MODEL_DIMENSION = original_dim

        assert result is True
        # The mismatch (384 stored vs 1024 model) should trigger delete + recreate
        mock_client.delete_collection.assert_called_once_with(VectorMemory.COLLECTION_NAME)
        # get_or_create_collection called twice: initial + after recreation
        assert mock_client.get_or_create_collection.call_count == 2

