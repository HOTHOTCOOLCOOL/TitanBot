"""Async message queue for decoupled channel-agent communication.

Phase 22D: Added topic-based domain event pub/sub for internal observability.
"""

import asyncio
from typing import Callable, Awaitable, Any

from loguru import logger

from nanobot.bus.events import InboundMessage, OutboundMessage, StreamEvent, DomainEvent


class MessageBus:
    """
    Async message bus that decouples chat channels from the agent core.
    
    Channels push messages to the inbound queue, and the agent processes
    them and pushes responses to the outbound queue.
    
    Phase 22D: Also supports typed domain events via publish_event/subscribe_event
    for internal system observability (tool execution, knowledge matching, etc.).
    """
    
    def __init__(self):
        self.inbound: asyncio.Queue[InboundMessage] = asyncio.Queue()
        self.outbound: asyncio.Queue[OutboundMessage] = asyncio.Queue()
        self._outbound_subscribers: dict[str, list[Callable[[OutboundMessage], Awaitable[None]]]] = {}
        self._global_subscribers: list[Callable[[OutboundMessage], Awaitable[None]]] = []
        self._inbound_subscribers: list[Callable[[InboundMessage], Awaitable[None]]] = []
        self._stream_subscribers: list[Callable[[StreamEvent], Awaitable[None]]] = []
        # Phase 22D: Domain event subscribers
        self._event_subscribers: dict[str, list[Callable[[DomainEvent], Awaitable[None]]]] = {}
        self._global_event_subscribers: list[Callable[[DomainEvent], Awaitable[None]]] = []
        self._running = False
    
    async def publish_inbound(self, msg: InboundMessage) -> None:
        """Publish a message from a channel to the agent."""
        await self.inbound.put(msg)
        for callback in self._inbound_subscribers:
            try:
                await callback(msg)
            except Exception as e:
                logger.error(f"Error in inbound subscriber: {e}")
                
    def subscribe_inbound_global(self, callback: Callable[[InboundMessage], Awaitable[None]]) -> None:
        """Subscribe to all inbound messages."""
        self._inbound_subscribers.append(callback)
    
    async def consume_inbound(self) -> InboundMessage:
        """Consume the next inbound message (blocks until available)."""
        return await self.inbound.get()
    
    async def publish_outbound(self, msg: OutboundMessage) -> None:
        """Publish a response from the agent to channels."""
        await self.outbound.put(msg)
    
    async def consume_outbound(self) -> OutboundMessage:
        """Consume the next outbound message (blocks until available)."""
        return await self.outbound.get()
    
    def subscribe_outbound(
        self, 
        channel: str, 
        callback: Callable[[OutboundMessage], Awaitable[None]]
    ) -> None:
        """Subscribe to outbound messages for a specific channel."""
        if channel not in self._outbound_subscribers:
            self._outbound_subscribers[channel] = []
        self._outbound_subscribers[channel].append(callback)
        
    def subscribe_global(
        self,
        callback: Callable[[OutboundMessage], Awaitable[None]]
    ) -> None:
        """Subscribe to all outbound messages across all channels."""
        self._global_subscribers.append(callback)
    
    async def dispatch_outbound(self) -> None:
        """
        Dispatch outbound messages to subscribed channels and global listeners.
        Run this as a background task.
        """
        self._running = True
        while self._running:
            try:
                msg = await asyncio.wait_for(self.outbound.get(), timeout=1.0)
                
                # Dispatch to global subscribers
                for callback in self._global_subscribers:
                    try:
                        await callback(msg)
                    except Exception as e:
                        logger.error(f"Error dispatching to global subscriber: {e}")
                        
                # Dispatch to specific channel subscribers
                subscribers = self._outbound_subscribers.get(msg.channel, [])
                for callback in subscribers:
                    try:
                        await callback(msg)
                    except Exception as e:
                        logger.error(f"Error dispatching to {msg.channel}: {e}")
            except asyncio.TimeoutError:
                continue
    
    def stop(self) -> None:
        """Stop the dispatcher loop."""
        self._running = False
    
    @property
    def inbound_size(self) -> int:
        """Number of pending inbound messages."""
        return self.inbound.qsize()
    
    @property
    def outbound_size(self) -> int:
        """Number of pending outbound messages."""
        return self.outbound.qsize()

    def subscribe_stream(
        self,
        callback: Callable[[StreamEvent], Awaitable[None]],
    ) -> None:
        """Subscribe to real-time streaming token events (Phase 21E)."""
        self._stream_subscribers.append(callback)

    async def publish_stream(self, event: StreamEvent) -> None:
        """Publish a streaming token event to all stream subscribers."""
        for callback in self._stream_subscribers:
            try:
                await callback(event)
            except Exception as e:
                logger.error(f"Error in stream subscriber: {e}")

    # ── Phase 22D: Domain Event Pub/Sub ─────────────────────────────

    def subscribe_event(
        self,
        event_type: str,
        callback: Callable[[DomainEvent], Awaitable[None]],
    ) -> None:
        """Subscribe to domain events by topic.

        Args:
            event_type: The event type to subscribe to, e.g. ``"tool_executed"``.
                Use ``"*"`` to receive **all** domain events (wildcard).
            callback: Async function called with the DomainEvent instance.
        """
        if event_type == "*":
            self._global_event_subscribers.append(callback)
        else:
            if event_type not in self._event_subscribers:
                self._event_subscribers[event_type] = []
            self._event_subscribers[event_type].append(callback)

    async def publish_event(self, event: DomainEvent) -> None:
        """Publish a domain event to all matching subscribers.

        Dispatches to:
        1. Topic-specific subscribers (matching ``event.event_type``)
        2. Wildcard ``"*"`` subscribers (receive everything)

        Errors in individual subscribers are logged but never propagate.
        """
        # Topic-specific subscribers
        for callback in self._event_subscribers.get(event.event_type, []):
            try:
                await callback(event)
            except Exception as e:
                logger.error(f"Error in event subscriber ({event.event_type}): {e}")

        # Wildcard subscribers
        for callback in self._global_event_subscribers:
            try:
                await callback(event)
            except Exception as e:
                logger.error(f"Error in global event subscriber: {e}")
