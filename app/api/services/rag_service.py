"""
RAG Service - Integrates existing Hybrid RAG with FastAPI
Provides async wrappers for RAG operations
"""
import asyncio
from typing import Dict, List, Any, Optional, AsyncGenerator
from functools import lru_cache
from datetime import datetime
import sys
import os

# Add src directory to path for importing existing modules
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src'))

from hybrid_rag import HybridRAG, get_hybrid_rag
from query_router import QueryRouter, QueryType


class RAGService:
    """
    FastAPI-compatible RAG Service wrapping HybridRAG

    Provides async methods for:
    - Query execution (with streaming support)
    - Query classification
    - System statistics
    """

    _instance: Optional['RAGService'] = None
    _initialized: bool = False

    def __init__(self):
        """Initialize RAG service with lazy loading"""
        self._hybrid_rag: Optional[HybridRAG] = None
        self._query_router: Optional[QueryRouter] = None

    @classmethod
    def get_instance(cls) -> 'RAGService':
        """Get singleton instance"""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def _ensure_initialized(self) -> HybridRAG:
        """Ensure RAG system is initialized (lazy loading)"""
        if self._hybrid_rag is None:
            print("Initializing HybridRAG system...")
            self._hybrid_rag = get_hybrid_rag()
            self._query_router = self._hybrid_rag.router

            # Initialize system components
            status = self._hybrid_rag.init_system()
            for component, ok in status.items():
                print(f"  {component}: {'OK' if ok else 'FAILED'}")

            self._initialized = True
        return self._hybrid_rag

    async def query(
        self,
        question: str,
        strategy: str = "auto",
        language: str = "auto",
        top_k: int = 5,
        conversation_id: Optional[str] = None,
        conversation_history: Optional[List[Dict]] = None
    ) -> Dict[str, Any]:
        """
        Execute RAG query asynchronously

        Args:
            question: User's question
            strategy: RAG strategy (auto, vector, graph, hybrid, code)
            language: Response language (auto, ko, ja, en)
            top_k: Number of results to retrieve
            conversation_id: Optional conversation session ID
            conversation_history: Previous Q&A pairs for context

        Returns:
            Dictionary with answer, sources, and metadata
        """
        # Run synchronous HybridRAG in thread pool
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None,
            self._sync_query,
            question, strategy, language, top_k, conversation_history
        )
        return result

    def _sync_query(
        self,
        question: str,
        strategy: str,
        language: str,
        top_k: int,
        conversation_history: Optional[List[Dict]]
    ) -> Dict[str, Any]:
        """Synchronous query execution"""
        rag = self._ensure_initialized()

        # Execute query
        result = rag.query(
            question=question,
            strategy=strategy,
            language=language,
            k=top_k,
            conversation_history=conversation_history
        )

        # Get query features for analysis
        features = self._query_router.get_query_features(question)

        # Format sources for API response
        sources = []
        for r in result.get("results", []):
            sources.append({
                "doc_id": r.get("doc_id", ""),
                "doc_name": r.get("doc_id", ""),  # TODO: Add document name lookup
                "chunk_id": r.get("chunk_id", ""),
                "chunk_index": r.get("chunk_index", 0),
                "content": r.get("content", "")[:500],
                "score": r.get("score", 0.0) if isinstance(r.get("score"), (int, float)) else 0.0,
                "source_type": r.get("source", "unknown"),
                "entities": r.get("entities", [])
            })

        return {
            "answer": result.get("answer", ""),
            "strategy": result.get("strategy", strategy),
            "language": result.get("language", language),
            "confidence": 0.85,  # TODO: Implement actual confidence scoring
            "sources": sources,
            "query_analysis": {
                "detected_language": features.get("language", "en"),
                "query_type": result.get("strategy", "vector"),
                "is_comprehensive": False,
                "is_deep_analysis": False,
                "has_error_code": features.get("has_error_code", False)
            }
        }

    async def stream_query(
        self,
        question: str,
        strategy: str = "auto",
        language: str = "auto",
        top_k: int = 5
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        Stream RAG query response

        Yields chunks of the response for real-time streaming.

        Args:
            question: User's question
            strategy: RAG strategy
            language: Response language
            top_k: Number of results

        Yields:
            Dictionaries with type and content
        """
        # Get full result first (TODO: implement true streaming from LLM)
        result = await self.query(
            question=question,
            strategy=strategy,
            language=language,
            top_k=top_k
        )

        answer = result.get("answer", "")

        # Simulate streaming by yielding chunks
        chunk_size = 50
        for i in range(0, len(answer), chunk_size):
            chunk = answer[i:i + chunk_size]
            yield {"type": "text", "content": chunk}
            await asyncio.sleep(0.02)  # Small delay for streaming effect

        # Yield sources at the end
        yield {"type": "sources", "sources": result.get("sources", [])}

    async def classify_query(self, question: str) -> Dict[str, Any]:
        """
        Classify query without executing search

        Args:
            question: User's question

        Returns:
            Classification result with strategy and probabilities
        """
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None,
            self._sync_classify,
            question
        )
        return result

    def _sync_classify(self, question: str) -> Dict[str, Any]:
        """Synchronous query classification"""
        self._ensure_initialized()

        # Get rule scores
        rule_scores = self._query_router._get_rule_scores(question)

        # Get classification result
        query_type = self._query_router.classify_query(question)

        # Get query features
        features = self._query_router.get_query_features(question)

        # Normalize scores to probabilities
        total = sum(rule_scores.values())
        probabilities = {k: v / total for k, v in rule_scores.items()}

        # Determine confidence based on score distribution
        max_prob = max(probabilities.values())
        confidence = min(max_prob * 1.5, 0.99)  # Scale up but cap at 0.99

        return {
            "strategy": query_type.value,
            "confidence": confidence,
            "probabilities": probabilities,
            "language": features.get("language", "en"),
            "has_error_code": features.get("has_error_code", False),
            "is_comprehensive": False,  # TODO: Implement detection
            "is_code_query": query_type == QueryType.CODE
        }

    async def get_stats(self) -> Dict[str, Any]:
        """Get RAG system statistics"""
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None,
            self._sync_get_stats
        )
        return result

    def _sync_get_stats(self) -> Dict[str, Any]:
        """Synchronous stats retrieval"""
        rag = self._ensure_initialized()
        return rag.get_stats()

    async def health_check(self) -> Dict[str, Any]:
        """Check RAG system health"""
        try:
            rag = self._ensure_initialized()
            status = rag.init_system()

            all_healthy = all(status.values())

            return {
                "status": "healthy" if all_healthy else "degraded",
                "components": status
            }
        except Exception as e:
            return {
                "status": "unhealthy",
                "error": str(e)
            }


# Singleton instance getter
@lru_cache()
def get_rag_service() -> RAGService:
    """Get cached RAG service instance"""
    return RAGService.get_instance()
