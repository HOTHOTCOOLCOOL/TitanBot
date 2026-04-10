"""Phase 41: MiddlewarePipeline — iterative two-phase executor (zero closures).

Eliminates the call_next closure recursion from classical onion patterns
(Opus critique S4).  Stack depth is always O(1) regardless of middleware count.
Tracebacks remain clean and readable.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from loguru import logger

from nanobot.agent.middleware.base import AgentMiddleware, TurnContext

if TYPE_CHECKING:
    from nanobot.agent.middleware.tool_executor import ToolExecutor


class MiddlewarePipeline:
    """Flat iterative executor for the onion middleware stack.

    Execution order:
        1. Pre-process:  outer → inner (in registration order)
        2. ToolExecutor:  core tool execution (only if not aborted)
        3. Post-process: inner → outer (LIFO — reversed ``entered`` list)

    Any middleware exception during pre/post is caught and logged but does NOT
    kill the agent loop (Lesson #3: limit blast radius of non-core failures).
    """

    def __init__(
        self,
        middlewares: list[AgentMiddleware],
        executor: ToolExecutor,
    ):
        self._middlewares = middlewares
        self._executor = executor

    async def run_turn(self, ctx: TurnContext) -> None:
        """Execute a full onion pipeline for one agent loop iteration."""
        entered: list[AgentMiddleware] = []

        # 1. Pre-process: outer → inner
        for mw in self._middlewares:
            try:
                await mw.pre_process(ctx)
            except Exception as e:
                logger.error(
                    f"Middleware {mw.__class__.__name__}.pre_process error: {e}"
                )
                ctx.abort(
                    f"mw_error:{mw.__class__.__name__}",
                    "⚠️ 中间件内部错误，已安全跳出。",
                )
            entered.append(mw)  # Even if aborted, this layer gets post_process
            if ctx.is_aborted:
                break

        # 2. Core ToolExecutor (only if not short-circuited)
        if not ctx.is_aborted:
            try:
                await self._executor.execute(ctx)
            except Exception as e:
                logger.error(
                    f"ToolExecutor.execute error: {e}", exc_info=True
                )
                ctx.abort(
                    "executor_error",
                    f"⚠️ 工具执行时发生内部错误：{e}",
                )

        # 3. Post-process: LIFO (reversed entered list)
        for mw in reversed(entered):
            try:
                await mw.post_process(ctx)
            except Exception as e:
                logger.error(
                    f"Middleware {mw.__class__.__name__}.post_process error: {e}"
                )
                # post_process errors do NOT change action; only log (Lesson #3)
