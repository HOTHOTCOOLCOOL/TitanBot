"""Message bus module for decoupled channel-agent communication."""

from nanobot.bus.events import InboundMessage, OutboundMessage
from nanobot.bus.queue import MessageBus
from nanobot.bus.whiteboard import SharedMemoryBoard, global_whiteboard

__all__ = ["MessageBus", "InboundMessage", "OutboundMessage", "SharedMemoryBoard", "global_whiteboard"]
