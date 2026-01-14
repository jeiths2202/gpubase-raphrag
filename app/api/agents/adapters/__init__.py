"""
Agent LLM Adapters
Provides LLM adapters for agent execution.

Features:
- Ollama adapter for local LLM inference
- Deep Agent adapter with LangGraph integration
- Long-term Memory support via CompositeBackend
"""
from .ollama_adapter import OllamaAgentAdapter, get_ollama_adapter
from .deep_agent_adapter import (
    DeepAgentAdapter,
    create_deep_agent_adapter,
    create_rag_deep_agent,
    create_code_deep_agent,
    create_project_deep_agent,
    DEEPAGENTS_AVAILABLE,
    DEEPAGENTS_BACKENDS_AVAILABLE,
    LANGGRAPH_STORE_AVAILABLE,
)
from .integration import (
    register_deep_agent,
    enable_deep_agents,
    get_deep_agent,
    is_deep_agent_enabled,
    auto_register_deep_agents,
)

__all__ = [
    # Ollama Adapter
    "OllamaAgentAdapter",
    "get_ollama_adapter",
    # Deep Agent Adapter
    "DeepAgentAdapter",
    "create_deep_agent_adapter",
    "create_rag_deep_agent",
    "create_code_deep_agent",
    "create_project_deep_agent",
    # Feature Flags
    "DEEPAGENTS_AVAILABLE",
    "DEEPAGENTS_BACKENDS_AVAILABLE",
    "LANGGRAPH_STORE_AVAILABLE",
    # Integration
    "register_deep_agent",
    "enable_deep_agents",
    "get_deep_agent",
    "is_deep_agent_enabled",
    "auto_register_deep_agents",
]
