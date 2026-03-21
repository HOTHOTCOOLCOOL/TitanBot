"""Event types for the message bus.

Phase 22D: Added typed domain events for internal system observability.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class InboundMessage:
    """Message received from a chat channel."""
    
    channel: str  # telegram, discord, slack, whatsapp
    sender_id: str  # User identifier
    chat_id: str  # Chat/channel identifier
    content: str  # Message text
    timestamp: datetime = field(default_factory=datetime.now)
    media: list[str] = field(default_factory=list)  # Media URLs
    metadata: dict[str, Any] = field(default_factory=dict)  # Channel-specific data
    
    @property
    def session_key(self) -> str:
        """Unique key for session identification."""
        return f"{self.channel}:{self.chat_id}"


@dataclass
class OutboundMessage:
    """Message to send to a chat channel."""
    
    channel: str
    chat_id: str
    content: str
    reply_to: str | None = None
    media: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class StreamEvent:
    """Real-time streaming token event (Phase 21E).
    
    Carries incremental LLM output for live display in dashboard/channels.
    """
    channel: str
    chat_id: str
    delta: str              # Incremental text token
    done: bool = False      # True on the final chunk
    metadata: dict[str, Any] = field(default_factory=dict)


# ── Phase 22D: Typed Domain Events ──────────────────────────────────────────
# Lightweight internal events for observability and decoupling.
# No persistence, no serialization overhead — just in-memory callback dispatch.


@dataclass
class DomainEvent:
    """Base class for all internal domain events.

    All domain events carry an ``event_type`` tag used for topic-based routing
    on the MessageBus, plus an automatic timestamp.
    """
    event_type: str
    timestamp: datetime = field(default_factory=datetime.now)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a JSON-safe dict for Dashboard WebSocket forwarding."""
        d: dict[str, Any] = {
            "event_type": self.event_type,
            "timestamp": self.timestamp.isoformat(),
        }
        # Include all non-base fields from the concrete subclass
        for f_name in self.__dataclass_fields__:
            if f_name not in ("event_type", "timestamp", "metadata"):
                val = getattr(self, f_name)
                if val is not None:
                    d[f_name] = val
        if self.metadata:
            d["metadata"] = self.metadata
        return d


@dataclass
class ToolExecutedEvent(DomainEvent):
    """Emitted after a tool finishes execution."""
    tool_name: str = ""
    duration_ms: float = 0.0
    success: bool = True
    error: str | None = None

    def __post_init__(self):
        self.event_type = "tool_executed"


@dataclass
class KnowledgeMatchedEvent(DomainEvent):
    """Emitted when knowledge base returns a match for a user request."""
    task_key: str = ""
    confidence: float = 0.0
    match_method: str = ""  # exact, substring, bm25, dense

    def __post_init__(self):
        self.event_type = "knowledge_matched"


@dataclass
class MemoryConsolidatedEvent(DomainEvent):
    """Emitted after memory auto-consolidation completes."""
    session_key: str = ""
    messages_consolidated: int = 0

    def __post_init__(self):
        self.event_type = "memory_consolidated"


@dataclass
class SessionLifecycleEvent(DomainEvent):
    """Emitted on session create, expire, or clear."""
    session_key: str = ""
    action: str = ""  # created, expired, cleared

    def __post_init__(self):
        self.event_type = "session_lifecycle"


@dataclass
class SkillTriggeredEvent(DomainEvent):
    """Emitted when a skill is triggered and loaded."""
    skill_name: str = ""
    category: str = ""

    def __post_init__(self):
        self.event_type = "skill_triggered"


@dataclass
class CronJobEvent(DomainEvent):
    """Emitted on cron job status changes."""
    job_name: str = ""
    status: str = ""  # started, completed, failed
    error: str | None = None

    def __post_init__(self):
        self.event_type = "cron_job"
