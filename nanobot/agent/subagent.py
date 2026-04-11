"""Subagent manager for background task execution."""

import asyncio
import json
import uuid
from pathlib import Path
from typing import Any

from loguru import logger

from nanobot.bus.events import InboundMessage
from nanobot.bus.queue import MessageBus
from nanobot.providers.base import LLMProvider
from nanobot.agent.tools.registry import ToolRegistry
from nanobot.agent.worker.bridge import BaseWorkerBridge, build_worker_toolset


class SubagentManager(BaseWorkerBridge):
    """
    Manages background subagent execution.
    
    Subagents are lightweight agent instances that run in the background
    to handle specific tasks. They share the same LLM provider but have
    isolated context and a focused system prompt.
    """
    
    def __init__(
        self,
        provider: LLMProvider,
        workspace: Path,
        bus: MessageBus,
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        brave_api_key: str | None = None,
        exec_config: "ExecToolConfig | None" = None,
        restrict_to_workspace: bool = False,
        agent_loop_ref: Any = None,
    ):
        from nanobot.config.schema import ExecToolConfig
        super().__init__(workspace=workspace, bus=bus, provider=provider)
        self.provider = provider
        self.model = model or provider.get_default_model()
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.brave_api_key = brave_api_key
        self.exec_config = exec_config or ExecToolConfig()
        self.restrict_to_workspace = restrict_to_workspace
        self.agent_loop_ref = agent_loop_ref
        self._running_tasks: dict[str, asyncio.Task[None]] = {}
    
    async def spawn(
        self,
        task: str,
        label: str | None = None,
        origin_channel: str = "cli",
        origin_chat_id: str = "direct",
    ) -> str:
        """
        Spawn a subagent to execute a task in the background.
        
        Args:
            task: The task description for the subagent.
            label: Optional human-readable label for the task.
            origin_channel: The channel to announce results to.
            origin_chat_id: The chat ID to announce results to.
        
        Returns:
            Status message indicating the subagent was started.
        """
        from nanobot.utils.trace_context import get_current_trace_id
        parent_trace = get_current_trace_id()
        task_id = f"t-{uuid.uuid4().hex[:8]}"
        display_label = label or task[:30] + ("..." if len(task) > 30 else "")
        
        origin = {
            "channel": origin_channel,
            "chat_id": origin_chat_id,
        }
        
        # Create background task
        bg_task = asyncio.create_task(
            self._run_subagent(task_id, task, display_label, origin, parent_trace)
        )
        self._running_tasks[task_id] = bg_task
        
        # Cleanup when done
        bg_task.add_done_callback(lambda _: self._running_tasks.pop(task_id, None))
        
        logger.info(f"Spawned subagent [{task_id}]: {display_label}")
        return f"Subagent [{display_label}] started (id: {task_id}). I'll notify you when it completes."
    
    async def _run_subagent(
        self,
        task_id: str,
        task: str,
        label: str,
        origin: dict[str, str],
        parent_trace: str | None = None,
    ) -> None:
        """Execute the subagent task and announce the result using the main AgentLoop."""
        from nanobot.utils.trace_context import _trace_id_var, _route_tags_var
        t_token = _trace_id_var.set(task_id)
        r_token = _route_tags_var.set(frozenset())
        
        logger.info(f"Subagent [{task_id}] starting task: {label}. parent_trace={parent_trace}")
        
        try:
            # Build subagent sandbox
            sandbox = self.workspace / "workers" / task_id
            sandbox.mkdir(parents=True, exist_ok=True)

            # Build subagent tools
            restricted_tools = build_worker_toolset(
                sandbox=sandbox,
                restrict_to_workspace=self.restrict_to_workspace,
                brave_api_key=self.brave_api_key
            )
            
            # Setup context for specific tools that need it
            for name in ["message", "spawn", "cron", "draw_image"]:
                tool = restricted_tools.get(name)
                if tool and hasattr(tool, "set_context"):
                    tool.set_context("system", f"worker:{task_id}")
            
            # Build messages with subagent-specific prompt
            system_prompt = self._build_subagent_prompt(task_id, task, sandbox)
            initial_messages: list[dict[str, Any]] = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": task},
            ]
            
            if not self.agent_loop_ref:
                raise RuntimeError("SubagentManager missing agent_loop_ref. Cannot run subagent.")

            # Delegate completely to the middleware-protected agent loop
            final_content, _, _ = await self.agent_loop_ref._run_agent_loop(
                initial_messages,
                channel="system",
                chat_id=f"worker:{task_id}",
                tool_registry_override=restricted_tools,
            )
            
            if final_content is None:
                final_content = "Task completed but no final response was generated, or loop aborted."
            
            logger.info(f"Subagent [{task_id}] completed successfully")
            await self._announce_result(task_id, label, task, final_content, origin, "ok")
            
        except Exception as e:
            error_msg = f"Error: {str(e)}"
            logger.error(f"Subagent [{task_id}] failed: {e}")
            await self._announce_result(task_id, label, task, error_msg, origin, "error")
        finally:
            _trace_id_var.reset(t_token)
            _route_tags_var.reset(r_token)
    
    def _build_subagent_prompt(self, task_id: str, task: str, sandbox: Path) -> str:
        """Build a focused system prompt for the subagent."""
        from datetime import datetime
        import time as _time
        now = datetime.now().strftime("%Y-%m-%d %H:%M (%A)")
        tz = _time.strftime("%Z") or "UTC"

        return f"""# Subagent

## Current Time
{now} ({tz})

You are a subagent spawned (task_id: {task_id}) by the main agent to complete a specific task.

## Rules
1. Stay focused - complete only the assigned task, nothing else
2. Your final response will be reported back to the main agent
3. Do not initiate conversations or take on side tasks
4. Be concise but informative in your findings

## What You Can Do
- Read and write files in the workspace / sandbox
- Search the web and fetch web pages
- Complete the task thoroughly

## What You Cannot Do
- Send messages directly to users (no message tool available)
- Spawn other subagents
- Execute shell commands (exec tool removed for security)
- Access the main agent's conversation history

## Workspace
Your isolated sandbox is at: {sandbox}
Main workspace is at: {self.workspace}
Skills are available at: {self.workspace}/skills/ (read SKILL.md files as needed)

When you have completed the task, provide a clear summary of your findings or actions."""
    
    def get_running_count(self) -> int:
        """Return the number of currently running subagents."""
        return len(self._running_tasks)
