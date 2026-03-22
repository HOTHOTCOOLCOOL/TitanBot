"""Tests for Phase 21E: Vision-Language Feedback Loop.

Covers:
- VLMFeedbackConfig schema
- VerificationResult / FeedbackLoopResult dataclasses
- VLMFeedbackLoop prompt building and response parsing
- RPAExecutorTool verify flag integration
- Retry logic
- Graceful degradation when VLM is not configured
"""

import json
import sys
import asyncio
from pathlib import Path
from dataclasses import asdict
from unittest.mock import AsyncMock, MagicMock, patch, PropertyMock

import pytest

# Ensure pyautogui/pydirectinput mocks exist before importing RPA tool
sys.modules.setdefault("pyautogui", MagicMock())
sys.modules.setdefault("pydirectinput", MagicMock())


# ── Config tests ──────────────────────────────────────────────────────────


class TestVLMFeedbackConfig:
    """Test VLMFeedbackConfig schema defaults and serialization."""

    def test_defaults(self):
        from nanobot.config.schema import VLMFeedbackConfig

        cfg = VLMFeedbackConfig()
        assert cfg.enabled is False
        assert cfg.max_retries == 3
        assert cfg.verification_delay == 1.0
        assert cfg.auto_verify_actions == ["click", "double_click", "type"]

    def test_custom_values(self):
        from nanobot.config.schema import VLMFeedbackConfig

        cfg = VLMFeedbackConfig(enabled=True, max_retries=5, verification_delay=2.0)
        assert cfg.enabled is True
        assert cfg.max_retries == 5
        assert cfg.verification_delay == 2.0

    def test_agents_config_has_vlm_feedback(self):
        from nanobot.config.schema import AgentsConfig

        cfg = AgentsConfig()
        assert hasattr(cfg, "vlm_feedback")
        assert cfg.vlm_feedback.enabled is False

    def test_full_config_has_vlm_feedback(self):
        from nanobot.config.schema import Config

        cfg = Config()
        assert hasattr(cfg.agents, "vlm_feedback")
        assert cfg.agents.vlm_feedback.max_retries == 3


# ── Dataclass tests ───────────────────────────────────────────────────────


class TestVerificationResult:
    """Test VerificationResult dataclass."""

    def test_creation_success(self):
        from nanobot.agent.vision.vlm_feedback import VerificationResult

        vr = VerificationResult(success=True, explanation="Button was clicked")
        assert vr.success is True
        assert vr.explanation == "Button was clicked"
        assert vr.suggested_correction is None
        assert vr.attempt == 1

    def test_creation_failure(self):
        from nanobot.agent.vision.vlm_feedback import VerificationResult

        vr = VerificationResult(
            success=False,
            explanation="Dialog did not close",
            suggested_correction="Click OK button first",
            attempt=2,
        )
        assert vr.success is False
        assert vr.attempt == 2
        assert vr.suggested_correction == "Click OK button first"


class TestFeedbackLoopResult:
    """Test FeedbackLoopResult dataclass."""

    def test_summary_success(self):
        from nanobot.agent.vision.vlm_feedback import (
            FeedbackLoopResult,
            VerificationResult,
        )

        result = FeedbackLoopResult(
            final_success=True,
            attempts=[VerificationResult(success=True, explanation="All good")],
        )
        assert "✅" in result.summary
        assert "All good" in result.summary

    def test_summary_failure_multiple_attempts(self):
        from nanobot.agent.vision.vlm_feedback import (
            FeedbackLoopResult,
            VerificationResult,
        )

        result = FeedbackLoopResult(
            final_success=False,
            attempts=[
                VerificationResult(
                    success=False,
                    explanation="No change",
                    suggested_correction="Try again",
                    attempt=1,
                ),
                VerificationResult(
                    success=False,
                    explanation="Still no change",
                    attempt=2,
                ),
            ],
        )
        summary = result.summary
        assert "❌" in summary
        assert "2 attempt(s)" in summary
        assert "Try again" in summary


# ── VLMFeedbackLoop parsing tests ─────────────────────────────────────────


