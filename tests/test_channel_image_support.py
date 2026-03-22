"""Tests for channel image support — Feishu image download and shared downloader."""

import json
from pathlib import Path
from unittest.mock import MagicMock, AsyncMock, patch

import pytest

from nanobot.channels.image_downloader import save_image_bytes, is_image_mime, MEDIA_DIR


# ---------------------------------------------------------------------------
# Shared image downloader tests
# ---------------------------------------------------------------------------

class TestImageDownloader:
    """Tests for nanobot.channels.image_downloader."""

    def test_save_image_bytes(self, tmp_path: Path):
        """Verify image bytes are saved to disk correctly."""
        with patch("nanobot.channels.image_downloader.MEDIA_DIR", tmp_path):
            result = save_image_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 100, "test.png")
        assert result is not None
        assert result.exists()
        assert result.name == "test.png"
        assert result.read_bytes() == b"\x89PNG\r\n\x1a\n" + b"\x00" * 100

    def test_save_image_bytes_empty(self):
        """Empty data should return None."""
        assert save_image_bytes(b"", "empty.jpg") is None

    def test_is_image_mime(self):
        """Verify MIME type detection."""
        assert is_image_mime("image/jpeg") is True
        assert is_image_mime("image/png") is True
        assert is_image_mime("image/gif") is True
        assert is_image_mime("image/webp") is True
        assert is_image_mime("text/plain") is False
        assert is_image_mime("application/json") is False
        assert is_image_mime("IMAGE/JPEG") is True  # case insensitive


# ---------------------------------------------------------------------------
# Feishu image download tests
# ---------------------------------------------------------------------------

class TestFeishuImageDownload:
    """Tests for FeishuChannel image download functionality."""

    @pytest.fixture
    def feishu_channel(self):
        """Create a FeishuChannel with mocked dependencies."""
        from nanobot.channels.feishu import FeishuChannel
        from nanobot.config.schema import FeishuConfig

        config = FeishuConfig(
            app_id="test_app_id",
            app_secret="test_app_secret",
        )
        bus = MagicMock()
        channel = FeishuChannel(config, bus)
        channel._client = MagicMock()
        return channel

    def test_download_image_sync_success(self, feishu_channel, tmp_path: Path):
        """Verify successful image download via Feishu API."""
        # Mock the API response
        mock_response = MagicMock()
        mock_response.success.return_value = True
        mock_response.file.read.return_value = b"\xff\xd8\xff\xe0" + b"\x00" * 100  # JPEG header
        feishu_channel._client.im.v1.message_resource.get.return_value = mock_response

        with patch("nanobot.channels.image_downloader.MEDIA_DIR", tmp_path):
            result = feishu_channel._download_image_sync("msg_123", "img_key_abc")

        assert result is not None
        assert result.exists()
        assert "feishu_img_key_abc" in result.name

    def test_download_image_sync_api_failure(self, feishu_channel):
        """Verify graceful handling of API failure."""
        mock_response = MagicMock()
        mock_response.success.return_value = False
        mock_response.code = 99999
        mock_response.msg = "Permission denied"
        feishu_channel._client.im.v1.message_resource.get.return_value = mock_response

        result = feishu_channel._download_image_sync("msg_123", "img_key_abc")
        assert result is None

    def test_download_image_sync_no_client(self, feishu_channel):
        """Verify None return when client not initialized."""
        feishu_channel._client = None
        result = feishu_channel._download_image_sync("msg_123", "img_key_abc")
        assert result is None

    @pytest.mark.asyncio
    async def test_on_message_with_image(self, feishu_channel, tmp_path: Path):
        """Verify _on_message correctly processes image messages end-to-end."""
        # Mock the event data
        mock_event = MagicMock()
        mock_message = MagicMock()
        mock_message.message_id = "om_test123"
        mock_message.chat_id = "oc_test_chat"
        mock_message.chat_type = "p2p"
        mock_message.message_type = "image"
        mock_message.content = json.dumps({"image_key": "img_key_xyz"})
        mock_event.message = mock_message

        mock_sender = MagicMock()
        mock_sender.sender_type = "user"
        mock_sender.sender_id.open_id = "ou_test_user"
        mock_event.sender = mock_sender

        mock_data = MagicMock()
        mock_data.event = mock_event

        # Mock image download
        saved_path = tmp_path / "feishu_img_key_xyz.jpg"
        saved_path.write_bytes(b"\xff\xd8" + b"\x00" * 50)

        with patch.object(feishu_channel, "_download_image", new_callable=AsyncMock, return_value=saved_path), \
             patch.object(feishu_channel, "_add_reaction", new_callable=AsyncMock), \
             patch.object(feishu_channel, "_handle_message", new_callable=AsyncMock) as mock_handle:
            await feishu_channel._on_message(mock_data)

        # Verify _handle_message was called with media paths
        mock_handle.assert_called_once()
        call_kwargs = mock_handle.call_args
        assert call_kwargs.kwargs.get("media") == [str(saved_path)]
        assert "analyze" in call_kwargs.kwargs.get("content", "").lower()
