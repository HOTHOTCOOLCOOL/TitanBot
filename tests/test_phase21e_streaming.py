"""Tests for Phase 21E: Streaming Response Delivery.

Covers: StreamChunk/StreamEvent dataclasses, provider stream_chat(),
MessageBus stream pub/sub, config flag, dashboard /ws/stream endpoint,
and AgentLoop._stream_llm_call integration.
"""
import asyncio
import inspect
import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from pathlib import Path


# ── StreamChunk dataclass ─────────────────────────────────────

def test_stream_chunk_defaults():
    """StreamChunk should have sensible defaults."""
    from nanobot.providers.base import StreamChunk
    chunk = StreamChunk()
    assert chunk.delta == ""
    assert chunk.finish_reason is None
    assert chunk.usage == {}
    assert chunk.tool_calls == []
    assert chunk.reasoning_content is None


def test_stream_chunk_with_data():
    """StreamChunk should hold delta text and metadata."""
    from nanobot.providers.base import StreamChunk, ToolCallRequest
    tc = ToolCallRequest(id="tc1", name="shell", arguments={"command": "ls"})
    chunk = StreamChunk(
        delta="Hello",
        finish_reason="stop",
        usage={"total_tokens": 100},
        tool_calls=[tc],
        reasoning_content="thinking...",
    )
    assert chunk.delta == "Hello"
    assert chunk.finish_reason == "stop"
    assert chunk.usage["total_tokens"] == 100
    assert len(chunk.tool_calls) == 1
    assert chunk.tool_calls[0].name == "shell"
    assert chunk.reasoning_content == "thinking..."


# ── StreamEvent dataclass ─────────────────────────────────────

def test_stream_event_defaults():
    """StreamEvent should carry channel, chat_id, delta, done."""
    from nanobot.bus.events import StreamEvent
    evt = StreamEvent(channel="cli", chat_id="user1", delta="Hi")
    assert evt.channel == "cli"
    assert evt.chat_id == "user1"
    assert evt.delta == "Hi"
    assert evt.done is False
    assert evt.metadata == {}


def test_stream_event_done():
    """StreamEvent done=True marks end of stream."""
    from nanobot.bus.events import StreamEvent
    evt = StreamEvent(channel="telegram", chat_id="123", delta="", done=True)
    assert evt.done is True
    assert evt.delta == ""


# ── Base provider fallback stream_chat ────────────────────────

@pytest.mark.asyncio
async def test_base_provider_fallback_stream():
    """Base LLMProvider.stream_chat() should fall back to non-streaming chat()."""
    from nanobot.providers.base import LLMProvider, LLMResponse, StreamChunk

    class FakeProvider(LLMProvider):
        async def chat(self, messages, tools=None, model=None,
                       max_tokens=4096, temperature=0.7):
            return LLMResponse(content="Hello world", finish_reason="stop",
                               usage={"total_tokens": 10})
        def get_default_model(self):
            return "fake-model"

    provider = FakeProvider()
    chunks = []
    async for chunk in provider.stream_chat(messages=[{"role": "user", "content": "hi"}]):
        chunks.append(chunk)

    assert len(chunks) == 2  # content chunk + final chunk
    assert chunks[0].delta == "Hello world"
    assert chunks[1].delta == ""
    assert chunks[1].finish_reason == "stop"
    assert chunks[1].usage == {"total_tokens": 10}


# ── MessageBus stream pub/sub ─────────────────────────────────

@pytest.mark.asyncio
async def test_message_bus_stream_pubsub():
    """MessageBus.publish_stream() should deliver to all subscribers."""
    from nanobot.bus.queue import MessageBus
    from nanobot.bus.events import StreamEvent

    bus = MessageBus()
    received = []

    async def on_stream(evt):
        received.append(evt)

    bus.subscribe_stream(on_stream)

    evt = StreamEvent(channel="cli", chat_id="u1", delta="tok")
    await bus.publish_stream(evt)
    assert len(received) == 1
    assert received[0].delta == "tok"


@pytest.mark.asyncio
async def test_message_bus_multiple_stream_subscribers():
    """Multiple stream subscribers should all receive events."""
    from nanobot.bus.queue import MessageBus
    from nanobot.bus.events import StreamEvent

    bus = MessageBus()
    r1, r2 = [], []

    bus.subscribe_stream(lambda e: asyncio.coroutine(lambda: r1.append(e))() if False else _async_append(r1, e))
    bus.subscribe_stream(lambda e: _async_append(r2, e))

    evt = StreamEvent(channel="ws", chat_id="c1", delta="a")
    await bus.publish_stream(evt)
    assert len(r1) == 1
    assert len(r2) == 1


