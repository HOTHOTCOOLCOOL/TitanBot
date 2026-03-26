"""Tests for Plugin lifecycle hooks (A29).

Covers:
- Basic setup/teardown method calls
- Reload flow: teardown old → setup new
"""

import asyncio
import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from nanobot.agent.tools.base import Tool
from nanobot.agent.tools.registry import ToolRegistry


class DummyLifecycleTool(Tool):
    def __init__(self):
        self.setup_called = 0
        self.teardown_called = 0
        self.call_order = []
        
    @property
    def name(self) -> str:
        return "dummy_lifecycle"

    @property
    def description(self) -> str:
        return "Dummy"

    @property
    def parameters(self) -> dict:
        return {"type": "object", "properties": {}, "required": []}
        
    async def setup(self) -> None:
        self.setup_called += 1
        self.call_order.append("setup")
        
    async def teardown(self) -> None:
        self.teardown_called += 1
        self.call_order.append("teardown")

    async def execute(self, **kwargs) -> str:
        return "ok"


@pytest.mark.asyncio
async def test_tool_lifecycle_methods():
    tool = DummyLifecycleTool()
    assert tool.setup_called == 0
    assert tool.teardown_called == 0
    
    await tool.setup()
    assert tool.setup_called == 1
    
    await tool.teardown()
    assert tool.teardown_called == 1


@pytest.mark.asyncio
async def test_base_tool_lifecycle_noop():
    """Base Tool setup/teardown are no-ops (should not raise)."""
    class MinimalTool(Tool):
        @property
        def name(self): return "minimal"
        @property
        def description(self): return "minimal"
        @property
        def parameters(self): return {"type": "object", "properties": {}}
        async def execute(self, **kwargs): return "ok"
    
    tool = MinimalTool()
    await tool.setup()     # should not raise
    await tool.teardown()  # should not raise


@pytest.mark.asyncio
async def test_reload_calls_teardown_then_setup():
    """Verify _reload_dynamic_tools calls teardown on old plugins and setup on new ones."""
    from nanobot.agent.tool_setup import _reload_dynamic_tools
    from types import SimpleNamespace
    
    # Create a mock agent with existing dynamic tools
    old_tool = DummyLifecycleTool()
    registry = ToolRegistry()
    registry.register(old_tool)
    
    fake_workspace = MagicMock()
    fake_workspace.__truediv__ = MagicMock(return_value=MagicMock(exists=MagicMock(return_value=False)))
    
    agent = SimpleNamespace(
        tools=registry,
        _dynamic_tool_names=["dummy_lifecycle"],
        workspace=fake_workspace,
    )
    
    # Mock scan_plugins to return a new tool with the same name
    new_tool = DummyLifecycleTool()
    
    # Don't mock unload_plugins — let real unregistration happen
    with patch("nanobot.agent.tool_setup.scan_plugins", return_value=[new_tool]):
        await _reload_dynamic_tools(agent)
    
    # Old tool should have teardown called
    assert old_tool.teardown_called == 1
    # New tool should have setup called
    assert new_tool.setup_called == 1
    # Teardown should happen before setup (order matters)
    assert old_tool.call_order == ["teardown"]
    assert new_tool.call_order == ["setup"]


@pytest.mark.asyncio
async def test_reload_teardown_failure_does_not_block():
    """If teardown raises, the reload should continue gracefully."""
    from nanobot.agent.tool_setup import _reload_dynamic_tools
    from types import SimpleNamespace
    
    class FailTeardownTool(Tool):
        @property
        def name(self): return "fail_teardown"
        @property
        def description(self): return "will fail teardown"
        @property
        def parameters(self): return {"type": "object", "properties": {}}
        async def execute(self, **kwargs): return "ok"
        async def teardown(self):
            raise RuntimeError("teardown exploded")
    
    bad_tool = FailTeardownTool()
    registry = ToolRegistry()
    registry.register(bad_tool)
    
    fake_workspace = MagicMock()
    fake_workspace.__truediv__ = MagicMock(return_value=MagicMock(exists=MagicMock(return_value=False)))
    
    agent = SimpleNamespace(
        tools=registry,
        _dynamic_tool_names=["fail_teardown"],
        workspace=fake_workspace,
    )
    
    new_tool = DummyLifecycleTool()
    
    with patch("nanobot.agent.tool_setup.scan_plugins", return_value=[new_tool]):
        # Should NOT raise even though teardown failed
        await _reload_dynamic_tools(agent)
    
    # New tool should still have setup called
    assert new_tool.setup_called == 1


@pytest.mark.asyncio
async def test_reload_setup_failure_does_not_block():
    """If setup raises on a new plugin, other plugins should still load."""
    from nanobot.agent.tool_setup import _reload_dynamic_tools
    from types import SimpleNamespace
    
    class FailSetupTool(Tool):
        @property
        def name(self): return "fail_setup"
        @property
        def description(self): return "will fail setup"
        @property
        def parameters(self): return {"type": "object", "properties": {}}
        async def execute(self, **kwargs): return "ok"
        async def setup(self):
            raise RuntimeError("setup exploded")
    
    bad_new = FailSetupTool()
    good_new = DummyLifecycleTool()
    
    registry = ToolRegistry()
    fake_workspace = MagicMock()
    fake_workspace.__truediv__ = MagicMock(return_value=MagicMock(exists=MagicMock(return_value=False)))
    
    agent = SimpleNamespace(
        tools=registry,
        _dynamic_tool_names=[],
        workspace=fake_workspace,
    )
    
    with patch("nanobot.agent.tool_setup.scan_plugins", return_value=[bad_new, good_new]):
        await _reload_dynamic_tools(agent)
    
    # Both tools should be registered even if bad_new.setup failed
    assert registry.has("fail_setup")
    assert registry.has("dummy_lifecycle")
    # Good tool's setup should still succeed
    assert good_new.setup_called == 1

