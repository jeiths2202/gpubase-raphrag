"""
Agent LLM Adapters
Provides LLM adapters for agent execution.
"""
from .ollama_adapter import OllamaAgentAdapter, get_ollama_adapter
from .deep_agent_adapter import (
    DeepAgentAdapter,
    create_rag_deep_agent,
    create_code_deep_agent,
    create_project_deep_agent,
)

__all__ = [
    # Ollama Adapter
    "OllamaAgentAdapter",
    "get_ollama_adapter",
    # Deep Agents Adapter
    "DeepAgentAdapter",
    "create_rag_deep_agent",
    "create_code_deep_agent",
    "create_project_deep_agent",
]
