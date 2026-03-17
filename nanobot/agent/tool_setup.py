"""Tool setup module for agent loop."""

__all__ = ["setup_all_tools"]

from pathlib import Path
from typing import TYPE_CHECKING
from loguru import logger

from nanobot.agent.tools.filesystem import ReadFileTool, WriteFileTool, EditFileTool, ListDirTool
from nanobot.agent.tools.shell import ExecTool
from nanobot.agent.tools.web import WebSearchTool, WebFetchTool
from nanobot.agent.tools.message import MessageTool
from nanobot.agent.tools.spawn import SpawnTool
from nanobot.agent.tools.cron import CronTool
from nanobot.agent.tools.save_skill import SaveSkillTool
from nanobot.agent.tools.save_experience import SaveExperienceTool
from nanobot.agent.tools.outlook import OutlookTool
from nanobot.agent.tools.attachment_analyzer import AttachmentAnalyzerTool
from nanobot.agent.tools.task_memory import TaskMemoryTool
from nanobot.agent.tools.memory_search_tool import MemorySearchTool
from nanobot.agent.tools.screen_capture import ScreenCaptureTool
from nanobot.agent.tools.rpa_executor import RPAExecutorTool
from nanobot.agent.memory import MemoryStore
from nanobot.plugin_loader import scan_plugins, unload_plugins

if TYPE_CHECKING:
    from nanobot.agent.loop import AgentLoop


def setup_all_tools(agent: "AgentLoop") -> None:
    """Setup default tools and dynamic plugin tools for the agent."""
    _register_default_tools(agent)
    _register_dynamic_tools(agent)


def _register_default_tools(agent: "AgentLoop") -> None:
    """Register the default set of tools."""
    # File tools (restrict to workspace if configured)
    allowed_dir = agent.workspace if agent.restrict_to_workspace else None
    agent.tools.register(ReadFileTool(allowed_dir=allowed_dir))
    agent.tools.register(WriteFileTool(allowed_dir=allowed_dir))
    agent.tools.register(EditFileTool(allowed_dir=allowed_dir))
    agent.tools.register(ListDirTool(allowed_dir=allowed_dir))
    
    # Shell tool
    agent.tools.register(ExecTool(
        working_dir=str(agent.workspace),
        timeout=agent.exec_config.timeout,
        restrict_to_workspace=agent.restrict_to_workspace,
    ))
    
    # Web tools
    agent.tools.register(WebSearchTool(api_key=agent.brave_api_key))
    agent.tools.register(WebFetchTool())
    
    # Message tool
    message_tool = MessageTool(send_callback=agent.bus.publish_outbound)
    agent.tools.register(message_tool)
    
    # Spawn tool (for subagents)
    spawn_tool = SpawnTool(manager=agent.subagents)
    agent.tools.register(spawn_tool)
    
    # Cron tool (for scheduling)
    if agent.cron_service:
        agent.tools.register(CronTool(agent.cron_service))
    
    # Save skill tool (for saving workflows as reusable skills)
    agent.tools.register(SaveSkillTool(agent.workspace))
    
    # Save experience tool (for actionable tactical prompts)
    agent.tools.register(SaveExperienceTool(agent.knowledge_workflow.knowledge_store))
    
    # Outlook tools (for email processing)
    agent.tools.register(OutlookTool())
    agent.tools.register(AttachmentAnalyzerTool())
    
    # Task knowledge tool
    agent.tools.register(TaskMemoryTool(agent.workspace))
    
    # Memory tool (unified CRUD: store/search/delete)
    memory_tool = MemorySearchTool()
    if hasattr(agent.context, 'vector_memory'):
        memory_tool.set_vector_memory(agent.context.vector_memory)
    memory_tool.set_memory_store(MemoryStore(agent.workspace))
    agent.tools.register(memory_tool)
    
    # Vision tools
    agent.tools.register(ScreenCaptureTool(agent.workspace))
    agent.tools.register(RPAExecutorTool())


def _register_dynamic_tools(agent: "AgentLoop") -> None:
    """Scan the plugins directory and register discovered tools.
    
    Tools that conflict with already-registered built-in tools are skipped.
    Previously loaded dynamic tools are unregistered first (for /reload).
    """
    # Unload any previously loaded plugins
    if agent._dynamic_tool_names:
        unload_plugins(agent.tools, agent._dynamic_tool_names)
        agent._dynamic_tool_names.clear()
    
    plugins_dir = agent.workspace / "nanobot" / "plugins"
    if not plugins_dir.exists():
        # Try relative to the package itself
        plugins_dir = Path(__file__).parent.parent / "plugins"
    
    discovered = scan_plugins(plugins_dir)
    
    for tool in discovered:
        if agent.tools.has(tool.name):
            logger.warning(
                f"Plugin '{tool.name}' conflicts with built-in tool, skipping"
            )
            continue
        agent.tools.register(tool)
        agent._dynamic_tool_names.append(tool.name)
    
    if agent._dynamic_tool_names:
        logger.info(
            f"Dynamic tools registered: {', '.join(agent._dynamic_tool_names)}"
        )
