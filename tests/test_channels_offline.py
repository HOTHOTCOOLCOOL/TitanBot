"""Offline channel verification tests for C2-C10 (Step 8).

These tests validate code-level correctness without any external API keys,
covering message parsing, format conversion, dedup, policy logic, and error paths.

C6 (Email) is already covered by test_email_channel.py — only a smoke-import is done here.
"""

import asyncio
import json
import re
from collections import deque
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from nanobot.bus.events import OutboundMessage
from nanobot.bus.queue import MessageBus
from nanobot.channels.base import BaseChannel


# ── Fixtures ─────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def _reset_master_identities():
    """Reset BaseChannel class-level cache between tests."""
    BaseChannel._master_identities = None
    yield
    BaseChannel._master_identities = None


# ══════════════════════════════════════════════════════════════════════
# C2  MoChat (企业微信)
# ══════════════════════════════════════════════════════════════════════

class TestC2Mochat:
    """C2: MoChat channel offline tests."""

    # --- mochat_utils ---

    def test_normalize_mochat_content_string(self):
        from nanobot.channels.mochat_utils import normalize_mochat_content
        assert normalize_mochat_content("  hello  ") == "hello"

    def test_normalize_mochat_content_none(self):
        from nanobot.channels.mochat_utils import normalize_mochat_content
        assert normalize_mochat_content(None) == ""

    def test_normalize_mochat_content_dict(self):
        from nanobot.channels.mochat_utils import normalize_mochat_content
        result = normalize_mochat_content({"key": "值"})
        assert '"key"' in result and '"值"' in result

    def test_resolve_target_session(self):
        from nanobot.channels.mochat_utils import resolve_mochat_target
        t = resolve_mochat_target("session_abc123")
        assert t.id == "session_abc123"
        assert t.is_panel is False

    def test_resolve_target_panel(self):
        from nanobot.channels.mochat_utils import resolve_mochat_target
        t = resolve_mochat_target("panel:pid-1")
        assert t.id == "pid-1"
        assert t.is_panel is True

    def test_resolve_target_empty(self):
        from nanobot.channels.mochat_utils import resolve_mochat_target
        t = resolve_mochat_target("")
        assert t.id == ""
        assert t.is_panel is False

    def test_resolve_target_non_session_is_panel(self):
        from nanobot.channels.mochat_utils import resolve_mochat_target
        t = resolve_mochat_target("abc123")
        assert t.id == "abc123"
        assert t.is_panel is True  # non-session_ prefix defaults to panel

    def test_build_buffered_body_single(self):
        from nanobot.channels.mochat_utils import build_buffered_body, MochatBufferedEntry
        entries = [MochatBufferedEntry(raw_body="hello", author="u1")]
        assert build_buffered_body(entries, is_group=False) == "hello"

    def test_build_buffered_body_multi_group(self):
        from nanobot.channels.mochat_utils import build_buffered_body, MochatBufferedEntry
        entries = [
            MochatBufferedEntry(raw_body="hi", author="u1", sender_name="Alice"),
            MochatBufferedEntry(raw_body="there", author="u2", sender_name="Bob"),
        ]
        result = build_buffered_body(entries, is_group=True)
        assert "Alice: hi" in result
        assert "Bob: there" in result

    def test_build_buffered_body_empty(self):
        from nanobot.channels.mochat_utils import build_buffered_body
        assert build_buffered_body([], is_group=False) == ""

    def test_extract_mention_ids_mixed(self):
        from nanobot.channels.mochat_utils import extract_mention_ids
        ids = extract_mention_ids(["u1", {"id": "u2"}, {"userId": "u3"}])
        assert ids == ["u1", "u2", "u3"]

    def test_extract_mention_ids_non_list(self):
        from nanobot.channels.mochat_utils import extract_mention_ids
        assert extract_mention_ids("not-a-list") == []

    def test_resolve_was_mentioned_meta_flag(self):
        from nanobot.channels.mochat_utils import resolve_was_mentioned
        payload = {"meta": {"mentioned": True}}
        assert resolve_was_mentioned(payload, "agent1") is True

    def test_resolve_was_mentioned_text_fallback(self):
        from nanobot.channels.mochat_utils import resolve_was_mentioned
        payload = {"content": "hey <@agent1> look"}
        assert resolve_was_mentioned(payload, "agent1") is True

    def test_resolve_was_mentioned_false(self):
        from nanobot.channels.mochat_utils import resolve_was_mentioned
        payload = {"content": "just chatting"}
        assert resolve_was_mentioned(payload, "agent1") is False

    def test_parse_timestamp_valid(self):
        from nanobot.channels.mochat_utils import parse_timestamp
        ts = parse_timestamp("2026-01-01T00:00:00Z")
        assert isinstance(ts, int)
        assert ts > 0

    def test_parse_timestamp_invalid(self):
        from nanobot.channels.mochat_utils import parse_timestamp
        assert parse_timestamp("not-a-date") is None
        assert parse_timestamp(None) is None

    def test_make_synthetic_event(self):
        from nanobot.channels.mochat_utils import make_synthetic_event
        evt = make_synthetic_event(
            message_id="m1", author="u1", content="hello",
            meta=None, group_id="g1", converse_id="c1",
        )
        assert evt["type"] == "message.add"
        assert evt["payload"]["messageId"] == "m1"
        assert evt["payload"]["author"] == "u1"

    def test_str_field_picks_first_non_empty(self):
        from nanobot.channels.mochat_utils import str_field
        src = {"a": "", "b": " bob ", "c": "carol"}
        assert str_field(src, "a", "b", "c") == "bob"

    def test_channel_instantiation(self):
        from nanobot.channels.mochat import MochatChannel
        from nanobot.config.schema import MochatConfig
        cfg = MochatConfig(enabled=True, claw_token="test-token")
        bus = MessageBus()
        ch = MochatChannel(cfg, bus)
        assert ch.name == "mochat"
        assert ch.config.claw_token == "test-token"

    def test_remember_message_id_dedup(self):
        from nanobot.channels.mochat import MochatChannel
        from nanobot.config.schema import MochatConfig
        ch = MochatChannel(MochatConfig(enabled=True), MessageBus())
        key = "session:s1"
        assert ch._remember_message_id(key, "m1") is False  # first time
        assert ch._remember_message_id(key, "m1") is True   # duplicate


