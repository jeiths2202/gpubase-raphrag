"""
RAG Pipeline Module
Clearly separated Embedding, Retrieval, and Generation stages.
"""
from .embedding import EmbeddingStage, EmbeddingConfig, EmbeddingResult
from .retrieval import RetrievalStage, RetrievalConfig, RetrievalResult
from .generation import GenerationStage, GenerationConfig, GenerationResult
from .orchestrator import RAGPipeline, PipelineConfig

__all__ = [
    # Embedding
    "EmbeddingStage",
    "EmbeddingConfig",
    "EmbeddingResult",
    # Retrieval
    "RetrievalStage",
    "RetrievalConfig",
    "RetrievalResult",
    # Generation
    "GenerationStage",
    "GenerationConfig",
    "GenerationResult",
    # Orchestrator
    "RAGPipeline",
    "PipelineConfig",
]
