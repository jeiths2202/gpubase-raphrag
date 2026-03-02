"""
Graph Visualization API Router
Neo4j 서브그래프를 ReactFlow JSON으로 반환하는 API

Endpoints:
  GET  /graph-viz/entity    — 엔티티 주변 서브그래프
  POST /graph-viz/query     — 쿼리 관련 엔티티 그래프
  GET  /graph-viz/product/{product_id} — 제품 엔티티 개요 그래프
"""
import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, Query, Path
from pydantic import BaseModel, Field

from ..core.deps import get_current_user
from ..services.graph_visualization_service import (
    get_graph_visualization_service,
    GraphVisualizationService,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/graph-viz", tags=["Graph Visualization"])


# ── Request / Response models ────────────────────────────────────────

class QueryGraphRequest(BaseModel):
    """쿼리 기반 그래프 요청"""
    query: str = Field(..., min_length=1, description="검색 쿼리")
    product_ids: Optional[List[str]] = Field(None, description="제품 ID 필터")
    limit: int = Field(20, ge=1, le=30, description="최대 노드 수")


class GraphResponse(BaseModel):
    """ReactFlow 호환 그래프 응답"""
    nodes: List[Dict[str, Any]] = Field(default_factory=list)
    edges: List[Dict[str, Any]] = Field(default_factory=list)


# ── Helper ───────────────────────────────────────────────────────────

def _get_service() -> GraphVisualizationService:
    return get_graph_visualization_service()


# ── Endpoints ────────────────────────────────────────────────────────

@router.get(
    "/entity",
    response_model=GraphResponse,
    summary="엔티티 서브그래프 조회",
    description="지정 엔티티 주변의 Neo4j 서브그래프를 ReactFlow JSON으로 반환합니다.",
)
async def get_entity_graph(
    name: str = Query(..., min_length=1, description="엔티티 이름 (부분 매칭)"),
    depth: int = Query(2, ge=1, le=3, description="탐색 깊이"),
    limit: int = Query(30, ge=1, le=50, description="최대 경로 수"),
    _user: dict = Depends(get_current_user),
    service: GraphVisualizationService = Depends(_get_service),
) -> GraphResponse:
    result = await service.get_entity_graph(name, depth=depth, limit=limit)
    return GraphResponse(**result)


@router.post(
    "/query",
    response_model=GraphResponse,
    summary="쿼리 관련 그래프 조회",
    description="쿼리 키워드와 매칭되는 엔티티 그래프를 반환합니다.",
)
async def get_query_graph(
    body: QueryGraphRequest,
    _user: dict = Depends(get_current_user),
    service: GraphVisualizationService = Depends(_get_service),
) -> GraphResponse:
    result = await service.get_query_graph(
        query=body.query,
        product_ids=body.product_ids,
        limit=body.limit,
    )
    return GraphResponse(**result)


@router.get(
    "/product/{product_id}",
    response_model=GraphResponse,
    summary="제품 엔티티 개요 그래프",
    description="제품의 주요 엔티티와 관계를 개요 그래프로 반환합니다.",
)
async def get_product_overview_graph(
    product_id: str = Path(..., description="제품 ID"),
    limit: int = Query(50, ge=1, le=80, description="최대 엔티티 수"),
    _user: dict = Depends(get_current_user),
    service: GraphVisualizationService = Depends(_get_service),
) -> GraphResponse:
    result = await service.get_product_overview_graph(product_id, limit=limit)
    return GraphResponse(**result)
