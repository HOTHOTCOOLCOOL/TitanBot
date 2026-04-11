import pytest
import asyncio
from unittest.mock import patch, MagicMock, AsyncMock
from pathlib import Path
from nanobot.agent.coordinator import CoordinatorManager

@pytest.fixture
def mock_workspace(tmp_path):
    return tmp_path

@pytest.fixture
def coordinator(mock_workspace):
    bus_mock = MagicMock()
    # Provide a mock bus
    return CoordinatorManager(
        workspace=mock_workspace,
        bus=bus_mock,
        provider=MagicMock(),
        enabled=True,
        max_workers=2
    )

@pytest.mark.asyncio
async def test_spawn_worker_success(coordinator):
    with patch('nanobot.agent.coordinator.subprocess.Popen') as mock_popen:
        # Mock the process running
        mock_process = MagicMock()
        mock_process.pid = 9999
        mock_process.poll.return_value = None
        # Mock stdout returning the port line
        mock_process.stdout = ["WORKER_READY:12345\n"]
        mock_popen.return_value = mock_process
        
        with patch('aiohttp.ClientSession.post') as mock_post:
            mock_cm = MagicMock()
            mock_post.return_value = mock_cm
            mock_post_resp = AsyncMock()
            mock_post_resp.status = 200
            mock_cm.__aenter__.return_value = mock_post_resp
            
            with patch('asyncio.create_task') as mock_create_task:
                result = await coordinator.spawn("compute pi", label="pi-calc")
                
                assert "Worker [pi-calc] started" in result
                assert len(coordinator.workers) == 1
                task_id = list(coordinator.workers.keys())[0]
                assert coordinator.workers[task_id]['port'] == 12345
                
                # Check HTTP POST was sent
                mock_post.assert_called_once()
                args, kwargs = mock_post.call_args
                assert "http://127.0.0.1:12345/task" in args[0]
                assert kwargs['json']['task'] == "compute pi"

@pytest.mark.asyncio
async def test_spawn_limit_reached(coordinator):
    coordinator.workers["dummy1"] = {"process": MagicMock()}
    coordinator.workers["dummy1"]["process"].poll.return_value = None
    coordinator.workers["dummy2"] = {"process": MagicMock()}
    coordinator.workers["dummy2"]["process"].poll.return_value = None
    
    result = await coordinator.spawn("over max limit")
    assert "Maximum worker limit (2) reached" in result
