"""
Chain Abstraction Layer
Composable chains for RAG and generation pipelines.
"""
from .base import Chain, ChainResult, ChainConfig, ChainStep
from .rag_chain import RAGChain, RAGChainConfig
from .generation_chain import GenerationChain, GenerationChainConfig
from .retrieval_chain import RetrievalChain, RetrievalChainConfig

__all__ = [
    # Base
    "Chain",
    "ChainResult",
    "ChainConfig",
    "ChainStep",
    # RAG
    "RAGChain",
    "RAGChainConfig",
    # Generation
    "GenerationChain",
    "GenerationChainConfig",
    # Retrieval
    "RetrievalChain",
    "RetrievalChainConfig",
]
