"""Tests for Phase 21D Architecture & Configuration Improvements.

Covers all 5 issues: I1, I2, D4, E1, E2.
"""
import asyncio
import json
import pytest
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, AsyncMock, patch


# ── I1: Config singleton consistency ──────────────────────────

def test_get_config_returns_singleton():
    """I1: get_config() should return the same instance on repeated calls."""
    from nanobot.config.loader import get_config, invalidate_config
    invalidate_config()  # start fresh
    c1 = get_config()
    c2 = get_config()
    assert c1 is c2
    invalidate_config()  # cleanup


def test_invalidate_config_resets():
    """I1: invalidate_config() should force a fresh Config() on next get_config()."""
    from nanobot.config.loader import get_config, invalidate_config
    invalidate_config()
    c1 = get_config()
    invalidate_config()
    c2 = get_config()
    # After invalidation, a new instance is created
    assert c1 is not c2
    invalidate_config()  # cleanup


def test_loop_get_config_uses_singleton():
    """I1: AgentLoop._get_config() should eventually use get_config() from loader."""
    import inspect
    from nanobot.agent.loop import AgentLoop
    source = inspect.getsource(AgentLoop._get_config)
    assert "get_config" in source
    assert "Config()" not in source


def test_subagent_uses_get_config():
    """I1: SubagentManager should use get_config() from loader."""
    import inspect
    from nanobot.agent.subagent import SubagentManager
    source = inspect.getsource(SubagentManager._run_subagent)
    assert "get_config" in source


def test_litellm_provider_uses_get_config():
    """I1: LiteLLMProvider.chat() should use get_config() from loader."""
    import inspect
    from nanobot.providers.litellm_provider import LiteLLMProvider
    source = inspect.getsource(LiteLLMProvider.chat)
    assert "get_config" in source


# ── I2: Dashboard KB/Reflection/Graph APIs ────────────────────

@pytest.mark.skipif(
    not __import__("importlib").util.find_spec("fastapi"),
    reason="fastapi not installed",
)
def test_dashboard_new_endpoints_exist():
    """I2: Dashboard should have 4 new API endpoints."""
    from nanobot.dashboard.app import app
    routes = [r.path for r in app.routes]
    assert "/api/reflections" in routes
    assert "/api/knowledge_graph" in routes
    assert "/api/knowledge_base" in routes
    assert "/api/background_tasks" in routes


# ── D4: Unified async task manager ────────────────────────────

def test_task_manager_singleton():
    """D4: BackgroundTaskManager.get() should return a singleton."""
    from nanobot.utils.task_manager import BackgroundTaskManager
    mgr1 = BackgroundTaskManager.get()
    mgr2 = BackgroundTaskManager.get()
    assert mgr1 is mgr2


@pytest.mark.asyncio
async def test_task_manager_spawn_and_track():
    """D4: spawn() should track the task and record completion."""
    from nanobot.utils.task_manager import BackgroundTaskManager, TaskState

    mgr = BackgroundTaskManager(max_concurrency=5)

    completed = False
    async def _work():
        nonlocal completed
        await asyncio.sleep(0.01)
        completed = True

    task = mgr.spawn(_work(), name="test_work")
    await task  # wait for completion
    await asyncio.sleep(0.05)  # let done callback run

    assert completed
    assert mgr.running_count == 0
    assert len(mgr._history) >= 1
    last = mgr._history[-1]
    assert last.state == TaskState.DONE


@pytest.mark.asyncio
async def test_task_manager_error_logging():
    """D4: Failed tasks should be recorded with error details."""
    from nanobot.utils.task_manager import BackgroundTaskManager, TaskState

    mgr = BackgroundTaskManager(max_concurrency=5)

    async def _fail():
        raise ValueError("test error")

    task = mgr.spawn(_fail(), name="test_fail")
    # Wait for task to complete (it will fail)
    try:
        await task
    except ValueError:
        pass
    await asyncio.sleep(0.05)

    assert len(mgr._history) >= 1
    last = mgr._history[-1]
    assert last.state == TaskState.FAILED
    assert "test error" in last.error


def test_task_manager_summary():
    """D4: summary() should return expected keys."""
    from nanobot.utils.task_manager import BackgroundTaskManager
    mgr = BackgroundTaskManager()
    summary = mgr.summary()
    assert "running" in summary
    assert "completed" in summary
    assert "failed" in summary
    assert "total_spawned" in summary
    assert "max_concurrency" in summary


def test_safe_create_task_delegates():
    """D4: _safe_create_task should delegate to BackgroundTaskManager."""
    import inspect
    from nanobot.agent.commands import _safe_create_task
    source = inspect.getsource(_safe_create_task)
    assert "BackgroundTaskManager" in source


