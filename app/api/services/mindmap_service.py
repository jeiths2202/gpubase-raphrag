"""
Mindmap Service - Concept extraction and mindmap generation
LLM을 활용한 개념 추출 및 마인드맵 생성 서비스

Phase 1 Improvements:
- H1: MindmapHealthChecker 통합 (Vector Index 확인)
- H2: LLMTimeoutWrapper 통합 (30초 타임아웃 + 재시도)
- H3: 청크 동적 조정 (Vector Search 우선)
"""
import asyncio
import hashlib
import re
import json
import logging
from typing import Dict, List, Any, Optional, Tuple
from functools import lru_cache
from datetime import datetime, timezone
import sys
import os

# Phase 1 imports
from .mindmap_health_checker import MindmapHealthChecker, HealthStatus, HealthCheckResult
from .llm_timeout_wrapper import LLMTimeoutWrapper, LLMTimeoutError, LLMError

logger = logging.getLogger(__name__)

# Add src directory to path for importing existing modules
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src'))

from langchain_openai import ChatOpenAI
from langchain_neo4j import Neo4jGraph

# Import config and embedding service from src
try:
    from config import config
    from embeddings import NeMoEmbeddingService
except ImportError:
    # Fallback config
    # SECURITY: No default values for sensitive credentials
    class FallbackConfig:
        class neo4j:
            uri = os.getenv("NEO4J_URI", "bolt://localhost:7687")
            user = os.getenv("NEO4J_USER", "neo4j")
            password = os.getenv("NEO4J_PASSWORD")  # REQUIRED: No default
        class llm:
            api_url = os.getenv("LLM_API_URL", "http://localhost:12800/v1")
            model = os.getenv("LLM_MODEL", "nvidia/nvidia-nemotron-nano-9b-v2")
        class embedding:
            api_url = os.getenv("EMBEDDING_API_URL", "http://localhost:12801/v1")
        class vector:
            index_name = "chunk_embedding"
    config = FallbackConfig()
    NeMoEmbeddingService = None  # Will be handled in service init

from ..adapters.learning_llm.vllm_adapter import MULTI_LORA_PRODUCT_MAPPING, MULTI_LORA_BASE_URL

from ..models.mindmap import (
    MindmapNode, MindmapEdge, MindmapData, MindmapInfo, MindmapFull,
    NodeType, RelationType,
    GenerateMindmapRequest, ExpandNodeRequest, QueryNodeRequest,
    GenerateMindmapResponse, ExpandNodeResponse, QueryNodeResponse, NodeDetailResponse
)


