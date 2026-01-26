"""
Prompt Management System
Centralized prompt templates and registry.
"""
from .base import PromptTemplate, PromptRegistry, PromptConfig
from .rag_prompts import (
    RAGPrompts,
    AnswerGenerationPrompt,
    ContextBuildingPrompt,
    QueryClassificationPrompt
)
from .mindmap_prompts import (
    MindmapPrompts,
    ConceptExtractionPrompt,
    NodeExpansionPrompt,
    NodeQueryPrompt
)
from .system_prompts import (
    SystemPrompts,
    ASSISTANT_PERSONA,
    CODE_ASSISTANT_PERSONA,
    ANALYST_PERSONA
)

__all__ = [
    # Base
    "PromptTemplate",
    "PromptRegistry",
    "PromptConfig",
    # RAG
    "RAGPrompts",
    "AnswerGenerationPrompt",
    "ContextBuildingPrompt",
    "QueryClassificationPrompt",
    # Mindmap
    "MindmapPrompts",
    "ConceptExtractionPrompt",
    "NodeExpansionPrompt",
    "NodeQueryPrompt",
    # System
    "SystemPrompts",
    "ASSISTANT_PERSONA",
    "CODE_ASSISTANT_PERSONA",
    "ANALYST_PERSONA",
]
