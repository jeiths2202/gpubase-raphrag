"""
Mindmap Service - Concept extraction and mindmap generation
LLM을 활용한 개념 추출 및 마인드맵 생성 서비스
"""
import asyncio
import hashlib
import re
import json
from typing import Dict, List, Any, Optional, Tuple
from functools import lru_cache
from datetime import datetime, timezone
import sys
import os

# Add src directory to path for importing existing modules
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src'))

from langchain_openai import ChatOpenAI
from langchain_neo4j import Neo4jGraph

# Import config from src
try:
    from config import config
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
    config = FallbackConfig()

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
    """

    _instance: Optional['MindmapService'] = None

    def __init__(self):
        """Initialize mindmap service"""
        self._graph: Optional[Neo4jGraph] = None
        self._llm: Optional[ChatOpenAI] = None
        self._initialized: bool = False

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

            # Initialize schema
            self._init_mindmap_schema()
            self._initialized = True

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

        # 1. 문서에서 청크 가져오기
        chunks = self._get_document_chunks(request.document_ids)

        if not chunks:
            # 빈 마인드맵 반환
            mindmap_id = self._generate_id("mm", "empty")
            return MindmapFull(
                id=mindmap_id,
                title=request.title or "Empty Mindmap",
                document_ids=request.document_ids,
                node_count=0,
                edge_count=0,
                data=MindmapData(nodes=[], edges=[], root_id=None)
            )

        # 2. LLM을 사용하여 개념과 관계 추출
        concepts_data = self._extract_concepts_and_relations(
            chunks,
            max_nodes=request.max_nodes,
            focus_topic=request.focus_topic,
            language=request.language
        )

        # 3. 마인드맵 데이터 구조 생성
        nodes, edges, root_id = self._build_mindmap_structure(
            concepts_data,
            request.depth
        )

        # 4. 마인드맵 정보 생성
        mindmap_id = self._generate_id("mm", request.title or chunks[0].get("content", "")[:50])
        title = request.title or self._generate_title(concepts_data, request.language)

        # 5. Neo4j에 저장
        self._save_mindmap_to_neo4j(mindmap_id, title, nodes, edges, request.document_ids)

        return MindmapFull(
            id=mindmap_id,
            title=title,
            description=f"Generated from {len(request.document_ids)} document(s)",
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

    def _extract_concepts_and_relations(
        self,
        chunks: List[Dict],
        max_nodes: int = 50,
        focus_topic: Optional[str] = None,
        language: str = "auto"
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

        # 언어별 프롬프트
        if language == "ko":
            lang_instruction = "한국어로 개념을 추출하세요."
        elif language == "ja":
            lang_instruction = "日本語で概念を抽出してください。"
        else:
            lang_instruction = "Extract concepts in the same language as the source documents."

        focus_instruction = ""
        if focus_topic:
            focus_instruction = f"\n집중할 주제: {focus_topic}\n이 주제를 중심으로 관련 개념들을 추출하세요."

        prompt = f"""다음 문서들에서 핵심 개념(concepts)과 그들 사이의 관계(relations)를 추출하세요.
{lang_instruction}
{focus_instruction}

문서 내용:
{combined_content}

기존에 추출된 엔티티들 (참고용):
{', '.join(list(existing_entities)[:30])}

다음 JSON 형식으로 응답하세요:
{{
    "main_topic": "가장 중요한 핵심 주제",
    "concepts": [
        {{"name": "개념명", "type": "concept|entity|topic|keyword", "importance": 0.0-1.0, "description": "간단한 설명"}}
    ],
    "relations": [
        {{"source": "개념1", "target": "개념2", "relation": "relates_to|contains|causes|depends_on|similar_to|part_of", "label": "관계 설명"}}
    ]
}}

규칙:
1. 최대 {max_nodes}개의 개념을 추출하세요
2. 가장 중요한 개념의 importance는 1.0에 가깝게, 덜 중요한 개념은 낮게 설정하세요
3. 관계는 명확한 연결이 있는 경우에만 추출하세요
4. main_topic은 문서 전체를 대표하는 핵심 주제입니다

