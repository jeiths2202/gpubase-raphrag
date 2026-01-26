"""
Projects/Notebooks API Router
프로젝트/노트북 관리 API
"""
import uuid
from datetime import datetime
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query

from ..models.base import SuccessResponse, PaginatedResponse, PaginationMeta, MetaInfo
from ..models.project import (
    ProjectVisibility,
    ProjectRole,
    TemplateCategory,
    CreateProjectRequest,
    UpdateProjectRequest,
    ShareProjectRequest,
    UpdateMemberRoleRequest,
    CloneProjectRequest,
    CreateTemplateRequest,
    AddDocumentToProjectRequest,
    RemoveDocumentFromProjectRequest,
    ProjectMember,
    ProjectStats,
    ProjectListItem,
    ProjectDetail,
    ProjectDocumentItem,
    ProjectTemplate,
    CloneProjectResponse,
    ShareProjectResponse,
    ProjectActivityItem,
)
from ..core.deps import get_current_user, get_project_service

router = APIRouter(prefix="/projects", tags=["Projects"])


# ==================== Project CRUD ====================

@router.post(
    "",
    response_model=SuccessResponse[ProjectDetail],
    summary="프로젝트 생성",
    description="새로운 프로젝트를 생성합니다."
)
async def create_project(
    request: CreateProjectRequest,
    current_user: dict = Depends(get_current_user),
    project_service = Depends(get_project_service)
):
    """Create a new project"""
    request_id = f"req_{uuid.uuid4().hex[:12]}"

    result = await project_service.create_project(
        name=request.name,
        description=request.description,
        visibility=request.visibility,
        color=request.color,
        icon=request.icon,
        tags=request.tags,
        template_id=request.template_id,
        user_id=current_user.get("user_id", "anonymous"),
        username=current_user.get("username", "Anonymous")
    )

    return SuccessResponse(
        data=ProjectDetail(**result),
        meta=MetaInfo(request_id=request_id)
    )


@router.get(
    "",
    response_model=PaginatedResponse[dict],
    summary="프로젝트 목록 조회",
    description="프로젝트 목록을 조회합니다."
)
async def list_projects(
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=100),
    visibility: Optional[ProjectVisibility] = Query(default=None),
    search: Optional[str] = Query(default=None, description="프로젝트명 검색"),
    include_shared: bool = Query(default=True, description="공유받은 프로젝트 포함"),
    current_user: dict = Depends(get_current_user),
    project_service = Depends(get_project_service)
):
    """List projects"""
    request_id = f"req_{uuid.uuid4().hex[:12]}"

    result = await project_service.list_projects(
        user_id=current_user.get("user_id"),
        page=page,
        limit=limit,
        visibility=visibility,
        search=search,
        include_shared=include_shared
    )

    return PaginatedResponse(
        data={"projects": result["projects"]},
        meta=MetaInfo(request_id=request_id),
        pagination=PaginationMeta(
            page=page,
            limit=limit,
            total_items=result["total"],
            total_pages=(result["total"] + limit - 1) // limit,
            has_next=page * limit < result["total"],
            has_prev=page > 1
        )
    )


@router.get(
    "/{project_id}",
    response_model=SuccessResponse[ProjectDetail],
    summary="프로젝트 상세 조회",
    description="프로젝트의 상세 정보를 조회합니다."
)
async def get_project(
    project_id: str,
    current_user: dict = Depends(get_current_user),
    project_service = Depends(get_project_service)
):
    """Get project details"""
    request_id = f"req_{uuid.uuid4().hex[:12]}"

    result = await project_service.get_project(project_id, current_user.get("user_id"))

    if not result:
        raise HTTPException(
            status_code=404,
            detail={"code": "PROJECT_NOT_FOUND", "message": "프로젝트를 찾을 수 없습니다."}
        )

    return SuccessResponse(
        data=ProjectDetail(**result),
        meta=MetaInfo(request_id=request_id)
    )


