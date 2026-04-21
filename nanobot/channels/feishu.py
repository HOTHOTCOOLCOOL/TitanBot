"""Feishu/Lark channel implementation using lark-oapi SDK with WebSocket long connection."""

import asyncio
import json
import re
import threading
from collections import OrderedDict
from typing import Any
from pathlib import Path

from loguru import logger

from nanobot.bus.events import OutboundMessage
from nanobot.bus.queue import MessageBus
from nanobot.channels.base import BaseChannel
from nanobot.config.schema import FeishuConfig

try:
    import lark_oapi as lark
    from lark_oapi.api.im.v1 import (
        CreateMessageRequest,
        CreateMessageRequestBody,
        CreateMessageReactionRequest,
        CreateMessageReactionRequestBody,
        Emoji,
        P2ImMessageReceiveV1,
        P2ImMessageMessageReadV1,
        GetMessageResourceRequest,
        CreateImageRequest,
        CreateImageRequestBody,
    )
    FEISHU_AVAILABLE = True
except ImportError:
    FEISHU_AVAILABLE = False
    lark = None
    Emoji = None

# Message type display mapping
MSG_TYPE_MAP = {
    "image": "[image]",
    "audio": "[audio]",
    "file": "[file]",
    "sticker": "[sticker]",
}


def _extract_post_text(content_json: dict) -> str:
    """Extract plain text from Feishu post (rich text) message content.
    
    Supports two formats:
    1. Direct format: {"title": "...", "content": [...]}
    2. Localized format: {"zh_cn": {"title": "...", "content": [...]}}
    """
    def extract_from_lang(lang_content: dict) -> str | None:
        if not isinstance(lang_content, dict):
            return None
        title = lang_content.get("title", "")
        content_blocks = lang_content.get("content", [])
        if not isinstance(content_blocks, list):
            return None
        text_parts = []
        if title:
            text_parts.append(title)
        for block in content_blocks:
            if not isinstance(block, list):
                continue
            for element in block:
                if isinstance(element, dict):
                    tag = element.get("tag")
                    if tag == "text":
                        text_parts.append(element.get("text", ""))
                    elif tag == "a":
                        text_parts.append(element.get("text", ""))
                    elif tag == "at":
                        text_parts.append(f"@{element.get('user_name', 'user')}")
        return " ".join(text_parts).strip() if text_parts else None
    
    # Try direct format first
    if "content" in content_json:
        result = extract_from_lang(content_json)
        if result:
            return result
    
    # Try localized format
    for lang_key in ("zh_cn", "en_us", "ja_jp"):
        lang_content = content_json.get(lang_key)
        result = extract_from_lang(lang_content)
        if result:
            return result
    
    return ""


