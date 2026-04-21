import asyncio
"""
Bridge abstractions for managing isolated Worker nodes (coroutine or subprocess).
"""

from abc import ABC, abstractmethod
from typing import Any
from pathlib import Path
from loguru import logger

from nanobot.bus.queue import MessageBus
from nanobot.bus.events import InboundMessage
from nanobot.utils.trace_context import get_current_trace_id


class BaseWorkerBridge(ABC):
    """
    Abstract base class for worker managers (SubagentManager, CoordinatorManager).
    Unifies common task spawning signatures and result announcements.
    """
    def __init__(self, workspace: Path, bus: MessageBus, provider: Any = None, **kwargs):
        self.workspace = workspace
        self.bus = bus
        self.provider = provider

    @abstractmethod
    async def spawn(
        self,
        task: str,
        label: str | None = None,
        origin_channel: str = "cli",
        origin_chat_id: str = "direct",
    ) -> str:
        """Spawn a new worker to execute a task."""
        pass

    @abstractmethod
    def get_running_count(self) -> int:
        """Return the number of currently running workers."""
        pass

    async def _announce_result(
        self,
        task_id: str,
        label: str,
        task: str,
        result: str,
        origin: dict[str, str],
        status: str,
        sender_id: str = "worker",
    ) -> None:
        """Announce the worker result back to the main agent bus."""
        status_text = "completed successfully" if status in ("ok", "completed") else "failed"
        
        # Outcome-Refining Pipeline (Phase 38B)
        # If output is too large and the task succeeded, use the manager's LLM to distill it.
        final_result = result
        if self.provider and status in ("ok", "completed") and len(result) > 500:
            try:
                refine_prompt = (
                    f"A background subagent completed the task: '{task}'.\n\n"
                    f"Raw Execution Output:\n---\n{result}\n---\n\n"
                    f"You are the Outcome-Refining Pipeline. Your goal is to drastically CONDENSE the raw output into a clear, concise summary of the key findings, conclusions, or actions taken. Discard any verbose boilerplate, reasoning traces, or unhelpful artifacts. Output ONLY the refined distillation."
                )
                logger.info(f"Coordinator: Refining output payload ({len(result)} chars) for worker '{label}'")
                
                # Fetch default model dynamically if possible, else rely on provider's default
                from nanobot.config.loader import get_config
                model = get_config().agents.defaults.model
                
                resp = await self.provider.chat(
                    messages=[
                        {"role": "system", "content": "You are an outcome-distillation system. Output clear, direct insight."},
                        {"role": "user", "content": refine_prompt}
                    ],
                    model=model,
                    temperature=0.3,
                    max_tokens=2048
                )
                if resp.content:
                    final_result = "[Refined Result]\n" + resp.content.strip()
            except Exception as e:
                if isinstance(e, asyncio.CancelledError):
                    raise
                logger.warning(f"Coordinator: Result refinement failed: {e}")

        announce_content = f"""[Worker '{label}' {status_text}]

Task: {task}

Result:
{final_result}

Summarize this naturally for the user. Keep it brief. Do not mention technical details like subprocess or task IDs."""
        
        msg = InboundMessage(
            channel="system",
            sender_id=sender_id,
            chat_id=f"{origin['channel']}:{origin['chat_id']}",
            content=announce_content,
            metadata={"trace_id": get_current_trace_id() or task_id},
        )
        
        await self.bus.publish_inbound(msg)
        logger.debug(f"{sender_id.capitalize()} [{task_id}] announced result to {origin['channel']}:{origin['chat_id']}")


def build_worker_toolset(sandbox: Path, restrict_to_workspace: bool, brave_api_key: str | None = None) -> "ToolRegistry":
    """
    Build a restricted ToolRegistry for isolated workers.
    Workers are intentionally denied message, spawn, coordinator, and exec capabilities.
    """
    from nanobot.agent.tools.registry import ToolRegistry
    from nanobot.agent.tools.filesystem import ReadFileTool, WriteFileTool, EditFileTool, ListDirTool
    from nanobot.agent.tools.web import WebSearchTool, WebFetchTool
    
    restricted_tools = ToolRegistry()
    allowed_dir = sandbox if restrict_to_workspace else None
    
    restricted_tools.register(ReadFileTool(allowed_dir=allowed_dir))
    restricted_tools.register(WriteFileTool(allowed_dir=allowed_dir))
    restricted_tools.register(EditFileTool(allowed_dir=allowed_dir))
    restricted_tools.register(ListDirTool(allowed_dir=allowed_dir))
    
    if brave_api_key:
        restricted_tools.register(WebSearchTool(api_key=brave_api_key))
    else:
        restricted_tools.register(WebSearchTool())
        
    restricted_tools.register(WebFetchTool())
    
    return restricted_tools
