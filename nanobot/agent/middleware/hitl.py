"""Phase 41 (P41-5): HITLMiddleware — Human-in-the-Loop approval gateway.

Pre:  Checks tool calls for high-risk operations (RiskTier >= MUTATE_EXTERNAL).
      If approval is required, suspends the session and aborts with a prompt
      for the user to approve/reject/always-approve.
Post: No-op (approval resolution happens in state_handler.py, not here).
"""

from __future__ import annotations

import asyncio
import json
import time
from typing import TYPE_CHECKING

from loguru import logger

from nanobot.agent.middleware.base import AgentMiddleware, TurnContext
from nanobot.bus.events import OutboundMessage

if TYPE_CHECKING:
    from nanobot.agent.loop import AgentLoop


class HITLMiddleware(AgentMiddleware):
    """Smart HITL approval gate for high-risk tool operations."""

    def __init__(self, agent: AgentLoop):
        self._agent = agent

    async def pre_process(self, ctx: TurnContext) -> None:
        """Check each tool call for HITL approval requirements."""
        if not ctx.channel or not ctx.chat_id:
            return

        from nanobot.agent.tools.base import RiskTier

        for tc in ctx.tool_calls:
            registry = getattr(ctx, "tool_registry_override", None) or self._agent.tools
            tool_impl = registry.get(tc.name)
            if not tool_impl or not hasattr(tool_impl, "get_risk_tier"):
                continue

            tier = tool_impl.get_risk_tier(tc.arguments)
            if tier.value < RiskTier.MUTATE_EXTERNAL.value:
                continue

            approval_store = self._agent._get_approval_store()

            # Phase 33 SEC-BUW-1: Forced-HITL for script execution
            forced_hitl = False
            if tc.name == "exec" and "command" in tc.arguments:
                cmd = str(tc.arguments["command"]).lower()
                if any(
                    x in cmd
                    for x in [".py", ".sh", ".ps1", "python -c", "node -e"]
                ):
                    forced_hitl = True
                    logger.warning(
                        f"Forced-HITL triggered for script execution: "
                        f"{cmd[:50]}"
                    )

            is_approved = (
                approval_store.is_approved(tc.name, tc.arguments)
                if approval_store
                else False
            )

            if not forced_hitl and is_approved:
                continue

            # ── HITL triggered ──
            session_key = self._agent.sessions.resolve_key(
                f"{ctx.channel}:{ctx.chat_id}"
            )
            session = self._agent.sessions._cache.get(session_key)
            if not session:
                continue

            short_id = tc.id[-4:].upper()
            session.pending_approval_task = {
                "tool": tc.name,
                "arguments": tc.arguments,
                "id": tc.id,
                "short_id": short_id,
                "timestamp": time.time(),
            }
            self._agent.sessions.save(session)
            self._agent.sessions.register_approval(short_id, session.key)

            hitl_msg = (
                f"⚠️ **Action Required!**\n\n"
                f"The agent is attempting a High-Risk operation:\n"
                f"- **Tool**: `{tc.name}`\n"
                f"- **Args**: `{json.dumps(tc.arguments, ensure_ascii=False)}`\n\n"
                f"Please reply with:\n"
                f"1. `Approve {short_id}` (allow this time)\n"
                f"2. `Always {short_id}` (allow this and future identical actions)\n"
                f"3. `Reject {short_id}` (block the action)\n\n"
                f"*(You can also just reply 'Approve' if approving from the "
                f"origin channel)*"
            )

            # Broadcast remote approval prompt to master identities
            cfg = self._agent._get_config()
            for target in cfg.master_identities.keys():
                if ":" in target:
                    t_chan, t_chat = target.split(":", 1)
                    if f"{t_chan}:{t_chat}" != session_key:
                        b_msg = (
                            f"🔔 **Remote Approval Request [{short_id}]**\n"
                            f"Origin: `{session_key}`\n\n{hitl_msg}"
                        )
                        asyncio.create_task(
                            self._agent.bus.publish_outbound(
                                OutboundMessage(
                                    channel=t_chan,
                                    chat_id=t_chat,
                                    content=b_msg,
                                )
                            )
                        )

            from nanobot.utils.trace_context import add_route_tag, InterceptTag
            add_route_tag(InterceptTag.HITL_SUSPEND)
            ctx.abort("hitl", hitl_msg)
            break  # Only process the first tool call requiring approval