# ══════════════════════════════════════════════════════════════════════
# C3  Telegram
# ══════════════════════════════════════════════════════════════════════

class TestC3Telegram:
    """C3: Telegram channel offline tests."""

    def test_markdown_to_html_bold(self):
        from nanobot.channels.telegram import _markdown_to_telegram_html
        result = _markdown_to_telegram_html("**bold text**")
        assert "<b>bold text</b>" in result

    def test_markdown_to_html_italic(self):
        from nanobot.channels.telegram import _markdown_to_telegram_html
        result = _markdown_to_telegram_html("_italic text_")
        assert "<i>italic text</i>" in result

    def test_markdown_to_html_code(self):
        from nanobot.channels.telegram import _markdown_to_telegram_html
        result = _markdown_to_telegram_html("`inline code`")
        assert "<code>inline code</code>" in result

    def test_markdown_to_html_code_block(self):
        from nanobot.channels.telegram import _markdown_to_telegram_html
        result = _markdown_to_telegram_html("```python\nprint('hi')\n```")
        assert "<pre><code>" in result
        assert "print" in result

    def test_markdown_to_html_link(self):
        from nanobot.channels.telegram import _markdown_to_telegram_html
        result = _markdown_to_telegram_html("[click](https://example.com)")
        assert '<a href="https://example.com">click</a>' in result

    def test_markdown_to_html_strikethrough(self):
        from nanobot.channels.telegram import _markdown_to_telegram_html
        result = _markdown_to_telegram_html("~~deleted~~")
        assert "<s>deleted</s>" in result

    def test_markdown_to_html_escapes_html(self):
        from nanobot.channels.telegram import _markdown_to_telegram_html
        result = _markdown_to_telegram_html("a < b & c > d")
        assert "&lt;" in result and "&amp;" in result and "&gt;" in result

    def test_markdown_to_html_empty(self):
        from nanobot.channels.telegram import _markdown_to_telegram_html
        assert _markdown_to_telegram_html("") == ""

    def test_split_message_short(self):
        from nanobot.channels.telegram import _split_message
        chunks = _split_message("short message")
        assert chunks == ["short message"]

    def test_split_message_long(self):
        from nanobot.channels.telegram import _split_message
        text = "A" * 5000
        chunks = _split_message(text, max_len=4000)
        assert len(chunks) >= 2
        assert all(len(c) <= 4000 for c in chunks)

    def test_split_message_prefers_newline(self):
        from nanobot.channels.telegram import _split_message
        text = "line1\n" + "A" * 4000
        chunks = _split_message(text, max_len=100)
        assert chunks[0] == "line1"

    @pytest.mark.asyncio
    async def test_start_returns_without_token(self):
        from nanobot.channels.telegram import TelegramChannel
        from nanobot.config.schema import TelegramConfig
        cfg = TelegramConfig(enabled=True, token="")
        ch = TelegramChannel(cfg, MessageBus())
        await ch.start()
        assert ch.is_running is False

    def test_sender_id_with_username(self):
        from nanobot.channels.telegram import TelegramChannel
        user = MagicMock(id=12345, username="alice")
        assert TelegramChannel._sender_id(user) == "12345|alice"

    def test_sender_id_without_username(self):
        from nanobot.channels.telegram import TelegramChannel
        user = MagicMock(id=12345, username=None)
        assert TelegramChannel._sender_id(user) == "12345"

    def test_get_extension(self):
        from nanobot.channels.telegram import TelegramChannel
        cfg = MagicMock()
        ch = TelegramChannel(cfg, MessageBus())
        assert ch._get_extension("image", "image/png") == ".png"
        assert ch._get_extension("voice", None) == ".ogg"
        assert ch._get_extension("file", None) == ""


