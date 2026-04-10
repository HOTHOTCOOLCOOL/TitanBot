import pytest
import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

from nanobot.agent.subagent import SubagentManager
from nanobot.agent.tools.registry import ToolRegistry
from nanobot.providers.base import LLMProvider
from nanobot.bus.queue import MessageBus

class MockAgentLoop:
    def __init__(self):
        self.call_args = []
        
    async def _run_agent_loop(self, messages, channel, chat_id, tool_registry_override=None):
        self.call_args.append({
            "messages": messages,
            "channel": channel,
            "chat_id": chat_id,
            "tool_registry_override": tool_registry_override
        })
        return "mock_result", [], []


@pytest.fixture
def mock_deps(tmp_path):
    provider = MagicMock(spec=LLMProvider)
    provider.get_default_model.return_value = "mock-model"
    bus = MagicMock(spec=MessageBus)
    bus.publish_inbound = AsyncMock()
    return provider, bus, tmp_path


@pytest.mark.asyncio
async def test_subagent_uses_agent_loop_facade(mock_deps):
    provider, bus, workspace = mock_deps
    
    manager = SubagentManager(
        provider=provider,
        workspace=workspace,
        bus=bus,
        agent_loop_ref=MockAgentLoop()
    )
    
    await manager.spawn("Test task", "Test label")
    
    # Wait for the background task to complete
    for _ in range(10):
        if not manager.get_running_count():
            break
        await asyncio.sleep(0.01)
        
    # Check if _run_agent_loop was called
    assert len(manager.agent_loop_ref.call_args) == 1
    call = manager.agent_loop_ref.call_args[0]
    
    assert call["channel"] == "system"
    assert call["chat_id"].startswith("worker:")
    
    # Verify the restricted tool registry
    registry = call["tool_registry_override"]
    assert isinstance(registry, ToolRegistry)
    
    # Ensure exec tool is NOT present
    assert registry.get("exec") is None
    assert registry.get("coordinator") is None
    assert registry.get("message") is None
    assert registry.get("spawn") is None
    
    # Ensure authorized tools are present
    assert registry.get("read_file") is not None
    assert registry.get("write_file") is not None
    assert registry.get("web_search") is not None

@pytest.mark.asyncio
async def test_subagent_without_agent_loop_ref(mock_deps):
    provider, bus, workspace = mock_deps
    
    # Intentionally omitted agent_loop_ref
    manager = SubagentManager(
        provider=provider,
        workspace=workspace,
        bus=bus
    )
    
    await manager.spawn("Test task")
    
    for _ in range(10):
        if not manager.get_running_count():
            break
        await asyncio.sleep(0.01)
        
    # The subagent should have caught an exception and reported error because agent_loop_ref is missing
    bus.publish_inbound.assert_called()
    msg = bus.publish_inbound.call_args[0][0]
    assert "[Subagent '" in msg.content
    assert "failed" in msg.content
    assert "Error:" in msg.content
