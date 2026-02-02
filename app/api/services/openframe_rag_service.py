"""
OpenFrame RAG Service

QLoRA Learning LLM 기반 Multi-Product RAG 메인 서비스.
제품 라우팅, Learning LLM, Vector/Graph 검색을 통합합니다.
"""
import asyncio
import logging
import time
from typing import AsyncGenerator, Dict, List, Optional, Any

from ..models.openframe_rag import (
    ProductId,
    SourceType,
    ConfidenceLevel,
    ClassificationResult,
    OpenFrameRAGRequest,
    OpenFrameRAGResponse,
    ProductSources,
    LearningLLMSource,
    VectorSource,
    GraphSource,
    OpenFrameRAGHealth,
    AdapterStatus,
)
from .product_router_service import get_product_router_service, ProductRouterService
from .deep_seek_service import get_deep_seek_service, DeepSeekService
from .learning_llm_service import get_learning_llm_service, LearningLLMService

logger = logging.getLogger(__name__)


class OpenFrameRAGService:
    """
    OpenFrame RAG Service

    Multi-Product RAG의 핵심 서비스로 다음을 통합합니다:
    1. Product Router: 쿼리 → 제품 분류
    2. Learning LLM: QLoRA 기반 응답 생성
    3. Vector Search: 유사도 기반 검색
    4. Graph Search: 엔티티 기반 검색
    """

    def __init__(
        self,
        product_router: Optional[ProductRouterService] = None,
        learning_llm_service: Optional[LearningLLMService] = None,
        deep_seek_service: Optional[DeepSeekService] = None,
        vector_search_service=None,
        graph_search_service=None,
    ):
        """
        Initialize OpenFrame RAG service

        Args:
            product_router: Product classification service
            learning_llm_service: QLoRA Learning LLM service
            deep_seek_service: DeepSeek comprehensive search service
            vector_search_service: Vector search service
            graph_search_service: Graph search service
        """
        self.product_router = product_router or get_product_router_service()
        self.learning_llm_service = learning_llm_service
        self.deep_seek_service = deep_seek_service
        self.vector_search_service = vector_search_service
        self.graph_search_service = graph_search_service

        self._is_initialized = False

    async def initialize(self) -> bool:
        """
        Initialize service and dependencies

        Returns:
            True if initialization succeeded
        """
        try:
            # Get Learning LLM service if not provided
            if self.learning_llm_service is None:
                self.learning_llm_service = get_learning_llm_service()

            # Initialize Learning LLM
            if self.learning_llm_service:
                await self.learning_llm_service.initialize()

            # Get DeepSeek service if not provided
            if self.deep_seek_service is None:
                self.deep_seek_service = get_deep_seek_service(
                    learning_llm_service=self.learning_llm_service,
                    vector_search_service=self.vector_search_service,
                    graph_search_service=self.graph_search_service,
                )

            self._is_initialized = True
            logger.info("OpenFrame RAG service initialized")
            return True

        except Exception as e:
            logger.error(f"Failed to initialize OpenFrame RAG service: {e}")
            return False

    async def chat(
        self,
        request: OpenFrameRAGRequest,
    ) -> OpenFrameRAGResponse:
        """
        Process RAG chat request

        Args:
            request: OpenFrame RAG request

        Returns:
            OpenFrameRAGResponse
        """
        start_time = time.time()

        try:
            # Ensure initialized
            if not self._is_initialized:
                await self.initialize()

            # Step 1: Classify query if auto
            classification = None
            product = request.product

            if product == ProductId.AUTO:
                classification = self.product_router.classify(request.message)
                product = classification.product

                # If needs selection, return early with classification info
                if classification.needs_selection:
                    return OpenFrameRAGResponse(
                        success=True,
                        response="",
                        product=product,
                        classification=classification,
                        sources=ProductSources(),
                        confidence=ConfidenceLevel.LOW,
                    )

            # Step 2: Build context from search results
            sources = ProductSources()
            context_parts = []

            # Vector search
            if request.use_vector_search and self.vector_search_service:
                try:
                    vector_results = await self._vector_search(
                        query=request.message,
                        product=product,
                        top_k=5,
                    )
                    sources.vector_search = vector_results
                    for vr in vector_results[:3]:
                        context_parts.append(f"[Document: {vr.doc_name}]\n{vr.content[:500]}")
                except Exception as e:
                    logger.warning(f"Vector search failed: {e}")

            # Graph search
            if request.use_graph_search and self.graph_search_service:
                try:
                    graph_results = await self._graph_search(
                        query=request.message,
                        product=product,
                        top_k=5,
                    )
                    sources.graph_search = graph_results
                    for gr in graph_results[:3]:
                        context_parts.append(f"[Entity: {gr.entity_name} ({gr.entity_type})]")
                except Exception as e:
                    logger.warning(f"Graph search failed: {e}")

            # Add file content if provided
            if request.file_content:
                context_parts.insert(0, f"[User File]\n{request.file_content[:2000]}")

            combined_context = "\n\n".join(context_parts) if context_parts else None

            # Step 3: Generate response with Learning LLM
            response_text = ""

            if request.use_learning_llm and self.learning_llm_service:
                try:
                    llm_result = await self.learning_llm_service.generate(
                        question=request.message,
                        context=combined_context,
                        max_tokens=1024,
                        temperature=0.7,
                    )

                    if llm_result:
                        response_text = llm_result.get("answer", "")
                        sources.learning_llm = LearningLLMSource(
                            model=llm_result.get("model", "Qwen/Qwen2.5-7B-Instruct"),
                            adapter=llm_result.get("adapter"),
                            confidence=0.8,
                            generation_time_ms=int((time.time() - start_time) * 1000),
                        )
                except Exception as e:
                    logger.error(f"Learning LLM generation failed: {e}")

            # Fallback: Generate simple response from context
            if not response_text and context_parts:
                response_text = self._generate_fallback_response(
                    query=request.message,
                    context_parts=context_parts,
                    language=request.language or "ja",
                )

            # Calculate confidence
            confidence = self._calculate_confidence(sources, response_text)

            processing_time = int((time.time() - start_time) * 1000)

            return OpenFrameRAGResponse(
                success=True,
                response=response_text,
                product=product,
                classification=classification,
                sources=sources,
                confidence=confidence,
                model="Qwen/Qwen2.5-7B-Instruct+QLoRA",
                processing_time_ms=processing_time,
            )

        except Exception as e:
            logger.exception(f"OpenFrame RAG chat error: {e}")
            return OpenFrameRAGResponse(
                success=False,
                response=f"Error: {str(e)}",
                product=request.product,
                confidence=ConfidenceLevel.LOW,
            )

    async def chat_stream(
        self,
        request: OpenFrameRAGRequest,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        Streaming RAG chat

        Yields:
            SSE-formatted events
        """
        start_time = time.time()

        try:
            # Ensure initialized
            if not self._is_initialized:
                await self.initialize()

            # Step 1: Classify (yield classification event)
            classification = None
            product = request.product

            if product == ProductId.AUTO:
                classification = self.product_router.classify(request.message)
                product = classification.product

                yield {
                    "type": "classification",
                    "data": {
                        "product": product.value,
                        "confidence": classification.confidence,
                        "needs_selection": classification.needs_selection,
                        "suggestions": classification.suggestions,
                    }
                }

                if classification.needs_selection:
                    yield {"type": "done", "data": {"needs_selection": True}}
                    return

            # Step 2: Search (yield search events)
            sources = ProductSources()
            context_parts = []

            if request.use_vector_search:
                yield {"type": "status", "data": {"step": "vector_search"}}
                try:
                    vector_results = await self._vector_search(
                        query=request.message,
                        product=product,
                        top_k=5,
                    )
                    sources.vector_search = vector_results
                    for vr in vector_results[:3]:
                        context_parts.append(f"[Document: {vr.doc_name}]\n{vr.content[:500]}")

                    yield {
                        "type": "sources",
                        "data": {
                            "source_type": "vector",
                            "count": len(vector_results),
                        }
                    }
                except Exception as e:
                    logger.warning(f"Vector search failed: {e}")

            if request.use_graph_search:
                yield {"type": "status", "data": {"step": "graph_search"}}
                try:
                    graph_results = await self._graph_search(
                        query=request.message,
                        product=product,
                        top_k=5,
                    )
                    sources.graph_search = graph_results
                    for gr in graph_results[:3]:
                        context_parts.append(f"[Entity: {gr.entity_name} ({gr.entity_type})]")

                    yield {
                        "type": "sources",
                        "data": {
                            "source_type": "graph",
                            "count": len(graph_results),
                        }
                    }
                except Exception as e:
                    logger.warning(f"Graph search failed: {e}")

            if request.file_content:
                context_parts.insert(0, f"[User File]\n{request.file_content[:2000]}")

            combined_context = "\n\n".join(context_parts) if context_parts else None

            # Step 3: Generate streaming response
            yield {"type": "status", "data": {"step": "generating"}}

            if request.use_learning_llm and self.learning_llm_service:
                try:
                    async for token in self.learning_llm_service.generate_stream(
                        question=request.message,
                        context=combined_context,
                        max_tokens=1024,
                        temperature=0.7,
                    ):
                        yield {"type": "token", "data": {"content": token}}

                    sources.learning_llm = LearningLLMSource(
                        model="Qwen/Qwen2.5-7B-Instruct",
                        confidence=0.8,
                    )

                except Exception as e:
                    logger.error(f"Learning LLM streaming failed: {e}")
                    # Fallback
                    fallback = self._generate_fallback_response(
                        query=request.message,
                        context_parts=context_parts,
                        language=request.language or "ja",
                    )
                    yield {"type": "token", "data": {"content": fallback}}

            # Final event
            processing_time = int((time.time() - start_time) * 1000)
            confidence = self._calculate_confidence(sources, "")

            yield {
                "type": "done",
                "data": {
                    "product": product.value,
                    "confidence": confidence.value,
                    "processing_time_ms": processing_time,
                    "sources": {
                        "learning_llm": sources.learning_llm.model_dump() if sources.learning_llm else None,
                        "vector_count": len(sources.vector_search),
                        "graph_count": len(sources.graph_search),
                    }
                }
            }

        except Exception as e:
            logger.exception(f"OpenFrame RAG stream error: {e}")
            yield {"type": "error", "data": {"message": str(e)}}

    async def _vector_search(
        self,
        query: str,
        product: ProductId,
        top_k: int = 5,
    ) -> List[VectorSource]:
        """Execute vector search with product filter"""
        # TODO: Integrate with existing vector search service
        # For now, return empty list
        return []

    async def _graph_search(
        self,
        query: str,
        product: ProductId,
        top_k: int = 5,
    ) -> List[GraphSource]:
        """Execute graph search with product filter"""
        # TODO: Integrate with existing graph search service
        # For now, return empty list
        return []

    def _calculate_confidence(
        self,
        sources: ProductSources,
        response: str,
    ) -> ConfidenceLevel:
        """Calculate overall confidence level"""
        score = 0.0

        # Learning LLM contribution
        if sources.learning_llm:
            score += 0.4

        # Vector search contribution
        if sources.vector_search:
            score += min(len(sources.vector_search) * 0.1, 0.3)

        # Graph search contribution
        if sources.graph_search:
            score += min(len(sources.graph_search) * 0.1, 0.3)

        # Response quality
        if response and len(response) > 100:
            score += 0.1

        if score >= 0.7:
            return ConfidenceLevel.HIGH
        elif score >= 0.4:
            return ConfidenceLevel.MEDIUM
        else:
            return ConfidenceLevel.LOW

    def _generate_fallback_response(
        self,
        query: str,
        context_parts: List[str],
        language: str = "ja",
    ) -> str:
        """Generate fallback response from context"""
        if not context_parts:
            if language == "ja":
                return "申し訳ございません。関連する情報が見つかりませんでした。別の質問をお試しください。"
            elif language == "ko":
                return "죄송합니다. 관련 정보를 찾을 수 없습니다. 다른 질문을 시도해 주세요."
            else:
                return "Sorry, no relevant information was found. Please try a different question."

        # Build response from context
        if language == "ja":
            header = f"「{query}」に関連する情報が見つかりました:\n\n"
        elif language == "ko":
            header = f"'{query}'에 관련된 정보를 찾았습니다:\n\n"
        else:
            header = f"Found information related to '{query}':\n\n"

        return header + "\n\n".join(context_parts[:3])

    async def health_check(self) -> OpenFrameRAGHealth:
        """
        Check service health

        Returns:
            OpenFrameRAGHealth status
        """
        available = False
        message = "Service not initialized"
        learning_llm_status = {}
        vector_available = False
        graph_available = False
        adapters = []

        try:
            # Check Learning LLM
            if self.learning_llm_service:
                learning_llm_status = self.learning_llm_service.get_status()
                if learning_llm_status.get("is_loaded"):
                    available = True
                    message = "Service available"

            # Check Vector search
            if self.vector_search_service:
                # TODO: Add actual health check
                vector_available = True

            # Check Graph search
            if self.graph_search_service:
                # TODO: Add actual health check
                graph_available = True

            # List adapters
            if learning_llm_status.get("available_adapters"):
                for adapter_name in learning_llm_status["available_adapters"][:5]:
                    adapters.append(AdapterStatus(
                        name=adapter_name,
                        product=ProductId.OPENFRAME_MVS,  # Default
                        loaded=adapter_name == learning_llm_status.get("current_adapter"),
                    ))

        except Exception as e:
            message = f"Health check failed: {e}"
            logger.error(message)

        return OpenFrameRAGHealth(
            available=available,
            message=message,
            learning_llm_status=learning_llm_status,
            vector_search_available=vector_available,
            graph_search_available=graph_available,
            adapters=adapters,
            supported_products=[p.value for p in ProductId if p not in (ProductId.AUTO, ProductId.OTHER)],
        )


# =============================================================================
# Singleton Instance
# =============================================================================

_openframe_rag_service: Optional[OpenFrameRAGService] = None


def get_openframe_rag_service() -> OpenFrameRAGService:
    """Get OpenFrame RAG service singleton"""
    global _openframe_rag_service
    if _openframe_rag_service is None:
        _openframe_rag_service = OpenFrameRAGService()
    return _openframe_rag_service


async def initialize_openframe_rag_service(
    learning_llm_service: Optional[LearningLLMService] = None,
    vector_search_service=None,
    graph_search_service=None,
) -> OpenFrameRAGService:
    """
    Initialize OpenFrame RAG service

    Args:
        learning_llm_service: Learning LLM service instance
        vector_search_service: Vector search service instance
        graph_search_service: Graph search service instance

    Returns:
        Initialized service
    """
    global _openframe_rag_service

    _openframe_rag_service = OpenFrameRAGService(
        learning_llm_service=learning_llm_service,
        vector_search_service=vector_search_service,
        graph_search_service=graph_search_service,
    )

    await _openframe_rag_service.initialize()

    logger.info("OpenFrame RAG service initialized")
    return _openframe_rag_service
