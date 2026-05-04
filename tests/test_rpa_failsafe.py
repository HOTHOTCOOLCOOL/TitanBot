"""Regression tests for PyAutoGUI FailSafe handling in RPA mouse actions."""

import sys
from unittest.mock import MagicMock, call, patch

import pytest

# Ensure pyautogui/pydirectinput mocks exist before importing the RPA tool
sys.modules.setdefault("pyautogui", MagicMock())
sys.modules.setdefault("pydirectinput", MagicMock())

from nanobot.agent.tools.rpa_executor import RPAExecutorTool


class FakeFailSafe(Exception):
    """Test-local substitute for pyautogui.FailSafeException."""


@pytest.fixture
def tool():
    return RPAExecutorTool()


class TestFailSafeRecovery:
    @pytest.mark.asyncio
    async def test_click_recovers_when_cursor_starts_in_corner(self, tool):
        """Benign center clicks should recover from a stale corner cursor."""
        fake_windll = MagicMock()

        with (
            patch.object(tool, "_load_anchors", return_value=(None, None)),
            patch.object(tool, "_load_monitor_context", return_value=None),
            patch("pyautogui.position", return_value=(0, 0)),
            patch("pyautogui.size", return_value=(1920, 1080)),
            patch("pyautogui.moveTo") as mock_move,
            patch("pyautogui.click") as mock_click,
            patch("pyautogui.FailSafeException", FakeFailSafe),
            patch("time.sleep"),
            patch("nanobot.agent.tools.rpa_executor.platform.system", return_value="Windows"),
            patch("nanobot.agent.tools.rpa_executor.ctypes.windll", fake_windll, create=True),
        ):
            result = await tool.execute(action="click", x=960, y=540, wait_after=0)

        assert "Successfully performed click" in result
        fake_windll.user32.SetCursorPos.assert_called_once_with(1, 1)
        mock_move.assert_called_once_with(960, 540, duration=0.5)
        mock_click.assert_called_once()

    @pytest.mark.asyncio
    async def test_corner_target_preserves_emergency_stop(self, tool):
        """Explicit corner clicks should still honor PyAutoGUI's abort semantics."""
        fake_windll = MagicMock()

        with (
            patch.object(tool, "_load_anchors", return_value=(None, None)),
            patch.object(tool, "_load_monitor_context", return_value=None),
            patch("pyautogui.position", return_value=(0, 0)),
            patch("pyautogui.size", return_value=(1920, 1080)),
            patch("pyautogui.moveTo", side_effect=FakeFailSafe),
            patch("pyautogui.click") as mock_click,
            patch("pyautogui.FailSafeException", FakeFailSafe),
            patch("time.sleep"),
            patch("nanobot.agent.tools.rpa_executor.platform.system", return_value="Windows"),
            patch("nanobot.agent.tools.rpa_executor.ctypes.windll", fake_windll, create=True),
        ):
            result = await tool.execute(action="click", x=0, y=0, wait_after=0)

        assert result.startswith("Error: PyAutoGUI FailSafe triggered")
        fake_windll.user32.SetCursorPos.assert_not_called()
        mock_click.assert_not_called()

    @pytest.mark.asyncio
    async def test_windows_corner_recovery_falls_back_to_pyautogui(self, tool):
        """If the Windows cursor API fails, use a one-shot PyAutoGUI nudge instead."""
        fake_windll = MagicMock()
        fake_windll.user32.SetCursorPos.side_effect = OSError("mocked SetCursorPos failure")

        with (
            patch.object(tool, "_load_anchors", return_value=(None, None)),
            patch.object(tool, "_load_monitor_context", return_value=None),
            patch("pyautogui.position", return_value=(0, 0)),
            patch("pyautogui.size", return_value=(1920, 1080)),
            patch("pyautogui.moveTo") as mock_move,
            patch("pyautogui.click") as mock_click,
            patch("pyautogui.FailSafeException", FakeFailSafe),
            patch("time.sleep"),
            patch("nanobot.agent.tools.rpa_executor.platform.system", return_value="Windows"),
            patch("nanobot.agent.tools.rpa_executor.ctypes.windll", fake_windll, create=True),
        ):
            result = await tool.execute(action="click", x=960, y=540, wait_after=0)

        assert "Successfully performed click" in result
        fake_windll.user32.SetCursorPos.assert_called_once_with(1, 1)
        assert mock_move.call_args_list == [
            call(1, 1, duration=0),
            call(960, 540, duration=0.5),
        ]
        mock_click.assert_called_once()
