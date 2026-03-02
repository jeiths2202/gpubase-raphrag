"""
RAG Query Router
할루시네이션 방지 RAG 엔드포인트

Endpoints:
- POST /api/v1/query/rag       - RAG 기반 쿼리 (메인)
- POST /api/v1/query/rag/search - 검색만 수행 (디버깅용)
- GET  /api/v1/query/rag/stats  - 서비스 통계
- GET  /api/v1/query/rag/health - 상태 확인
"""

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from typing import Optional, List, Dict
from enum import Enum
import logging

from ..services.rag_anti_hallucination_service import (
    RAGAntiHallucinationService,
    get_rag_service
)
from ..core.deps import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/query/rag", tags=["RAG Query"])


# ============================================================
# Enums
# ============================================================

class RAGMode(str, Enum):
    """RAG 쿼리 모드"""
    DIRECT = "direct"      # LLM 우회, 100% 정확
    LLM = "llm"            # LLM으로 재구성
    HYBRID = "hybrid"      # 자동 선택 (권장)


# ============================================================
# Request Models
# ============================================================

class RAGQueryRequest(BaseModel):
    """RAG 쿼리 요청"""
    query: str = Field(
        ...,
        description="사용자 질문",
        min_length=1,
        max_length=1000,
        examples=["DFSURGL0について説明してください。"]
    )
    mode: RAGMode = Field(
        default=RAGMode.HYBRID,
        description="RAG 모드: direct (100% 정확), llm (자연스러운 답변), hybrid (자동 선택)"
    )
    model: Optional[str] = Field(
        default="openframe_common_v2",
        description="LLM 모델 이름 (llm/hybrid 모드에서 사용)"
    )
    max_tokens: int = Field(
        default=500,
        ge=50,
        le=2000,
        description="최대 토큰 수"
    )
    temperature: float = Field(
        default=0.2,
        ge=0.0,
        le=2.0,
        description="Temperature (낮을수록 정확, 높을수록 창의적)"
    )

    model_config = {
        "json_schema_extra": {
            "example": {
                "query": "DFSURGL0について説明してください。",
                "mode": "hybrid",
                "model": "openframe_common_v2",
                "max_tokens": 500,
                "temperature": 0.2
            }
        }
    }


class RAGSearchRequest(BaseModel):
    """RAG 검색 요청 (디버깅용)"""
    query: str = Field(..., min_length=1, max_length=1000)
    top_k: int = Field(default=5, ge=1, le=20)


# ============================================================
# Response Models
# ============================================================

class SourceInfo(BaseModel):
    """출처 정보"""
    product: str = Field(..., description="제품명")
    name: str = Field(..., description="항목명")
    score: int = Field(..., description="검색 점수")


class MetadataInfo(BaseModel):
    """메타데이터"""
    search_time_ms: float = Field(..., description="검색 시간 (ms)")
    llm_time_ms: float = Field(..., description="LLM 처리 시간 (ms)")
    total_time_ms: float = Field(..., description="총 처리 시간 (ms)")
    error: Optional[str] = Field(None, description="에러 메시지 (있는 경우)")


class RAGQueryResponse(BaseModel):
    """RAG 쿼리 응답"""
    answer: str = Field(..., description="응답 내용")
    mode_used: str = Field(
        ...,
        description="실제 사용된 모드: direct_answer, llm_with_context, no_sources, error"
    )
    search_score: int = Field(..., description="검색 점수 (0-23)")
    sources: List[SourceInfo] = Field(default_factory=list, description="출처 목록")
    keyword_extracted: Optional[str] = Field(None, description="추출된 키워드")
    metadata: MetadataInfo = Field(..., description="처리 메타데이터")

    model_config = {
        "json_schema_extra": {
            "example": {
                "answer": "DFSURGL0は、HD再編成アンロード・ユーティリティ...",
                "mode_used": "direct_answer",
                "search_score": 23,
                "sources": [
                    {"product": "openframe_common", "name": "DFSURGL0", "score": 23}
                ],
                "keyword_extracted": "DFSURGL0",
                "metadata": {
                    "search_time_ms": 45.0,
                    "llm_time_ms": 0.0,
                    "total_time_ms": 45.0
                }
            }
        }
    }


class RAGSearchResult(BaseModel):
    """개별 검색 결과"""
    product: str
    name: str
    score: int
    instruction: str
    response: str


class RAGSearchResponse(BaseModel):
    """RAG 검색 응답 (디버깅용)"""
    query: str
    keyword_extracted: str
    results_count: int
    results: List[RAGSearchResult]
    error: Optional[str] = None


class RAGStatsResponse(BaseModel):
    """RAG 통계 응답"""
    total_documents: int = Field(..., description="총 문서 수")
    products: Dict[str, int] = Field(..., description="제품별 문서 수")
    total_queries: int = Field(..., description="총 쿼리 수")
    modes_usage: Dict[str, int] = Field(..., description="모드별 사용 횟수")
    avg_search_time_ms: float = Field(..., description="평균 검색 시간")
    avg_llm_time_ms: float = Field(..., description="평균 LLM 처리 시간")
    error: Optional[str] = None