# ── E1: Knowledge matching precision ─────────────────────────

def test_adaptive_threshold_small_kb():
    """E1: Small KB (≤10 entries) should use base threshold."""
    from nanobot.agent.knowledge_workflow import KnowledgeWorkflow
    threshold = KnowledgeWorkflow._adaptive_threshold(5)
    assert 0.60 <= threshold <= 0.62


def test_adaptive_threshold_large_kb():
    """E1: Large KB (100+ entries) should use stricter threshold."""
    from nanobot.agent.knowledge_workflow import KnowledgeWorkflow
    threshold = KnowledgeWorkflow._adaptive_threshold(100)
    assert threshold > 0.65
    # Cap at 0.75
    max_threshold = KnowledgeWorkflow._adaptive_threshold(1000)
    assert max_threshold <= 0.75


def test_key_extraction_cache():
    """E1: _key_extraction_cache should be a module-level dict."""
    from nanobot.agent.knowledge_workflow import _key_extraction_cache, _KEY_CACHE_MAX
    assert isinstance(_key_extraction_cache, dict)
    assert _KEY_CACHE_MAX == 128


def test_match_knowledge_returns_confidence():
    """E1: match_knowledge() should augment exact matches with _match_confidence."""
    from nanobot.agent.knowledge_workflow import KnowledgeWorkflow

    with tempfile.TemporaryDirectory() as tmpdir:
        workspace = Path(tmpdir)
        kw = KnowledgeWorkflow(workspace=workspace)

        kw.knowledge_store.add_task(
            key="查询天气预报",
            description="check weather",
            steps=[{"tool": "web_fetch", "args": {}}],
            params={},
            result_summary="Task completed",
        )

        result = kw.match_knowledge("查询天气预报")
        assert result is not None
        assert result.get("_match_confidence") == 1.0


# ── E2: Memory capacity management ───────────────────────────

def test_reflection_store_max_capacity():
    """E2: ReflectionStore should have MAX_REFLECTIONS constant."""
    from nanobot.agent.reflection import ReflectionStore
    assert hasattr(ReflectionStore, "MAX_REFLECTIONS")
    assert ReflectionStore.MAX_REFLECTIONS == 100


def test_reflection_store_auto_prune():
    """E2: Adding reflections beyond MAX should auto-prune oldest."""
    from nanobot.agent.reflection import ReflectionStore

    with tempfile.TemporaryDirectory() as tmpdir:
        workspace = Path(tmpdir)
        store = ReflectionStore(workspace)
        # Temporarily lower for testing
        store.MAX_REFLECTIONS = 5

        for i in range(8):
            store.add_reflection(f"trigger_{i}", f"reason_{i}", f"fix_{i}")

        assert store.count <= 5
        # Oldest should be pruned — trigger_0, trigger_1, trigger_2 gone
        triggers = [r["trigger"] for r in store._reflections]
        assert "trigger_0" not in triggers


def test_reflection_store_public_prune():
    """E2: ReflectionStore.prune() should trim and save."""
    from nanobot.agent.reflection import ReflectionStore

    with tempfile.TemporaryDirectory() as tmpdir:
        workspace = Path(tmpdir)
        store = ReflectionStore(workspace)
        for i in range(5):
            store.add_reflection(f"t_{i}", f"r_{i}", f"f_{i}")
        store.MAX_REFLECTIONS = 3
        removed = store.prune()
        assert removed == 2
        assert store.count == 3


def test_kg_max_capacity():
    """E2: KnowledgeGraph should have MAX_TRIPLES constant."""
    from nanobot.agent.knowledge_graph import KnowledgeGraph
    assert hasattr(KnowledgeGraph, "MAX_TRIPLES")
    assert KnowledgeGraph.MAX_TRIPLES == 500


def test_kg_auto_prune():
    """E2: Adding triples beyond MAX should auto-prune oldest."""
    from nanobot.agent.knowledge_graph import KnowledgeGraph

    with tempfile.TemporaryDirectory() as tmpdir:
        workspace = Path(tmpdir)
        kg = KnowledgeGraph(workspace)
        kg.MAX_TRIPLES = 5

        for i in range(8):
            kg._add_triple(f"subj_{i}", "rel", f"obj_{i}")

        assert kg.count <= 5
        subjects = [t["subject"] for t in kg._triples]
        assert "subj_0" not in subjects


def test_kg_count_property():
    """E2: KnowledgeGraph.count should reflect current size."""
    from nanobot.agent.knowledge_graph import KnowledgeGraph

    with tempfile.TemporaryDirectory() as tmpdir:
        workspace = Path(tmpdir)
        kg = KnowledgeGraph(workspace)
        assert kg.count == 0
        kg._add_triple("A", "likes", "B")
        assert kg.count == 1
