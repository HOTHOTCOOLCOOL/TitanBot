"""UI Anchor system (Set-of-Marks) for preventing vision hallucinations.

Supports three perception layers:
  Layer 1: Windows UIAutomation (fastest, most precise)
  Layer 2: PaddleOCR fallback (when UIAutomation finds too few elements)
  Layer 3: YOLO detection (GUI element detection for icon-only buttons, web UIs, etc.)
"""

import json
from pathlib import Path
from typing import Any, Dict, List, Tuple

from loguru import logger

try:
    import uiautomation as auto
    from PIL import Image, ImageDraw, ImageFont
    HAS_UIAUTOMATION = True
except ImportError:
    HAS_UIAUTOMATION = False


# ── Colours for Set-of-Marks annotation ──────────────────────────────────
_UIA_COLOR = (255, 0, 0, 200)       # Red  – UIAutomation elements
_UIA_TAG_BG = (255, 0, 0, 255)
_OCR_COLOR = (0, 120, 255, 200)     # Blue – OCR elements
_OCR_TAG_BG = (0, 120, 255, 255)
_YOLO_COLOR = (0, 200, 0, 200)      # Green – YOLO elements
_YOLO_TAG_BG = (0, 200, 0, 255)
_TAG_TEXT = (255, 255, 255, 255)     # White text


def _extract_uia_elements(
    monitor_left: int = 0,
    monitor_top: int = 0,
    monitor_right: int = 99999,
    monitor_bottom: int = 99999,
) -> List[Dict[str, Any]]:
    """Walk UIAutomation tree and return interactive elements within a monitor viewport."""
    if not HAS_UIAUTOMATION:
        return []

    auto.SetGlobalSearchTimeout(1.0)
    root = auto.GetRootControl()

    interactive_types = {
        auto.ControlType.ButtonControl,
        auto.ControlType.MenuItemControl,
        auto.ControlType.ListItemControl,
        auto.ControlType.TreeItemControl,
        auto.ControlType.EditControl,
        auto.ControlType.HyperlinkControl,
        auto.ControlType.TabItemControl,
        auto.ControlType.DocumentControl,
    }

    elements = []
    for control, depth in auto.WalkControl(root):
        if not control:
            continue
        if depth > 10:
            continue
        try:
            rect = control.BoundingRectangle
            if not rect or rect.width() <= 0 or rect.height() <= 0:
                continue

            # ── Multi-monitor filter: skip elements outside current monitor ──
            center_x = rect.left + rect.width() // 2
            center_y = rect.top + rect.height() // 2
            if (center_x < monitor_left or center_x > monitor_right or
                    center_y < monitor_top or center_y > monitor_bottom):
                continue

            if control.ControlType in interactive_types:
                elements.append({
                    "name": control.Name,
                    "type": control.ControlTypeName,
                    "bbox": [rect.left, rect.top, rect.right, rect.bottom],
                    "center": [center_x, center_y],
                    "source": "uia",
                })
        except Exception:
            pass

    return elements


def _merge_ocr_elements(
    uia_elements: List[Dict],
    image_path: Path,
    offset_x: int,
    offset_y: int,
    scale_ratio: float,
    min_confidence: float = 0.7,
) -> List[Dict[str, Any]]:
    """Run OCR and merge results with existing UIAutomation elements.

    OCR elements that overlap with existing UIA elements (by center distance)
    are dropped to avoid duplicates.
    """
    try:
        from nanobot.agent.vision.ocr_engine import detect_text, is_available
    except ImportError:
        return []

    if not is_available():
        logger.debug("PaddleOCR not available — skipping OCR merge")
        return []

    ocr_elements = detect_text(
        image_path,
        min_confidence=min_confidence,
        offset_x=offset_x,
        offset_y=offset_y,
        scale_ratio=scale_ratio,
    )

    if not ocr_elements:
        return []

    # Build set of existing UIA centers for overlap check
    uia_centers = [(el["center"][0], el["center"][1]) for el in uia_elements]

    merged = []
    for ocr_el in ocr_elements:
        cx, cy = ocr_el.center
        # Skip if an existing UIA element is within 30px (same region)
        if any(abs(cx - ux) < 30 and abs(cy - uy) < 30 for ux, uy in uia_centers):
            continue
        merged.append({
            "name": ocr_el.text,
            "type": "OCRText",
            "bbox": ocr_el.bbox,
            "center": ocr_el.center,
            "source": "ocr",
            "confidence": ocr_el.confidence,
        })

    logger.info(f"OCR added {len(merged)} new elements (filtered {len(ocr_elements) - len(merged)} overlaps with UIA)")
    return merged