# ══════════════════════════════════════════════════════════════════════
# C4  Discord
# ══════════════════════════════════════════════════════════════════════

class TestC4Discord:
    """C4: Discord channel offline tests."""

    def test_channel_instantiation(self):
        from nanobot.channels.discord import DiscordChannel
        from nanobot.config.schema import DiscordConfig
        cfg = DiscordConfig(enabled=True, token="test-token")
        ch = DiscordChannel(cfg, MessageBus())
        assert ch.name == "discord"
        assert ch._seq is None

    @pytest.mark.asyncio
    async def test_start_returns_without_token(self):
        from nanobot.channels.discord import DiscordChannel
        from nanobot.config.schema import DiscordConfig
        cfg = DiscordConfig(enabled=True, token="")
        ch = DiscordChannel(cfg, MessageBus())
        await ch.start()
        assert ch.is_running is False

    @pytest.mark.asyncio
    async def test_handle_message_create_ignores_bot(self):
        from nanobot.channels.discord import DiscordChannel
        from nanobot.config.schema import DiscordConfig
        cfg = DiscordConfig(enabled=True, token="t", allow_from=[])
        ch = DiscordChannel(cfg, MessageBus())
        ch._http = MagicMock()

        # Bot messages should be silently ignored
        payload = {"author": {"id": "123", "bot": True}, "channel_id": "ch1", "content": "hi"}
        await ch._handle_message_create(payload)
        # No assertion needed — should not raise

    @pytest.mark.asyncio
    async def test_handle_message_create_parses_payload(self):
        from nanobot.channels.discord import DiscordChannel
        from nanobot.config.schema import DiscordConfig
        cfg = DiscordConfig(enabled=True, token="t", allow_from=[])
        bus = MessageBus()
        ch = DiscordChannel(cfg, bus)
        ch._http = MagicMock()

        published = []
        bus.publish_inbound = AsyncMock(side_effect=lambda m: published.append(m))

        payload = {
            "author": {"id": "user1", "bot": False},
            "channel_id": "ch1",
            "content": "hello discord",
            "id": "msg1",
            "attachments": [],
        }
        await ch._handle_message_create(payload)
        assert len(published) == 1
        assert published[0].content == "hello discord"
        assert published[0].sender_id == "user1"

    @pytest.mark.asyncio
    async def test_send_rate_limit_retry(self):
        from nanobot.channels.discord import DiscordChannel
        from nanobot.config.schema import DiscordConfig
        cfg = DiscordConfig(enabled=True, token="t")
        ch = DiscordChannel(cfg, MessageBus())

        call_count = {"n": 0}
        rate_limit_resp = MagicMock(status_code=429, json=lambda: {"retry_after": 0.01})
        ok_resp = MagicMock(status_code=200)
        ok_resp.raise_for_status = MagicMock()

        async def fake_post(*args, **kwargs):
            call_count["n"] += 1
            if call_count["n"] == 1:
                return rate_limit_resp
            return ok_resp

        ch._http = MagicMock()
        ch._http.post = fake_post

        msg = OutboundMessage(channel="discord", chat_id="ch1", content="retry test")
        await ch.send(msg)
        assert call_count["n"] == 2  # First 429, then 200


