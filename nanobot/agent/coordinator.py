"""
Coordinator Manager for managing independent Worker subprocesses over HTTP JSON-RPC.
"""
import aiohttp
import asyncio
import atexit
import json
import os
import sys
import secrets
import subprocess
import weakref
import platform
from pathlib import Path
from typing import Any, Dict

from loguru import logger

_GLOBAL_WORKERS_GROUP = set()

def _cleanup_workers():
    """Kill all worker processes on master shutdown (atexit)"""
    for process_ref in list(_GLOBAL_WORKERS_GROUP):
        process = process_ref()
        if process and process.poll() is None:
            logger.info(f"Coordinator: Cleaning up orphan worker PID {process.pid}")
            try:
                if platform.system() == "Windows":
                    subprocess.call(['taskkill', '/F', '/T', '/PID', str(process.pid)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                else:
                    process.kill()
            except Exception:
                pass

atexit.register(_cleanup_workers)


class CoordinatorManager:
    """
    Manages Worker background subprocesses.
    It replaces the coroutine-based SubagentManager for Phase 38 Coordinator Mode.
    """
    def __init__(
        self,
        workspace: Path,
        bus: Any,
        enabled: bool = False,
        max_workers: int = 4,
        sandbox_root: str = "workspace/workers"
    ):
        self.workspace = workspace
        self.bus = bus
        self.enabled = enabled
        self.max_workers = max_workers
        self.sandbox_root = workspace / sandbox_root
        self.sandbox_root.mkdir(parents=True, exist_ok=True)
        
        self.workers: Dict[str, dict] = {}  # task_id -> {"process": Popen, "port": int, "token": str, "task_desc": str, "status_task": asyncio.Task}
        self.session: aiohttp.ClientSession | None = None

    def _get_session(self) -> aiohttp.ClientSession:
        if self.session is None:
            self.session = aiohttp.ClientSession()
        return self.session

    async def close(self):
        """Cleanup network session"""
        if self.session and not self.session.closed:
            await self.session.close()

    async def spawn(
        self,
        task: str,
        label: str | None = None,
        origin_channel: str = "cli",
        origin_chat_id: str = "direct",
    ) -> str:
        """
        Spawn a true isolated worker subprocess to execute a task.
        """
        if not self.enabled:
            return "Coordinator is disabled in config. Task cannot be spawned."
            
        if len(self.workers) >= self.max_workers:
            # Clean up dead ones
            await self._reconcile_workers()
            if len(self.workers) >= self.max_workers:
                return f"Error: Maximum worker limit ({self.max_workers}) reached. Please wait or cancel existing tasks."
                
        import uuid
        task_id = f"w-{uuid.uuid4().hex[:8]}"
        display_label = label or task[:30] + ("..." if len(task) > 30 else "")
        token = secrets.token_hex(16)
        
        from nanobot.config.loader import get_config
        config = get_config()
        
        # Start Python process
        # Use python -I -X utf8 -m nanobot.agent.worker_process --port 0 --token <xyz> --workspace <pwd> --timeout <sec>
        cmd = [
            sys.executable or "python",
            "-I", "-X", "utf8",
            "-m", "nanobot.agent.worker_process",
            "--port", "0",
            "--token", token,
            "--workspace", str(self.workspace),
            "--timeout", str(config.agents.coordinator.worker_timeout)
        ]
        
        # In order to avoid sharing file descriptors accidentally (e.g. windows sockets / pipe deadlocks),
        # we read stdout line by line until we see WORKER_READY:port
        kwargs = {}
        if platform.system() == "Windows":
            # CREATE_NEW_PROCESS_GROUP avoids Ctrl+C propagating directly 
            kwargs["creationflags"] = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 512)
        else:
            # Equivalent isolation for POSIX (macOS/Linux)
            kwargs["start_new_session"] = True
            
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            bufsize=1, # Line buffered
            **kwargs
        )
        
        # Register for atexit cleanup
        _GLOBAL_WORKERS_GROUP.add(weakref.ref(process))
        
        port = None
        # Async read stdout until ready
        def _read_ready_port():
            for line in process.stdout:
                if line.startswith("WORKER_READY:"):
                    return int(line.strip().split(":")[1])
                # We can also print worker startup logs here if needed
            return None
            
        def _drain_stdout(proc):
            try:
                for _ in proc.stdout:
                    pass
            except Exception:
                pass
            
        try:
            port = await asyncio.to_thread(_read_ready_port)
            if port:
                # Drain the remaining stdout pipe in the background to prevent Windows 64KB buffer deadlocks
                asyncio.create_task(asyncio.to_thread(_drain_stdout, process))
        except Exception as e:
            logger.error(f"Coordinator: Failed to start worker: {e}")
            
        if not port:
            process.kill()
            return f"Error: Worker failed to start or bind port. Check logs."
            
        # Call POST /task
        url = f"http://127.0.0.1:{port}/task"
        headers = {"Authorization": f"Bearer {token}"}
        
        try:
            async with self._get_session().post(url, headers=headers, json={"task": task, "task_id": task_id}) as resp:
                resp.raise_for_status()
        except Exception as e:
            process.kill()
            return f"Error: Failed to dispatch task to worker {task_id}: {e}"
            
        origin = {"channel": origin_channel, "chat_id": origin_chat_id}
        
        # Start background task to poll status
        status_monitor_task = asyncio.create_task(self._poll_worker_status(task_id, display_label, task, origin))
        
        self.workers[task_id] = {
            "process": process,
            "port": port,
            "token": token,
            "task_desc": task,
            "label": display_label,
            "origin": origin,
            "status_task": status_monitor_task
        }
        
        logger.info(f"Coordinator spawned worker '{display_label}' on port {port} (PID: {process.pid})")
        return f"Worker [{display_label}] started (id: {task_id}). I'll notify you when it completes."

    async def _reconcile_workers(self):
        """Remove dead worker processes from tracking dict"""
        to_remove = []
        for tid, info in self.workers.items():
            if info["process"].poll() is not None:
                to_remove.append(tid)
        for tid in to_remove:
            self.workers.pop(tid, None)

    async def _poll_worker_status(self, task_id: str, label: str, task_desc: str, origin: dict):
        """Long-running coroutine that polls worker and announces result when done."""
        worker_info = self.workers.get(task_id)
        if not worker_info:
            return
            
        url_status = f"http://127.0.0.1:{worker_info['port']}/result"
        headers = {"Authorization": f"Bearer {worker_info['token']}"}
        
        while True:
            await asyncio.sleep(10) # 10s heartbeat
            
            # Check if process crashed
            if worker_info["process"].poll() is not None:
                logger.error(f"Worker {task_id} process crashed unexpectedly.")
                await self._announce_result(task_id, label, task_desc, "Worker process crashed.", origin, "error")
                break
                
            try:
                async with self._get_session().get(url_status, headers=headers, timeout=5) as resp:
                    if resp.status == 202: # Still running
                        continue
                        
                    if resp.status == 200:
                        data = await resp.json()
                        st = data.get("status")
                        if st in ("completed", "error"):
                            final_result = data.get("result", "")
                            if st == "error":
                                final_result = data.get("error", "Unknown error")
                            
                            await self._announce_result(task_id, label, task_desc, final_result, origin, st)
                            # Cleanup
                            try:
                                async with self._get_session().post(f"http://127.0.0.1:{worker_info['port']}/shutdown", headers=headers, timeout=2):
                                    pass
                            except Exception:
                                pass
                            break
            except Exception as e:
                logger.debug(f"Coordinator: heartbeat error to worker {task_id}: {e}")
                
        # Remove from workers
        self.workers.pop(task_id, None)

    async def _announce_result(
        self,
        task_id: str,
        label: str,
        task: str,
        result: str,
        origin: dict[str, str],
        status: str,
    ) -> None:
        """Announce the worker result to the main agent bus."""
        from nanobot.utils.trace_context import get_current_trace_id
        from nanobot.bus.events import InboundMessage
        
        status_text = "completed successfully" if status == "completed" else "failed"
        
        announce_content = f"""[Worker '{label}' {status_text}]

Task: {task}

Result:
{result}

Summarize this naturally for the user. Keep it brief. Do not mention technical details like subprocess or task IDs."""
        
        msg = InboundMessage(
            channel="system",
            sender_id="coordinator",
            chat_id=f"{origin['channel']}:{origin['chat_id']}",
            content=announce_content,
            metadata={"trace_id": get_current_trace_id() or task_id},
        )
        
        await self.bus.publish_inbound(msg)
        
    def get_running_count(self) -> int:
        return sum(1 for w in self.workers.values() if w["process"].poll() is None)

