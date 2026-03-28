"""Tests for Phase 30 remaining fixes: SEC-1, SEC-3, BUG-1, BUG-2, BUG-5, DESIGN-4, DESIGN-5."""

import asyncio
import hmac
import json
import os
import pytest
from unittest.mock import patch, AsyncMock, MagicMock, PropertyMock

from nanobot.config.schema import Config


# ---------------------------------------------------------------------------
# SEC-1: hmac.compare_digest for token comparison
# ---------------------------------------------------------------------------

class TestDashboardTokenSecurity:
    """SEC-1: Dashboard token comparison uses constant-time hmac."""

    def test_verify_token_uses_hmac(self):
        """verify_token should use hmac.compare_digest, not ==."""
        import inspect
        from nanobot.dashboard.app import verify_token
        source = inspect.getsource(verify_token)
        assert "hmac.compare_digest" in source, "verify_token must use hmac.compare_digest"
        assert "!=" not in source.split("Bearer")[1], "verify_token must not use != for token"

    def test_ws_auth_uses_hmac(self):
        """WebSocket endpoints should use hmac.compare_digest for token check."""
        import inspect
        from nanobot.dashboard import app as dashboard_module
        source = inspect.getsource(dashboard_module)
        # Count hmac.compare_digest calls — should be 3 (verify_token + 2 WS endpoints)
        assert source.count("hmac.compare_digest") >= 3, (
            "Expected at least 3 hmac.compare_digest calls (1 HTTP + 2 WS)"
        )


# ---------------------------------------------------------------------------
# SEC-3: PythonSandbox must NOT include PYTHONPATH
# ---------------------------------------------------------------------------

class TestPythonSandboxSecurity:
    """SEC-3: PythonSandbox should not pass PYTHONPATH to subprocess."""

    def test_no_pythonpath_in_essential_vars(self):
        """PYTHONPATH must not be in the PythonSandbox essential_vars."""
        import inspect
        from nanobot.agent.sandbox import PythonSandbox
        source = inspect.getsource(PythonSandbox.run_hook)
        # The essential_vars set should NOT contain PYTHONPATH
        assert '"PYTHONPATH"' not in source, "PYTHONPATH must be removed from PythonSandbox"
        assert "'PYTHONPATH'" not in source, "PYTHONPATH must be removed from PythonSandbox"


# ---------------------------------------------------------------------------
# BUG-2: In-place list trim for _recent_call_sigs
# ---------------------------------------------------------------------------

class TestDuplicateDetectionListTrim:
    """BUG-2: _recent_call_sigs should be trimmed in-place, not reassigned."""

    def test_inplace_trim_source_check(self):
        """The loop source should use del for list trimming, not reassignment."""
        import inspect
        from nanobot.agent.loop import AgentLoop
        source = inspect.getsource(AgentLoop._run_agent_loop)
        assert "del _recent_call_sigs[:" in source, (
            "Expected in-place del for _recent_call_sigs trim"
        )
        # Should NOT contain the old reassignment pattern
        assert "_recent_call_sigs = _recent_call_sigs[" not in source, (
            "Old reassignment pattern should be replaced with in-place del"
        )


# ---------------------------------------------------------------------------
# BUG-1: _action_login should not double-save session
# ---------------------------------------------------------------------------

class TestLoginNoDoubleSave:
    """BUG-1: _action_login must not save session cookies twice."""

    @pytest.mark.asyncio
    async def test_login_passes_save_session_false_to_navigate(self):
        """_action_login should pass save_session=False to _action_navigate."""
        from nanobot.plugins.browser import BrowserTool

        tool = BrowserTool()
        tool._session_store = MagicMock()
        tool._context = AsyncMock()
        tool._pages = [AsyncMock()]
        tool._trust_manager = MagicMock()

        # Track what kwargs _action_navigate receives
        captured_kwargs = {}

        async def mock_navigate(kwargs):
            captured_kwargs.update(kwargs)
            return json.dumps({"action": "navigate", "url": "https://example.com", "status": 200, "title": "Test"})

        tool._action_navigate = mock_navigate
        tool._session_store.save_session = MagicMock(return_value=True)
        tool._context.cookies = AsyncMock(return_value=[{"name": "sid", "value": "abc123"}])

        # Mock page.evaluate for localStorage
        tool._pages[-1].evaluate = AsyncMock(return_value={})

        await tool._action_login({
            "url": "https://example.com",
            "save_session": True,
        })

        # _action_navigate should have received save_session=False
        assert captured_kwargs.get("save_session") is False, (
            "_action_login must pass save_session=False to _action_navigate to avoid double save"
        )

        # _action_login's own save logic should have called save_session once
        tool._session_store.save_session.assert_called_once()


