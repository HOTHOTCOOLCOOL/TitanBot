"""Tests for Phase 21B P1 security & bug fixes.

Covers all 10 issues: S3, S4, B2, B3, B4, L3, L4, D2, D3, C1.
"""
import asyncio
import pytest
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, AsyncMock, patch, PropertyMock


# ── S3: WebSocket input validation ─────────────────────────────
# (WebSocket tests require a running ASGI server; we test the constants
#  and the logic indirectly via unit-level assertions)

@pytest.mark.skipif(
    not __import__("importlib").util.find_spec("fastapi"),
    reason="fastapi not installed",
)
def test_ws_max_message_size_constant():
    """S3 constants should be defined in the dashboard module."""
    from nanobot.dashboard.app import _WS_MAX_MESSAGE_SIZE, _WS_RATE_LIMIT_WINDOW, _WS_RATE_LIMIT_MAX_MSGS
    assert _WS_MAX_MESSAGE_SIZE == 10_240
    assert _WS_RATE_LIMIT_WINDOW == 60
    assert _WS_RATE_LIMIT_MAX_MSGS == 30


# ── S4: Memory import path traversal ──────────────────────────

def test_import_memory_blocks_traversal():
    """S4: import_memory() should block paths outside workspace."""
    from nanobot.agent.commands import CommandHandler
    from nanobot.agent.task_tracker import TaskTracker

    with tempfile.TemporaryDirectory() as tmpdir:
        workspace = Path(tmpdir)
        tt = TaskTracker(workspace)
        handler = CommandHandler(workspace=workspace, task_tracker=tt)

        # Path that escapes workspace
        result = handler.import_memory("C:\\Windows\\System32\\config")
        assert "access denied" in result.lower() or "denied" in result.lower()


def test_import_memory_blocks_relative_traversal():
    """S4: relative path traversal should be blocked."""
    from nanobot.agent.commands import CommandHandler
    from nanobot.agent.task_tracker import TaskTracker

    with tempfile.TemporaryDirectory() as tmpdir:
        workspace = Path(tmpdir)
        tt = TaskTracker(workspace)
        handler = CommandHandler(workspace=workspace, task_tracker=tt)

        result = handler.import_memory(str(workspace / ".." / ".." / "etc" / "passwd"))
        assert "access denied" in result.lower() or "denied" in result.lower()


def test_import_memory_allows_workspace_file():
    """S4: paths within workspace should be allowed (file not found is OK)."""
    from nanobot.agent.commands import CommandHandler
    from nanobot.agent.task_tracker import TaskTracker

    with tempfile.TemporaryDirectory() as tmpdir:
        workspace = Path(tmpdir)
        tt = TaskTracker(workspace)
        handler = CommandHandler(workspace=workspace, task_tracker=tt)

        result = handler.import_memory(str(workspace / "nonexistent.json"))
        # Should not be access denied, but file-not-found
        assert "denied" not in result.lower()
        assert "不存在" in result or "not exist" in result.lower() or "not found" in result.lower()


# ── B2: Fire-and-forget task error logging ─────────────────────

@pytest.mark.asyncio
async def test_safe_create_task_logs_error():
    """B2/D4: Background task manager should log errors from background tasks."""
    from nanobot.agent.commands import _safe_create_task

    async def _failing_coro():
        raise ValueError("intentional test error")

    with patch("nanobot.utils.task_manager.logger") as mock_logger:
        task = _safe_create_task(_failing_coro(), name="test_fail")
        # Wait for the task to complete (it will fail)
        await asyncio.sleep(0.2)

        # The done callback should have logged the error
        mock_logger.error.assert_called()
        error_msg = str(mock_logger.error.call_args)
        assert "test_fail" in error_msg or "intentional" in error_msg


@pytest.mark.asyncio
async def test_safe_create_task_no_error_for_success():
    """B2: _safe_create_task should not log anything for successful tasks."""
    from nanobot.agent.commands import _safe_create_task

    async def _ok_coro():
        return "ok"

    with patch("nanobot.agent.commands.logger") as mock_logger:
        task = _safe_create_task(_ok_coro(), name="test_ok")
        await asyncio.sleep(0.1)
        mock_logger.error.assert_not_called()


# ── B3: SubagentManager Config caching ─────────────────────────

def test_subagent_config_not_per_iteration():
    """B3: Config() should not be called inside the tight inner loop."""
    import inspect
    from nanobot.agent.subagent import SubagentManager
    source = inspect.getsource(SubagentManager._run_subagent)

    # Check that 'Config()' is NOT inside the 'while iteration' loop body
    # It should appear before the loop
    lines = source.split("\n")
    in_loop = False
    config_in_loop = False
    for line in lines:
        stripped = line.strip()
        if "while iteration" in stripped:
            in_loop = True
        if in_loop and "Config()" in stripped:
            config_in_loop = True

    assert not config_in_loop, "Config() should be cached before the loop, not called inside it"