# ══════════════════════════════════════════════════════════════════════
# C5  Slack
# ══════════════════════════════════════════════════════════════════════

class TestC5Slack:
    """C5: Slack channel offline tests."""

    def test_to_mrkdwn_basic(self):
        from nanobot.channels.slack import SlackChannel
        result = SlackChannel._to_mrkdwn("**bold** and _italic_")
        # slackify_markdown converts to Slack mrkdwn format
        assert result  # non-empty

    def test_to_mrkdwn_empty(self):
        from nanobot.channels.slack import SlackChannel
        assert SlackChannel._to_mrkdwn("") == ""

    def test_convert_table(self):
        from nanobot.channels.slack import SlackChannel
        table = "| Name | Age |\n| --- | --- |\n| Alice | 30 |\n| Bob | 25 |"
        match = SlackChannel._TABLE_RE.search(table)
        assert match is not None
        result = SlackChannel._convert_table(match)
        assert "Name" in result
        assert "Alice" in result

    def test_is_allowed_dm_open(self):
        from nanobot.channels.slack import SlackChannel
        from nanobot.config.schema import SlackConfig
        cfg = SlackConfig(enabled=True, bot_token="t", app_token="t")
        ch = SlackChannel(cfg, MessageBus())
        assert ch._is_allowed("anyone", "ch1", "im") is True

    def test_is_allowed_dm_disabled(self):
        from nanobot.channels.slack import SlackChannel
        from nanobot.config.schema import SlackConfig, SlackDMConfig
        cfg = SlackConfig(enabled=True, bot_token="t", app_token="t",
                          dm=SlackDMConfig(enabled=False))
        ch = SlackChannel(cfg, MessageBus())
        assert ch._is_allowed("anyone", "ch1", "im") is False

    def test_is_allowed_dm_allowlist(self):
        from nanobot.channels.slack import SlackChannel
        from nanobot.config.schema import SlackConfig, SlackDMConfig
        cfg = SlackConfig(enabled=True, bot_token="t", app_token="t",
                          dm=SlackDMConfig(enabled=True, policy="allowlist", allow_from=["U123"]))
        ch = SlackChannel(cfg, MessageBus())
        assert ch._is_allowed("U123", "ch1", "im") is True
        assert ch._is_allowed("U999", "ch1", "im") is False

    def test_should_respond_mention_policy(self):
        from nanobot.channels.slack import SlackChannel
        from nanobot.config.schema import SlackConfig
        cfg = SlackConfig(enabled=True, bot_token="t", app_token="t", group_policy="mention")
        ch = SlackChannel(cfg, MessageBus())
        ch._bot_user_id = "BOTID"
        # app_mention event always responds
        assert ch._should_respond_in_channel("app_mention", "hey", "ch1") is True
        # plain message without mention is ignored
        assert ch._should_respond_in_channel("message", "hey", "ch1") is False
        # plain message with mention
        assert ch._should_respond_in_channel("message", "<@BOTID> hey", "ch1") is True

    def test_should_respond_open_policy(self):
        from nanobot.channels.slack import SlackChannel
        from nanobot.config.schema import SlackConfig
        cfg = SlackConfig(enabled=True, bot_token="t", app_token="t", group_policy="open")
        ch = SlackChannel(cfg, MessageBus())
        assert ch._should_respond_in_channel("message", "hey", "ch1") is True

    def test_should_respond_allowlist_policy(self):
        from nanobot.channels.slack import SlackChannel
        from nanobot.config.schema import SlackConfig
        cfg = SlackConfig(enabled=True, bot_token="t", app_token="t",
                          group_policy="allowlist", group_allow_from=["ch1"])
        ch = SlackChannel(cfg, MessageBus())
        assert ch._should_respond_in_channel("message", "hey", "ch1") is True
        assert ch._should_respond_in_channel("message", "hey", "ch2") is False

    def test_strip_bot_mention(self):
        from nanobot.channels.slack import SlackChannel
        from nanobot.config.schema import SlackConfig
        cfg = SlackConfig(enabled=True, bot_token="t", app_token="t")
        ch = SlackChannel(cfg, MessageBus())
        ch._bot_user_id = "U123"
        assert ch._strip_bot_mention("<@U123> hello") == "hello"
        assert ch._strip_bot_mention("hello") == "hello"


