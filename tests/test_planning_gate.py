from unittest.mock import MagicMock, patch
from pathlib import Path
import shutil

import pytest

from nanobot.agent.capability import CapabilityTag
from nanobot.agent.tools.registry import ToolRegistry


def _build_agent(tmp_path):
    agent = MagicMock()
    agent.workspace = tmp_path
    agent.restrict_to_workspace = True
    agent.tools = ToolRegistry()
    agent.exec_config = MagicMock(timeout=30)
    agent.brave_api_key = None
    agent.bus = MagicMock(publish_outbound=MagicMock())
    agent.coordinator_manager = MagicMock(enabled=False)
    agent.subagents = MagicMock()
    agent.cron_service = None
    agent.knowledge_workflow = MagicMock(knowledge_store=MagicMock())
    agent.context = MagicMock(vector_memory=MagicMock())
    agent._dynamic_tool_names = []
    return agent


@pytest.fixture
def workspace_dir():
    workspace = Path(".pytest_tmp_planning_gate") / "workspace"
    if workspace.exists():
        shutil.rmtree(workspace)
    workspace.mkdir(parents=True)
    yield workspace
    shutil.rmtree(workspace, ignore_errors=True)


def test_setup_registers_write_artifact(workspace_dir):
    from nanobot.agent.tool_setup import setup_all_tools

    agent = _build_agent(workspace_dir)
    with patch("nanobot.agent.tool_setup._register_dynamic_tools", return_value=None):
        setup_all_tools(agent)

    tool = agent.tools.get("write_artifact")
    assert tool is not None
    assert tool.static_tags & CapabilityTag.SENSITIVE
    assert not (tool.static_tags & CapabilityTag.DESTRUCTIVE)


@pytest.mark.asyncio
async def test_write_artifact_stays_inside_workspace(workspace_dir):
    from nanobot.tools.write_artifact import WriteArtifactTool

    tool = WriteArtifactTool(workspace_dir)
    result = await tool.execute("implementation_plan.md", "# Plan")

    assert "Awaiting user approval" in result
    assert (workspace_dir / "implementation_plan.md").read_text(encoding="utf-8") == "# Plan"

    with pytest.raises(PermissionError):
        await tool.execute("../escape.md", "nope")