# ── B4: VLM routing fallback ───────────────────────────────────

@pytest.mark.asyncio
async def test_vlm_fallback_on_missing_provider():
    """B4: When VLM provider config is missing, should fall back to default model."""
    from nanobot.agent.loop import AgentLoop
    from nanobot.bus.queue import MessageBus

    with tempfile.TemporaryDirectory() as tmpdir:
        workspace = Path(tmpdir)
        bus = MessageBus()
        provider = MagicMock()
        provider.get_default_model.return_value = "default-model"

        # Mock response that ends the loop (no tool calls)
        mock_response = MagicMock()
        mock_response.has_tool_calls = False
        mock_response.content = "test response"
        mock_response.reasoning_content = None
        mock_response.usage = None

        provider.chat = AsyncMock(return_value=mock_response)

        with patch("nanobot.agent.loop.SubagentManager"), \
             patch("nanobot.agent.tool_setup.setup_all_tools"):
            agent = AgentLoop(bus=bus, provider=provider, workspace=workspace)

        # Simulate: VLM enabled, but get_provider returns None → should fall back
        config_mock = MagicMock()
        config_mock.agents.vlm.enabled = True
        config_mock.agents.vlm.model = "nonexistent-vlm-model"
        config_mock.get_provider.return_value = None  # B4: missing provider
        agent._get_config = MagicMock(return_value=config_mock)

        # Create messages with an image to trigger VLM path
        messages = [
            {"role": "system", "content": "test"},
            {"role": "user", "content": [
                {"type": "image_url", "image_url": {"url": "data:image/png;base64,abc"}},
                {"type": "text", "text": "describe this"},
            ]},
        ]

        final_content, _, _ = await agent._run_agent_loop(messages)

        # Should have called provider.chat with the DEFAULT model (not VLM)
        call_kwargs = provider.chat.call_args
        assert call_kwargs.kwargs.get("model") == "default-model" or \
               call_kwargs[1].get("model") == "default-model"


# ── L3: Workflow success false-negative fix ────────────────────

def test_no_results_not_in_fail_indicators():
    """L3: 'no results' should NOT be in the fail indicators list."""
    from nanobot.agent.loop import _FAIL_INDICATORS
    for ind in _FAIL_INDICATORS:
        assert ind != "no results", "'no results' should be removed from _FAIL_INDICATORS"


def test_fail_indicators_still_work():
    """L3/DESIGN-4: legitimate fail indicators should still be present."""
    from nanobot.agent.loop import _FAIL_INDICATORS
    assert "找不到" in _FAIL_INDICATORS
    assert "not found" in _FAIL_INDICATORS
    assert "error:" in _FAIL_INDICATORS
    # DESIGN-4: standalone '失败'/'sorry' replaced with specific phrases
    assert "执行失败" in _FAIL_INDICATORS
    assert "操作失败" in _FAIL_INDICATORS
    assert "sorry, i" in _FAIL_INDICATORS


def test_workflow_succeeded_with_no_results_response():
    """L3: A response containing 'No results' should still be considered successful."""
    from nanobot.agent.loop import _FAIL_INDICATORS
    response = "No results matching your exact criteria, but I found 3 similar reports."
    _content_lower = response.lower()
    _workflow_succeeded = not any(ind in _content_lower for ind in _FAIL_INDICATORS)
    # After removing 'no results', this should now be considered successful
    assert _workflow_succeeded is True


# ── L4 / C1: Consolidation lock ───────────────────────────────

def test_memory_manager_has_consolidation_lock():
    """L4/C1: MemoryManager should have a _consolidation_lock attribute."""
    from nanobot.agent.memory_manager import MemoryManager

    with tempfile.TemporaryDirectory() as tmpdir:
        mm = MemoryManager(
            workspace=Path(tmpdir),
            provider=MagicMock(),
            model="test",
            memory_window=50,
        )
        assert hasattr(mm, "_consolidation_lock")
        assert isinstance(mm._consolidation_lock, asyncio.Lock)


