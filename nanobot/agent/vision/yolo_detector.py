"""YOLO-based UI element detector for screen captures.

Provides Layer 3 perception when UIAutomation and OCR cannot
discover interactive UI elements (e.g. icon-only buttons, canvas UIs,
complex web applications).

Uses Ultralytics YOLOv8 with a GUI-specialised model.
"""

import os
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

from loguru import logger

# ---------------------------------------------------------------------------
# Lazy-loaded YOLO singleton
# ---------------------------------------------------------------------------

_model_instance = None
_HAS_ULTRALYTICS = False

try:
    import importlib
    _ul_spec = importlib.util.find_spec("ultralytics")
    _HAS_ULTRALYTICS = _ul_spec is not None
except Exception:
    _HAS_ULTRALYTICS = False


# Default model directory
_DEFAULT_MODEL_DIR = Path.home() / ".nanobot" / "models"

# Built-in model options (name → HuggingFace repo or direct URL)
_KNOWN_MODELS = {
    "gpa-gui-detector": {
        "repo": "Salesforce/GPA-GUI-Detector",
        "filename": "model.pt",
    },
}


@dataclass
class YOLOElement:
    """A single UI element detected by YOLO."""

    label: str
    bbox: list          # [left, top, right, bottom]  — absolute screen coords
    center: list        # [cx, cy]
    confidence: float
    source: str = "yolo"


def _download_model(model_name: str, target_dir: Path) -> Path:
    """Download a known YOLO model from HuggingFace Hub.

    Returns the local path to the downloaded .pt file.
    """
    if model_name not in _KNOWN_MODELS:
        raise FileNotFoundError(
            f"Unknown YOLO model '{model_name}'. "
            f"Known models: {list(_KNOWN_MODELS.keys())}. "
            f"Or pass an absolute path to a .pt file."
        )

    info = _KNOWN_MODELS[model_name]
    target_dir.mkdir(parents=True, exist_ok=True)
    local_path = target_dir / f"{model_name}.pt"

    if local_path.exists():
        logger.debug(f"YOLO model already cached: {local_path}")
        return local_path

    logger.info(f"Downloading YOLO model '{model_name}' from HuggingFace...")

    try:
        from huggingface_hub import hf_hub_download
        downloaded = hf_hub_download(
            repo_id=info["repo"],
            filename=info["filename"],
            local_dir=str(target_dir),
            local_dir_use_symlinks=False,
        )
        # Rename to our standard name
        dl_path = Path(downloaded)
        if dl_path != local_path:
            dl_path.rename(local_path)
        logger.info(f"YOLO model saved to {local_path}")
    except ImportError:
        # Fallback: try direct download if huggingface_hub is not installed
        logger.info("huggingface_hub not installed, trying direct download...")
        import urllib.request
        url = f"https://huggingface.co/{info['repo']}/resolve/main/{info['filename']}"
        urllib.request.urlretrieve(url, str(local_path))
        logger.info(f"YOLO model downloaded to {local_path}")

    return local_path


def _get_model(model_name_or_path: str = "gpa-gui-detector"):
    """Lazy-init YOLO model singleton.

    Args:
        model_name_or_path: Either a known model name (e.g. "gpa-gui-detector")
                           or an absolute path to a .pt file.
    """
    global _model_instance
    if _model_instance is not None:
        return _model_instance

    from ultralytics import YOLO

    # Resolve model path
    model_path = Path(model_name_or_path)
    if not model_path.is_absolute() or not model_path.exists():
        # Try as a known model name
        model_path = _download_model(model_name_or_path, _DEFAULT_MODEL_DIR)

    logger.info(f"Loading YOLO model from {model_path}")
    _model_instance = YOLO(str(model_path))
    return _model_instance


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


def detect_elements(
    image_path: str | Path,
    confidence: float = 0.3,
    offset_x: int = 0,
    offset_y: int = 0,
    scale_ratio: float = 1.0,
    model_name: str = "gpa-gui-detector",
) -> List[YOLOElement]:
    """Run YOLO detection on an image and return detected UI elements.

    Args:
        image_path:     Path to the screenshot image.
        confidence:     Minimum detection confidence threshold (0-1).
        offset_x:       Monitor X offset (for multi-monitor absolute coordinate calculation).
        offset_y:       Monitor Y offset.
        scale_ratio:    The ratio used to resize the original screenshot.
                        YOLO runs on the *resized* image, so we need to convert
                        detected coordinates back to absolute screen coordinates.
        model_name:     Model name or path to .pt file.

    Returns:
        List of YOLOElement with absolute screen coordinates.
    """
    if not _HAS_ULTRALYTICS:
        logger.debug("ultralytics not installed — skipping YOLO detection")
        return []

    try:
        model = _get_model(model_name)
        results = model.predict(
            source=str(image_path),
            conf=confidence,
            verbose=False,
            imgsz=1280,
        )
    except Exception as e:
        logger.warning(f"YOLO detection failed: {e}")
        return []

    if not results or len(results) == 0:
        return []

    result = results[0]  # Single image, single result
    elements: List[YOLOElement] = []

    for box in result.boxes:
        # box.xyxy is [left, top, right, bottom] in image pixel space
        x1, y1, x2, y2 = box.xyxy[0].tolist()
        conf = float(box.conf[0])
        cls_id = int(box.cls[0])

        # Get class label
        label = result.names.get(cls_id, f"class_{cls_id}")

        # Convert image-pixel coordinates back to absolute screen coordinates
        if scale_ratio > 0 and scale_ratio != 1.0:
            abs_left = int(x1 / scale_ratio) + offset_x
            abs_top = int(y1 / scale_ratio) + offset_y
            abs_right = int(x2 / scale_ratio) + offset_x
            abs_bottom = int(y2 / scale_ratio) + offset_y
        else:
            abs_left = int(x1) + offset_x
            abs_top = int(y1) + offset_y
            abs_right = int(x2) + offset_x
            abs_bottom = int(y2) + offset_y

        cx = (abs_left + abs_right) // 2
        cy = (abs_top + abs_bottom) // 2

        elements.append(YOLOElement(
            label=label,
            bbox=[abs_left, abs_top, abs_right, abs_bottom],
            center=[cx, cy],
            confidence=round(conf, 3),
        ))

    # Sort by confidence (highest first)
    elements.sort(key=lambda e: e.confidence, reverse=True)

    logger.debug(f"YOLO detected {len(elements)} UI elements")
    return elements


def is_available() -> bool:
    """Check if ultralytics is installed and usable."""
    return _HAS_ULTRALYTICS