class MindmapService:
    """
    마인드맵 생성 및 관리 서비스

    - LLM을 사용하여 문서에서 개념과 관계 추출
    - Neo4j에 마인드맵 데이터 저장
    - 마인드맵 조회, 확장, 질의 기능 제공

    Phase 1 Features:
    - 헬스 체크: Vector Index 확인, 자동 생성
    - LLM 타임아웃: 30초 제한, 2회 재시도
    - 청크 동적 조정: Vector Search 우선
    """

    _instance: Optional['MindmapService'] = None

    # Phase 1 Configuration
    LLM_TIMEOUT = 30       # LLM 타임아웃 (초)
    LLM_MAX_RETRIES = 2    # 최대 재시도 횟수
    MIN_CHUNKS = 10        # 최소 청크 수
    MAX_CHUNKS = 100       # 최대 청크 수
    PREFERRED_CHUNKS = 50  # 권장 청크 수

    # 다국어 프롬프트 로컬라이제이션
    _LOCALE = {
        "ja": {
            "extract_intro": "以下の文書から核心概念(concepts)とそれらの間の関係(relations)を抽出してください。",
            "output_lang": "概念名(name)、説明(description)、関係ラベル(label)は必ず日本語で出力してください。原文が他言語の場合も日本語に翻訳して出力してください。",
            "focus_prefix": "集中トピック",
            "focus_suffix": "このトピックを中心に関連概念を抽出してください。",
            "doc_label": "文書内容",
            "entity_label": "既存エンティティ（参考）",
            "json_instruction": "以下のJSON形式で応答してください",
            "main_topic_hint": "最も重要な核心トピック",
            "name_hint": "概念名",
            "desc_hint": "簡単な説明",
            "rel_hint": "関係説明",
            "rules_label": "ルール",
            "rule1": "最大{n}個の概念を抽出してください",
            "rule2": "最も重要な概念のimportanceは1.0に近く、重要度が低い概念は低く設定してください",
            "rule3": "関係は明確な繋がりがある場合のみ抽出してください",
            "rule4": "main_topicは文書全体を代表する核心トピックです",
            "rule5": "全ての概念名・説明・ラベルを日本語で出力してください",
            "json_response": "JSON応答",
            "topic_intro": "トピック「{topic}」に関する核心概念(concepts)と関係(relations)を生成してください。",
            "topic_rule4": "各概念に簡潔で有用な説明を含めてください",
            "topic_rule5": "概念同士がよく繋がるように関係を生成してください",
            "related": "関連",
            "overview": "概要",
            "applications": "応用",
            "history": "歴史",
            "contains": "含む",
            "root_desc": "マインドマップのメイントピック",
            "main_topic_fallback": "メイントピック",
            "query_context": "文脈",
            "query_related": "関連概念",
            "query_question": "質問",
            "query_answer": "回答",
            "query_default_q": "について要約してください。",
            "query_prompt": "以下の文脈を基に質問に回答してください。",
            "query_fallback_title": "に関する情報",
            "query_no_info": "このノードに関する詳細情報が見つかりませんでした。",
        },
        "ko": {
            "extract_intro": "다음 문서들에서 핵심 개념(concepts)과 그들 사이의 관계(relations)를 추출하세요.",
            "output_lang": "개념명(name), 설명(description), 관계 라벨(label)을 한국어로 출력하세요.",
            "focus_prefix": "집중할 주제",
            "focus_suffix": "이 주제를 중심으로 관련 개념들을 추출하세요.",
            "doc_label": "문서 내용",
            "entity_label": "기존에 추출된 엔티티들 (참고용)",
            "json_instruction": "다음 JSON 형식으로 응답하세요",
            "main_topic_hint": "가장 중요한 핵심 주제",
            "name_hint": "개념명",
            "desc_hint": "간단한 설명",
            "rel_hint": "관계 설명",
            "rules_label": "규칙",
            "rule1": "최대 {n}개의 개념을 추출하세요",
            "rule2": "가장 중요한 개념의 importance는 1.0에 가깝게, 덜 중요한 개념은 낮게 설정하세요",
            "rule3": "관계는 명확한 연결이 있는 경우에만 추출하세요",
            "rule4": "main_topic은 문서 전체를 대표하는 핵심 주제입니다",
            "rule5": "모든 개념명, 설명, 라벨을 한국어로 출력하세요",
            "json_response": "JSON 응답",
            "topic_intro": "주제 \"{topic}\"에 대한 핵심 개념(concepts)과 관계(relations)를 생성하세요.",
            "topic_rule4": "각 개념에 대해 간단하지만 유용한 설명을 포함하세요",
            "topic_rule5": "개념들이 서로 잘 연결되도록 관계를 생성하세요",
            "related": "관련",
            "overview": "개요",
            "applications": "응용",
            "history": "역사",
            "contains": "포함",
            "root_desc": "마인드맵의 메인 토픽",
            "main_topic_fallback": "메인 토픽",
            "query_context": "문맥",
            "query_related": "관련 개념",
            "query_question": "질문",
            "query_answer": "답변",
            "query_default_q": "에 대해 요약해주세요.",
            "query_prompt": "다음 문맥을 바탕으로 질문에 답변하세요.",
            "query_fallback_title": "에 관한 정보",
            "query_no_info": "이 노드에 대한 상세 정보를 찾을 수 없습니다.",
        },
        "en": {
            "extract_intro": "Extract core concepts and relations from the following documents.",
            "output_lang": "Output concept names, descriptions, and relation labels in English.",
            "focus_prefix": "Focus topic",
            "focus_suffix": "Extract concepts centered around this topic.",
            "doc_label": "Document content",
            "entity_label": "Existing entities (reference)",
            "json_instruction": "Respond in the following JSON format",
            "main_topic_hint": "Most important core topic",
            "name_hint": "concept name",
            "desc_hint": "brief description",
            "rel_hint": "relation description",
            "rules_label": "Rules",
            "rule1": "Extract up to {n} concepts",
            "rule2": "Set importance close to 1.0 for the most important concepts, lower for less important",
            "rule3": "Only extract relations where there is a clear connection",
            "rule4": "main_topic represents the core topic of all documents",
            "rule5": "Output all names, descriptions, and labels in English",
            "json_response": "JSON response",
            "topic_intro": "Generate core concepts and relations about the topic \"{topic}\".",
            "topic_rule4": "Include a brief but useful description for each concept",
            "topic_rule5": "Generate relations so concepts connect well with each other",
            "related": "Related",
            "overview": "Overview",
            "applications": "Applications",
            "history": "History",
            "contains": "Contains",
            "root_desc": "Main topic of the mindmap",
            "main_topic_fallback": "Main Topic",
            "query_context": "Context",
            "query_related": "Related concepts",
            "query_question": "Question",
            "query_answer": "Answer",
            "query_default_q": " - please summarize.",
            "query_prompt": "Answer the question based on the following context.",
            "query_fallback_title": " - Information",
            "query_no_info": "No detailed information found for this node.",
        },
    }

    def __init__(self):
        """Initialize mindmap service"""
        self._graph: Optional[Neo4jGraph] = None
        self._llm: Optional[ChatOpenAI] = None
        self._embedding_service = None
        self._initialized: bool = False
        # Phase 1: Health checker and timeout wrapper
        self._health_checker: Optional[MindmapHealthChecker] = None
        self._llm_wrapper: Optional[LLMTimeoutWrapper] = None

    @classmethod
    def get_instance(cls) -> 'MindmapService':
        """Get singleton instance"""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def _ensure_initialized(self):
        """Ensure service is initialized"""
        if not self._initialized:
            # Initialize Neo4j connection
            self._graph = Neo4jGraph(
                url=config.neo4j.uri,
                username=config.neo4j.user,
                password=config.neo4j.password
            )

            # Initialize LLM
            llm_url = config.llm.api_url.replace("/chat/completions", "")
            self._llm = ChatOpenAI(
                base_url=llm_url,
                model=config.llm.model,
                api_key="not-needed",
                temperature=0.3
            )

            # Initialize embedding service for vector search
            if NeMoEmbeddingService is not None:
                try:
                    embedding_url = getattr(config, 'embedding', None)
                    if embedding_url and hasattr(embedding_url, 'api_url'):
                        self._embedding_service = NeMoEmbeddingService(base_url=embedding_url.api_url)
                    else:
                        self._embedding_service = NeMoEmbeddingService()
                except Exception as e:
                    logger.warning(f"Failed to initialize embedding service: {e}")
                    self._embedding_service = None

            # Phase 1: Initialize health checker
            self._health_checker = MindmapHealthChecker(self._graph)

            # Phase 1: Initialize LLM timeout wrapper with fallback
            self._llm_wrapper = LLMTimeoutWrapper(
                timeout=self.LLM_TIMEOUT,
                max_retries=self.LLM_MAX_RETRIES,
                fallback_fn=None  # 폴백은 각 호출에서 개별 설정
            )

            # Initialize schema
            self._init_mindmap_schema()
            self._initialized = True

    def _check_health(self) -> HealthCheckResult:
        """
        Phase 1 - H1: 서비스 상태 확인

        Returns:
            HealthCheckResult: 헬스 체크 결과
        """
        self._ensure_initialized()
        return self._health_checker.check_all()

    def get_health_status(self) -> dict:
        """
        외부에서 호출 가능한 헬스 상태 API

        Returns:
            dict: 상태 정보
        """
        result = self._check_health()
        stats = self._health_checker.get_stats()
        return {
            **result.to_dict(),
            "stats": stats
        }

    def _init_mindmap_schema(self):
        """Initialize Neo4j schema for mindmap"""
        constraints = [
            "CREATE CONSTRAINT mindmap_id IF NOT EXISTS FOR (m:Mindmap) REQUIRE m.id IS UNIQUE",
            "CREATE CONSTRAINT concept_id IF NOT EXISTS FOR (c:Concept) REQUIRE c.id IS UNIQUE",
        ]

        for constraint in constraints:
            try:
                self._graph.query(constraint)
            except Exception as e:
                print(f"Schema warning: {e}")

    def _get_llm(self, product_id: Optional[str] = None) -> ChatOpenAI:
        """제품별 Learning LLM 또는 기본 LLM 반환"""
        if not product_id:
            return self._llm

        product_lower = product_id.lower().strip()
        mapping = MULTI_LORA_PRODUCT_MAPPING.get(product_lower)
        if not mapping:
            print(f"[Mindmap] No adapter for product '{product_id}', using default LLM")
            return self._llm

        adapter_name = mapping.get("adapter", product_lower)
        print(f"[Mindmap] Using Learning LLM adapter '{adapter_name}' (product: {product_id})")
        return ChatOpenAI(
            base_url=MULTI_LORA_BASE_URL,
            model=adapter_name,
            api_key="not-needed",
            temperature=0.3
        )

    def _generate_id(self, prefix: str, content: str) -> str:
        """Generate unique ID"""
        hash_val = hashlib.md5(f"{content}{datetime.now(timezone.utc).isoformat()}".encode()).hexdigest()[:12]
        return f"{prefix}_{hash_val}"

    async def generate_mindmap(
        self,
        request: GenerateMindmapRequest
    ) -> MindmapFull:
        """
        문서들로부터 마인드맵 생성

        Args:
            request: 마인드맵 생성 요청

        Returns:
            생성된 마인드맵 전체 데이터
        """
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None,
            self._sync_generate_mindmap,
            request
        )
        return result

    def _sync_generate_mindmap(self, request: GenerateMindmapRequest) -> MindmapFull:
        """Synchronous mindmap generation"""
        self._ensure_initialized()

        # Phase 1 - H1: 헬스 체크 실행
        health = self._health_checker.check_all()

        if health.status == HealthStatus.UNHEALTHY:
            error_msg = "; ".join(health.messages) if health.messages else "서비스를 사용할 수 없습니다"
            raise ValueError(f"Mindmap service unavailable: {error_msg}")

        if not health.can_proceed:
            error_msg = health.messages[0] if health.messages else "필수 조건이 충족되지 않았습니다"
            raise ValueError(error_msg)

        # Phase 1 - H1: Vector Index 없으면 생성 시도
        if not health.checks.get("vector_index"):
            logger.info("Vector index not found, attempting to create...")
            self._health_checker.ensure_vector_index()

        chunks = []
        search_method = "graph"

        # Phase 1 - H3: 청크 동적 조정 - Vector Search 우선
        if request.document_ids:
            # 특정 문서 지정된 경우
            chunks = self._get_document_chunks(request.document_ids)
        else:
            # 문서 미지정: focus_topic이 있으면 Vector 검색 우선
            if request.focus_topic:
                chunks = self._get_relevant_chunks(
                    topic=request.focus_topic,
                    max_chunks=self.PREFERRED_CHUNKS
                )
                if chunks:
                    search_method = "vector"
                    logger.info(f"Dynamic chunk search found {len(chunks)} chunks for topic: {request.focus_topic}")

            # Vector 검색 결과 없으면 그래프 검색으로 폴백
            if not chunks:
                chunks = self._get_document_chunks([])

        if not chunks:
            # 어떤 방법으로도 청크를 찾지 못함
            raise ValueError(
                "No documents found in the knowledge base. "
                "Please upload documents first before generating a mindmap."
            )

        # 2. LLM을 사용하여 문서에서 개념과 관계 추출
        concepts_data = self._extract_concepts_and_relations(
            chunks,
            max_nodes=request.max_nodes,
            focus_topic=request.focus_topic,
            language=request.language,
            product_id=request.product_id
        )

        # 3. 마인드맵 데이터 구조 생성
        nodes, edges, root_id = self._build_mindmap_structure(
            concepts_data,
            request.depth,
            language=request.language
        )

        # 4. 마인드맵 정보 생성
        if request.title:
            id_seed = request.title
        elif request.focus_topic:
            id_seed = request.focus_topic
        else:
            id_seed = chunks[0].get("content", "mindmap")[:50]

        mindmap_id = self._generate_id("mm", id_seed)
        title = request.title or self._generate_title(concepts_data, request.language)

        # 5. Neo4j에 저장
        doc_ids = request.document_ids or list(set(c.get("doc_id", "unknown") for c in chunks if c.get("doc_id")))
        self._save_mindmap_to_neo4j(mindmap_id, title, nodes, edges, doc_ids, language=request.language, product_id=request.product_id)

        # 설명 생성
        doc_count = len(doc_ids) if doc_ids else len(set(c["doc_id"] for c in chunks))
        description = f"Generated from {doc_count} document(s) via {search_method} search"
        if request.focus_topic:
            description += f" (focus: {request.focus_topic})"

        return MindmapFull(
            id=mindmap_id,
            title=title,
            description=description,
            document_ids=request.document_ids,
            node_count=len(nodes),
            edge_count=len(edges),
            data=MindmapData(
                nodes=nodes,
                edges=edges,
                root_id=root_id,
                metadata={"focus_topic": request.focus_topic, "language": request.language}
            )
        )

    def _get_document_chunks(self, document_ids: List[str]) -> List[Dict]:
        """문서에서 청크 가져오기"""
        if not document_ids:
            # 모든 문서에서 청크 가져오기
            results = self._graph.query(
                """
                MATCH (d:Document)-[:CONTAINS]->(c:Chunk)
                OPTIONAL MATCH (c)-[:MENTIONS]->(e:Entity)
                RETURN
                    d.id AS doc_id,
                    c.id AS chunk_id,
                    c.content AS content,
                    c.index AS chunk_index,
                    collect(DISTINCT e.name) AS entities
                ORDER BY d.id, c.index
                LIMIT 100
                """
            )
        else:
            results = self._graph.query(
                """
                MATCH (d:Document)-[:CONTAINS]->(c:Chunk)
                WHERE d.id IN $doc_ids
                OPTIONAL MATCH (c)-[:MENTIONS]->(e:Entity)
                RETURN
                    d.id AS doc_id,
                    c.id AS chunk_id,
                    c.content AS content,
                    c.index AS chunk_index,
                    collect(DISTINCT e.name) AS entities
                ORDER BY d.id, c.index
                """,
                {"doc_ids": document_ids}
            )

        return [
            {
                "doc_id": r["doc_id"],
                "chunk_id": r["chunk_id"],
                "content": r["content"],
                "chunk_index": r["chunk_index"],
                "entities": r["entities"] or []
            }
            for r in results
        ]

    def _vector_search_chunks(self, query: str, k: int = 20, min_score: float = 0.3) -> List[Dict]:
        """
        Vector 유사도 검색으로 관련 청크 가져오기

        Args:
            query: 검색 쿼리 (focus_topic)
            k: 반환할 결과 수
            min_score: 최소 유사도 점수

        Returns:
            관련 청크 목록
        """
        if self._embedding_service is None:
            print("Warning: Embedding service not available, falling back to graph search")
            return []

        try:
            # Generate query embedding
            query_embedding = self._embedding_service.embed_text(query, input_type="query")

            # Get vector index name from config
            vector_index_name = getattr(getattr(config, 'vector', None), 'index_name', 'chunk_embedding')

            # Search using Neo4j vector index
            results = self._graph.query(
                f"""
                CALL db.index.vector.queryNodes('{vector_index_name}', $k, $embedding)
                YIELD node, score
                WHERE score >= $min_score
                OPTIONAL MATCH (d:Document)-[:CONTAINS]->(node)
                OPTIONAL MATCH (node)-[:MENTIONS]->(e:Entity)
                RETURN
                    node.id AS chunk_id,
                    node.content AS content,
                    node.index AS chunk_index,
                    score,
                    d.id AS doc_id,
                    collect(DISTINCT e.name)[..5] AS entities
                ORDER BY score DESC
                """,
                {"k": k, "embedding": query_embedding, "min_score": min_score}
            )

            return [
                {
                    "doc_id": r["doc_id"] or "unknown",
                    "chunk_id": r["chunk_id"],
                    "content": r["content"],
                    "chunk_index": r["chunk_index"] or 0,
                    "entities": r["entities"] or [],
                    "score": r["score"],
                    "source": "vector_search"
                }
                for r in results
                if r["content"]  # Only include chunks with content
            ]

        except Exception as e:
            logger.error(f"Vector search error: {e}")
            return []

    def _get_relevant_chunks(
        self,
        topic: str,
        max_chunks: int = 50
    ) -> List[Dict]:
        """
        Phase 1 - H3: 토픽 관련 청크를 동적으로 조회

        Strategy:
        1. 먼저 Vector Search로 관련 청크 검색 (우선순위 높음)
        2. 관련 청크가 부족하면 Document→Chunk 관계로 보충
        3. 최대 max_chunks 개로 제한

        Args:
            topic: 검색할 토픽
            max_chunks: 최대 청크 수

        Returns:
            관련 청크 목록
        """
        relevant_chunks = []

        # Step 1: Vector 유사도 검색 (우선순위 높음)
        try:
            vector_chunks = self._vector_search_chunks(
                query=topic,
                k=max_chunks,
                min_score=0.3
            )
            relevant_chunks.extend(vector_chunks)
            logger.info(f"Vector search returned {len(vector_chunks)} chunks for topic '{topic}'")
        except Exception as e:
            logger.warning(f"Vector search failed: {e}")

        # Step 2: 부족하면 Document→Chunk로 보충
        if len(relevant_chunks) < self.MIN_CHUNKS:
            additional_needed = max_chunks - len(relevant_chunks)
            existing_ids = {c.get('chunk_id') for c in relevant_chunks if c.get('chunk_id')}

            try:
                doc_chunks = self._get_document_chunks_excluding(
                    exclude_ids=existing_ids,
                    limit=additional_needed
                )
                relevant_chunks.extend(doc_chunks)
                logger.info(f"Added {len(doc_chunks)} chunks from documents (total: {len(relevant_chunks)})")
            except Exception as e:
                logger.warning(f"Document chunk retrieval failed: {e}")

        # Step 3: 최대 개수 제한
        return relevant_chunks[:max_chunks]

    def _get_document_chunks_excluding(
        self,
        exclude_ids: set,
        limit: int = 50
    ) -> List[Dict]:
        """
        특정 ID를 제외한 문서 청크 조회

        Args:
            exclude_ids: 제외할 청크 ID 집합
            limit: 최대 반환 수

        Returns:
            청크 목록
        """
        try:
            if exclude_ids:
                query = """
                MATCH (d:Document)-[:CONTAINS]->(c:Chunk)
                WHERE NOT c.id IN $exclude_ids
                OPTIONAL MATCH (c)-[:MENTIONS]->(e:Entity)
                RETURN
                    d.id AS doc_id,
                    c.id AS chunk_id,
                    c.content AS content,
                    c.index AS chunk_index,
                    collect(DISTINCT e.name)[..5] AS entities
                ORDER BY d.created_at DESC, c.index
                LIMIT $limit
                """
                results = self._graph.query(query, {
                    "exclude_ids": list(exclude_ids),
                    "limit": limit
                })
            else:
                query = """
                MATCH (d:Document)-[:CONTAINS]->(c:Chunk)
                OPTIONAL MATCH (c)-[:MENTIONS]->(e:Entity)
                RETURN
                    d.id AS doc_id,
                    c.id AS chunk_id,
                    c.content AS content,
                    c.index AS chunk_index,
                    collect(DISTINCT e.name)[..5] AS entities
                ORDER BY d.created_at DESC, c.index
                LIMIT $limit
                """
                results = self._graph.query(query, {"limit": limit})

            return [
                {
                    "doc_id": r["doc_id"] or "unknown",
                    "chunk_id": r["chunk_id"],
                    "content": r["content"],
                    "chunk_index": r["chunk_index"] or 0,
                    "entities": r["entities"] or [],
                    "source": "document_graph"
                }
                for r in results
                if r["content"]
            ]
        except Exception as e:
            logger.error(f"Document chunks excluding query failed: {e}")
            return []

    def _extract_concepts_and_relations(
        self,
        chunks: List[Dict],
        max_nodes: int = 50,
        focus_topic: Optional[str] = None,
        language: str = "auto",
        product_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """LLM을 사용하여 개념과 관계 추출"""

        # 청크 내용 결합
        combined_content = "\n\n".join([
            f"[Document: {c['doc_id']}, Chunk: {c['chunk_index']}]\n{c['content'][:1000]}"
            for c in chunks[:20]  # 최대 20개 청크만 사용
        ])

        # 기존 엔티티 수집
        existing_entities = set()
        for chunk in chunks:
            existing_entities.update(chunk.get("entities", []))

        # 언어별 프롬프트 (프롬프트 전체를 대상 언어로 구성)
        L = self._LOCALE.get(language, self._LOCALE["ko"])
        entities_str = ', '.join(list(existing_entities)[:30])

        focus_instruction = ""
        if focus_topic:
            focus_instruction = f"\n{L['focus_prefix']}: {focus_topic}\n{L['focus_suffix']}"

        prompt = f"""{L['extract_intro']}
{L['output_lang']}
{focus_instruction}

{L['doc_label']}:
{combined_content}

{L['entity_label']}:
{entities_str}

{L['json_instruction']}:
{{
    "main_topic": "{L['main_topic_hint']}",
    "concepts": [
        {{"name": "{L['name_hint']}", "type": "concept|entity|topic|keyword", "importance": 0.0-1.0, "description": "{L['desc_hint']}"}}
    ],
    "relations": [
        {{"source": "concept1", "target": "concept2", "relation": "relates_to|contains|causes|depends_on|similar_to|part_of", "label": "{L['rel_hint']}"}}
    ]
}}

{L['rules_label']}:
1. {L['rule1'].format(n=max_nodes)}
2. {L['rule2']}
3. {L['rule3']}
4. {L['rule4']}
5. {L['rule5']}

{L['json_response']}:"""

        # Phase 1 - H2: LLM 타임아웃 래퍼 적용
        llm = self._get_llm(product_id)

        def llm_call():
            """타임아웃이 적용될 LLM 호출"""
            response = llm.invoke(prompt)
            return response.content.strip()

        def fallback_fn(*args):
            """LLM 실패 시 폴백"""
            return self._fallback_concepts(chunks, existing_entities, language)

        try:
            # 타임아웃 래퍼로 LLM 호출 실행
            wrapper = LLMTimeoutWrapper(
                timeout=self.LLM_TIMEOUT,
                max_retries=self.LLM_MAX_RETRIES,
                fallback_fn=fallback_fn
            )
            response_text = wrapper.execute_sync(llm_call)

            # JSON 추출
            json_match = re.search(r'\{[\s\S]*\}', response_text)
            if json_match:
                concepts_data = json.loads(json_match.group())
                return concepts_data
            else:
                # JSON 파싱 실패 시 기본값 반환
                logger.warning("LLM response did not contain valid JSON, using fallback")
                return self._fallback_concepts(chunks, existing_entities, language)

        except json.JSONDecodeError as e:
            logger.warning(f"JSON parsing error: {e}")
            return self._fallback_concepts(chunks, existing_entities, language)
        except (LLMTimeoutError, LLMError) as e:
            logger.warning(f"LLM error (fallback already executed): {e}")
            # 폴백이 이미 실행되었으면 결과가 반환됨, 그렇지 않으면 여기서 실행
            return self._fallback_concepts(chunks, existing_entities, language)
        except Exception as e:
            logger.error(f"Concept extraction error: {e}")
            return self._fallback_concepts(chunks, existing_entities, language)

    def _fallback_concepts(self, chunks: List[Dict], entities: set, language: str = "ko") -> Dict[str, Any]:
        """개념 추출 실패 시 기존 엔티티 기반 폴백"""
        L = self._LOCALE.get(language, self._LOCALE["ko"])
        entity_list = list(entities)[:30]

        concepts = []
        for i, entity in enumerate(entity_list):
            concepts.append({
                "name": entity,
                "type": "entity",
                "importance": max(0.3, 1.0 - (i * 0.03)),
                "description": ""
            })

        # 간단한 관계 생성 (모든 엔티티를 첫 번째 엔티티에 연결)
        relations = []
        if len(entity_list) > 1:
            main_entity = entity_list[0]
            for entity in entity_list[1:10]:
                relations.append({
                    "source": main_entity,
                    "target": entity,
                    "relation": "relates_to",
                    "label": L["related"]
                })

        return {
            "main_topic": entity_list[0] if entity_list else "Document",
            "concepts": concepts,
            "relations": relations
        }

    def _generate_concepts_from_topic(
        self,
        topic: str,
        max_nodes: int = 30,
        language: str = "auto",
        product_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """주제만으로 LLM 지식을 사용해 개념과 관계 생성 (문서 없이)"""

        # 언어별 프롬프트 (프롬프트 전체를 대상 언어로 구성)
        L = self._LOCALE.get(language, self._LOCALE["ko"])

        prompt = f"""{L['topic_intro'].format(topic=topic)}
{L['output_lang']}

{L['json_instruction']}:
{{
    "main_topic": "{topic}",
    "concepts": [
        {{"name": "{L['name_hint']}", "type": "concept|entity|topic|keyword", "importance": 0.0-1.0, "description": "{L['desc_hint']}"}}
    ],
    "relations": [
        {{"source": "concept1", "target": "concept2", "relation": "relates_to|contains|causes|depends_on|similar_to|part_of", "label": "{L['rel_hint']}"}}
    ]
}}

{L['rules_label']}:
1. {L['rule1'].format(n=max_nodes)}
2. {L['rule2']}
3. {L['rule3']}
4. {L['topic_rule4']}
5. {L['topic_rule5']}
6. {L['rule5']}

{L['json_response']}:"""

        # Phase 1 - H2: LLM 타임아웃 래퍼 적용
        llm = self._get_llm(product_id)

        def llm_topic_call():
            response = llm.invoke(prompt)
            return response.content.strip()

        def topic_fallback(*args):
            return self._fallback_topic_concepts(topic, language)

        try:
            wrapper = LLMTimeoutWrapper(
                timeout=self.LLM_TIMEOUT,
                max_retries=self.LLM_MAX_RETRIES,
                fallback_fn=topic_fallback
            )
            response_text = wrapper.execute_sync(llm_topic_call)

            # JSON 추출
            json_match = re.search(r'\{[\s\S]*\}', response_text)
            if json_match:
                concepts_data = json.loads(json_match.group())
                # main_topic이 없으면 추가
                if "main_topic" not in concepts_data:
                    concepts_data["main_topic"] = topic
                return concepts_data
            else:
                # JSON 파싱 실패 시 기본 구조 반환
                logger.warning("Topic generation LLM response did not contain valid JSON")
                return self._fallback_topic_concepts(topic, language)

        except json.JSONDecodeError as e:
            logger.warning(f"JSON parsing error in topic generation: {e}")
            return self._fallback_topic_concepts(topic, language)
        except (LLMTimeoutError, LLMError) as e:
            logger.warning(f"Topic generation LLM error: {e}")
            return self._fallback_topic_concepts(topic, language)
        except Exception as e:
            logger.error(f"Topic concept generation error: {e}")
            return self._fallback_topic_concepts(topic, language)

    def _fallback_topic_concepts(self, topic: str, language: str = "ko") -> Dict[str, Any]:
        """주제 개념 생성 실패 시 기본 구조 반환"""
        L = self._LOCALE.get(language, self._LOCALE["ko"])
        return {
            "main_topic": topic,
            "concepts": [
                {"name": topic, "type": "topic", "importance": 1.0, "description": f"{L['root_desc']}: {topic}"},
                {"name": f"{topic} {L['overview']}", "type": "concept", "importance": 0.8, "description": L["overview"]},
                {"name": f"{topic} {L['applications']}", "type": "concept", "importance": 0.7, "description": L["applications"]},
                {"name": f"{topic} {L['history']}", "type": "concept", "importance": 0.6, "description": L["history"]},
            ],
            "relations": [
                {"source": topic, "target": f"{topic} {L['overview']}", "relation": "contains", "label": L["contains"]},
                {"source": topic, "target": f"{topic} {L['applications']}", "relation": "contains", "label": L["contains"]},
                {"source": topic, "target": f"{topic} {L['history']}", "relation": "contains", "label": L["contains"]},
            ]
        }

    def _fallback_expand_from_chunks(
        self,
        node_label: str,
        chunks: List[Dict],
        max_children: int,
        language: str = "ko"
    ) -> List[Dict[str, str]]:
        """LLM不可時にチャンク内容からエンティティを抽出してサブコンセプトを生成"""
        L = self._LOCALE.get(language, self._LOCALE["ko"])
        sub_concepts = []
        seen = {node_label.lower()}

        # チャンク内容からキーワードを抽出
        for chunk in chunks:
            content = chunk.get("content", "")
            # 英大文字の技術用語を抽出 (e.g., OPENFRAME_HOME, TJES, tmboot)
            keywords = re.findall(r'\b[A-Z][A-Za-z_]{2,}[A-Za-z0-9_]*\b', content)
            # 設定キーパターン (e.g., TLOGDIR, SHMKEY, RACPORT)
            keywords += re.findall(r'\b[A-Z]{2,}[A-Z_]*\b', content)

            for kw in keywords:
                kw_lower = kw.lower()
                if kw_lower not in seen and len(kw) >= 3:
                    seen.add(kw_lower)
                    sub_concepts.append({
                        "name": kw,
                        "relation": "relates_to",
                        "description": f"{L['related']}: {node_label}"
                    })
                    if len(sub_concepts) >= max_children:
                        break
            if len(sub_concepts) >= max_children:
                break

        # エンティティが見つからない場合、チャンク内既存のEntityノードを取得
        if not sub_concepts:
            for chunk in chunks:
                chunk_id = chunk.get("chunk_id", "")
                if chunk_id:
                    entity_result = self._graph.query(
                        """
                        MATCH (c:Chunk {id: $chunk_id})-[:MENTIONS]->(e:Entity)
                        RETURN e.name AS name
                        LIMIT $limit
                        """,
                        {"chunk_id": chunk_id, "limit": max_children}
                    )
                    for ent in entity_result:
                        name = ent.get("name", "")
                        if name and name.lower() not in seen:
                            seen.add(name.lower())
                            sub_concepts.append({
                                "name": name,
                                "relation": "relates_to",
                                "description": f"{L['related']}: {node_label}"
                            })
                            if len(sub_concepts) >= max_children:
                                break
                if len(sub_concepts) >= max_children:
                    break

        logger.debug(f"[expand] Fallback generated {len(sub_concepts)} sub-concepts")
        return sub_concepts

    def _build_mindmap_structure(
        self,
        concepts_data: Dict[str, Any],
        depth: int = 3,
        language: str = "ko"
    ) -> Tuple[List[MindmapNode], List[MindmapEdge], str]:
        """개념 데이터로부터 마인드맵 구조 생성"""
        L = self._LOCALE.get(language, self._LOCALE["ko"])
        nodes = []
        edges = []

        main_topic = concepts_data.get("main_topic", L["main_topic_fallback"])
        concepts = concepts_data.get("concepts", [])
        relations = concepts_data.get("relations", [])

        # 루트 노드 생성
        root_id = self._generate_id("node", main_topic)
        root_node = MindmapNode(
            id=root_id,
            label=main_topic,
            type=NodeType.ROOT,
            description=L["root_desc"],
            importance=1.0,
            color="#2563EB",  # Primary blue
            size=40
        )
        nodes.append(root_node)

        # 개념 노드 생성
        concept_id_map = {main_topic: root_id}

        for i, concept in enumerate(concepts):
            name = concept.get("name", f"Concept_{i}")
            if name == main_topic:
                continue

            node_id = self._generate_id("node", name)
            concept_id_map[name] = node_id

            # 노드 타입 결정
            type_str = concept.get("type", "concept").lower()
            if type_str == "entity":
                node_type = NodeType.ENTITY
                color = "#10B981"  # Green
            elif type_str == "topic":
                node_type = NodeType.TOPIC
                color = "#8B5CF6"  # Purple
            elif type_str == "keyword":
                node_type = NodeType.KEYWORD
                color = "#F59E0B"  # Amber
            else:
                node_type = NodeType.CONCEPT
                color = "#3B82F6"  # Blue

            importance = concept.get("importance", 0.5)
            size = 20 + (importance * 20)  # 20-40 크기 범위

            node = MindmapNode(
                id=node_id,
                label=name,
                type=node_type,
                description=concept.get("description", ""),
                importance=importance,
                color=color,
                size=size
            )
            nodes.append(node)

        # 관계 엣지 생성
        for i, relation in enumerate(relations):
            source_name = relation.get("source", "")
            target_name = relation.get("target", "")

            source_id = concept_id_map.get(source_name)
            target_id = concept_id_map.get(target_name)

            if source_id and target_id and source_id != target_id:
                # 관계 타입 결정
                rel_type_str = relation.get("relation", "relates_to").lower()
                try:
                    rel_type = RelationType(rel_type_str)
                except ValueError:
                    rel_type = RelationType.RELATES_TO

                edge_id = self._generate_id("edge", f"{source_id}_{target_id}")
                edge = MindmapEdge(
                    id=edge_id,
                    source=source_id,
                    target=target_id,
                    relation=rel_type,
                    label=relation.get("label", ""),
                    strength=0.7
                )
                edges.append(edge)

        # 루트에 연결되지 않은 노드들을 루트에 연결
        connected_nodes = set()
        for edge in edges:
            connected_nodes.add(edge.source)
            connected_nodes.add(edge.target)

        for node in nodes:
            if node.id != root_id and node.id not in connected_nodes:
                edge_id = self._generate_id("edge", f"{root_id}_{node.id}")
                edge = MindmapEdge(
                    id=edge_id,
                    source=root_id,
                    target=node.id,
                    relation=RelationType.CONTAINS,
                    label="포함",
                    strength=0.5
                )
                edges.append(edge)

        return nodes, edges, root_id

    def _generate_title(self, concepts_data: Dict[str, Any], language: str) -> str:
        """
        마인드맵 제목 생성

        Args:
            concepts_data: 추출된 개념 데이터
            language: 언어 설정 (ko, en, ja, auto)

        Returns:
            언어에 맞는 마인드맵 제목
        """
        main_topic = concepts_data.get("main_topic", "Mindmap")

        # Log the language parameter for debugging
        logger.info(f"_generate_title called with language='{language}', main_topic='{main_topic}'")

        if language == "ko":
            title = f"{main_topic} 마인드맵"
        elif language == "ja":
            title = f"{main_topic} マインドマップ"
        elif language == "en":
            title = f"{main_topic} Mindmap"
        else:
            # For 'auto' or unknown languages, default to English
            title = f"{main_topic} Mindmap"

        logger.info(f"Generated title: '{title}'")
        return title

    def _save_mindmap_to_neo4j(
        self,
        mindmap_id: str,
        title: str,
        nodes: List[MindmapNode],
        edges: List[MindmapEdge],
        document_ids: List[str],
        language: str = "ko",
        product_id: Optional[str] = None
    ):
        """마인드맵을 Neo4j에 저장"""
        # 마인드맵 노드 생성
        self._graph.query(
            """
            MERGE (m:Mindmap {id: $id})
            SET m.title = $title,
                m.document_ids = $doc_ids,
                m.node_count = $node_count,
                m.edge_count = $edge_count,
                m.created_at = datetime(),
                m.updated_at = datetime(),
                m.language = $language,
                m.product_id = $product_id
            """,
            {
                "id": mindmap_id,
                "title": title,
                "doc_ids": document_ids,
                "node_count": len(nodes),
                "edge_count": len(edges),
                "language": language,
                "product_id": product_id
            }
        )

        # 개념 노드들 생성 및 마인드맵에 연결
        for node in nodes:
            self._graph.query(
                """
                MERGE (c:Concept {id: $id})
                SET c.label = $label,
                    c.type = $type,
                    c.description = $description,
                    c.importance = $importance
                WITH c
                MATCH (m:Mindmap {id: $mindmap_id})
                MERGE (m)-[:HAS_CONCEPT]->(c)
                """,
                {
                    "id": node.id,
                    "label": node.label,
                    "type": node.type.value,
                    "description": node.description or "",
                    "importance": node.importance,
                    "mindmap_id": mindmap_id
                }
            )

        # 관계 엣지 생성
        for edge in edges:
            self._graph.query(
                """
                MATCH (s:Concept {id: $source})
                MATCH (t:Concept {id: $target})
                MERGE (s)-[r:CONCEPT_RELATION {id: $edge_id}]->(t)
                SET r.relation = $relation,
                    r.label = $label,
                    r.strength = $strength
                """,
                {
                    "source": edge.source,
                    "target": edge.target,
                    "edge_id": edge.id,
                    "relation": edge.relation.value,
                    "label": edge.label or "",
                    "strength": edge.strength
                }
            )

    async def get_mindmap(self, mindmap_id: str) -> Optional[MindmapFull]:
        """마인드맵 조회"""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._sync_get_mindmap, mindmap_id)

    def _sync_get_mindmap(self, mindmap_id: str) -> Optional[MindmapFull]:
        """Synchronous mindmap retrieval"""
        self._ensure_initialized()

        # 마인드맵 정보 조회
        mindmap_result = self._graph.query(
            """
            MATCH (m:Mindmap {id: $id})
            RETURN m.id AS id, m.title AS title, m.document_ids AS doc_ids,
                   m.node_count AS node_count, m.edge_count AS edge_count,
                   m.created_at AS created_at
            """,
            {"id": mindmap_id}
        )

        if not mindmap_result:
            return None

        mm = mindmap_result[0]

        # 개념 노드들 조회
        nodes_result = self._graph.query(
            """
            MATCH (m:Mindmap {id: $id})-[:HAS_CONCEPT]->(c:Concept)
            RETURN c.id AS id, c.label AS label, c.type AS type,
                   c.description AS description, c.importance AS importance
            """,
            {"id": mindmap_id}
        )

        nodes = []
        root_id = None
        for n in nodes_result:
            node_type = NodeType(n["type"]) if n["type"] else NodeType.CONCEPT
            if node_type == NodeType.ROOT:
                root_id = n["id"]

            # 색상 결정
            color_map = {
                NodeType.ROOT: "#2563EB",
                NodeType.CONCEPT: "#3B82F6",
                NodeType.ENTITY: "#10B981",
                NodeType.TOPIC: "#8B5CF6",
                NodeType.KEYWORD: "#F59E0B"
            }

            importance = n["importance"] or 0.5
            nodes.append(MindmapNode(
                id=n["id"],
                label=n["label"],
                type=node_type,
                description=n["description"],
                importance=importance,
                color=color_map.get(node_type, "#3B82F6"),
                size=20 + (importance * 20)
            ))

        # 엣지 조회
        edges_result = self._graph.query(
            """
            MATCH (m:Mindmap {id: $id})-[:HAS_CONCEPT]->(s:Concept)
            MATCH (s)-[r:CONCEPT_RELATION]->(t:Concept)
            MATCH (m)-[:HAS_CONCEPT]->(t)
            RETURN r.id AS id, s.id AS source, t.id AS target,
                   r.relation AS relation, r.label AS label, r.strength AS strength
            """,
            {"id": mindmap_id}
        )

        edges = []
        for e in edges_result:
            try:
                rel_type = RelationType(e["relation"]) if e["relation"] else RelationType.RELATES_TO
            except ValueError:
                rel_type = RelationType.RELATES_TO

            edges.append(MindmapEdge(
                id=e["id"],
                source=e["source"],
                target=e["target"],
                relation=rel_type,
                label=e["label"],
                strength=e["strength"] or 0.5
            ))

        return MindmapFull(
            id=mm["id"],
            title=mm["title"],
            document_ids=mm["doc_ids"] or [],
            node_count=len(nodes),
            edge_count=len(edges),
            data=MindmapData(
                nodes=nodes,
                edges=edges,
                root_id=root_id
            )
        )

    async def list_mindmaps(self, limit: int = 20, offset: int = 0) -> Tuple[List[MindmapInfo], int]:
        """마인드맵 목록 조회"""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._sync_list_mindmaps, limit, offset)

    def _sync_list_mindmaps(self, limit: int, offset: int) -> Tuple[List[MindmapInfo], int]:
        """Synchronous mindmap list retrieval"""
        self._ensure_initialized()

        # 전체 개수 조회
        count_result = self._graph.query("MATCH (m:Mindmap) RETURN count(m) AS total")
        total = count_result[0]["total"] if count_result else 0

        # 마인드맵 목록 조회
        results = self._graph.query(
            """
            MATCH (m:Mindmap)
            RETURN m.id AS id, m.title AS title, m.document_ids AS doc_ids,
                   m.node_count AS node_count, m.edge_count AS edge_count,
                   m.created_at AS created_at, m.updated_at AS updated_at
            ORDER BY m.created_at DESC
            SKIP $offset
            LIMIT $limit
            """,
            {"offset": offset, "limit": limit}
        )

        mindmaps = []
        for r in results:
            mindmaps.append(MindmapInfo(
                id=r["id"],
                title=r["title"],
                document_ids=r["doc_ids"] or [],
                node_count=r["node_count"] or 0,
                edge_count=r["edge_count"] or 0
            ))

        return mindmaps, total

    async def expand_node(self, mindmap_id: str, request: ExpandNodeRequest) -> ExpandNodeResponse:
        """노드 확장 (하위 개념 추가)"""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._sync_expand_node, mindmap_id, request)

    def _sync_expand_node(self, mindmap_id: str, request: ExpandNodeRequest) -> ExpandNodeResponse:
        """Synchronous node expansion"""
        self._ensure_initialized()

        logger.debug(f"[expand] Starting expand: mindmap={mindmap_id}, node={request.node_id}")

        # 노드 정보 조회
        node_result = self._graph.query(
            """
            MATCH (c:Concept {id: $node_id})
            RETURN c.label AS label, c.description AS description
            """,
            {"node_id": request.node_id}
        )

        logger.debug(f"[expand] Concept lookup result: {node_result}")

        if not node_result:
            logger.debug(f"[expand] Concept not found for node_id={request.node_id}")
            return ExpandNodeResponse(
                new_nodes=[],
                new_edges=[],
                expanded_from=request.node_id
            )

        node_label = node_result[0]["label"]
        logger.debug(f"[expand] Node label: '{node_label}'")

        # マインドマップの文書から関連チャンク検索
        # Step 1: CONTAINS 完全一致検索
        chunks = self._graph.query(
            """
            MATCH (m:Mindmap {id: $mindmap_id})
            UNWIND m.document_ids AS doc_id
            MATCH (d:Document {id: doc_id})-[:CONTAINS]->(c:Chunk)
            WHERE c.content CONTAINS $concept
            RETURN c.content AS content, c.id AS chunk_id
            LIMIT 5
            """,
            {"mindmap_id": mindmap_id, "concept": node_label}
        )

        logger.debug(f"[expand] Chunk search (exact) found {len(chunks)} chunks for '{node_label}'")

        # Step 2: 完全一致が見つからない場合、マインドマップに紐づく全チャンクを取得
        if not chunks:
            logger.debug("[expand] Trying fallback: all chunks from mindmap documents")
            chunks = self._graph.query(
                """
                MATCH (m:Mindmap {id: $mindmap_id})
                UNWIND m.document_ids AS doc_id
                MATCH (d:Document {id: doc_id})-[:CONTAINS]->(c:Chunk)
                RETURN c.content AS content, c.id AS chunk_id
                LIMIT 10
                """,
                {"mindmap_id": mindmap_id}
            )
            logger.debug(f"[expand] Fallback found {len(chunks)} chunks from mindmap docs")

        # Step 3: マインドマップにdoc_idsがない場合、直接グラフ全体から検索
        if not chunks:
            logger.debug(f"[expand] Trying graph-wide search for '{node_label}'")
            chunks = self._graph.query(
                """
                MATCH (d:Document)-[:CONTAINS]->(c:Chunk)
                WHERE c.content CONTAINS $concept
                RETURN c.content AS content, c.id AS chunk_id
                LIMIT 5
                """,
                {"concept": node_label}
            )
            logger.debug(f"[expand] Graph-wide search found {len(chunks)} chunks")

        if not chunks:
            logger.debug(f"[expand] No chunks found at all for node '{node_label}'")
            return ExpandNodeResponse(
                new_nodes=[],
                new_edges=[],
                expanded_from=request.node_id
            )

        # LLMで下位概念を抽出
        combined_content = "\n".join([c["content"][:500] for c in chunks])
        logger.debug(f"[expand] Combined content length: {len(combined_content)} chars")

        # マインドマップのメタデータから言語・product_idを取得
        meta_result = self._graph.query(
            """
            MATCH (m:Mindmap {id: $id})
            RETURN m.language AS language, m.product_id AS product_id
            """,
            {"id": mindmap_id}
        )
        language = "ja"  # default
        stored_product_id = request.product_id  # request에서 먼저 확인
        if meta_result:
            if meta_result[0].get("language"):
                language = meta_result[0]["language"]
            if not stored_product_id and meta_result[0].get("product_id"):
                stored_product_id = meta_result[0]["product_id"]
        L = self._LOCALE.get(language, self._LOCALE["ko"])

        # 言語別プロンプト
        _EXPAND_PROMPTS = {
            "ja": f'以下の内容から「{node_label}」の下位概念や関連する詳細情報を抽出してください。',
            "ko": f'다음 내용에서 "{node_label}"의 하위 개념이나 관련 세부 사항을 추출하세요.',
            "en": f'Extract sub-concepts or related details about "{node_label}" from the following content.',
        }
        _EXPAND_FORMAT = {
            "ja": "以下のJSON形式で応答してください",
            "ko": "다음 JSON 형식으로 응답하세요",
            "en": "Respond in the following JSON format",
        }
        _EXPAND_LIMIT = {
            "ja": f"最大{request.max_children}個の下位概念を抽出してください。",
            "ko": f"최대 {request.max_children}개의 하위 개념을 추출하세요.",
            "en": f"Extract up to {request.max_children} sub-concepts.",
        }

        intro = _EXPAND_PROMPTS.get(language, _EXPAND_PROMPTS["ko"])
        fmt = _EXPAND_FORMAT.get(language, _EXPAND_FORMAT["ko"])
        limit = _EXPAND_LIMIT.get(language, _EXPAND_LIMIT["ko"])

        prompt = f"""{intro}

{combined_content}

{fmt}:
{{
    "sub_concepts": [
        {{"name": "concept name", "relation": "part_of|example_of|relates_to", "description": "description"}}
    ]
}}

{limit}

JSON:"""

        # Phase 1 - H2: LLM 타임아웃 래퍼 적용
        llm = self._get_llm(stored_product_id)

        def llm_expand_call():
            response = llm.invoke(prompt)
            return response.content

        try:
            wrapper = LLMTimeoutWrapper(
                timeout=self.LLM_TIMEOUT,
                max_retries=self.LLM_MAX_RETRIES
            )
            response_content = wrapper.execute_sync(llm_expand_call)
            logger.debug(f"[expand] LLM response ({len(response_content)} chars): {response_content[:500]}")

            json_match = re.search(r'\{[\s\S]*\}', response_content)

            if json_match:
                sub_data = json.loads(json_match.group())
                sub_concepts = sub_data.get("sub_concepts", [])
                logger.debug(f"[expand] Parsed {len(sub_concepts)} sub_concepts")
            else:
                logger.debug("[expand] No JSON found in LLM response, using fallback")
                sub_concepts = []
        except (LLMTimeoutError, LLMError) as e:
            logger.warning(f"[expand] LLM error: {e}, using chunk-based fallback")
            sub_concepts = []
        except json.JSONDecodeError as e:
            logger.warning(f"[expand] JSON parse error: {e}, raw: {response_content[:200]}")
            sub_concepts = []
        except Exception as e:
            logger.warning(f"[expand] Unexpected error: {e}, using fallback")
            sub_concepts = []

        # LLM失敗時: チャンク内容からエンティティを抽出してフォールバック
        if not sub_concepts:
            logger.debug("[expand] Generating fallback sub-concepts from chunks")
            sub_concepts = self._fallback_expand_from_chunks(
                node_label, chunks, request.max_children, language
            )

        # 新しいノードとエッジ生成
        new_nodes = []
        new_edges = []

        for sub in sub_concepts[:request.max_children]:
            node_id = self._generate_id("node", sub["name"])

            new_node = MindmapNode(
                id=node_id,
                label=sub["name"],
                type=NodeType.CONCEPT,
                description=sub.get("description", ""),
                importance=0.4,
                color="#3B82F6",
                size=25
            )
            new_nodes.append(new_node)

            # Neo4j에 저장
            self._graph.query(
                """
                MERGE (c:Concept {id: $id})
                SET c.label = $label, c.type = $type,
                    c.description = $description, c.importance = $importance
                WITH c
                MATCH (m:Mindmap {id: $mindmap_id})
                MERGE (m)-[:HAS_CONCEPT]->(c)
                """,
                {
                    "id": node_id,
                    "label": sub["name"],
                    "type": "concept",
                    "description": sub.get("description", ""),
                    "importance": 0.4,
                    "mindmap_id": mindmap_id
                }
            )

            # 관계 결정
            rel_str = sub.get("relation", "relates_to")
            try:
                rel_type = RelationType(rel_str)
            except ValueError:
                rel_type = RelationType.RELATES_TO

            edge_id = self._generate_id("edge", f"{request.node_id}_{node_id}")
            new_edge = MindmapEdge(
                id=edge_id,
                source=request.node_id,
                target=node_id,
                relation=rel_type,
                label=sub.get("description", "")[:30],
                strength=0.6
            )
            new_edges.append(new_edge)

            # 엣지 Neo4j에 저장
            self._graph.query(
                """
                MATCH (s:Concept {id: $source})
                MATCH (t:Concept {id: $target})
                MERGE (s)-[r:CONCEPT_RELATION {id: $edge_id}]->(t)
                SET r.relation = $relation, r.label = $label, r.strength = $strength
                """,
                {
                    "source": request.node_id,
                    "target": node_id,
                    "edge_id": edge_id,
                    "relation": rel_type.value,
                    "label": sub.get("description", "")[:30],
                    "strength": 0.6
                }
            )

        # 마인드맵 노드/엣지 카운트 업데이트
        self._graph.query(
            """
            MATCH (m:Mindmap {id: $id})
            SET m.node_count = m.node_count + $new_nodes,
                m.edge_count = m.edge_count + $new_edges,
                m.updated_at = datetime()
            """,
            {"id": mindmap_id, "new_nodes": len(new_nodes), "new_edges": len(new_edges)}
        )

        return ExpandNodeResponse(
            new_nodes=new_nodes,
            new_edges=new_edges,
            expanded_from=request.node_id
        )

    async def query_node(self, mindmap_id: str, request: QueryNodeRequest) -> QueryNodeResponse:
        """노드 관련 RAG 질의"""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._sync_query_node, mindmap_id, request)

    def _sync_query_node(self, mindmap_id: str, request: QueryNodeRequest) -> QueryNodeResponse:
        """Synchronous node query"""
        self._ensure_initialized()

        # マインドマップの言語・product_id設定を取得
        meta_result = self._graph.query(
            "MATCH (m:Mindmap {id: $id}) RETURN m.language AS language, m.product_id AS product_id",
            {"id": mindmap_id}
        )
        language = "ja"
        stored_product_id = request.product_id  # request에서 먼저 확인
        if meta_result:
            if meta_result[0].get("language"):
                language = meta_result[0]["language"]
            if not stored_product_id and meta_result[0].get("product_id"):
                stored_product_id = meta_result[0]["product_id"]
        L = self._LOCALE.get(language, self._LOCALE["ko"])

        # 노드 정보 조회
        node_result = self._graph.query(
            """
            MATCH (c:Concept {id: $node_id})
            RETURN c.label AS label, c.description AS description
            """,
            {"node_id": request.node_id}
        )

        if not node_result:
            return QueryNodeResponse(
                node_id=request.node_id,
                node_label="Unknown",
                answer=L["query_no_info"],
                related_concepts=[],
                sources=[]
            )

        node_label = node_result[0]["label"]
        node_desc = node_result[0].get("description", "")

        # 관련 청크 검색
        chunks = self._graph.query(
            """
            MATCH (m:Mindmap {id: $mindmap_id})
            UNWIND m.document_ids AS doc_id
            MATCH (d:Document {id: doc_id})-[:CONTAINS]->(c:Chunk)
            WHERE c.content CONTAINS $concept
            RETURN c.content AS content, c.id AS chunk_id, d.id AS doc_id
            LIMIT 5
            """,
            {"mindmap_id": mindmap_id, "concept": node_label}
        )

        # 관련 개념 조회
        related = self._graph.query(
            """
            MATCH (c:Concept {id: $node_id})-[:CONCEPT_RELATION]-(other:Concept)
            RETURN DISTINCT other.label AS label
            LIMIT 10
            """,
            {"node_id": request.node_id}
        )
        related_concepts = [r["label"] for r in related]

        # 질문 생성 (언어별)
        question = request.question or f"{node_label}{L['query_default_q']}"

        # 컨텍스트 구성
        context = "\n\n".join([c["content"][:500] for c in chunks])

        # LLM으로 답변 생성 (언어별 프롬프트)
        prompt = f"""{L['query_prompt']}

{L['query_context']}:
{context}

{L['query_related']}: {', '.join(related_concepts)}

{L['query_question']}: {question}

{L['query_answer']}:"""

        # Phase 1 - H2: LLM 타임아웃 래퍼 적용
        llm = self._get_llm(stored_product_id)

        def llm_query_call():
            response = llm.invoke(prompt)
            return response.content.strip()

        try:
            wrapper = LLMTimeoutWrapper(
                timeout=self.LLM_TIMEOUT,
                max_retries=self.LLM_MAX_RETRIES
            )
            answer = wrapper.execute_sync(llm_query_call)
        except (LLMTimeoutError, LLMError, Exception) as e:
            logger.warning(f"Node query LLM error: {e}")
            answer = self._fallback_query_answer(node_label, node_desc, chunks, related_concepts, L)

        # 소스 정보
        sources = [
            {"chunk_id": c["chunk_id"], "doc_id": c["doc_id"], "content": c["content"][:200]}
            for c in chunks
        ]

        return QueryNodeResponse(
            node_id=request.node_id,
            node_label=node_label,
            answer=answer,
            related_concepts=related_concepts,
            sources=sources
        )

    def _fallback_query_answer(
        self, node_label: str, node_desc: str,
        chunks: List[Dict], related_concepts: List[str], L: Dict
    ) -> str:
        """LLM利用不可時のフォールバック回答生成"""
        parts = [f"**{node_label}**{L['query_fallback_title']}"]

        if node_desc:
            parts.append(f"\n{node_desc}")

        if related_concepts:
            parts.append(f"\n{L['query_related']}: {', '.join(related_concepts)}")

        # チャンクから要約を抽出
        if chunks:
            parts.append("")
            for chunk in chunks[:3]:
                content = chunk.get("content", "")[:300].strip()
                if content:
                    parts.append(f"- {content}")

        if not chunks and not node_desc:
            parts.append(f"\n{L['query_no_info']}")

        return "\n".join(parts)

    async def get_node_detail(self, mindmap_id: str, node_id: str) -> Optional[NodeDetailResponse]:
        """노드 상세 정보 조회"""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._sync_get_node_detail, mindmap_id, node_id)

    def _sync_get_node_detail(self, mindmap_id: str, node_id: str) -> Optional[NodeDetailResponse]:
        """Synchronous node detail retrieval"""
        self._ensure_initialized()

        # 노드 정보 조회
        node_result = self._graph.query(
            """
            MATCH (c:Concept {id: $node_id})
            RETURN c.id AS id, c.label AS label, c.type AS type,
                   c.description AS description, c.importance AS importance
            """,
            {"node_id": node_id}
        )

        if not node_result:
            return None

        n = node_result[0]
        node_type = NodeType(n["type"]) if n["type"] else NodeType.CONCEPT

        color_map = {
            NodeType.ROOT: "#2563EB",
            NodeType.CONCEPT: "#3B82F6",
            NodeType.ENTITY: "#10B981",
            NodeType.TOPIC: "#8B5CF6",
            NodeType.KEYWORD: "#F59E0B"
        }

        importance = n["importance"] or 0.5
        node = MindmapNode(
            id=n["id"],
            label=n["label"],
            type=node_type,
            description=n["description"],
            importance=importance,
            color=color_map.get(node_type, "#3B82F6"),
            size=20 + (importance * 20)
        )

        # 연결된 노드들 조회
        connected_result = self._graph.query(
            """
            MATCH (c:Concept {id: $node_id})-[r:CONCEPT_RELATION]-(other:Concept)
            RETURN other.id AS id, other.label AS label, other.type AS type,
                   other.description AS description, other.importance AS importance,
                   r.id AS edge_id, r.relation AS relation, r.label AS edge_label,
                   r.strength AS strength,
                   CASE WHEN startNode(r) = c THEN 'outgoing' ELSE 'incoming' END AS direction
            """,
            {"node_id": node_id}
        )

        connected_nodes = []
        edges = []

        for c in connected_result:
            c_type = NodeType(c["type"]) if c["type"] else NodeType.CONCEPT
            c_importance = c["importance"] or 0.5

            connected_nodes.append(MindmapNode(
                id=c["id"],
                label=c["label"],
                type=c_type,
                description=c["description"],
                importance=c_importance,
                color=color_map.get(c_type, "#3B82F6"),
                size=20 + (c_importance * 20)
            ))

            try:
                rel_type = RelationType(c["relation"]) if c["relation"] else RelationType.RELATES_TO
            except ValueError:
                rel_type = RelationType.RELATES_TO

            if c["direction"] == "outgoing":
                source, target = node_id, c["id"]
            else:
                source, target = c["id"], node_id

            edges.append(MindmapEdge(
                id=c["edge_id"],
                source=source,
                target=target,
                relation=rel_type,
                label=c["edge_label"],
                strength=c["strength"] or 0.5
            ))

        # 원본 문서 내용 조회
        source_content = self._graph.query(
            """
            MATCH (m:Mindmap {id: $mindmap_id})
            UNWIND m.document_ids AS doc_id
            MATCH (d:Document {id: doc_id})-[:CONTAINS]->(c:Chunk)
            WHERE c.content CONTAINS $concept
            RETURN c.content AS content, c.id AS chunk_id, d.id AS doc_id
            LIMIT 3
            """,
            {"mindmap_id": mindmap_id, "concept": node.label}
        )

        sources = [
            {"chunk_id": s["chunk_id"], "doc_id": s["doc_id"], "content": s["content"][:300]}
            for s in source_content
        ]

        return NodeDetailResponse(
            node=node,
            connected_nodes=connected_nodes,
            edges=edges,
            source_content=sources
        )

    async def delete_mindmap(self, mindmap_id: str) -> bool:
        """마인드맵 삭제"""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._sync_delete_mindmap, mindmap_id)

    def _sync_delete_mindmap(self, mindmap_id: str) -> bool:
        """Synchronous mindmap deletion"""
        self._ensure_initialized()

        try:
            # 관련 개념과 관계 삭제
            self._graph.query(
                """
                MATCH (m:Mindmap {id: $id})-[:HAS_CONCEPT]->(c:Concept)
                DETACH DELETE c
                """,
                {"id": mindmap_id}
            )

            # 마인드맵 삭제
            self._graph.query(
                "MATCH (m:Mindmap {id: $id}) DELETE m",
                {"id": mindmap_id}
            )

            return True
        except Exception as e:
            print(f"Delete error: {e}")
            return False


@lru_cache()
def get_mindmap_service() -> MindmapService:
    """Get cached mindmap service instance"""
    return MindmapService.get_instance()
