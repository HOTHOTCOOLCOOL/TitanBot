"""Tests for BFF request parameter sanitization."""

import json
import sys
from pathlib import Path


# BFF modules live in the ./bff directory and use script-style imports.
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "bff"))

from bff_server import (
    content_filter_error,
    is_content_filter_error,
    sanitize_reasoning_model_kwargs,
)


def test_sanitize_reasoning_model_kwargs_drops_unsupported_stop() -> None:
    kwargs = {
        "temperature": 0.7,
        "top_p": 0.9,
        "stop": ["###"],
        "max_tokens": 128,
    }

    sanitize_reasoning_model_kwargs("azure/gpt-5.4-mini", kwargs)

    assert "temperature" not in kwargs
    assert "top_p" not in kwargs
    assert "stop" not in kwargs
    assert kwargs["max_tokens"] == 128


def test_sanitize_reasoning_model_kwargs_leaves_non_reasoning_models_alone() -> None:
    kwargs = {
        "temperature": 0.7,
        "top_p": 0.9,
        "stop": ["###"],
        "max_tokens": 128,
    }

    sanitize_reasoning_model_kwargs("azure/gpt-4o", kwargs)

    assert kwargs["temperature"] == 0.7
    assert kwargs["top_p"] == 0.9
    assert kwargs["stop"] == ["###"]
    assert kwargs["max_tokens"] == 128


def test_is_content_filter_error_recognizes_azure_policy_message() -> None:
    message = (
        "OpenAIException - The response was filtered due to the prompt triggering "
        "Azure OpenAI's content management policy."
    )

    assert is_content_filter_error(message) is True
    assert is_content_filter_error("Azure OpenAI content filter blocked the prompt.") is True
    assert is_content_filter_error("BadRequestError: invalid request body") is False


def test_content_filter_error_returns_openai_shape() -> None:
    response = content_filter_error()
    payload = json.loads(response.body.decode("utf-8"))

    assert response.status_code == 400
    assert payload["error"]["type"] == "content_filter"
    assert payload["error"]["message"]
