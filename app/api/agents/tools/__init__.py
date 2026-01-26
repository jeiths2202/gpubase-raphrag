"""
Agent Tools Package
Provides tools that agents can use to perform actions.
"""
from .base import BaseTool, MockTool
from .vector_search import VectorSearchTool, GraphQueryTool
from .ims_search import IMSSearchTool
from .document_read import DocumentReadTool, WebFetchTool
from .bash import BashTool, SafeBashTool
from .image_search import ImageSearchTool
from .adaptive_search import AdaptiveSearchTool
from .unified_search import UnifiedSearchTool

__all__ = [
    "BaseTool",
    "MockTool",
    "VectorSearchTool",
    "GraphQueryTool",
    "IMSSearchTool",
    "DocumentReadTool",
    "WebFetchTool",
    "BashTool",
    "SafeBashTool",
    "ImageSearchTool",
    "AdaptiveSearchTool",
    "UnifiedSearchTool",
]


def get_all_tools():
    """Get all available tool instances"""
    return [
        VectorSearchTool(),
        GraphQueryTool(),
        IMSSearchTool(),
        DocumentReadTool(),
        WebFetchTool(),
        SafeBashTool(),
        ImageSearchTool(),
        AdaptiveSearchTool(),
        UnifiedSearchTool(),
    ]


def get_tool_by_name(name: str) -> BaseTool:
    """Get a tool instance by name"""
    tools = {
        "vector_search": VectorSearchTool,
        "graph_query": GraphQueryTool,
        "ims_search": IMSSearchTool,
        "document_read": DocumentReadTool,
        "web_fetch": WebFetchTool,
        "bash": SafeBashTool,
        "mock_tool": MockTool,
        "image_search": ImageSearchTool,
        "adaptive_search": AdaptiveSearchTool,
        "unified_search": UnifiedSearchTool,
    }

    tool_class = tools.get(name)
    if tool_class:
        return tool_class()
    raise ValueError(f"Unknown tool: {name}")
