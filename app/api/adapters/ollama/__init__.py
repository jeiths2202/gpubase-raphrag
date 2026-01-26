"""
Ollama Adapters

Local LLM inference using Ollama.
"""

from .llm_adapter import OllamaLLMAdapter, get_ollama_llm

__all__ = ["OllamaLLMAdapter", "get_ollama_llm"]
