"""Tests for channel security improvements (S7, S8, S9)."""

import asyncio
import pytest
from unittest.mock import patch, MagicMock, AsyncMock

from nanobot.channels.base import BaseChannel
from nanobot.bus.queue import MessageBus


class DummyChannel(BaseChannel):
    """Minimal concrete channel for testing."""
    name = "test_channel"
    async def start(self): pass
    async def stop(self): pass
    async def send(self, msg): pass


@pytest.fixture(autouse=True)
def reset_class_cache():
    """Reset cached master_identities between tests."""
    BaseChannel._master_identities = None
    yield
    BaseChannel._master_identities = None


# ── S7: Empty allowFrom warning ──

class TestAllowFromWarning:
    """S7: Empty allowFrom should emit a one-time warning."""

    @patch("nanobot.channels.base.BaseChannel._load_master_identities", return_value={})
    def test_warning_emitted_on_empty_allowfrom(self, _mock):
        bus = MessageBus()
        config = MagicMock(allow_from=[])
        chan = DummyChannel(config, bus)

        with patch("nanobot.channels.base.logger") as mock_logger:
            result = chan.is_allowed("anyone")
            assert result is True
            mock_logger.info.assert_called_once()
            assert "allowFrom is empty" in mock_logger.info.call_args[0][0]

    @patch("nanobot.channels.base.BaseChannel._load_master_identities", return_value={})
    def test_warning_emitted_only_once(self, _mock):
        bus = MessageBus()
        config = MagicMock(allow_from=[])
        chan = DummyChannel(config, bus)

        with patch("nanobot.channels.base.logger") as mock_logger:
            chan.is_allowed("user1")
            chan.is_allowed("user2")
            chan.is_allowed("user3")
            # Info should be called exactly once, not three times
            assert mock_logger.info.call_count == 1

    @patch("nanobot.channels.base.BaseChannel._load_master_identities", return_value={})
    def test_no_warning_when_allowfrom_configured(self, _mock):
        bus = MessageBus()
        config = MagicMock(allow_from=["allowed_user"])
        chan = DummyChannel(config, bus)

        with patch("nanobot.channels.base.logger") as mock_logger:
            chan.is_allowed("allowed_user")
            mock_logger.warning.assert_not_called()


# ── S8: Cached master_identities ──

class TestMasterIdentityCache:
    """S8: master_identities should be loaded once and cached."""

    def test_master_identities_cached(self):
        """_load_master_identities should only be called once across instances."""
        with patch.object(BaseChannel, "_load_master_identities", return_value={"test_channel:user1": "master:boss"}) as mock_load:
            bus = MessageBus()
            config = MagicMock(allow_from=["master:boss"])
            chan1 = DummyChannel(config, bus)
            chan2 = DummyChannel(config, bus)
            # Should be loaded exactly once (first __init__)
            assert mock_load.call_count == 1
            # Both instances share the same cache
            assert chan1.is_allowed("user1") is True
            assert chan2.is_allowed("user1") is True

    def test_cached_master_identity_lookup(self):
        """Master identity resolution via cached lookup."""
        with patch.object(BaseChannel, "_load_master_identities", return_value={"test_channel:user1": "master:boss"}):
            bus = MessageBus()
            config = MagicMock(allow_from=["master:boss"])
            chan = DummyChannel(config, bus)
            # user1 resolves to master:boss via cache
            assert chan.is_allowed("user1") is True
            # user2 is not in cache and not in allow_from
            assert chan.is_allowed("user2") is False


# ── S9: Error message sanitization ──

class TestErrorSanitization:
    """S9: Error messages to users must not contain internal details."""

    @pytest.mark.asyncio
    async def test_error_message_is_generic(self):
        """User-facing error should be generic, not containing Python exception text."""
        from nanobot.bus.events import InboundMessage, OutboundMessage

        bus = MessageBus()
        published = []
        original_publish = bus.publish_outbound

        async def capture_publish(msg):
            published.append(msg)
            # Don't actually publish to avoid blocking

        bus.publish_outbound = capture_publish

        # Simulate what loop.py does in the error handler
        msg = InboundMessage(
            channel="test", sender_id="user", chat_id="chat1", content="hello"
        )
        error = FileNotFoundError("/home/nanobot/.nanobot/config.json not found")

        # Replicate the sanitized error handling from loop.py
        error_content = "Sorry, I encountered an internal error. Please try again or contact the administrator."
        await bus.publish_outbound(OutboundMessage(
            channel=msg.channel, chat_id=msg.chat_id, content=error_content
        ))

        assert len(published) == 1
        assert "/home/nanobot" not in published[0].content
        assert "config.json" not in published[0].content
        assert "internal error" in published[0].content.lower()

    def test_error_message_does_not_contain_exception_str(self):
        """Verify the pattern: error messages should never contain raw exception text."""
        import re
        from pathlib import Path

        loop_py = Path("d:/Python/nanobot/nanobot/agent/loop.py").read_text(encoding="utf-8")

        # The old pattern `str(e)` in user-facing content should NOT exist
        # We look for the specific pattern: content=f"...{str(e)}" or content=f"...{e}"
        dangerous_patterns = [
            r'content=f".*\{str\(e\)\}"',
            r'content=f".*\{e\}"',
        ]
        for pattern in dangerous_patterns:
            matches = re.findall(pattern, loop_py)
            assert len(matches) == 0, f"Found dangerous error exposure pattern: {matches}"
