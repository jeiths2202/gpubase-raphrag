"""Domain Value Objects - Immutable value types"""

from .search_intent import SearchIntent, SearchIntentType
from .view_mode import ViewMode

__all__ = [
    "SearchIntent",
    "SearchIntentType",
    "ViewMode",
]
