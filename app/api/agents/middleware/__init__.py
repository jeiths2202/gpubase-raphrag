"""
Deep Agents Middleware and Tools Module
기존 WebUI Agent 도구를 Deep Agents에서 사용할 수 있도록 제공

Deep Agents에서는 도구(Tools)와 미들웨어(Middleware)가 분리됩니다:
- Tools: create_deep_agent의 tools 파라미터로 전달
- Middleware: langchain.agents.middleware.types.AgentMiddleware 상속
"""
from .rag_middleware import (
    RAGMiddleware,
    RAGToolsProvider,
    get_rag_tools,
    RAG_SYSTEM_PROMPT,
)
from .code_middleware import (
    CodeMiddleware,
    CodeToolsProvider,
    get_code_tools,
    CODE_SYSTEM_PROMPT,
)
from .ims_middleware import (
    IMSToolsProvider,
    get_ims_tools,
    IMS_SYSTEM_PROMPT,
)

__all__ = [
    # RAG
    "RAGMiddleware",
    "RAGToolsProvider",
    "get_rag_tools",
    "RAG_SYSTEM_PROMPT",
    # Code
    "CodeMiddleware",
    "CodeToolsProvider",
    "get_code_tools",
    "CODE_SYSTEM_PROMPT",
    # IMS
    "IMSToolsProvider",
    "get_ims_tools",
    "IMS_SYSTEM_PROMPT",
]
