"""Tests for RPA ui_name text matching feature."""

import pytest
import json
from pathlib import Path
from unittest.mock import patch, MagicMock

# Ensure pyautogui mock is available at module level
import sys
sys.modules.setdefault("pyautogui", MagicMock())
sys.modules.setdefault("pydirectinput", MagicMock())

from nanobot.agent.tools.rpa_executor import RPAExecutorTool


# --- Fixture: sample anchors data ---
SAMPLE_ANCHORS = {
    "1": {"name": "One", "type": "ButtonControl", "bbox": [100, 700, 200, 750], "center": [150, 725]},
    "2": {"name": "Two", "type": "ButtonControl", "bbox": [200, 700, 300, 750], "center": [250, 725]},
    "3": {"name": "Plus", "type": "ButtonControl", "bbox": [400, 600, 500, 650], "center": [450, 625]},
    "4": {"name": "Equals", "type": "ButtonControl", "bbox": [400, 700, 500, 750], "center": [450, 725]},
    "5": {"name": "Five", "type": "ButtonControl", "bbox": [200, 600, 300, 650], "center": [250, 625]},
    "6": {"name": "", "type": "ButtonControl", "bbox": [0, 0, 10, 10], "center": [5, 5]},
    "7": {"name": "Submit Order", "type": "ButtonControl", "bbox": [500, 500, 600, 550], "center": [550, 525]},
}


@pytest.fixture
def tool():
    return RPAExecutorTool()


class TestFindByName:
    """Test the _find_by_name method of RPAExecutorTool."""

    def test_exact_match(self, tool):
        idx, el = tool._find_by_name(SAMPLE_ANCHORS, "One")
        assert idx == "1"
        assert el["name"] == "One"

    def test_exact_match_plus(self, tool):
        idx, el = tool._find_by_name(SAMPLE_ANCHORS, "Plus")
        assert idx == "3"
        assert el["name"] == "Plus"

    def test_case_insensitive_match(self, tool):
        idx, el = tool._find_by_name(SAMPLE_ANCHORS, "one")
        assert idx == "1"
        assert el["name"] == "One"

    def test_case_insensitive_upper(self, tool):
        idx, el = tool._find_by_name(SAMPLE_ANCHORS, "EQUALS")
        assert idx == "4"
        assert el["name"] == "Equals"

    def test_substring_match(self, tool):
        idx, el = tool._find_by_name(SAMPLE_ANCHORS, "Submit")
        assert idx == "7"
        assert el["name"] == "Submit Order"

    def test_no_match(self, tool):
        idx, el = tool._find_by_name(SAMPLE_ANCHORS, "Nonexistent")
        assert idx is None
        assert el is None

    def test_empty_name_not_matched(self, tool):
        """Elements with empty names should never be matched."""
        idx, el = tool._find_by_name(SAMPLE_ANCHORS, "")
        # Should not match the empty-name element (index 6)
        assert idx is None or el.get("name", "") != ""

    def test_priority_exact_over_substring(self, tool):
        """Exact match should take priority over substring."""
        anchors = {
            "1": {"name": "One Button", "type": "ButtonControl", "center": [100, 100]},
            "2": {"name": "One", "type": "ButtonControl", "center": [200, 200]},
        }
        idx, el = tool._find_by_name(anchors, "One")
        assert idx == "2"
        assert el["name"] == "One"


class TestRPAExecuteWithUiName:
    """Test the execute method with ui_name parameter."""

    @pytest.mark.asyncio
    async def test_ui_name_click_success(self, tool):
        """ui_name should resolve to coordinates and click."""
        with patch.object(tool, "_load_anchors") as mock_load, \
             patch("pyautogui.moveTo") as mock_move, \
             patch("pyautogui.click") as mock_click:
            mock_load.return_value = (SAMPLE_ANCHORS, Path("/fake/anchors.json"))
            
            result = await tool.execute(action="click", ui_name="One")
            
            assert "UI Name Match" in result
            assert "'One'" in result
            assert "Successfully performed click" in result
            mock_move.assert_called_once()
            mock_click.assert_called_once()

    @pytest.mark.asyncio
    async def test_ui_name_not_found(self, tool):
        """ui_name that doesn't match should return error with available elements."""
        with patch.object(tool, "_load_anchors") as mock_load:
            mock_load.return_value = (SAMPLE_ANCHORS, Path("/fake/anchors.json"))
            
            result = await tool.execute(action="click", ui_name="Nonexistent")
            
            assert "Error" in result
            assert "No UI element found" in result
            assert "Available elements" in result

    @pytest.mark.asyncio
    async def test_ui_name_no_anchors_file(self, tool):
        """ui_name without anchors.json should return helpful error."""
        with patch.object(tool, "_load_anchors") as mock_load:
            mock_load.return_value = (None, Path("/fake/anchors.json"))
            
            result = await tool.execute(action="click", ui_name="One")
            
            assert "Error" in result
            assert "no anchors.json found" in result

    @pytest.mark.asyncio
    async def test_ui_name_priority_over_ui_index(self, tool):
        """ui_name should take priority when both ui_name and ui_index are provided."""
        with patch.object(tool, "_load_anchors") as mock_load, \
             patch("pyautogui.moveTo"), \
             patch("pyautogui.click"):
            mock_load.return_value = (SAMPLE_ANCHORS, Path("/fake/anchors.json"))
            
            # Provide both ui_name="One" (index 1) and ui_index="5" (Five)
            result = await tool.execute(action="click", ui_name="One", ui_index="5")
            
            # Should use ui_name (One) not ui_index (Five)
            assert "'One'" in result
            assert "UI Name Match" in result