class TestVLMFeedbackParsing:
    """Test VLMFeedbackLoop._parse_response()."""

    def test_parse_success_json(self):
        from nanobot.agent.vision.vlm_feedback import VLMFeedbackLoop

        text = '{"success": true, "explanation": "Button clicked successfully"}'
        result = VLMFeedbackLoop._parse_response(text)
        assert result.success is True
        assert "Button clicked" in result.explanation

    def test_parse_failure_json(self):
        from nanobot.agent.vision.vlm_feedback import VLMFeedbackLoop

        text = json.dumps({
            "success": False,
            "explanation": "Dialog still visible",
            "suggested_correction": "Click the X button",
        })
        result = VLMFeedbackLoop._parse_response(text)
        assert result.success is False
        assert result.suggested_correction == "Click the X button"

    def test_parse_json_with_markdown_fences(self):
        from nanobot.agent.vision.vlm_feedback import VLMFeedbackLoop

        text = '```json\n{"success": true, "explanation": "OK"}\n```'
        result = VLMFeedbackLoop._parse_response(text)
        assert result.success is True

    def test_parse_json_with_think_tags(self):
        from nanobot.agent.vision.vlm_feedback import VLMFeedbackLoop

        text = '<think>Let me analyze...</think>{"success": false, "explanation": "No change"}'
        result = VLMFeedbackLoop._parse_response(text)
        assert result.success is False

    def test_parse_heuristic_failure(self):
        from nanobot.agent.vision.vlm_feedback import VLMFeedbackLoop

        text = "The button did not change, the action seems to have failed"
        result = VLMFeedbackLoop._parse_response(text)
        assert result.success is False

    def test_parse_heuristic_success(self):
        from nanobot.agent.vision.vlm_feedback import VLMFeedbackLoop

        text = "Something happened but we cannot parse this"
        result = VLMFeedbackLoop._parse_response(text)
        assert result.success is True  # Assume success on unparseable

    def test_parse_empty_string(self):
        from nanobot.agent.vision.vlm_feedback import VLMFeedbackLoop

        result = VLMFeedbackLoop._parse_response("")
        assert result.success is True  # Empty = assume success

    def test_parse_explanation_truncated(self):
        from nanobot.agent.vision.vlm_feedback import VLMFeedbackLoop

        long_explanation = "x" * 500
        text = json.dumps({"success": True, "explanation": long_explanation})
        result = VLMFeedbackLoop._parse_response(text)
        assert len(result.explanation) <= 200


# ── VLMFeedbackLoop.verify_action() tests ─────────────────────────────────