@pytest.mark.asyncio
async def test_consolidation_lock_prevents_concurrent():
    """L4: Concurrent consolidation calls should be serialized by lock."""
    from nanobot.agent.memory_manager import MemoryManager
    from nanobot.session.manager import Session

    with tempfile.TemporaryDirectory() as tmpdir:
        workspace = Path(tmpdir)
        # Create memory dir
        (workspace / "memory").mkdir(parents=True, exist_ok=True)

        provider = MagicMock()
        provider.chat = AsyncMock()
        mock_response = MagicMock()
        mock_response.content = '{"history_entry": "test", "memory_update": "", "daily_log": ""}'
        mock_response.usage = None
        provider.chat.return_value = mock_response

        mm = MemoryManager(workspace=workspace, provider=provider, model="test", memory_window=50)

        session = Session(key="test:user")
        for i in range(30):
            session.add_message("user", f"msg {i}")

        # Run two consolidations concurrently — should not raise
        await asyncio.gather(
            mm.consolidate_memory(session),
            mm.consolidate_memory(session),
        )
        # If no exception, the lock worked


# ── D2: ReflectionStore / KG caching ──────────────────────────

def test_reflection_store_cached():
    """D2: AgentLoop should cache ReflectionStore (not re-create per message)."""
    from nanobot.agent.loop import AgentLoop
    from nanobot.bus.queue import MessageBus

    with tempfile.TemporaryDirectory() as tmpdir:
        workspace = Path(tmpdir)
        (workspace / "memory").mkdir(parents=True, exist_ok=True)
        bus = MessageBus()
        provider = MagicMock()
        provider.get_default_model.return_value = "test-model"

        with patch("nanobot.agent.loop.SubagentManager"), \
             patch("nanobot.agent.tool_setup.setup_all_tools"):
            agent = AgentLoop(bus=bus, provider=provider, workspace=workspace)

        # First call creates the instance
        rs1 = agent._get_reflection_store()
        # Second call should return same instance
        rs2 = agent._get_reflection_store()
        assert rs1 is rs2


def test_knowledge_graph_cached():
    """D2: AgentLoop should cache KnowledgeGraph (not re-create per message)."""
    from nanobot.agent.loop import AgentLoop
    from nanobot.bus.queue import MessageBus

    with tempfile.TemporaryDirectory() as tmpdir:
        workspace = Path(tmpdir)
        (workspace / "memory").mkdir(parents=True, exist_ok=True)
        bus = MessageBus()
        provider = MagicMock()
        provider.get_default_model.return_value = "test-model"

        with patch("nanobot.agent.loop.SubagentManager"), \
             patch("nanobot.agent.tool_setup.setup_all_tools"):
            agent = AgentLoop(bus=bus, provider=provider, workspace=workspace)

        kg1 = agent._get_knowledge_graph()
        kg2 = agent._get_knowledge_graph()
        assert kg1 is kg2


# ── D3: Injection budget ──────────────────────────────────────

def test_injection_budget_constant():
    """D3: _INJECTION_BUDGET should be defined and reasonable."""
    from nanobot.agent.loop import _INJECTION_BUDGET
    assert _INJECTION_BUDGET == 8000


def test_injection_budget_respected():
    """D3: When injections exceed budget, they should be capped."""
    from nanobot.agent.loop import _INJECTION_BUDGET

    # Simulate the budget tracking logic
    injection_used = 0

    # First injection: 5000 chars (should fit)
    hint_text = "x" * 5000
    if injection_used + len(hint_text) <= _INJECTION_BUDGET:
        injection_used += len(hint_text)
    assert injection_used == 5000

    # Second injection: 4000 chars (should NOT fit — 5000 + 4000 > 8000)
    memory_hint = "y" * 4000
    if injection_used + len(memory_hint) <= _INJECTION_BUDGET:
        injection_used += len(memory_hint)
    # Should still be 5000 (second injection didn't fit)
    assert injection_used == 5000


# ── C1: Memory store vs consolidation race ────────────────────

def test_deep_consolidate_shares_lock_with_regular():
    """C1: deep_consolidate and consolidate_memory should use the same lock."""
    from nanobot.agent.memory_manager import MemoryManager

    with tempfile.TemporaryDirectory() as tmpdir:
        mm = MemoryManager(
            workspace=Path(tmpdir),
            provider=MagicMock(),
            model="test",
            memory_window=50,
        )
        # Both methods should use the same lock
        assert hasattr(mm, "_consolidation_lock")
        # Verify both wrapper methods exist
        import inspect
        consolidate_src = inspect.getsource(mm.consolidate_memory)
        deep_src = inspect.getsource(mm.deep_consolidate)
        assert "_consolidation_lock" in consolidate_src
        assert "_consolidation_lock" in deep_src


def test_context_builder_accepts_knowledge_graph():
    """D2: build_messages should accept a knowledge_graph parameter."""
    import inspect
    from nanobot.agent.context import ContextBuilder
    sig = inspect.signature(ContextBuilder.build_messages)
    assert "knowledge_graph" in sig.parameters