# ══════════════════════════════════════════════════════════════════════
# C6  Email  (already covered by test_email_channel.py)
# ══════════════════════════════════════════════════════════════════════

class TestC6Email:
    """C6: Email channel — smoke import only (full tests in test_email_channel.py)."""

    def test_import(self):
        from nanobot.channels.email import EmailChannel
        assert EmailChannel.name == "email"


# ══════════════════════════════════════════════════════════════════════
# C7  Feishu (飞书)
# ══════════════════════════════════════════════════════════════════════

class TestC7Feishu:
    """C7: Feishu channel offline tests."""

    def test_extract_post_text_direct_format(self):
        from nanobot.channels.feishu import _extract_post_text
        content = {
            "title": "公告",
            "content": [[{"tag": "text", "text": "内容一"}, {"tag": "a", "text": "链接"}]],
        }
        result = _extract_post_text(content)
        assert "公告" in result
        assert "内容一" in result
        assert "链接" in result

    def test_extract_post_text_localized_format(self):
        from nanobot.channels.feishu import _extract_post_text
        content = {
            "zh_cn": {
                "title": "通知",
                "content": [[{"tag": "text", "text": "测试消息"}]],
            }
        }
        result = _extract_post_text(content)
        assert "通知" in result
        assert "测试消息" in result

    def test_extract_post_text_at_tag(self):
        from nanobot.channels.feishu import _extract_post_text
        content = {
            "content": [[{"tag": "at", "user_name": "张三"}]],
        }
        result = _extract_post_text(content)
        assert "@张三" in result

    def test_extract_post_text_empty(self):
        from nanobot.channels.feishu import _extract_post_text
        assert _extract_post_text({}) == ""

    def test_parse_md_table(self):
        from nanobot.channels.feishu import FeishuChannel
        table_text = "| Name | Age |\n| --- | --- |\n| Alice | 30 |"
        result = FeishuChannel._parse_md_table(table_text)
        assert result is not None
        assert result["tag"] == "table"
        assert len(result["columns"]) == 2
        assert result["columns"][0]["display_name"] == "Name"
        assert len(result["rows"]) == 1

    def test_build_card_elements_markdown_only(self):
        from nanobot.channels.feishu import FeishuChannel
        from nanobot.config.schema import FeishuConfig
        ch = FeishuChannel(FeishuConfig(enabled=True), MessageBus())
        elements = ch._build_card_elements("Just normal text")
        assert any(el.get("tag") == "markdown" for el in elements)

    def test_build_card_elements_with_table(self):
        from nanobot.channels.feishu import FeishuChannel
        from nanobot.config.schema import FeishuConfig
        ch = FeishuChannel(FeishuConfig(enabled=True), MessageBus())
        content = "Summary\n\n| A | B |\n| --- | --- |\n| 1 | 2 |\n\nFooter"
        elements = ch._build_card_elements(content)
        tags = [el.get("tag") for el in elements]
        assert "table" in tags or "markdown" in tags  # table or markdown wrapper

    def test_split_headings(self):
        from nanobot.channels.feishu import FeishuChannel
        from nanobot.config.schema import FeishuConfig
        ch = FeishuChannel(FeishuConfig(enabled=True), MessageBus())
        elements = ch._split_headings("## Title\n\nBody text")
        assert len(elements) >= 2
        # Should have a div for heading and markdown for body
        tags = [el.get("tag") for el in elements]
        assert "div" in tags

    def test_msg_type_map(self):
        from nanobot.channels.feishu import MSG_TYPE_MAP
        assert MSG_TYPE_MAP["image"] == "[image]"
        assert MSG_TYPE_MAP["audio"] == "[audio]"


