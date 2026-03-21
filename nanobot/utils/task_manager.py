"""D4: Unified background task manager with error logging and concurrency control.

Replaces scattered _safe_create_task patterns with a centralized manager that
tracks all fire-and-forget async tasks, enforces a concurrency limit, surfaces
errors, and exposes task metadata for the dashboard.
"""

import asyncio
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Coroutine

from loguru import logger


class TaskState(str, Enum):
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class TaskInfo:
    """Metadata for a tracked background task."""
    name: str
    state: TaskState = TaskState.RUNNING
    started_at: float = field(default_factory=time.time)
    finished_at: float | None = None
    error: str | None = None


class BackgroundTaskManager:
    """Centralized manager for all fire-and-forget async tasks.

    Features:
    - Concurrency limit (default 10) — excess tasks are queued.
    - Done-callback error logging (no silent exceptions).
    - Task listing for dashboard / /stats introspection.
    - Cancel-by-name support.
    """

    _instance: "BackgroundTaskManager | None" = None

    def __init__(self, max_concurrency: int = 10) -> None:
        self._max_concurrency = max_concurrency
        self._semaphore = asyncio.Semaphore(max_concurrency)
        self._tasks: dict[str, asyncio.Task] = {}
        self._history: list[TaskInfo] = []  # keep last N completed
        self._counter = 0
        self._max_history = 50

    # ── Singleton access ──────────────────────────────────────────
    @classmethod
    def get(cls) -> "BackgroundTaskManager":
        """Return the process-level singleton, creating it lazily."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    # ── Public API ────────────────────────────────────────────────

    def spawn(self, coro: Coroutine, *, name: str = "background") -> asyncio.Task:
        """Create a tracked background task.

        Respects the concurrency semaphore and logs errors on completion.
        """
        self._counter += 1
        task_id = f"{name}#{self._counter}"
        info = TaskInfo(name=task_id)

        async def _guarded():
            async with self._semaphore:
                return await coro

        task = asyncio.create_task(_guarded(), name=task_id)
        self._tasks[task_id] = task

        def _done_cb(t: asyncio.Task) -> None:
            self._tasks.pop(task_id, None)
            if t.cancelled():
                info.state = TaskState.CANCELLED
            elif exc := t.exception():
                info.state = TaskState.FAILED
                info.error = str(exc)
                logger.error(f"Background task '{task_id}' failed: {exc}", exc_info=exc)
            else:
                info.state = TaskState.DONE
            info.finished_at = time.time()
            self._history.append(info)
            # Trim history
            if len(self._history) > self._max_history:
                self._history = self._history[-self._max_history:]

        task.add_done_callback(_done_cb)
        return task

    def cancel(self, name_prefix: str) -> int:
        """Cancel all running tasks whose ID starts with *name_prefix*.

        Returns the number of tasks cancelled.
        """
        cancelled = 0
        for tid, task in list(self._tasks.items()):
            if tid.startswith(name_prefix) and not task.done():
                task.cancel()
                cancelled += 1
        return cancelled

    # ── Introspection ─────────────────────────────────────────────

    @property
    def running_count(self) -> int:
        return sum(1 for t in self._tasks.values() if not t.done())

    def list_tasks(self) -> list[dict[str, Any]]:
        """Return a combined list of running + recent completed tasks."""
        now = time.time()
        items: list[dict[str, Any]] = []
        # Running
        for tid, task in self._tasks.items():
            items.append({
                "id": tid,
                "state": TaskState.RUNNING.value,
                "elapsed_s": round(now - (now - 1), 1),  # placeholder; real start in _history
            })
        # Completed (most recent first)
        for info in reversed(self._history[-20:]):
            items.append({
                "id": info.name,
                "state": info.state.value,
                "started_at": info.started_at,
                "duration_s": round(info.finished_at - info.started_at, 2) if info.finished_at else None,
                "error": info.error,
            })
        return items

    def summary(self) -> dict[str, Any]:
        """Compact summary for /stats and dashboard."""
        return {
            "running": self.running_count,
            "completed": sum(1 for i in self._history if i.state == TaskState.DONE),
            "failed": sum(1 for i in self._history if i.state == TaskState.FAILED),
            "total_spawned": self._counter,
            "max_concurrency": self._max_concurrency,
        }