JSON 응답:"""

        try:
            response = self._llm.invoke(prompt)
            response_text = response.content.strip()

            # JSON 추출
            json_match = re.search(r'\{[\s\S]*\}', response_text)
            if json_match:
                concepts_data = json.loads(json_match.group())
                return concepts_data
            else:
                # JSON 파싱 실패 시 기본값 반환
                return self._fallback_concepts(chunks, existing_entities)

        except json.JSONDecodeError as e:
            print(f"JSON parsing error: {e}")
            return self._fallback_concepts(chunks, existing_entities)
        except Exception as e:
            print(f"Concept extraction error: {e}")
            return self._fallback_concepts(chunks, existing_entities)

    def _fallback_concepts(self, chunks: List[Dict], entities: set) -> Dict[str, Any]:
        """개념 추출 실패 시 기존 엔티티 기반 폴백"""
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
                    "label": "관련"
                })

        return {
            "main_topic": entity_list[0] if entity_list else "Document",
            "concepts": concepts,
            "relations": relations
        }

    def _build_mindmap_structure(
        self,
        concepts_data: Dict[str, Any],
        depth: int = 3
    ) -> Tuple[List[MindmapNode], List[MindmapEdge], str]:
        """개념 데이터로부터 마인드맵 구조 생성"""
        nodes = []
        edges = []

        main_topic = concepts_data.get("main_topic", "Main Topic")
        concepts = concepts_data.get("concepts", [])
        relations = concepts_data.get("relations", [])

        # 루트 노드 생성
        root_id = self._generate_id("node", main_topic)
        root_node = MindmapNode(
            id=root_id,
            label=main_topic,
            type=NodeType.ROOT,
            description=f"Main topic of the mindmap",
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
        """마인드맵 제목 생성"""
        main_topic = concepts_data.get("main_topic", "Mindmap")

        if language == "ko":
            return f"{main_topic} 마인드맵"
        elif language == "ja":
            return f"{main_topic} マインドマップ"
        else:
            return f"{main_topic} Mindmap"

    def _save_mindmap_to_neo4j(
        self,
        mindmap_id: str,
        title: str,
        nodes: List[MindmapNode],
        edges: List[MindmapEdge],
        document_ids: List[str]
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
                m.updated_at = datetime()
            """,
            {
                "id": mindmap_id,
                "title": title,
                "doc_ids": document_ids,
                "node_count": len(nodes),
                "edge_count": len(edges)
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

        # 노드 정보 조회
        node_result = self._graph.query(
            """
            MATCH (c:Concept {id: $node_id})
            RETURN c.label AS label, c.description AS description
            """,
            {"node_id": request.node_id}
        )

        if not node_result:
            return ExpandNodeResponse(
                new_nodes=[],
                new_edges=[],
                expanded_from=request.node_id
            )

        node_label = node_result[0]["label"]

        # 마인드맵의 문서에서 관련 청크 검색
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

        if not chunks:
            return ExpandNodeResponse(
                new_nodes=[],
                new_edges=[],
                expanded_from=request.node_id
            )

        # LLM으로 하위 개념 추출
        combined_content = "\n".join([c["content"][:500] for c in chunks])

        prompt = f"""다음 내용에서 "{node_label}"의 하위 개념이나 관련 세부 사항을 추출하세요.

내용:
{combined_content}

다음 JSON 형식으로 응답하세요:
{{
    "sub_concepts": [
        {{"name": "하위 개념명", "relation": "part_of|example_of|relates_to", "description": "설명"}}
    ]
}}

최대 {request.max_children}개의 하위 개념을 추출하세요.

JSON:"""

        try:
            response = self._llm.invoke(prompt)
            json_match = re.search(r'\{[\s\S]*\}', response.content)

            if json_match:
                sub_data = json.loads(json_match.group())
                sub_concepts = sub_data.get("sub_concepts", [])
            else:
                sub_concepts = []
        except Exception as e:
            print(f"Expansion error: {e}")
            sub_concepts = []

        # 새 노드와 엣지 생성
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
                answer="Node not found",
                related_concepts=[],
                sources=[]
            )

        node_label = node_result[0]["label"]

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

        # 질문 생성
        question = request.question or f"{node_label}에 대해 요약해주세요."

        # 컨텍스트 구성
        context = "\n\n".join([c["content"][:500] for c in chunks])

        # LLM으로 답변 생성
        prompt = f"""다음 문맥을 바탕으로 질문에 답변하세요.

문맥:
{context}

관련 개념들: {', '.join(related_concepts)}

질문: {question}

답변:"""

        try:
            response = self._llm.invoke(prompt)
            answer = response.content.strip()
        except Exception as e:
            answer = f"Error generating answer: {e}"

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
            {"mindmap_id": mindmap_id, "concept": node["label"]}
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
