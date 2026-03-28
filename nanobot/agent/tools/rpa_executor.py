"""RPA Executor tool for performing actions on the system UI."""

import time
import platform
import ctypes
from typing import Any, Dict

try:
    import pyautogui
    import pydirectinput
    
    # Force High DPI Awareness on Windows to prevent coordinate drift
    if platform.system() == "Windows":
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(2) # PROCESS_PER_MONITOR_DPI_AWARE
        except Exception:
            try:
                ctypes.windll.user32.SetProcessDPIAware()
            except Exception:
                pass
                
    # Configure safety nets
    pyautogui.FAILSAFE = True  # Move mouse to corner to abort
    pyautogui.PAUSE = 0.1      # Small global pause between actions
    
    HAS_RPA_DEPS = True
except ImportError:
    HAS_RPA_DEPS = False

from nanobot.agent.tools.base import Tool


class RPAExecutorTool(Tool):
    """
    Executes standard RPA (Robotic Process Automation) actions on the screen
    using physical keyboard and mouse emulation.
    """

    name = "rpa"
    description = (
        "Perform physical mouse and keyboard actions on the computer. "
        "Allows clicking, typing, and navigating the system UI autonomously."
    )
    
    parameters = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["click", "double_click", "right_click", "type", "press", "hotkey", "scroll", "wait"],
                "description": "The RPA action to perform."
            },
            "ui_name": {
                "type": "string",
                "description": "RECOMMENDED: The NAME of the UI element to interact with (e.g., 'One', 'Plus', 'Equals', 'Submit'). "
                               "The system will automatically find and click the element by matching its name in the UI anchor data. "
                               "This is the fastest and most reliable method — no screenshot analysis needed."
            },
            "ui_index": {
                "type": "string",
                "description": "The numbered UI anchor index (e.g., '15') from a recent screen_capture with annotate_ui=True. "
                               "Use ui_name instead when you know the element's label."
            },
            "x": {
                "type": "integer",
                "description": "WARNING: DO NOT use this if you have ui_name or ui_index. X coordinate on the screen (for click actions)."
            },
            "y": {
                "type": "integer",
                "description": "WARNING: DO NOT use this if you have ui_name or ui_index. Y coordinate on the screen (for click actions)."
            },
            "text": {
                "type": "string",
                "description": "Text to type out (for 'type' action)."
            },
            "keys": {
                "type": "array",
                "items": {"type": "string"},
                "description": "List of keys (e.g. ['ctrl', 'c']) for 'press' or 'hotkey'."
            },
            "amount": {
                "type": "integer",
                "description": "Amount to scroll (positive for up, negative for down)."
            },
            "wait_after": {
                "type": "number",
                "description": "Seconds to wait after the action completes before returning. Default 1.0.",
                "default": 1.0
            },
            "verify": {
                "type": "boolean",
                "description": "If true, capture a screenshot after the action and ask the VLM to verify "
                               "whether the action succeeded. If it failed, the system retries automatically. "
                               "Use this for critical UI actions where correctness is important.",
                "default": False
            },
            "expected_outcome": {
                "type": "string",
                "description": "Optional description of what the screen should look like after the action. "
                               "Used by the VLM verifier to assess success. E.g. 'The dialog should close'."
            }
        },
        "required": ["action"],
        "additionalProperties": False,
    }

    def __init__(self):
        super().__init__()
        import asyncio
        self._lock = asyncio.Lock()  # Phase 31 Retro: serialize physical device ops

    def _get_vlm_feedback_loop(self):
        """Lazy-create a VLMFeedbackLoop if VLM feedback is enabled.

        Returns (feedback_loop, config) or (None, None).
        """
        try:
            from nanobot.config.loader import get_config
            config = get_config()
            fb_cfg = config.agents.vlm_feedback
            if not fb_cfg.enabled:
                return None, None
            if not (config.agents.vlm.enabled and config.agents.vlm.model):
                return None, None

            vlm_model = config.agents.vlm.model
            p_conf = config.get_provider(vlm_model)
            if not p_conf:
                return None, None

            from nanobot.providers.litellm_provider import LiteLLMProvider
            provider_name = config.get_provider_name(vlm_model)
            provider = LiteLLMProvider(
                api_key=p_conf.api_key,
                api_base=config.get_api_base(vlm_model),
                default_model=vlm_model,
                extra_headers=p_conf.extra_headers,
                provider_name=provider_name,
            )

            from nanobot.agent.vision.vlm_feedback import VLMFeedbackLoop
            return VLMFeedbackLoop(provider=provider, vlm_model=vlm_model), fb_cfg
        except Exception as e:
            print(f"[RPA] VLM feedback init failed: {e}")
            return None, None

    def _load_anchors(self):
        """Load anchors.json from the workspace tmp directory."""
        import json
        from nanobot.config.loader import load_config
        config = load_config()
        anchors_json_path = config.workspace_path / "tmp" / "anchors.json"
        if not anchors_json_path.exists():
            return None, anchors_json_path
        try:
            with open(anchors_json_path, 'r', encoding='utf-8') as f:
                mapping = json.load(f)
            return mapping, anchors_json_path
        except Exception as e:
            print(f"[RPA Debug] ERROR reading anchors JSON: {e}")
            return None, anchors_json_path

    def _load_monitor_context(self) -> dict | None:
        """Load monitor_context.json for boundary checking."""
        import json
        from nanobot.config.loader import load_config
        config = load_config()
        ctx_path = config.workspace_path / "tmp" / "monitor_context.json"
        if not ctx_path.exists():
            return None
        try:
            with open(ctx_path, 'r') as f:
                return json.load(f)
        except Exception:
            return None

    def _check_bounds(self, x: int, y: int) -> str | None:
        """Check if coordinates are within the captured monitor area. Returns warning string or None."""
        ctx = self._load_monitor_context()
        if not ctx:
            return None
        ox, oy = ctx.get("offset_x", 0), ctx.get("offset_y", 0)
        r, b = ctx.get("right", 99999), ctx.get("bottom", 99999)
        if x < ox or x > r or y < oy or y > b:
            return (f"⚠️ WARNING: Target ({x},{y}) is OUTSIDE the captured monitor area "
                    f"(monitor {ctx.get('monitor_index')}: {ox},{oy} → {r},{b}). "
                    f"The click may land on the wrong screen.")
        return None

    def _find_by_name(self, mapping: dict, target_name: str) -> tuple:
        """
        Find a UI element in anchors mapping by name.
        
        Matching priority:
        1. Exact match
        2. Case-insensitive match
        3. Substring/contains match (case-insensitive)
        
        Returns: (index, element_dict) or (None, None) if not found.
        """
        target_lower = target_name.lower().strip()
        
        # Don't match empty queries
        if not target_lower:
            return None, None
        
        # Pass 1: Exact match
        for idx, el in mapping.items():
            if el.get("name", "") == target_name:
                return idx, el
        
        # Pass 2: Case-insensitive exact match
        for idx, el in mapping.items():
            if el.get("name", "").lower() == target_lower:
                return idx, el
        
        # Pass 3: Substring/contains match (target is part of name)
        for idx, el in mapping.items():
            el_name_lower = el.get("name", "").lower()
            if not el_name_lower:  # Skip unnamed elements
                continue
            if target_lower in el_name_lower:
                return idx, el
        
        return None, None

    async def execute(self, **kwargs) -> str:
        async with self._lock:
            return await self._execute_impl(**kwargs)

    async def _execute_impl(self, **kwargs) -> str:
        if not HAS_RPA_DEPS:
            return "Error: Missing dependencies for RPA. Please run: pip install pyautogui pydirectinput"

        action = kwargs.get("action")
        x = kwargs.get("x")
        y = kwargs.get("y")
        text = kwargs.get("text")
        keys = kwargs.get("keys", [])
        amount = kwargs.get("amount", 0)
        ui_index = kwargs.get("ui_index")
        ui_name = kwargs.get("ui_name")
        wait_after = float(kwargs.get("wait_after", 1.0))
        verify = kwargs.get("verify", False)
        expected_outcome = kwargs.get("expected_outcome", "")

        # Resolve verify flag from string if needed
        if isinstance(verify, str):
            verify = verify.lower() == "true"

        try:
            if action in ["click", "double_click", "right_click"]:
                result_prefix = ""
                
                mapping, anchors_json_path = self._load_anchors()
                
                # Priority: ui_name > ui_index > x,y
                # Resolve ui_name to coordinates (highest priority — fast text matching)
                if ui_name and mapping:
                    ui_name_clean = str(ui_name).strip('"\'')
                    print(f"[RPA Debug] Searching for UI element by name: '{ui_name_clean}'")
                    print(f"[RPA Debug] Loaded {len(mapping)} anchors from JSON.")
                    
                    found_idx, found_el = self._find_by_name(mapping, ui_name_clean)
                    if found_idx and found_el:
                        center = found_el["center"]
                        x, y = int(center[0]), int(center[1])
                        el_name = found_el.get('name', '?')
                        el_type = found_el.get('type', '?')
                        el_source = found_el.get('source', 'uia')
                        source_label = 'via OCR' if el_source == 'ocr' else 'via UIAutomation'
                        print(f"[RPA Debug] Found Match! Name '{ui_name_clean}' -> Index {found_idx}, "
                              f"Name: '{el_name}', Type: '{el_type}', Source: {source_label}. "
                              f"Target Coordinates: ({x}, {y})")
                        result_prefix = f"[UI Name Match: '{el_name}' (index {found_idx}, {source_label})] "
                    else:
                        # List available elements to help the LLM
                        available = [f"  {idx}: '{el.get('name', '')}' ({el.get('type', '')})" 
                                     for idx, el in list(mapping.items())[:30] if el.get('name')]
                        available_str = "\n".join(available)
                        print(f"[RPA Debug] No match found for name '{ui_name_clean}'.")
                        return (f"Error: No UI element found matching name '{ui_name_clean}'. "
                                f"Available elements (first 30):\n{available_str}")
                
                elif ui_name and not mapping:
                    return ("Error: ui_name was provided but no anchors.json found. "
                            "Run screen_capture with annotate_ui=true first to detect UI elements.")
                
                # Resolve ui_index to coordinates (fallback)
                elif ui_index:
                    if not mapping:
                        print(f"[RPA Debug] ERROR: anchors.json file does not exist.")
                        return "Error: No recent anchors found. Did you run screen_capture with annotate_ui=True?"
                    
                    ui_index = str(ui_index).strip('"\'')
                    print(f"[RPA Debug] Attempting to click UI Anchor Index: {ui_index}")
                    print(f"[RPA Debug] Loaded {len(mapping)} anchors from JSON.")
                    
                    if str(ui_index) in mapping:
                        center = mapping[str(ui_index)]["center"]
                        x, y = int(center[0]), int(center[1])
                        el_name = mapping[str(ui_index)]['name']
                        el_type = mapping[str(ui_index)]['type']
                        print(f"[RPA Debug] Found Match! Index {ui_index} -> Name: '{el_name}', Type: '{el_type}'. Target Coordinates: ({x}, {y})")
                        result_prefix = f"[UI Anchor {ui_index}: {el_name}] "
                    else:
                        print(f"[RPA Debug] ERROR: Index {ui_index} NOT FOUND in anchors.json.")
                        return f"Error: UI index {ui_index} not found in recent anchors."
                
                # Reject raw x,y if anchors are available
                elif x is not None and y is not None and mapping:
                    print(f"[RPA Debug] REJECTING raw x/y because anchors are available.")
                    return ("Error: UI anchors are available. Use 'ui_name' (recommended) or 'ui_index' "
                            "instead of raw x/y coordinates to avoid errors.")
                
                if x is None or y is None:
                    print(f"[RPA Debug] ERROR: Target coordinates are missing (action: {action}).")
                    return (f"Error: Action '{action}' requires ui_name, ui_index, or (x, y) coordinates. "
                            f"Recommended: use ui_name with the element's label text.")
                
                # Multi-monitor boundary check
                bounds_warning = self._check_bounds(x, y)
                if bounds_warning:
                    print(f"[RPA Debug] {bounds_warning}")
                    result_prefix = f"{bounds_warning}\n{result_prefix}" if result_prefix else f"{bounds_warning}\n"
                
                print(f"[RPA Debug] Executing mouse movement to ({x}, {y}) over 0.5s smoothly...")
                # Move to location smoothly (0.5 seconds)
                pyautogui.moveTo(x, y, duration=0.5)
                
                print(f"[RPA Debug] Performing mouse action: '{action}' at ({x}, {y})...")
                if action == "click":
                    pyautogui.click()
                elif action == "double_click":
                    pyautogui.doubleClick()
                elif action == "right_click":
                    pyautogui.rightClick()
                    
                result = f"{result_prefix}Successfully performed {action} at ({x}, {y})."

            elif action == "type":
                if not text:
                    return "Error: Action 'type' requires 'text' parameter."
                # Use typewrite for strings. Does not handle non-ascii perfectly, 
                # but standard pyautogui usage applies.
                import keyboard # sometimes needed if pydirectinput fails
                # using pyautogui.write is safer for ascii
                pyautogui.write(str(text), interval=0.05)
                result = f"Successfully typed: '{text}'"

            elif action == "press":
                if not keys:
                    return "Error: Action 'press' requires 'keys' array."
                for k in keys:
                    pyautogui.press(k)
                result = f"Successfully pressed keys: {keys}"

            elif action == "hotkey":
                if not keys or len(keys) < 2:
                    return "Error: Action 'hotkey' requires 'keys' array with at least 2 keys (e.g. ['ctrl', 'c'])."
                pyautogui.hotkey(*keys)
                result = f"Successfully executed hotkey: {keys}"

            elif action == "scroll":
                if amount == 0:
                    return "Error: Action 'scroll' requires non-zero 'amount'."
                pyautogui.scroll(amount)
                result = f"Successfully scrolled by {amount}."
                
            elif action == "wait":
                result = "Waiting action executed."

            else:
                return f"Error: Unknown action '{action}'"

            # Always wait afterwards to let the UI settle before capturing screen again
            if wait_after > 0:
                time.sleep(wait_after)
                result += f" Waited {wait_after} seconds."

            # ── VLM Feedback Loop: post-action verification ──
            if verify and action in ("click", "double_click", "right_click", "type"):
                result = await self._run_vlm_verification(
                    result, action, ui_name or ui_index or f"({x},{y})",
                    expected_outcome,
                )

            return result

        except pyautogui.FailSafeException:
            return "Error: PyAutoGUI FailSafe triggered (mouse moved to corner). Action aborted for safety."
        except Exception as e:
            return f"Error executing RPA action '{action}': {str(e)}"

    async def _run_vlm_verification(
        self,
        action_result: str,
        action: str,
        target: str,
        expected_outcome: str,
    ) -> str:
        """Run VLM-based post-action verification if configured.

        Returns the original result with verification summary appended.
        """
        feedback_loop, fb_cfg = self._get_vlm_feedback_loop()
        if not feedback_loop or not fb_cfg:
            return action_result + "\n⚠️ VLM verification requested but not configured."

        import asyncio
        from pathlib import Path
        from nanobot.config.loader import get_config

        config = get_config()
        workspace = config.workspace_path

        # Find the most recent screenshot as "before" image
        tmp_dir = workspace / "tmp"
        captures = sorted(tmp_dir.glob("capture_*.jpg"), key=lambda p: p.stat().st_mtime)
        if not captures:
            return action_result + "\n⚠️ VLM verification skipped: no prior screenshot found."
        before_screenshot = captures[-1]

        action_desc = f"{action} on '{target}'"
        max_retries = fb_cfg.max_retries

        for attempt in range(1, max_retries + 1):
            # Wait for UI to settle
            await asyncio.sleep(fb_cfg.verification_delay)

            try:
                vr, after_path = await feedback_loop.capture_and_verify(
                    action_description=action_desc,
                    before_screenshot=before_screenshot,
                    workspace=workspace,
                    expected_outcome=expected_outcome,
                )
            except Exception as e:
                return action_result + f"\n⚠️ VLM verification error: {e}"

            if vr.success:
                return (
                    action_result
                    + f"\n✅ VLM Verified (attempt {attempt}): {vr.explanation}"
                )

            # Verification failed
            correction = vr.suggested_correction or "no suggestion"
            print(
                f"[RPA] VLM verification failed (attempt {attempt}/{max_retries}): "
                f"{vr.explanation} | suggestion: {correction}"
            )

            if attempt >= max_retries:
                return (
                    action_result
                    + f"\n❌ VLM Verification failed after {max_retries} attempts: "
                    + f"{vr.explanation}"
                    + (f"\n💡 Suggestion: {correction}" if vr.suggested_correction else "")
                )

            # Update "before" to current "after" for next attempt
            before_screenshot = after_path

        return action_result  # Fallback (should not reach here)
