"""Agent routing and intent classification logic."""

import re
from loguru import logger
from collections import OrderedDict
from typing import Any

from nanobot.providers.base import LLMProvider

# ── Phase 39: Fast Path Chitchat Regex (Exhaustive Ping List) ──
_CHITCHAT_REGEX = r"^(你*好[呀啊么吗]*|你在这里么|干[嘛啥哈]呢|在干[嘛啥哈]|你干什么呢|还?在[吗么不]|早|早上好|中午好|下午好|晚上好|晚安|hello|hi|测试|test|ping|1|111|123|在不在|有人在[吗么]?)[！？\s~]*$"

class IntentClassifier:
    """Classifies the intent of user messages to optimize routing."""
    
    @classmethod
    def detect_intent(cls, text: str) -> str:
        """
        Detect the user intent based on the text.
        
        Returns:
            "chitchat_safe" if it matches chitchat/ping patterns.
            "task" otherwise.
        """
        if re.match(_CHITCHAT_REGEX, text, re.IGNORECASE):
            return "chitchat_safe"
        return "task"


class ModelRouter:
    """Handles dynamic routing of target model and provider provisioning."""
    
    _VLM_RECENCY_WINDOW = 2
    
    @classmethod
    def determine_target_model(
        cls,
        messages: list[dict],
        default_model: str,
        default_provider: LLMProvider,
        config: Any,
        vlm_provider_cache: OrderedDict[str, LLMProvider],
        target_model_override: str | None = None,
    ) -> tuple[str, LLMProvider]:
        """
        Determine the target model to use for the current turn.
        Handles target overrides, VLM detecting for images, and maintains an LRU
        provider instance cache.
        
        Args:
            messages: Conversation messages.
            default_model: The default agent model.
            default_provider: The default agent LLM provider.
            config: Main node config.
            vlm_provider_cache: OrderedDict acting as an LRU cache.
            target_model_override: Explicit override model.
            
        Returns:
            Tuple of (target_model_name, provider_instance).
        """
        target_model = default_model
        provider_for_turn = default_provider
        
        if target_model_override:
            target_model = target_model_override
            logger.debug(f"Target model overridden to: {target_model}")
            p_conf = config.get_provider(target_model)
            if not p_conf:
                logger.warning(f"Provider config missing for override {target_model}, falling back to default")
                target_model = default_model
            else:
                provider_for_turn = cls._get_or_create_provider(
                    target_model, config, vlm_provider_cache
                )
        
        if not target_model_override and config.agents.vlm.enabled and config.agents.vlm.model:
            has_image = False
            
            # Find the most recent user message's index, fallback to last 5 messages if none found
            start_idx = max(0, len(messages) - 5)
            for i in range(len(messages) - 1, -1, -1):
                if messages[i].get("role") == "user":
                    start_idx = min(i, start_idx)  # Include the last user message
                    break
                    
            recent_msgs = messages[start_idx:]
            
            for msg in recent_msgs:
                if isinstance(msg.get("content"), list):
                    for block in msg["content"]:
                        if block.get("type") == "image_url":
                            has_image = True
                            break
                if has_image:
                    break
            
            if has_image:
                target_model = config.agents.vlm.model
                logger.debug(f"Image detected in recent context (from user turn). Routing to VLM: {target_model}")
                
                # B4: Graceful fallback if VLM provider config is missing
                p_conf = config.get_provider(target_model)
                if not p_conf:
                    logger.warning(f"VLM provider config missing for {target_model}, falling back to default model")
                    target_model = default_model
                else:
                    provider_for_turn = cls._get_or_create_provider(
                        target_model, config, vlm_provider_cache
                    )
            else:
                logger.debug(f"No images in recent context. Using main model: {target_model}")
        
        return target_model, provider_for_turn

    @staticmethod
    def _get_or_create_provider(
        model_name: str, 
        config: Any, 
        cache: OrderedDict[str, LLMProvider]
    ) -> LLMProvider:
        """DESIGN-5: Cache VLM provider to avoid re-creating per turn."""
        if model_name not in cache:
            # Phase 31 Retro: evict oldest if cache full (LRU)
            if len(cache) >= 4:
                cache.popitem(last=False)
            from nanobot.providers.factory import ProviderFactory
            cache[model_name] = ProviderFactory.get_provider(model_name, config)
        else:
            # B-2 fix: LRU semantics - move to end on hit
            cache.move_to_end(model_name)
        return cache[model_name]
