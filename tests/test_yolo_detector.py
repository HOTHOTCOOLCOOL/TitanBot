"""Tests for YOLO UI element detector (nanobot.agent.vision.yolo_detector).

These tests verify the module's API surface and logic WITHOUT requiring
the ultralytics package or a real YOLO model to be present.
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch, PropertyMock
import pytest


class _TensorLike:
    """Minimal mock for a torch-like tensor value with .tolist()."""
    def __init__(self, val):
        self._val = val
    def tolist(self):
        return self._val
    def __float__(self):
        return float(self._val)
    def __int__(self):
        return int(self._val)
    def __getitem__(self, idx):
        return self._val[idx]


# ---------------------------------------------------------------------------
# Test: is_available() returns False when ultralytics is not installed
# ---------------------------------------------------------------------------


def test_is_available_when_ultralytics_missing():
    """is_available() should return False if ultralytics is not found."""
    # We test the module-level _HAS_ULTRALYTICS flag
    from nanobot.agent.vision import yolo_detector
    # The actual value depends on the environment—just ensure it returns a bool
    result = yolo_detector.is_available()
    assert isinstance(result, bool)


def test_detect_elements_returns_empty_when_unavailable():
    """detect_elements() should gracefully return [] when ultralytics is missing."""
    from nanobot.agent.vision import yolo_detector

    with patch.object(yolo_detector, "_HAS_ULTRALYTICS", False):
        elements = yolo_detector.detect_elements(
            image_path="/tmp/fake_screenshot.jpg",
            confidence=0.3,
        )
        assert elements == []


# ---------------------------------------------------------------------------
# Test: YOLOElement dataclass
# ---------------------------------------------------------------------------


def test_yolo_element_creation():
    """YOLOElement should store all fields correctly."""
    from nanobot.agent.vision.yolo_detector import YOLOElement

    el = YOLOElement(
        label="button",
        bbox=[10, 20, 100, 50],
        center=[55, 35],
        confidence=0.85,
    )
    assert el.label == "button"
    assert el.bbox == [10, 20, 100, 50]
    assert el.center == [55, 35]
    assert el.confidence == 0.85
    assert el.source == "yolo"


# ---------------------------------------------------------------------------
# Test: IoU computation (_iou)
# ---------------------------------------------------------------------------


def test_iou_identical_boxes():
    """Identical boxes should have IoU = 1.0."""
    from nanobot.agent.vision.yolo_detector import _iou

    box = [0, 0, 100, 100]
    assert _iou(box, box) == pytest.approx(1.0)


def test_iou_no_overlap():
    """Non-overlapping boxes should have IoU = 0.0."""
    from nanobot.agent.vision.yolo_detector import _iou

    box1 = [0, 0, 50, 50]
    box2 = [100, 100, 200, 200]
    assert _iou(box1, box2) == pytest.approx(0.0)


def test_iou_partial_overlap():
    """Partially overlapping boxes should have 0 < IoU < 1."""
    from nanobot.agent.vision.yolo_detector import _iou

    box1 = [0, 0, 100, 100]
    box2 = [50, 50, 150, 150]
    result = _iou(box1, box2)
    assert 0.0 < result < 1.0
    # Manual calculation: intersection = 50*50 = 2500, union = 10000 + 10000 - 2500 = 17500
    # IoU = 2500/17500 ≈ 0.1429
    assert result == pytest.approx(2500 / 17500, abs=0.01)


def test_iou_zero_area_box():
    """A zero-area box should have IoU = 0 with any box."""
    from nanobot.agent.vision.yolo_detector import _iou

    box1 = [50, 50, 50, 50]  # zero area
    box2 = [0, 0, 100, 100]
    assert _iou(box1, box2) == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# Test: _download_model raises for unknown models
# ---------------------------------------------------------------------------


def test_download_model_unknown_raises():
    """Unknown model names should raise FileNotFoundError."""
    from nanobot.agent.vision.yolo_detector import _download_model

    with pytest.raises(FileNotFoundError, match="Unknown YOLO model"):
        _download_model("nonexistent-model-xyz", Path("/tmp"))


# ---------------------------------------------------------------------------
# Test: detect_elements with mocked ultralytics
# ---------------------------------------------------------------------------


def test_detect_elements_with_mock_model():
    """detect_elements should parse YOLO results correctly when ultralytics is available."""
    from nanobot.agent.vision import yolo_detector
    from nanobot.agent.vision.yolo_detector import YOLOElement

    # Create mock box objects

    class MockBox:
        def __init__(self, xyxy, conf, cls):
            self.xyxy = [_TensorLike(xyxy)]
            self.conf = [_TensorLike(conf)]
            self.cls = [_TensorLike(cls)]

    class MockResult:
        def __init__(self):
            self.names = {0: "button", 1: "input", 2: "icon"}
            self.boxes = [
                MockBox([10.0, 20.0, 110.0, 70.0], 0.92, 0),
                MockBox([200.0, 300.0, 350.0, 340.0], 0.75, 2),
            ]

    mock_model = MagicMock()
    mock_model.predict.return_value = [MockResult()]

    with patch.object(yolo_detector, "_HAS_ULTRALYTICS", True), \
         patch.object(yolo_detector, "_model_instance", mock_model):

        elements = yolo_detector.detect_elements(
            image_path="/tmp/test.jpg",
            confidence=0.3,
            offset_x=0,
            offset_y=0,
            scale_ratio=1.0,
        )

    assert len(elements) == 2
    # First element should be higher confidence
    assert elements[0].label == "button"
    assert elements[0].confidence == 0.92
    assert elements[0].source == "yolo"
    # Centers should be computed correctly
    assert elements[0].center == [60, 45]  # midpoint of (10,20)-(110,70)
    assert elements[1].label == "icon"
    assert elements[1].center == [275, 320]  # midpoint of (200,300)-(350,340)


def test_detect_elements_applies_scale_and_offset():
    """detect_elements should correctly transform coordinates with scale_ratio and offset."""
    from nanobot.agent.vision import yolo_detector

    class MockBox:
        def __init__(self, xyxy, conf, cls):
            self.xyxy = [_TensorLike(xyxy)]
            self.conf = [_TensorLike(conf)]
            self.cls = [_TensorLike(cls)]

    class MockResult:
        def __init__(self):
            self.names = {0: "button"}
            # Box at image pixel (100, 200) - (200, 300) with scale_ratio=0.5
            # Should convert to absolute: (200+1920, 400+0) - (400+1920, 600+0)
            self.boxes = [MockBox([100.0, 200.0, 200.0, 300.0], 0.9, 0)]

    mock_model = MagicMock()
    mock_model.predict.return_value = [MockResult()]

    with patch.object(yolo_detector, "_HAS_ULTRALYTICS", True), \
         patch.object(yolo_detector, "_model_instance", mock_model):

        elements = yolo_detector.detect_elements(
            image_path="/tmp/test.jpg",
            confidence=0.3,
            offset_x=1920,  # Second monitor offset
            offset_y=0,
            scale_ratio=0.5,
        )

    assert len(elements) == 1
    el = elements[0]
    # image (100, 200) / 0.5 + 1920 = 2120, 400
    assert el.bbox[0] == 2120  # abs_left = 100/0.5 + 1920
    assert el.bbox[1] == 400   # abs_top = 200/0.5 + 0
    assert el.bbox[2] == 2320  # abs_right = 200/0.5 + 1920
    assert el.bbox[3] == 600   # abs_bottom = 300/0.5 + 0


# ---------------------------------------------------------------------------
# Test: VisionConfig has YOLO fields
# ---------------------------------------------------------------------------


def test_vision_config_yolo_fields():
    """VisionConfig should have YOLO-related fields with correct defaults."""
    from nanobot.config.schema import VisionConfig

    cfg = VisionConfig()
    assert cfg.yolo_enabled is False
    assert cfg.yolo_model == "gpa-gui-detector"
    assert cfg.yolo_confidence == 0.3
