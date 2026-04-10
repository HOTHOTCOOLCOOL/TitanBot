"""Phase 41 (P41-3): CircuitBreakerMiddleware — failure detection & loop termination.

Handles three types of loop detection:
1. Consecutive all-exception turns (circuit breaker threshold = 3)
2. L14 exact duplicate tool call detection
3. Phase 33 fuzzy loop detection (semantic tool-action pattern repetition)

Also fires Phase 37 post-mortem extraction on any detected loop/breaker event.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from loguru import logger

from nanobot.agent.middleware.base import AgentMiddleware, TurnContext
from nanobot.agent.loop import (
    _detect_fuzzy_loop,
    _is_error_result,
    _SIG_DELIMITER,
    _FUZZY_LOOP_WINDOW,
)

if TYPE_CHECKING:
    from nanobot.agent.loop import AgentLoop

_CB_THRESHOLD = 3
_DUPLICATE_THRESHOLD = 3


class CircuitBreakerMiddleware(AgentMiddleware):
    """Post-process only: detects failure loops and triggers abort."""

    def __init__(self, agent: AgentLoop):
        self._agent = agent

    async def post_process(self, ctx: TurnContext) -> None:
        if ctx.is_aborted or not ctx.results:
            return

        # 1. All-exception circuit breaker
        all_errors = all(_is_error_result(r) for r in ctx.results)
        if all_errors:
            ctx.consecutive_all_exceptions += 1
            logger.warning(
                f"All {len(ctx.results)} tools failed "
                f"(streak: {ctx.consecutive_all_exceptions})"
            )
            if ctx.consecutive_all_exceptions >= _CB_THRESHOLD:
                logger.error(
                    f"Circuit breaker: {ctx.consecutive_all_exceptions} "
                    f"consecutive all-exception turns. Breaking."
                )
                from nanobot.utils.trace_context import add_route_tag, InterceptTag
                add_route_tag(InterceptTag.CB_TRIP)
                self._fire_postmortem(ctx, "circuit_breaker")
                ctx.abort(
                    "circuit_breaker",
                    "⚠️ Multiple consecutive tool failures detected. "
                    "Please check your request and try again.",
                )
                return
        else:
            ctx.consecutive_all_exceptions = 0

        # 2. L14 exact duplicate detection
        _sig = _SIG_DELIMITER.join(
            f"{tc.name}:{json.dumps(tc.arguments, sort_keys=True)}"
            for tc in ctx.tool_calls
        )
        ctx.recent_call_sigs.append(_sig)
        _SIG_RETENTION = max(_DUPLICATE_THRESHOLD, _FUZZY_LOOP_WINDOW)
        if len(ctx.recent_call_sigs) > _SIG_RETENTION:
            del ctx.recent_call_sigs[:-_SIG_RETENTION]

        if (
            len(ctx.recent_call_sigs) >= _DUPLICATE_THRESHOLD
            and len(set(ctx.recent_call_sigs[-_DUPLICATE_THRESHOLD:])) == 1
        ):
            logger.warning(
                f"Duplicate tool call detected ({_DUPLICATE_THRESHOLD}x): "
                f"{_sig[:120]}..."
            )
            from nanobot.utils.trace_context import add_route_tag, InterceptTag
            add_route_tag(InterceptTag.CB_TRIP)
            self._fire_postmortem(ctx, "duplicate_loop")
            ctx.abort(
                "duplicate_loop",
                "⚠️ I appear to be stuck in a loop calling the same tool "
                "repeatedly. Please rephrase your request or try a different "
                "approach.",
            )
            return

        # 3. Fuzzy loop detection
        if _detect_fuzzy_loop(ctx.recent_call_sigs):
            logger.warning(
                "Fuzzy loop detected: tool-action pattern repeating."
            )
            from nanobot.utils.trace_context import add_route_tag, InterceptTag
            add_route_tag(InterceptTag.CB_TRIP)
            self._fire_postmortem(ctx, "fuzzy_loop")
            ctx.abort(
                "fuzzy_loop",
                "⚠️ I appear to be stuck repeating similar actions without "
                "progress. Please check if the page loaded correctly, or try "
                "a different approach.",
            )

    def _fire_postmortem(self, ctx: TurnContext, reason: str) -> None:
        """Fire-and-forget Phase 37 post-mortem extraction."""
        from nanobot.agent.commands import _safe_create_task

        _user_req = ""
        for m in reversed(ctx.messages):
            if m.get("role") == "user" and isinstance(m.get("content"), str):
                _user_req = m["content"][:200]
                break

        _last_err = str(ctx.results[0])[:500] if ctx.results else "unknown"
        _safe_create_task(
            self._agent._extract_trace_postmortem(
                request_text=_user_req,
                tool_calls_with_args=[
                    {"tool": tc.name, "args": tc.arguments}
                    for tc in ctx.tool_calls
                ],
                action_log=ctx.action_log,
                last_error=_last_err,
                break_reason=reason,
            ),
            name=f"p37_postmortem_{reason}",
        )
