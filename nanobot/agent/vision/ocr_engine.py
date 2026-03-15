"""OCR Engine using PaddleOCR for text detection on screen captures.

Provides a fallback perception layer when Windows UIAutomation cannot
discover UI elements (e.g. web apps, remote desktops, canvas-based UIs).
"""

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

from loguru import logger

# ---------------------------------------------------------------------------
# Lazy-loaded PaddleOCR singleton
# ---------------------------------------------------------------------------

_ocr_instance = None
_HAS_PADDLE = False

try:
    # Probe availability without heavy init
    import importlib
    _paddle_spec = importlib.util.find_spec("paddleocr")
    _HAS_PADDLE = _paddle_spec is not None
except Exception:
    _HAS_PADDLE = False


@dataclass
class OCRElement:
    """A single text element detected by OCR."""

    text: str
    bbox: list  # [left, top, right, bottom]
    center: list  # [cx, cy]
    confidence: float
    source: str = "ocr"


def _detect_cuda() -> bool:
    """Return True if a usable CUDA GPU is available for PaddlePaddle."""
    try:
        import paddle
        return paddle.device.is_compiled_with_cuda() and paddle.device.cuda.device_count() > 0
    except Exception:
        return False


def _get_ocr_instance():
    """Lazy-init PaddleOCR singleton with CUDA auto-detection."""
    global _ocr_instance
    if _ocr_instance is not None:
        return _ocr_instance

    from paddleocr import PaddleOCR

    use_gpu = _detect_cuda()
    logger.info(f"Initializing PaddleOCR (use_gpu={use_gpu})")

    _ocr_instance = PaddleOCR(
        use_angle_cls=True,  # Handle rotated text
        lang="ch",           # Chinese model also handles English
        use_gpu=use_gpu,
        show_log=False,
        # Suppress first-run model download progress bars
        det_model_dir=None,
        rec_model_dir=None,
        cls_model_dir=None,
    )
    return _ocr_instance


def _polygon_to_bbox(polygon: list) -> tuple:
    """Convert PaddleOCR polygon [[x1,y1],[x2,y2],[x3,y3],[x4,y4]] to [left, top, right, bottom]."""
    xs = [p[0] for p in polygon]
    ys = [p[1] for p in polygon]
    return int(min(xs)), int(min(ys)), int(max(xs)), int(max(ys))


def _iou(box1: list, box2: list) -> float:
    """Compute Intersection-over-Union between two [l, t, r, b] boxes."""
    x1 = max(box1[0], box2[0])
    y1 = max(box1[1], box2[1])
    x2 = min(box1[2], box2[2])
    y2 = min(box1[3], box2[3])
    inter = max(0, x2 - x1) * max(0, y2 - y1)
    area1 = (box1[2] - box1[0]) * (box1[3] - box1[1])
    area2 = (box2[2] - box2[0]) * (box2[3] - box2[1])
    union = area1 + area2 - inter
    return inter / union if union > 0 else 0.0


def detect_text(
    image_path: str | Path,
    min_confidence: float = 0.7,
    offset_x: int = 0,
    offset_y: int = 0,
    scale_ratio: float = 1.0,
) -> List[OCRElement]:
    """
    Run OCR on an image and return detected text elements.

    Args:
        image_path:     Path to the screenshot image.
        min_confidence: Minimum confidence threshold (0-1).
        offset_x:       Monitor X offset (for multi-monitor absolute coordinate calculation).
        offset_y:       Monitor Y offset.
        scale_ratio:    The ratio used to resize the original screenshot.
                        OCR runs on the *resized* image, so we need to convert
                        detected coordinates back to absolute screen coordinates.

    Returns:
        List of OCRElement with absolute screen coordinates.
    """
    if not _HAS_PADDLE:
        logger.debug("PaddleOCR not installed — skipping OCR detection")
        return []

    try:
        ocr = _get_ocr_instance()
        results = ocr.ocr(str(image_path), cls=True)
    except Exception as e:
        logger.warning(f"PaddleOCR detection failed: {e}")
        return []

    if not results or not results[0]:
        return []

    elements: List[OCRElement] = []
    for line in results[0]:
        polygon, (text, confidence) = line[0], line[1]
        if confidence < min_confidence:
            continue
        if not text or not text.strip():
            continue

        # Convert polygon to bbox in image-pixel space
        img_left, img_top, img_right, img_bottom = _polygon_to_bbox(polygon)

        # Convert image-pixel coordinates back to absolute screen coordinates
        if scale_ratio > 0 and scale_ratio != 1.0:
            abs_left = int(img_left / scale_ratio) + offset_x
            abs_top = int(img_top / scale_ratio) + offset_y
            abs_right = int(img_right / scale_ratio) + offset_x
            abs_bottom = int(img_bottom / scale_ratio) + offset_y
        else:
            abs_left = img_left + offset_x
            abs_top = img_top + offset_y
            abs_right = img_right + offset_x
            abs_bottom = img_bottom + offset_y

        cx = (abs_left + abs_right) // 2
        cy = (abs_top + abs_bottom) // 2

        elements.append(OCRElement(
            text=text.strip(),
            bbox=[abs_left, abs_top, abs_right, abs_bottom],
            center=[cx, cy],
            confidence=round(confidence, 3),
        ))

    # Dedup: merge highly overlapping boxes (IoU > 0.5), keep higher confidence
    elements.sort(key=lambda e: e.confidence, reverse=True)
    deduped: List[OCRElement] = []
    for el in elements:
        if any(_iou(el.bbox, kept.bbox) > 0.5 for kept in deduped):
            continue
        deduped.append(el)

    logger.debug(f"OCR detected {len(deduped)} text elements (from {len(elements)} raw)")
    return deduped


def is_available() -> bool:
    """Check if PaddleOCR is installed and usable."""
    return _HAS_PADDLE
