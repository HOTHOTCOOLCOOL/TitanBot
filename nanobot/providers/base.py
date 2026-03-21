"""Base LLM provider interface."""

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ToolCallRequest:
    """A tool call request from the LLM."""
    id: str
    name: str
    arguments: dict[str, Any]


@dataclass
class LLMResponse:
    """Response from an LLM provider."""
    content: str | None
    tool_calls: list[ToolCallRequest] = field(default_factory=list)
    finish_reason: str = "stop"
    usage: dict[str, int] = field(default_factory=dict)
    reasoning_content: str | None = None  # Kimi, DeepSeek-R1 etc.
    
    @property
    def has_tool_calls(self) -> bool:
        """Check if response contains tool calls."""
        return len(self.tool_calls) > 0


class LLMProvider(ABC):
    """
    Abstract base class for LLM providers.
    
    Implementations should handle the specifics of each provider's API
    while maintaining a consistent interface.
    """
    
    def __init__(self, api_key: str | None = None, api_base: str | None = None):
        self.api_key = api_key
        self.api_base = api_base
    
    @abstractmethod
    async def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        model: str | None = None,
        max_tokens: int = 4096,
        temperature: float = 0.7,
    ) -> LLMResponse:
        """
        Send a chat completion request.
        
        Args:
            messages: List of message dicts with 'role' and 'content'.
            tools: Optional list of tool definitions.
            model: Model identifier (provider-specific).
            max_tokens: Maximum tokens in response.
            temperature: Sampling temperature.
        
        Returns:
            LLMResponse with content and/or tool calls.
        """
        pass
    
    async def stream_chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        model: str | None = None,
        max_tokens: int = 4096,
        temperature: float = 0.7,
    ) -> AsyncIterator["StreamChunk"]:
        """Stream a chat completion, yielding chunks as they arrive.

        Default implementation falls back to non-streaming chat().
        Subclasses should override for true token-by-token streaming.
        """
        response = await self.chat(
            messages=messages, tools=tools, model=model,
            max_tokens=max_tokens, temperature=temperature,
        )
        if response.content:
            yield StreamChunk(delta=response.content, finish_reason=response.finish_reason)
        yield StreamChunk(
            delta="", finish_reason=response.finish_reason or "stop",
            usage=response.usage, tool_calls=response.tool_calls,
            reasoning_content=response.reasoning_content,
        )

    @abstractmethod
    def get_default_model(self) -> str:
        """Get the default model for this provider."""
        pass


@dataclass
class StreamChunk:
    """A single chunk from a streaming LLM response."""
    delta: str = ""                                     # Incremental text token
    finish_reason: str | None = None                    # None while streaming, set on last chunk
    usage: dict[str, int] = field(default_factory=dict) # Only populated on final chunk
    tool_calls: list[ToolCallRequest] = field(default_factory=list)  # Accumulated tool calls (final chunk)
    reasoning_content: str | None = None                # Reasoning content (final chunk)
