"""Tests for Phase 22D — Architecture Evolution.

Covers:
- AE1: Event-Driven Architecture Enhancement (domain events, pub/sub)
- AE2: Session Save Optimization (metadata dirty flag, append-only)
"""

import asyncio
import inspect
import json
import time
import tempfile
from pathlib import Path
from datetime import datetime
from unittest.mock import AsyncMock, patch

import pytest

from nanobot.bus.events import (
    DomainEvent,
    ToolExecutedEvent,
    KnowledgeMatchedEvent,
    MemoryConsolidatedEvent,
    SessionLifecycleEvent,
    SkillTriggeredEvent,
    CronJobEvent,
)
from nanobot.bus.queue import MessageBus
from nanobot.session.manager import Session, SessionManager


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# AE1: Domain Event Data Classes
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


class TestDomainEventTypes:
    """Test domain event dataclass definitions and serialization."""

    def test_domain_event_base_fields(self):
        """DomainEvent has event_type, timestamp, metadata fields."""
        evt = DomainEvent(event_type="test")
        assert evt.event_type == "test"
        assert isinstance(evt.timestamp, datetime)
        assert evt.metadata == {}

    def test_tool_executed_event_auto_type(self):
        """ToolExecutedEvent.__post_init__ sets event_type automatically."""
        evt = ToolExecutedEvent(event_type="", tool_name="web_search", duration_ms=123.4)
        assert evt.event_type == "tool_executed"
        assert evt.tool_name == "web_search"
        assert evt.duration_ms == 123.4
        assert evt.success is True
        assert evt.error is None

    def test_knowledge_matched_event_auto_type(self):
        """KnowledgeMatchedEvent.__post_init__ sets event_type."""
        evt = KnowledgeMatchedEvent(event_type="", task_key="查天气", confidence=0.95)
        assert evt.event_type == "knowledge_matched"
        assert evt.task_key == "查天气"

    def test_memory_consolidated_event(self):
        evt = MemoryConsolidatedEvent(event_type="", session_key="tg:123", messages_consolidated=20)
        assert evt.event_type == "memory_consolidated"
        assert evt.session_key == "tg:123"
        assert evt.messages_consolidated == 20

    def test_session_lifecycle_event(self):
        evt = SessionLifecycleEvent(event_type="", session_key="cli:direct", action="expired")
        assert evt.event_type == "session_lifecycle"
        assert evt.action == "expired"

    def test_skill_triggered_event(self):
        evt = SkillTriggeredEvent(event_type="", skill_name="email-sender", category="infra_ops")
        assert evt.event_type == "skill_triggered"
        assert evt.skill_name == "email-sender"

    def test_cron_job_event(self):
        evt = CronJobEvent(event_type="", job_name="daily_report", status="completed")
        assert evt.event_type == "cron_job"
        assert evt.status == "completed"

    def test_to_dict_serialization(self):
        """to_dict() produces a JSON-safe dict with all fields."""
        evt = ToolExecutedEvent(
            event_type="", tool_name="outlook", duration_ms=500.0,
            success=True, error=None,
        )
        d = evt.to_dict()
        assert d["event_type"] == "tool_executed"
        assert d["tool_name"] == "outlook"
        assert d["duration_ms"] == 500.0
        assert d["success"] is True
        assert "timestamp" in d
        # Should be JSON-serializable
        json.dumps(d, ensure_ascii=False)

    def test_to_dict_excludes_none_error(self):
        """to_dict() omits error field when None."""
        evt = ToolExecutedEvent(event_type="", tool_name="web", success=True, error=None)
        d = evt.to_dict()
        assert "error" not in d

    def test_to_dict_includes_error_when_present(self):
        """to_dict() includes error field when set."""
        evt = ToolExecutedEvent(event_type="", tool_name="web", success=False, error="timeout")
        d = evt.to_dict()
        assert d["error"] == "timeout"


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# AE1: MessageBus Domain Event Pub/Sub
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


