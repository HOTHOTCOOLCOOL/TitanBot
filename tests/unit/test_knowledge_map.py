"""Unit tests for KnowledgeMapTool (ADR-67).

Tests cover:
- A2: Empty/missing graph returns standard "Error: ..." prefix
- A3: Output strictly ≤ 3,000 chars even with a large graph
- A4: mtime-based cache prevents redundant JSON parsing
- A5: Basic output structure is sane and parseable
"""

import asyncio
import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from nanobot.agent.tools.knowledge_map import (
    KnowledgeMapTool,
    _ERR_UNAVAILABLE,
    _MAP_OUTPUT_CAP,
    _TRUNCATION_SUFFIX,
)


# ─── Fixtures ──────────────────────────────────────────────────────────────────


def _make_tool(tmp_path: Path) -> KnowledgeMapTool:
    return KnowledgeMapTool(workspace=tmp_path)


def _write_graph(tmp_path: Path, triples: list[dict]) -> Path:
    memory_dir = tmp_path / "memory"
    memory_dir.mkdir(parents=True, exist_ok=True)
    graph_path = memory_dir / "graph.json"
    graph_path.write_text(json.dumps({"triples": triples}), encoding="utf-8")
    return graph_path


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


# ─── A2: Empty / missing graph ─────────────────────────────────────────────────


def test_missing_graph_returns_error(tmp_path):
    """A2: No graph.json → standard Error prefix."""
    tool = _make_tool(tmp_path)
    result = _run(tool.execute())
    assert result == _ERR_UNAVAILABLE
    assert result.startswith("Error:")


def test_empty_triples_returns_error(tmp_path):
    """A2: graph.json exists but has zero triples → standard Error prefix."""
    _write_graph(tmp_path, [])
    tool = _make_tool(tmp_path)
    result = _run(tool.execute())
    assert result == _ERR_UNAVAILABLE
    assert result.startswith("Error:")


def test_corrupt_json_returns_error(tmp_path):
    """A2: Malformed graph.json → standard Error prefix (no exception leaks)."""
    memory_dir = tmp_path / "memory"
    memory_dir.mkdir(parents=True, exist_ok=True)
    (memory_dir / "graph.json").write_text("{bad json", encoding="utf-8")
    tool = _make_tool(tmp_path)
    result = _run(tool.execute())
    assert result.startswith("Error:")


# ─── A3: Output cap ────────────────────────────────────────────────────────────


def test_output_cap_enforced(tmp_path):
    """A3: Output must be ≤ _MAP_OUTPUT_CAP chars even with a dense graph."""
    long_hub = "Hub_" + ("A" * (_MAP_OUTPUT_CAP + 500))
    triples = [
        {
            "source": long_hub,
            "target": f"SubTopic_{i}_" + ("B" * 400),
            "predicate": "relates_to",
        }
        for i in range(6)
    ]
    _write_graph(tmp_path, triples)
    tool = _make_tool(tmp_path)
    result = _run(tool.execute())
    assert result.endswith(_TRUNCATION_SUFFIX), "Expected truncation branch to be exercised"
    assert len(result) <= _MAP_OUTPUT_CAP, (
        f"Output length {len(result)} exceeds cap {_MAP_OUTPUT_CAP}"
    )


def test_output_not_error_on_valid_graph(tmp_path):
    """A3: A valid graph should NOT return an Error string."""
    triples = [
        {"source": "Security", "target": "verification.py", "predicate": "involves"},
        {"source": "Security", "target": "AST Isolation", "predicate": "uses"},
        {"source": "Memory", "target": "IFCC", "predicate": "includes"},
    ]
    _write_graph(tmp_path, triples)
    tool = _make_tool(tmp_path)
    result = _run(tool.execute())
    assert not result.startswith("Error:")
    assert "📌" in result  # domain hubs are formatted
    assert len(result) <= _MAP_OUTPUT_CAP


# ─── A4: Lazy mtime cache ──────────────────────────────────────────────────────


def test_cache_hit_skips_json_reload(tmp_path):
    """A4: Second call with same mtime must NOT re-parse graph.json."""
    triples = [{"source": "A", "target": "B", "predicate": "rel"}]
    graph_path = _write_graph(tmp_path, triples)
    tool = _make_tool(tmp_path)

    call_count = 0
    original_loads = json.loads

    def counting_loads(s):
        nonlocal call_count
        call_count += 1
        return original_loads(s)

    with patch("nanobot.agent.tools.knowledge_map.json.loads", side_effect=counting_loads):
        _run(tool.execute())  # First call — should parse
        _run(tool.execute())  # Second call — should hit cache

    assert call_count == 1, (
        f"json.loads called {call_count} times; expected 1 (cache should prevent re-parse)"
    )


def test_cache_invalidated_on_mtime_change(tmp_path):
    """A4: Cache is rebuilt when graph.json mtime changes."""
    triples = [{"source": "A", "target": "B", "predicate": "rel"}]
    graph_path = _write_graph(tmp_path, triples)
    tool = _make_tool(tmp_path)

    _run(tool.execute())  # Populate cache
    first_cache = tool._cache

    # Simulate a file update (force a different mtime)
    import time
    time.sleep(0.05)
    new_triples = triples + [{"source": "NewHub", "target": "C", "predicate": "links"}]
    graph_path.write_text(json.dumps({"triples": new_triples}), encoding="utf-8")

    _run(tool.execute())  # Should re-parse
    assert tool._cache != first_cache, "Cache was not invalidated after mtime change"
    assert "NewHub" in tool._cache


# ─── A5: Sanity / structure ────────────────────────────────────────────────────


def test_output_structure(tmp_path):
    """A5: Output contains numbered domain list with expected format."""
    triples = [
        {"source": "Security", "target": "verification.py", "predicate": "involves"},
        {"source": "Security", "target": "AST Isolation", "predicate": "uses"},
        {"source": "Memory", "target": "IFCC", "predicate": "includes"},
        {"source": "RPA", "target": "rpa_executor.py", "predicate": "uses"},
    ]
    _write_graph(tmp_path, triples)
    tool = _make_tool(tmp_path)
    result = _run(tool.execute())

    lines = result.splitlines()
    assert lines[0] == "[Knowledge Domain Map]"
    # Check that at least one hub line is present
    hub_lines = [l for l in lines if l.startswith("1.") or "📌" in l]
    assert len(hub_lines) >= 1
