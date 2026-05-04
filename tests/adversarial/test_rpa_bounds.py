"""ADR-66 Adversarial Tests: RPA Bounds Checking (Fix V2).

Tests that _check_bounds correctly decouples:
  - Stale context (>60s old): should ALLOW action with warning prefix
  - True out-of-bounds coordinates: should HARD BLOCK

These tests target the V2 bug where stale context and OOB were conflated,
causing all RPA operations to lock 60 seconds after the last screen capture.
"""
import json
import time
import os
import pytest
from unittest.mock import patch, MagicMock, mock_open

from nanobot.agent.tools.rpa_executor import RPAExecutorTool


@pytest.fixture
def rpa():
    return RPAExecutorTool()


def _make_context(offset_x=0, offset_y=0, right=1920, bottom=1080,
                   monitor_index=1, stale=False, scale_ratio=1.0) -> dict:
    ctx = {
        "offset_x": offset_x,
        "offset_y": offset_y,
        "right": right,
        "bottom": bottom,
        "monitor_index": monitor_index,
        "scale_ratio": scale_ratio,
    }
    if stale:
        ctx["stale"] = True
    return ctx


class TestCheckBoundsDecoupling:
    """Verify the tuple[bool, str|None] contract of _check_bounds (ADR-66 B1)."""

    def test_no_context_returns_false_none(self, rpa):
        """When no monitor context file exists, return (False, None) — allow action."""
        with patch.object(rpa, "_load_monitor_context", return_value=None):
            is_blocked, msg = rpa._check_bounds(500, 500)
        assert is_blocked is False
        assert msg is None

    def test_in_bounds_fresh_context_clean(self, rpa):
        """In-bounds coords with fresh context → (False, None)."""
        ctx = _make_context(right=1920, bottom=1080)
        with patch.object(rpa, "_load_monitor_context", return_value=ctx):
            is_blocked, msg = rpa._check_bounds(960, 540)
        assert is_blocked is False
        assert msg is None

    def test_stale_context_in_bounds_allows_with_warning(self, rpa):
        """Stale context but coords in bounds → (False, warning_str) — action ALLOWED."""
        ctx = _make_context(right=1920, bottom=1080, stale=True)
        with patch.object(rpa, "_load_monitor_context", return_value=ctx):
            is_blocked, msg = rpa._check_bounds(960, 540)
        assert is_blocked is False, (
            "REGRESSION: Stale context caused hard block! "
            "Legitimate RPA actions are now locked after 60s."
        )
        assert msg is not None, "Expected a stale warning message"
        assert ">60s" in msg or "stale" in msg.lower() or "old" in msg.lower()

    def test_out_of_bounds_hard_blocks(self, rpa):
        """Coordinates outside monitor boundary → (True, error_str) — hard block."""
        ctx = _make_context(right=1920, bottom=1080)
        with patch.object(rpa, "_load_monitor_context", return_value=ctx):
            is_blocked, msg = rpa._check_bounds(2500, 540)  # x=2500 > right=1920
        assert is_blocked is True, (
            "REGRESSION: Out-of-bounds coordinates were NOT hard-blocked! "
            "Physical RPA could fly to second monitor."
        )
        assert msg is not None

    def test_stale_AND_out_of_bounds_hard_blocks(self, rpa):
        """Even with stale context, true OOB must still hard-block."""
        ctx = _make_context(right=1920, bottom=1080, stale=True)
        with patch.object(rpa, "_load_monitor_context", return_value=ctx):
            is_blocked, msg = rpa._check_bounds(9999, 9999)
        assert is_blocked is True, "OOB must block even with stale context."

    def test_y_out_of_bounds_hard_blocks(self, rpa):
        """Y coordinate below bottom boundary → hard block."""
        ctx = _make_context(right=1920, bottom=1080)
        with patch.object(rpa, "_load_monitor_context", return_value=ctx):
            is_blocked, msg = rpa._check_bounds(960, 1200)  # y=1200 > bottom=1080
        assert is_blocked is True

    def test_negative_coords_out_of_bounds(self, rpa):
        """Negative coordinates are outside the monitor → hard block."""
        ctx = _make_context(offset_x=0, offset_y=0, right=1920, bottom=1080)
        with patch.object(rpa, "_load_monitor_context", return_value=ctx):
            is_blocked, msg = rpa._check_bounds(-100, 540)
        assert is_blocked is True


class TestExecuteImplBlockingBehavior:
    """Integration-level tests: verify _execute_impl returns Error on OOB."""

    @pytest.mark.asyncio
    async def test_execute_returns_error_on_oob(self, rpa):
        """_execute_impl must return an Error string (not execute pyautogui) on OOB."""
        ctx = _make_context(right=1920, bottom=1080)
        with (
            patch.object(rpa, "_load_monitor_context", return_value=ctx),
            patch.object(rpa, "_load_anchors", return_value=(None, None)),
            patch("pyautogui.moveTo") as mock_move,
            patch("pyautogui.click") as mock_click,
        ):
            result = await rpa._execute_impl(action="click", x=3000, y=500)

        assert result.startswith("Error:"), (
            f"Expected 'Error:' prefix for OOB click, got: {result[:100]}"
        )
        mock_move.assert_not_called(), "pyautogui.moveTo must NOT be called on OOB"
        mock_click.assert_not_called(), "pyautogui.click must NOT be called on OOB"

    @pytest.mark.asyncio
    async def test_stale_context_still_executes(self, rpa):
        """Stale context must not prevent action execution."""
        ctx = _make_context(right=1920, bottom=1080, stale=True)
        with (
            patch.object(rpa, "_load_monitor_context", return_value=ctx),
            patch.object(rpa, "_load_anchors", return_value=(None, None)),
            patch("pyautogui.moveTo"),
            patch("pyautogui.click"),
            patch("time.sleep"),
        ):
            result = await rpa._execute_impl(action="click", x=960, y=540)

        assert not result.startswith("Error:"), (
            f"REGRESSION: Stale context caused hard block: {result[:100]}"
        )
        assert "60s" in result or "stale" in result.lower() or "old" in result.lower() or "Successfully" in result