class TestMessageBusDomainPubSub:
    """Test MessageBus domain event subscription and publishing."""

    @pytest.mark.asyncio
    async def test_publish_event_to_topic_subscriber(self):
        """publish_event dispatches to matching topic subscribers."""
        bus = MessageBus()
        received = []

        async def handler(event):
            received.append(event)

        bus.subscribe_event("tool_executed", handler)

        evt = ToolExecutedEvent(event_type="tool_executed", tool_name="web")
        await bus.publish_event(evt)

        assert len(received) == 1
        assert received[0].tool_name == "web"

    @pytest.mark.asyncio
    async def test_publish_event_no_cross_delivery(self):
        """Events are only delivered to matching topic subscribers."""
        bus = MessageBus()
        received = []

        async def handler(event):
            received.append(event)

        bus.subscribe_event("tool_executed", handler)

        # Publish a different event type
        evt = KnowledgeMatchedEvent(event_type="knowledge_matched", task_key="test")
        await bus.publish_event(evt)

        assert len(received) == 0  # Should not receive

    @pytest.mark.asyncio
    async def test_wildcard_subscriber_receives_all(self):
        """subscribe_event('*', ...) receives all event types."""
        bus = MessageBus()
        received = []

        async def handler(event):
            received.append(event)

        bus.subscribe_event("*", handler)

        await bus.publish_event(ToolExecutedEvent(event_type="tool_executed", tool_name="a"))
        await bus.publish_event(KnowledgeMatchedEvent(event_type="knowledge_matched", task_key="b"))
        await bus.publish_event(CronJobEvent(event_type="cron_job", job_name="c"))

        assert len(received) == 3

    @pytest.mark.asyncio
    async def test_subscriber_error_isolation(self):
        """Error in one subscriber does not block others."""
        bus = MessageBus()
        received = []

        async def bad_handler(event):
            raise RuntimeError("deliberate error")

        async def good_handler(event):
            received.append(event)

        bus.subscribe_event("tool_executed", bad_handler)
        bus.subscribe_event("tool_executed", good_handler)

        evt = ToolExecutedEvent(event_type="tool_executed", tool_name="test")
        await bus.publish_event(evt)

        assert len(received) == 1  # good_handler still receives

    @pytest.mark.asyncio
    async def test_wildcard_error_isolation(self):
        """Error in wildcard subscriber does not block other wildcard subscribers."""
        bus = MessageBus()
        received = []

        async def bad_handler(event):
            raise RuntimeError("deliberate error")

        async def good_handler(event):
            received.append(event)

        bus.subscribe_event("*", bad_handler)
        bus.subscribe_event("*", good_handler)

        await bus.publish_event(ToolExecutedEvent(event_type="tool_executed"))

        assert len(received) == 1

    @pytest.mark.asyncio
    async def test_topic_and_wildcard_both_receive(self):
        """Both topic-specific and wildcard subscribers receive the event."""
        bus = MessageBus()
        topic_received = []
        wildcard_received = []

        async def topic_handler(event):
            topic_received.append(event)

        async def wildcard_handler(event):
            wildcard_received.append(event)

        bus.subscribe_event("tool_executed", topic_handler)
        bus.subscribe_event("*", wildcard_handler)

        await bus.publish_event(ToolExecutedEvent(event_type="tool_executed", tool_name="x"))

        assert len(topic_received) == 1
        assert len(wildcard_received) == 1

    @pytest.mark.asyncio
    async def test_no_subscribers_no_error(self):
        """Publishing with no subscribers does not raise."""
        bus = MessageBus()
        await bus.publish_event(ToolExecutedEvent(event_type="tool_executed"))
        # Should not raise

    @pytest.mark.asyncio
    async def test_multiple_topic_subscribers(self):
        """Multiple subscribers on the same topic all receive the event."""
        bus = MessageBus()
        received_a = []
        received_b = []

        async def handler_a(event):
            received_a.append(event)

        async def handler_b(event):
            received_b.append(event)

        bus.subscribe_event("cron_job", handler_a)
        bus.subscribe_event("cron_job", handler_b)

        await bus.publish_event(CronJobEvent(event_type="cron_job", job_name="test"))

        assert len(received_a) == 1
        assert len(received_b) == 1


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# AE1: Event Wiring in AgentLoop (source-level checks)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


