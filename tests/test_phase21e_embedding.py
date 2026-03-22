"""Tests for Phase 21E — Embedding Model Upgrade.

Validates:
- Default model changed to BGE-M3
- Config wiring through ContextBuilder → VectorMemory → EmbeddingFn
- Custom model override
- Dimension introspection property
- Collection dimension migration on model switch
- Backward compatibility
"""

from pathlib import Path
from unittest.mock import MagicMock, patch, PropertyMock
import pytest


# ---------------------------------------------------------------------------
# 1. Default model path updated to BGE-M3
# ---------------------------------------------------------------------------

class TestEmbeddingDefaults:
    """Verify the default model has been updated to BAAI/bge-m3."""

    def test_default_model_is_bge_m3(self):
        from nanobot.agent.vector_store import _SentenceTransformerEmbedding
        assert "bge-m3" in _SentenceTransformerEmbedding._DEFAULT_MODEL

    def test_default_model_not_minilm(self):
        """Ensure old model is no longer the default."""
        from nanobot.agent.vector_store import _SentenceTransformerEmbedding
        assert "minilm" not in _SentenceTransformerEmbedding._DEFAULT_MODEL.lower()

    def test_custom_model_path_override(self):
        """Constructor should accept and store a custom model path."""
        from nanobot.agent.vector_store import _SentenceTransformerEmbedding
        custom = r"C:\models\my-custom-model"
        emb = _SentenceTransformerEmbedding(model_path=custom)
        assert emb._model_path == custom

    def test_none_model_path_uses_default(self):
        """None or empty model_path should fall back to _DEFAULT_MODEL."""
        from nanobot.agent.vector_store import _SentenceTransformerEmbedding
        emb = _SentenceTransformerEmbedding(model_path=None)
        assert emb._model_path == _SentenceTransformerEmbedding._DEFAULT_MODEL


# ---------------------------------------------------------------------------
# 2. Dimension property
# ---------------------------------------------------------------------------

class TestDimensionProperty:
    """Verify the dimension introspection property."""

    def test_dimension_property_exists(self):
        from nanobot.agent.vector_store import _SentenceTransformerEmbedding
        # Check that 'dimension' is a property on the class
        assert isinstance(
            type.__getattribute__(_SentenceTransformerEmbedding, "dimension"),
            property
        )

    @patch("nanobot.agent.vector_store._SentenceTransformerEmbedding._load")
    def test_dimension_returns_cached_value(self, mock_load):
        """After model load, dimension should return the cached value."""
        from nanobot.agent.vector_store import _SentenceTransformerEmbedding

        # Save and restore class state
        orig_dim = _SentenceTransformerEmbedding._MODEL_DIMENSION
        orig_model = _SentenceTransformerEmbedding._SHARED_MODEL
        try:
            _SentenceTransformerEmbedding._MODEL_DIMENSION = 1024
            _SentenceTransformerEmbedding._SHARED_MODEL = MagicMock()
            emb = _SentenceTransformerEmbedding(model_path="/fake/path")
            assert emb.dimension == 1024
        finally:
            _SentenceTransformerEmbedding._MODEL_DIMENSION = orig_dim
            _SentenceTransformerEmbedding._SHARED_MODEL = orig_model

    @patch("nanobot.agent.vector_store._SentenceTransformerEmbedding._load")
    def test_dimension_triggers_load_when_none(self, mock_load):
        """Accessing dimension should trigger _load() if MODEL_DIMENSION is None."""
        from nanobot.agent.vector_store import _SentenceTransformerEmbedding

        orig_dim = _SentenceTransformerEmbedding._MODEL_DIMENSION
        orig_model = _SentenceTransformerEmbedding._SHARED_MODEL
        try:
            _SentenceTransformerEmbedding._MODEL_DIMENSION = None
            _SentenceTransformerEmbedding._SHARED_MODEL = None
            emb = _SentenceTransformerEmbedding(model_path="/fake/path")
            _ = emb.dimension
            mock_load.assert_called_once()
        finally:
            _SentenceTransformerEmbedding._MODEL_DIMENSION = orig_dim
            _SentenceTransformerEmbedding._SHARED_MODEL = orig_model


# ---------------------------------------------------------------------------
# 3. Config wiring
# ---------------------------------------------------------------------------

