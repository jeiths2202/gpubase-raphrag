"""
Semantic Search Tool

LLM Query Understanding + Hybrid Retrieval 기반 시맨틱 검색
기존 unified_search.py와 통합하여 사용

Feature Flag: USE_SEMANTIC_SEARCH=true (default)
"""

import os
import logging
import time
from typing import Dict, Any, Optional, List

from .base import BaseTool
from ..types import ToolResult, AgentContext
from ...services.hybrid_retriever_service import (
    HybridRetrieverService,
    get_hybrid_retriever_service,
    create_hybrid_retriever,
)
from ...services.query_understanding_service import (
    QueryUnderstandingService,
    get_query_understanding_service,
)
from ...models.query_analysis import HybridSearchResult, QueryIntent

logger = logging.getLogger(__name__)

# Feature flags
USE_SEMANTIC_SEARCH = os.getenv("USE_SEMANTIC_SEARCH", "true").lower() == "true"
SEMANTIC_SEARCH_FALLBACK = os.getenv("SEMANTIC_SEARCH_FALLBACK", "true").lower() == "true"


class SemanticSearchTool(BaseTool):
    """시맨틱 검색 도구 (LLM Query Understanding + Hybrid Retrieval)"""

    name = "semantic_search"
    description = """
    Advanced semantic search with LLM query understanding.
    Combines Vector search, BM25 keyword search, and Entity lookup.
    Automatically analyzes query intent and extracts entities.
    """

    def __init__(
        self,
        hybrid_retriever: HybridRetrieverService = None,
        vector_search_func=None,
        keyword_search_func=None,
    ):
        self.hybrid_retriever = hybrid_retriever or get_hybrid_retriever_service()

        # 외부 검색 함수 설정
        if vector_search_func:
            self.hybrid_retriever.set_vector_search(vector_search_func)
        if keyword_search_func:
            self.hybrid_retriever.set_keyword_search(keyword_search_func)

    async def execute(
        self,
        context: AgentContext,
        query: str,
        top_k: int = 10,
        **kwargs
    ) -> ToolResult:
        """
        시맨틱 검색 실행

        Args:
            context: Agent context
            query: 검색 쿼리
            top_k: 반환할 결과 수
        """
        start_time = time.time()

        try:
            # Hybrid Search 실행
            result: HybridSearchResult = await self.hybrid_retriever.search(
                query=query,
                top_k=top_k,
                include_analysis=True,
            )

            # 결과 포맷팅
            formatted_results = self._format_results(result)

            execution_time = (time.time() - start_time) * 1000
            logger.info(f"Semantic search completed in {execution_time:.1f}ms: "
                       f"{len(result.results)} results")

            return ToolResult(
                success=True,
                data={
                    "results": formatted_results,
                    "query_analysis": {
                        "intent": result.query_analysis.intent.value if result.query_analysis else None,
                        "entities": [
                            {"type": e.type, "value": e.value, "confidence": e.confidence}
                            for e in (result.query_analysis.entities if result.query_analysis else [])
                        ],
                        "rewritten_query": result.query_analysis.rewritten_query if result.query_analysis else query,
                        "language": result.query_analysis.language if result.query_analysis else "en",
                    },
                    "metadata": {
                        "total_candidates": result.total_candidates,
                        "search_time_ms": result.search_time_ms,
                        "vector_count": result.vector_count,
                        "keyword_count": result.keyword_count,
                        "entity_count": result.entity_count,
                    }
                },
                message=f"Found {len(result.results)} results"
            )

        except Exception as e:
            logger.error(f"Semantic search error: {e}", exc_info=True)
            return ToolResult(
                success=False,
                error=str(e),
                message="Semantic search failed"
            )

    def _format_results(self, result: HybridSearchResult) -> List[Dict[str, Any]]:
        """검색 결과 포맷팅"""
        formatted = []

        for r in result.results:
            formatted.append({
                "doc_id": r.doc_id,
                "content": r.content,
                "score": r.score,
                "source": r.source,
                "original_scores": r.original_scores,
                "document_title": r.document_title,
                "page_number": r.page_number,
                "pdf_path": r.pdf_path,
                "metadata": r.metadata,
            })

        return formatted


# =============================================================
# Integration with existing unified_search
# =============================================================

async def semantic_search_wrapper(
    query: str,
    top_k: int = 10,
    context: AgentContext = None,
    vector_search_func=None,
    keyword_search_func=None,
    **kwargs
) -> Dict[str, Any]:
    """
    Semantic Search wrapper for integration with existing code

    Returns unified_search compatible format
    """
    if not USE_SEMANTIC_SEARCH:
        return {"results": [], "use_fallback": True}

    try:
        tool = SemanticSearchTool(
            vector_search_func=vector_search_func,
            keyword_search_func=keyword_search_func,
        )

        result = await tool.execute(
            context=context or AgentContext(),
            query=query,
            top_k=top_k,
            **kwargs
        )

        if not result.success:
            return {"results": [], "use_fallback": SEMANTIC_SEARCH_FALLBACK}

        return {
            "results": result.data.get("results", []),
            "query_analysis": result.data.get("query_analysis", {}),
            "metadata": result.data.get("metadata", {}),
            "use_fallback": False,
        }

    except Exception as e:
        logger.error(f"Semantic search wrapper error: {e}")
        return {"results": [], "use_fallback": SEMANTIC_SEARCH_FALLBACK}


def get_query_understanding_for_bm25(query: str) -> Dict[str, Any]:
    """
    BM25 검색을 위한 쿼리 분석 (동기 버전)

    Returns:
        {
            "rewritten_query": "...",
            "entities": [...],
            "intent": "...",
            "keywords": [...]
        }
    """
    service = get_query_understanding_service()
    analysis = service.analyze_sync(query)

    return {
        "rewritten_query": analysis.rewritten_query,
        "entities": [
            {"type": e.type, "value": e.value}
            for e in analysis.entities
        ],
        "intent": analysis.intent.value,
        "keywords": analysis.keywords,
        "language": analysis.language,
    }


# =============================================================
# Factory functions
# =============================================================

_tool_instance: Optional[SemanticSearchTool] = None


def get_semantic_search_tool(
    vector_search_func=None,
    keyword_search_func=None,
) -> SemanticSearchTool:
    """SemanticSearchTool 싱글톤 반환"""
    global _tool_instance
    if _tool_instance is None:
        _tool_instance = SemanticSearchTool(
            vector_search_func=vector_search_func,
            keyword_search_func=keyword_search_func,
        )
    return _tool_instance


async def initialize_semantic_search(
    neo4j_driver=None,
    vector_search_func=None,
    keyword_search_func=None,
) -> SemanticSearchTool:
    """
    Semantic Search 초기화

    애플리케이션 시작 시 호출하여 인덱스 로드 및 서비스 초기화
    """
    # HybridRetriever 생성
    hybrid_retriever = await create_hybrid_retriever(
        neo4j_driver=neo4j_driver,
        vector_search_func=vector_search_func,
        keyword_search_func=keyword_search_func,
    )

    # Tool 생성
    tool = SemanticSearchTool(hybrid_retriever=hybrid_retriever)

    global _tool_instance
    _tool_instance = tool

    logger.info("Semantic Search initialized successfully")
    return tool
