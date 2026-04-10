"""Phase 41: Core types — TurnContext, TurnAction, AgentMiddleware.

TurnContext is the controlled single-turn context that flows through the
middleware pipeline.  State changes MUST go through method APIs (abort/finish)
to prevent ad-hoc mutation bugs (Opus critique F1).

AgentMiddleware is the two-phase base class.  Both hooks are optional no-ops.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    pass


class TurnAction(Enum):
    """Outcome of a single agent loop iteration."""

    CONTINUE = "continue"   # Normal iteration complete, while loop continues
    ABORT    = "abort"       # Short-circuited by middleware (L1/HITL/CB), while breaks
    FINISH   = "finish"     # LLM returned plain text (no tools), natural end


class TurnContext:
    """Controlled single-turn iteration context.

    State changes MUST go through ``abort()`` / ``finish()`` methods.
    Direct mutation of ``_action`` is forbidden.

    Attributes set by the while-loop caller:
        messages, iteration, channel, chat_id
        consecutive_all_exceptions, recent_call_sigs, action_log,
        message_call_count, loop_injection_used

    Attributes set by ToolExecutor:
        tool_calls, results, llm_response
    """

    __slots__ = (
        "messages", "iteration", "channel", "chat_id",
        "consecutive_all_exceptions", "recent_call_sigs",
        "action_log", "message_call_count", "loop_injection_used",
        "tool_calls", "results", "llm_response",
        "_action", "_action_reason", "_final_content",
        "_metrics_start",  # Used by MetricsMiddleware
        "tool_registry_override",
    )

    def __init__(
        self,
        *,
        messages: list[dict],
        iteration: int,
        channel: str | None,
        chat_id: str | None,
        # Cross-turn persistent state (passed by the while loop)
        consecutive_all_exceptions: int,
        recent_call_sigs: list[str],
        action_log: list[dict],
        message_call_count: int,
        loop_injection_used: int,
    ):
        # Input context (middlewares may append to messages, must not replace)
        self.messages = messages
        self.iteration = iteration
        self.channel = channel
        self.chat_id = chat_id

        # Cross-turn readable/mutable state
        self.consecutive_all_exceptions = consecutive_all_exceptions
        self.recent_call_sigs = recent_call_sigs
        self.action_log = action_log
        self.message_call_count = message_call_count
        self.loop_injection_used = loop_injection_used

        # Per-turn output (filled by ToolExecutor)
        self.tool_calls: list[Any] = []
        self.results: list[Any] = []
        self.llm_response: Any = None
        self.tool_registry_override: Any = None

        # Private control state — read-only props + dedicated transition methods
        self._action = TurnAction.CONTINUE
        self._action_reason: str = ""
        self._final_content: str | None = None

    # ── Control API ──────────────────────────────────────────────────

    def abort(self, reason: str, final_content: str | None = None) -> None:
        """Middleware calls this to short-circuit the current turn.

        First-come-first-served: subsequent abort/finish calls are ignored
        to prevent middlewares from overriding each other.
        """
        if self._action == TurnAction.CONTINUE:
            self._action = TurnAction.ABORT
            self._action_reason = reason
            if final_content is not None:
                self._final_content = final_content

    def finish(self, final_content: str | None = None) -> None:
        """Executor calls this when the LLM returns plain text (no tools).

        Respects first-come-first-served: if already aborted, finish is ignored.
        """
        if self._action == TurnAction.CONTINUE:  # Only transition from CONTINUE
            self._action = TurnAction.FINISH
            if final_content is not None:
                self._final_content = final_content

    # ── Read-only properties ─────────────────────────────────────────

    @property
    def action(self) -> TurnAction:
        return self._action

    @property
    def is_aborted(self) -> bool:
        return self._action == TurnAction.ABORT

    @property
    def final_content(self) -> str | None:
        return self._final_content

    @property
    def action_reason(self) -> str:
        return self._action_reason


class AgentMiddleware:
    """Two-phase flat onion node.

    - ``pre_process``:  Called before the inner layer (including ToolExecutor)
    - ``post_process``: Called after the inner layer (in LIFO order)

    Both hooks are optional; default implementation is a no-op.
    """

    async def pre_process(self, ctx: TurnContext) -> None:
        """Pre-hook: may modify ctx.messages, may call ctx.abort() to short-circuit."""

    async def post_process(self, ctx: TurnContext) -> None:
        """Post-hook: may read ctx.results, may modify cross-turn state fields."""
