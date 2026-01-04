"""
Search Intent Value Object - Represents parsed search intent from NL query
"""

from dataclasses import dataclass
from enum import Enum
from typing import Optional, List, Dict, Any


class SearchIntentType(str, Enum):
    """Search intent type enumeration"""
    KEYWORD_SEARCH = "keyword_search"  # Simple keyword matching
    STATUS_FILTER = "status_filter"  # Filter by status (open, resolved, etc.)
    PRIORITY_FILTER = "priority_filter"  # Filter by priority
    DATE_RANGE = "date_range"  # Date range queries
    ASSIGNEE_FILTER = "assignee_filter"  # Filter by assignee
    PROJECT_FILTER = "project_filter"  # Filter by project
    COMPLEX_QUERY = "complex_query"  # Multiple filters combined
    SEMANTIC_SEARCH = "semantic_search"  # Vector-based similarity search


@dataclass(frozen=True)
class SearchIntent:
    """
    Value Object representing parsed search intent.

    Immutable value object created by NL parser (NVIDIA NIM).
    Contains all information needed to execute IMS search.
    """

    # Intent Type
    intent_type: SearchIntentType

    # Parsed Filters
    keywords: List[str]
    status_filters: List[str]
    priority_filters: List[str]
    assignee_filters: List[str]
    project_filters: List[str]

    # Date Range
    date_from: Optional[str] = None
    date_to: Optional[str] = None

    # Semantic Search
    semantic_query: Optional[str] = None  # For vector search

    # Advanced Options
    include_related: bool = True
    include_attachments: bool = True
    max_results: int = 100

    # Original Query
    raw_query: str = ""
    parsed_ims_syntax: Optional[str] = None  # IMS native syntax

    # Confidence
    confidence_score: float = 0.0  # NL parser confidence (0.0 - 1.0)

    def is_simple_keyword_search(self) -> bool:
        """Check if this is a simple keyword-only search"""
        return (
            self.intent_type == SearchIntentType.KEYWORD_SEARCH and
            len(self.status_filters) == 0 and
            len(self.priority_filters) == 0
        )

    def has_filters(self) -> bool:
        """Check if intent has any filters applied"""
        return any([
            self.status_filters,
            self.priority_filters,
            self.assignee_filters,
            self.project_filters,
            self.date_from,
            self.date_to,
        ])

    def requires_semantic_search(self) -> bool:
        """Check if semantic search should be used"""
        return (
            self.intent_type == SearchIntentType.SEMANTIC_SEARCH or
            self.semantic_query is not None
        )

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            "intent_type": self.intent_type.value,
            "keywords": self.keywords,
            "status_filters": self.status_filters,
            "priority_filters": self.priority_filters,
            "assignee_filters": self.assignee_filters,
            "project_filters": self.project_filters,
            "date_from": self.date_from,
            "date_to": self.date_to,
            "semantic_query": self.semantic_query,
            "include_related": self.include_related,
            "include_attachments": self.include_attachments,
            "max_results": self.max_results,
            "raw_query": self.raw_query,
            "parsed_ims_syntax": self.parsed_ims_syntax,
            "confidence_score": self.confidence_score,
        }
