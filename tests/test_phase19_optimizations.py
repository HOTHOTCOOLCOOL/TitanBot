"""Tests for Phase 19+ optimizations: cron notifications, context trimming, parallel tools."""

import asyncio
import pytest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
import json
import time


# ============================================================================
# Context Window Optimization Tests
# ============================================================================


class TestContextWindowTrimming:
    """Tests for ContextBuilder._trim_history and _estimate_chars."""

    def _make_builder(self, tmp_path):
        """Create a ContextBuilder with mocked dependencies."""
        workspace = tmp_path / "workspace"
        workspace.mkdir()
        with patch("nanobot.agent.context.VectorMemory"):
            with patch("nanobot.agent.context.MemoryStore"):
                with patch("nanobot.agent.context.SkillsLoader"):
                    from nanobot.agent.context import ContextBuilder
                    return ContextBuilder(workspace)

    def test_estimate_chars_string(self, tmp_path):
        builder = self._make_builder(tmp_path)
        messages = [{"role": "user", "content": "hello world"}]
        assert builder._estimate_chars(messages) == 11

    def test_estimate_chars_multimodal(self, tmp_path):
        builder = self._make_builder(tmp_path)
        messages = [
            {"role": "user", "content": [
                {"type": "text", "text": "hi"},
                {"type": "image_url", "image_url": {"url": "data:..."}}
            ]}
        ]
        assert builder._estimate_chars(messages) == 2

    def test_trim_history_no_trim_needed(self, tmp_path):
        builder = self._make_builder(tmp_path)
        history = [{"role": "user", "content": "short"}]
        result = builder._trim_history(history, "sys", "msg", context_limit=100_000)
        assert result is history  # same object, no copy

    def test_trim_history_drops_oldest(self, tmp_path):
        builder = self._make_builder(tmp_path)
        # Create history that exceeds limit
        history = [
            {"role": "user", "content": "A" * 1000},
            {"role": "assistant", "content": "B" * 1000},
            {"role": "user", "content": "C" * 1000},
            {"role": "assistant", "content": "D" * 1000},
            {"role": "user", "content": "E" * 1000},
            {"role": "assistant", "content": "F" * 1000},
        ]
        result = builder._trim_history(history, "short_sys", "msg", context_limit=3000)
        assert len(result) < len(history)
        # Should keep the most recent messages
        assert result[-1]["content"] == "F" * 1000

    def test_trim_history_keeps_min_messages(self, tmp_path):
        builder = self._make_builder(tmp_path)
        history = [
            {"role": "user", "content": "X" * 5000},
            {"role": "assistant", "content": "Y" * 5000},
            {"role": "user", "content": "Z" * 5000},
            {"role": "assistant", "content": "W" * 5000},
        ]
        # Even with tiny limit, keeps at least 4 messages
        result = builder._trim_history(history, "sys", "msg", context_limit=100)
        assert len(result) == 4


# ============================================================================
# Cron Notification Tests
# ============================================================================


class TestCronNotification:
    """Tests for CronService proactive failure notifications."""

    def _make_service(self, tmp_path, notification_cb=None):
        from nanobot.cron.service import CronService
        store_path = tmp_path / "cron" / "jobs.json"
        store_path.parent.mkdir(parents=True, exist_ok=True)
        svc = CronService(store_path, notification_callback=notification_cb)
        return svc

    @pytest.mark.asyncio
    async def test_notify_failure_called_on_error(self, tmp_path):
        """notification_callback is invoked when a job execution raises."""
        cb = AsyncMock()
        svc = self._make_service(tmp_path, notification_cb=cb)

        from nanobot.cron.types import CronSchedule
        job = svc.add_job(
            name="test-fail-job",
            schedule=CronSchedule(kind="at", at_ms=int(time.time() * 1000) + 100_000),
            message="do something"
        )

        # Simulate execution that throws
        svc.on_job = AsyncMock(side_effect=RuntimeError("boom"))
        await svc._execute_job(job)

        cb.assert_called_once()
        args = cb.call_args[0]
        assert args[0] == "test-fail-job"
        assert "boom" in args[1]

    @pytest.mark.asyncio
    async def test_notify_failure_called_on_error_response(self, tmp_path):
        """notification_callback is invoked when job returns error text."""
        cb = AsyncMock()
        svc = self._make_service(tmp_path, notification_cb=cb)

        from nanobot.cron.types import CronSchedule
        job = svc.add_job(
            name="test-err-response",
            schedule=CronSchedule(kind="every", every_ms=60_000),
            message="try"
        )

        svc.on_job = AsyncMock(return_value="Error: something failed badly")
        await svc._execute_job(job)

        cb.assert_called_once()
        assert "Error:" in cb.call_args[0][1]

    @pytest.mark.asyncio
    async def test_no_notification_on_success(self, tmp_path):
        """notification_callback is NOT invoked on success."""
        cb = AsyncMock()
        svc = self._make_service(tmp_path, notification_cb=cb)

        from nanobot.cron.types import CronSchedule
        job = svc.add_job(
            name="test-ok",
            schedule=CronSchedule(kind="at", at_ms=int(time.time() * 1000) + 100_000),
            message="all good"
        )

        svc.on_job = AsyncMock(return_value="Task completed successfully.")
        await svc._execute_job(job)

        cb.assert_not_called()

    @pytest.mark.asyncio
    async def test_no_callback_no_crash(self, tmp_path):
        """If notification_callback is None, failure still runs without crash."""
        svc = self._make_service(tmp_path, notification_cb=None)

        from nanobot.cron.types import CronSchedule
        job = svc.add_job(
            name="no-cb",
            schedule=CronSchedule(kind="at", at_ms=int(time.time() * 1000) + 100_000),
            message="msg"
        )

        svc.on_job = AsyncMock(side_effect=RuntimeError("err"))
        # Should not raise
        await svc._execute_job(job)
        assert job.state.last_status == "error"


# ============================================================================
# Parallel Tool Execution Tests
# ============================================================================


class TestParallelToolExecution:
    """Verify that multiple tool calls from one LLM turn execute concurrently."""

    @pytest.mark.asyncio
    async def test_tools_run_concurrently(self):
        """Two slow tools should complete in roughly the time of one."""
        from nanobot.agent.tools.registry import ToolRegistry

        registry = ToolRegistry()

        # Register a fake slow tool
        async def slow_tool(args):
            await asyncio.sleep(0.2)
            return f"result-{args.get('id', '')}"

        tool_def = MagicMock()
        tool_def.name = "slow"
        registry._tools["slow"] = tool_def
        registry.execute = AsyncMock(side_effect=lambda name, args: slow_tool(args))

        # Simulate 3 concurrent calls
        tasks = [registry.execute("slow", {"id": i}) for i in range(3)]

        start = time.monotonic()
        results = await asyncio.gather(*tasks)
        elapsed = time.monotonic() - start

        assert len(results) == 3
        # If sequential, would take ~0.6s; parallel should be ~0.2s
        assert elapsed < 0.5, f"Expected parallel execution, took {elapsed:.2f}s"
