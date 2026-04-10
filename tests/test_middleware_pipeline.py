"""Phase 41: Unit tests for the onion middleware pipeline.

Tests:
1. TurnContext abort/finish state machine (first-come-first-served)
2. MiddlewarePipeline pre/post execution order (LIFO verification)
3. Abort short-circuit (pre abort skips inner layers but post still runs)
4. Module-level _is_error_result boundary cases
5. Individual middleware isolation tests
"""

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from nanobot.agent.middleware.base import (
    TurnAction,
    TurnContext,
    AgentMiddleware,
)
from nanobot.agent.middleware.pipeline import MiddlewarePipeline


# ── Helpers ──────────────────────────────────────────────────────────

def _make_ctx(**overrides) -> TurnContext:
    """Create a TurnContext with sensible defaults."""
    defaults = dict(
        messages=[{"role": "system", "content": "test"}],
        iteration=1,
        channel="test",
        chat_id="user1",
        consecutive_all_exceptions=0,
        recent_call_sigs=[],
        action_log=[],
        message_call_count=0,
        loop_injection_used=0,
    )
    defaults.update(overrides)
    return TurnContext(**defaults)


class RecordingMiddleware(AgentMiddleware):
    """Middleware that records pre/post call order for testing."""

    def __init__(self, name: str, log: list):
        self.name = name
        self.log = log

    async def pre_process(self, ctx: TurnContext) -> None:
        self.log.append(f"pre:{self.name}")

    async def post_process(self, ctx: TurnContext) -> None:
        self.log.append(f"post:{self.name}")


class AbortingMiddleware(AgentMiddleware):
    """Middleware that aborts during pre_process."""

    def __init__(self, log: list):
        self.log = log

    async def pre_process(self, ctx: TurnContext) -> None:
        self.log.append("pre:aborter")
        ctx.abort("test_abort", "aborted!")

    async def post_process(self, ctx: TurnContext) -> None:
        self.log.append("post:aborter")


class DummyToolExecutor:
    """Stand-in for ToolExecutor in tests."""

    def __init__(self, log: list):
        self.log = log

    async def execute(self, ctx: TurnContext) -> None:
        self.log.append("executor")


# ── TurnContext State Machine Tests ──────────────────────────────────

class TestTurnContext:
    def test_initial_state(self):
        ctx = _make_ctx()
        assert ctx.action == TurnAction.CONTINUE
        assert ctx.is_aborted is False
        assert ctx.final_content is None
        assert ctx.action_reason == ""

    def test_abort(self):
        ctx = _make_ctx()
        ctx.abort("test_reason", "goodbye")
        assert ctx.action == TurnAction.ABORT
        assert ctx.is_aborted is True
        assert ctx.final_content == "goodbye"
        assert ctx.action_reason == "test_reason"

    def test_abort_first_come_first_served(self):
        """Second abort call should be ignored."""
        ctx = _make_ctx()
        ctx.abort("first", "first_msg")
        ctx.abort("second", "second_msg")
        assert ctx.action_reason == "first"
        assert ctx.final_content == "first_msg"

    def test_finish(self):
        ctx = _make_ctx()
        ctx.finish("all done")
        assert ctx.action == TurnAction.FINISH
        assert ctx.final_content == "all done"

    def test_abort_blocks_finish(self):
        """Once aborted, finish should not override."""
        ctx = _make_ctx()
        ctx.abort("reason", "aborted")
        ctx.finish("finished")  # Should be ignored
        assert ctx.action == TurnAction.ABORT
        assert ctx.final_content == "aborted"

    def test_abort_without_content(self):
        ctx = _make_ctx()
        ctx.abort("reason")
        assert ctx.action == TurnAction.ABORT
        assert ctx.final_content is None


# ── Pipeline Execution Order Tests ───────────────────────────────────

