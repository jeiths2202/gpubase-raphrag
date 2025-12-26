"""
Mock RAG Service

Provides predefined RAG responses without requiring
GPU, vector stores, or external LLM APIs.
"""
from typing import Optional, Dict, Any, List
from datetime import datetime
import uuid


class MockRAGService:
    """
    Mock RAG service for testing.

    Features:
    - Predefined responses for common queries
    - Configurable response templates
    - Call tracking for assertions
    - No external dependencies
    """

    # Predefined responses for testing
    DEFAULT_RESPONSES = {
        "en": {
            "default": "This is a mock response for testing purposes.",
            "chart": "The chart shows an upward trend in the data.",
            "table": "The table contains structured data with multiple columns.",
            "code": "Here is a sample code implementation:\n```python\ndef example():\n    return 'Hello, World!'\n```",
        },
        "ko": {
            "default": "이것은 테스트 목적의 모의 응답입니다.",
            "chart": "차트는 데이터의 상승 추세를 보여줍니다.",
            "table": "테이블에는 여러 열이 있는 구조화된 데이터가 포함되어 있습니다.",
            "code": "다음은 샘플 코드 구현입니다:\n```python\ndef example():\n    return 'Hello, World!'\n```",
        }
    }

    def __init__(
        self,
        response_delay_ms: int = 0,
        default_confidence: float = 0.85
    ):
        self.response_delay_ms = response_delay_ms
        self.default_confidence = default_confidence
        self._call_count = 0
        self._call_history: List[Dict[str, Any]] = []
        self._custom_responses: Dict[str, str] = {}

    async def query(
        self,
        query: str,
        language: str = "en",
        top_k: int = 5,
        document_ids: List[str] = None,
        use_graph: bool = True,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Execute RAG query and return mock response.

        Args:
            query: The user's question
            language: Response language (en, ko)
            top_k: Number of results to retrieve
            document_ids: Optional list of document IDs to search
            use_graph: Whether to use graph-based retrieval

        Returns:
            Dict with answer, sources, and metadata
        """
        import asyncio

        self._call_count += 1
        query_id = f"query_{uuid.uuid4().hex[:12]}"

        # Record call
        self._call_history.append({
            "query_id": query_id,
            "query": query,
            "language": language,
            "top_k": top_k,
            "document_ids": document_ids,
            "use_graph": use_graph,
            "timestamp": datetime.utcnow().isoformat(),
            "kwargs": kwargs
        })

        # Simulate delay if configured
        if self.response_delay_ms > 0:
            await asyncio.sleep(self.response_delay_ms / 1000)

        # Determine response type based on query content
        response_type = self._detect_response_type(query)

        # Get appropriate response
        lang_responses = self.DEFAULT_RESPONSES.get(language, self.DEFAULT_RESPONSES["en"])
        answer = self._custom_responses.get(query) or lang_responses.get(response_type, lang_responses["default"])

        # Generate mock sources
        sources = self._generate_mock_sources(document_ids, top_k)

        return {
            "query_id": query_id,
            "answer": answer,
            "sources": sources,
            "confidence": self.default_confidence,
            "language": language,
            "query_type": response_type,
            "routing": {
                "selected_llm": "text" if response_type != "chart" else "vision",
                "reasoning": f"Query routed based on {response_type} detection"
            },
            "metadata": {
                "total_tokens": len(query) // 4 + len(answer) // 4,
                "latency_ms": self.response_delay_ms or 50,
                "model_used": "mock-llm",
                "retrieval_count": len(sources)
            }
        }

    def _detect_response_type(self, query: str) -> str:
        """Detect query type from content"""
        query_lower = query.lower()

        if any(word in query_lower for word in ["chart", "graph", "차트", "그래프", "visualization"]):
            return "chart"
        elif any(word in query_lower for word in ["table", "표", "데이터", "data"]):
            return "table"
        elif any(word in query_lower for word in ["code", "function", "코드", "함수", "implement"]):
            return "code"
        else:
            return "default"

    def _generate_mock_sources(
        self,
        document_ids: List[str] = None,
        count: int = 3
    ) -> List[Dict[str, Any]]:
        """Generate mock source documents"""
        sources = []

        if document_ids:
            for i, doc_id in enumerate(document_ids[:count]):
                sources.append({
                    "document_id": doc_id,
                    "filename": f"document_{i+1}.pdf",
                    "chunk_id": f"chunk_{doc_id}_{i}",
                    "content": f"This is content from {doc_id}...",
                    "page_number": i + 1,
                    "relevance_score": 0.95 - (i * 0.05)
                })
        else:
            for i in range(min(count, 3)):
                sources.append({
                    "document_id": f"mock_doc_{i+1}",
                    "filename": f"mock_document_{i+1}.pdf",
                    "chunk_id": f"chunk_mock_{i}",
                    "content": f"Mock content for testing source {i+1}...",
                    "page_number": i + 1,
                    "relevance_score": 0.90 - (i * 0.05)
                })

        return sources

    async def get_document_context(
        self,
        document_ids: List[str],
        query: str = None
    ) -> List[Dict[str, Any]]:
        """Get context from specific documents"""
        self._call_history.append({
            "method": "get_document_context",
            "document_ids": document_ids,
            "query": query,
            "timestamp": datetime.utcnow().isoformat()
        })

        return self._generate_mock_sources(document_ids, len(document_ids))

    async def hybrid_search(
        self,
        query: str,
        vector_weight: float = 0.5,
        graph_weight: float = 0.5,
        top_k: int = 10
    ) -> List[Dict[str, Any]]:
        """Perform hybrid vector + graph search"""
        self._call_history.append({
            "method": "hybrid_search",
            "query": query,
            "vector_weight": vector_weight,
            "graph_weight": graph_weight,
            "top_k": top_k,
            "timestamp": datetime.utcnow().isoformat()
        })

        return self._generate_mock_sources(None, top_k)

    async def health_check(self) -> Dict[str, Any]:
        """Health check for RAG service"""
        return {
            "status": "healthy",
            "components": {
                "vector_store": "mock",
                "graph_store": "mock",
                "llm": "mock"
            },
            "timestamp": datetime.utcnow().isoformat()
        }

    # ==================== Test Helpers ====================

    def set_custom_response(self, query: str, response: str) -> None:
        """Set custom response for specific query"""
        self._custom_responses[query] = response

    def set_confidence(self, confidence: float) -> None:
        """Set default confidence level"""
        self.default_confidence = confidence

    def get_call_count(self) -> int:
        """Get number of calls made"""
        return self._call_count

    def get_call_history(self) -> List[Dict[str, Any]]:
        """Get call history for assertions"""
        return self._call_history

    def get_last_call(self) -> Optional[Dict[str, Any]]:
        """Get the most recent call"""
        return self._call_history[-1] if self._call_history else None

    def reset(self) -> None:
        """Reset mock state"""
        self._call_count = 0
        self._call_history.clear()
        self._custom_responses.clear()
