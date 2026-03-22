"""Tests for LiteLLMProvider response parsing and model resolution."""

import json
import pytest
from unittest.mock import MagicMock, AsyncMock
from types import SimpleNamespace
from typing import Any

from nanobot.providers.base import LLMResponse, ToolCallRequest
from nanobot.providers.litellm_provider import LiteLLMProvider


def _make_mock_response(
    content: str | None = "Hello!",
    tool_calls: list | None = None,
    finish_reason: str = "stop",
    usage: dict | None = None,
    reasoning_content: str | None = None,
) -> Any:
    """Build a mock LiteLLM response object."""
    message = SimpleNamespace(
        content=content,
        tool_calls=tool_calls,
        reasoning_content=reasoning_content,
    )
    choice = SimpleNamespace(message=message, finish_reason=finish_reason)

    mock_usage = None
    if usage:
        mock_usage = SimpleNamespace(**usage)

    return SimpleNamespace(choices=[choice], usage=mock_usage)


def _make_tool_call(
    tc_id: str = "call_001",
    name: str = "exec",
    arguments: str | dict = '{"command": "ls"}',
) -> Any:
    """Build a mock tool call object."""
    args = arguments if isinstance(arguments, str) else json.dumps(arguments)
    func = SimpleNamespace(name=name, arguments=args)
    return SimpleNamespace(id=tc_id, function=func)


# ── Response Parsing ──

class TestParseResponse:
    """Test _parse_response for various LLM response formats."""

    def test_simple_text_response(self) -> None:
        provider = LiteLLMProvider.__new__(LiteLLMProvider)
        resp = _make_mock_response(content="Hello world!")
        result = provider._parse_response(resp)

        assert isinstance(result, LLMResponse)
        assert result.content == "Hello world!"
        assert result.tool_calls == []
        assert result.has_tool_calls is False
        assert result.finish_reason == "stop"

    def test_response_with_tool_calls(self) -> None:
        provider = LiteLLMProvider.__new__(LiteLLMProvider)
        tc = _make_tool_call("call_1", "read_file", '{"path": "/tmp/test.txt"}')
        resp = _make_mock_response(content=None, tool_calls=[tc])
        result = provider._parse_response(resp)

        assert result.has_tool_calls is True
        assert len(result.tool_calls) == 1
        assert result.tool_calls[0].name == "read_file"
        assert result.tool_calls[0].arguments == {"path": "/tmp/test.txt"}
        assert result.tool_calls[0].id == "call_1"

    def test_response_with_multiple_tool_calls(self) -> None:
        provider = LiteLLMProvider.__new__(LiteLLMProvider)
        tc1 = _make_tool_call("call_1", "exec", '{"command": "ls"}')
        tc2 = _make_tool_call("call_2", "read_file", '{"path": "a.txt"}')
        resp = _make_mock_response(content="Running...", tool_calls=[tc1, tc2])
        result = provider._parse_response(resp)

        assert result.has_tool_calls is True
        assert len(result.tool_calls) == 2
        assert result.tool_calls[0].name == "exec"
        assert result.tool_calls[1].name == "read_file"

    def test_response_with_usage(self) -> None:
        provider = LiteLLMProvider.__new__(LiteLLMProvider)
        resp = _make_mock_response(
            content="Hi",
            usage={"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150},
        )
        result = provider._parse_response(resp)

        assert result.usage == {
            "prompt_tokens": 100,
            "completion_tokens": 50,
            "total_tokens": 150,
        }

    def test_response_without_usage(self) -> None:
        provider = LiteLLMProvider.__new__(LiteLLMProvider)
        resp = _make_mock_response(content="Hi", usage=None)
        result = provider._parse_response(resp)
        assert result.usage == {}

    def test_response_with_reasoning_content(self) -> None:
        provider = LiteLLMProvider.__new__(LiteLLMProvider)
        resp = _make_mock_response(
            content="The answer is 42.",
            reasoning_content="Let me think... 6 * 7 = 42",
        )
        result = provider._parse_response(resp)

        assert result.content == "The answer is 42."
        assert result.reasoning_content == "Let me think... 6 * 7 = 42"

    def test_response_without_reasoning_content(self) -> None:
        provider = LiteLLMProvider.__new__(LiteLLMProvider)
        resp = _make_mock_response(content="Hello")
        result = provider._parse_response(resp)
        assert result.reasoning_content is None


# ── JSON Repair for Tool Arguments ──

class TestToolArgumentParsing:
    """Test that malformed JSON in tool arguments is repaired."""

    def test_valid_json_arguments(self) -> None:
        provider = LiteLLMProvider.__new__(LiteLLMProvider)
        tc = _make_tool_call("c1", "exec", '{"command": "echo hello"}')
        resp = _make_mock_response(tool_calls=[tc])
        result = provider._parse_response(resp)
        assert result.tool_calls[0].arguments == {"command": "echo hello"}

    def test_dict_arguments_passed_through(self) -> None:
        """When arguments are already a dict, they should pass through."""
        provider = LiteLLMProvider.__new__(LiteLLMProvider)
        tc = _make_tool_call("c1", "exec", {"command": "echo hello"})
        # Arguments is a dict → json.dumps → then json_repair.loads in _parse_response
        resp = _make_mock_response(tool_calls=[tc])
        result = provider._parse_response(resp)
        assert result.tool_calls[0].arguments == {"command": "echo hello"}


# ── Model Resolution ──

class TestModelResolution:
    """Test _resolve_model for prefix handling."""

    def test_gateway_applies_prefix(self) -> None:
        provider = LiteLLMProvider.__new__(LiteLLMProvider)
        gw = SimpleNamespace(
            litellm_prefix="openrouter",
            strip_model_prefix=False,
        )
        provider._gateway = gw
        result = provider._resolve_model("anthropic/claude-opus-4-5")
        assert result == "openrouter/anthropic/claude-opus-4-5"

    def test_gateway_strip_prefix(self) -> None:
        provider = LiteLLMProvider.__new__(LiteLLMProvider)
        gw = SimpleNamespace(
            litellm_prefix="aihubmix",
            strip_model_prefix=True,
        )
        provider._gateway = gw
        result = provider._resolve_model("openai/gpt-5")
        assert result == "aihubmix/gpt-5"

    def test_no_gateway_no_double_prefix(self) -> None:
        provider = LiteLLMProvider.__new__(LiteLLMProvider)
        provider._gateway = None
        # Model already has known prefix — behavior depends on registry
        result = provider._resolve_model("custom-model")
        # Should not crash
        assert isinstance(result, str)

    def test_already_prefixed_gateway_skips(self) -> None:
        provider = LiteLLMProvider.__new__(LiteLLMProvider)
        gw = SimpleNamespace(
            litellm_prefix="openrouter",
            strip_model_prefix=False,
        )
        provider._gateway = gw
        result = provider._resolve_model("openrouter/anthropic/claude-opus-4-5")
        assert result == "openrouter/anthropic/claude-opus-4-5"
        assert not result.startswith("openrouter/openrouter/")
