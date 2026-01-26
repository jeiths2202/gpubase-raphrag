"""
Event Bus Implementation
In-memory event bus with async support.
"""
from typing import (
    Type, TypeVar, Dict, List, Callable, Any, Optional,
    Awaitable, Union, Set
)
from dataclasses import dataclass, field
from datetime import datetime, timezone
from collections import defaultdict
import asyncio
import logging
import traceback

from .domain_events import DomainEvent, EventPriority

logger = logging.getLogger(__name__)

T = TypeVar('T', bound=DomainEvent)

# Event handler type
EventHandler = Callable[[DomainEvent], Union[None, Awaitable[None]]]


@dataclass
class EventSubscription:
    """Represents a subscription to an event type"""
    event_type: Type[DomainEvent]
    handler: EventHandler
    priority: int = 0
    is_async: bool = True
    filter_func: Optional[Callable[[DomainEvent], bool]] = None

    def matches(self, event: DomainEvent) -> bool:
        """Check if this subscription matches the event"""
        if not isinstance(event, self.event_type):
            return False
        if self.filter_func and not self.filter_func(event):
            return False
        return True


@dataclass
class EventRecord:
    """Record of a published event"""
    event: DomainEvent
    published_at: datetime
    handlers_called: int = 0
    handlers_succeeded: int = 0
    handlers_failed: int = 0
    errors: List[str] = field(default_factory=list)