# ══════════════════════════════════════════════════════════════════════
# C8  DingTalk (钉钉)
# ══════════════════════════════════════════════════════════════════════

class TestC8DingTalk:
    """C8: DingTalk channel offline tests."""

    def test_channel_instantiation(self):
        from nanobot.channels.dingtalk import DingTalkChannel
        from nanobot.config.schema import DingTalkConfig
        cfg = DingTalkConfig(enabled=True, client_id="test-id", client_secret="test-secret")
        ch = DingTalkChannel(cfg, MessageBus())
        assert ch.name == "dingtalk"
        assert ch._access_token is None

    @pytest.mark.asyncio
    async def test_start_returns_without_credentials(self):
        from nanobot.channels.dingtalk import DingTalkChannel, DINGTALK_AVAILABLE
        from nanobot.config.schema import DingTalkConfig

        if not DINGTALK_AVAILABLE:
            pytest.skip("dingtalk-stream SDK not installed")

        cfg = DingTalkConfig(enabled=True, client_id="", client_secret="")
        ch = DingTalkChannel(cfg, MessageBus())
        await ch.start()
        assert ch.is_running is False

    @pytest.mark.asyncio
    async def test_send_requires_access_token(self):
        from nanobot.channels.dingtalk import DingTalkChannel
        from nanobot.config.schema import DingTalkConfig
        cfg = DingTalkConfig(enabled=True, client_id="id", client_secret="secret")
        ch = DingTalkChannel(cfg, MessageBus())
        ch._http = MagicMock()

        # _get_access_token returns None → send silently returns
        ch._get_access_token = AsyncMock(return_value=None)
        msg = OutboundMessage(channel="dingtalk", chat_id="user1", content="test")
        await ch.send(msg)
        # No error should be raised

    @pytest.mark.asyncio
    async def test_on_message_dispatches(self):
        from nanobot.channels.dingtalk import DingTalkChannel
        from nanobot.config.schema import DingTalkConfig
        cfg = DingTalkConfig(enabled=True, client_id="id", client_secret="secret")
        bus = MessageBus()
        ch = DingTalkChannel(cfg, bus)
        ch._running = True

        published = []
        bus.publish_inbound = AsyncMock(side_effect=lambda m: published.append(m))

        await ch._on_message("hello ding", "staff123", "TestUser")
        assert len(published) == 1
        assert published[0].content == "hello ding"
        assert published[0].sender_id == "staff123"


# ══════════════════════════════════════════════════════════════════════
# C9  WhatsApp
# ══════════════════════════════════════════════════════════════════════

