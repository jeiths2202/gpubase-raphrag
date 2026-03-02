"""
OpenFrame RAG API Router

QLoRA Learning LLM 기반 Multi-Product RAG API 엔드포인트.
8개 제품에 대한 동적 라우팅 및 DeepSeek 통합 검색을 제공합니다.
"""
import json
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse

from ..core.deps import get_current_user
from ..models.openframe_rag import (
    ProductId,
    ClassifyRequest,
    ClassifyResponse,
    OpenFrameRAGRequest,
    OpenFrameRAGResponse,
    DeepSeekRequest,
    DeepSeekResponse,
    OpenFrameRAGHealth,
)
from ..services.openframe_rag_service import (
    get_openframe_rag_service,
    OpenFrameRAGService,
)
from ..services.product_router_service import (
    get_product_router_service,
    ProductRouterService,
)
from ..services.deep_seek_service import (
    get_deep_seek_service,
    DeepSeekService,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/openframe-rag", tags=["OpenFrame RAG"])


# =============================================================================
# Dependencies
# =============================================================================

def get_rag_service() -> OpenFrameRAGService:
    """Get OpenFrame RAG service"""
    return get_openframe_rag_service()


def get_router_service() -> ProductRouterService:
    """Get Product Router service"""
    return get_product_router_service()


def get_deepsearch_service() -> DeepSeekService:
    """Get DeepSeek service"""
    return get_deep_seek_service()


# =============================================================================
# Health & Info Endpoints
# =============================================================================

@router.get("/health", response_model=OpenFrameRAGHealth)
async def health_check(
    service: OpenFrameRAGService = Depends(get_rag_service),
) -> OpenFrameRAGHealth:
    """
    Check OpenFrame RAG service health.

    Returns:
        OpenFrameRAGHealth with service status
    """
    return await service.health_check()


@router.get("/products")
async def get_products(
    current_user: dict = Depends(get_current_user),
):
    """
    Get list of supported products.

    Returns:
        List of product IDs and names
    """
    products = [
        {"id": p.value, "name": p.value.replace("_", " ").title()}
        for p in ProductId
        if p not in (ProductId.AUTO, ProductId.OTHER)
    ]

    return {
        "success": True,
        "products": products,
        "special": [
            {"id": "auto", "name": "Auto (Automatic Classification)"},
            {"id": "other", "name": "Other (Search All)"},
        ]
    }


# =============================================================================
# Classification Endpoints
# =============================================================================

@router.post("/classify", response_model=ClassifyResponse)
async def classify_query(
    request: ClassifyRequest,
    current_user: dict = Depends(get_current_user),
    router_service: ProductRouterService = Depends(get_router_service),
) -> ClassifyResponse:
    """
    Classify a query to determine the target product.

    This endpoint analyzes the query and returns:
    - The detected product
    - Confidence score (0-1)
    - Whether user selection is needed (if confidence < 0.7)
    - Alternative suggestions

    Args:
        request: Classification request with query

    Returns:
        ClassifyResponse with classification result
    """
    try:
        logger.info(f"Classifying query for user {current_user.get('user_id', 'unknown')}")

        classification = router_service.classify(request.query)

        return ClassifyResponse(
            success=True,
            classification=classification,
            message="Query classified successfully",
        )

    except Exception as e:
        logger.exception(f"Classification error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e),
        )


# =============================================================================
# Chat Endpoints
# =============================================================================

@router.post("/chat", response_model=OpenFrameRAGResponse)
async def chat(
    request: OpenFrameRAGRequest,
    current_user: dict = Depends(get_current_user),
    service: OpenFrameRAGService = Depends(get_rag_service),
) -> OpenFrameRAGResponse:
    """
    OpenFrame RAG chat endpoint.

    Process flow:
    1. If product=auto, classify the query
    2. Search relevant documents (Vector + Graph)
    3. Generate response with Learning LLM
    4. Return response with sources

    Args:
        request: RAG chat request

    Returns:
        OpenFrameRAGResponse with AI response and sources
    """
    try:
        logger.info(
            f"OpenFrame RAG chat from user {current_user.get('user_id', 'unknown')}, "
            f"product={request.product.value}"
        )

        response = await service.chat(request)

        return response

    except TimeoutError:
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail="Request timed out. The model may be overloaded.",
        )
    except Exception as e:
        logger.exception(f"OpenFrame RAG chat error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e),
        )


