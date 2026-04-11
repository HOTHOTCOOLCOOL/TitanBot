"""Tool for generating images (DALL-E, Seedance)."""

from typing import Any, Callable, Awaitable
from loguru import logger

from nanobot.agent.tools.base import Tool
from nanobot.bus.events import OutboundMessage
from nanobot.config.loader import get_config
from nanobot.agent.i18n import msg as i18n_msg
from nanobot.agent.capability import CapabilityTag


class DrawImageTool(Tool):
    """
    Generate an image based on a prompt and send it directly to the user.
    Uses OpenAI DALL-E or Volcengine Seedance based on configuration.
    """
    
    @property
    def name(self) -> str:
        return "draw_image"
        
    @property
    def static_tags(self) -> CapabilityTag:
        return CapabilityTag.SYS_COMMUNICATION | CapabilityTag.MUTATIVE

        
    @property
    def description(self) -> str:
        return "Generate an image based on a prompt and send it to the user. Use this when the user asks you to literally 'draw', 'paint', or 'generate an image' of something."

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "prompt": {
                    "type": "string",
                    "description": "Detailed description of the image to generate.",
                },
                "aspect_ratio": {
                    "type": "string",
                    "description": "Target aspect ratio of the image (e.g. '1:1', '16:9', '9:16').",
                    "enum": ["1:1", "16:9", "9:16"]
                }
            },
            "required": ["prompt"],
        }

    def __init__(
        self, 
        send_callback: Callable[[OutboundMessage], Awaitable[None]] | None = None,
        default_channel: str = "",
        default_chat_id: str = ""
    ):
        self._send_callback = send_callback
        self._default_channel = default_channel
        self._default_chat_id = default_chat_id

    def set_context(self, channel: str, chat_id: str) -> None:
        """Set the current message context."""
        self._default_channel = channel
        self._default_chat_id = chat_id

    async def execute(self, **kwargs: Any) -> str:
        prompt = kwargs.get("prompt", "")
        aspect_ratio = kwargs.get("aspect_ratio", "1:1")
        
        if not prompt:
            return "Error: no prompt provided."

        config = get_config()
        from nanobot.providers.image_gen import ImageProviderFactory
        
        provider = ImageProviderFactory.get_default(config)
        if not provider:
            return "Error: No image generation provider configured."
            
        logger.info(f"Generating image for prompt: {prompt}")

        try:
            image_path = await provider.generate_image(prompt, aspect_ratio)
            
            if not image_path:
                return "Error: Image generation failed."

            if self._send_callback and self._default_channel and self._default_chat_id:
                # Send the image directly as an outbound media message bypass
                out_msg = OutboundMessage(
                    channel=self._default_channel,
                    chat_id=self._default_chat_id,
                    content="",  # Just the image
                    media=[str(image_path)],
                    metadata={}
                )
                await self._send_callback(out_msg)
                return "Success: Image generated and sent to the user successfully. (You do not need to include any image output in your final message, only acknowledge it)."
            
            # If no callback (e.g. testing), just return the path
            return f"Image generated successfully at {image_path}. Please use the 'message' tool to send this image path to the user."
        except Exception as e:
            return f"Error communicating with image provider: {e}"