@router.put(
    "/{project_id}",
    response_model=SuccessResponse[ProjectDetail],
    summary="프로젝트 수정",
    description="프로젝트를 수정합니다."
)
async def update_project(
    project_id: str,
    request: UpdateProjectRequest,
    current_user: dict = Depends(get_current_user),
    project_service = Depends(get_project_service)
):
    """Update a project"""
    request_id = f"req_{uuid.uuid4().hex[:12]}"

    result = await project_service.update_project(
        project_id=project_id,
        user_id=current_user.get("user_id"),
        name=request.name,
        description=request.description,
        visibility=request.visibility,
        color=request.color,
        icon=request.icon,
        tags=request.tags
    )

    if not result:
        raise HTTPException(
            status_code=404,
            detail={"code": "PROJECT_NOT_FOUND", "message": "프로젝트를 찾을 수 없습니다."}
        )

    return SuccessResponse(
        data=ProjectDetail(**result),
        meta=MetaInfo(request_id=request_id)
    )


@router.delete(
    "/{project_id}",
    response_model=SuccessResponse[dict],
    summary="프로젝트 삭제",
    description="프로젝트와 관련 데이터를 삭제합니다."
)
async def delete_project(
    project_id: str,
    delete_documents: bool = Query(default=False, description="연결된 문서도 삭제"),
    current_user: dict = Depends(get_current_user),
    project_service = Depends(get_project_service)
):
    """Delete a project"""
    request_id = f"req_{uuid.uuid4().hex[:12]}"

    result = await project_service.delete_project(
        project_id=project_id,
        user_id=current_user.get("user_id"),
        delete_documents=delete_documents
    )

    if not result:
        raise HTTPException(
            status_code=404,
            detail={"code": "PROJECT_NOT_FOUND", "message": "프로젝트를 찾을 수 없습니다."}
        )

    return SuccessResponse(
        data={"project_id": project_id, "message": "프로젝트가 삭제되었습니다.", **result},
        meta=MetaInfo(request_id=request_id)
    )


# ==================== Documents in Project ====================

@router.get(
    "/{project_id}/documents",
    response_model=PaginatedResponse[dict],
    summary="프로젝트 문서 목록",
    description="프로젝트에 연결된 문서 목록을 조회합니다."
)
async def list_project_documents(
    project_id: str,
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=100),
    current_user: dict = Depends(get_current_user),
    project_service = Depends(get_project_service)
):
    """List documents in a project"""
    request_id = f"req_{uuid.uuid4().hex[:12]}"

    result = await project_service.list_project_documents(
        project_id=project_id,
        user_id=current_user.get("user_id"),
        page=page,
        limit=limit
    )

    if result is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "PROJECT_NOT_FOUND", "message": "프로젝트를 찾을 수 없습니다."}
        )

    return PaginatedResponse(
        data={"documents": result["documents"]},
        meta=MetaInfo(request_id=request_id),
        pagination=PaginationMeta(
            page=page,
            limit=limit,
            total_items=result["total"],
            total_pages=(result["total"] + limit - 1) // limit,
            has_next=page * limit < result["total"],
            has_prev=page > 1
        )
    )


@router.post(
    "/{project_id}/documents",
    response_model=SuccessResponse[dict],
    summary="프로젝트에 문서 추가",
    description="프로젝트에 문서를 추가합니다."
)
async def add_document_to_project(
    project_id: str,
    request: AddDocumentToProjectRequest,
    current_user: dict = Depends(get_current_user),
    project_service = Depends(get_project_service)
):
    """Add document to project"""
    request_id = f"req_{uuid.uuid4().hex[:12]}"

    result = await project_service.add_document(
        project_id=project_id,
        document_id=request.document_id,
        user_id=current_user.get("user_id")
    )

    if not result:
        raise HTTPException(
            status_code=404,
            detail={"code": "NOT_FOUND", "message": "프로젝트 또는 문서를 찾을 수 없습니다."}
        )

    return SuccessResponse(
        data={"message": "문서가 프로젝트에 추가되었습니다.", **result},
        meta=MetaInfo(request_id=request_id)
    )