class TestMiddlewarePipeline:
    @pytest.mark.asyncio
    async def test_pre_post_order_is_lifo(self):
        """Pre runs outer→inner, Post runs inner→outer (LIFO)."""
        log = []
        pipeline = MiddlewarePipeline(
            middlewares=[
                RecordingMiddleware("A", log),
                RecordingMiddleware("B", log),
                RecordingMiddleware("C", log),
            ],
            executor=DummyToolExecutor(log),
        )
        ctx = _make_ctx()
        await pipeline.run_turn(ctx)

        assert log == [
            "pre:A", "pre:B", "pre:C",
            "executor",
            "post:C", "post:B", "post:A",
        ]

    @pytest.mark.asyncio
    async def test_abort_skips_remaining_pre_and_executor(self):
        """Abort in middle layer skips deeper pre and executor."""
        log = []
        pipeline = MiddlewarePipeline(
            middlewares=[
                RecordingMiddleware("outer", log),
                AbortingMiddleware(log),
                RecordingMiddleware("inner", log),
            ],
            executor=DummyToolExecutor(log),
        )
        ctx = _make_ctx()
        await pipeline.run_turn(ctx)

        # outer.pre → aborter.pre → (SKIP inner.pre, executor)
        # aborter.post → outer.post  (LIFO from entered)
        assert log == [
            "pre:outer", "pre:aborter",
            "post:aborter", "post:outer",
        ]
        assert ctx.is_aborted
        assert ctx.final_content == "aborted!"

    @pytest.mark.asyncio
    async def test_executor_exception_triggers_abort(self):
        """If ToolExecutor raises, pipeline aborts gracefully."""
        log = []

        class FailingExecutor:
            async def execute(self, ctx):
                raise RuntimeError("tool crash")

        pipeline = MiddlewarePipeline(
            middlewares=[RecordingMiddleware("A", log)],
            executor=FailingExecutor(),
        )
        ctx = _make_ctx()
        await pipeline.run_turn(ctx)

        assert ctx.is_aborted
        assert "executor_error" in ctx.action_reason
        assert log == ["pre:A", "post:A"]

    @pytest.mark.asyncio
    async def test_middleware_pre_exception_triggers_abort(self):
        """If a middleware pre_process raises, abort and still run post."""
        log = []

        class CrashingMiddleware(AgentMiddleware):
            async def pre_process(self, ctx):
                raise ValueError("boom")
            async def post_process(self, ctx):
                log.append("post:crasher")

        pipeline = MiddlewarePipeline(
            middlewares=[CrashingMiddleware()],
            executor=DummyToolExecutor(log),
        )
        ctx = _make_ctx()
        await pipeline.run_turn(ctx)

        assert ctx.is_aborted
        assert "mw_error" in ctx.action_reason
        assert "post:crasher" in log

    @pytest.mark.asyncio
    async def test_empty_pipeline_runs_executor_only(self):
        """Pipeline with no middlewares still runs the executor."""
        log = []
        pipeline = MiddlewarePipeline(
            middlewares=[],
            executor=DummyToolExecutor(log),
        )
        ctx = _make_ctx()
        await pipeline.run_turn(ctx)
        assert log == ["executor"]
        assert not ctx.is_aborted


# ── Module-level _is_error_result Tests ──────────────────────────────

class TestIsErrorResult:
    def test_base_exception(self):
        from nanobot.agent.loop import _is_error_result
        assert _is_error_result(RuntimeError("fail")) is True

    def test_error_string_prefix(self):
        from nanobot.agent.loop import _is_error_result
        assert _is_error_result("Error: something went wrong") is True

    def test_action_failed_string(self):
        from nanobot.agent.loop import _is_error_result
        assert _is_error_result("Some text ⚠️ ACTION FAILED: click") is True

    def test_normal_string(self):
        from nanobot.agent.loop import _is_error_result
        assert _is_error_result("Success: task completed") is False

    def test_none_via_str(self):
        from nanobot.agent.loop import _is_error_result
        # None would be caught by str conversion
        assert _is_error_result(None) is False

    def test_integer(self):
        from nanobot.agent.loop import _is_error_result
        assert _is_error_result(42) is False


# ── FloodGuardMiddleware Tests ───────────────────────────────────────

class TestFloodGuardMiddleware:
    @pytest.mark.asyncio
    async def test_flood_guard_triggers(self):
        from nanobot.agent.middleware.flood_guard import FloodGuardMiddleware

        mw = FloodGuardMiddleware()
        ctx = _make_ctx(message_call_count=2)

        # Simulate 1 message() tool call → total becomes 3 (== _MAX_MESSAGE_CALLS)
        tc = MagicMock()
        tc.name = "message"
        ctx.tool_calls = [tc]

        await mw.post_process(ctx)
        assert ctx.is_aborted
        assert ctx.action_reason == "flood_guard"

    @pytest.mark.asyncio
    async def test_flood_guard_no_trigger(self):
        from nanobot.agent.middleware.flood_guard import FloodGuardMiddleware

        mw = FloodGuardMiddleware()
        ctx = _make_ctx(message_call_count=0)

        tc = MagicMock()
        tc.name = "exec"
        ctx.tool_calls = [tc]

        await mw.post_process(ctx)
        assert not ctx.is_aborted


# ── MetricsMiddleware Tests ──────────────────────────────────────────

class TestMetricsMiddleware:
    @pytest.mark.asyncio
    async def test_records_timing(self):
        from nanobot.agent.middleware.metrics import MetricsMiddleware
        from nanobot.utils.metrics import metrics

        mw = MetricsMiddleware()
        ctx = _make_ctx()

        await mw.pre_process(ctx)
        assert hasattr(ctx, '_metrics_start')

        await mw.post_process(ctx)
        timing = metrics.get_timing("loop_iteration_ms")
        assert timing["count"] >= 1
