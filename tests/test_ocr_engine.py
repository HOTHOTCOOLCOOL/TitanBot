"""Tests for OCR engine module (nanobot.agent.vision.ocr_engine)."""

import sys
from unittest.mock import patch, MagicMock

# Mock chromadb before any nanobot imports to avoid pydantic v1 + Python 3.14 conflict
sys.modules.setdefault("chromadb", MagicMock())
sys.modules.setdefault("chromadb.api.types", MagicMock())

import pytest
from dataclasses import asdict


class TestOCRElement:
    """Test OCRElement data structure."""

    def test_element_fields(self):
        from nanobot.agent.vision.ocr_engine import OCRElement

        el = OCRElement(
            text="Submit",
            bbox=[100, 200, 300, 250],
            center=[200, 225],
            confidence=0.95,
        )
        assert el.text == "Submit"
        assert el.bbox == [100, 200, 300, 250]
        assert el.center == [200, 225]
        assert el.confidence == 0.95
        assert el.source == "ocr"

    def test_element_custom_source(self):
        from nanobot.agent.vision.ocr_engine import OCRElement

        el = OCRElement(text="X", bbox=[0,0,1,1], center=[0,0], confidence=0.5, source="custom")
        assert el.source == "custom"

    def test_element_to_dict(self):
        from nanobot.agent.vision.ocr_engine import OCRElement

        el = OCRElement(text="OK", bbox=[0,0,10,10], center=[5,5], confidence=0.8)
        d = asdict(el)
        assert d["text"] == "OK"
        assert d["source"] == "ocr"


class TestPolygonToBbox:
    """Test polygon → bbox conversion."""

    def test_regular_polygon(self):
        from nanobot.agent.vision.ocr_engine import _polygon_to_bbox

        polygon = [[10, 20], [100, 20], [100, 50], [10, 50]]
        left, top, right, bottom = _polygon_to_bbox(polygon)
        assert left == 10
        assert top == 20
        assert right == 100
        assert bottom == 50

    def test_rotated_polygon(self):
        from nanobot.agent.vision.ocr_engine import _polygon_to_bbox

        polygon = [[50, 10], [110, 30], [100, 60], [40, 40]]
        left, top, right, bottom = _polygon_to_bbox(polygon)
        assert left == 40
        assert top == 10
        assert right == 110
        assert bottom == 60


class TestIoU:
    """Test IoU calculation."""

    def test_identical_boxes(self):
        from nanobot.agent.vision.ocr_engine import _iou
        assert _iou([0,0,10,10], [0,0,10,10]) == 1.0

    def test_no_overlap(self):
        from nanobot.agent.vision.ocr_engine import _iou
        assert _iou([0,0,10,10], [20,20,30,30]) == 0.0

    def test_partial_overlap(self):
        from nanobot.agent.vision.ocr_engine import _iou
        iou = _iou([0,0,10,10], [5,5,15,15])
        assert 0.1 < iou < 0.3  # ~14.3%

    def test_zero_area(self):
        from nanobot.agent.vision.ocr_engine import _iou
        assert _iou([0,0,0,0], [0,0,10,10]) == 0.0