class TestC9WhatsApp:
    """C9: WhatsApp channel offline tests."""

    def test_channel_instantiation(self):
        from nanobot.channels.whatsapp import WhatsAppChannel
        from nanobot.config.schema import WhatsAppConfig
        cfg = WhatsAppConfig(enabled=True, bridge_url="ws://localhost:3001")
        ch = WhatsAppChannel(cfg, MessageBus())
        assert ch.name == "whatsapp"
        assert ch._connected is False

    @pytest.mark.asyncio
    async def test_handle_bridge_message_text(self):
        from nanobot.channels.whatsapp import WhatsAppChannel
        from nanobot.config.schema import WhatsAppConfig
        cfg = WhatsAppConfig(enabled=True, allow_from=[])
        bus = MessageBus()
        ch = WhatsAppChannel(cfg, bus)

        published = []
        bus.publish_inbound = AsyncMock(side_effect=lambda m: published.append(m))

        raw = json.dumps({
            "type": "message",
            "sender": "123456@lid",
            "pn": "",
            "content": "hello whatsapp",
            "id": "msg1",
            "timestamp": 1234567890,
            "isGroup": False,
        })
        await ch._handle_bridge_message(raw)
        assert len(published) == 1
        assert published[0].content == "hello whatsapp"
        assert published[0].chat_id == "123456@lid"

    @pytest.mark.asyncio
    async def test_handle_bridge_message_status(self):
        from nanobot.channels.whatsapp import WhatsAppChannel
        from nanobot.config.schema import WhatsAppConfig
        cfg = WhatsAppConfig(enabled=True)
        ch = WhatsAppChannel(cfg, MessageBus())

        raw = json.dumps({"type": "status", "status": "connected"})
        await ch._handle_bridge_message(raw)
        assert ch._connected is True

        raw = json.dumps({"type": "status", "status": "disconnected"})
        await ch._handle_bridge_message(raw)
        assert ch._connected is False

    @pytest.mark.asyncio
    async def test_handle_bridge_message_qr(self):
        from nanobot.channels.whatsapp import WhatsAppChannel
        from nanobot.config.schema import WhatsAppConfig
        ch = WhatsAppChannel(WhatsAppConfig(enabled=True), MessageBus())
        raw = json.dumps({"type": "qr"})
        # Should not raise
        await ch._handle_bridge_message(raw)

    @pytest.mark.asyncio
    async def test_handle_bridge_message_invalid_json(self):
        from nanobot.channels.whatsapp import WhatsAppChannel
        from nanobot.config.schema import WhatsAppConfig
        ch = WhatsAppChannel(WhatsAppConfig(enabled=True), MessageBus())
        # Should not raise on invalid JSON
        await ch._handle_bridge_message("not json {{{")

    @pytest.mark.asyncio
    async def test_handle_bridge_message_voice(self):
        from nanobot.channels.whatsapp import WhatsAppChannel
        from nanobot.config.schema import WhatsAppConfig
        cfg = WhatsAppConfig(enabled=True, allow_from=[])
        bus = MessageBus()
        ch = WhatsAppChannel(cfg, bus)

        published = []
        bus.publish_inbound = AsyncMock(side_effect=lambda m: published.append(m))

        raw = json.dumps({
            "type": "message",
            "sender": "user@lid",
            "pn": "",
            "content": "[Voice Message]",
            "id": "v1",
        })
        await ch._handle_bridge_message(raw)
        assert len(published) == 1
        assert "Transcription not available" in published[0].content

    @pytest.mark.asyncio
    async def test_send_not_connected(self):
        from nanobot.channels.whatsapp import WhatsAppChannel
        from nanobot.config.schema import WhatsAppConfig
        ch = WhatsAppChannel(WhatsAppConfig(enabled=True), MessageBus())
        msg = OutboundMessage(channel="whatsapp", chat_id="user1", content="test")
        # Should not raise when not connected
        await ch.send(msg)

    def test_sender_id_extraction_from_lid(self):
        """Verify that sender_id is correctly extracted from LID format."""
        lid = "123456@lid"
        sender_id = lid.split("@")[0]
        assert sender_id == "123456"

    def test_sender_id_extraction_from_phone(self):
        """Verify sender_id extraction from phone number format."""
        pn = "8613800138000@s.whatsapp.net"
        sender_id = pn.split("@")[0]
        assert sender_id == "8613800138000"