@router.post("/stream")
async def stream_chat(
    request: OpenFrameRAGRequest,
    current_user: dict = Depends(get_current_user),
    service: OpenFrameRAGService = Depends(get_rag_service),
):
    """
    Streaming OpenFrame RAG chat endpoint.

    Streams SSE events:
    - classification: Product classification result
    - status: Processing status (vector_search, graph_search, generating)
    - sources: Source information
    - token: Generated response tokens
    - done: Completion with metadata
    - error: Error information

    Args:
        request: RAG chat request

    Returns:
        Server-Sent Events stream
    """
    logger.info(
        f"OpenFrame RAG stream from user {current_user.get('user_id', 'unknown')}, "
        f"product={request.product.value}"
    )

    async def generate():
        """Generate SSE events"""
        try:
            async for event in service.chat_stream(request):
                yield f"data: {json.dumps(event)}\n\n"

            yield "data: [DONE]\n\n"

        except Exception as e:
            logger.error(f"Stream error: {e}")
            yield f"data: {json.dumps({'type': 'error', 'data': {'message': str(e)}})}\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# =============================================================================
# DeepSeek Endpoints
# =============================================================================

@router.post("/deep-seek", response_model=DeepSeekResponse)
async def deep_seek(
    request: DeepSeekRequest,
    current_user: dict = Depends(get_current_user),
    service: DeepSeekService = Depends(get_deepsearch_service),
) -> DeepSeekResponse:
    """
    DeepSeek comprehensive search endpoint.

    Searches across ALL products and databases:
    - 8 products in parallel
    - Vector + Graph search
    - Learning LLM for each product
    - Synthesized summary

    Args:
        request: DeepSeek request

    Returns:
        DeepSeekResponse with results from all products
    """
    try:
        logger.info(
            f"DeepSeek search from user {current_user.get('user_id', 'unknown')}, "
            f"max_products={request.max_products}"
        )

        response = await service.search_comprehensive(
            query=request.message,
            history=[{"role": m.role, "content": m.content} for m in request.history] if request.history else None,
            file_content=request.file_content,
            language=request.language or "ja",
            max_products=request.max_products,
        )

        return response

    except TimeoutError:
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail="DeepSeek search timed out.",
        )
    except Exception as e:
        logger.exception(f"DeepSeek error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e),
        )


@router.post("/deep-seek/stream")
async def deep_seek_stream(
    request: DeepSeekRequest,
    current_user: dict = Depends(get_current_user),
    service: DeepSeekService = Depends(get_deepsearch_service),
):
    """
    Streaming DeepSeek comprehensive search.

    Streams progress and results:
    - progress: Current product and percentage
    - product_result: Result from each product
    - final: Synthesized summary

    Args:
        request: DeepSeek request

    Returns:
        Server-Sent Events stream with progress
    """
    logger.info(
        f"DeepSeek stream from user {current_user.get('user_id', 'unknown')}, "
        f"max_products={request.max_products}"
    )

    async def generate():
        """Generate SSE events"""
        try:
            async for progress in service.search_comprehensive_stream(
                query=request.message,
                history=[{"role": m.role, "content": m.content} for m in request.history] if request.history else None,
                file_content=request.file_content,
                language=request.language or "ja",
                max_products=request.max_products,
            ):
                # Convert Pydantic model to dict for JSON serialization
                event_data = progress.model_dump()

                # Handle nested ProductSearchResult
                if progress.product_result:
                    event_data["product_result"] = progress.product_result.model_dump()

                yield f"data: {json.dumps(event_data)}\n\n"

            yield "data: [DONE]\n\n"

        except Exception as e:
            logger.error(f"DeepSeek stream error: {e}")
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# =============================================================================
# Product-Specific Endpoints
# =============================================================================

@router.post("/chat/{product_id}", response_model=OpenFrameRAGResponse)
async def chat_with_product(
    product_id: str,
    request: OpenFrameRAGRequest,
    current_user: dict = Depends(get_current_user),
    service: OpenFrameRAGService = Depends(get_rag_service),
) -> OpenFrameRAGResponse:
    """
    Chat with a specific product (skip classification).

    Args:
        product_id: Target product ID (e.g., "openframe_mvs")
        request: RAG chat request

    Returns:
        OpenFrameRAGResponse
    """
    try:
        # Validate product ID
        try:
            product = ProductId(product_id)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid product: {product_id}. Valid products: {[p.value for p in ProductId]}",
            )

        # Override product in request
        request.product = product

        logger.info(
            f"OpenFrame RAG chat (product={product_id}) from user {current_user.get('user_id', 'unknown')}"
        )

        return await service.chat(request)

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Product chat error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e),
        )