@router.delete(
    "/{project_id}/documents/{document_id}",
    response_model=SuccessResponse[dict],
    summary="프로젝트에서 문서 제거",
    description="프로젝트에서 문서를 제거합니다."
)
async def remove_document_from_project(
    project_id: str,
    document_id: str,
    current_user: dict = Depends(get_current_user),
    project_service = Depends(get_project_service)
):
    """Remove document from project"""
    request_id = f"req_{uuid.uuid4().hex[:12]}"

    result = await project_service.remove_document(
        project_id=project_id,
        document_id=document_id,
        user_id=current_user.get("user_id")
    )

    if not result:
        raise HTTPException(
            status_code=404,
            detail={"code": "NOT_FOUND", "message": "프로젝트 또는 문서를 찾을 수 없습니다."}
        )

    return SuccessResponse(
        data={"message": "문서가 프로젝트에서 제거되었습니다."},
        meta=MetaInfo(request_id=request_id)
    )


# ==================== Sharing ====================

@router.post(
    "/{project_id}/share",
    response_model=SuccessResponse[ShareProjectResponse],
    summary="프로젝트 공유",
    description="프로젝트를 다른 사용자와 공유합니다."
)
async def share_project(
    project_id: str,
    request: ShareProjectRequest,
    current_user: dict = Depends(get_current_user),
    project_service = Depends(get_project_service)
):
    """Share project with other users"""
    request_id = f"req_{uuid.uuid4().hex[:12]}"

    result = await project_service.share_project(
        project_id=project_id,
        owner_id=current_user.get("user_id"),
        user_ids=request.user_ids,
        role=request.role,
        message=request.message
    )

    if not result:
        raise HTTPException(
            status_code=404,
            detail={"code": "PROJECT_NOT_FOUND", "message": "프로젝트를 찾을 수 없습니다."}
        )

    return SuccessResponse(
        data=ShareProjectResponse(**result),
        meta=MetaInfo(request_id=request_id)
    )


@router.get(
    "/{project_id}/members",
    response_model=SuccessResponse[dict],
    summary="프로젝트 멤버 목록",
    description="프로젝트 멤버 목록을 조회합니다."
)
async def list_project_members(
    project_id: str,
    current_user: dict = Depends(get_current_user),
    project_service = Depends(get_project_service)
):
    """List project members"""
    request_id = f"req_{uuid.uuid4().hex[:12]}"

    result = await project_service.list_members(
        project_id=project_id,
        user_id=current_user.get("user_id")
    )

    if result is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "PROJECT_NOT_FOUND", "message": "프로젝트를 찾을 수 없습니다."}
        )

    return SuccessResponse(
        data={"members": result},
        meta=MetaInfo(request_id=request_id)
    )


@router.put(
    "/{project_id}/members/{user_id}",
    response_model=SuccessResponse[dict],
    summary="멤버 역할 변경",
    description="프로젝트 멤버의 역할을 변경합니다."
)
async def update_member_role(
    project_id: str,
    user_id: str,
    request: UpdateMemberRoleRequest,
    current_user: dict = Depends(get_current_user),
    project_service = Depends(get_project_service)
):
    """Update member role"""
    request_id = f"req_{uuid.uuid4().hex[:12]}"

    result = await project_service.update_member_role(
        project_id=project_id,
        owner_id=current_user.get("user_id"),
        target_user_id=user_id,
        role=request.role
    )

    if not result:
        raise HTTPException(
            status_code=404,
            detail={"code": "NOT_FOUND", "message": "프로젝트 또는 멤버를 찾을 수 없습니다."}
        )

    return SuccessResponse(
        data={"message": "멤버 역할이 변경되었습니다.", **result},
        meta=MetaInfo(request_id=request_id)
    )


@router.delete(
    "/{project_id}/members/{user_id}",
    response_model=SuccessResponse[dict],
    summary="멤버 제거",
    description="프로젝트에서 멤버를 제거합니다."
)
async def remove_member(
    project_id: str,
    user_id: str,
    current_user: dict = Depends(get_current_user),
    project_service = Depends(get_project_service)
):
    """Remove member from project"""
    request_id = f"req_{uuid.uuid4().hex[:12]}"

    result = await project_service.remove_member(
        project_id=project_id,
        owner_id=current_user.get("user_id"),
        target_user_id=user_id
    )

    if not result:
        raise HTTPException(
            status_code=404,
            detail={"code": "NOT_FOUND", "message": "프로젝트 또는 멤버를 찾을 수 없습니다."}
        )

    return SuccessResponse(
        data={"message": "멤버가 제거되었습니다."},
        meta=MetaInfo(request_id=request_id)
    )