class TestVLMFeedbackVerify:
    """Test VLMFeedbackLoop.verify_action() with mocked provider."""

    @pytest.fixture
    def mock_provider(self):
        provider = MagicMock()
        provider.chat = AsyncMock()
        return provider

    @pytest.fixture
    def feedback_loop(self, mock_provider):
        from nanobot.agent.vision.vlm_feedback import VLMFeedbackLoop

        return VLMFeedbackLoop(provider=mock_provider, vlm_model="test-vlm")

    @pytest.mark.asyncio
    async def test_verify_success(self, feedback_loop, mock_provider, tmp_path):
        """Successful verification returns success=True."""
        from nanobot.providers.base import LLMResponse

        mock_provider.chat.return_value = LLMResponse(
            content='{"success": true, "explanation": "Button was clicked"}',
            tool_calls=[],
            finish_reason="stop",
        )

        before = tmp_path / "before.jpg"
        after = tmp_path / "after.jpg"
        before.write_bytes(b"\xff\xd8\xff\xe0test_before")
        after.write_bytes(b"\xff\xd8\xff\xe0test_after")

        result = await feedback_loop.verify_action(
            action_description="click Submit",
            before_screenshot=before,
            after_screenshot=after,
        )

        assert result.success is True
        mock_provider.chat.assert_called_once()

        # Verify the prompt includes before/after images
        call_args = mock_provider.chat.call_args
        messages = call_args.kwargs["messages"]
        assert messages[0]["role"] == "system"
        assert messages[1]["role"] == "user"
        # User message should be multi-modal with images
        content = messages[1]["content"]
        assert isinstance(content, list)
        assert len(content) == 3  # text + 2 images

    @pytest.mark.asyncio
    async def test_verify_failure(self, feedback_loop, mock_provider, tmp_path):
        """Failed verification returns success=False with correction."""
        from nanobot.providers.base import LLMResponse

        mock_provider.chat.return_value = LLMResponse(
            content=json.dumps({
                "success": False,
                "explanation": "Nothing changed",
                "suggested_correction": "Try clicking the larger button",
            }),
            tool_calls=[],
            finish_reason="stop",
        )

        before = tmp_path / "before.jpg"
        after = tmp_path / "after.jpg"
        before.write_bytes(b"\xff\xd8\xff\xe0test")
        after.write_bytes(b"\xff\xd8\xff\xe0test")

        result = await feedback_loop.verify_action(
            action_description="click Submit",
            before_screenshot=before,
            after_screenshot=after,
        )

        assert result.success is False
        assert result.suggested_correction == "Try clicking the larger button"

    @pytest.mark.asyncio
    async def test_verify_vlm_error_assumes_success(
        self, feedback_loop, mock_provider, tmp_path,
    ):
        """VLM call error should assume success to avoid blocking."""
        mock_provider.chat.side_effect = RuntimeError("VLM unavailable")

        before = tmp_path / "before.jpg"
        after = tmp_path / "after.jpg"
        before.write_bytes(b"\xff\xd8\xff\xe0test")
        after.write_bytes(b"\xff\xd8\xff\xe0test")

        result = await feedback_loop.verify_action(
            action_description="click",
            before_screenshot=before,
            after_screenshot=after,
        )

        assert result.success is True  # Graceful: assume success
        assert "error" in result.explanation.lower()

    @pytest.mark.asyncio
    async def test_verify_with_expected_outcome(
        self, feedback_loop, mock_provider, tmp_path,
    ):
        """Expected outcome should be included in the prompt."""
        from nanobot.providers.base import LLMResponse

        mock_provider.chat.return_value = LLMResponse(
            content='{"success": true, "explanation": "Dialog closed"}',
            tool_calls=[],
            finish_reason="stop",
        )

        before = tmp_path / "before.jpg"
        after = tmp_path / "after.jpg"
        before.write_bytes(b"\xff\xd8\xff\xe0test")
        after.write_bytes(b"\xff\xd8\xff\xe0test")

        await feedback_loop.verify_action(
            action_description="click OK",
            before_screenshot=before,
            after_screenshot=after,
            expected_outcome="The dialog should close",
        )

        call_args = mock_provider.chat.call_args
        messages = call_args.kwargs["messages"]
        user_content = messages[1]["content"]
        text_block = user_content[0]["text"]
        assert "The dialog should close" in text_block


# ── RPAExecutorTool verify integration tests ──────────────────────────────


