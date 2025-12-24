"""
Query API Router
RAG 시스템 질의 관련 API
"""
import time
import uuid
from typing import AsyncGenerator
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sse_starlette.sse import EventSourceResponse

from ..models.base import SuccessResponse, MetaInfo
from ..models.query import (
    QueryRequest,
    QueryResponse,
    ClassifyResponse,
    ClassificationResult,
    ClassificationFeatures,
    StrategyType,
    LanguageType,
    SourceInfo,
    QueryAnalysis,
)
from ..core.deps import get_current_user, get_rag_service

router = APIRouter(prefix="/query", tags=["Query"])


@router.post(
    "",
    response_model=SuccessResponse[QueryResponse],
    summary="RAG 질의 실행",
    description="Hybrid RAG 시스템을 통해 질문에 대한 답변을 생성합니다."
)
async def execute_query(
    request: QueryRequest,
    current_user: dict = Depends(get_current_user),
    rag_service = Depends(get_rag_service)
):
    """Execute RAG query and return answer with sources"""
    start_time = time.time()
    request_id = f"req_{uuid.uuid4().hex[:12]}"

    try:
        # Execute RAG query via service
        result = await rag_service.query(
            question=request.question,
            strategy=request.strategy.value,
            language=request.language.value,
            top_k=request.options.top_k if request.options else 5,
            conversation_id=request.options.conversation_id if request.options else None
        )

        processing_time = int((time.time() - start_time) * 1000)

        return SuccessResponse(
            data=QueryResponse(
                answer=result["answer"],
                strategy=StrategyType(result["strategy"]),
                language=LanguageType(result["language"]),
                confidence=result.get("confidence", 0.85),
                sources=[SourceInfo(**s) for s in result.get("sources", [])],
                query_analysis=QueryAnalysis(**result["query_analysis"]) if result.get("query_analysis") else None
            ),
            meta=MetaInfo(
                request_id=request_id,
                processing_time_ms=processing_time
            )
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post(
    "/stream",
    summary="스트리밍 응답 질의",
    description="Server-Sent Events를 통해 실시간으로 응답을 스트리밍합니다."
)
async def stream_query(
    request: QueryRequest,
    current_user: dict = Depends(get_current_user),
    rag_service = Depends(get_rag_service)
):
    """Stream RAG query response via SSE"""
    query_id = f"q_{uuid.uuid4().hex[:12]}"

    async def generate_events() -> AsyncGenerator[dict, None]:
        start_time = time.time()

        # Start event
        yield {
            "event": "start",
            "data": {"query_id": query_id, "strategy": request.strategy.value}
        }

        try:
            # Stream answer chunks
            async for chunk in rag_service.stream_query(
                question=request.question,
                strategy=request.strategy.value,
                language=request.language.value
            ):
                if chunk.get("type") == "text":
                    yield {"event": "chunk", "data": {"text": chunk["content"]}}
                elif chunk.get("type") == "sources":
                    yield {"event": "sources", "data": {"sources": chunk["sources"]}}

            # Done event
            processing_time = int((time.time() - start_time) * 1000)
            yield {"event": "done", "data": {"processing_time_ms": processing_time}}

        except Exception as e:
            yield {"event": "error", "data": {"message": str(e)}}

    return EventSourceResponse(generate_events())


@router.get(
    "/classify",
    response_model=SuccessResponse[ClassifyResponse],
    summary="질문 분류",
    description="질문을 분석하여 최적의 검색 전략을 결정합니다."
)
async def classify_query(
    question: str = Query(..., min_length=1, max_length=2000, description="분류할 질문"),
    current_user: dict = Depends(get_current_user),
    rag_service = Depends(get_rag_service)
):
    """Classify query without executing search"""
    request_id = f"req_{uuid.uuid4().hex[:12]}"
    start_time = time.time()

    try:
        result = await rag_service.classify_query(question)

        processing_time = int((time.time() - start_time) * 1000)

        return SuccessResponse(
            data=ClassifyResponse(
                question=question,
                classification=ClassificationResult(
                    strategy=StrategyType(result["strategy"]),
                    confidence=result["confidence"],
                    probabilities=result["probabilities"]
                ),
                features=ClassificationFeatures(
                    language=result["language"],
                    has_error_code=result.get("has_error_code", False),
                    is_comprehensive=result.get("is_comprehensive", False),
                    is_code_query=result.get("is_code_query", False)
                )
            ),
            meta=MetaInfo(
                request_id=request_id,
                processing_time_ms=processing_time
            )
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
