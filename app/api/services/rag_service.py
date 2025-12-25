"""
RAG Service - Integrates existing Hybrid RAG with FastAPI
Provides async wrappers for RAG operations with session document priority
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
    - Session document priority retrieval
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
        conversation_history: Optional[List[Dict]] = None,
        # Session document options
        session_id: Optional[str] = None,
        use_session_docs: bool = True,
        session_weight: float = 2.0
    ) -> Dict[str, Any]:
        """
        Execute RAG query asynchronously with session document priority

        Args:
            question: User's question
            strategy: RAG strategy (auto, vector, graph, hybrid, code)
            language: Response language (auto, ko, ja, en)
            top_k: Number of results to retrieve
            conversation_id: Optional conversation session ID
            conversation_history: Previous Q&A pairs for context
            session_id: Session ID for uploaded documents
            use_session_docs: Whether to use session documents (default True)
            session_weight: Score boost for session results (default 2.0)

        Returns:
            Dictionary with answer, sources, and metadata
        """
        session_results = []
        used_session_docs = False
        session_doc_count = 0

        # Step 1: Search session documents first (if available)
        if session_id and use_session_docs:
            try:
                from .session_document_service import get_session_document_service
                session_service = get_session_document_service()

                session_results = await session_service.search_session(
                    session_id=session_id,
                    query=question,
                    top_k=top_k,
                    min_score=0.3
                )

                if session_results:
                    used_session_docs = True
                    session_doc_count = len(session_results)
                    print(f"[RAGService] Found {session_doc_count} results from session documents")

            except Exception as e:
                print(f"[RAGService] Session document search failed: {e}")

        # Step 2: Search global knowledge base
        loop = asyncio.get_event_loop()
        global_result = await loop.run_in_executor(
            None,
            self._sync_query,
            question, strategy, language, top_k, conversation_history
        )

        # Step 3: Merge results with priority
        merged_sources = self._merge_results_with_priority(
            session_results=session_results,
            global_sources=global_result.get("sources", []),
            session_weight=session_weight,
            top_k=top_k
        )

        # Step 4: Generate answer with combined context
        if session_results:
            # Re-generate answer with session context included
            answer = await self._generate_answer_with_session_context(
                question=question,
                session_results=session_results,
                global_sources=global_result.get("sources", []),
                language=language,
                original_answer=global_result.get("answer", "")
            )
        else:
            answer = global_result.get("answer", "")

        # Get query features for analysis
        features = self._query_router.get_query_features(question)

        return {
            "answer": answer,
            "strategy": global_result.get("strategy", strategy),
            "language": global_result.get("language", language),
            "confidence": 0.85,
            "sources": merged_sources,
            "query_analysis": {
                "detected_language": features.get("language", "en"),
                "query_type": global_result.get("strategy", "vector"),
                "is_comprehensive": False,
                "is_deep_analysis": False,
                "has_error_code": features.get("has_error_code", False),
                "used_session_docs": used_session_docs,
                "session_doc_count": session_doc_count
            }
        }

    def _merge_results_with_priority(
        self,
        session_results: List[Any],
        global_sources: List[Dict],
        session_weight: float,
        top_k: int
    ) -> List[Dict]:
        """
        Merge session and global results with priority scoring.
        Session documents get a score boost.
        """
        merged = []

        # Add session results with boosted scores
        for sr in session_results:
            merged.append({
                "doc_id": sr.document_id,
                "doc_name": sr.source_name,
                "chunk_id": sr.chunk_id,
                "chunk_index": sr.metadata.get("index", 0),
                "content": sr.content[:500],
                "score": min(sr.score * session_weight, 1.0),  # Boost but cap at 1.0
                "source_type": "session",
                "entities": [],
                "is_session_doc": True,
                "page_number": sr.page_number
            })

        # Add global results
        for gs in global_sources:
            # Check if this chunk is already from session
            if not any(m.get("chunk_id") == gs.get("chunk_id") for m in merged):
                merged.append({
                    **gs,
                    "is_session_doc": False,
                    "page_number": None
                })

        # Sort by score descending
        merged.sort(key=lambda x: x.get("score", 0), reverse=True)

        return merged[:top_k]

    async def _generate_answer_with_session_context(
        self,
        question: str,
        session_results: List[Any],
        global_sources: List[Dict],
        language: str,
        original_answer: str
    ) -> str:
        """
        Generate answer with session document context prioritized.
        """
        try:
            rag = self._ensure_initialized()

            # Build context from session documents first
            context_parts = []

            # Session context (marked as uploaded documents)
            if session_results:
                context_parts.append("=== 업로드된 문서 (우선 참조) ===")
                for i, sr in enumerate(session_results[:5], 1):
                    source_info = f"[{sr.source_name}]"
                    if sr.page_number:
                        source_info += f" (페이지 {sr.page_number})"
                    context_parts.append(f"[업로드{i}] {source_info}")
                    context_parts.append(sr.content[:600])
                context_parts.append("")

            # Global context (reference knowledge base)
            if global_sources:
                context_parts.append("=== 기존 지식 베이스 ===")
                for i, gs in enumerate(global_sources[:3], 1):
                    context_parts.append(f"[참조{i}] {gs.get('content', '')[:400]}")

            context = "\n\n".join(context_parts)

            # Language instruction
            lang_instruction = ""
            if language == "ko":
                lang_instruction = "한국어로 답변해주세요."
            elif language == "ja":
                lang_instruction = "日本語で回答してください。"

            # Generate answer
            prompt = f"""다음 문서들을 참고하여 질문에 답변하세요.
{lang_instruction}

**중요**: '업로드된 문서'의 내용을 우선적으로 참조하여 답변하세요.
답변 시 정보의 출처(업로드 문서 또는 기존 지식)를 명시해주세요.

{context}

질문: {question}

답변:"""

            # Run in thread pool
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None,
                lambda: rag.llm.invoke(prompt)
            )

            answer = response.content

            # Clean thinking tokens
            if "</think>" in answer:
                answer = answer.split("</think>")[-1].strip()

            return answer

        except Exception as e:
            print(f"[RAGService] Answer generation with session context failed: {e}")
            # Fallback to original answer
            return original_answer

    def _sync_query(
        self,
        question: str,
        strategy: str,
        language: str,
        top_k: int,
        conversation_history: Optional[List[Dict]]
    ) -> Dict[str, Any]:
        """Synchronous query execution for global knowledge base"""
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
                "doc_name": r.get("doc_id", ""),
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
            "confidence": 0.85,
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
        top_k: int = 5,
        session_id: Optional[str] = None,
        use_session_docs: bool = True
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        Stream RAG query response

        Yields chunks of the response for real-time streaming.

        Args:
            question: User's question
            strategy: RAG strategy
            language: Response language
            top_k: Number of results
            session_id: Session ID for documents
            use_session_docs: Whether to use session documents

        Yields:
            Dictionaries with type and content
        """
        # Get full result first (TODO: implement true streaming from LLM)
        result = await self.query(
            question=question,
            strategy=strategy,
            language=language,
            top_k=top_k,
            session_id=session_id,
            use_session_docs=use_session_docs
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
            "is_comprehensive": False,
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