class RAGHealthResponse(BaseModel):
    """RAG 상태 응답"""
    status: str = Field(..., description="healthy 또는 unhealthy")
    documents_loaded: int = Field(..., description="로드된 문서 수")
    available_modes: List[str] = Field(..., description="사용 가능한 모드")
    error: Optional[str] = None


# ============================================================
# Endpoints
# ============================================================

@router.post("", response_model=RAGQueryResponse)
async def query_with_rag(
    request: RAGQueryRequest,
    current_user: dict = Depends(get_current_user),
    rag_service: RAGAntiHallucinationService = Depends(get_rag_service)
):
    """
    RAG 기반 쿼리 (할루시네이션 방지)

    **Modes:**
    - `direct`: 학습 데이터 직접 반환 (100% 정확, 환각 불가능)
    - `llm`: LLM으로 재구성 (자연스러운 답변)
    - `hybrid`: 자동 선택 (권장) - 정확한 키워드면 direct, 애매하면 llm

    **Score 기준:**
    - instruction에 키워드 포함: +10점
    - response에 키워드 포함: +5점
    - name에 키워드 포함: +8점
    - Score >= 10 → Direct Answer
    - Score < 10 → LLM with Context

    **Example:**
    ```bash
    curl -X POST http://localhost:9000/api/v1/query/rag \\
      -H "Authorization: Bearer <token>" \\
      -H "Content-Type: application/json" \\
      -d '{"query": "DFSURGL0について説明してください。", "mode": "hybrid"}'
    ```
    """
    try:
        logger.info(f"RAG query from user {current_user['username']}: {request.query[:50]}...")

        if request.mode == RAGMode.DIRECT:
            result = await rag_service.query_direct(request.query)
        elif request.mode == RAGMode.LLM:
            result = await rag_service.query_llm(
                query=request.query,
                model=request.model,
                max_tokens=request.max_tokens,
                temperature=request.temperature
            )
        else:  # hybrid (default)
            result = await rag_service.query_hybrid(
                query=request.query,
                model=request.model,
                max_tokens=request.max_tokens,
                temperature=request.temperature
            )

        logger.info(f"RAG query completed: mode={result['mode_used']}, score={result['search_score']}")

        # Convert to response model
        return RAGQueryResponse(
            answer=result['answer'],
            mode_used=result['mode_used'],
            search_score=result['search_score'],
            sources=[SourceInfo(**s) for s in result['sources']],
            keyword_extracted=result['keyword_extracted'],
            metadata=MetadataInfo(**result['metadata'])
        )

    except Exception as e:
        logger.error(f"RAG query failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"RAG query failed: {str(e)}"
        )


@router.post("/search", response_model=RAGSearchResponse)
async def search_training_data(
    request: RAGSearchRequest,
    current_user: dict = Depends(get_current_user),
    rag_service: RAGAntiHallucinationService = Depends(get_rag_service)
):
    """
    학습 데이터 검색만 수행 (LLM 사용 안 함)

    디버깅 및 검색 품질 확인용입니다.
    keyword_extracted와 results_count를 확인하여
    검색 로직을 디버깅할 수 있습니다.
    """
    try:
        result = await rag_service.search_only(request.query, request.top_k)

        return RAGSearchResponse(
            query=result['query'],
            keyword_extracted=result['keyword_extracted'],
            results_count=result['results_count'],
            results=[RAGSearchResult(**r) for r in result['results']],
            error=result.get('error')
        )

    except Exception as e:
        logger.error(f"RAG search failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Search failed: {str(e)}"
        )


@router.get("/stats", response_model=RAGStatsResponse)
async def get_rag_stats(
    current_user: dict = Depends(get_current_user),
    rag_service: RAGAntiHallucinationService = Depends(get_rag_service)
):
    """
    RAG 서비스 통계

    제품별 문서 수, 모드별 사용 횟수, 평균 처리 시간 등을 반환합니다.
    """
    try:
        stats = rag_service.get_stats()
        return RAGStatsResponse(**stats)

    except Exception as e:
        logger.error(f"Get stats failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Get stats failed: {str(e)}"
        )


@router.get("/health", response_model=RAGHealthResponse)
async def rag_health():
    """
    RAG 서비스 상태 확인

    인증 없이 접근 가능합니다.
    서비스 모니터링용입니다.
    """
    try:
        rag_service = get_rag_service()

        if rag_service.is_initialized:
            return RAGHealthResponse(
                status="healthy",
                documents_loaded=len(rag_service.rag.documents),
                available_modes=["direct", "llm", "hybrid"]
            )
        else:
            return RAGHealthResponse(
                status="unhealthy",
                documents_loaded=0,
                available_modes=[],
                error="RAG service not initialized"
            )

    except Exception as e:
        return RAGHealthResponse(
            status="unhealthy",
            documents_loaded=0,
            available_modes=[],
            error=str(e)
        )
