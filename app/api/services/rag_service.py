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
        session_weight: float = 2.0,
        # External resource options
        user_id: Optional[str] = None,
        use_external_resources: bool = True,
        external_weight: float = 2.5
    ) -> Dict[str, Any]:
        """
        Execute RAG query asynchronously with priority-based retrieval

        Priority order:
        1. Session documents (uploaded in current session)
        2. User's external resources (OneNote, GitHub, Drive, Notion, Confluence)
        3. Global knowledge base

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
            user_id: User ID for external resources
            use_external_resources: Whether to use external resources (default True)
            external_weight: Score boost for external results (default 2.5)

        Returns:
            Dictionary with answer, sources, and metadata
        """
        session_results = []
        external_results = []
        used_session_docs = False
        used_external_resources = False
        session_doc_count = 0
        external_doc_count = 0

        # Step 1: Search session documents first (highest priority)
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

        # Step 2: Search user's external resources (second priority)
        if user_id and use_external_resources:
            try:
                from .external_document_service import get_external_document_service
                external_service = get_external_document_service()

                external_results = await external_service.search_user_resources(
                    user_id=user_id,
                    query=question,
                    top_k=top_k,
                    min_score=0.3
                )

                if external_results:
                    used_external_resources = True
                    external_doc_count = len(external_results)
                    print(f"[RAGService] Found {external_doc_count} results from external resources")

            except Exception as e:
                print(f"[RAGService] External resource search failed: {e}")

        # Step 3: Search global knowledge base (if needed)
        # Skip global search if we have sufficient results from user sources
        search_global = True
        if (session_doc_count + external_doc_count) >= top_k:
            # Check if scores are high enough
            all_user_results = session_results + external_results
            avg_score = sum(r.score for r in all_user_results) / len(all_user_results) if all_user_results else 0
            if avg_score >= 0.7:
                search_global = False
                print(f"[RAGService] Skipping global search (sufficient user context: avg_score={avg_score:.2f})")

        global_result = {"answer": "", "sources": [], "strategy": strategy, "language": language}
        if search_global:
            loop = asyncio.get_event_loop()
            global_result = await loop.run_in_executor(
                None,
                self._sync_query,
                question, strategy, language, top_k, conversation_history
            )

        # Step 4: Merge results with priority
        merged_sources = self._merge_all_results_with_priority(
            session_results=session_results,
            external_results=external_results,
            global_sources=global_result.get("sources", []),
            session_weight=session_weight,
            external_weight=external_weight,
            top_k=top_k
        )

        # Step 5: Generate answer with combined context
        if session_results or external_results:
            # Re-generate answer with user context included
            answer = await self._generate_answer_with_full_context(
                question=question,
                session_results=session_results,
                external_results=external_results,
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
                "session_doc_count": session_doc_count,
                "used_external_resources": used_external_resources,
                "external_doc_count": external_doc_count
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

    def _merge_all_results_with_priority(
        self,
        session_results: List[Any],
        external_results: List[Any],
        global_sources: List[Dict],
        session_weight: float,
        external_weight: float,
        top_k: int
    ) -> List[Dict]:
        """
        Merge session, external, and global results with priority scoring.

        Priority (highest to lowest):
        1. Session documents (uploaded in current chat) - highest weight
        2. External resources (user's connected resources) - medium weight
        3. Global knowledge base - base score
        """
        merged = []

        # Add session results with highest boost
        for sr in session_results:
            merged.append({
                "doc_id": sr.document_id,
                "doc_name": sr.source_name,
                "chunk_id": sr.chunk_id,
                "chunk_index": sr.metadata.get("index", 0),
                "content": sr.content[:500],
                "score": min(sr.score * session_weight, 1.0),
                "source_type": "session",
                "entities": [],
                "is_session_doc": True,
                "is_external_resource": False,
                "page_number": getattr(sr, 'page_number', None),
                "source_url": None
            })

        # Add external resource results with medium boost
        for er in external_results:
            merged.append({
                "doc_id": er.document_id,
                "doc_name": er.source_name,
                "chunk_id": er.chunk_id,
                "chunk_index": er.metadata.get("index", 0),
                "content": er.content[:500],
                "score": min(er.score * external_weight, 1.0),
                "source_type": f"external_{er.source}" if hasattr(er, 'source') else "external",
                "entities": [],
                "is_session_doc": False,
                "is_external_resource": True,
                "page_number": getattr(er, 'page_number', None),
                "source_url": getattr(er, 'source_url', None),
                "external_source": er.source if hasattr(er, 'source') else None,
                "section_title": getattr(er, 'section_title', None)
            })

        # Add global results (no boost)
        for gs in global_sources:
            # Check if this chunk is already included
            existing_chunks = {m.get("chunk_id") for m in merged}
            if gs.get("chunk_id") not in existing_chunks:
                merged.append({
                    **gs,
                    "is_session_doc": False,
                    "is_external_resource": False,
                    "page_number": None,
                    "source_url": None
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

            # Language instruction from policy service
            from .language_policy import get_language_policy_service
            policy_service = get_language_policy_service()
            lang_instruction = policy_service.get_language_instruction(language)

            # Generate answer
            prompt = f"""다음 문서들을 참고하여 질문에 답변하세요.

**응답 언어 지시**: {lang_instruction}

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

    async def _generate_answer_with_full_context(
        self,
        question: str,
        session_results: List[Any],
        external_results: List[Any],
        global_sources: List[Dict],
        language: str,
        original_answer: str
    ) -> str:
        """
        Generate answer with full context from all sources.

        Priority:
        1. Session documents (uploaded files)
        2. External resources (connected accounts)
        3. Global knowledge base
        """
        try:
            rag = self._ensure_initialized()

            context_parts = []

            # Session context (highest priority)
            if session_results:
                context_parts.append("=== 업로드된 문서 (최우선 참조) ===")
                for i, sr in enumerate(session_results[:4], 1):
                    source_info = f"[{sr.source_name}]"
                    if hasattr(sr, 'page_number') and sr.page_number:
                        source_info += f" (페이지 {sr.page_number})"
                    context_parts.append(f"[업로드{i}] {source_info}")
                    context_parts.append(sr.content[:500])
                context_parts.append("")

            # External resource context (second priority)
            if external_results:
                context_parts.append("=== 연결된 외부 리소스 (우선 참조) ===")
                for i, er in enumerate(external_results[:4], 1):
                    source_type = er.source if hasattr(er, 'source') else "external"
                    source_info = f"[{er.source_name}] ({source_type})"
                    if hasattr(er, 'source_url') and er.source_url:
                        source_info += f"\n   링크: {er.source_url}"
                    if hasattr(er, 'section_title') and er.section_title:
                        source_info += f"\n   섹션: {er.section_title}"
                    context_parts.append(f"[외부{i}] {source_info}")
                    context_parts.append(er.content[:500])
                context_parts.append("")

            # Global context (base knowledge)
            if global_sources:
                context_parts.append("=== 기존 지식 베이스 ===")
                for i, gs in enumerate(global_sources[:3], 1):
                    context_parts.append(f"[참조{i}] {gs.get('content', '')[:400]}")

            context = "\n\n".join(context_parts)

            # Language instruction from policy service
            from .language_policy import get_language_policy_service
            policy_service = get_language_policy_service()
            lang_instruction = policy_service.get_language_instruction(language)

            # Generate answer with source attribution
            prompt = f"""다음 문서들을 참고하여 질문에 답변하세요.

**응답 언어 지시**: {lang_instruction}

**중요 지시사항**:
1. '업로드된 문서'와 '연결된 외부 리소스'의 내용을 우선적으로 참조하여 답변하세요.
2. 답변에 사용한 정보의 출처를 명시해주세요:
   - 업로드된 문서에서 온 정보: "[업로드 문서]"
   - 외부 리소스에서 온 정보: "[외부 리소스: 소스명]"
   - 기존 지식에서 온 정보: "[기존 지식]"
3. 외부 리소스의 링크가 있다면 참조용으로 제공해주세요.

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
            print(f"[RAGService] Answer generation with full context failed: {e}")
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
