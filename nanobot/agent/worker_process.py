"""
Worker Process Entry Point for Coordinator Mode.
Runs an isolated AgentLoop and exposes it via HTTP JSON-RPC.
"""
import argparse
import asyncio
import json
import os
import sys
import uuid
import weakref
from pathlib import Path
from typing import Any

from aiohttp import web
from loguru import logger

# Monkey-patch TaskKnowledgeStore to make it Read-Only in the worker process
from nanobot.agent.knowledge.readonly_store import ReadOnlyKnowledgeStore
from nanobot.agent.task_knowledge import TaskKnowledgeStore as OriginalTaskKnowledgeStore
import nanobot.agent.knowledge_workflow
import nanobot.agent.task_knowledge

nanobot.agent.knowledge_workflow.TaskKnowledgeStore = lambda ws: ReadOnlyKnowledgeStore(OriginalTaskKnowledgeStore(ws))

from nanobot.bus.events import InboundMessage
from nanobot.bus.queue import MessageBus
from nanobot.providers.factory import ProviderFactory
from nanobot.config.loader import get_config
from nanobot.agent.loop import AgentLoop
from nanobot.agent.tools.registry import ToolRegistry
from nanobot.agent.tools.filesystem import ReadFileTool, WriteFileTool, EditFileTool, ListDirTool
from nanobot.agent.tools.web import WebSearchTool, WebFetchTool
from nanobot.utils.trace_context import _trace_id_var, _route_tags_var

