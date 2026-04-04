"""Text To Speech (TTS) providers."""

from pathlib import Path
from loguru import logger
import uuid
import asyncio

class EdgeTTSProvider:
    """TTS provider using Microsoft Edge TTS (free, no key required)."""
    
    def __init__(self, voice: str = "zh-CN-XiaoxiaoNeural"):
        self.voice = voice
        from nanobot.channels.image_downloader import MEDIA_DIR
        self.media_dir = MEDIA_DIR
        self.media_dir.mkdir(parents=True, exist_ok=True)
        
    async def synthesize(self, text: str) -> "Path | None":
        """Synthesize text to speech using edge-tts CLI."""
        try:
            import edge_tts
        except ImportError:
            logger.error("edge_tts package not installed. Run: pip install edge-tts")
            return None

        if not text.strip():
            return None
            
        file_path = self.media_dir / f"tts_{uuid.uuid4().hex[:8]}.mp3"
        try:
            communicate = edge_tts.Communicate(text, self.voice)
            await communicate.save(str(file_path))
            logger.info(f"Synthesized TTS to {file_path}")
            return file_path
        except Exception as e:
            logger.error(f"Edge TTS error: {e}")
            return None
