"""Tests for Phase 18D: P3 Architecture Improvements.

Covers:
- P3-1: DRY Channel Manager registration registry
- P3-2: Data-driven tool context dispatch
- P3-3: `__all__` exports for public modules
- P3-4: Startup uptime metric
"""

import importlib
import time
from unittest.mock import MagicMock, patch

import pytest

# ────────────────────────────────────────────────
# P3-1: Channel Manager DRY Registry
# ────────────────────────────────────────────────

class TestChannelManagerRegistry:
    """Tests for the data-driven _CHANNEL_REGISTRY in channels/manager.py."""

    def test_registry_contains_all_channels(self):
        """Registry should list all 9 supported channels."""
        from nanobot.channels.manager import _CHANNEL_REGISTRY
        names = [entry[0] for entry in _CHANNEL_REGISTRY]
        expected = [
            "telegram", "whatsapp", "discord", "feishu",
            "mochat", "dingtalk", "email", "slack", "qq",
        ]
        assert names == expected

    def test_registry_entry_structure(self):
        """Each registry entry should be a 4-tuple (name, module, class, factory_or_None)."""
        from nanobot.channels.manager import _CHANNEL_REGISTRY
        for entry in _CHANNEL_REGISTRY:
            assert len(entry) == 4
            name, mod_path, cls_name, factory = entry
            assert isinstance(name, str)
            assert isinstance(mod_path, str) and mod_path.startswith("nanobot.channels.")
            assert isinstance(cls_name, str)
            assert factory is None or callable(factory)

    def test_telegram_has_factory(self):
        """Telegram should use a custom factory (needs groq_api_key)."""
        from nanobot.channels.manager import _CHANNEL_REGISTRY
        telegram_entry = _CHANNEL_REGISTRY[0]
        assert telegram_entry[0] == "telegram"
        assert telegram_entry[3] is not None  # factory function

    def test_non_telegram_channels_have_no_factory(self):
        """All channels except Telegram should use the default factory (None)."""
        from nanobot.channels.manager import _CHANNEL_REGISTRY
        for entry in _CHANNEL_REGISTRY[1:]:
            assert entry[3] is None, f"{entry[0]} should have factory=None"

    def test_init_channels_skips_disabled(self):
        """Disabled channels should be skipped by _init_channels."""
        from nanobot.channels.manager import ChannelManager

        mock_config = MagicMock()
        # Make all channels disabled
        for name in ["telegram", "whatsapp", "discord", "feishu",
                      "mochat", "dingtalk", "email", "slack", "qq"]:
            channel_cfg = MagicMock()
            channel_cfg.enabled = False
            setattr(mock_config.channels, name, channel_cfg)

        mock_bus = MagicMock()
        mgr = ChannelManager(mock_config, mock_bus)
        assert len(mgr.channels) == 0

    def test_init_channels_handles_import_error(self):
        """ImportError during channel init should be caught and logged."""
        from nanobot.channels.manager import ChannelManager

        mock_config = MagicMock()
        # Only enable whatsapp (will fail to import in test environment)
        for name in ["telegram", "discord", "feishu",
                      "mochat", "dingtalk", "email", "slack", "qq"]:
            channel_cfg = MagicMock()
            channel_cfg.enabled = False
            setattr(mock_config.channels, name, channel_cfg)

        wa_cfg = MagicMock()
        wa_cfg.enabled = True
        mock_config.channels.whatsapp = wa_cfg

        mock_bus = MagicMock()

        with patch("importlib.import_module", side_effect=ImportError("test")):
            mgr = ChannelManager(mock_config, mock_bus)
        # Should not crash, just log warning
        assert "whatsapp" not in mgr.channels

    def test_init_channels_missing_channel_config(self):
        """If a channel config attribute is missing, skip gracefully."""
        from nanobot.channels.manager import ChannelManager

        mock_config = MagicMock(spec=[])  # spec=[] means no attributes
        # Create a channels mock that only has 'telegram'
        channels_mock = MagicMock()
        channels_mock.telegram.enabled = False
        # Delete all other channel configs so getattr returns None
        for name in ["whatsapp", "discord", "feishu",
                      "mochat", "dingtalk", "email", "slack", "qq"]:
            delattr(channels_mock, name) if hasattr(channels_mock, name) else None
        mock_config.channels = channels_mock
        
        mock_bus = MagicMock()
        # Should not crash
        mgr = ChannelManager(mock_config, mock_bus)


# ────────────────────────────────────────────────
# P3-2: Data-Driven Tool Context Dispatch
# ────────────────────────────────────────────────