class TestEventWiring:
    """Verify domain events are wired in the agent loop source code."""

    def test_loop_imports_domain_events(self):
        """AgentLoop module imports ToolExecutedEvent etc."""
        import nanobot.agent.loop as loop_mod
        assert hasattr(loop_mod, "ToolExecutedEvent")
        assert hasattr(loop_mod, "KnowledgeMatchedEvent")
        assert hasattr(loop_mod, "MemoryConsolidatedEvent")

    def test_loop_emits_tool_executed_event(self):
        """_run_agent_loop source contains publish_event(ToolExecutedEvent(...))."""
        from nanobot.agent.loop import AgentLoop
        source = inspect.getsource(AgentLoop._run_agent_loop)
        assert "publish_event" in source
        assert "ToolExecutedEvent" in source

    def test_loop_emits_knowledge_matched_event(self):
        """_process_message source contains KnowledgeMatchedEvent."""
        from nanobot.agent.loop import AgentLoop
        source = inspect.getsource(AgentLoop._process_message)
        assert "KnowledgeMatchedEvent" in source

    def test_loop_emits_memory_consolidated_event(self):
        """_execute_with_llm source contains MemoryConsolidatedEvent."""
        from nanobot.agent.loop import AgentLoop
        source = inspect.getsource(AgentLoop._execute_with_llm)
        assert "MemoryConsolidatedEvent" in source

    @pytest.mark.skipif(
        not __import__("importlib").util.find_spec("fastapi"),
        reason="fastapi not installed",
    )
    def test_dashboard_has_event_subscription(self):
        """Dashboard module exports init_event_subscription."""
        from nanobot.dashboard.app import init_event_subscription
        assert callable(init_event_subscription)

    def test_bus_exports_all_domain_events(self):
        """bus __init__ exports all domain event types."""
        import nanobot.bus as bus_mod
        for name in [
            "DomainEvent", "ToolExecutedEvent", "KnowledgeMatchedEvent",
            "MemoryConsolidatedEvent", "SessionLifecycleEvent",
            "SkillTriggeredEvent", "CronJobEvent",
        ]:
            assert hasattr(bus_mod, name), f"Missing export: {name}"


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# AE2: Session Save Optimization
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


@pytest.fixture
def session_workspace(tmp_path):
    """Create a workspace with sessions dir."""
    (tmp_path / "sessions").mkdir()
    return tmp_path


class TestSessionDirtyFlag:
    """Test the metadata dirty flag mechanism."""

    def test_new_session_is_dirty(self):
        """Freshly created Session has _metadata_dirty=True."""
        s = Session(key="test:1")
        assert s._metadata_dirty is True

    def test_add_message_does_not_dirty(self):
        """add_message() only adds messages, does not set _metadata_dirty."""
        s = Session(key="test:1")
        s._metadata_dirty = False
        s.add_message("user", "hello")
        assert s._metadata_dirty is False

    def test_clear_sets_dirty(self):
        """clear() sets _metadata_dirty=True."""
        s = Session(key="test:1")
        s._metadata_dirty = False
        s.clear()
        assert s._metadata_dirty is True

    def test_clear_pending_sets_dirty(self):
        """clear_pending() sets _metadata_dirty=True."""
        s = Session(key="test:1")
        s._metadata_dirty = False
        s.clear_pending()
        assert s._metadata_dirty is True

    def test_mark_metadata_dirty(self):
        """mark_metadata_dirty() sets the flag."""
        s = Session(key="test:1")
        s._metadata_dirty = False
        s.mark_metadata_dirty()
        assert s._metadata_dirty is True


