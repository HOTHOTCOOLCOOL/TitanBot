from __future__ import annotations
"""Phase 41: ToolExecutor — innermost onion layer.

Handles concurrent tool execution via asyncio.gather, result normalization,
and message assembly.  Extracted from loop.py _exec_tool closure (L792-L897).
"""


import asyncio
import time
from typing import Any, TYPE_CHECKING

from loguru import logger

from nanobot.agent.middleware.base import TurnContext
from nanobot.bus.events import ToolExecutedEvent
from nanobot.utils.metrics import metrics

if TYPE_CHECKING:
    from nanobot.agent.loop import AgentLoop


# Re-use the normalizer from loop.py (module-level function)
from nanobot.agent.loop import _normalize_tool_result, _MAX_TOOL_RESULT_CHARS


class ToolExecutor:
    """Innermost onion layer: concurrent tool execution + message assembly."""

    def __init__(self, agent: AgentLoop):
        self._agent = agent

    async def execute(self, ctx: TurnContext) -> None:
        """Execute all tool calls concurrently, normalize results, assemble messages."""
        if not ctx.tool_calls:
            return

        async def _exec_one(tc: Any) -> Any:
            _start = time.monotonic()
            with metrics.timer("tool_execution"):
                registry = getattr(ctx, "tool_registry_override", None) or self._agent.tools
                res = await registry.execute(tc.name, tc.arguments)
            _elapsed_ms = (time.monotonic() - _start) * 1000
            metrics.increment("tool_executions_count")
            logger.debug(f"Tool {tc.name} completed in {_elapsed_ms / 1000:.1f}s")

            # Phase 22D: Emit domain event for observability
            _is_err = isinstance(res, BaseException) or (
                isinstance(res, str) and res.startswith("Error: ")
            )
            await self._agent.bus.publish_event(ToolExecutedEvent(
                event_type="tool_executed",
                tool_name=tc.name,
                duration_ms=_elapsed_ms,
                success=not _is_err,
                error=str(res)[:200] if _is_err else None,
            ))
            return res

        results = await asyncio.gather(
            *[_exec_one(tc) for tc in ctx.tool_calls],
            return_exceptions=True,
        )
        ctx.results = list(results)

        # Assemble tool results back into messages
        cfg = self._agent._get_config()
        max_chars = getattr(
            getattr(cfg.agents, 'context', None),
            'max_tool_result_chars',
            _MAX_TOOL_RESULT_CHARS,
        )
        for tc, result in zip(ctx.tool_calls, ctx.results):
            if isinstance(result, BaseException):
                logger.error(f"Tool {tc.name} raised: {result}")
            normalized = _normalize_tool_result(result, tc.name, max_chars=max_chars)
            ctx.messages = self._agent.context.add_tool_result(
                ctx.messages, tc.id, tc.name, normalized
            )
