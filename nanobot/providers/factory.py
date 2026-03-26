"""Factory for instantiating LLM providers."""

from typing import Any

from loguru import logger
from nanobot.providers.base import LLMProvider


class ProviderFactory:
    """Factory for creating LLMProvider instances based on model name and config."""

    @staticmethod
    def get_provider(
        model: str,
        config: Any,
    ) -> LLMProvider:
        """
        Get the appropriate LLM provider for the given model.
        
        Args:
            model: The target model name (e.g., 'anthropic/claude-3-opus').
            config: The global Configuration instance.
            
        Returns:
            An instantiated LLMProvider subclass.
        """
        from nanobot.providers.registry import find_by_model, find_gateway, find_by_name
        
        provider_config = config.get_provider(model)
        api_key = provider_config.api_key if provider_config else None
        api_base = config.get_api_base(model)
        extra_headers = provider_config.extra_headers if provider_config else None
        provider_name = config.get_provider_name(model)
        
        spec = None
        if provider_name:
            spec = find_by_name(provider_name)
            
        if not spec:
            spec = find_gateway(provider_name, api_key, api_base) or find_by_model(model)
        
        
        if spec:
            if spec.is_direct and spec.name == "custom":
                from nanobot.providers.custom_provider import CustomProvider
                logger.debug(f"ProviderFactory: Instantiating CustomProvider for {model}")
                return CustomProvider(api_key=api_key, api_base=api_base, default_model=model)
            elif spec.is_oauth and spec.name == "openai_codex":
                from nanobot.providers.openai_codex_provider import OpenAICodexProvider
                logger.debug(f"ProviderFactory: Instantiating OpenAICodexProvider for {model}")
                return OpenAICodexProvider(default_model=model)
                
        # Default fallback to LiteLLMProvider
        from nanobot.providers.litellm_provider import LiteLLMProvider
        logger.debug(f"ProviderFactory: Instantiating LiteLLMProvider for {model}")
        return LiteLLMProvider(
            api_key=api_key,
            api_base=api_base,
            default_model=model,
            extra_headers=extra_headers,
            provider_name=provider_name
        )
