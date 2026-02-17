"""
Agentic RAG API Router

제품별 Agent 기반 RAG 시스템 API 엔드포인트.
다단계 질문 라우터, 정형/비정형 응답, 사후 검증을 지원합니다.
"""
import json
import logging
import time

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from ..core.deps import get_current_user
from ..models.agentic_rag import (
    AgenticRAGRequest,
    AgenticRAGResponse,
    AgenticRAGHealth,
    RouterResult,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/agentic-rag", tags=["Agentic RAG"])


# =============================================================================
# Classify-only Request Model
# =============================================================================

class ClassifyRequest(BaseModel):
    """쿼리 분류 요청"""
    query: str = Field(..., min_length=1, max_length=8000)
    language: str = Field(default="ja")


# =============================================================================
# Dependencies
# =============================================================================

def get_agentic_rag_service():
    """Get Agentic RAG service (lazy init)"""
    from ..services.agentic_rag_service import get_agentic_rag_service as _get
    return _get()


# =============================================================================
# Health & Info Endpoints
# =============================================================================

@router.get("/health", response_model=AgenticRAGHealth)
async def health_check():
    """서비스 상태 확인 (인증 불필요)"""
    try:
        service = get_agentic_rag_service()
        return await service.health_check()
    except Exception as e:
        logger.warning(f"Agentic RAG health check failed: {e}")
        return AgenticRAGHealth(
            available=False,
            message=f"Service unavailable: {str(e)}",
        )


@router.get("/products")
async def get_products(
    current_user: dict = Depends(get_current_user),
):
    """
    제품 목록 (트리 구조) 반환

    Returns:
        products: 패밀리별 그룹핑된 제품 트리
        special: 특수 옵션 (Auto)
    """
    from ..services.manual_registry_service import get_manual_registry_service

    registry = get_manual_registry_service()
    groups = registry.get_product_groups()

    product_tree = []
    for family, versions in sorted(groups.items()):
        version_list = []
        for v in versions:
            version_list.append({
                "product_id": v.product_id,
                "version": v.version,
                "doc_version": v.doc_version,
                "language": v.language,
                "pdf_count": len(v.pdf_files),
            })
        product_tree.append({
            "name": family,
            "versions": version_list,
        })

    return {
        "success": True,
        "products": product_tree,
        "special": [
            {"id": "auto", "name": "Auto"},
        ],
    }


# =============================================================================
# Classification Endpoint
# =============================================================================

@router.post("/classify", response_model=RouterResult)
async def classify_query(
    request: ClassifyRequest,
    current_user: dict = Depends(get_current_user),
):
    """쿼리 분류 (다단계 확인)"""
    try:
        service = get_agentic_rag_service()
        result = service.query_router.classify(request.query, request.language)
        return result
    except Exception as e:
        logger.exception(f"Classification error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e),
        )


# =============================================================================
# Chat Endpoints
# =============================================================================

@router.post("/chat", response_model=AgenticRAGResponse)
async def chat(
    request: AgenticRAGRequest,
    current_user: dict = Depends(get_current_user),
):
    """동기식 Agent 채팅"""
    try:
        # Long-term Memory용 user_id 주입
        request.user_id = current_user.get("user_id", "anonymous")
        service = get_agentic_rag_service()
        start = time.time()

        response = await service.chat(request)
        response.processing_time_ms = int((time.time() - start) * 1000)

        # Log query with token usage
        try:
            from ..infrastructure.services.query_log_writer import get_query_log_writer
            writer = get_query_log_writer()
            if writer:
                msg_len = len(request.message)
                resp_len = len(response.answer) if response.answer else 0
                await writer.submit_query({
                    'user_id': request.user_id,
                    'query_text': request.message,
                    'agent_type': 'agentic_rag',
                    'intent_type': response.query_type or 'unknown',
                    'category': response.product or request.product or 'auto',
                    'language': request.language or 'ja',
                    'execution_time_ms': response.processing_time_ms,
                    'input_tokens': max(1, int(msg_len / 1.5)),
                    'output_tokens': max(0, int(resp_len / 1.5)),
                    'success': True,
                    'response_summary': request.message[:200],
                })
        except Exception as log_err:
            logger.debug(f"Query log write failed (non-blocking): {log_err}")

        return response
    except TimeoutError:
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail="Request timed out. The model may be overloaded.",
        )
    except Exception as e:
        logger.exception(f"Agentic RAG chat error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e),
        )


@router.post("/stream")
async def stream_chat(
    request: AgenticRAGRequest,
    current_user: dict = Depends(get_current_user),
):
    """SSE 스트리밍 Agent 채팅"""
    # Long-term Memory용 user_id 주입
    request.user_id = current_user.get("user_id", "anonymous")
    logger.info(
        f"Agentic RAG stream from user {request.user_id}, "
        f"product={request.product}"
    )

    async def generate():
        """Generate SSE events (Agent Teams 패턴 적용) with token tracking"""
        start_time = time.time()
        output_chars = 0
        success = True
        product = request.product or "auto"
        query_type = "unknown"

        try:
            from ..services.agent_teams.team_orchestrator import get_team_orchestrator
            orchestrator = get_team_orchestrator()
            async for event in orchestrator.stream_chat_enhanced(request):
                # Track output tokens from llm_token events
                if event.get("type") == "llm_token":
                    output_chars += len(event.get("token", ""))
                elif event.get("type") == "done":
                    product = event.get("product", product)
                    query_type = event.get("query_type", query_type)
                elif event.get("type") == "error":
                    success = False

                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"

        except Exception as e:
            logger.error(f"Agentic RAG stream error: {e}")
            success = False
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"
        finally:
            # Log query with token usage (non-blocking)
            try:
                from ..infrastructure.services.query_log_writer import get_query_log_writer
                writer = get_query_log_writer()
                if writer:
                    # Estimate tokens: CJK ~1.5 chars/token, Latin ~4 chars/token
                    msg_len = len(request.message)
                    input_tokens = max(1, int(msg_len / 1.5))
                    output_tokens = max(0, int(output_chars / 1.5))

                    await writer.submit_query({
                        'user_id': request.user_id,
                        'query_text': request.message,
                        'agent_type': 'agentic_rag',
                        'intent_type': query_type,
                        'category': product,
                        'language': request.language or 'ja',
                        'execution_time_ms': int((time.time() - start_time) * 1000),
                        'input_tokens': input_tokens,
                        'output_tokens': output_tokens,
                        'success': success,
                        'response_summary': request.message[:200],
                    })
            except Exception as log_err:
                logger.debug(f"Query log write failed (non-blocking): {log_err}")

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
