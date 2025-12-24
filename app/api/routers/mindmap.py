"""
Mindmap API Router
마인드맵 생성, 조회, 확장, 질의 API
"""
import time
import uuid
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, Path

from ..models.base import SuccessResponse, MetaInfo, PaginatedResponse, PaginationMeta
from ..models.mindmap import (
    MindmapInfo, MindmapFull, MindmapListResponse,
    GenerateMindmapRequest, GenerateMindmapResponse,
    ExpandNodeRequest, ExpandNodeResponse,
    QueryNodeRequest, QueryNodeResponse,
    NodeDetailResponse
)
from ..core.deps import get_current_user
from ..services.mindmap_service import get_mindmap_service, MindmapService

router = APIRouter(prefix="/mindmap", tags=["Mindmap"])


def get_service() -> MindmapService:
    """Get mindmap service instance"""
    return get_mindmap_service()


@router.post(
    "/generate",
    response_model=SuccessResponse[GenerateMindmapResponse],
    summary="마인드맵 생성",
    description="문서들로부터 마인드맵을 자동 생성합니다. LLM을 사용하여 핵심 개념과 관계를 추출합니다."
)
async def generate_mindmap(
    request: GenerateMindmapRequest,
    current_user: dict = Depends(get_current_user),
    service: MindmapService = Depends(get_service)
):
    """
    Generate mindmap from documents

    - **document_ids**: 마인드맵을 생성할 문서 ID 목록
    - **title**: 마인드맵 제목 (선택, 없으면 자동 생성)
    - **max_nodes**: 최대 노드 수 (기본: 50)
    - **depth**: 탐색 깊이 (기본: 3)
    - **focus_topic**: 집중할 주제 (선택)
    - **language**: 언어 설정 (auto, ko, en, ja)
    """
    start_time = time.time()
    request_id = f"req_{uuid.uuid4().hex[:12]}"

    try:
        mindmap = await service.generate_mindmap(request)

        processing_time = int((time.time() - start_time) * 1000)

        return SuccessResponse(
            data=GenerateMindmapResponse(
                mindmap=mindmap,
                message=f"Mindmap generated with {mindmap.node_count} nodes and {mindmap.edge_count} edges"
            ),
            meta=MetaInfo(
                request_id=request_id,
                processing_time_ms=processing_time
            )
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to generate mindmap: {str(e)}")


@router.get(
    "",
    response_model=PaginatedResponse[MindmapListResponse],
    summary="마인드맵 목록 조회",
    description="생성된 마인드맵 목록을 조회합니다."
)
async def list_mindmaps(
    page: int = Query(1, ge=1, description="페이지 번호"),
    limit: int = Query(20, ge=1, le=100, description="페이지당 항목 수"),
    current_user: dict = Depends(get_current_user),
    service: MindmapService = Depends(get_service)
):
    """List all mindmaps with pagination"""
    request_id = f"req_{uuid.uuid4().hex[:12]}"
    start_time = time.time()

    try:
        offset = (page - 1) * limit
        mindmaps, total = await service.list_mindmaps(limit=limit, offset=offset)

        total_pages = (total + limit - 1) // limit

        processing_time = int((time.time() - start_time) * 1000)

        return PaginatedResponse(
            data=MindmapListResponse(mindmaps=mindmaps, total=total),
            meta=MetaInfo(
                request_id=request_id,
                processing_time_ms=processing_time
            ),
            pagination=PaginationMeta(
                page=page,
                limit=limit,
                total_items=total,
                total_pages=total_pages,
                has_next=page < total_pages,
                has_prev=page > 1
            )
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to list mindmaps: {str(e)}")


@router.get(
    "/{mindmap_id}",
    response_model=SuccessResponse[MindmapFull],
    summary="마인드맵 상세 조회",
    description="마인드맵의 전체 데이터(노드, 엣지)를 조회합니다."
)
async def get_mindmap(
    mindmap_id: str = Path(..., description="마인드맵 ID"),
    current_user: dict = Depends(get_current_user),
    service: MindmapService = Depends(get_service)
):
    """Get mindmap with full data (nodes and edges)"""
    request_id = f"req_{uuid.uuid4().hex[:12]}"
    start_time = time.time()

    try:
        mindmap = await service.get_mindmap(mindmap_id)

        if not mindmap:
            raise HTTPException(status_code=404, detail=f"Mindmap not found: {mindmap_id}")

        processing_time = int((time.time() - start_time) * 1000)

        return SuccessResponse(
            data=mindmap,
            meta=MetaInfo(
                request_id=request_id,
                processing_time_ms=processing_time
            )
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get mindmap: {str(e)}")


@router.delete(
    "/{mindmap_id}",
    response_model=SuccessResponse[dict],
    summary="마인드맵 삭제",
    description="마인드맵과 관련 데이터를 삭제합니다."
)
async def delete_mindmap(
    mindmap_id: str = Path(..., description="마인드맵 ID"),
    current_user: dict = Depends(get_current_user),
    service: MindmapService = Depends(get_service)
):
    """Delete a mindmap"""
    request_id = f"req_{uuid.uuid4().hex[:12]}"
    start_time = time.time()

    try:
        success = await service.delete_mindmap(mindmap_id)

        if not success:
            raise HTTPException(status_code=404, detail=f"Mindmap not found or delete failed: {mindmap_id}")

        processing_time = int((time.time() - start_time) * 1000)

        return SuccessResponse(
            data={"deleted": True, "mindmap_id": mindmap_id},
            meta=MetaInfo(
                request_id=request_id,
                processing_time_ms=processing_time
            )
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to delete mindmap: {str(e)}")


@router.post(
    "/{mindmap_id}/expand",
    response_model=SuccessResponse[ExpandNodeResponse],
    summary="노드 확장",
    description="마인드맵의 특정 노드를 확장하여 하위 개념을 추가합니다."
)
async def expand_node(
    mindmap_id: str = Path(..., description="마인드맵 ID"),
    request: ExpandNodeRequest = ...,
    current_user: dict = Depends(get_current_user),
    service: MindmapService = Depends(get_service)
):
    """
    Expand a node to add sub-concepts

    - **node_id**: 확장할 노드 ID
    - **depth**: 확장 깊이 (기본: 1)
    - **max_children**: 최대 하위 노드 수 (기본: 10)
    """
    request_id = f"req_{uuid.uuid4().hex[:12]}"
    start_time = time.time()

    try:
        result = await service.expand_node(mindmap_id, request)

        processing_time = int((time.time() - start_time) * 1000)

        return SuccessResponse(
            data=result,
            meta=MetaInfo(
                request_id=request_id,
                processing_time_ms=processing_time
            )
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to expand node: {str(e)}")


@router.post(
    "/{mindmap_id}/query",
    response_model=SuccessResponse[QueryNodeResponse],
    summary="노드 관련 질의",
    description="마인드맵의 특정 노드에 대해 RAG 질의를 수행합니다."
)
async def query_node(
    mindmap_id: str = Path(..., description="마인드맵 ID"),
    request: QueryNodeRequest = ...,
    current_user: dict = Depends(get_current_user),
    service: MindmapService = Depends(get_service)
):
    """
    Query about a specific node using RAG

    - **node_id**: 질의할 노드 ID
    - **question**: 추가 질문 (선택, 없으면 노드 요약)
    """
    request_id = f"req_{uuid.uuid4().hex[:12]}"
    start_time = time.time()

    try:
        result = await service.query_node(mindmap_id, request)

        processing_time = int((time.time() - start_time) * 1000)

        return SuccessResponse(
            data=result,
            meta=MetaInfo(
                request_id=request_id,
                processing_time_ms=processing_time
            )
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to query node: {str(e)}")


@router.get(
    "/{mindmap_id}/node/{node_id}",
    response_model=SuccessResponse[NodeDetailResponse],
    summary="노드 상세 조회",
    description="마인드맵의 특정 노드 상세 정보와 연결된 노드들을 조회합니다."
)
async def get_node_detail(
    mindmap_id: str = Path(..., description="마인드맵 ID"),
    node_id: str = Path(..., description="노드 ID"),
    current_user: dict = Depends(get_current_user),
    service: MindmapService = Depends(get_service)
):
    """Get detailed information about a specific node"""
    request_id = f"req_{uuid.uuid4().hex[:12]}"
    start_time = time.time()

    try:
        result = await service.get_node_detail(mindmap_id, node_id)

        if not result:
            raise HTTPException(status_code=404, detail=f"Node not found: {node_id}")

        processing_time = int((time.time() - start_time) * 1000)

        return SuccessResponse(
            data=result,
            meta=MetaInfo(
                request_id=request_id,
                processing_time_ms=processing_time
            )
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get node detail: {str(e)}")


@router.post(
    "/from-all-documents",
    response_model=SuccessResponse[GenerateMindmapResponse],
    summary="전체 문서로 마인드맵 생성",
    description="시스템에 있는 모든 문서로부터 마인드맵을 생성합니다."
)
async def generate_mindmap_from_all(
    title: Optional[str] = Query(None, description="마인드맵 제목"),
    max_nodes: int = Query(50, ge=5, le=200, description="최대 노드 수"),
    focus_topic: Optional[str] = Query(None, description="집중할 주제"),
    language: str = Query("auto", description="언어 설정"),
    current_user: dict = Depends(get_current_user),
    service: MindmapService = Depends(get_service)
):
    """Generate mindmap from all documents in the system"""
    start_time = time.time()
    request_id = f"req_{uuid.uuid4().hex[:12]}"

    try:
        request = GenerateMindmapRequest(
            document_ids=[],  # 빈 배열 = 모든 문서
            title=title,
            max_nodes=max_nodes,
            focus_topic=focus_topic,
            language=language
        )

        mindmap = await service.generate_mindmap(request)

        processing_time = int((time.time() - start_time) * 1000)

        return SuccessResponse(
            data=GenerateMindmapResponse(
                mindmap=mindmap,
                message=f"Mindmap generated from all documents with {mindmap.node_count} nodes"
            ),
            meta=MetaInfo(
                request_id=request_id,
                processing_time_ms=processing_time
            )
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to generate mindmap: {str(e)}")
