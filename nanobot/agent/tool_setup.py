import asyncio
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
from nanobot.agent.tools.excel_actuator import ExcelActuatorTool
from nanobot.agent.tools.draw import DrawImageTool
from nanobot.agent.memory import MemoryStore
from nanobot.plugin_loader import scan_plugins, unload_plugins

if TYPE_CHECKING:
    from nanobot.agent.loop import AgentLoop


def setup_all_tools(agent: "AgentLoop") -> None:
    """Setup default tools and dynamic plugin tools for the agent.
    
    Called synchronously from AgentLoop.__init__().
    Lifecycle hooks (setup) are NOT called here — AgentLoop.run() handles that.
    """
    _register_default_tools(agent)
    _register_dynamic_tools(agent)


def _register_default_tools(agent: "AgentLoop") -> None:
    """Register the default set of tools."""
    # File tools (restrict to workspace if configured)
    allowed_dir = agent.workspace if agent.restrict_to_workspace else None
    
    # Zone A (Workspace) is Read-only. Zone C (sandbox) is writable.
    sandbox_dir = agent.workspace / "sandbox"
    sandbox_dir.mkdir(parents=True, exist_ok=True)
    
    agent.tools.register(ReadFileTool(allowed_dir=allowed_dir, forbidden_dirs=None))
    agent.tools.register(ListDirTool(allowed_dir=allowed_dir, forbidden_dirs=None))
    
    # Write and Edit are strictly limited to the Sandbox (Zone C)
    agent.tools.register(WriteFileTool(allowed_dir=sandbox_dir, forbidden_dirs=None))
    agent.tools.register(EditFileTool(allowed_dir=sandbox_dir, forbidden_dirs=None))
    
    # Shell tool
    sandbox_dir = agent.workspace / "sandbox"
    sandbox_dir.mkdir(parents=True, exist_ok=True)
    agent.tools.register(ExecTool(
        working_dir=str(sandbox_dir),
        timeout=agent.exec_config.timeout,
        restrict_to_workspace=agent.restrict_to_workspace,
    ))
    
    # Web tools
    agent.tools.register(WebSearchTool(api_key=agent.brave_api_key))
    agent.tools.register(WebFetchTool())
    
    # Message tool
    message_tool = MessageTool(send_callback=agent.bus.publish_outbound)
    agent.tools.register(message_tool)
    
    # Draw Image tool
    draw_image_tool = DrawImageTool(send_callback=agent.bus.publish_outbound)
    agent.tools.register(draw_image_tool)
    
    # Spawn tool (for subagents)
    if hasattr(agent, 'coordinator_manager') and agent.coordinator_manager.enabled:
        from nanobot.agent.tools.coordinator import CoordinatorTool
        agent.tools.register(CoordinatorTool(agent.coordinator_manager))
    else:
        from nanobot.agent.tools.spawn import SpawnTool
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
    
    # Vision & Desktop Actuation tools
    agent.tools.register(ScreenCaptureTool(agent.workspace))
    agent.tools.register(RPAExecutorTool())
    # ADR-53: Excel OLAP automation (Windows-only; gracefully no-ops if pywin32 missing)
    agent.tools.register(ExcelActuatorTool(workspace=agent.workspace))

    # KG topology navigator (ADR-67) — zero-overhead fallback for search failures
    # Zero context pollution: only consumes tokens when the agent explicitly calls it.
    from nanobot.agent.tools.knowledge_map import KnowledgeMapTool
    agent.tools.register(KnowledgeMapTool(agent.workspace))



def _register_dynamic_tools(agent: "AgentLoop") -> None:
    """Scan the plugins directory and register discovered tools (sync, no lifecycle hooks).
    
    Used at startup by setup_all_tools(). Lifecycle hooks (setup) are called
    later by AgentLoop.run() which iterates all registered tools.
    Tools that conflict with already-registered built-in tools are skipped.
    """
    plugins_dir = agent.workspace / "nanobot" / "plugins"
    fallback_dir = agent.workspace.parent / "plugins"
    src_dir = Path(__file__).parent.parent / "plugins"
    
    dirs_to_scan = []
    if plugins_dir.exists():
        dirs_to_scan.append(plugins_dir)
    if fallback_dir.exists():
        dirs_to_scan.append(fallback_dir)
    if src_dir.exists():
        dirs_to_scan.append(src_dir)
    
    discovered = []
    for d in dirs_to_scan:
        discovered.extend(scan_plugins(d))
    
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


async def _reload_dynamic_tools(agent: "AgentLoop") -> None:
    """Reload dynamic plugin tools with full lifecycle management.
    
    Used by /reload command. Calls teardown() on old plugins before unloading,
    then scans for new plugins and calls setup() on each.
    """
    # Teardown and unload any previously loaded plugins
    if agent._dynamic_tool_names:
        for name in agent._dynamic_tool_names:
            tool = agent.tools.get(name)
            if tool:
                try:
                    await tool.teardown()
                    logger.info(f"Plugin teardown completed: '{name}'")
                except Exception as e:
                    if isinstance(e, asyncio.CancelledError):
                        raise
                    logger.warning(f"Plugin teardown failed for '{name}': {e}")
        unload_plugins(agent.tools, agent._dynamic_tool_names)
        agent._dynamic_tool_names.clear()
    
    plugins_dir = agent.workspace / "nanobot" / "plugins"
    fallback_dir = agent.workspace.parent / "plugins"
    src_dir = Path(__file__).parent.parent / "plugins"
    
    dirs_to_scan = []
    if plugins_dir.exists():
        dirs_to_scan.append(plugins_dir)
    if fallback_dir.exists():
        dirs_to_scan.append(fallback_dir)
    if src_dir.exists():
        dirs_to_scan.append(src_dir)
    
    discovered = []
    for d in dirs_to_scan:
        discovered.extend(scan_plugins(d))
    
    for tool in discovered:
        if agent.tools.has(tool.name):
            logger.warning(
                f"Plugin '{tool.name}' conflicts with built-in tool, skipping"
            )
            continue
        agent.tools.register(tool)
        agent._dynamic_tool_names.append(tool.name)
        # Call setup on newly loaded plugin
        try:
            await tool.setup()
            logger.info(f"Plugin setup completed: '{tool.name}'")
        except Exception as e:
            if isinstance(e, asyncio.CancelledError):
                raise
            logger.warning(f"Plugin setup failed for '{tool.name}': {e}")
    
    if agent._dynamic_tool_names:
        logger.info(
            f"Dynamic tools reloaded: {', '.join(agent._dynamic_tool_names)}"
        )