def _merge_yolo_elements(
    existing_elements: List[Dict],
    image_path: Path,
    offset_x: int,
    offset_y: int,
    scale_ratio: float,
    min_confidence: float = 0.3,
    model_name: str = "gpa-gui-detector",
) -> List[Dict[str, Any]]:
    """Run YOLO detection and merge results with existing UIA + OCR elements.

    YOLO elements that overlap with existing elements (by IoU > 0.5)
    are dropped to avoid duplicates.
    """
    try:
        from nanobot.agent.vision.yolo_detector import detect_elements, is_available
    except ImportError:
        return []

    if not is_available():
        logger.debug("ultralytics not available — skipping YOLO detection")
        return []

    yolo_elements = detect_elements(
        image_path,
        confidence=min_confidence,
        offset_x=offset_x,
        offset_y=offset_y,
        scale_ratio=scale_ratio,
        model_name=model_name,
    )

    if not yolo_elements:
        return []

    # Build set of existing bboxes for overlap check
    existing_bboxes = [el["bbox"] for el in existing_elements]

    def _iou(box1, box2):
        x1 = max(box1[0], box2[0])
        y1 = max(box1[1], box2[1])
        x2 = min(box1[2], box2[2])
        y2 = min(box1[3], box2[3])
        inter = max(0, x2 - x1) * max(0, y2 - y1)
        area1 = (box1[2] - box1[0]) * (box1[3] - box1[1])
        area2 = (box2[2] - box2[0]) * (box2[3] - box2[1])
        union = area1 + area2 - inter
        return inter / union if union > 0 else 0.0

    merged = []
    for yel in yolo_elements:
        # Skip if any existing element overlaps significantly
        if any(_iou(yel.bbox, eb) > 0.5 for eb in existing_bboxes):
            continue
        merged.append({
            "name": yel.label,
            "type": "YOLODetected",
            "bbox": yel.bbox,
            "center": yel.center,
            "source": "yolo",
            "confidence": yel.confidence,
        })

    logger.info(
        f"YOLO added {len(merged)} new elements "
        f"(filtered {len(yolo_elements) - len(merged)} overlaps with UIA/OCR)"
    )
    return merged


