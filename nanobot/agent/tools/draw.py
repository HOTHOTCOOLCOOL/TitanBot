"""Tool for generating images (DALL-E, Seedance)."""

from typing import Any, ClassVar
from loguru import logger

from nanobot.agent.tools.base import BaseTool, ProcessContext
from nanobot.bus.events import OutboundMessage
from nanobot.config.loader import get_config
from nanobot.agent.i18n import msg as i18n_msg


class DrawImageTool(BaseTool):
    """
    Generate an image based on a prompt and send it directly to the user.
    Uses OpenAI DALL-E or Volcengine Seedance based on configuration.
    """
    
    # We assign RiskTier.READ_ONLY here because the impact is local cost,
    # no system destruction. Could be RESOURCE_CONSUMING.
    # To keep it from constantly nagging the user, READ_ONLY is fine.
    
    _config_schema: ClassVar[dict[str, Any]] = {
        "name": "draw_image",
        "description": "Generate an image based on a prompt and send it to the user. Use this when the user asks you to literally 'draw', 'paint', or 'generate an image' of something.",
        "parameters": {
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
        },
    }

    def __init__(self, **kwargs: Any):
        super().__init__(**kwargs)
        # Store a callback to let us inject outbound messages to the bus
        self._send_callback = kwargs.get("send_callback")

    def _get_schema_impl(self) -> dict[str, Any]:
        return self._config_schema

    async def _execute_impl(self, args: dict[str, Any], context: ProcessContext | None = None) -> Any:
        prompt = args.get("prompt", "")
        aspect_ratio = args.get("aspect_ratio", "1:1")
        
        if not prompt:
            return "Error: no prompt provided."

        config = get_config()
        from nanobot.providers.image_gen import ImageProviderFactory
        
        provider = ImageProviderFactory.get_default(config)
        if not provider:
            return "Error: No image generation provider configured."
            
        logger.info(f"Generating image for prompt: {prompt}")
        
        # We start typing to let user know we are doing long work
        if self._send_callback and context:
            # We don't have a direct start_typing callback here, but AgentLoop auto-acks on progress.
            pass

        image_path = await provider.generate_image(prompt, aspect_ratio)
        
        if not image_path:
            return "Error: Image generation failed."

        if self._send_callback and context:
            # Send the image directly as an outbound media message bypass
            out_msg = OutboundMessage(
                channel=context.channel,
                chat_id=context.chat_id,
                content="",  # Just the image
                media=[str(image_path)],
                metadata={}
            )
            await self._send_callback(out_msg)
            return "Success: Image generated and sent to the user successfully. (You do not need to include any image output in your final message, only acknowledge it)."
        
        # If no callback (e.g. testing), just return the path
        return f"Image generated successfully at {image_path}"
