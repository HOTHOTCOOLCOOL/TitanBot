"""Screen capture tool for multi-modal vision."""

import json
import time
from pathlib import Path
from typing import Any, Dict

try:
    import mss
    from PIL import Image
    HAS_VISION_DEPS = True
except ImportError:
    HAS_VISION_DEPS = False

from nanobot.agent.tools.base import Tool


class ScreenCaptureTool(Tool):
    """
    Captures the current screen and prepares it for VLM consumption.
    Saves the screenshot to the workspace tmp directory and returns a special path
    that the ContextBuilder will intercept to inject the image payload.
    """

    name = "screen_capture"
    description = (
        "Captures the current computer screen and returns the image plus a structured "
        "text list of all interactive UI elements. Use this to discover what buttons, "
        "inputs, and controls are on screen. After calling this, you can click any "
        "element directly with rpa(action='click', ui_name='ElementName') — no VLM needed. "
        "If UI elements are missing from the list (e.g. web apps), add use_ocr=true to "
        "detect text on screen via OCR."
    )
    
    parameters = {
        "type": "object",
        "properties": {
            "monitor": {
                "type": "integer",
                "description": (
                    "Monitor index to capture. 0 = all monitors combined, "
                    "1 = primary monitor, 2 = secondary, etc. Defaults to 1."
                ),
                "default": 1
            },
            "resize_width": {
                "type": "integer",
                "description": "Optional max width to resize the image to shrink token size. Defaults to 1280.",
                "default": 1280
            },
            "annotate_ui": {
                "type": "boolean",
                "description": "If true, detects interactive UI elements and returns their names and types. "
                               "After this, use rpa(action='click', ui_name='<name>') to click any element by name.",
                "default": False
            },
            "use_ocr": {
                "type": "boolean",
                "description": (
                    "If true, force PaddleOCR text detection in addition to UIAutomation. "
                    "Useful for web apps, Electron apps, or any UI where standard element detection "
                    "fails to find buttons/text. Requires annotate_ui=true."
                ),
                "default": False
            }
        },
        "additionalProperties": False,
    }

    def __init__(self, workspace: Path):
        self.workspace = Path(workspace)
        self.tmp_dir = self.workspace / "tmp"
        self.tmp_dir.mkdir(parents=True, exist_ok=True)

    def _group_anchors_by_type(self, anchors_json_path: Path) -> str:
        """
        Read anchors.json and produce a grouped-by-type summary for text LLMs.
        E.g.:
          ## Buttons
            - "One" (index 5)
            - "Plus" (index 12)
          ## OCR Detected Text
            - "Submit" (index 23) [OCR]
        """
        try:
            with open(anchors_json_path, 'r', encoding='utf-8') as f:
                mapping = json.load(f)
        except Exception:
            return ""
        
        if not mapping:
            return ""
        
        # Group by control type
        groups: Dict[str, list] = {}
        for idx, el in mapping.items():
            el_type = el.get("type", "Unknown")
            el_name = el.get("name", "")
            if not el_name:
                continue
            # Use a more user-friendly group name for OCR/YOLO elements
            source = el.get("source", "uia")
            if source == "ocr":
                group_key = "OCR Detected Text"
            elif source == "yolo":
                group_key = "YOLO Detected"
            else:
                group_key = el_type
            if group_key not in groups:
                groups[group_key] = []
            source_tag = " [OCR]" if source == "ocr" else (" [YOLO]" if source == "yolo" else "")
            groups[group_key].append((idx, el_name, source_tag))
        
        if not groups:
            return ""
        
        lines = ["\n── UI Elements by Type ──"]
        for ctrl_type, items in groups.items():
            lines.append(f"\n### {ctrl_type}")
            for idx, name, tag in items:
                lines.append(f'  - "{name}" (index {idx}){tag}')
        
        lines.append(
            "\n💡 TIP: Use rpa(action='click', ui_name='<name>') to click any element above by its name. "
            "No screenshot analysis needed!"
        )
        return "\n".join(lines)

    async def execute(self, **kwargs) -> str:
        if not HAS_VISION_DEPS:
            return "Error: Missing dependencies for screen_capture. Please run: pip install mss Pillow"

        monitor_idx = kwargs.get("monitor", 1)
        max_width = kwargs.get("resize_width", 1280)
        
        annotate_ui_arg = kwargs.get("annotate_ui", False)
        if isinstance(annotate_ui_arg, str):
            annotate_ui = annotate_ui_arg.lower() == "true"
        else:
            annotate_ui = bool(annotate_ui_arg)

        use_ocr_arg = kwargs.get("use_ocr", False)
        if isinstance(use_ocr_arg, str):
            use_ocr = use_ocr_arg.lower() == "true"
        else:
            use_ocr = bool(use_ocr_arg)

        # Generate a unique filename based on timestamp
        filename = f"capture_{int(time.time()*1000)}.jpg"
        filepath = self.tmp_dir / filename
        anchors_json_path = self.tmp_dir / "anchors.json"
        monitor_context_path = self.tmp_dir / "monitor_context.json"

        try:
            with mss.mss() as sct:
                # mss monitors list: [0] is all monitors combined, [1] is first monitor, etc
                if monitor_idx >= len(sct.monitors):
                    monitor_idx = 1
                
                monitor = sct.monitors[monitor_idx]
                sct_img = sct.grab(monitor)
                offset_x = monitor["left"]
                offset_y = monitor["top"]
                monitor_width = monitor["width"]
                monitor_height = monitor["height"]
                
                # Convert to PIL Image
                img = Image.frombytes("RGB", sct_img.size, sct_img.bgra, "raw", "BGRX")
                
                # Resize if needed to save tokens (keep aspect ratio)
                scale_ratio = 1.0
                if img.width > max_width:
                    scale_ratio = max_width / float(img.width)
                    new_height = int((float(img.height) * float(scale_ratio)))
                    img = img.resize((max_width, new_height), Image.Resampling.LANCZOS)
                
                # Save as JPEG with moderate compression to save context size
                img.save(filepath, "JPEG", quality=80)

                # Persist monitor context for RPA executor boundary checks
                monitor_context = {
                    "monitor_index": monitor_idx,
                    "offset_x": offset_x,
                    "offset_y": offset_y,
                    "width": monitor_width,
                    "height": monitor_height,
                    "right": offset_x + monitor_width,
                    "bottom": offset_y + monitor_height,
                    "scale_ratio": scale_ratio,
                }
                with open(monitor_context_path, 'w') as f:
                    json.dump(monitor_context, f, indent=2)

            # If requested, draw the Set-of-Marks UI anchors
            anchor_summary = []
            if annotate_ui:
                from nanobot.agent.vision.ui_anchors import extract_and_draw_anchors
                from nanobot.config.loader import load_config

                # Load vision config for OCR and YOLO settings
                try:
                    config = load_config()
                    vision_cfg = config.agents.vision
                    ocr_enabled = vision_cfg.ocr_enabled
                    ocr_min_confidence = vision_cfg.ocr_min_confidence
                    uia_threshold = vision_cfg.uia_fallback_threshold
                    yolo_enabled = vision_cfg.yolo_enabled
                    yolo_confidence = vision_cfg.yolo_confidence
                    yolo_model = vision_cfg.yolo_model
                except Exception:
                    ocr_enabled = True
                    ocr_min_confidence = 0.7
                    uia_threshold = 3
                    yolo_enabled = False
                    yolo_confidence = 0.3
                    yolo_model = "gpa-gui-detector"

                # If user explicitly requests OCR, lower the threshold to force it
                if use_ocr:
                    uia_threshold = 999999  # Force OCR regardless of UIA count

                try:
                    print(f"\n[ScreenCapture] Annotating UI elements. Monitor: idx={monitor_idx}, "
                          f"offset=({offset_x},{offset_y}), size={monitor_width}x{monitor_height}")
                    anchor_summary = extract_and_draw_anchors(
                        filepath, filepath, anchors_json_path,
                        offset_x=offset_x,
                        offset_y=offset_y,
                        scale_ratio=scale_ratio,
                        use_ocr_fallback=ocr_enabled or use_ocr,
                        ocr_min_confidence=ocr_min_confidence,
                        uia_fallback_threshold=uia_threshold,
                        monitor_right=offset_x + monitor_width,
                        monitor_bottom=offset_y + monitor_height,
                        use_yolo=yolo_enabled,
                        yolo_confidence=yolo_confidence,
                        yolo_model=yolo_model,
                    )
                    print(f"[ScreenCapture] Detected {len(anchor_summary)} elements total")
                except Exception as e:
                    print(f"\n[ScreenCapture] ERROR in ui_anchors.py: {e}\n")
                    anchor_summary = [f"Failed to annotate UI: {e}"]

            # Keep only the latest 5 screenshots in tmp to avoid disk bloat
            self._cleanup_old_captures()
                
            # Return the special format that loop.py ContextBuilder will intercept
            result_str = f"__IMAGE__:{filepath.resolve()}"
            if annotate_ui and isinstance(anchor_summary, list):
                # Flat index list (traditional)
                summary_text = "\n".join(anchor_summary[:100])
                if len(anchor_summary) > 100:
                    summary_text += f"\n... and {len(anchor_summary) - 100} more."
                
                # Grouped-by-type summary for text LLMs
                grouped_text = self._group_anchors_by_type(anchors_json_path)
                
                result_str = (
                    f"__IMAGE__:{filepath.resolve()} | ANCHORS:\n{summary_text}"
                    f"{grouped_text}"
                )
                
            return result_str
            
        except Exception as e:
            return f"Error capturing screen: {str(e)}"
            
    def _cleanup_old_captures(self) -> None:
        """Keep only the most recent 5 captures."""
        try:
            captures = list(self.tmp_dir.glob("capture_*.jpg"))
            if len(captures) > 5:
                # Sort by modification time, newest first
                captures.sort(key=lambda x: x.stat().st_mtime, reverse=True)
                for old_file in captures[5:]:
                    old_file.unlink(missing_ok=True)
        except Exception:
            pass
