"""
Knowledge Graph API Router
지식 그래프 생성, 조회, 관리 API

Based on Neo4j Knowledge Graph patterns:
- Entity extraction and management
- Relationship building
- Graph traversal and querying
- Cypher query execution
"""
import uuid
import time
from datetime import datetime
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, Query, status

from ..models.base import SuccessResponse, PaginatedResponse, PaginationMeta, MetaInfo
from ..models.knowledge_graph import (
    EntityType,
    RelationType,
    KGEntity,
    KGRelationship,
    KnowledgeGraph,
    KGSummary,
    # Request models
    ExtractEntitiesRequest,
    BuildKGRequest,
    QueryKGRequest,
    ExpandEntityRequest,
    MergeKGRequest,
    InferRelationshipsRequest,
    CypherQueryRequest,
    Neo4jExportRequest,
    # Response models
    ExtractEntitiesResponse,
    BuildKGResponse,
    QueryKGResponse,
    ExpandEntityResponse,
    InferRelationshipsResponse,
    KGListResponse,
    CypherQueryResponse,
    Neo4jExportResponse,
)
from ..core.deps import get_current_user
from ..services.knowledge_graph_service import get_knowledge_graph_service

router = APIRouter(prefix="/knowledge-graph", tags=["Knowledge Graph"])


# === Build & Manage Knowledge Graphs ===

