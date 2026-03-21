"""Shared image download helper for channel implementations.

Provides a common utility to save received image data to the local media directory,
avoiding duplication across Telegram, Discord, Feishu, etc.
"""

from __future__ import annotations

from pathlib import Path
from loguru import logger


# Central media directory — same as used by Telegram and Discord channels
MEDIA_DIR = Path.home() / ".nanobot" / "media"

# Image MIME types we recognise
_IMAGE_MIMES = frozenset({
    "image/jpeg", "image/png", "image/gif", "image/webp",
    "image/bmp", "image/tiff", "image/svg+xml",
})


def is_image_mime(mime: str) -> bool:
    """Check whether *mime* is a recognised image MIME type."""
    return mime.lower().strip() in _IMAGE_MIMES


def save_image_bytes(data: bytes, filename: str) -> Path | None:
    """Save raw image bytes to the shared media directory.

    Args:
        data: Raw image binary data.
        filename: Target filename (e.g. ``"abc123.jpg"``).

    Returns:
        Absolute path to the saved file, or ``None`` on failure.
    """
    if not data:
        logger.warning("image_downloader: empty data, skipping save")
        return None
    try:
        MEDIA_DIR.mkdir(parents=True, exist_ok=True)
        file_path = MEDIA_DIR / filename
        file_path.write_bytes(data)
        logger.debug(f"image_downloader: saved {len(data)} bytes → {file_path}")
        return file_path
    except Exception as e:
        logger.error(f"image_downloader: failed to save {filename}: {e}")
        return None
