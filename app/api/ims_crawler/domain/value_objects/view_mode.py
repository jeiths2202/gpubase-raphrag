"""
View Mode Value Object - Represents UI display preference
"""

from enum import Enum


class ViewMode(str, Enum):
    """
    View mode enumeration for frontend display.

    Determines how search results are rendered to the user.
    """

    TABLE = "table"  # Traditional table view with sorting/filtering
    CARDS = "cards"  # Card-based grid layout
    GRAPH = "graph"  # Graph visualization showing relationships

    @classmethod
    def default(cls) -> "ViewMode":
        """Return default view mode"""
        return cls.TABLE

    def is_graphical(self) -> bool:
        """Check if view mode requires graph rendering"""
        return self == ViewMode.GRAPH
