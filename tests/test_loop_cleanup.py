"""Test: verify dead code has been cleaned from loop.py and constants extracted."""

import pytest


class TestLoopCleanup:
    """Verify P0 cleanup: dead code removed and inline constants extracted."""

    def test_no_execute_from_knowledge(self):
        """_execute_from_knowledge should have been removed as dead code."""
        from nanobot.agent.loop import AgentLoop
        assert not hasattr(AgentLoop, "_execute_from_knowledge"), (
            "_execute_from_knowledge is dead code and should be removed"
        )

    def test_no_extract_tool_args_from_history(self):
        """_extract_tool_args_from_history should have been removed as dead code."""
        from nanobot.agent.loop import AgentLoop
        assert not hasattr(AgentLoop, "_extract_tool_args_from_history"), (
            "_extract_tool_args_from_history is dead code and should be removed"
        )

    def test_module_constants_exist(self):
        """Module-level constants should exist after extraction."""
        from nanobot.agent import loop

        assert hasattr(loop, "_CONTINUE_TOOLS"), "_CONTINUE_TOOLS not found"
        assert hasattr(loop, "_WAIT_PHRASES"), "_WAIT_PHRASES not found"
        assert hasattr(loop, "_FAKE_COMPLETION_PHRASES"), "_FAKE_COMPLETION_PHRASES not found"
        assert hasattr(loop, "_FAIL_INDICATORS"), "_FAIL_INDICATORS not found"

    def test_continue_tools_is_set(self):
        """_CONTINUE_TOOLS should be a set containing known tool names (message excluded to prevent loops)."""
        from nanobot.agent.loop import _CONTINUE_TOOLS, _MAX_MESSAGE_CALLS
        assert isinstance(_CONTINUE_TOOLS, set)
        assert "outlook" in _CONTINUE_TOOLS
        assert "attachment_analyzer" in _CONTINUE_TOOLS
        # message was intentionally removed — it caused infinite loops
        assert "message" not in _CONTINUE_TOOLS
        assert _MAX_MESSAGE_CALLS == 3

    def test_wait_phrases_is_list(self):
        """_WAIT_PHRASES should be a non-empty list."""
        from nanobot.agent.loop import _WAIT_PHRASES
        assert isinstance(_WAIT_PHRASES, list)
        assert len(_WAIT_PHRASES) > 0
        assert "稍等" in _WAIT_PHRASES

    def test_fake_completion_phrases_is_list(self):
        """_FAKE_COMPLETION_PHRASES should be a non-empty list."""
        from nanobot.agent.loop import _FAKE_COMPLETION_PHRASES
        assert isinstance(_FAKE_COMPLETION_PHRASES, list)
        assert len(_FAKE_COMPLETION_PHRASES) > 0
        assert "已完成" in _FAKE_COMPLETION_PHRASES

    def test_fail_indicators_is_list(self):
        """_FAIL_INDICATORS should be a non-empty list."""
        from nanobot.agent.loop import _FAIL_INDICATORS
        assert isinstance(_FAIL_INDICATORS, list)
        assert len(_FAIL_INDICATORS) > 0
        assert "error:" in _FAIL_INDICATORS
        assert "not found" in _FAIL_INDICATORS