class TestConfigWiring:
    """Verify embedding_model flows from config → ContextBuilder → VectorMemory."""

    def test_config_schema_has_embedding_model(self):
        """Config schema should have agents.defaults.embedding_model field."""
        from nanobot.config.schema import Config
        cfg = Config()
        assert hasattr(cfg.agents.defaults, "embedding_model")

    def test_config_default_is_empty_string(self):
        """Default embedding_model should be empty string (auto-detect)."""
        from nanobot.config.schema import AgentDefaults
        defaults = AgentDefaults()
        assert defaults.embedding_model == ""

    def test_config_field_comment_updated(self):
        """The schema source should reference bge-m3 in the embedding_model field."""
        from nanobot.config.schema import AgentDefaults

        # Read the source file directly to check the comment
        import nanobot.config.schema as schema_mod
        source_file = Path(schema_mod.__file__)
        source_text = source_file.read_text(encoding="utf-8")
        # Find the embedding_model line
        for line in source_text.splitlines():
            if "embedding_model" in line and "bge-m3" in line.lower():
                break
        else:
            pytest.fail("embedding_model field comment does not reference bge-m3")

    def test_vector_memory_accepts_embedding_model(self):
        """VectorMemory should accept embedding_model parameter."""
        from nanobot.agent.vector_store import VectorMemory
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "memory").mkdir()
            vm = VectorMemory(tmp, embedding_model=r"C:\models\test-model")
            assert vm._embedding_fn._model_path == r"C:\models\test-model"

    def test_vector_memory_none_embedding_model_uses_default(self):
        """VectorMemory with no embedding_model should use the default."""
        from nanobot.agent.vector_store import VectorMemory, _SentenceTransformerEmbedding
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "memory").mkdir()
            vm = VectorMemory(tmp)
            assert vm._embedding_fn._model_path == _SentenceTransformerEmbedding._DEFAULT_MODEL

    def test_context_builder_accepts_embedding_model(self):
        """ContextBuilder should accept and forward embedding_model."""
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            (workspace / "memory").mkdir()

            from nanobot.agent.context import ContextBuilder
            cb = ContextBuilder(
                workspace, language="en",
                embedding_model=r"C:\models\test-model",
            )
            assert cb.vector_memory._embedding_fn._model_path == r"C:\models\test-model"


# ---------------------------------------------------------------------------
# 4. Collection dimension migration
# ---------------------------------------------------------------------------