class TestDetectText:
    """Test the detect_text function."""

    def test_graceful_when_paddle_not_installed(self):
        """Should return empty list when PaddleOCR is not installed."""
        from nanobot.agent.vision import ocr_engine
        
        # Temporarily pretend paddle is not available
        original = ocr_engine._HAS_PADDLE
        ocr_engine._HAS_PADDLE = False
        try:
            result = ocr_engine.detect_text("nonexistent.jpg")
            assert result == []
        finally:
            ocr_engine._HAS_PADDLE = original

    @patch("nanobot.agent.vision.ocr_engine._HAS_PADDLE", True)
    @patch("nanobot.agent.vision.ocr_engine._get_ocr_instance")
    def test_detect_with_mock_ocr(self, mock_get_instance):
        from nanobot.agent.vision.ocr_engine import detect_text

        mock_ocr = MagicMock()
        mock_ocr.ocr.return_value = [[
            [[[10, 20], [100, 20], [100, 50], [10, 50]], ("Submit", 0.95)],
            [[[200, 300], [350, 300], [350, 340], [200, 340]], ("Cancel", 0.88)],
            [[[400, 400], [420, 400], [420, 410], [400, 410]], ("x", 0.3)],  # low confidence
        ]]
        mock_get_instance.return_value = mock_ocr

        results = detect_text("test.jpg", min_confidence=0.7)

        assert len(results) == 2
        assert results[0].text == "Submit"
        assert results[0].confidence == 0.95
        assert results[1].text == "Cancel"

    @patch("nanobot.agent.vision.ocr_engine._HAS_PADDLE", True)
    @patch("nanobot.agent.vision.ocr_engine._get_ocr_instance")
    def test_detect_with_offset_and_scale(self, mock_get_instance):
        """OCR coordinates should be converted to absolute screen coordinates."""
        from nanobot.agent.vision.ocr_engine import detect_text

        mock_ocr = MagicMock()
        # Image-pixel bbox: [100, 100, 200, 150] (after resize)
        mock_ocr.ocr.return_value = [[
            [[[100, 100], [200, 100], [200, 150], [100, 150]], ("Button", 0.9)],
        ]]
        mock_get_instance.return_value = mock_ocr

        # Monitor at offset (1920, 0), image was scaled to 0.5
        results = detect_text(
            "test.jpg",
            offset_x=1920,
            offset_y=0,
            scale_ratio=0.5,
        )

        assert len(results) == 1
        el = results[0]
        # bbox should be: left = 100/0.5 + 1920 = 2120, etc
        assert el.bbox[0] == 2120  # left
        assert el.center[0] == (2120 + 2320) // 2  # center x

    @patch("nanobot.agent.vision.ocr_engine._HAS_PADDLE", True)
    @patch("nanobot.agent.vision.ocr_engine._get_ocr_instance")
    def test_dedup_overlapping(self, mock_get_instance):
        """Highly overlapping boxes should be deduped (keep higher confidence)."""
        from nanobot.agent.vision.ocr_engine import detect_text

        mock_ocr = MagicMock()
        mock_ocr.ocr.return_value = [[
            [[[10, 10], [100, 10], [100, 50], [10, 50]], ("Hello", 0.95)],
            [[[12, 12], [98, 12], [98, 48], [12, 48]], ("Hello", 0.80)],  # nearly identical
        ]]
        mock_get_instance.return_value = mock_ocr

        results = detect_text("test.jpg")
        assert len(results) == 1
        assert results[0].confidence == 0.95

    @patch("nanobot.agent.vision.ocr_engine._HAS_PADDLE", True)
    @patch("nanobot.agent.vision.ocr_engine._get_ocr_instance")
    def test_empty_results(self, mock_get_instance):
        from nanobot.agent.vision.ocr_engine import detect_text

        mock_ocr = MagicMock()
        mock_ocr.ocr.return_value = [None]
        mock_get_instance.return_value = mock_ocr

        results = detect_text("test.jpg")
        assert results == []

    @patch("nanobot.agent.vision.ocr_engine._HAS_PADDLE", True)
    @patch("nanobot.agent.vision.ocr_engine._get_ocr_instance")
    def test_ocr_exception_handled_gracefully(self, mock_get_instance):
        from nanobot.agent.vision.ocr_engine import detect_text

        mock_ocr = MagicMock()
        mock_ocr.ocr.side_effect = RuntimeError("PaddleOCR crashed")
        mock_get_instance.return_value = mock_ocr

        results = detect_text("test.jpg")
        assert results == []


class TestIsAvailable:
    """Test availability check."""

    def test_reflects_paddle_state(self):
        from nanobot.agent.vision import ocr_engine

        original = ocr_engine._HAS_PADDLE
        try:
            ocr_engine._HAS_PADDLE = True
            assert ocr_engine.is_available() is True

            ocr_engine._HAS_PADDLE = False
            assert ocr_engine.is_available() is False
        finally:
            ocr_engine._HAS_PADDLE = original


class TestCudaDetection:
    """Test CUDA auto-detection function."""

    @patch("nanobot.agent.vision.ocr_engine.importlib")
    def test_cuda_detection_no_paddle_installed(self, mock_importlib):
        from nanobot.agent.vision.ocr_engine import _detect_cuda

        # When paddle import fails, should return False
        with patch.dict("sys.modules", {"paddle": None}):
            with patch("builtins.__import__", side_effect=ImportError):
                result = _detect_cuda()
                assert result is False
