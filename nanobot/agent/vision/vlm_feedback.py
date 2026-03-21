"""Vision-Language Feedback Loop for self-correcting RPA.

After an RPA action, captures a new screenshot and asks the VLM to compare
before/after states.  If the action did not produce the expected outcome,
returns a structured correction hint so the agent can retry.

Phase 21E Feature Enhancement.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from loguru import logger

if TYPE_CHECKING:
    from nanobot.providers.base import LLMProvider


# ── Verification prompt template ─────────────────────────────────────────

_VERIFY_SYSTEM_PROMPT = (
    "You are a UI verification assistant.  You will receive two screenshots: "
    "a BEFORE image (before an RPA action) and an AFTER image (after the action). "
    "Your job is to determine whether the intended action succeeded.\n\n"
    "Respond ONLY with a valid JSON object — no markdown fences, no explanation "
    "outside the JSON.  Schema:\n"
    '{"success": true/false, "explanation": "...", "suggested_correction": "..." or null}\n\n'
    "Rules:\n"
    "- success=true  → the UI changed as expected.\n"
    "- success=false → the UI did NOT change, or an error/popup appeared.\n"
    "- suggested_correction → if failed, a short hint (e.g. 'click the OK button "
    "on the error dialog first').\n"
    "- Keep explanations concise (≤80 chars)."
)


@dataclass
class VerificationResult:
    """Outcome of a VLM-based post-action verification."""

    success: bool
    explanation: str
    suggested_correction: str | None = None
    attempt: int = 1


@dataclass
class FeedbackLoopResult:
    """Aggregate result of the full feedback loop (possibly multiple retries)."""

    final_success: bool
    attempts: list[VerificationResult] = field(default_factory=list)
    after_screenshot: Path | None = None

    @property
    def summary(self) -> str:
        """Human-readable summary for inclusion in tool output."""
        if self.final_success:
            return (
                f"✅ VLM Verification passed (attempt {len(self.attempts)}): "
                f"{self.attempts[-1].explanation}"
            )
        lines = [f"❌ VLM Verification failed after {len(self.attempts)} attempt(s):"]
        for v in self.attempts:
            tag = "✅" if v.success else "❌"
            lines.append(f"  {tag} Attempt {v.attempt}: {v.explanation}")
            if v.suggested_correction:
                lines.append(f"     💡 Suggestion: {v.suggested_correction}")
        return "\n".join(lines)


class VLMFeedbackLoop:
    """Stateless utility that verifies RPA actions via VLM comparison.

    Usage::

        loop = VLMFeedbackLoop(provider, vlm_model)
        result = await loop.verify_action(
            action_description="Clicked 'Submit' button",
            before_screenshot=Path("before.jpg"),
            after_screenshot=Path("after.jpg"),
        )
    """

    def __init__(
        self,
        provider: LLMProvider,
        vlm_model: str,
    ) -> None:
        self._provider = provider
        self._vlm_model = vlm_model

    # ── Public API ────────────────────────────────────────────────────

    async def verify_action(
        self,
        action_description: str,
        before_screenshot: Path,
        after_screenshot: Path,
        expected_outcome: str = "",
    ) -> VerificationResult:
        """Ask the VLM whether *action_description* succeeded.

        Args:
            action_description: Human-readable description of what was done.
            before_screenshot:  Path to the screenshot taken before the action.
            after_screenshot:   Path to the screenshot taken after the action.
            expected_outcome:   Optional hint about what success looks like.

        Returns:
            A ``VerificationResult``.
        """
        user_msg = self._build_user_message(
            action_description, before_screenshot, after_screenshot, expected_outcome,
        )
        messages = [
            {"role": "system", "content": _VERIFY_SYSTEM_PROMPT},
            user_msg,
        ]

        try:
            response = await self._provider.chat(
                messages=messages,
                tools=[],
                model=self._vlm_model,
                temperature=0.1,   # low creativity for factual verification
                max_tokens=512,
            )

            return self._parse_response(response.content or "")

        except Exception as e:
            logger.warning(f"VLM verification call failed: {e}")
            # On VLM error, assume success to avoid blocking the workflow
            return VerificationResult(
                success=True,
                explanation=f"VLM verification skipped (error: {e})",
            )

    async def capture_and_verify(
        self,
        action_description: str,
        before_screenshot: Path,
        workspace: Path,
        expected_outcome: str = "",
        monitor: int = 1,
    ) -> tuple[VerificationResult, Path]:
        """Capture a fresh screenshot, then verify.

        Returns (result, after_screenshot_path).
        """
        after_path = self._capture_raw(workspace, monitor)
        result = await self.verify_action(
            action_description, before_screenshot, after_path, expected_outcome,
        )
        return result, after_path

    # ── Internals ─────────────────────────────────────────────────────

    @staticmethod
    def _capture_raw(workspace: Path, monitor: int = 1) -> Path:
        """Take a plain screenshot (no annotation) for verification.

        Returns the saved file path.
        """
        try:
            import mss
            from PIL import Image
        except ImportError as exc:
            raise RuntimeError("mss/Pillow not installed") from exc

        tmp_dir = workspace / "tmp"
        tmp_dir.mkdir(parents=True, exist_ok=True)
        filename = f"verify_{int(time.time() * 1000)}.jpg"
        filepath = tmp_dir / filename

        with mss.mss() as sct:
            if monitor >= len(sct.monitors):
                monitor = 1
            mon = sct.monitors[monitor]
            sct_img = sct.grab(mon)
            img = Image.frombytes("RGB", sct_img.size, sct_img.bgra, "raw", "BGRX")

            # Resize to a reasonable size for VLM consumption
            max_width = 1280
            if img.width > max_width:
                ratio = max_width / float(img.width)
                new_h = int(img.height * ratio)
                img = img.resize((max_width, new_h), Image.Resampling.LANCZOS)

            img.save(filepath, "JPEG", quality=80)

        return filepath

    def _build_user_message(
        self,
        action_description: str,
        before_path: Path,
        after_path: Path,
        expected_outcome: str,
    ) -> dict:
        """Build a multi-modal user message with before/after images."""
        import base64

        def _encode(path: Path) -> str:
            with open(path, "rb") as f:
                return base64.b64encode(f.read()).decode("utf-8")

        text = f"Action performed: {action_description}"
        if expected_outcome:
            text += f"\nExpected outcome: {expected_outcome}"
        text += "\n\nPlease compare the BEFORE and AFTER screenshots and verify."

        return {
            "role": "user",
            "content": [
                {"type": "text", "text": text},
                {
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:image/jpeg;base64,{_encode(before_path)}",
                    },
                },
                {
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:image/jpeg;base64,{_encode(after_path)}",
                    },
                },
            ],
        }

    @staticmethod
    def _parse_response(text: str) -> VerificationResult:
        """Parse VLM JSON response into a VerificationResult."""
        # Strip markdown fences if present
        cleaned = text.strip()
        if cleaned.startswith("```"):
            lines = cleaned.split("\n")
            lines = [l for l in lines if not l.strip().startswith("```")]
            cleaned = "\n".join(lines).strip()

        # Strip <think> tags if present (reasoning models)
        import re
        cleaned = re.sub(r"<think>.*?</think>", "", cleaned, flags=re.DOTALL).strip()

        try:
            data = json.loads(cleaned)
            return VerificationResult(
                success=bool(data.get("success", True)),
                explanation=str(data.get("explanation", ""))[:200],
                suggested_correction=data.get("suggested_correction"),
            )
        except (json.JSONDecodeError, TypeError):
            # Try json_repair as fallback
            try:
                import json_repair
                data = json_repair.loads(cleaned)
                return VerificationResult(
                    success=bool(data.get("success", True)),
                    explanation=str(data.get("explanation", ""))[:200],
                    suggested_correction=data.get("suggested_correction"),
                )
            except Exception:
                pass

            # If VLM returned non-JSON, try heuristic
            text_lower = text.lower()
            if any(w in text_lower for w in ("fail", "error", "not change", "没有", "失败")):
                return VerificationResult(
                    success=False,
                    explanation=text[:200],
                )
            return VerificationResult(
                success=True,
                explanation=text[:200] or "VLM returned unparseable response, assuming success",
            )
