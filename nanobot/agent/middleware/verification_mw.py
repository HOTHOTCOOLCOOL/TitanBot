"""Phase 41 (P41-4): VerificationMiddleware — L1 rule interception & L3 audit.

Pre:  Runs L1 rigid rules against proposed tool calls. If violations are found,
      injects synthetic error results into messages and aborts with reason
      'l1_violation' so the while loop can `continue` (let LLM self-correct).
Post: Runs L3 anti-pattern audit (log-only, fire-and-forget).

File named verification_mw.py to avoid module name collision with
nanobot.agent.verification.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from loguru import logger

from nanobot.agent.middleware.base import AgentMiddleware, TurnContext

if TYPE_CHECKING:
    from nanobot.agent.loop import AgentLoop


class VerificationMiddleware(AgentMiddleware):
    """L1 pre-execution rule check + L3 post-execution audit."""

    def __init__(self, agent: AgentLoop):
        self._agent = agent

    async def pre_process(self, ctx: TurnContext) -> None:
        """L1: Check rigid rules against proposed tool calls."""
        if not ctx.tool_calls:
            return

        verification = self._agent._get_verification()
        registry = getattr(ctx, "tool_registry_override", None) or self._agent.tools
        cfg = self._agent._get_config()
        overrides = cfg.agents.sandbox.capability_overrides if cfg and getattr(cfg, 'agents', None) and getattr(cfg.agents, 'sandbox', None) else {}
        rule_result = verification.check_rules(ctx.tool_calls, ctx.messages, registry=registry, config_overrides=overrides)

        if not rule_result.passed:
            logger.warning(
                f"L1: Blocking {len(rule_result.violations)} violation(s)"
            )
            # Inject violation feedback as synthetic tool results
            # so the LLM can self-correct instead of hard-failing
            for tc in ctx.tool_calls:
                ctx.messages = self._agent.context.add_tool_result(
                    ctx.messages,
                    tc.id,
                    tc.name,
                    f"Error: Action blocked by verification layer. "
                    f"{rule_result.rewrite_hint}",
                )
            # Use 'l1_violation' reason so the while loop continues
            # instead of breaking — gives LLM a chance to self-correct
            from nanobot.utils.trace_context import add_route_tag, InterceptTag
            add_route_tag(InterceptTag.L1_BLOCK)
            ctx.abort("l1_violation")

    async def post_process(self, ctx: TurnContext) -> None:
        """L3: Anti-pattern audit (log-only, non-critical)."""
        tool_calls_with_args = [
            {"tool": tc.name, "args": tc.arguments}
            for tc in ctx.tool_calls
        ]
        if not tool_calls_with_args:
            return

        try:
            self._agent._get_verification().audit_antipatterns(
                tool_calls_with_args
            )
        except Exception as e:
            logger.debug(f"L3 anti-pattern audit error (non-critical): {e}")
