"""Phase 41: ActionHistoryMiddleware — browser/RPA action tracking (Phase 33).

Pre:  Injects compact action history into system prompt for browser/RPA tasks.
Post: Records tool outcomes into the cross-turn action log.
"""

from __future__ import annotations

from nanobot.agent.middleware.base import AgentMiddleware, TurnContext
from nanobot.agent.loop import (
    _build_action_history_summary,
    _ACTION_HISTORY_SENTINEL,
    _ACTION_HISTORY_MAX,
    _INJECTION_BUDGET,
    _MAX_ACTION_HISTORY,
)


class ActionHistoryMiddleware(AgentMiddleware):
    """Tracks browser/RPA action outcomes and injects history into system prompt."""

    async def pre_process(self, ctx: TurnContext) -> None:
        """Inject action history summary into system prompt if browser/rpa actions exist."""
        if not ctx.action_log:
            return
        if not any(e["tool"] in ("browser", "rpa") for e in ctx.action_log):
            return

        history_summary = _build_action_history_summary(ctx.action_log)
        if not history_summary:
            return
        if not ctx.messages or ctx.messages[0].get("role") != "system":
            return

        sys_content = ctx.messages[0]["content"]

        # Remove stale history from previous iteration (idempotent)
        sentinel_idx = sys_content.find(_ACTION_HISTORY_SENTINEL)
        if sentinel_idx != -1:
            sys_content = sys_content[:sentinel_idx]

        # Budget check
        history_len = len(history_summary) + len(_ACTION_HISTORY_SENTINEL)
        remaining = _INJECTION_BUDGET - ctx.loop_injection_used
        if history_len <= _ACTION_HISTORY_MAX and history_len <= remaining:
            ctx.messages[0]["content"] = (
                sys_content + _ACTION_HISTORY_SENTINEL + history_summary
            )
            ctx.loop_injection_used += history_len

    async def post_process(self, ctx: TurnContext) -> None:
        """Record browser/rpa/browser_use_worker outcomes into action log."""
        for tool_call, result in zip(ctx.tool_calls, ctx.results):
            if tool_call.name not in ("browser", "rpa", "browser_use_worker"):
                continue

            _is_err = isinstance(result, BaseException) or (
                isinstance(result, str)
                and (
                    result.startswith("Error:")
                    or "⚠️ ACTION FAILED:" in result
                )
            )
            _is_verify = (
                isinstance(result, str)
                and "__IMAGE__:" in result
                and not _is_err
            )

            ctx.action_log.append({
                "tool": tool_call.name,
                "action": tool_call.arguments.get("action", ""),
                "outcome": (
                    "error" if _is_err
                    else ("pending_verify" if _is_verify else "ok")
                ),
                "detail": (
                    str(result)[:80] if _is_err
                    else tool_call.arguments.get("selector", "")[:80]
                ),
            })
            if len(ctx.action_log) > _MAX_ACTION_HISTORY:
                del ctx.action_log[:-_MAX_ACTION_HISTORY]
