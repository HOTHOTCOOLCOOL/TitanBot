"""Phase 41: Onion Middleware Architecture — pluggable per-turn pipeline.

This package decouples cross-cutting concerns (metrics, circuit breaker,
verification, HITL, crash recovery, etc.) from the monolithic _run_agent_loop
into independent, layered middleware components.

Design: Two-phase iterative runner (pre_process → ToolExecutor → post_process)
with LIFO post ordering. No closures, O(1) stack depth.
"""

from nanobot.agent.middleware.base import (
    TurnAction,
    TurnContext,
    AgentMiddleware,
)
from nanobot.agent.middleware.pipeline import MiddlewarePipeline

__all__ = [
    "TurnAction",
    "TurnContext",
    "AgentMiddleware",
    "MiddlewarePipeline",
]
