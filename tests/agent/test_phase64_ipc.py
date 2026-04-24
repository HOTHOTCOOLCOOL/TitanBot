# test_phase64_ipc.py
import pytest
from pathlib import Path
from unittest.mock import AsyncMock, patch, MagicMock

from nanobot.bus.queue import MessageBus
from nanobot.agent.subagent import SubagentManager
from nanobot.agent.ipc_utils import _MAX_IPC_PAYLOAD_BYTES

@pytest.mark.asyncio
async def test_ipc_subagent_integration_barrier(tmp_path: Path):
    """Test standard payloads are naturally truncated during Subagent return architecture."""
    bus = MessageBus()
    
    class FakeAgent:
        def __init__(self):
            self.knowledge_workflow = MagicMock()
            self.knowledge_workflow.knowledge_store = None
        async def _run_agent_loop(self, *args, **kwargs):
            print("==== FAKE AGENT CALLED ====")
            from nanobot.agent.loop import LoopResult
            return LoopResult(final_content="X" * (_MAX_IPC_PAYLOAD_BYTES + 1024), tools_used=[], action_reason=None)

    mgr = SubagentManager(
        workspace=tmp_path,
        bus=bus,
        provider=AsyncMock(), # provide a mock provider to satisfy constructor
    )
    mgr.agent_loop_ref = FakeAgent()
    
    # Mock announce result to intercept
    mgr._announce_result = AsyncMock()
    
    task_id = "test_sub_ipc"
    await mgr._run_subagent(task_id, "label", "massive-task", {})
    
    mgr._announce_result.assert_called_once()
    announced_result = mgr._announce_result.call_args[0][3]
    print(f"==== ANNOUNCED RESULT: {announced_result[:100]} ====")
    assert len(announced_result.encode('utf-8')) <= _MAX_IPC_PAYLOAD_BYTES
    assert "truncated preview" in announced_result
    
    # Ensure physical spill writes directly to private space
    sandbox = tmp_path / "workers" / "test_sub_ipc"
    spilled_files = list(sandbox.glob("large_SubagentManager_output_*.txt"))
    assert len(spilled_files) == 1
    
    # Verify warning notice generates exact structural provenance map relative to workspace
    assert "workers/test_sub_ipc/large_SubagentManager_output" in announced_result

from nanobot.agent.worker_process import WorkerNode
from nanobot.agent.coordinator import CoordinatorManager
from unittest.mock import patch, MagicMock, AsyncMock

@pytest.mark.asyncio
async def test_ipc_worker_process_boundary_e2e(tmp_path: Path):
    """Test full E2E string truncation spanning from WorkerNode execution to Coordinator poll."""
    worker = WorkerNode(port=0, token="test-token", workspace_path=tmp_path)
    
    async def mock_run_agent_loop(*args, **kwargs):
        from nanobot.agent.ipc_utils import _MAX_IPC_PAYLOAD_BYTES
        from nanobot.agent.loop import LoopResult
        # Return 5 elements: final_content, tools_used, tool_calls_with_args, milestone, action_reason
        return LoopResult(final_content="X" * (_MAX_IPC_PAYLOAD_BYTES + 1024), tools_used=[], action_reason=None)
        
    # Execute the internal logic which inherently runs enforce_ipc_limit
    with patch("nanobot.agent.loop.AgentLoop._run_agent_loop_v2", new=mock_run_agent_loop):
        await worker._execute_agent_loop(
            task_id="test1234",
            task="do something",
            trace_id="no-trace",
            model="gpt-4",
            temperature=0,
            max_tokens=100,
            brave_api_key=None
        )
        
    assert worker.status == "completed"
    
    # Start web server to route Coordinator properly
    from aiohttp import web
    app = web.Application()
    app.router.add_get('/result', worker.handle_result)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '127.0.0.1', 0)
    await site.start()
    
    # Dynamically fetched active port
    port = runner.addresses[0][1]

    coordinator = CoordinatorManager(workspace=tmp_path, bus=MagicMock(), enabled=True)
    coordinator._announce_result = AsyncMock()
    mock_process = MagicMock()
    mock_process.poll.return_value = None
    coordinator.workers["test1234"] = {
        "port": port,
        "token": "test-token",
        "process": mock_process
    }
    
    # Process the poll
    with patch("asyncio.sleep", new_callable=AsyncMock):
        await coordinator._poll_worker_status("test1234", "lbl", "tsk", {})
        
    await runner.cleanup()
    
    assert coordinator._announce_result.call_count == 1
    args, kwargs = coordinator._announce_result.call_args
    final_result = args[3]
    
    from nanobot.agent.ipc_utils import _MAX_IPC_PAYLOAD_BYTES
    assert len(final_result.encode("utf-8")) <= _MAX_IPC_PAYLOAD_BYTES
    assert "truncated" in final_result
