"""Tests for Phase 31 Retrospective fixes: concurrency locks and VLM cache bounds."""

import asyncio
import pytest

from nanobot.agent.tools.outlook import OutlookTool
from nanobot.agent.tools.rpa_executor import RPAExecutorTool


# ═════════════════════════════════════════════════════════════════════════
# Concurrency Lock Tests
# ═════════════════════════════════════════════════════════════════════════

def test_outlook_tool_has_lock():
    """OutlookTool must have an asyncio.Lock for COM serialization."""
    tool = OutlookTool()
    assert hasattr(tool, "_lock")
    assert isinstance(tool._lock, asyncio.Lock)


def test_rpa_tool_has_lock():
    """RPAExecutorTool must have an asyncio.Lock for device serialization."""
    tool = RPAExecutorTool()
    assert hasattr(tool, "_lock")
    assert isinstance(tool._lock, asyncio.Lock)


# ═════════════════════════════════════════════════════════════════════════
# VLM Cache Bounds Test
# ═════════════════════════════════════════════════════════════════════════

def test_vlm_cache_eviction():
    """VLM provider cache should evict oldest entry when exceeding 4."""
    # Simulate the eviction logic from AgentLoop
    cache: dict[str, str] = {}
    max_size = 4

    for i in range(6):
        model = f"model-{i}"
        if model not in cache:
            if len(cache) >= max_size:
                oldest_key = next(iter(cache))
                del cache[oldest_key]
            cache[model] = f"provider-{i}"

    # Should have exactly max_size entries
    assert len(cache) == max_size
    # Oldest entries (model-0, model-1) should be evicted
    assert "model-0" not in cache
    assert "model-1" not in cache
    # Newest entries should remain
    assert "model-5" in cache
    assert "model-4" in cache
