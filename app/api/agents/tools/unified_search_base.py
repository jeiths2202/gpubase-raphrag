"""Unified Search Base Module

Contains constants, configuration, and base class components.
"""
import logging
import os
from typing import Dict, Any, Optional

from .base import BaseTool

logger = logging.getLogger(__name__)

# =============================================================
# CONFIGURATION CONSTANTS
# =============================================================

# RAG Accuracy Improvement Feature Toggle
ENABLE_RAG_ACCURACY_GRADING = os.getenv("RAG_ACCURACY_ENABLE_GRADING", "true").lower() == "true"

# Learning LLM Feature Toggle
ENABLE_LEARNING_LLM = os.getenv("ENABLE_LEARNING_LLM", "false").lower() == "true"
LEARNING_LLM_MIN_CONFIDENCE = float(os.getenv("LEARNING_LLM_MIN_CONFIDENCE", "0.6"))
LEARNING_LLM_VERIFICATION_THRESHOLD = float(os.getenv("LEARNING_LLM_VERIFICATION_THRESHOLD", "0.7"))

# Vision Knowledge Feature Toggle (MiniCPM-V enrichment for PDF pages)
ENABLE_VISION_ENRICHMENT = os.getenv("ENABLE_VISION_ENRICHMENT", "true").lower() == "true"

# Default top_k based on LLM context size
_USE_LARGE_CONTEXT = os.getenv("RAG_LLM_USE_LARGE_CONTEXT", "false").lower() == "true"
DEFAULT_TOP_K = 5 if _USE_LARGE_CONTEXT else 3

# Search mode: "hybrid", "vector_only", "keyword_only"
DEFAULT_SEARCH_MODE = os.getenv("UNIFIED_SEARCH_MODE", "hybrid").lower()
if DEFAULT_SEARCH_MODE not in ("hybrid", "vector_only", "keyword_only"):
    logger.warning(f"Invalid UNIFIED_SEARCH_MODE '{DEFAULT_SEARCH_MODE}', using 'hybrid'")
    DEFAULT_SEARCH_MODE = "hybrid"

# RRF (Reciprocal Rank Fusion) toggle
ENABLE_RRF_FUSION = os.getenv("ENABLE_RRF_FUSION", "false").lower() == "true"

# Semantic Search Feature Toggle
USE_SEMANTIC_SEARCH = os.getenv("USE_SEMANTIC_SEARCH", "true").lower() == "true"
SEMANTIC_QUERY_PREPROCESSING = os.getenv("SEMANTIC_QUERY_PREPROCESSING", "true").lower() == "true"


class UnifiedSearchBase(BaseTool):
    """
    Base class for UnifiedSearchTool with service initialization.

    Provides:
    - Tool metadata and parameters
    - Lazy-loaded service properties
    - Common utility methods
    """

    def __init__(self, rag_service=None):
        super().__init__(
            name="unified_search",
            description="""PRIMARY search tool - combines Neo4j accuracy with PostgreSQL structure.
Use this FIRST for any knowledge base query. Features:
- Semantic search via Neo4j (verified asymmetric embeddings)
- RRF hybrid ranking (semantic + keyword)
- PDF structure preservation (sections, tables, images)
- CLIP text-to-image search
- Error code detection and boosting
Returns relevant document chunks with full context and source information."""
        )
        self._rag_service = rag_service
        self._adaptive_service = None
        self._embedding_service = None
        self._clip_service = None
        self._query_understanding_service = None

    @property
    def query_understanding_service(self):
        """Lazy load Query Understanding service for semantic search"""
        if self._query_understanding_service is None and SEMANTIC_QUERY_PREPROCESSING:
            try:
                from ...services.query_understanding_service import get_query_understanding_service
                self._query_understanding_service = get_query_understanding_service()
                logger.debug("Query Understanding service loaded")
            except Exception as e:
                logger.warning(f"Failed to load Query Understanding service: {e}")
        return self._query_understanding_service

    def _get_default_parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "The search query - MUST be the EXACT user question without modification"
                },
                "top_k": {
                    "type": "integer",
                    "description": f"Number of results to return (default: {DEFAULT_TOP_K})",
                    "default": DEFAULT_TOP_K
                },
                "doc_filter": {
                    "type": "string",
                    "description": "Optional: ONLY use if the user explicitly mentions a specific document name."
                },
                "include_images": {
                    "type": "boolean",
                    "description": "Include CLIP-based image search (default: true)",
                    "default": True
                },
                "include_tables": {
                    "type": "boolean",
                    "description": "Auto-include related tables (default: true)",
                    "default": True
                },
                "search_mode": {
                    "type": "string",
                    "description": f"Search mode: hybrid, vector_only, keyword_only. Default: {DEFAULT_SEARCH_MODE}",
                    "enum": ["hybrid", "vector_only", "keyword_only"],
                    "default": DEFAULT_SEARCH_MODE
                }
            },
            "required": ["query"]
        }

    @property
    def rag_service(self):
        """Lazy load RAG service for Neo4j vector search"""
        if self._rag_service is None:
            logger.debug("Lazy loading RAG service...")
            try:
                from ...core.deps import get_rag_service
                self._rag_service = get_rag_service()
                logger.debug(f"RAG service loaded: {self._rag_service is not None}")
            except Exception as e:
                logger.error(f"Failed to get RAG service: {e}")
        return self._rag_service

    async def _get_adaptive_service(self):
        """Lazy load adaptive service for PostgreSQL operations"""
        if self._adaptive_service is None:
            try:
                from ...core.deps import get_adaptive_embedding_service
                self._adaptive_service = await get_adaptive_embedding_service()
            except Exception as e:
                logger.error(f"Failed to get adaptive service: {e}")
        return self._adaptive_service

    async def _get_embedding_service(self):
        """Lazy load embedding service"""
        if self._embedding_service is None:
            try:
                from ...core.deps import get_adaptive_embedding_service
                adaptive = await get_adaptive_embedding_service()
                if adaptive and hasattr(adaptive, 'embedding_service'):
                    self._embedding_service = adaptive.embedding_service
            except Exception as e:
                logger.error(f"Failed to get embedding service: {e}")
        return self._embedding_service

    async def _get_clip_service(self):
        """Lazy load CLIP service for image search"""
        if self._clip_service is None:
            try:
                from ...core.deps import get_clip_service_instance
                self._clip_service = await get_clip_service_instance()
            except Exception as e:
                logger.debug(f"CLIP service not available: {e}")
        return self._clip_service
