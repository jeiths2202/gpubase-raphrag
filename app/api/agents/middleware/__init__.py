"""
Agent Middleware Package
Provides middleware and tool wrappers for Deep Agents integration.
"""
from .rag_tools import (
    RAGToolsProvider,
    create_vector_search_tool,
    create_graph_query_tool,
    get_rag_tools,
)
from .ims_middleware import (
    IMSToolsProvider,
    get_ims_tools,
    IMS_SYSTEM_PROMPT,
)

__all__ = [
    # RAG
    "RAGToolsProvider",
    "create_vector_search_tool",
    "create_graph_query_tool",
    "get_rag_tools",
    # IMS
    "IMSToolsProvider",
    "get_ims_tools",
    "IMS_SYSTEM_PROMPT",
]