class WorkerNode:
    def __init__(self, port: int, token: str, workspace_path: Path, timeout: int = 300):
        self.port = port
        self.token = token
        self.workspace = workspace_path
        self.timeout = timeout
        self.app = web.Application()
        self.app.add_routes([
            web.post("/task", self.handle_task),
            web.get("/status", self.handle_status),
            web.get("/result", self.handle_result),
            web.post("/shutdown", self.handle_shutdown),
        ])
        
        self.config = get_config()
        self.bus = MessageBus()  # Local bus, not connected to master
        # AgentLoop and Provider are instantiated dynamically per task to prevent context leakage
        
        self.current_task_id: str | None = None
        self.status = "idle"  # idle, running, completed, error
        self.result: str | None = None
        self.error: str | None = None
        
        self._task_future: asyncio.Task | None = None
        # Auto-shutdown task
        self._idle_timeout_task: asyncio.Task | None = None
        
    async def _idle_watchdog(self):
        """Shutdown worker if it remains idle for too long without instructions."""
        await asyncio.sleep(self.timeout) # Enforce dynamic idle timeout
        if self.status in ("idle", "completed", "error") and not getattr(self, "_shutdown_requested", False):
            logger.warning(f"Worker idle timeout ({self.timeout}s) reached. Shutting down automatically.")
            os._exit(0)
            
    async def start(self):
        self._idle_timeout_task = asyncio.create_task(self._idle_watchdog())
        runner = web.AppRunner(self.app)
        await runner.setup()
        site = web.TCPSite(runner, '127.0.0.1', self.port)
        await site.start()
        
        if site._server and site._server.sockets:
            self.port = site._server.sockets[0].getsockname()[1]
            
        logger.info(f"Worker process listening on 127.0.0.1:{self.port}")
        # Signal master that we are ready
        sys.stdout.write(f"WORKER_READY:{self.port}\n")
        sys.stdout.flush()
        
    def _authenticate(self, request: web.Request) -> bool:
        auth = request.headers.get("Authorization", "")
        if not auth.startswith("Bearer ") or auth[7:] != self.token:
            return False
        return True

    async def handle_task(self, request: web.Request) -> web.Response:
        if not self._authenticate(request):
            return web.json_response({"error": "Unauthorized"}, status=401)
            
        if self.status == "running":
            return web.json_response({"error": "Worker is already running a task"}, status=409)
            
        data = await request.json()
        task_desc = data.get("task")
        task_id = data.get("task_id", uuid.uuid4().hex[:8])
        trace_id = data.get("trace_id", task_id)
        
        model = data.get("model") or self.config.agents.defaults.model
        temperature = data.get("temperature", 0.7)
        max_tokens = data.get("max_tokens", 4096)
        brave_api_key = data.get("brave_api_key")
        
        if not task_desc:
            return web.json_response({"error": "Task is required"}, status=400)
            
        self.current_task_id = task_id
        self.status = "running"
        self.result = None
        self.error = None
        
        # Optionally reset watchdog
        if self._idle_timeout_task:
            self._idle_timeout_task.cancel()
            
        # Spawn execution in background
        self._task_future = asyncio.create_task(self._execute_agent_loop(
            task_id, task_desc, trace_id, model, temperature, max_tokens, brave_api_key
        ))
        
        return web.json_response({"status": "accepted", "task_id": task_id})

    async def handle_status(self, request: web.Request) -> web.Response:
        if not self._authenticate(request):
            return web.json_response({"error": "Unauthorized"}, status=401)
        return web.json_response({
            "task_id": self.current_task_id,
            "status": self.status
        })

    async def handle_result(self, request: web.Request) -> web.Response:
        if not self._authenticate(request):
            return web.json_response({"error": "Unauthorized"}, status=401)
            
        if self.status == "running":
            return web.json_response({"error": "Task is still running", "status": self.status}, status=202)
            
        return web.json_response({
            "task_id": self.current_task_id,
            "status": self.status,
            "result": self.result,
            "error": self.error
        })
        
    async def handle_shutdown(self, request: web.Request) -> web.Response:
        if not self._authenticate(request):
            return web.json_response({"error": "Unauthorized"}, status=401)
            
        logger.info("Shutdown requested")
        self._shutdown_requested = True
        
        # Schedule exit
        async def do_exit():
            await asyncio.sleep(0.5)
            os._exit(0)
            
        asyncio.create_task(do_exit())
        return web.json_response({"status": "shutting down"})

    async def _execute_agent_loop(self, task_id: str, task: str, trace_id: str, model: str, temperature: float, max_tokens: int, brave_api_key: str | None):
        t_token = _trace_id_var.set(trace_id)
        r_token = _route_tags_var.set(frozenset(["worker"]))
        
        try:
            provider = ProviderFactory.get_provider(model, self.config)
            agent_loop = AgentLoop(
                bus=self.bus,
                provider=provider,
                workspace=self.workspace,
                model=model,
                temperature=float(temperature),
                max_tokens=int(max_tokens),
                brave_api_key=brave_api_key,
                restrict_to_workspace=self.config.tools.restrict_to_workspace
            )
            
            sandbox = self.workspace / "workers" / task_id
            sandbox.mkdir(parents=True, exist_ok=True)
            
            from nanobot.agent.worker.bridge import build_worker_toolset
            restricted_tools = build_worker_toolset(
                sandbox=sandbox,
                restrict_to_workspace=agent_loop.restrict_to_workspace,
                brave_api_key=agent_loop.brave_api_key
            )
            
            from datetime import datetime
            import time as _time
            now = datetime.now().strftime("%Y-%m-%d %H:%M (%A)")
            tz = _time.strftime("%Z") or "UTC"

            system_prompt = f"""# Subagent

## Current Time
{now} ({tz})

You are a subagent spawned (task_id: {task_id}) by the main agent.

## Rules
1. Stay focused - complete only the assigned task.
2. Be concise but informative in your findings.
3. No external mutations out of your sandbox boundaries.

## Workspace
Your isolated sandbox is at: {sandbox}
Main workspace is at: {self.workspace}

When completed, provide a clear summary of findings."""

            initial_messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": task},
            ]

            final_content, _, _ = await agent_loop._run_agent_loop_v2(
                initial_messages,
                channel="system",
                chat_id=f"worker:{task_id}",
                tool_registry_override=restricted_tools,
            )
            
            self.result = final_content if final_content else "Task completed (no textual response)"
            self.status = "completed"
            
            # Persist output to json in sandbox as fallback
            output_json = sandbox / "output.json"
            output_json.write_text(json.dumps({"status": "completed", "result": self.result}, ensure_ascii=False))

        except Exception as e:
            if isinstance(e, asyncio.CancelledError):
                raise
            logger.exception("Worker agent loop failed")
            self.error = str(e)
            self.status = "error"
            
        finally:
            _trace_id_var.reset(t_token)
            _route_tags_var.reset(r_token)
            
            # Restart idle watchdog
            self._idle_timeout_task = asyncio.create_task(self._idle_watchdog())

async def main():
    parser = argparse.ArgumentParser("Worker Process")
    parser.add_argument("--port", type=int, required=True, help="Port to bind HTTP server")
    parser.add_argument("--token", type=str, required=True, help="Secret token for authentication")
    parser.add_argument("--workspace", type=str, required=True, help="Workspace path")
    parser.add_argument("--timeout", type=int, default=300, help="Worker idle timeout seconds")
    parser.add_argument("--disable-network-socket", action="store_true", help="Unused in worker_process (kept for compatibility)")
    
    args = parser.parse_args()
    
    workspace_path = Path(args.workspace).expanduser().resolve()
    
    node = WorkerNode(args.port, args.token, workspace_path, timeout=args.timeout)
    await node.start()
    
    # Keep alive
    while True:
        await asyncio.sleep(3600)

def _bootstrap_security(argv: list[str]) -> None:
    """CLI 安全引导：必须在所有业务逻辑启动前调用。"""
    # Defensive programming: Block raw OS execution, but ALLOW sockets to preserve LLM and IPC.
    def _block_dangerous_ops(event, args):
        if event in ("os.system", "os.exec", "os.posix_spawn"):
            raise PermissionError(f"Worker: Direct OS execution blocked by parent policy ({event})")
            
    import sys
    sys.addaudithook(_block_dangerous_ops)

if __name__ == "__main__":
    _bootstrap_security(sys.argv)
    asyncio.run(main())
