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
from .vision_middleware import (
    VisionToolsProvider,
    get_vision_tools,
    VISION_SYSTEM_PROMPT,
)
from .code_middleware import (
    CodeToolsProvider,
    get_code_tools,
    CODE_SYSTEM_PROMPT,
)
from .planner_middleware import (
    PlannerToolsProvider,
    get_planner_tools,
    PLANNER_SYSTEM_PROMPT,
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
    # Vision
    "VisionToolsProvider",
    "get_vision_tools",
    "VISION_SYSTEM_PROMPT",
    # Code
    "CodeToolsProvider",
    "get_code_tools",
    "CODE_SYSTEM_PROMPT",
    # Planner
    "PlannerToolsProvider",
    "get_planner_tools",
    "PLANNER_SYSTEM_PROMPT",
]
