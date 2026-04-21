"""Tests for Phase 51 MarkerExtractor (M-RAG)."""

import pytest
from unittest.mock import MagicMock, AsyncMock
from pathlib import Path
import json

from nanobot.agent.marker_extractor import MarkerExtractor, MetaMarker

@pytest.fixture
def mock_provider():
    provider = MagicMock()
    provider.chat = AsyncMock()
    # Mock LLM response
    mock_resp = MagicMock()
    mock_resp.content = json.dumps([
        {
            "key": "Test Key",
            "value": "Test Value",
            "paragraphs": [0, 1]
        }
    ])
    provider.chat.return_value = mock_resp
    return provider

@pytest.mark.asyncio
async def test_marker_extractor_caching(tmp_path, mock_provider, monkeypatch):
    from nanobot.config.loader import get_config
    config = get_config()
    config.features.marker_indexing = True
    config.features.marker_prompt_version = "v1"

    extractor = MarkerExtractor(workspace=tmp_path, provider=mock_provider, model="test-model")
    
    # First extraction
    content = "Para 1\n\nPara 2\n\nPara 3"
    
    # The mock returns paragraphs [0, 1], coverage is 2/3 < 95%
    markers = await extractor.extract(content, "test.md")
    assert markers is None  # Fallback to chunking
    
    # Change mock to cover all to test caching
    mock_resp = MagicMock()
    mock_resp.content = json.dumps([
        {
            "key": "Test Key",
            "value": "Test Value",
            "paragraphs": [0, 1, 2]
        }
    ])
    mock_provider.chat.return_value = mock_resp
    
    markers = await extractor.extract(content, "test.md")
    assert markers is not None
    assert len(markers) == 1
    assert markers[0].key == "Test Key"
    
    # Second extraction should hit cache, meaning LLM isn't called again.
    # LLM should have been called 2 times total since the first one failed check.
    assert mock_provider.chat.call_count == 2
    
    markers_cached = await extractor.extract(content, "test.md")
    assert mock_provider.chat.call_count == 2 # Remains 2
    assert len(markers_cached) == 1
    assert markers_cached[0].key == "Test Key"