class EventBus:
    """
    In-memory event bus for publishing and subscribing to domain events.

    Features:
    - Async and sync handler support
    - Event filtering
    - Priority-based handler ordering
    - Error handling and recovery
    - Event history for debugging
    """

    def __init__(
        self,
        max_history: int = 1000,
        propagate_errors: bool = False
    ):
        self._subscriptions: Dict[Type[DomainEvent], List[EventSubscription]] = defaultdict(list)
        self._global_handlers: List[EventSubscription] = []
        self._history: List[EventRecord] = []
        self._max_history = max_history
        self._propagate_errors = propagate_errors
        self._paused = False
        self._pending_events: List[DomainEvent] = []

    def subscribe(
        self,
        event_type: Type[T],
        handler: Callable[[T], Union[None, Awaitable[None]]],
        priority: int = 0,
        filter_func: Optional[Callable[[T], bool]] = None
    ) -> None:
        """
        Subscribe to events of a specific type.

        Args:
            event_type: Type of event to subscribe to
            handler: Function to call when event is published
            priority: Higher priority handlers are called first
            filter_func: Optional function to filter events
        """
        subscription = EventSubscription(
            event_type=event_type,
            handler=handler,
            priority=priority,
            is_async=asyncio.iscoroutinefunction(handler),
            filter_func=filter_func
        )

        self._subscriptions[event_type].append(subscription)
        # Sort by priority (higher first)
        self._subscriptions[event_type].sort(key=lambda s: -s.priority)

        logger.debug(
            f"Subscribed to {event_type.__name__} with priority {priority}"
        )

    def subscribe_all(
        self,
        handler: Callable[[DomainEvent], Union[None, Awaitable[None]]],
        priority: int = 0
    ) -> None:
        """
        Subscribe to all events.

        Args:
            handler: Function to call for any event
            priority: Higher priority handlers are called first
        """
        subscription = EventSubscription(
            event_type=DomainEvent,
            handler=handler,
            priority=priority,
            is_async=asyncio.iscoroutinefunction(handler)
        )

        self._global_handlers.append(subscription)
        self._global_handlers.sort(key=lambda s: -s.priority)

        logger.debug(f"Subscribed global handler with priority {priority}")

    def unsubscribe(
        self,
        event_type: Type[DomainEvent],
        handler: EventHandler
    ) -> bool:
        """
        Unsubscribe a handler from an event type.

        Returns:
            True if handler was found and removed
        """
        subs = self._subscriptions.get(event_type, [])
        for i, sub in enumerate(subs):
            if sub.handler == handler:
                subs.pop(i)
                return True
        return False

    async def publish(self, event: DomainEvent) -> EventRecord:
        """
        Publish an event to all subscribers.

        Args:
            event: Event to publish

        Returns:
            EventRecord with publishing results
        """
        if self._paused:
            self._pending_events.append(event)
            logger.debug(f"Event {event.event_type} queued (bus paused)")
            return EventRecord(event=event, published_at=datetime.now(timezone.utc))

        record = EventRecord(
            event=event,
            published_at=datetime.now(timezone.utc)
        )

        # Get all matching handlers
        handlers: List[EventSubscription] = []

        # Add type-specific handlers
        for event_class in type(event).__mro__:
            if event_class in self._subscriptions:
                for sub in self._subscriptions[event_class]:
                    if sub.matches(event):
                        handlers.append(sub)

        # Add global handlers
        for sub in self._global_handlers:
            handlers.append(sub)

        # Sort by priority
        handlers.sort(key=lambda s: -s.priority)

        # Execute handlers
        for sub in handlers:
            record.handlers_called += 1
            try:
                if sub.is_async:
                    await sub.handler(event)
                else:
                    sub.handler(event)
                record.handlers_succeeded += 1

            except Exception as e:
                record.handlers_failed += 1
                error_msg = f"{type(e).__name__}: {str(e)}"
                record.errors.append(error_msg)

                logger.error(
                    f"Handler failed for {event.event_type}: {error_msg}",
                    extra={
                        "event_id": event.event_id,
                        "event_type": event.event_type,
                        "handler": sub.handler.__name__
                    }
                )

                if self._propagate_errors:
                    raise

        # Record history
        self._add_to_history(record)

        logger.debug(
            f"Published {event.event_type}: "
            f"{record.handlers_succeeded}/{record.handlers_called} handlers succeeded"
        )

        return record

    def publish_sync(self, event: DomainEvent) -> None:
        """
        Publish event synchronously (for non-async contexts).
        Creates a new event loop if needed.
        """
        try:
            loop = asyncio.get_running_loop()
            # We're in an async context, create a task
            asyncio.create_task(self.publish(event))
        except RuntimeError:
            # No running loop, run synchronously
            asyncio.run(self.publish(event))

    def pause(self) -> None:
        """Pause event processing (events are queued)"""
        self._paused = True
        logger.info("Event bus paused")

    async def resume(self) -> List[EventRecord]:
        """Resume event processing and process queued events"""
        self._paused = False
        logger.info(f"Event bus resumed, processing {len(self._pending_events)} pending events")

        records = []
        for event in self._pending_events:
            record = await self.publish(event)
            records.append(record)

        self._pending_events.clear()
        return records

    def _add_to_history(self, record: EventRecord) -> None:
        """Add record to history, maintaining max size"""
        self._history.append(record)
        if len(self._history) > self._max_history:
            self._history.pop(0)

    def get_history(
        self,
        event_type: Optional[Type[DomainEvent]] = None,
        limit: int = 100
    ) -> List[EventRecord]:
        """
        Get event history.

        Args:
            event_type: Filter by event type
            limit: Maximum records to return

        Returns:
            List of event records (most recent first)
        """
        records = self._history[::-1]  # Reverse for most recent first

        if event_type:
            records = [r for r in records if isinstance(r.event, event_type)]

        return records[:limit]

    def get_stats(self) -> Dict[str, Any]:
        """Get event bus statistics"""
        event_type_counts: Dict[str, int] = defaultdict(int)
        total_published = 0
        total_succeeded = 0
        total_failed = 0

        for record in self._history:
            event_type_counts[record.event.event_type] += 1
            total_published += 1
            total_succeeded += record.handlers_succeeded
            total_failed += record.handlers_failed

        return {
            "total_subscriptions": sum(len(subs) for subs in self._subscriptions.values()),
            "global_handlers": len(self._global_handlers),
            "total_published": total_published,
            "total_handlers_succeeded": total_succeeded,
            "total_handlers_failed": total_failed,
            "pending_events": len(self._pending_events),
            "is_paused": self._paused,
            "event_type_counts": dict(event_type_counts)
        }

    def clear_history(self) -> None:
        """Clear event history"""
        self._history.clear()

    def clear_subscriptions(self) -> None:
        """Clear all subscriptions (for testing)"""
        self._subscriptions.clear()
        self._global_handlers.clear()


# Decorator for easy subscription
def on_event(
    event_type: Type[T],
    priority: int = 0,
    filter_func: Optional[Callable[[T], bool]] = None
):
    """
    Decorator for subscribing a function to an event type.

    Usage:
        @on_event(DocumentCreatedEvent)
        async def handle_document_created(event: DocumentCreatedEvent):
            # Handle event
            pass
    """
    def decorator(func: Callable[[T], Union[None, Awaitable[None]]]):
        # Store metadata on function for later registration
        if not hasattr(func, '_event_subscriptions'):
            func._event_subscriptions = []

        func._event_subscriptions.append({
            'event_type': event_type,
            'priority': priority,
            'filter_func': filter_func
        })

        return func

    return decorator


# Global event bus instance
_event_bus: Optional[EventBus] = None


def get_event_bus() -> EventBus:
    """Get the global event bus instance"""
    global _event_bus
    if _event_bus is None:
        _event_bus = EventBus()
    return _event_bus


def reset_event_bus() -> None:
    """Reset the global event bus (for testing)"""
    global _event_bus
    _event_bus = None