# ==================== Clone ====================

@router.post(
    "/{project_id}/clone",
    response_model=SuccessResponse[CloneProjectResponse],
    summary="프로젝트 복제",
    description="프로젝트를 복제합니다."
)
async def clone_project(
    project_id: str,
    request: CloneProjectRequest,
    current_user: dict = Depends(get_current_user),
    project_service = Depends(get_project_service)
):
    """Clone a project"""
    request_id = f"req_{uuid.uuid4().hex[:12]}"

    result = await project_service.clone_project(
        project_id=project_id,
        user_id=current_user.get("user_id"),
        username=current_user.get("username", "Anonymous"),
        new_name=request.new_name,
        include_documents=request.include_documents,
        include_notes=request.include_notes,
        include_mindmaps=request.include_mindmaps,
        include_conversations=request.include_conversations
    )

    if not result:
        raise HTTPException(
            status_code=404,
            detail={"code": "PROJECT_NOT_FOUND", "message": "프로젝트를 찾을 수 없습니다."}
        )

    return SuccessResponse(
        data=CloneProjectResponse(**result),
        meta=MetaInfo(request_id=request_id)
    )


# ==================== Templates ====================

@router.get(
    "/templates",
    response_model=SuccessResponse[dict],
    summary="템플릿 목록",
    description="사용 가능한 프로젝트 템플릿 목록을 조회합니다."
)
async def list_templates(
    category: Optional[TemplateCategory] = Query(default=None),
    include_public: bool = Query(default=True),
    current_user: dict = Depends(get_current_user),
    project_service = Depends(get_project_service)
):
    """List available project templates"""
    request_id = f"req_{uuid.uuid4().hex[:12]}"

    result = await project_service.list_templates(
        user_id=current_user.get("user_id"),
        category=category,
        include_public=include_public
    )

    return SuccessResponse(
        data={"templates": result},
        meta=MetaInfo(request_id=request_id)
    )


@router.post(
    "/{project_id}/save-as-template",
    response_model=SuccessResponse[ProjectTemplate],
    summary="템플릿으로 저장",
    description="프로젝트를 템플릿으로 저장합니다."
)
async def save_as_template(
    project_id: str,
    request: CreateTemplateRequest,
    current_user: dict = Depends(get_current_user),
    project_service = Depends(get_project_service)
):
    """Save project as template"""
    request_id = f"req_{uuid.uuid4().hex[:12]}"

    result = await project_service.create_template(
        project_id=project_id,
        user_id=current_user.get("user_id"),
        name=request.name,
        description=request.description,
        category=request.category,
        include_structure=request.include_structure,
        include_sample_notes=request.include_sample_notes,
        is_public=request.is_public
    )

    if not result:
        raise HTTPException(
            status_code=404,
            detail={"code": "PROJECT_NOT_FOUND", "message": "프로젝트를 찾을 수 없습니다."}
        )

    return SuccessResponse(
        data=ProjectTemplate(**result),
        meta=MetaInfo(request_id=request_id)
    )


# ==================== Activity ====================

@router.get(
    "/{project_id}/activity",
    response_model=SuccessResponse[dict],
    summary="프로젝트 활동 기록",
    description="프로젝트의 활동 기록을 조회합니다."
)
async def get_project_activity(
    project_id: str,
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=50, ge=1, le=100),
    current_user: dict = Depends(get_current_user),
    project_service = Depends(get_project_service)
):
    """Get project activity log"""
    request_id = f"req_{uuid.uuid4().hex[:12]}"

    result = await project_service.get_activity(
        project_id=project_id,
        user_id=current_user.get("user_id"),
        page=page,
        limit=limit
    )

    if result is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "PROJECT_NOT_FOUND", "message": "프로젝트를 찾을 수 없습니다."}
        )

    return SuccessResponse(
        data={"activities": result["activities"], "total": result["total"]},
        meta=MetaInfo(request_id=request_id)
    )