class TestDimensionMigration:
    """Verify the dimension migration logic in _ensure_init.

    Uses mocked ChromaDB to avoid PersistentClient file locking issues on Windows.
    """

    @patch("chromadb.PersistentClient")
    def test_dimension_mismatch_triggers_recreation(self, mock_persistent_client):
        """When stored dimension != model dimension, collection should be deleted and recreated."""
        from nanobot.agent.vector_store import _SentenceTransformerEmbedding, VectorMemory
        import tempfile

        orig_dim = _SentenceTransformerEmbedding._MODEL_DIMENSION
        orig_model = _SentenceTransformerEmbedding._SHARED_MODEL
        try:
            # Set model dimension to 1024
            _SentenceTransformerEmbedding._MODEL_DIMENSION = 1024
            _SentenceTransformerEmbedding._SHARED_MODEL = MagicMock()

            # Mock ChromaDB collection with 384-dim stored embeddings
            mock_collection = MagicMock()
            mock_collection.count.return_value = 5  # Has existing data
            mock_collection.get.return_value = {
                "embeddings": [[0.1] * 384],  # Old dimension
                "documents": ["test"],
                "ids": ["doc1"],
            }
            mock_client = MagicMock()
            mock_client.get_or_create_collection.return_value = mock_collection
            mock_persistent_client.return_value = mock_client

            with tempfile.TemporaryDirectory() as tmp:
                (Path(tmp) / "memory").mkdir()
                vm = VectorMemory(tmp)
                vm._ensure_init()

            # Verify: delete_collection was called due to dimension mismatch
            mock_client.delete_collection.assert_called_once_with(VectorMemory.COLLECTION_NAME)
            # And get_or_create_collection was called twice (initial + recreation)
            assert mock_client.get_or_create_collection.call_count == 2

        finally:
            _SentenceTransformerEmbedding._MODEL_DIMENSION = orig_dim
            _SentenceTransformerEmbedding._SHARED_MODEL = orig_model

    @patch("chromadb.PersistentClient")
    def test_same_dimension_preserves_collection(self, mock_persistent_client):
        """When stored dimension == model dimension, collection is NOT recreated."""
        from nanobot.agent.vector_store import _SentenceTransformerEmbedding, VectorMemory
        import tempfile

        orig_dim = _SentenceTransformerEmbedding._MODEL_DIMENSION
        orig_model = _SentenceTransformerEmbedding._SHARED_MODEL
        try:
            # Set model dimension to 384 (same as stored)
            _SentenceTransformerEmbedding._MODEL_DIMENSION = 384
            _SentenceTransformerEmbedding._SHARED_MODEL = MagicMock()

            mock_collection = MagicMock()
            mock_collection.count.return_value = 5
            mock_collection.get.return_value = {
                "embeddings": [[0.1] * 384],  # Same dimension
                "documents": ["test"],
                "ids": ["doc1"],
            }
            mock_client = MagicMock()
            mock_client.get_or_create_collection.return_value = mock_collection
            mock_persistent_client.return_value = mock_client

            with tempfile.TemporaryDirectory() as tmp:
                (Path(tmp) / "memory").mkdir()
                vm = VectorMemory(tmp)
                vm._ensure_init()

            # Verify: delete_collection was NOT called
            mock_client.delete_collection.assert_not_called()
            # Only one get_or_create_collection call (no recreation needed)
            assert mock_client.get_or_create_collection.call_count == 1

        finally:
            _SentenceTransformerEmbedding._MODEL_DIMENSION = orig_dim
            _SentenceTransformerEmbedding._SHARED_MODEL = orig_model

    @patch("chromadb.PersistentClient")
    def test_dimension_probe_error_triggers_recreation(self, mock_persistent_client):
        """When the probe itself raises a dimension-related error, force recreation."""
        from nanobot.agent.vector_store import _SentenceTransformerEmbedding, VectorMemory
        import tempfile

        orig_dim = _SentenceTransformerEmbedding._MODEL_DIMENSION
        orig_model = _SentenceTransformerEmbedding._SHARED_MODEL
        try:
            _SentenceTransformerEmbedding._MODEL_DIMENSION = 1024
            _SentenceTransformerEmbedding._SHARED_MODEL = MagicMock()

            mock_collection = MagicMock()
            mock_collection.count.return_value = 5
            # Simulate ChromaDB raising a dimension error on get()
            mock_collection.get.side_effect = ValueError(
                "Collection expecting embedding with dimension of 384, got 1024"
            )
            mock_client = MagicMock()
            mock_client.get_or_create_collection.return_value = mock_collection
            mock_persistent_client.return_value = mock_client

            with tempfile.TemporaryDirectory() as tmp:
                (Path(tmp) / "memory").mkdir()
                vm = VectorMemory(tmp)
                result = vm._ensure_init()

            # Should succeed (collection was recreated)
            assert result is True
            # delete_collection was called due to dimension error
            mock_client.delete_collection.assert_called_once_with(VectorMemory.COLLECTION_NAME)
            # get_or_create_collection called twice (initial + recreation)
            assert mock_client.get_or_create_collection.call_count == 2

        finally:
            _SentenceTransformerEmbedding._MODEL_DIMENSION = orig_dim
            _SentenceTransformerEmbedding._SHARED_MODEL = orig_model

    @patch("chromadb.PersistentClient")
    def test_non_dimension_probe_error_does_not_recreate(self, mock_persistent_client):
        """When probe raises a non-dimension error, skip gracefully (don't recreate)."""
        from nanobot.agent.vector_store import _SentenceTransformerEmbedding, VectorMemory
        import tempfile

        orig_dim = _SentenceTransformerEmbedding._MODEL_DIMENSION
        orig_model = _SentenceTransformerEmbedding._SHARED_MODEL
        try:
            _SentenceTransformerEmbedding._MODEL_DIMENSION = 1024
            _SentenceTransformerEmbedding._SHARED_MODEL = MagicMock()

            mock_collection = MagicMock()
            mock_collection.count.return_value = 5
            # Simulate a non-dimension error (e.g., timeout)
            mock_collection.get.side_effect = RuntimeError("Connection timeout")
            mock_client = MagicMock()
            mock_client.get_or_create_collection.return_value = mock_collection
            mock_persistent_client.return_value = mock_client

            with tempfile.TemporaryDirectory() as tmp:
                (Path(tmp) / "memory").mkdir()
                vm = VectorMemory(tmp)
                result = vm._ensure_init()

            # Should still succeed (init didn't fail)
            assert result is True
            # delete_collection should NOT be called (error wasn't dimension-related)
            mock_client.delete_collection.assert_not_called()

        finally:
            _SentenceTransformerEmbedding._MODEL_DIMENSION = orig_dim
            _SentenceTransformerEmbedding._SHARED_MODEL = orig_model


# ---------------------------------------------------------------------------
# 5. Offline mode preserved
# ---------------------------------------------------------------------------

class TestOfflineMode:
    """Verify local_files_only is still enforced."""

    def test_hf_hub_offline_set_in_source(self):
        """_load source code should set HF_HUB_OFFLINE=1."""
        from nanobot.agent.vector_store import _SentenceTransformerEmbedding
        source_file = Path(_SentenceTransformerEmbedding.__module__.replace(".", "/") + ".py")
        # Build absolute path from package
        import nanobot.agent.vector_store as vs_mod
        source_text = Path(vs_mod.__file__).read_text(encoding="utf-8")
        assert 'HF_HUB_OFFLINE' in source_text
        assert 'local_files_only=True' in source_text


# ---------------------------------------------------------------------------
# 6. Backward compatibility
# ---------------------------------------------------------------------------

class TestBackwardCompatibility:
    """Ensure existing VectorMemory usage patterns still work."""

    def test_vector_memory_no_args_works(self):
        """VectorMemory() with no args should still work (backward compat)."""
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "memory").mkdir()
            from nanobot.agent.vector_store import VectorMemory
            vm = VectorMemory(tmp)
            assert vm._embedding_fn._model_path is not None

    def test_vector_memory_old_style_init(self):
        """VectorMemory(workspace, provider, model) still works (positional)."""
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "memory").mkdir()
            from nanobot.agent.vector_store import VectorMemory
            vm = VectorMemory(tmp, None, None)
            assert vm._embedding_fn._model_path is not None