async def _async_append(lst, item):
    lst.append(item)


@pytest.mark.asyncio
async def test_message_bus_stream_error_isolation():
    """A failing subscriber should not prevent others from receiving events."""
    from nanobot.bus.queue import MessageBus
    from nanobot.bus.events import StreamEvent

    bus = MessageBus()
    received = []

    async def _fail(evt):
        raise RuntimeError("boom")

    async def _ok(evt):
        received.append(evt)

    bus.subscribe_stream(_fail)
    bus.subscribe_stream(_ok)

    await bus.publish_stream(StreamEvent(channel="t", chat_id="c", delta="x"))
    assert len(received) == 1


# ── StreamingConfig ───────────────────────────────────────────

def test_streaming_config_defaults():
    """StreamingConfig should default to enabled=True."""
    from nanobot.config.schema import StreamingConfig
    cfg = StreamingConfig()
    assert cfg.enabled is True


def test_agents_config_has_streaming():
    """AgentsConfig should include the streaming field."""
    from nanobot.config.schema import AgentsConfig
    ac = AgentsConfig()
    assert hasattr(ac, "streaming")
    assert ac.streaming.enabled is True


def test_streaming_config_disable():
    """StreamingConfig should support enabled=False."""
    from nanobot.config.schema import StreamingConfig
    cfg = StreamingConfig(enabled=False)
    assert cfg.enabled is False


# ── Dashboard /ws/stream endpoint ─────────────────────────────

@pytest.mark.skipif(
    not __import__("importlib").util.find_spec("fastapi"),
    reason="fastapi not installed",
)
def test_dashboard_stream_endpoint_exists():
    """Dashboard should have /ws/stream WebSocket route."""
    from nanobot.dashboard.app import app
    routes = [r.path for r in app.routes]
    assert "/ws/stream" in routes


@pytest.mark.skipif(
    not __import__("importlib").util.find_spec("fastapi"),
    reason="fastapi not installed",
)
def test_dashboard_init_stream_subscription():
    """init_stream_subscription should register with bus.subscribe_stream."""
    from nanobot.dashboard.app import init_stream_subscription
    mock_bus = MagicMock()
    init_stream_subscription(mock_bus)
    mock_bus.subscribe_stream.assert_called_once()


# ── AgentLoop._stream_llm_call ────────────────────────────────

def test_agent_loop_has_stream_method():
    """AgentLoop should have _stream_llm_call method."""
    from nanobot.agent.loop import AgentLoop
    assert hasattr(AgentLoop, "_stream_llm_call")
    assert asyncio.iscoroutinefunction(AgentLoop._stream_llm_call)


def test_agent_loop_streaming_gated_by_config():
    """AgentLoop._run_agent_loop should check streaming config."""
    from nanobot.agent.loop import AgentLoop
    source = inspect.getsource(AgentLoop._run_agent_loop)
    assert "streaming" in source
    assert "_stream_llm_call" in source


# ── LiteLLMProvider.stream_chat ───────────────────────────────

def test_litellm_provider_has_stream_chat():
    """LiteLLMProvider should override stream_chat."""
    from nanobot.providers.litellm_provider import LiteLLMProvider
    assert hasattr(LiteLLMProvider, "stream_chat")
    # Should be defined on the class itself (not just inherited)
    assert "stream_chat" in LiteLLMProvider.__dict__


def test_litellm_stream_chat_uses_stream_true():
    """LiteLLMProvider.stream_chat should pass stream=True to acompletion."""
    from nanobot.providers.litellm_provider import LiteLLMProvider
    source = inspect.getsource(LiteLLMProvider.stream_chat)
    assert '"stream": True' in source or "'stream': True" in source


def test_litellm_stream_chat_has_fallback():
    """LiteLLMProvider.stream_chat should fall back on error."""
    from nanobot.providers.litellm_provider import LiteLLMProvider
    source = inspect.getsource(LiteLLMProvider.stream_chat)
    assert "super().stream_chat" in source


# ── StreamChunk import from providers.base ────────────────────

def test_stream_chunk_importable():
    """StreamChunk should be importable from providers.base."""
    from nanobot.providers.base import StreamChunk
    assert StreamChunk is not None


def test_stream_event_importable():
    """StreamEvent should be importable from bus.events."""
    from nanobot.bus.events import StreamEvent
    assert StreamEvent is not None
