import asyncio
"""Voice transcription providers."""

import os
from pathlib import Path
from typing import Any
from abc import ABC, abstractmethod

import httpx
from loguru import logger


class BaseTranscriptionProvider(ABC):
    """Base class for transcription providers."""
    
    @abstractmethod
    async def transcribe(self, file_path: str | Path) -> str:
        """Transcribe an audio file."""
        pass


class GroqTranscriptionProvider(BaseTranscriptionProvider):
    """
    Voice transcription provider using Groq's Whisper API.
    
    Groq offers extremely fast transcription with a generous free tier.
    """
    
    def __init__(self, api_key: str | None = None):
        self.api_key = api_key or os.environ.get("GROQ_API_KEY")
        self.api_url = "https://api.groq.com/openai/v1/audio/transcriptions"
    
    async def transcribe(self, file_path: str | Path) -> str:
        """
        Transcribe an audio file using Groq.
        
        Args:
            file_path: Path to the audio file.
            
        Returns:
            Transcribed text.
        """
        if not self.api_key:
            logger.warning("Groq API key not configured for transcription")
            return ""
        
        path = Path(file_path)
        if not path.exists():
            logger.error(f"Audio file not found: {file_path}")
            return ""
        
        try:
            async with httpx.AsyncClient() as client:
                with open(path, "rb") as f:
                    files = {
                        "file": (path.name, f),
                        "model": (None, "whisper-large-v3"),
                    }
                    headers = {
                        "Authorization": f"Bearer {self.api_key}",
                    }
                    
                    response = await client.post(
                        self.api_url,
                        headers=headers,
                        files=files,
                        timeout=60.0
                    )
                    
                    response.raise_for_status()
                    data = response.json()
                    return data.get("text", "")
                    
        except Exception as e:
            if isinstance(e, asyncio.CancelledError):
                raise
            logger.error(f"Groq transcription error: {e}")
            return ""


class OpenAITranscriptionProvider(BaseTranscriptionProvider):
    """Voice transcription provider using OpenAI's Whisper API."""
    
    def __init__(self, api_key: str | None = None, api_base: str | None = None):
        self.api_key = api_key or os.environ.get("OPENAI_API_KEY")
        base = (api_base or "https://api.openai.com/v1").rstrip("/")
        self.api_url = f"{base}/audio/transcriptions"
    
    async def transcribe(self, file_path: str | Path) -> str:
        """Transcribe an audio file using OpenAI."""
        if not self.api_key:
            logger.warning("OpenAI API key not configured for transcription")
            return ""
        
        path = Path(file_path)
        if not path.exists():
            logger.error(f"Audio file not found: {file_path}")
            return ""
        
        try:
            async with httpx.AsyncClient() as client:
                with open(path, "rb") as f:
                    files = {
                        "file": (path.name, f),
                        "model": (None, "whisper-1"),
                    }
                    headers = {
                        "Authorization": f"Bearer {self.api_key}",
                    }
                    
                    response = await client.post(
                        self.api_url,
                        headers=headers,
                        files=files,
                        timeout=60.0
                    )
                    
                    response.raise_for_status()
                    data = response.json()
                    return data.get("text", "")
                    
        except Exception as e:
            if isinstance(e, asyncio.CancelledError):
                raise
            logger.error(f"OpenAI transcription error: {e}")
            return ""


class TranscriptionProviderFactory:
    """Factory to get the appropriate transcription provider."""

    @staticmethod
    def get_default(config: Any) -> BaseTranscriptionProvider | None:
        """
        Get the configured transcription provider.
        Checks Groq first, then OpenAI.
        """
        if getattr(config.providers.groq, "api_key", None):
            return GroqTranscriptionProvider(api_key=config.providers.groq.api_key)
        
        openai_key = getattr(config.providers.openai, "api_key", None)
        if openai_key:
            return OpenAITranscriptionProvider(
                api_key=openai_key, 
                api_base=getattr(config.providers.openai, "api_base", None)
            )
        
        return None