class TestToolContextDispatch:
    """Tests for the duck-typed _set_tool_context in loop.py."""

    def test_contextual_tools_tuple_exists(self):
        """AgentLoop should have a _CONTEXTUAL_TOOLS class attribute."""
        from nanobot.agent.loop import AgentLoop
        assert hasattr(AgentLoop, "_CONTEXTUAL_TOOLS")
        assert isinstance(AgentLoop._CONTEXTUAL_TOOLS, tuple)
        assert set(AgentLoop._CONTEXTUAL_TOOLS) == {"message", "spawn", "cron"}

    def test_set_tool_context_calls_set_context(self):
        """_set_tool_context should call set_context on tools that support it."""
        from nanobot.agent.loop import AgentLoop

        mock_agent = MagicMock(spec=AgentLoop)
        mock_agent._CONTEXTUAL_TOOLS = AgentLoop._CONTEXTUAL_TOOLS

        # Create mock tools that have set_context
        mock_message_tool = MagicMock()
        mock_spawn_tool = MagicMock()
        mock_cron_tool = MagicMock()

        def tools_get(name):
            return {"message": mock_message_tool, "spawn": mock_spawn_tool, "cron": mock_cron_tool}.get(name)

        mock_agent.tools = MagicMock()
        mock_agent.tools.get = tools_get

        # Call the real method
        AgentLoop._set_tool_context(mock_agent, "telegram", "123")

        mock_message_tool.set_context.assert_called_once_with("telegram", "123")
        mock_spawn_tool.set_context.assert_called_once_with("telegram", "123")
        mock_cron_tool.set_context.assert_called_once_with("telegram", "123")

    def test_set_tool_context_skips_missing_tools(self):
        """_set_tool_context should not crash if a tool doesn't exist."""
        from nanobot.agent.loop import AgentLoop

        mock_agent = MagicMock(spec=AgentLoop)
        mock_agent._CONTEXTUAL_TOOLS = AgentLoop._CONTEXTUAL_TOOLS
        mock_agent.tools = MagicMock()
        mock_agent.tools.get = MagicMock(return_value=None)

        # Should not raise
        AgentLoop._set_tool_context(mock_agent, "cli", "direct")

    def test_set_tool_context_skips_tools_without_set_context(self):
        """Tools without a set_context method should be silently skipped."""
        from nanobot.agent.loop import AgentLoop

        mock_agent = MagicMock(spec=AgentLoop)
        mock_agent._CONTEXTUAL_TOOLS = AgentLoop._CONTEXTUAL_TOOLS

        # A tool that exists but doesn't have set_context
        tool_without_method = object()
        mock_agent.tools = MagicMock()
        mock_agent.tools.get = MagicMock(return_value=tool_without_method)

        # Should not raise
        AgentLoop._set_tool_context(mock_agent, "cli", "direct")


# ────────────────────────────────────────────────
# P3-3: __all__ Exports
# ────────────────────────────────────────────────

class TestAllExports:
    """Tests that all public modules declare __all__ exports."""

    @pytest.mark.parametrize("module_path,expected_names", [
        ("nanobot.agent.context", ["ContextBuilder"]),
        ("nanobot.agent.commands", ["CommandHandler"]),
        ("nanobot.agent.state_handler", ["StateHandler"]),
        ("nanobot.agent.tool_setup", ["setup_all_tools"]),
        ("nanobot.agent.hybrid_retriever", ["hybrid_retrieve"]),
        ("nanobot.utils.metrics", ["metrics", "get_metrics", "MetricsCollector"]),
        ("nanobot.session.manager", ["Session", "SessionManager"]),
        ("nanobot.channels.manager", ["ChannelManager"]),
    ])
    def test_module_has_all(self, module_path, expected_names):
        """Module should declare __all__ with expected names."""
        mod = importlib.import_module(module_path)
        assert hasattr(mod, "__all__"), f"{module_path} is missing __all__"
        for name in expected_names:
            assert name in mod.__all__, f"{name} not in {module_path}.__all__"

    @pytest.mark.parametrize("module_path", [
        "nanobot.agent.context",
        "nanobot.agent.commands",
        "nanobot.agent.state_handler",
        "nanobot.agent.tool_setup",
        "nanobot.agent.hybrid_retriever",
        "nanobot.utils.metrics",
        "nanobot.session.manager",
        "nanobot.channels.manager",
    ])
    def test_all_names_are_importable(self, module_path):
        """Every name declared in __all__ should be importable from the module."""
        mod = importlib.import_module(module_path)
        for name in mod.__all__:
            assert hasattr(mod, name), f"{module_path}.{name} is declared in __all__ but not defined"


# ────────────────────────────────────────────────
# P3-4: Uptime Metric
# ────────────────────────────────────────────────

class TestUptimeMetric:
    """Tests for the uptime_seconds() method and its integration."""

    def test_uptime_returns_positive_float(self):
        """uptime_seconds() should return a positive float."""
        from nanobot.utils.metrics import MetricsCollector
        mc = MetricsCollector()
        uptime = mc.uptime_seconds()
        assert isinstance(uptime, float)
        assert uptime >= 0.0

    def test_uptime_increases_over_time(self):
        """uptime_seconds() should increase as time passes."""
        from nanobot.utils.metrics import MetricsCollector
        mc = MetricsCollector()
        t1 = mc.uptime_seconds()
        time.sleep(0.05)
        t2 = mc.uptime_seconds()
        assert t2 > t1

    def test_report_includes_uptime(self):
        """report() output should contain the Uptime line."""
        from nanobot.utils.metrics import MetricsCollector
        mc = MetricsCollector()
        report = mc.report()
        assert "Uptime:" in report

    def test_get_metrics_includes_uptime(self):
        """get_metrics() dict should contain uptime_seconds key."""
        from nanobot.utils.metrics import get_metrics
        data = get_metrics()
        assert "uptime_seconds" in data
        assert isinstance(data["uptime_seconds"], float)
        assert data["uptime_seconds"] >= 0.0

    def test_reset_does_not_reset_uptime(self):
        """reset() should clear counters/timings but NOT uptime."""
        from nanobot.utils.metrics import MetricsCollector
        mc = MetricsCollector()
        time.sleep(0.05)
        mc.reset()
        assert mc.uptime_seconds() > 0.0


# ────────────────────────────────────────────────
# Bonus: Channel Manager __all__ import check
# ────────────────────────────────────────────────

class TestChannelManagerExport:
    """Verify ChannelManager is importable via __all__."""

    def test_channel_manager_importable(self):
        from nanobot.channels.manager import ChannelManager
        assert ChannelManager is not None
