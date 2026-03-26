"""Tests for Code Review Phase 30 High-priority fixes: BUG-3 + BP-3."""

import asyncio
import os
import pytest
from typing import Any
from unittest.mock import patch, AsyncMock, MagicMock

from nanobot.agent.tools.base import Tool
from nanobot.agent.tools.registry import ToolRegistry
from nanobot.config.schema import Config
from nanobot.agent.sandbox import ShellSandbox, PythonSandbox


# ---------------------------------------------------------------------------
# BP-3: Tool execution unified timeout
# ---------------------------------------------------------------------------

class FastTool(Tool):
    @property
    def name(self) -> str:
        return "fast_tool"

    @property
    def description(self) -> str:
        return "Returns immediately"

    @property
    def parameters(self) -> dict[str, Any]:
        return {"type": "object", "properties": {}}

    async def execute(self, **kwargs: Any) -> str:
        return "done"


class SlowTool(Tool):
    @property
    def name(self) -> str:
        return "slow_tool"

    @property
    def description(self) -> str:
        return "Takes too long"

    @property
    def parameters(self) -> dict[str, Any]:
        return {"type": "object", "properties": {}}

    @property
    def execution_timeout(self) -> int | None:
        return 1  # 1 second

    async def execute(self, **kwargs: Any) -> str:
        await asyncio.sleep(10)
        return "should not reach"


class NoTimeoutTool(Tool):
    @property
    def name(self) -> str:
        return "no_timeout_tool"

    @property
    def description(self) -> str:
        return "No timeout limit"

    @property
    def parameters(self) -> dict[str, Any]:
        return {"type": "object", "properties": {}}

    @property
    def execution_timeout(self) -> int | None:
        return None  # Disable timeout

    async def execute(self, **kwargs: Any) -> str:
        return "unlimited"


@pytest.mark.asyncio
async def test_fast_tool_executes_normally():
    """Tool with default timeout should execute normally when fast."""
    reg = ToolRegistry()
    reg.register(FastTool())
    result = await reg.execute("fast_tool", {})
    assert result == "done"


@pytest.mark.asyncio
async def test_slow_tool_times_out():
    """Tool that exceeds its timeout should return a timeout error."""
    reg = ToolRegistry()
    reg.register(SlowTool())
    result = await reg.execute("slow_tool", {})
    assert "timed out" in result
    assert "1 seconds" in result


@pytest.mark.asyncio
async def test_no_timeout_tool_executes():
    """Tool with timeout=None should execute without timeout enforcement."""
    reg = ToolRegistry()
    reg.register(NoTimeoutTool())
    result = await reg.execute("no_timeout_tool", {})
    assert result == "unlimited"


def test_tool_default_execution_timeout():
    """Tool base class should have a default execution_timeout of 120 seconds."""
    tool = FastTool()
    assert tool.execution_timeout == 120


def test_tool_execution_timeout_override():
    """Subclass should be able to override execution_timeout."""
    assert SlowTool().execution_timeout == 1
    assert NoTimeoutTool().execution_timeout is None


# ---------------------------------------------------------------------------
# BUG-3: process.wait() after kill
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def mock_sandbox_config():
    """Provide test config for sandbox tests."""
    test_config = Config()
    test_config.agents.sandbox.shell_timeout_seconds = 1
    test_config.agents.sandbox.python_timeout_seconds = 1
    with patch("nanobot.agent.sandbox.get_config", return_value=test_config):
        yield


@pytest.mark.asyncio
async def test_shell_sandbox_timeout_reaps_process():
    """ShellSandbox should call process.wait() after kill() on timeout."""
    mock_process = AsyncMock()
    mock_process.communicate = AsyncMock(side_effect=asyncio.TimeoutError)
    mock_process.kill = MagicMock()
    mock_process.wait = AsyncMock()

    with patch("asyncio.create_subprocess_shell", return_value=mock_process):
        code, stdout, stderr = await ShellSandbox.execute("sleep 100", cwd=os.getcwd(), timeout=1)

    assert code == -1
    assert "timed out" in stderr
    mock_process.kill.assert_called_once()
    mock_process.wait.assert_awaited_once()


@pytest.mark.asyncio
async def test_python_sandbox_timeout_reaps_process(tmp_path):
    """PythonSandbox should call process.wait() after kill() on timeout."""
    hooks_file = tmp_path / "hooks.py"
    hooks_file.write_text("def pre_execute(context): pass", encoding="utf-8")

    mock_process = AsyncMock()
    mock_process.communicate = AsyncMock(side_effect=asyncio.TimeoutError)
    mock_process.kill = MagicMock()
    mock_process.wait = AsyncMock()

    with patch("asyncio.create_subprocess_exec", return_value=mock_process):
        success, msg, result = await PythonSandbox.run_hook(
            hooks_file=hooks_file,
            hook_name="pre_execute",
            context={}
        )

    assert success is False
    assert "timed out" in msg
    mock_process.kill.assert_called_once()
    mock_process.wait.assert_awaited_once()