def extract_and_draw_anchors(
    image_path: Path,
    output_path: Path,
    anchors_json_path: Path,
    offset_x: int = 0,
    offset_y: int = 0,
    scale_ratio: float = 1.0,
    use_ocr_fallback: bool = True,
    ocr_min_confidence: float = 0.7,
    uia_fallback_threshold: int = 3,
    monitor_right: int = 99999,
    monitor_bottom: int = 99999,
    use_yolo: bool = False,
    yolo_confidence: float = 0.3,
    yolo_model: str = "gpa-gui-detector",
) -> List[str]:
    """
    Extracts UI elements, draws Set-of-Marks numbered boxes on the image,
    and saves the coordinate mapping to a JSON file.

    Three-layer perception:
      1. UIAutomation (always attempted first)
      2. PaddleOCR (auto-triggered when UIA finds < uia_fallback_threshold elements)
      3. YOLO (detects icon-only buttons, web UI elements, etc.)

    Returns summary lines of the elements extracted.
    """
    if not HAS_UIAUTOMATION:
        raise ImportError("uiautomation library is missing.")

    # ── Layer 1: UIAutomation ──
    elements = _extract_uia_elements(
        monitor_left=offset_x,
        monitor_top=offset_y,
        monitor_right=monitor_right,
        monitor_bottom=monitor_bottom,
    )
    uia_count = len(elements)
    logger.debug(f"UIAutomation discovered {uia_count} interactive elements")

    # ── Layer 2: OCR fallback ──
    if use_ocr_fallback and uia_count < uia_fallback_threshold:
        logger.info(
            f"UIAutomation found only {uia_count} elements (< {uia_fallback_threshold}). "
            f"Triggering PaddleOCR fallback..."
        )
        ocr_extra = _merge_ocr_elements(
            elements, image_path, offset_x, offset_y, scale_ratio, ocr_min_confidence,
        )
        elements.extend(ocr_extra)
    elif use_ocr_fallback:
        logger.debug(f"UIAutomation found {uia_count} elements — OCR fallback not needed")

    # ── Layer 3: YOLO detection ──
    if use_yolo:
        logger.info("YOLO detection enabled — running GUI element detection...")
        yolo_extra = _merge_yolo_elements(
            elements, image_path, offset_x, offset_y, scale_ratio,
            min_confidence=yolo_confidence,
            model_name=yolo_model,
        )
        elements.extend(yolo_extra)

    # ── Draw Set-of-Marks on image ──
    try:
        img = Image.open(image_path).convert("RGBA")
        draw = ImageDraw.Draw(img)

        try:
            font = ImageFont.truetype("arialbd.ttf", 14)
        except IOError:
            font = ImageFont.load_default()

        anchors_mapping = {}
        rendered_elements = []

        seen_centers = []
        index = 1

        for el in elements:
            cx, cy = el["center"]
            el_source = el.get("source", "uia")
            is_ocr = el_source == "ocr"
            is_yolo = el_source == "yolo"

            # Convert to relative coordinates within the image
            rel_cx = (cx - offset_x) * scale_ratio
            rel_cy = (cy - offset_y) * scale_ratio

            # Check if it's within the image bounds
            if rel_cx < 0 or rel_cx > img.width or rel_cy < 0 or rel_cy > img.height:
                continue

            # Skip if we already have an element extremely close (within 10 pixels)
            if any(abs(rel_cx - sx) < 10 and abs(rel_cy - sy) < 10 for sx, sy in seen_centers):
                continue

            seen_centers.append((rel_cx, rel_cy))

            # Choose colour based on source
            if is_yolo:
                box_color, tag_bg = _YOLO_COLOR, _YOLO_TAG_BG
            elif is_ocr:
                box_color, tag_bg = _OCR_COLOR, _OCR_TAG_BG
            else:
                box_color, tag_bg = _UIA_COLOR, _UIA_TAG_BG

            # Draw bounding box
            orig_left, orig_top, orig_right, orig_bottom = el["bbox"]
            left = (orig_left - offset_x) * scale_ratio
            right = (orig_right - offset_x) * scale_ratio
            top = (orig_top - offset_y) * scale_ratio
            bottom = (orig_bottom - offset_y) * scale_ratio

            draw.rectangle([left, top, right, bottom], outline=box_color, width=2)

            # Draw tag with index number
            text = str(index)
            try:
                left_txt, top_txt, right_txt, bottom_txt = draw.textbbox((0, 0), text, font=font)
                tw, th = right_txt - left_txt, bottom_txt - top_txt
            except AttributeError:
                tw, th = draw.textsize(text, font=font)

            draw.rectangle(
                [left, max(0, top - th - 4), left + tw + 4, max(th + 4, top)],
                fill=tag_bg,
            )
            draw.text((left + 2, max(0, top - th - 2)), text, fill=_TAG_TEXT, font=font)

            # Save to mapping (original un-scaled absolute coordinates for RPA executor)
            anchors_mapping[str(index)] = el
            source_tag = " [YOLO]" if is_yolo else (" [OCR]" if is_ocr else "")
            rendered_elements.append(
                f"Index {index}: [{el['type']}] {el['name']}{source_tag}"
            )
            index += 1

        # Save annotated image
        img.convert("RGB").save(output_path, "JPEG", quality=85)

        # Save mapping to JSON
        with open(anchors_json_path, 'w', encoding='utf-8') as f:
            json.dump(anchors_mapping, f, ensure_ascii=False, indent=2)

        return rendered_elements

    except Exception as e:
        raise RuntimeError(f"Failed to draw anchors: {e}")