class FeishuChannel(BaseChannel):
    """
    Feishu/Lark channel using WebSocket long connection.
    
    Uses WebSocket to receive events - no public IP or webhook required.
    
    Requires:
    - App ID and App Secret from Feishu Open Platform
    - Bot capability enabled
    - Event subscription enabled (im.message.receive_v1)
    """
    
    name = "feishu"
    
    def __init__(self, config: FeishuConfig, bus: MessageBus):
        super().__init__(config, bus)
        self.config: FeishuConfig = config
        self._client: Any = None
        self._ws_client: Any = None
        self._ws_thread: threading.Thread | None = None
        self._processed_message_ids: OrderedDict[str, None] = OrderedDict()  # Ordered dedup cache
        self._loop: asyncio.AbstractEventLoop | None = None
    
    async def start(self) -> None:
        """Start the Feishu bot with WebSocket long connection."""
        if not FEISHU_AVAILABLE:
            logger.error("Feishu SDK not installed. Run: pip install lark-oapi")
            return
        
        if not self.config.app_id or not self.config.app_secret:
            logger.error("Feishu app_id and app_secret not configured")
            return
        
        self._running = True
        self._loop = asyncio.get_running_loop()
        
        # Create Lark client for sending messages
        self._client = lark.Client.builder() \
            .app_id(self.config.app_id) \
            .app_secret(self.config.app_secret) \
            .log_level(lark.LogLevel.INFO) \
            .build()
        
        # Create event handler (only register message receive, ignore other events)
        event_handler = lark.EventDispatcherHandler.builder(
            self.config.encrypt_key or "",
            self.config.verification_token or "",
        ).register_p2_im_message_receive_v1(
            self._on_message_sync
        ).register_p2_im_message_message_read_v1(
            lambda data: None
        ).build()
        
        # Create WebSocket client for long connection
        self._ws_client = lark.ws.Client(
            self.config.app_id,
            self.config.app_secret,
            event_handler=event_handler,
            log_level=lark.LogLevel.INFO
        )
        
        # Start WebSocket client in a separate thread with reconnect loop
        def run_ws():
            while self._running:
                try:
                    self._ws_client.start()
                except Exception as e:
                    if isinstance(e, asyncio.CancelledError):
                        raise
                    logger.warning(f"Feishu WebSocket error: {e}")
                if self._running:
                    import time; time.sleep(5)
        
        self._ws_thread = threading.Thread(target=run_ws, daemon=True)
        self._ws_thread.start()
        
        logger.info("Feishu bot started with WebSocket long connection")
        logger.info("No public IP required - using WebSocket to receive events")
        
        # Keep running until stopped
        while self._running:
            await asyncio.sleep(1)
    
    async def stop(self) -> None:
        """Stop the Feishu bot."""
        self._running = False
        if self._ws_client:
            try:
                self._ws_client.stop()
            except Exception as e:
                if isinstance(e, asyncio.CancelledError):
                    raise
                logger.warning(f"Error stopping WebSocket client: {e}")
        logger.info("Feishu bot stopped")
    
    def _add_reaction_sync(self, message_id: str, emoji_type: str) -> None:
        """Sync helper for adding reaction (runs in thread pool)."""
        try:
            request = CreateMessageReactionRequest.builder() \
                .message_id(message_id) \
                .request_body(
                    CreateMessageReactionRequestBody.builder()
                    .reaction_type(Emoji.builder().emoji_type(emoji_type).build())
                    .build()
                ).build()
            
            response = self._client.im.v1.message_reaction.create(request)
            
            if not response.success():
                logger.warning(f"Failed to add reaction: code={response.code}, msg={response.msg}")
            else:
                logger.debug(f"Added {emoji_type} reaction to message {message_id}")
        except Exception as e:
            logger.warning(f"Error adding reaction: {e}")

    async def _add_reaction(self, message_id: str, emoji_type: str = "THUMBSUP") -> None:
        """
        Add a reaction emoji to a message (non-blocking).
        
        Common emoji types: THUMBSUP, OK, EYES, DONE, OnIt, HEART
        """
        if not self._client or not Emoji:
            return
        
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, self._add_reaction_sync, message_id, emoji_type)
    
    # Regex to match markdown tables (header + separator + data rows)
    _TABLE_RE = re.compile(
        r"((?:^[ \t]*\|.+\|[ \t]*\n)(?:^[ \t]*\|[-:\s|]+\|[ \t]*\n)(?:^[ \t]*\|.+\|[ \t]*\n?)+)",
        re.MULTILINE,
    )

    _HEADING_RE = re.compile(r"^(#{1,6})\s+(.+)$", re.MULTILINE)

    _CODE_BLOCK_RE = re.compile(r"(```[\s\S]*?```)", re.MULTILINE)

    @staticmethod
    def _parse_md_table(table_text: str) -> dict | None:
        """Parse a markdown table into a Feishu table element."""
        lines = [l.strip() for l in table_text.strip().split("\n") if l.strip()]
        if len(lines) < 3:
            return None
        split = lambda l: [c.strip() for c in l.strip("|").split("|")]
        headers = split(lines[0])
        rows = [split(l) for l in lines[2:]]
        columns = [{"tag": "column", "name": f"c{i}", "display_name": h, "width": "auto"}
                   for i, h in enumerate(headers)]
        return {
            "tag": "table",
            "page_size": len(rows) + 1,
            "columns": columns,
            "rows": [{f"c{i}": r[i] if i < len(r) else "" for i in range(len(headers))} for r in rows],
        }

    def _build_card_elements(self, content: str) -> list[dict]:
        """Split content into div/markdown + table elements for Feishu card."""
        elements, last_end = [], 0
        for m in self._TABLE_RE.finditer(content):
            before = content[last_end:m.start()]
            if before.strip():
                elements.extend(self._split_headings(before))
            elements.append(self._parse_md_table(m.group(1)) or {"tag": "markdown", "content": m.group(1)})
            last_end = m.end()
        remaining = content[last_end:]
        if remaining.strip():
            elements.extend(self._split_headings(remaining))
        return elements or [{"tag": "markdown", "content": content}]

    def _split_headings(self, content: str) -> list[dict]:
        """Split content by headings, converting headings to div elements."""
        protected = content
        code_blocks = []
        for m in self._CODE_BLOCK_RE.finditer(content):
            code_blocks.append(m.group(1))
            protected = protected.replace(m.group(1), f"\x00CODE{len(code_blocks)-1}\x00", 1)

        elements = []
        last_end = 0
        for m in self._HEADING_RE.finditer(protected):
            before = protected[last_end:m.start()].strip()
            if before:
                elements.append({"tag": "markdown", "content": before})
            level = len(m.group(1))
            text = m.group(2).strip()
            elements.append({
                "tag": "div",
                "text": {
                    "tag": "lark_md",
                    "content": f"**{text}**",
                },
            })
            last_end = m.end()
        remaining = protected[last_end:].strip()
        if remaining:
            elements.append({"tag": "markdown", "content": remaining})

        for i, cb in enumerate(code_blocks):
            for el in elements:
                if el.get("tag") == "markdown":
                    el["content"] = el["content"].replace(f"\x00CODE{i}\x00", cb)

        return elements or [{"tag": "markdown", "content": content}]

    def _upload_image_sync(self, image_path: str) -> str | None:
        """Upload a local image synchronously to get an image_key."""
        if not self._client:
            return None
        try:
            with open(image_path, "rb") as f:
                request = CreateImageRequest.builder() \
                    .request_body(
                        CreateImageRequestBody.builder()
                        .image_type("message")
                        .image(f)
                        .build()
                    ).build()
                response = self._client.im.v1.image.create(request)
                if response.success():
                    # Response structure: data -> image_key usually, check lark sdk
                    # It's an object, so we access with dot notation
                    if hasattr(response.data, "image_key"):
                        return response.data.image_key
                logger.error(f"Feishu image upload failed: code={response.code}, msg={response.msg}")
                return None
        except Exception as e:
            logger.error(f"Feishu image upload error: {e}")
            return None

    async def _upload_images(self, media_paths: list[str]) -> list[str]:
        """Upload all image paths sequentially or concurrently (here sequentially for simplicity) and return keys."""
        from nanobot.channels.image_downloader import is_image_mime
        import mimetypes
        loop = asyncio.get_running_loop()
        image_keys = []
        for path in media_paths:
            mime = mimetypes.guess_type(path)[0] or "application/octet-stream"
            if is_image_mime(mime) or path.lower().endswith((".png", ".jpg", ".jpeg", ".gif", ".webp")):
                key = await loop.run_in_executor(None, self._upload_image_sync, path)
                if key:
                    image_keys.append(key)
        return image_keys

    async def send(self, msg: OutboundMessage) -> None:
        """Send a message through Feishu."""
        if not self._client:
            logger.warning("Feishu client not initialized")
            return
        
        try:
            # Determine receive_id_type based on chat_id format
            # open_id starts with "ou_", chat_id starts with "oc_"
            if msg.chat_id.startswith("oc_"):
                receive_id_type = "chat_id"
            else:
                receive_id_type = "open_id"
            
            # Pre-upload any image media before building the card
            image_keys = []
            if msg.media:
                image_keys = await self._upload_images(msg.media)
            
            # Build card with markdown + table support
            elements = self._build_card_elements(msg.content)
            
            # Embed the pre-uploaded images atomically into the interactive card Elements array
            image_elements = [
                {
                    "tag": "img",
                    "image_key": key,
                    "alt": {"tag": "plain_text", "content": "Image"}
                }
                for key in image_keys
            ]
            
            # Insert images at the beginning of the card elements
            elements = image_elements + elements
            
            card = {
                "config": {"wide_screen_mode": True},
                "elements": elements,
            }
            content = json.dumps(card, ensure_ascii=False)
            
            request = CreateMessageRequest.builder() \
                .receive_id_type(receive_id_type) \
                .request_body(
                    CreateMessageRequestBody.builder()
                    .receive_id(msg.chat_id)
                    .msg_type("interactive")
                    .content(content)
                    .build()
                ).build()
            
            response = self._client.im.v1.message.create(request)
            
            if not response.success():
                logger.error(
                    f"Failed to send Feishu message: code={response.code}, "
                    f"msg={response.msg}, log_id={response.get_log_id()}"
                )
            else:
                logger.debug(f"Feishu message sent to {msg.chat_id}")
                
        except Exception as e:
            if isinstance(e, asyncio.CancelledError):
                raise
            logger.error(f"Error sending Feishu message: {e}")
    
    def _on_message_sync(self, data: "P2ImMessageReceiveV1") -> None:
        """
        Sync handler for incoming messages (called from WebSocket thread).
        Schedules async handling in the main event loop.
        """
        if self._loop and self._loop.is_running():
            asyncio.run_coroutine_threadsafe(self._on_message(data), self._loop)
    
    async def _on_message(self, data: "P2ImMessageReceiveV1") -> None:
        """Handle incoming message from Feishu."""
        try:
            event = data.event
            message = event.message
            sender = event.sender
            
            # Deduplication check
            message_id = message.message_id
            if message_id in self._processed_message_ids:
                return
            self._processed_message_ids[message_id] = None
            
            # Trim cache: keep most recent 500 when exceeds 1000
            while len(self._processed_message_ids) > 1000:
                self._processed_message_ids.popitem(last=False)
            
            # Skip bot messages
            sender_type = sender.sender_type
            if sender_type == "bot":
                return
            
            sender_id = sender.sender_id.open_id if sender.sender_id else "unknown"
            chat_id = message.chat_id
            chat_type = message.chat_type  # "p2p" or "group"
            msg_type = message.message_type
            
            # Add reaction to indicate "seen"
            await self._add_reaction(message_id, "THUMBSUP")
            
            # Parse message content
            media_paths: list[str] = []

            if msg_type == "text":
                try:
                    content = json.loads(message.content).get("text", "")
                except json.JSONDecodeError:
                    content = message.content or ""
            elif msg_type == "post":
                try:
                    content_json = json.loads(message.content)
                    content = _extract_post_text(content_json)
                except (json.JSONDecodeError, TypeError):
                    content = message.content or ""
            elif msg_type == "image":
                # Download image via Feishu API
                image_key = ""
                try:
                    content_json = json.loads(message.content)
                    image_key = content_json.get("image_key", "")
                except (json.JSONDecodeError, TypeError):
                    pass
                if image_key:
                    path = await self._download_image(message_id, image_key)
                    if path:
                        media_paths.append(str(path))
                        content = "[User sent an image, please analyze its content]"
                    else:
                        content = "[image: download failed]"
                else:
                    content = "[image: no image_key found]"
            elif msg_type == "audio":
                file_key = ""
                try:
                    content_json = json.loads(message.content)
                    file_key = content_json.get("file_key", "")
                except (json.JSONDecodeError, TypeError):
                    pass
                    
                if file_key:
                    path = await self._download_audio(message_id, file_key)
                    if path:
                        media_paths.append(str(path))
                        from nanobot.providers.transcription import TranscriptionProviderFactory
                        from nanobot.config.loader import get_config
                        config = get_config()
                        transcriber = TranscriptionProviderFactory.get_default(config)
                        transcription = await transcriber.transcribe(path) if transcriber else ""
                        if transcription:
                            content = f"[transcription: {transcription}]"
                        else:
                            content = f"[audio: {path}]"
                    else:
                        content = "[audio: download failed]"
                else:
                    content = "[audio: no file_key found]"
            else:
                content = MSG_TYPE_MAP.get(msg_type, f"[{msg_type}]")
            
            if not content:
                return
            
            # Forward to message bus
            reply_to = chat_id if chat_type == "group" else sender_id
            await self._handle_message(
                sender_id=sender_id,
                chat_id=reply_to,
                content=content,
                media=media_paths,
                metadata={
                    "message_id": message_id,
                    "chat_type": chat_type,
                    "msg_type": msg_type,
                }
            )
            
        except Exception as e:
            if isinstance(e, asyncio.CancelledError):
                raise
            logger.error(f"Error processing Feishu message: {e}")

    def _download_image_sync(self, message_id: str, image_key: str) -> "Path | None":
        """Sync helper to download image via Feishu API (runs in thread pool).

        Uses ``client.im.v1.message_resource.get()`` to fetch the image binary.
        """
        if not self._client:
            return None
        try:
            request = GetMessageResourceRequest.builder() \
                .message_id(message_id) \
                .file_key(image_key) \
                .type("image") \
                .build()

            response = self._client.im.v1.message_resource.get(request)

            if not response.success():
                logger.error(
                    f"Feishu image download failed: code={response.code}, "
                    f"msg={response.msg}"
                )
                return None

            # response.file is a file-like object with the image bytes
            image_data = response.file.read() if response.file else None
            if not image_data:
                logger.warning(f"Feishu image download returned empty data for {image_key}")
                return None

            from nanobot.channels.image_downloader import save_image_bytes
            return save_image_bytes(image_data, f"feishu_{image_key[:20]}.jpg")

        except Exception as e:
            logger.error(f"Feishu image download error: {e}")
            return None

    async def _download_image(self, message_id: str, image_key: str) -> "Path | None":
        """Download image from Feishu (non-blocking, runs sync API in executor)."""
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            None, self._download_image_sync, message_id, image_key
        )

    def _download_audio_sync(self, message_id: str, file_key: str) -> "Path | None":
        """Sync helper to download audio via Feishu API."""
        if not self._client:
            return None
        try:
            request = GetMessageResourceRequest.builder() \
                .message_id(message_id) \
                .file_key(file_key) \
                .type("file") \
                .build()

            response = self._client.im.v1.message_resource.get(request)

            if not response.success():
                logger.error(f"Feishu audio download failed: {response.msg}")
                return None

            audio_data = response.file.read() if response.file else None
            if not audio_data:
                return None

            from nanobot.channels.image_downloader import MEDIA_DIR
            MEDIA_DIR.mkdir(parents=True, exist_ok=True)
            file_path = MEDIA_DIR / f"feishu_{file_key[:16]}.ogg"
            file_path.write_bytes(audio_data)
            return file_path
        except Exception as e:
            logger.error(f"Feishu audio download error: {e}")
            return None

    async def _download_audio(self, message_id: str, file_key: str) -> "Path | None":
        """Download audio from Feishu (non-blocking)."""
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self._download_audio_sync, message_id, file_key)

