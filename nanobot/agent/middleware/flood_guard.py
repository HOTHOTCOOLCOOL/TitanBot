from __future__ import annotations
"""Phase 41: FloodGuardMiddleware — message() call flood prevention.

Post: Counts message() tool invocations and triggers abort when the
      safety threshold (_MAX_MESSAGE_CALLS) is exceeded.
"""


from loguru import logger

from nanobot.agent.middleware.base import AgentMiddleware, TurnContext
from nanobot.agent.loop import _MAX_MESSAGE_CALLS


class FloodGuardMiddleware(AgentMiddleware):
    """Prevents the agent from flooding the user with too many message() calls."""

    async def post_process(self, ctx: TurnContext) -> None:
        for tc in ctx.tool_calls:
            if tc.name == "message":
                ctx.message_call_count += 1

        if ctx.message_call_count >= _MAX_MESSAGE_CALLS:
            logger.warning(
                f"Message flood guard: {ctx.message_call_count} message() "
                f"calls, breaking loop"
            )
            from nanobot.utils.trace_context import add_route_tag, InterceptTag
            add_route_tag(InterceptTag.FLOOD_BLOCK)
            ctx.abort("flood_guard")
