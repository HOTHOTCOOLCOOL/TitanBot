"""Integration tests for OCR + UIAutomation anchor merging and RPA name matching."""

import sys
from unittest.mock import patch, MagicMock

# Mock heavy dependencies before any nanobot imports
sys.modules.setdefault("chromadb", MagicMock())
sys.modules.setdefault("chromadb.api.types", MagicMock())
sys.modules.setdefault("pyautogui", MagicMock())
sys.modules.setdefault("pydirectinput", MagicMock())

import pytest
import json
from pathlib import Path

from nanobot.agent.tools.rpa_executor import RPAExecutorTool


# ── Fixtures ──────────────────────────────────────────────────────────────

SAMPLE_UIA_ANCHORS = {
    "1": {"name": "One", "type": "ButtonControl", "bbox": [100, 700, 200, 750], "center": [150, 725], "source": "uia"},
    "2": {"name": "Plus", "type": "ButtonControl", "bbox": [400, 600, 500, 650], "center": [450, 625], "source": "uia"},
}

SAMPLE_MIXED_ANCHORS = {
    "1": {"name": "One", "type": "ButtonControl", "bbox": [100, 700, 200, 750], "center": [150, 725], "source": "uia"},
    "2": {"name": "Plus", "type": "ButtonControl", "bbox": [400, 600, 500, 650], "center": [450, 625], "source": "uia"},
    "3": {"name": "Submit", "type": "OCRText", "bbox": [300, 400, 450, 440], "center": [375, 420], "source": "ocr", "confidence": 0.92},
    "4": {"name": "搜索", "type": "OCRText", "bbox": [500, 100, 600, 140], "center": [550, 120], "source": "ocr", "confidence": 0.85},
}


@pytest.fixture
def tool():
    return RPAExecutorTool()


class TestMixedAnchorsFormat:
    """Verify anchors.json with mixed UIA + OCR elements has correct structure."""

    def test_all_elements_have_source_field(self):
        for idx, el in SAMPLE_MIXED_ANCHORS.items():
            assert "source" in el, f"Element {idx} missing 'source' field"
            assert el["source"] in ("uia", "ocr")

    def test_ocr_elements_have_confidence(self):
        ocr_els = [el for el in SAMPLE_MIXED_ANCHORS.values() if el["source"] == "ocr"]
        for el in ocr_els:
            assert "confidence" in el
            assert 0 < el["confidence"] <= 1.0

    def test_uia_elements_no_confidence(self):
        uia_els = [el for el in SAMPLE_MIXED_ANCHORS.values() if el["source"] == "uia"]
        for el in uia_els:
            assert "confidence" not in el

    def test_all_elements_have_required_fields(self):
        for idx, el in SAMPLE_MIXED_ANCHORS.items():
            assert "name" in el
            assert "type" in el
            assert "bbox" in el and len(el["bbox"]) == 4
            assert "center" in el and len(el["center"]) == 2


class TestFindByNameWithOCR:
    """Test _find_by_name works with OCR elements."""

    def test_find_ocr_element_by_exact_name(self, tool):
        idx, el = tool._find_by_name(SAMPLE_MIXED_ANCHORS, "Submit")
        assert idx == "3"
        assert el["source"] == "ocr"

    def test_find_ocr_element_chinese(self, tool):
        idx, el = tool._find_by_name(SAMPLE_MIXED_ANCHORS, "搜索")
        assert idx == "4"
        assert el["source"] == "ocr"

    def test_find_uia_element_still_works(self, tool):
        idx, el = tool._find_by_name(SAMPLE_MIXED_ANCHORS, "One")
        assert idx == "1"
        assert el["source"] == "uia"

    def test_case_insensitive_ocr(self, tool):
        idx, el = tool._find_by_name(SAMPLE_MIXED_ANCHORS, "submit")
        assert idx == "3"

    def test_no_match_returns_none(self, tool):
        idx, el = tool._find_by_name(SAMPLE_MIXED_ANCHORS, "不存在的元素")
        assert idx is None
        assert el is None


class TestRPAExecuteWithOCRElements:
    """Test execute with mixed UIA/OCR anchors — verify source is logged."""

    @pytest.mark.asyncio
    async def test_click_ocr_element(self, tool):
        with patch.object(tool, "_load_anchors") as mock_load, \
             patch.object(tool, "_check_bounds", return_value=None), \
             patch("pyautogui.moveTo") as mock_move, \
             patch("pyautogui.click") as mock_click:
            mock_load.return_value = (SAMPLE_MIXED_ANCHORS, Path("/fake/anchors.json"))

            result = await tool.execute(action="click", ui_name="Submit")

            assert "via OCR" in result
            assert "'Submit'" in result
            assert "Successfully performed click" in result
            mock_move.assert_called_once()
            mock_click.assert_called_once()

    @pytest.mark.asyncio
    async def test_click_uia_element(self, tool):
        with patch.object(tool, "_load_anchors") as mock_load, \
             patch.object(tool, "_check_bounds", return_value=None), \
             patch("pyautogui.moveTo"), \
             patch("pyautogui.click"):
            mock_load.return_value = (SAMPLE_MIXED_ANCHORS, Path("/fake/anchors.json"))

            result = await tool.execute(action="click", ui_name="One")

            assert "via UIAutomation" in result
            assert "'One'" in result


class TestMonitorBoundaryCheck:
    """Test _check_bounds for multi-monitor support."""

    def test_within_bounds(self, tool):
        with patch.object(tool, "_load_monitor_context") as mock_ctx:
            mock_ctx.return_value = {
                "monitor_index": 1,
                "offset_x": 0, "offset_y": 0,
                "right": 1920, "bottom": 1080,
            }
            result = tool._check_bounds(960, 540)
            assert result is None  # No warning

    def test_outside_bounds(self, tool):
        with patch.object(tool, "_load_monitor_context") as mock_ctx:
            mock_ctx.return_value = {
                "monitor_index": 1,
                "offset_x": 0, "offset_y": 0,
                "right": 1920, "bottom": 1080,
            }
            result = tool._check_bounds(2500, 540)
            assert result is not None
            assert "OUTSIDE" in result
            assert "WARNING" in result

    def test_no_context_file(self, tool):
        with patch.object(tool, "_load_monitor_context") as mock_ctx:
            mock_ctx.return_value = None
            result = tool._check_bounds(100, 100)
            assert result is None  # No warning when no context

    def test_negative_coordinates_secondary_monitor(self, tool):
        """Secondary monitor to the left of primary has negative offset."""
        with patch.object(tool, "_load_monitor_context") as mock_ctx:
            mock_ctx.return_value = {
                "monitor_index": 2,
                "offset_x": -1920, "offset_y": 0,
                "right": 0, "bottom": 1080,
            }
            # Click at (-960, 540) is within the secondary monitor
            result = tool._check_bounds(-960, 540)
            assert result is None

            # Click at (500, 500) is outside the secondary monitor
            result = tool._check_bounds(500, 500)
            assert result is not None
            assert "OUTSIDE" in result
