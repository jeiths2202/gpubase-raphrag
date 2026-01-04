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
    QueryOptions,
    ClassifyResponse,
    ClassificationResult,
    ClassificationFeatures,
    StrategyType,
    LanguageType,
    SourceInfo,
    QueryAnalysis,
)
from ..core.deps import get_current_user, get_rag_service
from ..core.tracing import get_trace_context_from_request, detect_response_quality, should_sample_trace
from ..core.app_mode import get_app_mode_manager
from ..infrastructure.services.trace_writer import get_trace_writer

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
        # Get options with defaults
        opts = request.options or QueryOptions()

        # Execute RAG query via service with session document and external resource support
        result = await rag_service.query(
            question=request.question,
            strategy=request.strategy.value,
            language=request.language.value,
            top_k=opts.top_k,
            conversation_id=opts.conversation_id,
            # Session document options
            session_id=opts.session_id,
            use_session_docs=opts.use_session_docs,
            session_weight=opts.session_weight,
            # External resource options
            user_id=current_user.get("user_id") or current_user.get("id"),
            use_external_resources=opts.use_external_resources,
            external_weight=opts.external_weight
        )

        processing_time = int((time.time() - start_time) * 1000)

        # Build sources list with session document and external resource info
        sources = []
        for s in result.get("sources", []):
            source_info = SourceInfo(
                doc_id=s.get("doc_id", ""),
                doc_name=s.get("doc_name", ""),
                chunk_id=s.get("chunk_id", ""),
                chunk_index=s.get("chunk_index", 0),
                content=s.get("content", ""),
                score=s.get("score", 0.0),
                source_type=s.get("source_type", "unknown"),
                entities=s.get("entities", []),
                is_session_doc=s.get("is_session_doc", False),
                page_number=s.get("page_number"),
                is_external_resource=s.get("is_external_resource", False),
                source_url=s.get("source_url"),
                external_source=s.get("external_source"),
                section_title=s.get("section_title")
            )
            sources.append(source_info)

        # ==================== Trace Persistence ====================
        # Detect quality and persist trace data for E2E message tracing
        trace_ctx = get_trace_context_from_request()
        if trace_ctx:
            try:
                # Detect response quality
                response_quality_flag = detect_response_quality(
                    response=result["answer"],
                    rag_confidence=result.get("confidence", 0.0),
                    user_feedback=None  # TODO: Get from conversation feedback if available
                )

                # Mode-aware sampling: DEVELOP=100%, PRODUCT=10% success/100% errors
                mode_manager = get_app_mode_manager()
                is_error = response_quality_flag == "ERROR"
                if not should_sample_trace(mode_manager, is_error=is_error):
                    # Skip trace persistence for this request (sampling decision)
                    return SuccessResponse(
                        data=QueryResponse(
                            answer=result["answer"],
                            strategy=StrategyType(result["strategy"]),
                            language=LanguageType(result["language"]),
                            confidence=result.get("confidence", 0.85),
                            sources=sources,
                            query_analysis=QueryAnalysis(**result["query_analysis"]) if result.get("query_analysis") else None
                        ),
                        meta=MetaInfo(
                            request_id=request_id,
                            processing_time_ms=processing_time
                        )
                    )

                # Assemble trace data
                trace_data = {
                    'trace_id': trace_ctx.trace_id,
                    'user_id': current_user.get("user_id") or current_user.get("id", "unknown"),
                    'session_id': opts.session_id if opts else None,
                    'conversation_id': opts.conversation_id if opts else None,
                    'original_prompt': request.question,
                    'normalized_prompt': request.question,  # TODO: Add normalization if needed
                    'model_name': 'hybrid-rag',  # TODO: Get actual model from result
                    'model_version': None,
                    'inference_params': {},
                    'start_time': trace_ctx.spans[trace_ctx.root_span_id].start_time,
                    'end_time': trace_ctx.spans[trace_ctx.root_span_id].end_time,
                    'total_latency_ms': processing_time,
                    'embedding_latency_ms': None,  # Will be filled from spans
                    'retrieval_latency_ms': None,  # Will be filled from spans
                    'generation_latency_ms': None,  # Will be filled from spans
                    'response_content': result["answer"],
                    'response_length': len(result["answer"]),
                    'input_tokens': 0,  # TODO: Calculate from prompt
                    'output_tokens': 0,  # TODO: Calculate from response
                    'total_tokens': 0,
                    'response_quality_flag': response_quality_flag,
                    'error_code': None,
                    'error_message': None,
                    'error_stacktrace': None,
                    'strategy': result.get("strategy", "auto"),
                    'language': result.get("language", "auto"),
                    'rag_confidence_score': result.get("confidence", 0.0),
                    'rag_result_count': len(sources),
                    'metadata': {
                        'used_session_docs': result.get("query_analysis", {}).get("used_session_docs", False),
                        'used_external_resources': result.get("query_analysis", {}).get("used_external_resources", False)
                    }
                }

                # Extract latencies from spans
                for span in trace_ctx.spans.values():
                    if span.span_type.value == "EMBEDDING" and span.latency_ms:
                        trace_data['embedding_latency_ms'] = span.latency_ms
                    elif span.span_type.value == "RETRIEVAL" and span.latency_ms:
                        trace_data['retrieval_latency_ms'] = span.latency_ms
                    elif span.span_type.value == "GENERATION" and span.latency_ms:
                        trace_data['generation_latency_ms'] = span.latency_ms
                        # Try to extract token counts from metadata
                        if 'input_tokens' in span.metadata:
                            trace_data['input_tokens'] = span.metadata['input_tokens']
                        if 'output_tokens' in span.metadata:
                            trace_data['output_tokens'] = span.metadata['output_tokens']

                # Calculate total tokens
                trace_data['total_tokens'] = trace_data['input_tokens'] + trace_data['output_tokens']

                # Submit to trace writer for background persistence
                trace_writer = get_trace_writer()
                await trace_writer.submit_trace(trace_data, trace_ctx.get_all_spans())

            except Exception as e:
                # Log trace persistence failure but don't fail the request
                import logging
                logger = logging.getLogger(__name__)
                logger.error(f"Trace persistence failed: {e}", exc_info=True)

        return SuccessResponse(
            data=QueryResponse(
                answer=result["answer"],
                strategy=StrategyType(result["strategy"]),
                language=LanguageType(result["language"]),
                confidence=result.get("confidence", 0.85),
                sources=sources,
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
        opts = request.options or QueryOptions()

        # Start event
        yield {
            "event": "start",
            "data": {"query_id": query_id, "strategy": request.strategy.value}
        }

        try:
            # Stream answer chunks with session document support
            async for chunk in rag_service.stream_query(
                question=request.question,
                strategy=request.strategy.value,
                language=request.language.value,
                session_id=opts.session_id,
                use_session_docs=opts.use_session_docs
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
