"""Phase 37: Tests for Execution Trace Archive.

Covers:
  1. TraceArchive — debug trace dump and auto-cleanup.
  2. AgentLoop._extract_trace_postmortem — LLM-driven post-mortem extraction
     into Experience Bank (mocked provider).
"""

import asyncio
import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ── TraceArchive tests ──────────────────────────────────────────────────


class TestTraceArchive:
    """Tests for the developer-only debug trace dumper."""

    def _make_archive(self, tmp_path: Path):
        from nanobot.agent.trace_archive import TraceArchive
        return TraceArchive(tmp_path)

    def test_dump_creates_file(self, tmp_path):
        archive = self._make_archive(tmp_path)
        result = archive.dump_debug_trace(
            request_text="login to system X",
            tool_calls_with_args=[{"tool": "browser", "args": {"action": "navigate"}}],
            action_log=[{"tool": "browser", "action": "navigate", "outcome": "ok"}],
            final_content="Error: timeout",
        )
        assert result is not None
        assert result.exists()
        assert result.suffix == ".json"

        data = json.loads(result.read_text(encoding="utf-8"))
        assert "login to system X" in data["request"]
        assert len(data["tool_chain"]) == 1
        assert data["tool_chain"][0]["tool"] == "browser"

    def test_dump_truncates_long_content(self, tmp_path):
        archive = self._make_archive(tmp_path)
        result = archive.dump_debug_trace(
            request_text="x" * 1000,  # 1000 chars, will be truncated to 500
            tool_calls_with_args=[{"tool": "exec", "args": {"command": "y" * 1000}}],
            action_log=[],
            final_content="z" * 1000,
        )
        assert result is not None
        data = json.loads(result.read_text(encoding="utf-8"))
        assert len(data["request"]) == 500
        assert len(data["final_content"]) == 500

    def test_cleanup_evicts_oldest(self, tmp_path):
        archive = self._make_archive(tmp_path)
        archive.MAX_TRACES = 3

        # Create 5 traces
        created = []
        for i in range(5):
            result = archive.dump_debug_trace(
                request_text=f"task {i}",
                tool_calls_with_args=[{"tool": "browser", "args": {}}],
                action_log=[],
                final_content=f"error {i}",
            )
            if result:
                created.append(result)

        # Should have at most MAX_TRACES files
        traces = list(archive.traces_dir.glob("trace_*.json"))
        assert len(traces) <= 3

    def test_dump_returns_none_on_error(self, tmp_path):
        archive = self._make_archive(tmp_path)
        # Simulate I/O failure via mock
        with patch.object(Path, "write_text", side_effect=OSError("disk full")):
            result = archive.dump_debug_trace(
                request_text="test",
                tool_calls_with_args=[],
                action_log=[],
                final_content="error",
            )
        # Should return None, not raise
        assert result is None

    def test_empty_tool_chain(self, tmp_path):
        archive = self._make_archive(tmp_path)
        result = archive.dump_debug_trace(
            request_text="simple query",
            tool_calls_with_args=[],
            action_log=[],
            final_content="no tools used",
        )
        assert result is not None
        data = json.loads(result.read_text(encoding="utf-8"))
        assert data["tool_chain"] == []


# ── Post-mortem extraction tests ────────────────────────────────────────