class TestRPAExecutorVerify:
    """Test RPAExecutorTool with verify parameter."""

    @pytest.fixture
    def tool(self):
        from nanobot.agent.tools.rpa_executor import RPAExecutorTool

        return RPAExecutorTool()

    @pytest.mark.asyncio
    async def test_verify_false_no_vlm_call(self, tool):
        """Default verify=False should not trigger VLM verification."""
        with patch.object(tool, "_load_anchors") as mock_load, \
             patch("pyautogui.moveTo"), \
             patch("pyautogui.click"):
            mock_load.return_value = (
                {"1": {"name": "OK", "type": "Button", "bbox": [0, 0, 100, 50], "center": [50, 25]}},
                Path("/fake/anchors.json"),
            )

            result = await tool.execute(action="click", ui_name="OK")

            assert "VLM" not in result
            assert "Successfully performed click" in result

    @pytest.mark.asyncio
    async def test_verify_true_not_configured(self, tool):
        """verify=True but VLM feedback not configured → warning."""
        with patch.object(tool, "_load_anchors") as mock_load, \
             patch("pyautogui.moveTo"), \
             patch("pyautogui.click"), \
             patch.object(tool, "_get_vlm_feedback_loop", return_value=(None, None)):
            mock_load.return_value = (
                {"1": {"name": "OK", "type": "Button", "bbox": [0, 0, 100, 50], "center": [50, 25]}},
                Path("/fake/anchors.json"),
            )

            result = await tool.execute(action="click", ui_name="OK", verify=True)

            assert "not configured" in result

    @pytest.mark.asyncio
    async def test_verify_true_success(self, tool, tmp_path):
        """verify=True with successful VLM verification."""
        from nanobot.agent.vision.vlm_feedback import VLMFeedbackLoop, VerificationResult
        from nanobot.config.schema import VLMFeedbackConfig

        mock_loop = MagicMock(spec=VLMFeedbackLoop)
        mock_loop.capture_and_verify = AsyncMock(return_value=(
            VerificationResult(success=True, explanation="UI changed correctly"),
            tmp_path / "after.jpg",
        ))
        mock_cfg = VLMFeedbackConfig(enabled=True, max_retries=3, verification_delay=0.0)

        # Create a fake before screenshot
        fake_workspace = tmp_path / "workspace"
        fake_tmp = fake_workspace / "tmp"
        fake_tmp.mkdir(parents=True)
        before_img = fake_tmp / "capture_1000.jpg"
        before_img.write_bytes(b"fake_jpg")

        with patch.object(tool, "_load_anchors") as mock_load, \
             patch("pyautogui.moveTo"), \
             patch("pyautogui.click"), \
             patch.object(tool, "_get_vlm_feedback_loop", return_value=(mock_loop, mock_cfg)), \
             patch("nanobot.config.loader.get_config") as mock_config:
            mock_load.return_value = (
                {"1": {"name": "OK", "type": "Button", "bbox": [0, 0, 100, 50], "center": [50, 25]}},
                Path("/fake/anchors.json"),
            )
            mock_config.return_value = MagicMock(workspace_path=fake_workspace)

            result = await tool.execute(action="click", ui_name="OK", verify=True)

            assert "✅ VLM Verified" in result
            assert "UI changed correctly" in result
            mock_loop.capture_and_verify.assert_called_once()

    @pytest.mark.asyncio
    async def test_verify_true_failure_with_suggestion(self, tool, tmp_path):
        """verify=True with all retries failing returns failure + suggestion."""
        from nanobot.agent.vision.vlm_feedback import VLMFeedbackLoop, VerificationResult
        from nanobot.config.schema import VLMFeedbackConfig

        mock_loop = MagicMock(spec=VLMFeedbackLoop)
        after_img = tmp_path / "after.jpg"
        after_img.write_bytes(b"fake")
        mock_loop.capture_and_verify = AsyncMock(return_value=(
            VerificationResult(
                success=False,
                explanation="Nothing changed",
                suggested_correction="Close popup first",
            ),
            after_img,
        ))
        mock_cfg = VLMFeedbackConfig(enabled=True, max_retries=2, verification_delay=0.0)

        fake_workspace = tmp_path / "workspace"
        fake_tmp = fake_workspace / "tmp"
        fake_tmp.mkdir(parents=True)
        (fake_tmp / "capture_1000.jpg").write_bytes(b"fake_jpg")

        with patch.object(tool, "_load_anchors") as mock_load, \
             patch("pyautogui.moveTo"), \
             patch("pyautogui.click"), \
             patch.object(tool, "_get_vlm_feedback_loop", return_value=(mock_loop, mock_cfg)), \
             patch("nanobot.config.loader.get_config") as mock_config:
            mock_load.return_value = (
                {"1": {"name": "OK", "type": "Button", "bbox": [0, 0, 100, 50], "center": [50, 25]}},
                Path("/fake/anchors.json"),
            )
            mock_config.return_value = MagicMock(workspace_path=fake_workspace)

            result = await tool.execute(action="click", ui_name="OK", verify=True)

            assert "❌" in result
            assert "2 attempts" in result
            assert "Close popup first" in result
            assert mock_loop.capture_and_verify.call_count == 2

    @pytest.mark.asyncio
    async def test_verify_retry_success_second_attempt(self, tool, tmp_path):
        """Verification fails first time but succeeds on retry."""
        from nanobot.agent.vision.vlm_feedback import VLMFeedbackLoop, VerificationResult
        from nanobot.config.schema import VLMFeedbackConfig

        mock_loop = MagicMock(spec=VLMFeedbackLoop)
        after1 = tmp_path / "after1.jpg"
        after2 = tmp_path / "after2.jpg"
        after1.write_bytes(b"fake")
        after2.write_bytes(b"fake")

        mock_loop.capture_and_verify = AsyncMock(side_effect=[
            (VerificationResult(success=False, explanation="Not yet"), after1),
            (VerificationResult(success=True, explanation="Now it worked"), after2),
        ])
        mock_cfg = VLMFeedbackConfig(enabled=True, max_retries=3, verification_delay=0.0)

        fake_workspace = tmp_path / "workspace"
        fake_tmp = fake_workspace / "tmp"
        fake_tmp.mkdir(parents=True)
        (fake_tmp / "capture_1000.jpg").write_bytes(b"fake_jpg")

        with patch.object(tool, "_load_anchors") as mock_load, \
             patch("pyautogui.moveTo"), \
             patch("pyautogui.click"), \
             patch.object(tool, "_get_vlm_feedback_loop", return_value=(mock_loop, mock_cfg)), \
             patch("nanobot.config.loader.get_config") as mock_config:
            mock_load.return_value = (
                {"1": {"name": "OK", "type": "Button", "bbox": [0, 0, 100, 50], "center": [50, 25]}},
                Path("/fake/anchors.json"),
            )
            mock_config.return_value = MagicMock(workspace_path=fake_workspace)

            result = await tool.execute(action="click", ui_name="OK", verify=True)

            assert "✅ VLM Verified (attempt 2)" in result
            assert mock_loop.capture_and_verify.call_count == 2

    @pytest.mark.asyncio
    async def test_verify_string_true(self, tool):
        """verify='true' (string) should be treated as True."""
        with patch.object(tool, "_load_anchors") as mock_load, \
             patch("pyautogui.moveTo"), \
             patch("pyautogui.click"), \
             patch.object(tool, "_get_vlm_feedback_loop", return_value=(None, None)):
            mock_load.return_value = (
                {"1": {"name": "OK", "type": "Button", "bbox": [0, 0, 100, 50], "center": [50, 25]}},
                Path("/fake/anchors.json"),
            )

            result = await tool.execute(action="click", ui_name="OK", verify="true")

            # Should attempt verification (but not configured)
            assert "not configured" in result

    @pytest.mark.asyncio
    async def test_verify_not_on_scroll_action(self, tool):
        """Verify flag is ignored for non-verifiable actions like scroll."""
        result = await tool.execute(action="scroll", amount=3, verify=True)

        assert "VLM" not in result
        assert "Successfully scrolled" in result

    @pytest.mark.asyncio
    async def test_no_prior_screenshot(self, tool, tmp_path):
        """verify=True but no prior screenshot → skip verification."""
        from nanobot.agent.vision.vlm_feedback import VLMFeedbackLoop
        from nanobot.config.schema import VLMFeedbackConfig

        mock_loop = MagicMock(spec=VLMFeedbackLoop)
        mock_cfg = VLMFeedbackConfig(enabled=True, max_retries=3, verification_delay=0.0)

        fake_workspace = tmp_path / "workspace"
        fake_tmp = fake_workspace / "tmp"
        fake_tmp.mkdir(parents=True)
        # No capture_*.jpg files

        with patch.object(tool, "_load_anchors") as mock_load, \
             patch("pyautogui.moveTo"), \
             patch("pyautogui.click"), \
             patch.object(tool, "_get_vlm_feedback_loop", return_value=(mock_loop, mock_cfg)), \
             patch("nanobot.config.loader.get_config") as mock_config:
            mock_load.return_value = (
                {"1": {"name": "OK", "type": "Button", "bbox": [0, 0, 100, 50], "center": [50, 25]}},
                Path("/fake/anchors.json"),
            )
            mock_config.return_value = MagicMock(workspace_path=fake_workspace)

            result = await tool.execute(action="click", ui_name="OK", verify=True)

            assert "no prior screenshot" in result


# ── _get_vlm_feedback_loop tests ──────────────────────────────────────────


class TestGetVLMFeedbackLoop:
    """Test RPAExecutorTool._get_vlm_feedback_loop()."""

    @pytest.fixture
    def tool(self):
        from nanobot.agent.tools.rpa_executor import RPAExecutorTool

        return RPAExecutorTool()

    def test_disabled_returns_none(self, tool):
        """VLM feedback disabled → (None, None)."""
        from nanobot.config.schema import Config

        with patch("nanobot.config.loader.get_config") as mock_cfg:
            config = Config()
            config.agents.vlm_feedback.enabled = False
            mock_cfg.return_value = config

            loop, cfg = tool._get_vlm_feedback_loop()
            assert loop is None
            assert cfg is None

    def test_no_vlm_model_returns_none(self, tool):
        """VLM feedback enabled but no VLM model configured → (None, None)."""
        from nanobot.config.schema import Config

        with patch("nanobot.config.loader.get_config") as mock_cfg:
            config = Config()
            config.agents.vlm_feedback.enabled = True
            config.agents.vlm.enabled = False
            mock_cfg.return_value = config

            loop, cfg = tool._get_vlm_feedback_loop()
            assert loop is None
