"""
Graph Visualization Service

Neo4j 서브그래프를 추출하고 ReactFlow 호환 JSON으로 변환합니다.
neuml/rag의 NetworkX 시각화 접근법을 참고하여,
서버사이드에서 레이아웃 좌표를 계산 후 프론트엔드에 전송합니다.
"""
import math
import logging
import os
from typing import Any, Dict, List, Optional

import networkx as nx

logger = logging.getLogger(__name__)

# EntityType별 시각화 속성
_ENTITY_COLORS: Dict[str, str] = {
    "command": "#10b981",
    "error_code": "#ef4444",
    "config": "#3b82f6",
    "product": "#8b5cf6",
    "technology": "#f59e0b",
    "concept": "#6b7280",
    "term": "#14b8a6",
    "topic": "#ec4899",
    "process": "#f97316",
    "person": "#06b6d4",
    "organization": "#a855f7",
    "document": "#64748b",
}

_DEFAULT_COLOR = "#6b7280"


class GraphVisualizationService:
    """Neo4j 서브그래프 → ReactFlow JSON 변환 서비스"""

    def __init__(self):
        self._graph = None

    def _ensure_neo4j(self):
        """Neo4j 연결 초기화 (lazy)"""
        if self._graph is not None:
            return
        try:
            from langchain_neo4j import Neo4jGraph
            uri = os.getenv("NEO4J_URI", "bolt://localhost:7687")
            user = os.getenv("NEO4J_USER", "neo4j")
            password = os.getenv("NEO4J_PASSWORD", "")
            self._graph = Neo4jGraph(url=uri, username=user, password=password)
        except Exception as e:
            logger.warning(f"Neo4j connection failed: {e}")

    def _run_cypher(self, query: str, params: Optional[Dict] = None) -> List[Dict]:
        """Cypher 쿼리 실행"""
        self._ensure_neo4j()
        if not self._graph:
            return []
        try:
            return self._graph.query(query, params or {})
        except Exception as e:
            logger.warning(f"Cypher query failed: {e}")
            return []

    async def get_entity_graph(
        self,
        entity_name: str,
        depth: int = 2,
        limit: int = 30,
    ) -> Dict[str, Any]:
        """엔티티 주변 서브그래프 추출"""
        depth = min(depth, 3)  # 과도한 탐색 방지
        limit = min(limit, 50)

        cypher = """
        MATCH (n)
        WHERE toLower(n.name) CONTAINS toLower($entity)
           OR toLower(n.label) CONTAINS toLower($entity)
        WITH n LIMIT 3
        CALL {
            WITH n
            MATCH path = (n)-[*1..%d]-(m)
            RETURN nodes(path) AS ns, relationships(path) AS rs
            LIMIT %d
        }
        WITH ns, rs
        UNWIND ns AS node
        WITH COLLECT(DISTINCT node) AS allNodes, COLLECT(rs) AS allRels
        UNWIND allRels AS relList
        UNWIND relList AS rel
        WITH allNodes, COLLECT(DISTINCT rel) AS allRelations
        RETURN allNodes, allRelations
        """ % (depth, limit)

        results = self._run_cypher(cypher, {"entity": entity_name})
        if not results:
            return {"nodes": [], "edges": []}

        return self._neo4j_paths_to_reactflow(results)

    async def get_query_graph(
        self,
        query: str,
        product_ids: Optional[List[str]] = None,
        limit: int = 20,
    ) -> Dict[str, Any]:
        """쿼리 관련 엔티티 그래프 추출 (키워드 매칭 기반)"""
        limit = min(limit, 30)

        # 쿼리에서 핵심 키워드 추출
        keywords = self._extract_keywords(query)
        if not keywords:
            return {"nodes": [], "edges": []}

        # 키워드로 Entity 검색 + 관계 추출
        where_clauses = " OR ".join(
            f"toLower(e.name) CONTAINS toLower('{kw}')" for kw in keywords[:5]
        )

        cypher = f"""
        MATCH (e)
        WHERE ({where_clauses})
          AND (e:Entity OR e:Concept OR e:Chunk)
        WITH e LIMIT {limit}
        OPTIONAL MATCH (e)-[r]-(e2)
        WHERE e2:Entity OR e2:Concept
        RETURN COLLECT(DISTINCT e) AS entities,
               COLLECT(DISTINCT e2) AS related,
               COLLECT(DISTINCT r) AS relations
        """

        results = self._run_cypher(cypher)
        if not results:
            return {"nodes": [], "edges": []}

        return self._entity_results_to_reactflow(results)

    async def get_product_overview_graph(
        self,
        product_id: str,
        limit: int = 50,
    ) -> Dict[str, Any]:
        """제품 엔티티 개요 그래프"""
        limit = min(limit, 80)

        cypher = """
        MATCH (d:Document)-[:CONTAINS]->(c:Chunk)-[:MENTIONS]->(e:Entity)
        WHERE d.product = $product_id OR d.product CONTAINS $product_id
        WITH e, count(DISTINCT c) AS mentions
        ORDER BY mentions DESC
        LIMIT $limit
        WITH COLLECT(e) AS topEntities
        UNWIND topEntities AS e1
        OPTIONAL MATCH (e1)-[r]-(e2)
        WHERE e2 IN topEntities
        RETURN topEntities,
               COLLECT(DISTINCT r) AS relations
        """

        results = self._run_cypher(cypher, {"product_id": product_id, "limit": limit})
        if not results:
            return {"nodes": [], "edges": []}

        return self._product_results_to_reactflow(results)

    # =========================================================================
    # ReactFlow JSON 변환
    # =========================================================================

    def _neo4j_paths_to_reactflow(self, results: List[Dict]) -> Dict[str, Any]:
        """Neo4j path 결과 → ReactFlow JSON"""
        nodes_map: Dict[str, Dict] = {}
        edges_list: List[Dict] = []

        for row in results:
            all_nodes = row.get("allNodes", [])
            all_relations = row.get("allRelations", [])

            for node in all_nodes:
                if not isinstance(node, dict):
                    continue
                nid = str(node.get("id", node.get("name", id(node))))
                if nid not in nodes_map:
                    nodes_map[nid] = self._make_node(nid, node)

            for rel in all_relations:
                if not isinstance(rel, dict):
                    continue
                edge = self._make_edge(rel)
                if edge:
                    edges_list.append(edge)

        return self._apply_layout(list(nodes_map.values()), edges_list)

    def _entity_results_to_reactflow(self, results: List[Dict]) -> Dict[str, Any]:
        """Entity 검색 결과 → ReactFlow JSON"""
        nodes_map: Dict[str, Dict] = {}
        edges_list: List[Dict] = []

        for row in results:
            for entity in row.get("entities", []):
                if not isinstance(entity, dict):
                    continue
                nid = str(entity.get("id", entity.get("name", id(entity))))
                if nid not in nodes_map:
                    nodes_map[nid] = self._make_node(nid, entity, primary=True)

            for related in row.get("related", []):
                if not isinstance(related, dict) or related is None:
                    continue
                nid = str(related.get("id", related.get("name", id(related))))
                if nid not in nodes_map:
                    nodes_map[nid] = self._make_node(nid, related)

            for rel in row.get("relations", []):
                if not isinstance(rel, dict) or rel is None:
                    continue
                edge = self._make_edge(rel)
                if edge:
                    edges_list.append(edge)

        return self._apply_layout(list(nodes_map.values()), edges_list)

    def _product_results_to_reactflow(self, results: List[Dict]) -> Dict[str, Any]:
        """제품 개요 결과 → ReactFlow JSON"""
        nodes_map: Dict[str, Dict] = {}
        edges_list: List[Dict] = []

        for row in results:
            for entity in row.get("topEntities", []):
                if not isinstance(entity, dict):
                    continue
                nid = str(entity.get("id", entity.get("name", id(entity))))
                if nid not in nodes_map:
                    nodes_map[nid] = self._make_node(nid, entity)

            for rel in row.get("relations", []):
                if not isinstance(rel, dict) or rel is None:
                    continue
                edge = self._make_edge(rel)
                if edge:
                    edges_list.append(edge)

        return self._apply_layout(list(nodes_map.values()), edges_list)

    # =========================================================================
    # 노드/엣지 생성 헬퍼
    # =========================================================================

    def _make_node(self, nid: str, props: Dict, primary: bool = False) -> Dict:
        """Neo4j 노드 → ReactFlow 노드"""
        label = props.get("name") or props.get("label") or props.get("text", nid)
        if len(label) > 40:
            label = label[:37] + "..."

        entity_type = (
            props.get("entity_type")
            or props.get("type")
            or self._infer_type(props)
        )
        color = _ENTITY_COLORS.get(str(entity_type).lower(), _DEFAULT_COLOR)

        return {
            "id": nid,
            "type": "entity",
            "position": {"x": 0, "y": 0},  # _apply_layout에서 계산
            "data": {
                "label": label,
                "entityType": str(entity_type).lower(),
                "color": color,
                "primary": primary,
                "properties": {
                    k: self._to_json_safe(v)
                    for k, v in props.items()
                    if k not in ("id", "name", "label", "text", "embedding")
                    and not k.startswith("_")
                },
            },
        }

    @staticmethod
    def _to_json_safe(value: Any) -> Any:
        """Neo4j 타입을 JSON 직렬화 가능한 타입으로 변환"""
        if isinstance(value, (str, int, float, bool)) or value is None:
            return value
        if isinstance(value, (list, tuple)):
            return [GraphVisualizationService._to_json_safe(v) for v in value]
        if isinstance(value, dict):
            return {k: GraphVisualizationService._to_json_safe(v) for k, v in value.items()}
        # neo4j.time.DateTime, Date, Duration 등
        return str(value)

    def _make_edge(self, rel: Dict) -> Optional[Dict]:
        """Neo4j 관계 → ReactFlow 엣지"""
        # langchain_neo4j는 관계를 dict로 반환 (start_node, end_node 키 등)
        source = rel.get("source_id") or rel.get("start") or rel.get("from")
        target = rel.get("target_id") or rel.get("end") or rel.get("to")
        if not source or not target:
            return None

        rel_type = (
            rel.get("type")
            or rel.get("relation_type")
            or rel.get("label")
            or "RELATED_TO"
        )

        return {
            "id": f"e-{source}-{target}-{rel_type}",
            "source": str(source),
            "target": str(target),
            "label": rel_type.replace("_", " ").title(),
            "type": "smoothstep",
            "animated": False,
            "style": {"stroke": "#94a3b8"},
        }

    def _infer_type(self, props: Dict) -> str:
        """노드 속성에서 엔티티 타입 추론"""
        labels = props.get("_labels", [])
        if isinstance(labels, list):
            for label in labels:
                lbl = label.lower()
                if lbl in _ENTITY_COLORS:
                    return lbl
        return "concept"

    # =========================================================================
    # 레이아웃 계산 (NetworkX spring_layout)
    # =========================================================================

    def _apply_layout(
        self,
        nodes: List[Dict],
        edges: List[Dict],
        scale: float = 400.0,
    ) -> Dict[str, Any]:
        """NetworkX spring_layout으로 노드 좌표 계산"""
        if not nodes:
            return {"nodes": [], "edges": []}

        # 엣지의 source/target이 nodes에 있는지 확인
        node_ids = {n["id"] for n in nodes}
        valid_edges = [
            e for e in edges
            if e["source"] in node_ids and e["target"] in node_ids
        ]

        # NetworkX 그래프 생성
        G = nx.Graph()
        for n in nodes:
            G.add_node(n["id"])
        for e in valid_edges:
            G.add_edge(e["source"], e["target"])

        # spring_layout (neuml/rag 참고: seed=0, k=0.9)
        if len(nodes) == 1:
            pos = {nodes[0]["id"]: (0.0, 0.0)}
        else:
            k = 1.5 / math.sqrt(max(len(nodes), 1))
            pos = nx.spring_layout(G, seed=42, k=k, iterations=50, scale=scale)

        # 좌표 적용
        for node in nodes:
            nid = node["id"]
            if nid in pos:
                x, y = pos[nid]
                node["position"] = {"x": float(x), "y": float(y)}

        # 중복 엣지 제거
        seen_edges = set()
        unique_edges = []
        for e in valid_edges:
            key = (e["source"], e["target"])
            if key not in seen_edges:
                seen_edges.add(key)
                unique_edges.append(e)

        return {"nodes": nodes, "edges": unique_edges}

    # =========================================================================
    # 키워드 추출
    # =========================================================================

    def _extract_keywords(self, query: str) -> List[str]:
        """쿼리에서 검색용 키워드 추출"""
        import re
        # 영문/CJK 토큰 추출
        tokens = re.findall(
            r'[a-zA-Z][a-zA-Z0-9_\-]*[a-zA-Z0-9]|[a-zA-Z]'
            r'|[\u30a0-\u30ff]{2,}'
            r'|[\u4e00-\u9fff]{2,}'
            r'|[\uac00-\ud7af]{2,}',
            query,
        )
        # 불용어 필터
        stopwords = {
            "the", "is", "are", "was", "were", "about", "what", "how",
            "please", "tell", "me", "show", "explain",
            "について", "ください", "してください", "教えて",
            "알려주세요", "보여주세요", "설명",
        }
        return [t for t in tokens if t.lower() not in stopwords and len(t) >= 2]


# =============================================================================
# Singleton
# =============================================================================

_instance: Optional[GraphVisualizationService] = None


def get_graph_visualization_service() -> GraphVisualizationService:
    """Get singleton GraphVisualizationService"""
    global _instance
    if _instance is None:
        _instance = GraphVisualizationService()
    return _instance