class TestSessionSaveOptimization:
    """Test the append-only vs full-rewrite save optimization."""

    def test_first_save_full_rewrite(self, session_workspace):
        """First save always does full rewrite."""
        mgr = SessionManager(session_workspace)
        s = Session(key="test:1")
        s.add_message("user", "hello")
        s.add_message("assistant", "hi")

        mgr.save(s)

        path = session_workspace / "sessions" / "test_1.jsonl"
        assert path.exists()
        lines = path.read_text(encoding="utf-8").strip().split("\n")
        assert len(lines) == 3  # 1 metadata + 2 messages

    def test_second_save_append_only(self, session_workspace):
        """Second save with only new messages uses append mode."""
        mgr = SessionManager(session_workspace)
        s = Session(key="test:1")
        s.add_message("user", "hello")
        mgr.save(s)

        # Now add more messages WITHOUT changing metadata
        s.add_message("assistant", "hi there")
        s.add_message("user", "thanks")
        mgr.save(s)

        path = session_workspace / "sessions" / "test_1.jsonl"
        lines = path.read_text(encoding="utf-8").strip().split("\n")
        # Should be: 1 metadata + 3 messages total
        assert len(lines) == 4

    def test_no_duplicate_messages_on_append(self, session_workspace):
        """Append mode should not duplicate existing messages."""
        mgr = SessionManager(session_workspace)
        s = Session(key="test:1")
        s.add_message("user", "msg 1")
        mgr.save(s)

        s.add_message("assistant", "msg 2")
        mgr.save(s)

        s.add_message("user", "msg 3")
        mgr.save(s)

        # Reload and verify
        mgr.invalidate("test:1")
        loaded = mgr.get_or_create("test:1")
        assert len(loaded.messages) == 3
        assert loaded.messages[0]["content"] == "msg 1"
        assert loaded.messages[1]["content"] == "msg 2"
        assert loaded.messages[2]["content"] == "msg 3"

    def test_metadata_dirty_triggers_full_rewrite(self, session_workspace):
        """When metadata is dirty, save does a full rewrite."""
        mgr = SessionManager(session_workspace)
        s = Session(key="test:1")
        s.add_message("user", "msg 1")
        mgr.save(s)

        # Change metadata
        s.pending_save = {"key": "test_task"}
        s.mark_metadata_dirty()
        s.add_message("assistant", "msg 2")
        mgr.save(s)

        # Reload and verify metadata is correct
        mgr.invalidate("test:1")
        loaded = mgr.get_or_create("test:1")
        assert len(loaded.messages) == 2
        assert loaded.pending_save is not None
        assert loaded.pending_save["key"] == "test_task"

    def test_clear_resets_saved_count(self, session_workspace):
        """clear() resets _last_saved_msg_count so next save does full rewrite."""
        mgr = SessionManager(session_workspace)
        s = Session(key="test:1")
        s.add_message("user", "msg")
        mgr.save(s)

        s.clear()
        s.add_message("user", "fresh msg")
        mgr.save(s)

        mgr.invalidate("test:1")
        loaded = mgr.get_or_create("test:1")
        assert len(loaded.messages) == 1
        assert loaded.messages[0]["content"] == "fresh msg"

    def test_round_trip_chinese_content(self, session_workspace):
        """Chinese text survives save/load round-trip."""
        mgr = SessionManager(session_workspace)
        s = Session(key="test:cn")
        s.add_message("user", "帮我查一下明天的天气预报")
        s.add_message("assistant", "好的，让我为您查询天气。")
        mgr.save(s)

        mgr.invalidate("test:cn")
        loaded = mgr.get_or_create("test:cn")
        assert loaded.messages[0]["content"] == "帮我查一下明天的天气预报"
        assert loaded.messages[1]["content"] == "好的，让我为您查询天气。"

    def test_append_only_multiple_cycles(self, session_workspace):
        """Multiple append-only save cycles produce correct result."""
        mgr = SessionManager(session_workspace)
        s = Session(key="test:multi")
        # Initial save
        s.add_message("user", "m1")
        mgr.save(s)

        # 5 more append cycles
        for i in range(2, 7):
            s.add_message("user" if i % 2 == 0 else "assistant", f"m{i}")
            mgr.save(s)

        # Reload from disk
        mgr.invalidate("test:multi")
        loaded = mgr.get_or_create("test:multi")
        assert len(loaded.messages) == 6
        for i, msg in enumerate(loaded.messages, 1):
            assert msg["content"] == f"m{i}"