# ---------------------------------------------------------------------------
# BUG-5: WebSocket tracking uses set
# ---------------------------------------------------------------------------

class TestWebSocketSetType:
    """BUG-5: _active_websockets and _stream_websockets should be sets."""

    def test_active_websockets_is_set(self):
        from nanobot.dashboard.app import _active_websockets
        assert isinstance(_active_websockets, set), f"Expected set, got {type(_active_websockets)}"

    def test_stream_websockets_is_set(self):
        from nanobot.dashboard.app import _stream_websockets
        assert isinstance(_stream_websockets, set), f"Expected set, got {type(_stream_websockets)}"


# ---------------------------------------------------------------------------
# DESIGN-4: Refined _FAIL_INDICATORS
# ---------------------------------------------------------------------------

class TestFailIndicatorsRefinement:
    """DESIGN-4: _FAIL_INDICATORS should not have false positives."""

    def _check_indicators(self, text: str) -> bool:
        from nanobot.agent.loop import _FAIL_INDICATORS
        text_lower = text.lower()
        return any(ind in text_lower for ind in _FAIL_INDICATORS)

    def test_no_false_positive_on_analysis(self):
        """Analytical text mentioning '失败' should NOT trigger a false positive."""
        # This text is an analysis report, not a tool failure.
        text = "分析结果：该任务失败的原因是网络延迟过高"
        assert not self._check_indicators(text), (
            "Standalone '失败' should no longer trigger. Use '执行失败'/'操作失败' instead."
        )

    def test_no_false_positive_on_sorry(self):
        """Text containing 'sorry' in a non-apologetic context should not trigger."""
        text = "He felt sorry for the loss."
        assert not self._check_indicators(text), (
            "Standalone 'sorry' should no longer trigger. Use 'sorry, i' instead."
        )

    def test_no_false_positive_on_apology_substring(self):
        """Text containing '抱歉' in greeting context should not trigger."""
        text = "不好意思打扰你了，抱歉打扰"
        assert not self._check_indicators(text), (
            "Standalone '抱歉' should no longer trigger. Use '很抱歉' instead."
        )

    def test_real_failure_execution_failed(self):
        """'执行失败' should always be detected."""
        assert self._check_indicators("命令执行失败，请重试")

    def test_real_failure_operation_failed(self):
        """'操作失败' should always be detected."""
        assert self._check_indicators("文件操作失败")

    def test_real_failure_error_prefix(self):
        """'error:' should always be detected."""
        assert self._check_indicators("Error: file not found")

    def test_real_failure_not_found(self):
        """'not found' should be detected."""
        assert self._check_indicators("Error: File not found in directory")

    def test_real_failure_sorry_apology(self):
        """'no emails found' should be detected."""
        assert self._check_indicators("There were no emails found matching the criteria.")

    def test_real_failure_very_sorry(self):
        """'无法执行此操作' should be detected."""
        assert self._check_indicators("很抱歉，我无法执行此操作因为权限不足")

    def test_real_failure_unable_complete(self):
        """'无法完成' should be detected."""
        assert self._check_indicators("系统无法完成此任务")

    def test_real_failure_unable_execute(self):
        """'执行失败' should be detected."""
        assert self._check_indicators("该命令执行失败，请重试")


# ---------------------------------------------------------------------------
# DESIGN-5: VLM provider cache
# ---------------------------------------------------------------------------

class TestVLMProviderCache:
    """DESIGN-5: AgentLoop should cache VLM provider instances."""

    def test_vlm_cache_attribute_exists(self):
        """AgentLoop should have _vlm_provider_cache dict."""
        from nanobot.agent.loop import AgentLoop
        import inspect
        source = inspect.getsource(AgentLoop.__init__)
        assert "_vlm_provider_cache" in source, "AgentLoop.__init__ should initialize _vlm_provider_cache"

    def test_vlm_cache_source_pattern(self):
        """_run_agent_loop should check cache before creating new provider."""
        from nanobot.agent.loop import AgentLoop
        import inspect
        source = inspect.getsource(AgentLoop._run_agent_loop)
        assert "self._vlm_provider_cache" in source, (
            "_run_agent_loop should use self._vlm_provider_cache"
        )
        assert "not in self._vlm_provider_cache" in source, (
            "_run_agent_loop should check cache before creating"
        )