@router.post(
    "/build",
    response_model=SuccessResponse[BuildKGResponse],
    status_code=status.HTTP_201_CREATED,
    summary="지식 그래프 생성",
    description="""쿼리 및/또는 문서로부터 지식 그래프를 생성합니다.

**주요 기능:**
- 자연어 쿼리에서 엔티티 및 관계 추출
- LLM/NLP 기반 엔티티 인식
- 관계 추론 및 그래프 구축
- Neo4j 호환 형식으로 출력

**처리 옵션:**
- `use_llm_extraction`: LLM을 사용한 정확한 추출
- `use_ner`: NER 모델을 사용한 엔티티 감지
- `infer_relationships`: 암시적 관계 추론
- `merge_similar_entities`: 유사 엔티티 병합
"""
)
async def build_knowledge_graph(
    request: BuildKGRequest,
    current_user: dict = Depends(get_current_user)
):
    """Build a Knowledge Graph from query and/or documents."""
    request_id = f"req_{uuid.uuid4().hex[:12]}"
    start_time = time.time()

    try:
        kg_service = get_knowledge_graph_service()

        kg = await kg_service.build_knowledge_graph(
            query=request.query,
            document_ids=request.document_ids,
            name=request.name,
            description=request.description,
            max_entities=request.max_entities,
            max_relationships=request.max_relationships,
            entity_types=request.entity_types or None,
            relation_types=request.relation_types or None,
            use_llm_extraction=request.use_llm_extraction,
            infer_relationships=request.infer_relationships,
            merge_similar_entities=request.merge_similar_entities,
            language=request.language
        )

        processing_time = int((time.time() - start_time) * 1000)

        return SuccessResponse(
            data=BuildKGResponse(
                knowledge_graph=kg,
                message=f"Knowledge Graph '{kg.name}' created with {kg.entity_count} entities and {kg.relationship_count} relationships",
                stats={
                    "processing_time_ms": processing_time,
                    "entity_count": kg.entity_count,
                    "relationship_count": kg.relationship_count,
                    "source_query": request.query,
                    "source_documents": len(request.document_ids)
                }
            ),
            meta=MetaInfo(request_id=request_id, processing_time_ms=processing_time)
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get(
    "",
    response_model=SuccessResponse[KGListResponse],
    summary="지식 그래프 목록 조회",
    description="생성된 지식 그래프 목록을 조회합니다."
)
async def list_knowledge_graphs(
    page: int = Query(default=1, ge=1, description="페이지 번호"),
    limit: int = Query(default=20, ge=1, le=100, description="페이지당 항목 수"),
    current_user: dict = Depends(get_current_user)
):
    """List all Knowledge Graphs."""
    request_id = f"req_{uuid.uuid4().hex[:12]}"

    try:
        kg_service = get_knowledge_graph_service()
        result = await kg_service.list_knowledge_graphs(page, limit)

        return SuccessResponse(
            data=KGListResponse(
                knowledge_graphs=result["knowledge_graphs"],
                total=result["total"]
            ),
            meta=MetaInfo(request_id=request_id)
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get(
    "/{kg_id}",
    response_model=SuccessResponse[KnowledgeGraph],
    summary="지식 그래프 상세 조회",
    description="특정 지식 그래프의 전체 데이터를 조회합니다."
)
async def get_knowledge_graph(
    kg_id: str,
    current_user: dict = Depends(get_current_user)
):
    """Get a Knowledge Graph by ID."""
    request_id = f"req_{uuid.uuid4().hex[:12]}"

    try:
        kg_service = get_knowledge_graph_service()
        kg = await kg_service.get_knowledge_graph(kg_id)

        if not kg:
            raise HTTPException(
                status_code=404,
                detail={
                    "code": "KG_NOT_FOUND",
                    "message": f"Knowledge Graph not found: {kg_id}"
                }
            )

        return SuccessResponse(
            data=kg,
            meta=MetaInfo(request_id=request_id)
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete(
    "/{kg_id}",
    response_model=SuccessResponse[dict],
    summary="지식 그래프 삭제",
    description="지식 그래프를 삭제합니다."
)
async def delete_knowledge_graph(
    kg_id: str,
    current_user: dict = Depends(get_current_user)
):
    """Delete a Knowledge Graph."""
    request_id = f"req_{uuid.uuid4().hex[:12]}"

    try:
        kg_service = get_knowledge_graph_service()
        deleted = await kg_service.delete_knowledge_graph(kg_id)

        if not deleted:
            raise HTTPException(
                status_code=404,
                detail={
                    "code": "KG_NOT_FOUND",
                    "message": f"Knowledge Graph not found: {kg_id}"
                }
            )

        return SuccessResponse(
            data={"deleted": True, "kg_id": kg_id},
            meta=MetaInfo(request_id=request_id)
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# === Query Knowledge Graph ===

@router.post(
    "/{kg_id}/query",
    response_model=SuccessResponse[QueryKGResponse],
    summary="지식 그래프 질의",
    description="""지식 그래프에 자연어로 질의합니다.

**기능:**
- 자연어 질의를 그래프 탐색으로 변환
- 관련 엔티티 및 관계 검색
- 경로 탐색 (max_hops 설정)
- Neo4j Cypher 쿼리 생성
"""
)
async def query_knowledge_graph(
    kg_id: str,
    request: QueryKGRequest,
    current_user: dict = Depends(get_current_user)
):
    """Query a Knowledge Graph with natural language."""
    request_id = f"req_{uuid.uuid4().hex[:12]}"
    start_time = time.time()

    try:
        kg_service = get_knowledge_graph_service()

        result = await kg_service.query_knowledge_graph(
            knowledge_graph_id=kg_id,
            query=request.query,
            max_hops=request.max_hops,
            include_paths=request.include_paths,
            use_embeddings=request.use_embeddings
        )

        processing_time = int((time.time() - start_time) * 1000)

        return SuccessResponse(
            data=QueryKGResponse(
                answer=result["answer"],
                relevant_entities=result["relevant_entities"],
                relevant_relationships=result["relevant_relationships"],
                paths=result["paths"],
                confidence=result["confidence"],
                cypher_query=result.get("cypher_query")
            ),
            meta=MetaInfo(request_id=request_id, processing_time_ms=processing_time)
        )

    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# === Entity Operations ===

@router.post(
    "/entities/extract",
    response_model=SuccessResponse[ExtractEntitiesResponse],
    summary="엔티티 추출",
    description="""텍스트에서 엔티티를 추출합니다.

**추출 가능 엔티티 유형:**
- 개념(concept), 인물(person), 조직(organization)
- 위치(location), 이벤트(event), 기술(technology)
- 프로세스(process), 제품(product), 용어(term) 등
"""
)
async def extract_entities(
    request: ExtractEntitiesRequest,
    current_user: dict = Depends(get_current_user)
):
    """Extract entities from text."""
    request_id = f"req_{uuid.uuid4().hex[:12]}"
    start_time = time.time()

    try:
        kg_service = get_knowledge_graph_service()

        entities = await kg_service.entity_extractor.extract_entities(
            text=request.text,
            entity_types=request.entity_types or None,
            language=request.language,
            use_llm=True
        )

        # Also extract relationships
        relationships = await kg_service.relationship_extractor.extract_relationships(
            text=request.text,
            entities=entities,
            use_llm=True
        )

        processing_time = int((time.time() - start_time) * 1000)

        return SuccessResponse(
            data=ExtractEntitiesResponse(
                entities=entities,
                relationships=relationships,
                entity_count=len(entities),
                relationship_count=len(relationships),
                processing_time_ms=processing_time
            ),
            meta=MetaInfo(request_id=request_id, processing_time_ms=processing_time)
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post(
    "/entities/{entity_id}/expand",
    response_model=SuccessResponse[ExpandEntityResponse],
    summary="엔티티 확장",
    description="엔티티와 연결된 이웃 엔티티들을 조회합니다."
)
async def expand_entity(
    entity_id: str,
    request: ExpandEntityRequest,
    current_user: dict = Depends(get_current_user)
):
    """Expand an entity with its neighbors."""
    request_id = f"req_{uuid.uuid4().hex[:12]}"

    try:
        kg_service = get_knowledge_graph_service()

        result = await kg_service.expand_entity(
            entity_id=entity_id,
            max_depth=request.max_depth,
            max_neighbors=request.max_neighbors,
            relation_types=request.relation_types or None
        )

        return SuccessResponse(
            data=ExpandEntityResponse(
                center_entity=result["center_entity"],
                expanded_entities=result["expanded_entities"],
                relationships=result["relationships"],
                depth_reached=result["depth_reached"]
            ),
            meta=MetaInfo(request_id=request_id)
        )

    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# === Inference ===

@router.post(
    "/{kg_id}/infer",
    response_model=SuccessResponse[InferRelationshipsResponse],
    summary="관계 추론",
    description="""온톨로지 규칙을 사용하여 새로운 관계를 추론합니다.

**추론 규칙:**
- 전이성 (A→B, B→C이면 A→C)
- 동일 유형 클러스터링
- 온톨로지 기반 추론
"""
)
async def infer_relationships(
    kg_id: str,
    request: InferRelationshipsRequest,
    current_user: dict = Depends(get_current_user)
):
    """Infer new relationships using reasoning rules."""
    request_id = f"req_{uuid.uuid4().hex[:12]}"

    try:
        kg_service = get_knowledge_graph_service()

        kg = await kg_service.get_knowledge_graph(kg_id)
        if not kg:
            raise HTTPException(status_code=404, detail=f"Knowledge Graph not found: {kg_id}")

        # Run inference
        inferred = await kg_service._infer_relationships(
            kg.entities,
            kg.relationships
        )

        # Filter by confidence
        inferred = [
            r for r in inferred
            if r.confidence >= request.confidence_threshold
        ]

        return SuccessResponse(
            data=InferRelationshipsResponse(
                inferred_relationships=inferred,
                rules_applied=list(set(
                    r.properties.get("rule", "unknown") for r in inferred
                )),
                inference_count=len(inferred)
            ),
            meta=MetaInfo(request_id=request_id)
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# === Neo4j / Cypher ===

@router.post(
    "/{kg_id}/cypher",
    response_model=SuccessResponse[CypherQueryResponse],
    summary="Cypher 쿼리 실행",
    description="지식 그래프에 Cypher 쿼리를 실행합니다 (시뮬레이션)."
)
async def execute_cypher(
    kg_id: str,
    request: CypherQueryRequest,
    current_user: dict = Depends(get_current_user)
):
    """Execute a Cypher query on Knowledge Graph (simulated)."""
    request_id = f"req_{uuid.uuid4().hex[:12]}"
    start_time = time.time()

    try:
        kg_service = get_knowledge_graph_service()

        kg = await kg_service.get_knowledge_graph(kg_id)
        if not kg:
            raise HTTPException(status_code=404, detail=f"Knowledge Graph not found: {kg_id}")

        # Parse and simulate Cypher query
        # In production, this would connect to actual Neo4j
        cypher_lower = request.cypher.lower()

        results = []
        columns = []

        if "match" in cypher_lower and "return" in cypher_lower:
            # Simple simulation: return matching nodes
            if "(n)" in cypher_lower or "(n:" in cypher_lower:
                columns = ["n.id", "n.label", "n.type"]
                for ent in kg.entities[:20]:
                    results.append({
                        "n.id": ent.id,
                        "n.label": ent.label,
                        "n.type": ent.entity_type.value
                    })

        processing_time = int((time.time() - start_time) * 1000)

        return SuccessResponse(
            data=CypherQueryResponse(
                results=results,
                columns=columns,
                row_count=len(results),
                execution_time_ms=processing_time
            ),
            meta=MetaInfo(request_id=request_id, processing_time_ms=processing_time)
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post(
    "/{kg_id}/export",
    response_model=SuccessResponse[Neo4jExportResponse],
    summary="Neo4j 형식으로 내보내기",
    description="지식 그래프를 Neo4j 호환 형식(Cypher, JSON, GraphML)으로 내보냅니다."
)
async def export_to_neo4j(
    kg_id: str,
    request: Neo4jExportRequest,
    current_user: dict = Depends(get_current_user)
):
    """Export Knowledge Graph to Neo4j format."""
    request_id = f"req_{uuid.uuid4().hex[:12]}"

    try:
        kg_service = get_knowledge_graph_service()

        kg = await kg_service.get_knowledge_graph(kg_id)
        if not kg:
            raise HTTPException(status_code=404, detail=f"Knowledge Graph not found: {kg_id}")

        if request.format == "cypher":
            data = await kg_service.export_to_cypher(
                kg_id,
                include_properties=request.include_properties
            )
        elif request.format == "json":
            # JSON export
            import json
            data = json.dumps({
                "nodes": [e.model_dump() for e in kg.entities],
                "relationships": [r.model_dump() for r in kg.relationships]
            }, default=str, indent=2)
        else:
            # GraphML export (simplified)
            nodes_xml = "\n".join([
                f'  <node id="{e.id}"><data key="label">{e.label}</data><data key="type">{e.entity_type.value}</data></node>'
                for e in kg.entities
            ])
            edges_xml = "\n".join([
                f'  <edge source="{r.source_id}" target="{r.target_id}"><data key="type">{r.relation_type.value}</data></edge>'
                for r in kg.relationships
            ])
            data = f'''<?xml version="1.0" encoding="UTF-8"?>
<graphml>
  <key id="label" for="node" attr.name="label" attr.type="string"/>
  <key id="type" for="node" attr.name="type" attr.type="string"/>
  <key id="type" for="edge" attr.name="type" attr.type="string"/>
  <graph id="G" edgedefault="directed">
{nodes_xml}
{edges_xml}
  </graph>
</graphml>'''

        return SuccessResponse(
            data=Neo4jExportResponse(
                format=request.format,
                data=data,
                node_count=len(kg.entities),
                relationship_count=len(kg.relationships)
            ),
            meta=MetaInfo(request_id=request_id)
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# === Entity Types & Relation Types ===

@router.get(
    "/types/entities",
    response_model=SuccessResponse[dict],
    summary="엔티티 유형 목록",
    description="사용 가능한 엔티티 유형 목록을 조회합니다."
)
async def get_entity_types(
    current_user: dict = Depends(get_current_user)
):
    """Get available entity types."""
    request_id = f"req_{uuid.uuid4().hex[:12]}"

    types = [
        {"value": t.value, "name": t.name, "description": _get_entity_type_description(t)}
        for t in EntityType
    ]

    return SuccessResponse(
        data={"entity_types": types, "count": len(types)},
        meta=MetaInfo(request_id=request_id)
    )


@router.get(
    "/types/relations",
    response_model=SuccessResponse[dict],
    summary="관계 유형 목록",
    description="사용 가능한 관계 유형 목록을 조회합니다."
)
async def get_relation_types(
    current_user: dict = Depends(get_current_user)
):
    """Get available relation types."""
    request_id = f"req_{uuid.uuid4().hex[:12]}"

    types = [
        {"value": t.value, "name": t.name, "description": _get_relation_type_description(t)}
        for t in RelationType
    ]

    return SuccessResponse(
        data={"relation_types": types, "count": len(types)},
        meta=MetaInfo(request_id=request_id)
    )


def _get_entity_type_description(entity_type: EntityType) -> str:
    """Get description for entity type."""
    descriptions = {
        EntityType.CONCEPT: "추상적 개념",
        EntityType.PERSON: "사람/인물",
        EntityType.ORGANIZATION: "조직/회사",
        EntityType.LOCATION: "위치/장소",
        EntityType.EVENT: "이벤트/사건",
        EntityType.DOCUMENT: "문서",
        EntityType.TOPIC: "주제/테마",
        EntityType.TECHNOLOGY: "기술/도구",
        EntityType.PROCESS: "프로세스/절차",
        EntityType.PRODUCT: "제품/서비스",
        EntityType.TERM: "용어/정의",
        EntityType.METRIC: "지표/측정값",
        EntityType.DATE: "날짜/시간",
        EntityType.QUANTITY: "수량/단위",
    }
    return descriptions.get(entity_type, entity_type.value)


def _get_relation_type_description(relation_type: RelationType) -> str:
    """Get description for relation type."""
    descriptions = {
        RelationType.IS_A: "~이다 (유형 계층)",
        RelationType.PART_OF: "~의 일부",
        RelationType.CONTAINS: "포함하다",
        RelationType.SUBCLASS_OF: "~의 하위 클래스",
        RelationType.RELATED_TO: "관련 있다",
        RelationType.SIMILAR_TO: "유사하다",
        RelationType.OPPOSITE_OF: "반대이다",
        RelationType.SYNONYM_OF: "동의어이다",
        RelationType.CAUSES: "야기하다",
        RelationType.LEADS_TO: "이어지다",
        RelationType.DEPENDS_ON: "의존하다",
        RelationType.ENABLES: "가능하게 하다",
        RelationType.PREVENTS: "방지하다",
        RelationType.BEFORE: "전에",
        RelationType.AFTER: "후에",
        RelationType.DURING: "동안",
        RelationType.CREATED_BY: "~가 만들다",
        RelationType.OWNED_BY: "소유하다",
        RelationType.WORKS_FOR: "근무하다",
        RelationType.LOCATED_IN: "위치하다",
        RelationType.PARTICIPATES_IN: "참여하다",
        RelationType.DEFINES: "정의하다",
        RelationType.DESCRIBES: "설명하다",
        RelationType.REFERENCES: "참조하다",
        RelationType.DERIVED_FROM: "파생되다",
        RelationType.EXAMPLE_OF: "예시이다",
        RelationType.USES: "사용하다",
        RelationType.IMPLEMENTS: "구현하다",
        RelationType.EXTENDS: "확장하다",
        RelationType.INTEGRATES_WITH: "통합하다",
    }
    return descriptions.get(relation_type, relation_type.value)
