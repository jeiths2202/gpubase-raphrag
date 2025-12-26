"""
Event System
Domain events and event bus implementation.
"""
from .domain_events import (
    DomainEvent,
    DocumentEvent,
    DocumentCreatedEvent,
    DocumentUpdatedEvent,
    DocumentDeletedEvent,
    DocumentProcessedEvent,
    UserEvent,
    UserCreatedEvent,
    UserLoginEvent,
    ProjectEvent,
    ProjectCreatedEvent,
    QueryEvent,
    QueryExecutedEvent
)
from .event_bus import (
    EventBus,
    EventHandler,
    get_event_bus
)

__all__ = [
    # Domain Events
    "DomainEvent",
    "DocumentEvent",
    "DocumentCreatedEvent",
    "DocumentUpdatedEvent",
    "DocumentDeletedEvent",
    "DocumentProcessedEvent",
    "UserEvent",
    "UserCreatedEvent",
    "UserLoginEvent",
    "ProjectEvent",
    "ProjectCreatedEvent",
    "QueryEvent",
    "QueryExecutedEvent",
    # Event Bus
    "EventBus",
    "EventHandler",
    "get_event_bus",
]
