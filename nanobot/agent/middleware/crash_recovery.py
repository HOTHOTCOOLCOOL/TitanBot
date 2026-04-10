"""Phase 41: CrashRecoveryMiddleware — P40B-1 WAL checkpoint management.

Pre:  Writes a checkpoint WAL file before tool execution so that crash
      recovery can detect interrupted operations on restart.
Post: Clears the checkpoint WAL after execution completes (always, via finally).

Positioned AFTER Verification/HITL in the middleware stack (P4 fix) to avoid
writing checkpoints for tool calls that will be rejected by L1 or suspended
by HITL.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from loguru import logger

from nanobot.agent.middleware.base import AgentMiddleware, TurnContext

if TYPE_CHECKING:
    from nanobot.agent.loop import AgentLoop


class CrashRecoveryMiddleware(AgentMiddleware):
    """WAL checkpoint write (pre) and clear (post) around tool execution."""

    def __init__(self, agent: AgentLoop):
        self._agent = agent
        self._ckpt_path = None

    async def pre_process(self, ctx: TurnContext) -> None:
        """Write WAL checkpoint before tools execute."""
        if not ctx.tool_calls or not ctx.channel or not ctx.chat_id:
            return
        try:
            cfg = self._agent._get_config()
            enabled = getattr(
                getattr(cfg.agents, 'reliability', None),
                'checkpoint_enabled',
                True,
            )
            if not enabled:
                return

            session_key = self._agent.sessions.resolve_key(
                f"{ctx.channel}:{ctx.chat_id}"
            )
            tool_infos = [
                {"name": tc.name, "arguments": tc.arguments}
                for tc in ctx.tool_calls
            ]
            self._ckpt_path = self._agent.sessions.write_checkpoint(
                session_key, tool_infos
            )
        except Exception as e:
            logger.error(
                f"CrashRecoveryMiddleware.pre: WAL write failed (non-critical): {e}"
            )

    async def post_process(self, ctx: TurnContext) -> None:
        """Clear WAL checkpoint (always, regardless of success/failure)."""
        if not self._ckpt_path:
            return
        try:
            self._agent.sessions.clear_checkpoint(self._ckpt_path)
        except Exception as e:
            logger.error(
                f"CrashRecoveryMiddleware.post: WAL clear failed (non-critical): {e}"
            )
        finally:
            self._ckpt_path = None
