"""
DeepSeek Service

모든 제품 및 데이터베이스에서 종합 검색을 수행하는 서비스.
병렬 검색으로 8개 제품에서 동시에 검색하고 결과를 통합합니다.
"""
import asyncio
import logging
import time
from typing import AsyncGenerator, Dict, List, Optional, Any

from ..models.openframe_rag import (
    ProductId,
    ProductSearchResult,
    ProductSources,
    DeepSeekProgress,
    DeepSeekResponse,
    LearningLLMSource,
    VectorSource,
    GraphSource,
)

logger = logging.getLogger(__name__)


class DeepSeekService:
    """
    DeepSeek Service

    모든 제품 및 데이터베이스에서 종합적인 검색을 수행합니다.
    - 8개 제품 병렬 검색
    - Vector + Graph DB 통합
    - Learning LLM 응답 생성
    - 결과 통합 및 요약
    """

    def __init__(
        self,
        learning_llm_service=None,
        vector_search_service=None,
        graph_search_service=None,
        max_parallel: int = 4,
    ):
        """
        Initialize DeepSeek service

        Args:
            learning_llm_service: Learning LLM service instance
            vector_search_service: Vector search service instance
            graph_search_service: Graph search service instance
            max_parallel: Maximum parallel searches (기본: 4)
        """
        self.learning_llm_service = learning_llm_service
        self.vector_search_service = vector_search_service
        self.graph_search_service = graph_search_service
        self.max_parallel = max_parallel

        # All products to search
        self.all_products = [
            ProductId.OPENFRAME_MVS,
            ProductId.MSP_OPENFRAME,
            ProductId.VOS3_OPENFRAME,
            ProductId.TIBERO7,
            ProductId.OFASM,
            ProductId.OFCOBOL,
            ProductId.XSP_OPENFRAME,
            ProductId.TMAX,
        ]

    async def search_comprehensive(
        self,
        query: str,
        history: Optional[List[Dict]] = None,
        file_content: Optional[str] = None,
        language: str = "ja",
        max_products: int = 8,
    ) -> DeepSeekResponse:
        """
        Comprehensive search across all products

        Args:
            query: User query
            history: Conversation history
            file_content: Optional file content
            language: UI language
            max_products: Maximum products to search

        Returns:
            DeepSeekResponse with all results
        """
        start_time = time.time()
        products_to_search = self.all_products[:max_products]

        # Search all products in parallel
        tasks = [
            self._search_product(
                product=product,
                query=query,
                history=history,
                file_content=file_content,
                language=language,
            )
            for product in products_to_search
        ]

        # Use semaphore to limit parallelism
        semaphore = asyncio.Semaphore(self.max_parallel)

        async def bounded_search(task):
            async with semaphore:
                return await task

        results = await asyncio.gather(
            *[bounded_search(task) for task in tasks],
            return_exceptions=True
        )

        # Process results
        product_results: List[ProductSearchResult] = []
        total_sources = 0

        for i, result in enumerate(results):
            if isinstance(result, Exception):
                logger.error(f"DeepSeek search error for {products_to_search[i]}: {result}")
                product_results.append(ProductSearchResult(
                    product=products_to_search[i],
                    response="",
                    sources=ProductSources(),
                    confidence=0.0,
                    error=str(result),
                ))
            else:
                product_results.append(result)
                total_sources += (
                    len(result.sources.vector_search) +
                    len(result.sources.graph_search)
                )

        # Sort by confidence
        product_results.sort(key=lambda x: x.confidence, reverse=True)

        # Generate summary from all results
        summary = await self._generate_summary(
            query=query,
            product_results=product_results,
            language=language,
        )

        processing_time = int((time.time() - start_time) * 1000)

        return DeepSeekResponse(
            success=True,
            query=query,
            summary=summary,
            product_results=product_results,
            total_sources=total_sources,
            processing_time_ms=processing_time,
            products_searched=len(products_to_search),
        )

    async def search_comprehensive_stream(
        self,
        query: str,
        history: Optional[List[Dict]] = None,
        file_content: Optional[str] = None,
        language: str = "ja",
        max_products: int = 8,
    ) -> AsyncGenerator[DeepSeekProgress, None]:
        """
        Streaming comprehensive search with progress updates

        Yields:
            DeepSeekProgress events
        """
        start_time = time.time()
        products_to_search = self.all_products[:max_products]
        total = len(products_to_search)
        completed = 0
        all_results: List[ProductSearchResult] = []

        # Search products sequentially for progress updates
        for product in products_to_search:
            # Yield progress before search
            yield DeepSeekProgress(
                type="progress",
                current_product=product.value,
                completed=completed,
                total=total,
                percentage=round((completed / total) * 100, 1),
            )

            try:
                result = await self._search_product(
                    product=product,
                    query=query,
                    history=history,
                    file_content=file_content,
                    language=language,
                )
                all_results.append(result)

                # Yield product result
                yield DeepSeekProgress(
                    type="product_result",
                    current_product=product.value,
                    completed=completed + 1,
                    total=total,
                    percentage=round(((completed + 1) / total) * 100, 1),
                    product_result=result,
                )

            except Exception as e:
                logger.error(f"DeepSeek stream error for {product}: {e}")
                error_result = ProductSearchResult(
                    product=product,
                    response="",
                    sources=ProductSources(),
                    confidence=0.0,
                    error=str(e),
                )
                all_results.append(error_result)

                yield DeepSeekProgress(
                    type="product_result",
                    current_product=product.value,
                    completed=completed + 1,
                    total=total,
                    percentage=round(((completed + 1) / total) * 100, 1),
                    product_result=error_result,
                )

            completed += 1

        # Generate final summary
        summary = await self._generate_summary(
            query=query,
            product_results=all_results,
            language=language,
        )

        processing_time = int((time.time() - start_time) * 1000)

        # Yield final result
        yield DeepSeekProgress(
            type="final",
            completed=total,
            total=total,
            percentage=100.0,
            product_result=ProductSearchResult(
                product=ProductId.OTHER,  # Use OTHER for summary
                response=summary,
                confidence=1.0,
                search_time_ms=processing_time,
            ),
        )

    async def _search_product(
        self,
        product: ProductId,
        query: str,
        history: Optional[List[Dict]] = None,
        file_content: Optional[str] = None,
        language: str = "ja",
    ) -> ProductSearchResult:
        """
        Search a single product

        Args:
            product: Target product
            query: User query
            history: Conversation history
            file_content: Optional file content
            language: UI language

        Returns:
            ProductSearchResult
        """
        start_time = time.time()
        sources = ProductSources()
        response = ""
        confidence = 0.0

        try:
            # Build product-specific context
            product_context = f"Product: {product.value}\n"
            if file_content:
                product_context += f"File Context:\n{file_content[:2000]}\n"

            # Vector search (if available)
            vector_results = []
            if self.vector_search_service:
                try:
                    vector_results = await self._vector_search(
                        query=query,
                        product=product,
                        top_k=3,
                    )
                    sources.vector_search = vector_results
                except Exception as e:
                    logger.warning(f"Vector search failed for {product}: {e}")

            # Graph search (if available)
            graph_results = []
            if self.graph_search_service:
                try:
                    graph_results = await self._graph_search(
                        query=query,
                        product=product,
                        top_k=3,
                    )
                    sources.graph_search = graph_results
                except Exception as e:
                    logger.warning(f"Graph search failed for {product}: {e}")

            # Build context from search results
            context_parts = []
            for vs in vector_results[:2]:
                context_parts.append(f"[Vector] {vs.content[:300]}")
            for gs in graph_results[:2]:
                context_parts.append(f"[Graph] {gs.entity_name}: {gs.entity_type}")

            combined_context = "\n".join(context_parts) if context_parts else None

            # Generate response with Learning LLM (if available)
            if self.learning_llm_service:
                try:
                    llm_result = await self.learning_llm_service.generate(
                        question=query,
                        context=combined_context,
                        max_tokens=512,
                        temperature=0.7,
                    )
                    if llm_result:
                        response = llm_result.get("answer", "")
                        sources.learning_llm = LearningLLMSource(
                            model=llm_result.get("model", "Qwen/Qwen2.5-7B-Instruct"),
                            adapter=llm_result.get("adapter"),
                            confidence=0.7,
                        )
                except Exception as e:
                    logger.warning(f"Learning LLM failed for {product}: {e}")

            # Calculate confidence
            confidence = self._calculate_confidence(sources)

            search_time = int((time.time() - start_time) * 1000)

            return ProductSearchResult(
                product=product,
                response=response,
                sources=sources,
                confidence=confidence,
                search_time_ms=search_time,
            )

        except Exception as e:
            logger.error(f"Product search error for {product}: {e}")
            return ProductSearchResult(
                product=product,
                response="",
                sources=ProductSources(),
                confidence=0.0,
                error=str(e),
            )

    async def _vector_search(
        self,
        query: str,
        product: ProductId,
        top_k: int = 3,
    ) -> List[VectorSource]:
        """Execute vector search"""
        # TODO: Implement actual vector search with product filter
        # For now, return empty list - will be integrated with existing vector search
        return []

    async def _graph_search(
        self,
        query: str,
        product: ProductId,
        top_k: int = 3,
    ) -> List[GraphSource]:
        """Execute graph search"""
        # TODO: Implement actual graph search with product filter
        # For now, return empty list - will be integrated with existing graph search
        return []

    def _calculate_confidence(self, sources: ProductSources) -> float:
        """Calculate overall confidence from sources"""
        confidence = 0.0

        # Learning LLM contribution
        if sources.learning_llm:
            confidence += 0.4 * sources.learning_llm.confidence

        # Vector search contribution
        if sources.vector_search:
            avg_score = sum(v.score for v in sources.vector_search) / len(sources.vector_search)
            confidence += 0.3 * min(avg_score, 1.0)

        # Graph search contribution
        if sources.graph_search:
            avg_score = sum(g.score for g in sources.graph_search) / len(sources.graph_search)
            confidence += 0.3 * min(avg_score, 1.0)

        return min(confidence, 1.0)

    async def _generate_summary(
        self,
        query: str,
        product_results: List[ProductSearchResult],
        language: str = "ja",
    ) -> str:
        """
        Generate summary from all product results

        Args:
            query: Original query
            product_results: Results from all products
            language: UI language

        Returns:
            Synthesized summary
        """
        # Filter results with actual responses
        valid_results = [r for r in product_results if r.response and r.confidence > 0.3]

        if not valid_results:
            if language == "ja":
                return "申し訳ございません。関連する情報が見つかりませんでした。"
            elif language == "ko":
                return "죄송합니다. 관련 정보를 찾을 수 없습니다."
            else:
                return "Sorry, no relevant information was found."

        # Sort by confidence
        valid_results.sort(key=lambda x: x.confidence, reverse=True)

        # Build summary from top results
        summary_parts = []

        if language == "ja":
            summary_parts.append(f"「{query}」についての検索結果:\n")
        elif language == "ko":
            summary_parts.append(f"'{query}'에 대한 검색 결과:\n")
        else:
            summary_parts.append(f"Search results for '{query}':\n")

        for i, result in enumerate(valid_results[:3], 1):
            product_name = result.product.value.replace("_", " ").title()
            summary_parts.append(f"\n**{i}. {product_name}** (confidence: {result.confidence:.0%})")
            summary_parts.append(f"\n{result.response[:500]}")
            if len(result.response) > 500:
                summary_parts.append("...")

        return "\n".join(summary_parts)


# =============================================================================
# Singleton Instance
# =============================================================================

_deep_seek_service: Optional[DeepSeekService] = None


def get_deep_seek_service(
    learning_llm_service=None,
    vector_search_service=None,
    graph_search_service=None,
) -> DeepSeekService:
    """Get DeepSeek service singleton"""
    global _deep_seek_service
    if _deep_seek_service is None:
        _deep_seek_service = DeepSeekService(
            learning_llm_service=learning_llm_service,
            vector_search_service=vector_search_service,
            graph_search_service=graph_search_service,
        )
    return _deep_seek_service


async def initialize_deep_seek_service(
    learning_llm_service=None,
    vector_search_service=None,
    graph_search_service=None,
) -> DeepSeekService:
    """Initialize DeepSeek service"""
    global _deep_seek_service
    _deep_seek_service = DeepSeekService(
        learning_llm_service=learning_llm_service,
        vector_search_service=vector_search_service,
        graph_search_service=graph_search_service,
    )
    logger.info("DeepSeek service initialized")
    return _deep_seek_service
