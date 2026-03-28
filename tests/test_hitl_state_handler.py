import pytest
from unittest.mock import AsyncMock, MagicMock
from nanobot.agent.state_handler import StateHandler
from nanobot.session.manager import Session
from nanobot.bus.events import InboundMessage

@pytest.mark.asyncio
async def test_state_handler_approve_always():
    session = Session(key="test:1")
    session.pending_approval_task = {
        "tool": "exec",
        "arguments": {"command": "rm -rf /"},
        "id": "tc_123"
    }

    mock_agent = MagicMock()
    mock_agent.memory_window = 10
    mock_agent._set_tool_context = MagicMock()
    mock_agent.tools.execute = AsyncMock(return_value="Success")
    mock_agent._run_agent_loop = AsyncMock(return_value=("final text", ["exec"], [{"tool": "exec", "args": {}}]))
    
    mock_auth_store = MagicMock()
    mock_agent._get_approval_store.return_value = mock_auth_store

    handler = StateHandler(mock_agent)
    msg = InboundMessage(channel="test", chat_id="1", content="always", sender_id="user1")

    result = await handler.handle_pending_approval(session, msg, "always")

    # Assert pending state cleared
    assert session.pending_approval_task is None

    # Assert auth store recorded "always"
    mock_auth_store.add_approval.assert_called_once_with("exec", "")

    # Assert tool executed
    mock_agent.tools.execute.assert_called_once_with("exec", {"command": "rm -rf /"})

    # Assert loop resumed
    mock_agent._run_agent_loop.assert_called_once()
    assert result.content == "final text"

@pytest.mark.asyncio
async def test_state_handler_reject():
    session = Session(key="test:1")
    session.pending_approval_task = {
        "tool": "exec",
        "arguments": {"command": "rm -rf /"},
        "id": "tc_123"
    }

    mock_agent = MagicMock()
    mock_agent.memory_window = 10
    mock_agent._set_tool_context = MagicMock()
    mock_agent.tools.execute = AsyncMock()
    mock_agent._run_agent_loop = AsyncMock(return_value=("rejected text", [], []))

    handler = StateHandler(mock_agent)
    msg = InboundMessage(channel="test", chat_id="1", content="reject", sender_id="user1")

    result = await handler.handle_pending_approval(session, msg, "reject")

    # Assert pending state cleared
    assert session.pending_approval_task is None

    # Assert tool NOT executed
    mock_agent.tools.execute.assert_not_called()

    # Verify synthetic error inserted into session
    added_tool_msg = session.messages[-1]
    assert added_tool_msg["role"] == "assistant"
    assert session.messages[-2]["content"] == "Error: Execution blocked by user rejection."
    
    assert result.content == "rejected text"
