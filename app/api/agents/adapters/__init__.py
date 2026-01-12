"""
Agent LLM Adapters
Provides LLM adapters for agent execution.
"""
from .ollama_adapter import OllamaAgentAdapter, get_ollama_adapter
from .deep_agent_adapter import (
    DeepAgentAdapter,
    create_deep_agent_adapter,
    create_rag_deep_agent,
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
    # Integration
    "register_deep_agent",
    "enable_deep_agents",
    "get_deep_agent",
    "is_deep_agent_enabled",
    "auto_register_deep_agents",
]
