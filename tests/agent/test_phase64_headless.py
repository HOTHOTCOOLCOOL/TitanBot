import pytest
from pathlib import Path
from unittest.mock import AsyncMock, patch, MagicMock

from nanobot.agent.loop import AgentLoop
from nanobot.bus.queue import MessageBus
from nanobot.agent.capability import CapabilityTag
from nanobot.providers.base import LLMResponse, ToolCallRequest
from nanobot.utils.trace_context import InterceptTag
from nanobot.agent.verification import RuleResult

@pytest.mark.asyncio
async def test_headless_process_direct_integration(tmp_path: Path):
    """Test full integration chain process_direct -> _process_message -> _run_agent_loop_v2 -> middleware aborts."""
    bus = MagicMock()
    
    agent = AgentLoop(workspace=tmp_path, bus=bus, provider=MagicMock())

    call_count = 0
    async def fake_call_llm(messages, *args, **kwargs):
        nonlocal call_count
        call_count += 1
        # Always stubbornly return the dangerous tool
        return LLMResponse(content="", tool_calls=[ToolCallRequest(id="call_1", name="write_file", arguments={"path": "C:\\Windows\\System32\\test.txt"})])
            
    agent._call_llm_for_turn = fake_call_llm

    class FakeImpl:
        name = "write_file"

        def get_effective_tags(self, args, config_override=None):
            return CapabilityTag.IS_HIGH_RISK

        async def evaluate_dynamic_tags(self, action: 'TurnAction', context: 'TurnContext') -> CapabilityTag:
             return CapabilityTag.IS_HIGH_RISK

        def to_schema(self):
             return {}

        def __call__(self, *args, **kwargs):
             pass
    
    fi = FakeImpl()
    agent.tools._tools = {"write_file": fi}
    agent.tools.dispatch = AsyncMock(return_value=None)
    
    # Mock approval store
    approval_store_mock = MagicMock()
    approval_store_mock.is_approved.return_value = False
    agent._get_approval_store = MagicMock(return_value=approval_store_mock)

    # Mock validation to explicitly pass, bypassing L1 generic error to reach HITL explicitly
    verification_mock = MagicMock()
    verification_mock.check_rules.return_value = RuleResult(passed=True, violations=[], rewrite_hint="")
    agent._get_verification = MagicMock(return_value=verification_mock)
    
    result = await agent.process_direct(
        content="do high risk stuff", 
        channel="api",  # This triggers the automatic is_headless=True inside TurnContext
        session_key="api:test"
    )

    # Middleware will abort the turn entirely, bypassing the ToolExecutor.
    assert agent.tools.dispatch.call_count == 0
    
    # The agent loop should immediately abort on the first encounter with the high-risk tool
    # in headless mode, breaking the while loop due to 'fatal_violation' instead of letting it retry.
    assert call_count == 1

    # The result output must explicitly contain the headless failure string
    assert "HITL_REQUIRED_IN_HEADLESS" in result

    # Phase 64 Iteration 3 assertion: Verify the generated output doesn't disguise
    # the failure and prevents the pending save workflow.
    assert "Save this task" not in result
    session = agent.sessions._cache.get(agent.sessions.resolve_key("api:test"))
    assert hasattr(session, "pending_save"), "Session must exist and have attributes."
    assert not session.pending_save
