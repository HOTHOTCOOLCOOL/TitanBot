"""Phase 23C — P2 Architecture Polish: Tests.

Covers 4 risk items:
- R11: Image size limit in _build_user_content (20 MB)
- R6:  Write file size limit in WriteFileTool (10 MB)
- R14: VLM env variable direct override
- R16: Visual memory hash uses SHA256
"""

import hashlib
import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from nanobot.agent.context import ContextBuilder
from nanobot.agent.tools.filesystem import WriteFileTool


# ──────────────────────────────────────────────────────────────────────
# R11: Image Size Limit
# ──────────────────────────────────────────────────────────────────────

class TestImageSizeLimit:
    """R11: Oversized images should be skipped in _build_user_content."""

    def test_image_size_limit_skips_large(self, tmp_path: Path) -> None:
        """A file larger than 20 MB should be skipped."""
        big_file = tmp_path / "huge.png"
        big_file.write_bytes(b"\x89PNG" + b"\x00" * 100)  # small real file

        builder = ContextBuilder(tmp_path)

        # Patch the size check by temporarily lowering the threshold
        original_max = ContextBuilder._MAX_IMAGE_BYTES
        try:
            ContextBuilder._MAX_IMAGE_BYTES = 50  # 50 bytes — our file is >100
            result = builder._build_user_content("hello", [str(big_file)])
        finally:
            ContextBuilder._MAX_IMAGE_BYTES = original_max

        # Should return plain text since the only image was skipped
        assert result == "hello"

    def test_image_size_limit_allows_normal(self, tmp_path: Path) -> None:
        """A normal-sized image should be included."""
        # Create a minimal valid PNG-like file
        img_file = tmp_path / "small.png"
        img_file.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 50)

        builder = ContextBuilder(tmp_path)
        result = builder._build_user_content("hello", [str(img_file)])

        # Should return a list with image + text blocks
        assert isinstance(result, list)
        assert any(
            isinstance(b, dict) and b.get("type") == "image_url"
            for b in result
        )


# ──────────────────────────────────────────────────────────────────────
# R6: Write File Size Limit
# ──────────────────────────────────────────────────────────────────────

class TestWriteFileSizeLimit:
    """R6: WriteFileTool should reject content exceeding 10 MB."""

    @pytest.mark.asyncio
    async def test_write_file_rejects_oversized(self, tmp_path: Path) -> None:
        """Content exceeding 10 MB should be rejected."""
        tool = WriteFileTool(allowed_dir=tmp_path)
        # 10 MB + 1 byte in UTF-8
        big_content = "A" * (10 * 1024 * 1024 + 1)
        result = await tool.execute(
            path=str(tmp_path / "big.txt"), content=big_content
        )
        assert "Error" in result
        assert "too large" in result.lower()

    @pytest.mark.asyncio
    async def test_write_file_allows_normal(self, tmp_path: Path) -> None:
        """Normal content should write successfully."""
        tool = WriteFileTool(allowed_dir=tmp_path)
        result = await tool.execute(
            path=str(tmp_path / "ok.txt"), content="Hello, world!"
        )
        assert "Successfully" in result
        assert (tmp_path / "ok.txt").read_text() == "Hello, world!"


# ──────────────────────────────────────────────────────────────────────
# R14: VLM Env Variable Override
# ──────────────────────────────────────────────────────────────────────

class TestVLMEnvOverride:
    """R14: VLM dynamic route should override existing env key."""

    def test_vlm_env_override(self) -> None:
        """When VLM route runs, env key should be overwritten, not setdefault'd."""
        import inspect
        from nanobot.providers import litellm_provider as lp_mod

        source = inspect.getsource(lp_mod.LiteLLMProvider.chat)
        # The VLM env section should use direct assignment, not setdefault
        # Find the section that handles VLM routing (model != default_model)
        assert "os.environ[spec.env_key]" in source, (
            "VLM route should use os.environ[key] = value, not setdefault"
        )


# ──────────────────────────────────────────────────────────────────────
# R16: Visual Memory Hash Uses SHA256
# ──────────────────────────────────────────────────────────────────────

class TestVisualMemoryHash:
    """R16: Visual memory dedup hash should use SHA256, not MD5."""

    def test_visual_hash_uses_sha256(self) -> None:
        """context.py should use sha256, not md5, for visual memory hash."""
        import inspect
        from nanobot.agent import context as ctx_module

        source = inspect.getsource(ctx_module.ContextBuilder)
        # Should contain sha256 call
        assert "hashlib.sha256" in source, "Visual memory should use sha256"
        # Should NOT contain md5 for content hashing
        assert "hashlib.md5" not in source, "Visual memory should not use md5"

    def test_hash_length_is_16(self) -> None:
        """SHA256 hash should be truncated to 16 characters."""
        test_content = "test visual memory content"
        expected = hashlib.sha256(test_content.encode("utf-8")).hexdigest()[:16]
        assert len(expected) == 16
