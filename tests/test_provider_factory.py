"""Tests for ProviderFactory."""

import pytest
from unittest.mock import MagicMock
from nanobot.providers.factory import ProviderFactory
from nanobot.providers.litellm_provider import LiteLLMProvider
from nanobot.providers.custom_provider import CustomProvider
from nanobot.providers.openai_codex_provider import OpenAICodexProvider

def test_get_provider_litellm():
    mock_config = MagicMock()
    mock_provider_conf = MagicMock()
    mock_provider_conf.api_key = "sk-test"
    mock_provider_conf.extra_headers = None
    mock_config.get_provider.return_value = mock_provider_conf
    mock_config.get_api_base.return_value = None
    mock_config.get_provider_name.return_value = "anthropic"
    
    provider = ProviderFactory.get_provider("anthropic/claude-3-opus", mock_config)
    assert isinstance(provider, LiteLLMProvider)
    assert provider.api_key == "sk-test"

def test_get_provider_custom():
    mock_config = MagicMock()
    mock_provider_conf = MagicMock()
    mock_provider_conf.api_key = "sk-custom"
    mock_provider_conf.extra_headers = None
    mock_config.get_provider.return_value = mock_provider_conf
    mock_config.get_api_base.return_value = "http://localhost:8000"
    mock_config.get_provider_name.return_value = "custom"
    
    provider = ProviderFactory.get_provider("my-custom-model", mock_config)
    assert isinstance(provider, CustomProvider)
    assert provider.api_base == "http://localhost:8000"
    assert provider.api_key == "sk-custom"