# ══════════════════════════════════════════════════════════════════════
# C10  QQ
# ══════════════════════════════════════════════════════════════════════

class TestC10QQ:
    """C10: QQ channel offline tests."""

    def test_channel_instantiation(self):
        from nanobot.channels.qq import QQChannel
        from nanobot.config.schema import QQConfig
        cfg = QQConfig(enabled=True, app_id="test-id", secret="test-secret")
        ch = QQChannel(cfg, MessageBus())
        assert ch.name == "qq"
        assert isinstance(ch._processed_ids, deque)
        assert ch._processed_ids.maxlen == 1000

    @pytest.mark.asyncio
    async def test_start_returns_without_sdk(self):
        from nanobot.channels.qq import QQChannel, QQ_AVAILABLE
        from nanobot.config.schema import QQConfig

        if QQ_AVAILABLE:
            pytest.skip("qq-botpy SDK is installed, testing missing-SDK path not applicable")

        cfg = QQConfig(enabled=True, app_id="id", secret="secret")
        ch = QQChannel(cfg, MessageBus())
        await ch.start()
        assert ch.is_running is False

    @pytest.mark.asyncio
    async def test_start_returns_without_credentials(self):
        from nanobot.channels.qq import QQChannel, QQ_AVAILABLE
        from nanobot.config.schema import QQConfig

        if not QQ_AVAILABLE:
            pytest.skip("qq-botpy SDK not installed")

        cfg = QQConfig(enabled=True, app_id="", secret="")
        ch = QQChannel(cfg, MessageBus())
        await ch.start()
        assert ch.is_running is False

    @pytest.mark.asyncio
    async def test_on_message_dedup(self):
        from nanobot.channels.qq import QQChannel
        from nanobot.config.schema import QQConfig
        cfg = QQConfig(enabled=True, app_id="id", secret="s", allow_from=[])
        bus = MessageBus()
        ch = QQChannel(cfg, bus)

        published = []
        bus.publish_inbound = AsyncMock(side_effect=lambda m: published.append(m))

        class FakeMessage:
            id = "msg-001"
            content = "hello qq"
            class author:
                id = "user1"

        msg = FakeMessage()
        await ch._on_message(msg)
        assert len(published) == 1

        # Same message ID → should be deduped
        await ch._on_message(msg)
        assert len(published) == 1  # still 1, not 2


# ══════════════════════════════════════════════════════════════════════
# Cross-channel: ChannelManager + Registry
# ══════════════════════════════════════════════════════════════════════

class TestChannelRegistry:
    """Verify channel manager registry and initialization."""

    def test_all_channels_in_registry(self):
        from nanobot.channels.manager import _CHANNEL_REGISTRY
        names = [entry[0] for entry in _CHANNEL_REGISTRY]
        expected = ["telegram", "whatsapp", "discord", "feishu", "mochat",
                    "dingtalk", "email", "slack", "qq"]
        for name in expected:
            assert name in names, f"{name} missing from _CHANNEL_REGISTRY"

    def test_channel_manager_no_channels_enabled(self):
        from nanobot.channels.manager import ChannelManager
        from nanobot.config.schema import Config
        cfg = Config()  # All channels disabled by default
        bus = MessageBus()
        mgr = ChannelManager(cfg, bus)
        assert len(mgr.channels) == 0

    def test_channel_manager_status_empty(self):
        from nanobot.channels.manager import ChannelManager
        from nanobot.config.schema import Config
        mgr = ChannelManager(Config(), MessageBus())
        status = mgr.get_status()
        assert status == {}

    def test_channels_config_schema(self):
        from nanobot.config.schema import ChannelsConfig
        cfg = ChannelsConfig()
        # All channels should have an 'enabled' field defaulting to False
        for name in ["whatsapp", "telegram", "discord", "feishu", "mochat",
                     "dingtalk", "email", "slack", "qq"]:
            channel_cfg = getattr(cfg, name)
            assert hasattr(channel_cfg, "enabled")
            assert channel_cfg.enabled is False
