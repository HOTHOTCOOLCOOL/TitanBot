import asyncio
"""Image generation providers (DALL-E, Seedance)."""

import os
import uuid
import httpx
from pathlib import Path
from typing import Any
from loguru import logger
from abc import ABC, abstractmethod


class BaseImageGenProvider(ABC):
    @abstractmethod
    async def generate_image(self, prompt: str, aspect_ratio: str = "1:1") -> "Path | None":
        pass


class OpenAIImageProvider(BaseImageGenProvider):
    """OpenAI DALL-E 3 image generation provider."""
    
    def __init__(self, api_key: str | None = None, api_base: str | None = None):
        self.api_key = api_key or os.environ.get("OPENAI_API_KEY")
        base = (api_base or "https://api.openai.com/v1").rstrip("/")
        self.api_url = f"{base}/images/generations"

    async def generate_image(self, prompt: str, aspect_ratio: str = "1:1") -> "Path | None":
        if not self.api_key:
            logger.error("OpenAI API key missing for image generation.")
            return None
            
        size = "1024x1024"
        if aspect_ratio == "16:9":
            size = "1792x1024"
        elif aspect_ratio == "9:16":
            size = "1024x1792"
            
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.post(
                    self.api_url,
                    headers={"Authorization": f"Bearer {self.api_key}"},
                    json={
                        "prompt": prompt,
                        "model": "dall-e-3",
                        "size": size,
                        "response_format": "url"
                    },
                    timeout=60.0
                )
                resp.raise_for_status()
                data = resp.json()
                if "data" in data and len(data["data"]) > 0:
                    image_url = data["data"][0].get("url")
                    if image_url:
                        return await download_image(image_url, client)
                return None
        except Exception as e:
            if isinstance(e, asyncio.CancelledError):
                raise
            logger.error(f"DALL-E generation failed: {e}")
            return None


class VolcengineImageProvider(BaseImageGenProvider):
    """Volcengine Seedance (Doubao) image generation provider."""
    
    def __init__(self, api_key: str | None = None):
        self.api_key = api_key or os.environ.get("ARK_API_KEY")
        # Ensure your custom model endpoint is handled according to Volcengine specs
        self.api_url = "https://ark.cn-beijing.volces.com/api/v3/images/generations"

    async def generate_image(self, prompt: str, aspect_ratio: str = "1:1") -> "Path | None":
        if not self.api_key:
            logger.error("Volcengine API key missing for image generation.")
            return None
            
        try:
            # Note: The model id needs to be replaced with the actual Endpoint ID 
            # for your Seedance deployment. We'll leave "ep-seedance" as placeholder.
            async with httpx.AsyncClient() as client:
                resp = await client.post(
                    self.api_url,
                    headers={"Authorization": f"Bearer {self.api_key}"},
                    json={
                        "model": "ep-seedance",
                        "prompt": prompt,
                    },
                    timeout=60.0
                )
                resp.raise_for_status()
                data = resp.json()
                if "data" in data and len(data["data"]) > 0:
                    image_url = data["data"][0].get("url")
                    if image_url:
                        return await download_image(image_url, client)
                return None
        except Exception as e:
            if isinstance(e, asyncio.CancelledError):
                raise
            logger.error(f"Volcengine generation failed: {e}")
            return None


async def download_image(url: str, client: httpx.AsyncClient) -> "Path | None":
    """Download image to media dir."""
    try:
        from nanobot.channels.image_downloader import MEDIA_DIR
        MEDIA_DIR.mkdir(parents=True, exist_ok=True)
        img_resp = await client.get(url, timeout=30.0)
        img_resp.raise_for_status()
        
        file_path = MEDIA_DIR / f"img_gen_{uuid.uuid4().hex[:8]}.png"
        file_path.write_bytes(img_resp.content)
        return file_path
    except Exception as e:
        if isinstance(e, asyncio.CancelledError):
            raise
        logger.error(f"Failed to download generated image: {e}")
        return None


class ImageProviderFactory:
    """Factory for image generation providers."""
    
    @staticmethod
    def get_default(config: Any) -> BaseImageGenProvider | None:
        """Prefers OpenAI, then Volcengine."""
        openai_key = getattr(config.providers.openai, "api_key", None)
        if openai_key:
            return OpenAIImageProvider(
                api_key=openai_key,
                api_base=getattr(config.providers.openai, "api_base", None)
            )
            
        volc_key = getattr(config.providers.volcengine, "api_key", None)
        if volc_key:
            return VolcengineImageProvider(api_key=volc_key)
            
        return None
