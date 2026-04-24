import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from pathlib import Path
from dataclasses import dataclass
import json

from nanobot.agent.loop import AgentLoop, LoopResult
from nanobot.agent.state_handler import StateHandler
from nanobot.session.manager import Session
from nanobot.bus.events import InboundMessage
from nanobot.bus.queue import MessageBus

@pytest.fixture
def mock_agent():
    agent = MagicMock()
    agent.sessions = MagicMock()
    agent._set_tool_context = MagicMock()
    agent.context = MagicMock()
    agent.context.build_messages = MagicMock(return_value=[{"role": "user", "content": "hi"}])
    return agent

@pytest.mark.asyncio
async def test_process_direct_plain_text():
    """1. Legal plain text direct return for process_direct"""
    bus = MessageBus()
    agent = AgentLoop(
        model="gpt-4",
        provider=AsyncMock(),
        workspace=Path("."),
        bus=bus
    )
    # Patch out the underlying run to quickly assert direct iteration path
    with patch.object(
        agent,
        "_run_agent_loop_v2",
        new_callable=AsyncMock,
        return_value=LoopResult(
            final_content="plain text response",
            tools_used=[],
            tool_calls_with_args=[]
        )
    ) as mock_loop:
        result = await agent.process_direct(
            content="hello",
            channel="api"
        )
        assert result == "plain text response"

@pytest.mark.asyncio
async def test_process_direct_tool_then_text():
    """2. Normal convergence of tool -> text, proving real LoopResult logic."""
    bus = MessageBus()
    agent = AgentLoop(
        model="gpt-4",
        provider=AsyncMock(),
        workspace=Path("."),
        bus=bus
    )
    
    from nanobot.providers.base import LLMResponse
    # First turn: LLM calls a tool. Second turn: LLM returns text.
    mock_tool = MagicMock()
    mock_tool.id = "call_x"
    mock_tool.name = "mock_tool"
    mock_tool.arguments = {"a": 1}
    call1 = LLMResponse(content="", tool_calls=[mock_tool])
    call2 = LLMResponse(content="Final truth output", tool_calls=[])
    
    mock_llm = AsyncMock(side_effect=[call1, call2, call2])
    
    # Needs valid tool registration to avoid pipeline exception
    agent.tools.registry = {"mock_tool": MagicMock()}
    # Mock tool execution to just return string so no crash
    agent.tools.execute = AsyncMock(return_value="tool output success")
    
    with patch.object(agent, "_call_llm_for_turn", mock_llm):
        result = await agent.process_direct(
            content="do tool please",
            channel="api",
            session_key="api:user"
        )
        assert "Final truth output" in result
        assert agent.sessions.get_or_create("api:user").pending_save

@pytest.mark.asyncio
async def test_system_message_convergence(mock_agent):
    """3. handle_system_message convergence"""
    handler = StateHandler(mock_agent)
    
    mock_agent._run_agent_loop = AsyncMock(
        return_value=LoopResult(
            final_content="Got system message",
            tools_used=[],
            tool_calls_with_args=[]
        )
    )
    
    session_mock = MagicMock()
    # Ensure role mapping isn't failing on tools
    session_mock.messages = []
    def add_message(*args, **kwargs):
        pass
    session_mock.add_message = add_message
    
    # Mock get_or_create properly
    mock_agent.sessions.get_or_create.return_value = session_mock
    
    msg = InboundMessage(channel="system", chat_id="system1", content="Alert!", sender_id="system")
    
    result = await handler.handle_system_message(msg)
    
    assert result.content == "Got system message"
    assert result.channel == "cli"

@pytest.mark.asyncio
async def test_pending_approval_convergence(mock_agent):
    """4. handle_pending_approval convergence recovery chain"""
    handler = StateHandler(mock_agent)
    
    session = Session(key="user:123")
    session.pending_approval_task = {
        "tool": "delete_all",
        "arguments": {},
        "id": "tc_001"
    }
    
    # We approved the destructive trace
    mock_agent.tools.execute = AsyncMock(return_value="Deleted files")
    
    mock_agent._run_agent_loop = AsyncMock(
        return_value=LoopResult(
            final_content="Approved text",
            tools_used=["delete_all"],
            tool_calls_with_args=[{"tool": "delete_all", "args": {}}]
        )
    )
    
    # Needs auth store logic bypassed gracefully or mocked
    mock_agent._get_approval_store.return_value = MagicMock()
    
    msg = InboundMessage(channel="user", chat_id="123", content="approve", sender_id="user")
    
    result = await handler.handle_pending_approval(session, msg, "approve")
    
    assert result.content == "Approved text"
    assert session.pending_approval_task is None

@pytest.mark.asyncio
async def test_middleware_abort_maps_to_exit_kind():
    """5. Generic abort correctly maps to ExitKind.ABORT."""
    from nanobot.agent.middleware.base import TurnContext, TurnAction
    from nanobot.agent.loop import AgentLoop
    
    agent = AgentLoop(model="gpt-4", provider=AsyncMock(), workspace=Path("."), bus=MessageBus())
    
    # Mock LLM to return one message with a tool call so it reaches the pipeline
    from nanobot.providers.base import LLMResponse
    mock_tool = MagicMock()
    mock_tool.id = "call_x"
    mock_tool.name = "mock_tool"
    mock_tool.arguments = {}
    agent._call_llm_for_turn = AsyncMock(return_value=LLMResponse(content="llm response", tool_calls=[mock_tool]))
    
    # Inject a middleware that aborts
    class AbortMiddleware:
        async def pre_process(self, ctx: TurnContext) -> None:
            ctx.abort("flood_guard", "You are sending too many messages")
        async def post_process(self, ctx: TurnContext) -> None:
            pass

    agent._get_middleware_pipeline = MagicMock()
    
    # Setup mock pipeline
    pipeline = MagicMock()
    pipeline.run_turn = AsyncMock(side_effect=lambda ctx: ctx.abort("flood_guard", "You are sending too many messages"))
    agent._get_middleware_pipeline.return_value = pipeline
    
    result = await agent._run_agent_loop_v2(initial_messages=[{"role": "user", "content": "hi"}], channel="api", chat_id="123")
    
    assert result.exit_kind == "abort"
    assert result.action_reason == "flood_guard"
    assert result.final_content == "You are sending too many messages"

@pytest.mark.asyncio
async def test_process_direct_abort_omits_save_prompt():
    """6. Generic abort (from flood_guard or fuzzy_loop) omits pending_save."""
    agent = AgentLoop(model="gpt-4", provider=AsyncMock(), workspace=Path("."), bus=MessageBus())
    
    # Simulate a loop run that ends with exit_kind="abort" with tool calls
    with patch.object(
        agent,
        "_run_agent_loop_v2",
        new_callable=AsyncMock,
        return_value=LoopResult(
            final_content="Aborted by duplicate_loop",
            tools_used=["mock_tool"],
            tool_calls_with_args=[{"tool": "mock_tool", "args": {}}],
            action_reason="duplicate_loop",
            exit_kind="abort"
        )
    ):
        result = await agent.process_direct(
            content="do loop",
            channel="api",
            session_key="api:user2"
        )
        assert "Aborted by duplicate_loop" in result
        session = agent.sessions.get_or_create("api:user2")
        # Ensure pending_save is not populated because exit_kind="abort"
        assert not session.pending_save
