"""Tests for Phase 18C: P2 Code Quality & Bug Fixes.

Covers:
- /reload command fix (was calling non-existent method)
- Memory intent detection (hoisted constants)
- Module exports (__all__)
"""

import pytest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch


# ── /reload command fix ──


class TestReloadCommandFix:
    """Verify /reload uses _register_dynamic_tools from tool_setup, not a method on AgentLoop."""

    @pytest.mark.asyncio
    async def test_reload_calls_module_function(self):
        """The /reload command must import and call _register_dynamic_tools(agent)."""
        from nanobot.agent.commands import CommandHandler
        from nanobot.bus.events import InboundMessage

        handler = CommandHandler(workspace=Path("/tmp"), task_tracker=MagicMock())
        msg = InboundMessage(channel="cli", sender_id="user", chat_id="test", content="/reload")
        session = MagicMock()

        # Create a mock agent — no _register_dynamic_tools method on it
        agent = MagicMock()
        agent._dynamic_tool_names = ["plugin_a"]

        with patch("nanobot.agent.tool_setup._reload_dynamic_tools", new_callable=AsyncMock) as mock_fn:
            result = await handler.dispatch_command("/reload", msg, session, MagicMock(), agent)

        assert result is not None
        mock_fn.assert_awaited_once_with(agent)
        assert "Plugins reloaded" in result.content

    @pytest.mark.asyncio
    async def test_reload_no_dynamic_tools(self):
        """When no dynamic tools found, message should say so."""
        from nanobot.agent.commands import CommandHandler
        from nanobot.bus.events import InboundMessage

        handler = CommandHandler(workspace=Path("/tmp"), task_tracker=MagicMock())
        msg = InboundMessage(channel="cli", sender_id="user", chat_id="test", content="/reload")
        agent = MagicMock()
        agent._dynamic_tool_names = []

        with patch("nanobot.agent.tool_setup._reload_dynamic_tools", new_callable=AsyncMock):
            result = await handler.dispatch_command("/reload", msg, MagicMock(), MagicMock(), agent)

        assert "No dynamic tools found" in result.content


# ── Memory intent detection ──


class TestMemoryIntentDetection:
    """Test detect_memory_intent with hoisted constants."""

    @pytest.fixture
    def handler(self):
        from nanobot.agent.commands import CommandHandler
        return CommandHandler(workspace=Path("/tmp"), task_tracker=MagicMock())

    @pytest.mark.parametrize("text", [
        "请记住我喜欢红色",
        "别忘了明天开会",
        "帮我记一下密码是123",
        "remember this for later",
        "don't forget I need report by Friday",
        "save this note please",
        "keep in mind I prefer dark mode",
    ])
    def test_detects_memory_intent(self, handler, text):
        result = handler.detect_memory_intent(text)
        assert "Memory Intent Detected" in result

    @pytest.mark.parametrize("text", [
        "你好",
        "what's the weather?",
        "帮我查一下邮件",
        "run the report",
    ])
    def test_no_false_positive(self, handler, text):
        result = handler.detect_memory_intent(text)
        assert result == ""


# ── Module constants ──


class TestModuleConstants:
    def test_memory_triggers_is_module_level(self):
        """_MEMORY_TRIGGERS should be accessible as a module attribute."""
        from nanobot.agent import commands
        assert hasattr(commands, "_MEMORY_TRIGGERS")
        assert isinstance(commands._MEMORY_TRIGGERS, list)
        assert len(commands._MEMORY_TRIGGERS) > 0

    def test_tool_setup_has_all(self):
        """tool_setup should have __all__ defined."""
        from nanobot.agent import tool_setup
        assert hasattr(tool_setup, "__all__")
        assert "setup_all_tools" in tool_setup.__all__

    def test_hybrid_retriever_has_all(self):
        """hybrid_retriever should have __all__ defined."""
        from nanobot.agent import hybrid_retriever
        assert hasattr(hybrid_retriever, "__all__")
        assert "hybrid_retrieve" in hybrid_retriever.__all__


# ── Personalization import fix ──


class TestPersonalizationImport:
    def test_re_imported_at_module_level(self):
        """S6: personalization now uses strip_think_tags utility instead of direct re import."""
        import nanobot.agent.personalization as p
        import inspect
        source = inspect.getsource(p)
        # S6: Should use strip_think_tags instead of raw re.sub
        assert "strip_think_tags" in source
