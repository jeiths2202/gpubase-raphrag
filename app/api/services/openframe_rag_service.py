"""
OpenFrame RAG Service

TRT-LLM NIM 기반 Multi-Product RAG 메인 서비스.
제품 라우팅, TRT-LLM NIM, Vector/Graph 검색을 통합합니다.

TRT-LLM NIM (Port 12820):
- OpenFrame 8제품 전용 최적화 LLM
- 제품별 시스템 프롬프트로 정확한 응답 생성
"""
import logging
import os
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
from .multimodal_embedding import TextEmbeddingService
from ..adapters.openframe_llm import TRTLLMAdapter, get_trtllm_adapter, initialize_trtllm_adapter

logger = logging.getLogger(__name__)


class OpenFrameRAGService:
    """
    OpenFrame RAG Service

    Multi-Product RAG의 핵심 서비스로 다음을 통합합니다:
    1. Product Router: 쿼리 → 제품 분류
    2. TRT-LLM NIM: OpenFrame 8제품 전용 LLM (Port 12820)
    3. Learning LLM: QLoRA 기반 응답 생성 (폴백용)
    4. Vector Search: 유사도 기반 검색
    5. Graph Search: 엔티티 기반 검색
    """

    def __init__(
        self,
        product_router: Optional[ProductRouterService] = None,
        trtllm_adapter: Optional[TRTLLMAdapter] = None,
        learning_llm_service: Optional[LearningLLMService] = None,
        deep_seek_service: Optional[DeepSeekService] = None,
        vector_search_service=None,
        graph_search_service=None,
    ):
        """
        Initialize OpenFrame RAG service

        Args:
            product_router: Product classification service
            trtllm_adapter: TRT-LLM NIM adapter (primary LLM for OpenFrame)
            learning_llm_service: QLoRA Learning LLM service (fallback)
            deep_seek_service: DeepSeek comprehensive search service
            vector_search_service: Vector search service
            graph_search_service: Graph search service
        """
        self.product_router = product_router or get_product_router_service()
        self.trtllm_adapter = trtllm_adapter
        self.learning_llm_service = learning_llm_service
        self.deep_seek_service = deep_seek_service
        self.vector_search_service = vector_search_service
        self.graph_search_service = graph_search_service

        # TRT-LLM NIM 설정
        self.use_trtllm = os.getenv("ENABLE_TRTLLM_NIM", "true").lower() == "true"

        self._is_initialized = False

    async def initialize(self) -> bool:
        """
        Initialize service and dependencies

        Returns:
            True if initialization succeeded
        """
        try:
            # Initialize TRT-LLM NIM adapter (primary for OpenFrame)
            if self.use_trtllm and self.trtllm_adapter is None:
                trtllm_url = os.getenv("TRTLLM_NIM_URL", "http://192.168.8.11:12820/v1")
                trtllm_model = os.getenv("TRTLLM_NIM_MODEL", "ensemble")
                self.trtllm_adapter = await initialize_trtllm_adapter(
                    base_url=trtllm_url,
                    model=trtllm_model,
                )
                logger.info(f"TRT-LLM NIM adapter initialized: {trtllm_url}")

            # Get Learning LLM service as fallback if not provided
            if self.learning_llm_service is None:
                self.learning_llm_service = get_learning_llm_service()

            # Initialize Learning LLM (fallback)
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
            logger.info(f"OpenFrame RAG service initialized (TRT-LLM NIM: {self.use_trtllm})")
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

            # Step 3: Generate response with TRT-LLM NIM (primary) or Learning LLM (fallback)
            response_text = ""

            # Try TRT-LLM NIM first (primary for OpenFrame)
            if self.use_trtllm and self.trtllm_adapter and self.trtllm_adapter.is_loaded:
                try:
                    trtllm_result = await self.trtllm_adapter.generate_with_metadata(
                        question=request.message,
                        context=combined_context,
                        product=product.value if product != ProductId.AUTO else None,
                        language=request.language or "ja",
                        max_tokens=int(os.getenv("TRTLLM_NIM_MAX_TOKENS", "1024")),
                        temperature=float(os.getenv("TRTLLM_NIM_TEMPERATURE", "0.7")),
                    )

                    if trtllm_result and trtllm_result.answer:
                        response_text = trtllm_result.answer
                        sources.learning_llm = LearningLLMSource(
                            model=f"TRT-LLM NIM ({trtllm_result.model})",
                            adapter=f"trtllm-{product.value}",
                            product=product.value,
                            confidence=trtllm_result.confidence,
                            generation_time_ms=int((time.time() - start_time) * 1000),
                        )
                        logger.info(f"TRT-LLM NIM response generated for product: {product.value}")
                except Exception as e:
                    logger.error(f"TRT-LLM NIM generation failed: {e}")

            # Fallback to Learning LLM
            if not response_text and request.use_learning_llm and self.learning_llm_service:
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
                            product=product.value,
                            confidence=0.8,
                            generation_time_ms=int((time.time() - start_time) * 1000),
                        )
                        logger.info("Fallback to Learning LLM for response generation")
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
        IR Pipeline Streaming RAG:
        Query → BGE-M3 (Sparse+Dense) → RRF merge → Top-K → Qwen3-32B LLM 생성

        Yields:
            SSE-formatted events
        """
        start_time = time.time()

        try:
            # Ensure initialized
            if not self._is_initialized:
                await self.initialize()

            product = request.product

            # Auto-classification (product=auto 일 때 자동 분류)
            if product == ProductId.AUTO:
                classification = self.product_router.classify(request.message)
                product = classification.product
                # 분류된 제품이 있으면 진행 (needs_selection이어도 최선의 제품으로 진행)
                if product == ProductId.AUTO:
                    # 분류 실패 → 기본 제품으로 fallback
                    product = ProductId.OPENFRAME_MVS

            # Step 1: BGE-M3 IR Search (Neo4j Vector Index)
            yield {"type": "status", "data": {"step": "ir_search", "product": product.value}}

            from .bge_m3_ir_service import get_bge_m3_ir_service

            ir_service = get_bge_m3_ir_service()

            context_parts = []
            sources = ProductSources()
            product_id = product.value

            # Neo4j Vector Search (항상 즉시 실행 - 인메모리 인덱스 구축 불필요)
            try:
                neo4j_results = await ir_service.neo4j_vector_search(
                    query=request.message,
                    product_id=product_id,
                    top_k=20,
                )

                if neo4j_results:
                    yield {
                        "type": "sources",
                        "data": {
                            "source_type": "ir_search",
                            "count": len(neo4j_results),
                            "top_score": neo4j_results[0]["score"] if neo4j_results else 0,
                        }
                    }

                    for item in neo4j_results[:10]:
                        context_parts.append(
                            f"[Source: {item['doc_name']} / {item['title']}]\n"
                            f"{item['content'][:600]}"
                        )
            except Exception as e:
                logger.warning(f"Neo4j vector search failed: {e}")

            # Fallback: 기존 vector+graph search (IR 인덱스 미구축 또는 결과 부족 시)
            if len(context_parts) < 3:
                fallback_parts = await self._fallback_search(request, product)
                context_parts.extend(fallback_parts)
                if fallback_parts:
                    yield {
                        "type": "sources",
                        "data": {"source_type": "fallback_search", "count": len(fallback_parts)}
                    }

            if request.file_content:
                context_parts.insert(0, f"[User File]\n{request.file_content[:2000]}")

            combined_context = "\n\n".join(context_parts) if context_parts else None

            # Step 2: LLM Generation (Qwen3-32B via vLLM)
            yield {"type": "status", "data": {"step": "generating"}}

            llm_used = None

            if request.use_learning_llm and self.learning_llm_service:
                try:
                    # Qwen3 <think>...</think> 처리
                    # enable_thinking=True: think 블록을 "think_token" 이벤트로 분리 전송
                    # enable_thinking=False: <think> 생성 안됨 (safety filter는 이중 안전장치)
                    enable_thinking = getattr(request, 'enable_thinking', False)
                    in_think_block = False

                    async for token in self.learning_llm_service.generate_stream(
                        question=request.message,
                        context=combined_context,
                        max_tokens=2048 if enable_thinking else 1024,
                        temperature=0.7,
                        enable_thinking=enable_thinking,
                    ):
                        # <think> 블록 시작 감지
                        if "<think>" in token:
                            in_think_block = True
                            before = token.split("<think>")[0]
                            if before.strip():
                                yield {"type": "token", "data": {"content": before}}
                            continue
                        # </think> 블록 종료 감지
                        if "</think>" in token:
                            in_think_block = False
                            after = token.split("</think>")[-1]
                            if after.strip():
                                yield {"type": "token", "data": {"content": after}}
                            continue
                        # think 블록 내부
                        if in_think_block:
                            if enable_thinking:
                                # Think ON: 프론트엔드 Think 패널에 표시
                                yield {"type": "think_token", "data": {"content": token}}
                            # Think OFF: 스킵 (safety filter)
                            continue
                        yield {"type": "token", "data": {"content": token}}

                    model_name = os.getenv("LEARNING_LLM_MODEL", "/opt/models/qwen3-32b")
                    sources.learning_llm = LearningLLMSource(
                        model=model_name,
                        adapter=None,
                        product=product.value,
                        confidence=0.8,
                    )
                    llm_used = "qwen3-32b"
                    logger.info(f"Qwen3-32B response for product: {product.value}")

                except Exception as e:
                    logger.error(f"LLM streaming failed: {e}")

            # Final fallback to context-based response
            if llm_used is None:
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

    def _resolve_section_content(
        self, section_key: str, knowledge_store
    ) -> Optional[Dict]:
        """
        IR search의 section_key를 실제 섹션 콘텐츠로 변환.
        key format: "{product_id}::{domain}::{source}::{title}"
        """
        if knowledge_store is None:
            return None
        try:
            # knowledge_store 캐시에서 직접 조회
            sections = getattr(knowledge_store, '_sections_cache', {})
            if section_key in sections:
                return sections[section_key]

            # key 파싱하여 섹션 탐색
            parts = section_key.split("::", 3)
            if len(parts) >= 4:
                return {
                    "product_id": parts[0],
                    "domain": parts[1],
                    "source": parts[2],
                    "title": parts[3],
                    "content": f"[{parts[2]}] {parts[3]}",
                }
        except Exception as e:
            logger.debug(f"Failed to resolve section key '{section_key}': {e}")
        return None

    async def _fallback_search(
        self, request: OpenFrameRAGRequest, product: ProductId
    ) -> List[str]:
        """기존 vector+graph search fallback (IR 결과 부족 시)"""
        context_parts = []
        try:
            if request.use_vector_search:
                vector_results = await self._vector_search(
                    query=request.message, product=product, top_k=5,
                )
                for vr in (vector_results or [])[:3]:
                    context_parts.append(
                        f"[Document: {vr.doc_name}]\n{vr.content[:500]}"
                    )
            if request.use_graph_search:
                graph_results = await self._graph_search(
                    query=request.message, product=product, top_k=5,
                )
                for gr in (graph_results or [])[:3]:
                    context_parts.append(
                        f"[Entity: {gr.entity_name} ({gr.entity_type})]"
                    )
        except Exception as e:
            logger.warning(f"Fallback search failed: {e}")
        return context_parts

    def _get_neo4j_driver(self):
        """
        Neo4j driver 획득 (comprehensive_search.py와 동일한 방식)
        """
        from neo4j import GraphDatabase

        uri = os.getenv("NEO4J_URI", "bolt://localhost:7687")
        user = os.getenv("NEO4J_USER", "neo4j")
        password = os.getenv("NEO4J_PASSWORD", "")

        return GraphDatabase.driver(uri, auth=(user, password))

    def _extract_keywords(self, query: str) -> List[str]:
        """
        쿼리에서 검색용 키워드 추출

        OpenFrame 관련 명령어, 에러코드, 기술용어를 우선 추출합니다.
        """
        import re

        keywords = []
        query_lower = query.lower()

        # 1. OpenFrame 관련 명령어 패턴
        command_patterns = [
            r'\b(tjesmgr|tacfmgr|hidbmgr|oscmgr|osimgr|ndbmgr|volmgr|catmgr)\b',
            r'\b(tmboot|tmdown|ofboot|ofdown|jesinit|jesdown)\b',
            r'\b(idcams|iebgener|iebcopy|dfsort|dsmigin|dsmigout)\b',
        ]

        for pattern in command_patterns:
            matches = re.findall(pattern, query, re.IGNORECASE)
            keywords.extend([m.lower() for m in matches])

        # 2. 명령어 옵션 (BOOT, SHUTDOWN, START, STOP 등)
        option_patterns = [
            r'\b(BOOT|SHUTDOWN|START|STOP|CANCEL|SUBMIT|HOLD|RELEASE)\b',
            r'\b(DISPLAY|STATUS|INIT|DOWN|UP)\b',
        ]

        for pattern in option_patterns:
            matches = re.findall(pattern, query, re.IGNORECASE)
            keywords.extend([m.upper() for m in matches])

        # 3. 에러코드 패턴
        error_codes = re.findall(r'-\d{4,5}', query)
        keywords.extend(error_codes)

        # 4. 기술용어 (대문자 2글자 이상)
        tech_terms = re.findall(r'\b[A-Z]{2,}[a-z]*\b', query)
        keywords.extend([t for t in tech_terms if len(t) >= 3])

        # 5. 일반 단어 (4글자 이상, 영어/한자)
        if not keywords:
            words = re.findall(r'\b[a-zA-Z]{4,}\b', query)
            keywords.extend(words[:3])  # 최대 3개

        # 중복 제거 및 반환
        return list(dict.fromkeys(keywords))[:5]  # 최대 5개 키워드

    async def _vector_search(
        self,
        query: str,
        product: ProductId,
        top_k: int = 5,
    ) -> List[VectorSource]:
        """
        Execute vector search using Neo4j CONTAINS query.

        Similar to comprehensive_search.py pattern for consistency.
        Searches chunks that contain extracted keywords from the query.
        """
        try:
            # 키워드 추출
            keywords = self._extract_keywords(query)
            if not keywords:
                keywords = [query]  # 폴백: 전체 쿼리 사용

            logger.info(f"Vector search keywords: {keywords}")

            driver = self._get_neo4j_driver()
            try:
                with driver.session() as session:
                    # 키워드 기반 검색 (ANY keyword match)
                    result = session.run(
                        """
                        MATCH (d:Document)-[:HAS_CHUNK|CONTAINS]->(c:Chunk)
                        WHERE ANY(keyword IN $keywords WHERE
                            c.content CONTAINS keyword OR
                            toLower(c.content) CONTAINS toLower(keyword)
                        )
                        WITH c, d,
                             size([keyword IN $keywords WHERE c.content CONTAINS keyword]) as match_count
                        RETURN
                            c.content as content,
                            d.filename as doc_name,
                            d.id as doc_id,
                            c.page_number as page_number,
                            c.chunk_type as chunk_type,
                            toFloat(match_count) / size($keywords) as score
                        ORDER BY match_count DESC
                        LIMIT $limit
                        """,
                        keywords=keywords,
                        limit=top_k
                    )

                    vector_sources = []
                    for idx, record in enumerate(result):
                        vector_sources.append(VectorSource(
                            chunk_id=f"chunk_{idx}",
                            doc_id=record["doc_id"] or f"doc_{idx}",
                            doc_name=record["doc_name"] or "Unknown",
                            content=record["content"][:1000] if record["content"] else "",
                            score=record["score"],
                            page_number=record["page_number"],
                            product=product.value if product else None,
                        ))

                    logger.info(f"Vector search returned {len(vector_sources)} results for keywords: {keywords}")
                    return vector_sources

            finally:
                driver.close()

        except Exception as e:
            logger.error(f"Vector search failed: {e}")
            return []

    async def _graph_search(
        self,
        query: str,
        product: ProductId,
        top_k: int = 5,
    ) -> List[GraphSource]:
        """
        Execute graph search using Neo4j Entity-Chunk relationships.

        Similar to comprehensive_search.py pattern for consistency.
        Searches entities that match extracted keywords from the query.
        """
        try:
            # 키워드 추출
            keywords = self._extract_keywords(query)
            if not keywords:
                keywords = [query]

            logger.info(f"Graph search keywords: {keywords}")

            driver = self._get_neo4j_driver()
            try:
                with driver.session() as session:
                    # 키워드 기반 엔티티 검색
                    result = session.run(
                        """
                        MATCH (e:Entity)-[r:MENTIONS]-(c:Chunk)
                        WHERE ANY(keyword IN $keywords WHERE
                            e.name CONTAINS keyword OR
                            toLower(e.name) CONTAINS toLower(keyword)
                        )
                        WITH e, c,
                             size([keyword IN $keywords WHERE e.name CONTAINS keyword]) as match_count
                        RETURN
                            e.name as entity_name,
                            e.type as entity_type,
                            c.content as content,
                            toFloat(match_count) / size($keywords) as score
                        ORDER BY match_count DESC
                        LIMIT $limit
                        """,
                        keywords=keywords,
                        limit=top_k
                    )

                    graph_sources = []
                    for idx, record in enumerate(result):
                        graph_sources.append(GraphSource(
                            entity_id=f"entity_{idx}",
                            entity_name=record["entity_name"] or "Unknown",
                            entity_type=record["entity_type"] or "ENTITY",
                            related_chunks=[record["content"][:500]] if record["content"] else [],
                            score=record["score"],
                            product=product.value if product else None,
                        ))

                    logger.info(f"Graph search returned {len(graph_sources)} results for keywords: {keywords}")
                    return graph_sources

            finally:
                driver.close()

        except Exception as e:
            logger.error(f"Graph search failed: {e}")
            return []

    async def _cross_product_similarity_search(
        self,
        query: str,
        current_product: ProductId,
        top_k: int = 3,
    ) -> List[VectorSource]:
        """
        Cross-product similarity search using Neo4j vector index.

        동일한 쿼리 문자열이 다른 유사 제품군에도 존재하는지 검색하고
        유사도가 가장 높은 top_k 결과를 반환합니다.

        이 검색은 기존 vector_search와 병렬로 실행되어
        다양한 제품군에서 가장 관련성 높은 결과를 찾습니다.

        Args:
            query: 검색 쿼리
            current_product: 현재 선택된 제품 (제외할 수도 있음)
            top_k: 반환할 최대 결과 수 (기본값: 3)

        Returns:
            유사도 순으로 정렬된 VectorSource 리스트
        """
        try:
            # 1. Generate query embedding
            embedding_service = TextEmbeddingService()
            query_embedding = await embedding_service.embed_text(query, input_type="query")

            if not query_embedding or len(query_embedding) == 0:
                logger.warning("Failed to generate query embedding for cross-product search")
                return []

            logger.info(f"[CrossProductSearch] Generated embedding for query: '{query[:50]}...'")

            # 2. Search across all products using Neo4j vector index
            driver = self._get_neo4j_driver()
            try:
                with driver.session() as session:
                    # Vector similarity search across all products
                    result = session.run(
                        """
                        CALL db.index.vector.queryNodes('chunk_embedding', $k, $embedding)
                        YIELD node, score
                        MATCH (d:Document)-[:HAS_CHUNK|CONTAINS]->(node)
                        RETURN
                            node.id as chunk_id,
                            node.content as content,
                            d.filename as doc_name,
                            d.id as doc_id,
                            node.page_number as page_number,
                            score
                        ORDER BY score DESC
                        LIMIT $limit
                        """,
                        embedding=query_embedding,
                        k=top_k * 2,  # Get more to filter
                        limit=top_k
                    )

                    cross_product_sources = []
                    for idx, record in enumerate(result):
                        doc_name = record["doc_name"] or "Unknown"
                        content = record["content"] or ""
                        score = record["score"] or 0.0

                        # Detect product from document name
                        detected_product = self._detect_product_from_doc_name(doc_name)

                        cross_product_sources.append(VectorSource(
                            chunk_id=record["chunk_id"] or f"cross_{idx}",
                            doc_id=record["doc_id"] or f"doc_{idx}",
                            doc_name=doc_name,
                            content=content[:1000] if content else "",
                            score=score,
                            page_number=record["page_number"],
                            product=detected_product,
                        ))

                    logger.info(
                        f"[CrossProductSearch] Found {len(cross_product_sources)} results "
                        f"across products (top score: {cross_product_sources[0].score:.4f})"
                        if cross_product_sources else
                        "[CrossProductSearch] No cross-product results found"
                    )

                    return cross_product_sources

            finally:
                driver.close()

        except Exception as e:
            logger.error(f"Cross-product similarity search failed: {e}")
            return []

    def _detect_product_from_doc_name(self, doc_name: str) -> str:
        """
        Detect product from document filename.

        Args:
            doc_name: Document filename

        Returns:
            Detected product ID or 'unknown'
        """
        doc_lower = doc_name.lower()

        # Product patterns in order of specificity
        product_patterns = [
            ("of_base", "openframe_base"),
            ("of_batch", "openframe_batch"),
            ("of_osc", "openframe_osc"),
            ("of_osi", "openframe_osi"),
            ("of_aim", "openframe_aim"),
            ("of_tacf", "openframe_tacf"),
            ("of_hidb", "openframe_hidb"),
            ("of_ndb", "openframe_ndb"),
            ("tjes", "openframe_batch"),
            ("tibero", "tibero7"),
            ("jeus", "jeus"),
            ("tmax", "tmax"),
            ("webtob", "webtob"),
            ("ofasm", "ofasm"),
            ("ofcobol", "ofcobol"),
            ("protrieve", "protrieve"),
            ("prosync", "prosync"),
            ("ofstudio", "ofstudio"),
            ("ofminer", "ofminer"),
            ("prosort", "prosort"),
            ("openframe", "openframe_mvs"),  # Generic fallback
        ]

        for pattern, product in product_patterns:
            if pattern in doc_lower:
                return product

        return "unknown"

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
        trtllm_status = {}
        vector_available = False
        graph_available = False
        adapters = []

        try:
            # Check TRT-LLM NIM (primary)
            if self.use_trtllm and self.trtllm_adapter:
                trtllm_health = await self.trtllm_adapter.health_check()
                trtllm_status = self.trtllm_adapter.get_status()
                if trtllm_health.get("status") == "healthy":
                    available = True
                    message = f"TRT-LLM NIM available ({self.trtllm_adapter.base_url})"

                    # Add TRT-LLM adapter status
                    adapters.append(AdapterStatus(
                        name="trtllm-nim",
                        product=ProductId.OPENFRAME_MVS,
                        loaded=True,
                    ))

            # Check Learning LLM (fallback)
            if self.learning_llm_service:
                learning_llm_status = self.learning_llm_service.get_status()
                if learning_llm_status.get("is_loaded"):
                    if not available:
                        available = True
                        message = "Learning LLM available (fallback)"

            # Check Vector search
            if self.vector_search_service:
                vector_available = True

            # Check Graph search
            if self.graph_search_service:
                graph_available = True

            # List Learning LLM adapters
            if learning_llm_status.get("available_adapters"):
                for adapter_name in learning_llm_status["available_adapters"][:5]:
                    adapters.append(AdapterStatus(
                        name=adapter_name,
                        product=ProductId.OPENFRAME_MVS,
                        loaded=adapter_name == learning_llm_status.get("current_adapter"),
                    ))

        except Exception as e:
            message = f"Health check failed: {e}"
            logger.error(message)

        # Merge TRT-LLM status into learning_llm_status for backward compatibility
        combined_status = {
            **learning_llm_status,
            "trtllm_nim": trtllm_status,
            "primary_llm": "trtllm-nim" if (self.use_trtllm and self.trtllm_adapter and self.trtllm_adapter.is_loaded) else "learning-llm",
        }

        return OpenFrameRAGHealth(
            available=available,
            message=message,
            learning_llm_status=combined_status,
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
    trtllm_adapter: Optional[TRTLLMAdapter] = None,
    learning_llm_service: Optional[LearningLLMService] = None,
    vector_search_service=None,
    graph_search_service=None,
) -> OpenFrameRAGService:
    """
    Initialize OpenFrame RAG service

    Args:
        trtllm_adapter: TRT-LLM NIM adapter instance (primary LLM)
        learning_llm_service: Learning LLM service instance (fallback)
        vector_search_service: Vector search service instance
        graph_search_service: Graph search service instance

    Returns:
        Initialized service
    """
    global _openframe_rag_service

    _openframe_rag_service = OpenFrameRAGService(
        trtllm_adapter=trtllm_adapter,
        learning_llm_service=learning_llm_service,
        vector_search_service=vector_search_service,
        graph_search_service=graph_search_service,
    )

    await _openframe_rag_service.initialize()

    use_trtllm = os.getenv("ENABLE_TRTLLM_NIM", "true").lower() == "true"
    logger.info(f"OpenFrame RAG service initialized (TRT-LLM NIM: {use_trtllm})")
    return _openframe_rag_service
