"""Message bus module for decoupled channel-agent communication."""

from nanobot.bus.events import (
    InboundMessage, OutboundMessage, StreamEvent,
    DomainEvent, ToolExecutedEvent, KnowledgeMatchedEvent,
    MemoryConsolidatedEvent, SessionLifecycleEvent,
    SkillTriggeredEvent, CronJobEvent,
)
from nanobot.bus.queue import MessageBus
from nanobot.bus.whiteboard import SharedMemoryBoard, global_whiteboard

__all__ = [
    "MessageBus", "InboundMessage", "OutboundMessage", "StreamEvent",
    "SharedMemoryBoard", "global_whiteboard",
    # Phase 22D: Domain events
    "DomainEvent", "ToolExecutedEvent", "KnowledgeMatchedEvent",
    "MemoryConsolidatedEvent", "SessionLifecycleEvent",
    "SkillTriggeredEvent", "CronJobEvent",
]
