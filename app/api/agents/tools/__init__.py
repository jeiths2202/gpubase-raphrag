"""
Agent Tools Package
Provides tools that agents can use to perform actions.
"""
from .base import BaseTool, MockTool
from .vector_search import VectorSearchTool, GraphQueryTool
from .ims_search import IMSSearchTool
from .document_read import DocumentReadTool, WebFetchTool
from .bash import BashTool, SafeBashTool

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
    }

    tool_class = tools.get(name)
    if tool_class:
        return tool_class()
    raise ValueError(f"Unknown tool: {name}")