class TestPostMortemExtraction:
    """Tests for _extract_trace_postmortem integration in AgentLoop."""

    @pytest.fixture
    def mock_loop(self, tmp_path):
        """Create a minimal AgentLoop-like object with mocked dependencies."""
        from nanobot.agent.loop import AgentLoop

        loop = MagicMock()
        loop.workspace = tmp_path
        loop.model = "test-model"
        loop._get_config = MagicMock()
        # Must set class-level attribute explicitly for set intersection logic
        loop._HIGH_COMPLEXITY_TOOLS = AgentLoop._HIGH_COMPLEXITY_TOOLS

        # Config with trace_archive_enabled
        mock_config = MagicMock()
        mock_config.agents.verification.trace_archive_enabled = True
        mock_config.agents.memory_features.experience_enabled = True
        loop._get_config.return_value = mock_config

        # Knowledge workflow with store
        loop.knowledge_workflow = MagicMock()
        loop.knowledge_workflow.knowledge_store = MagicMock()
        loop.knowledge_workflow.knowledge_store.add_experience = MagicMock()

        # Provider
        loop.provider = AsyncMock()

        return loop

    @pytest.mark.asyncio
    async def test_postmortem_stores_experience_for_complex_tools(self, mock_loop, tmp_path):
        """Post-mortem should extract and store experience for browser/RPA failures."""
        from nanobot.agent.loop import AgentLoop

        # Mock LLM response with valid JSON
        mock_response = MagicMock()
        mock_response.content = json.dumps({
            "root_cause": "Login button selector changed",
            "failed_approach": "Used CSS #btn-submit which no longer exists",
            "recommended_fix": "Use text-based selector button:has-text('Login') instead",
        })
        mock_loop.provider.chat = AsyncMock(return_value=mock_response)

        # Call the method directly (unbound, passing mock_loop as self)
        await AgentLoop._extract_trace_postmortem(
            mock_loop,
            request_text="Login to system X",
            tool_calls_with_args=[
                {"tool": "browser", "args": {"action": "navigate", "url": "https://x.com"}},
                {"tool": "browser", "args": {"action": "click", "selector": "#btn-submit"}},
            ],
            action_log=[
                {"tool": "browser", "action": "navigate", "outcome": "ok"},
                {"tool": "browser", "action": "click", "outcome": "error"},
            ],
            last_error="Error: element not found",
            break_reason="circuit_breaker",
        )

        # Verify experience was stored
        mock_loop.knowledge_workflow.knowledge_store.add_experience.assert_called_once()
        call_kwargs = mock_loop.knowledge_workflow.knowledge_store.add_experience.call_args
        assert call_kwargs[1]["action_type"] == "trace_postmortem"
        assert "TRACE POST-MORTEM" in call_kwargs[1]["tactical_prompt"]
        assert "Login button selector" in call_kwargs[1]["tactical_prompt"]

    @pytest.mark.asyncio
    async def test_postmortem_fallback_for_simple_tools(self, mock_loop):
        """Non-complex tool failures should get a simple 1-line experience (fallback)."""
        from nanobot.agent.loop import AgentLoop

        await AgentLoop._extract_trace_postmortem(
            mock_loop,
            request_text="Send email to Bob",
            tool_calls_with_args=[
                {"tool": "outlook", "args": {"action": "send_email"}},
            ],
            action_log=[],
            last_error="Error: SMTP connection failed",
            break_reason="circuit_breaker",
        )

        # Should store simple error_recovery, NOT call LLM
        mock_loop.provider.chat.assert_not_called()
        call_kwargs = mock_loop.knowledge_workflow.knowledge_store.add_experience.call_args
        assert call_kwargs[1]["action_type"] == "error_recovery"

    @pytest.mark.asyncio
    async def test_postmortem_disabled_via_config(self, mock_loop):
        """Post-mortem should be skipped when trace_archive_enabled is False."""
        from nanobot.agent.loop import AgentLoop

        mock_loop._get_config.return_value.agents.verification.trace_archive_enabled = False

        await AgentLoop._extract_trace_postmortem(
            mock_loop,
            request_text="Login to X",
            tool_calls_with_args=[{"tool": "browser", "args": {}}],
            action_log=[],
            last_error="Error: timeout",
        )

        # Nothing should be stored
        mock_loop.knowledge_workflow.knowledge_store.add_experience.assert_not_called()
        mock_loop.provider.chat.assert_not_called()

    @pytest.mark.asyncio
    async def test_postmortem_survives_llm_error(self, mock_loop):
        """LLM call failure should not raise — fire-and-forget safety."""
        from nanobot.agent.loop import AgentLoop

        mock_loop.provider.chat = AsyncMock(side_effect=Exception("LLM timeout"))

        # Should not raise
        await AgentLoop._extract_trace_postmortem(
            mock_loop,
            request_text="Navigate to dashboard",
            tool_calls_with_args=[
                {"tool": "browser", "args": {"action": "navigate"}},
            ],
            action_log=[],
            last_error="Error: timeout",
            break_reason="circuit_breaker",
        )

        # No experience stored due to LLM failure, but no exception raised
        mock_loop.knowledge_workflow.knowledge_store.add_experience.assert_not_called()

    @pytest.mark.asyncio
    async def test_postmortem_caps_tactical_prompt_at_800(self, mock_loop):
        """The tactical prompt stored in Experience Bank must not exceed 800 chars."""
        from nanobot.agent.loop import AgentLoop

        # Mock LLM response with very long content
        mock_response = MagicMock()
        mock_response.content = json.dumps({
            "root_cause": "x" * 300,
            "failed_approach": "y" * 300,
            "recommended_fix": "z" * 300,
        })
        mock_loop.provider.chat = AsyncMock(return_value=mock_response)

        await AgentLoop._extract_trace_postmortem(
            mock_loop,
            request_text="Complex browser task",
            tool_calls_with_args=[
                {"tool": "browser_use_worker", "args": {"task": "login"}},
            ],
            action_log=[],
            last_error="Error: timeout",
        )

        call_kwargs = mock_loop.knowledge_workflow.knowledge_store.add_experience.call_args
        tactical = call_kwargs[1]["tactical_prompt"]
        assert len(tactical) <= 800

    @pytest.mark.asyncio
    async def test_postmortem_debug_trace_also_created(self, mock_loop, tmp_path):
        """Debug trace file should be created alongside experience storage."""
        from nanobot.agent.loop import AgentLoop

        mock_response = MagicMock()
        mock_response.content = json.dumps({
            "root_cause": "Timeout on page load",
            "failed_approach": "Direct navigation",
            "recommended_fix": "Add wait_for_load step",
        })
        mock_loop.provider.chat = AsyncMock(return_value=mock_response)

        await AgentLoop._extract_trace_postmortem(
            mock_loop,
            request_text="Navigate to report page",
            tool_calls_with_args=[
                {"tool": "exec", "args": {"command": "python script.py"}},
            ],
            action_log=[],
            last_error="Error: script failed",
        )

        # Check that debug trace was created
        traces_dir = tmp_path / "memory" / "traces"
        if traces_dir.exists():
            traces = list(traces_dir.glob("trace_*.json"))
            assert len(traces) == 1


# ── Config flag test ────────────────────────────────────────────────────


class TestTraceArchiveConfig:
    """Test that the config flag exists and defaults correctly."""

    def test_verification_config_has_trace_archive_enabled(self):
        from nanobot.config.schema import VerificationConfig
        config = VerificationConfig()
        assert config.trace_archive_enabled is True

    def test_verification_config_can_disable_trace_archive(self):
        from nanobot.config.schema import VerificationConfig
        config = VerificationConfig(trace_archive_enabled=False)
        assert config.trace_archive_enabled is False
