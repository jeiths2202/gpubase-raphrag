"""
RAG Configuration & Governance API Router
Admin endpoints for managing RAG profiles, experiments, and metrics
"""
import uuid
from typing import Optional
from fastapi import APIRouter, Depends, Query, HTTPException, status
from uuid import UUID

from ..models.base import SuccessResponse, PaginatedResponse, PaginationMeta, MetaInfo
from ..models.rag_config import (
    RAGProfile, RAGProfileCreate, RAGProfileUpdate,
    RAGProfileSummary, RAGProfileListResponse,
    RAGExperiment, ExperimentCreate, ExperimentUpdate,
    ExperimentSummary, ExperimentListResponse, ExperimentStatus,
    ExperimentMetricsComparison, RAGConfigOverview
)
from ..core.deps import get_admin_user
from ..services.rag_config_service import get_rag_config_service

router = APIRouter(prefix="/rag-config", tags=["RAG Configuration"])


def get_request_id() -> str:
    """Generate unique request ID"""
    return f"req_{uuid.uuid4().hex[:12]}"


# =============================================================================
# Overview Endpoints
# =============================================================================

@router.get(
    "/overview",
    response_model=SuccessResponse[RAGConfigOverview],
    summary="RAG Configuration Overview",
    description="Get dashboard overview of RAG profiles and experiments"
)
async def get_overview(
    space_id: Optional[str] = Query(None, description="Space ID (null for global)"),
    admin_user: dict = Depends(get_admin_user),
    service = Depends(get_rag_config_service)
):
    """Get RAG configuration overview for admin dashboard"""
    request_id = get_request_id()

    try:
        overview = await service.get_overview(space_id)
        return SuccessResponse(
            data=overview,
            meta=MetaInfo(request_id=request_id)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"code": "RAG_CONFIG_ERROR", "message": str(e)}
        )


# =============================================================================
# RAG Profile Endpoints
# =============================================================================

@router.get(
    "/profiles",
    response_model=PaginatedResponse[RAGProfileListResponse],
    summary="List RAG Profiles",
    description="List all RAG profiles with pagination"
)
async def list_profiles(
    space_id: Optional[str] = Query(None, description="Space ID (null for global)"),
    include_inactive: bool = Query(False, description="Include inactive profiles"),
    page: int = Query(1, ge=1, description="Page number"),
    limit: int = Query(20, ge=1, le=100, description="Items per page"),
    admin_user: dict = Depends(get_admin_user),
    service = Depends(get_rag_config_service)
):
    """List RAG profiles for admin management"""
    request_id = get_request_id()

    profiles, total, active = await service.list_profiles(
        space_id=space_id,
        include_inactive=include_inactive,
        page=page,
        limit=limit
    )

    return PaginatedResponse(
        data=RAGProfileListResponse(
            profiles=profiles,
            total_count=total,
            active_count=active
        ),
        meta=MetaInfo(request_id=request_id),
        pagination=PaginationMeta(
            page=page,
            limit=limit,
            total_items=total,
            total_pages=(total + limit - 1) // limit if total > 0 else 1,
            has_next=page * limit < total,
            has_prev=page > 1
        )
    )


@router.get(
    "/profiles/{profile_id}",
    response_model=SuccessResponse[RAGProfile],
    summary="Get RAG Profile",
    description="Get a single RAG profile by ID"
)
async def get_profile(
    profile_id: UUID,
    admin_user: dict = Depends(get_admin_user),
    service = Depends(get_rag_config_service)
):
    """Get RAG profile details"""
    request_id = get_request_id()

    profile = await service.get_profile(profile_id)
    if not profile:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "PROFILE_NOT_FOUND", "message": "RAG profile not found"}
        )

    return SuccessResponse(
        data=profile,
        meta=MetaInfo(request_id=request_id)
    )


@router.post(
    "/profiles",
    response_model=SuccessResponse[RAGProfile],
    status_code=status.HTTP_201_CREATED,
    summary="Create RAG Profile",
    description="Create a new RAG profile with auto-incremented embedding version"
)
async def create_profile(
    data: RAGProfileCreate,
    admin_user: dict = Depends(get_admin_user),
    service = Depends(get_rag_config_service)
):
    """
    Create a new RAG profile.

    **Note**: Creating a profile automatically increments the embedding version.
    Existing documents will continue using the previous version until re-embedded.
    """
    request_id = get_request_id()

    try:
        profile = await service.create_profile(data, UUID(admin_user["id"]))
        return SuccessResponse(
            data=profile,
            meta=MetaInfo(request_id=request_id)
        )
    except Exception as e:
        if "unique" in str(e).lower():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={"code": "PROFILE_NAME_EXISTS", "message": "Profile name already exists in this space"}
            )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"code": "PROFILE_CREATE_ERROR", "message": str(e)}
        )


@router.patch(
    "/profiles/{profile_id}",
    response_model=SuccessResponse[RAGProfile],
    summary="Update RAG Profile",
    description="Update RAG profile settings. Embedding-related changes create a new version."
)
async def update_profile(
    profile_id: UUID,
    data: RAGProfileUpdate,
    admin_user: dict = Depends(get_admin_user),
    service = Depends(get_rag_config_service)
):
    """
    Update RAG profile settings.

    **Important**: Changing chunking or embedding settings will increment the
    embedding version. Existing embeddings remain valid but new documents will
    use the updated settings.
    """
    request_id = get_request_id()

    profile = await service.update_profile(profile_id, data)
    if not profile:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "PROFILE_NOT_FOUND", "message": "RAG profile not found"}
        )

    return SuccessResponse(
        data=profile,
        meta=MetaInfo(request_id=request_id)
    )


@router.delete(
    "/profiles/{profile_id}",
    response_model=SuccessResponse[dict],
    summary="Delete RAG Profile",
    description="Soft delete a RAG profile (sets is_active=false)"
)
async def delete_profile(
    profile_id: UUID,
    admin_user: dict = Depends(get_admin_user),
    service = Depends(get_rag_config_service)
):
    """Delete (deactivate) a RAG profile"""
    request_id = get_request_id()

    try:
        success = await service.delete_profile(profile_id)
        if not success:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"code": "PROFILE_NOT_FOUND", "message": "RAG profile not found"}
            )

        return SuccessResponse(
            data={"message": "Profile deleted successfully", "profile_id": str(profile_id)},
            meta=MetaInfo(request_id=request_id)
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "PROFILE_IN_USE", "message": str(e)}
        )


@router.post(
    "/profiles/{profile_id}/clone",
    response_model=SuccessResponse[RAGProfile],
    status_code=status.HTTP_201_CREATED,
    summary="Clone RAG Profile",
    description="Create a copy of an existing profile with a new name"
)
async def clone_profile(
    profile_id: UUID,
    new_name: str = Query(..., min_length=1, max_length=255),
    admin_user: dict = Depends(get_admin_user),
    service = Depends(get_rag_config_service)
):
    """Clone an existing RAG profile with a new name"""
    request_id = get_request_id()

    # Get original profile
    original = await service.get_profile(profile_id)
    if not original:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "PROFILE_NOT_FOUND", "message": "Source profile not found"}
        )

    # Create clone
    clone_data = RAGProfileCreate(
        name=new_name,
        description=f"Clone of {original.name}",
        space_id=original.space_id,
        project_id=original.project_id,
        chunking=original.chunking,
        embedding=original.embedding,
        image_ingestion=original.image_ingestion,
        retrieval=original.retrieval,
        generation=original.generation,
        metadata=original.metadata
    )

    try:
        profile = await service.create_profile(clone_data, UUID(admin_user["id"]))
        return SuccessResponse(
            data=profile,
            meta=MetaInfo(request_id=request_id)
        )
    except Exception as e:
        if "unique" in str(e).lower():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={"code": "PROFILE_NAME_EXISTS", "message": "Profile name already exists"}
            )
        raise


@router.post(
    "/profiles/{profile_id}/activate",
    response_model=SuccessResponse[RAGProfile],
    summary="Activate RAG Profile",
    description="Set a profile as the primary active profile for its space"
)
async def activate_profile(
    profile_id: UUID,
    traffic_percentage: int = Query(100, ge=0, le=100),
    admin_user: dict = Depends(get_admin_user),
    service = Depends(get_rag_config_service)
):
    """Activate a RAG profile with specified traffic percentage"""
    request_id = get_request_id()

    update_data = RAGProfileUpdate(
        is_active=True,
        traffic_percentage=traffic_percentage
    )

    profile = await service.update_profile(profile_id, update_data)
    if not profile:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "PROFILE_NOT_FOUND", "message": "RAG profile not found"}
        )

    return SuccessResponse(
        data=profile,
        meta=MetaInfo(request_id=request_id)
    )


# =============================================================================
# A/B Experiment Endpoints
# =============================================================================

@router.get(
    "/experiments",
    response_model=PaginatedResponse[ExperimentListResponse],
    summary="List Experiments",
    description="List A/B testing experiments"
)
async def list_experiments(
    space_id: Optional[str] = Query(None),
    status_filter: Optional[ExperimentStatus] = Query(None, alias="status"),
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    admin_user: dict = Depends(get_admin_user),
    service = Depends(get_rag_config_service)
):
    """List A/B experiments for admin management"""
    request_id = get_request_id()

    experiments, total, active = await service.list_experiments(
        space_id=space_id,
        status=status_filter,
        page=page,
        limit=limit
    )

    return PaginatedResponse(
        data=ExperimentListResponse(
            experiments=experiments,
            total_count=total,
            active_count=active
        ),
        meta=MetaInfo(request_id=request_id),
        pagination=PaginationMeta(
            page=page,
            limit=limit,
            total_items=total,
            total_pages=(total + limit - 1) // limit if total > 0 else 1,
            has_next=page * limit < total,
            has_prev=page > 1
        )
    )


@router.post(
    "/experiments",
    response_model=SuccessResponse[RAGExperiment],
    status_code=status.HTTP_201_CREATED,
    summary="Create Experiment",
    description="Create a new A/B testing experiment"
)
async def create_experiment(
    data: ExperimentCreate,
    admin_user: dict = Depends(get_admin_user),
    service = Depends(get_rag_config_service)
):
    """
    Create a new A/B testing experiment.

    **Requirements**:
    - Variant traffic ratios must sum to 1.0 (100%)
    - Baseline profile must exist and be active
    - All variant profiles must exist
    """
    request_id = get_request_id()

    try:
        experiment = await service.create_experiment(data, UUID(admin_user["id"]))
        return SuccessResponse(
            data=experiment,
            meta=MetaInfo(request_id=request_id)
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "INVALID_EXPERIMENT", "message": str(e)}
        )


@router.patch(
    "/experiments/{experiment_id}",
    response_model=SuccessResponse[RAGExperiment],
    summary="Update Experiment",
    description="Update experiment status or configuration"
)
async def update_experiment(
    experiment_id: UUID,
    data: ExperimentUpdate,
    admin_user: dict = Depends(get_admin_user),
    service = Depends(get_rag_config_service)
):
    """
    Update experiment configuration.

    **Status transitions**:
    - draft → active: Starts the experiment
    - active → paused: Pauses traffic routing
    - active → completed: Ends the experiment
    - paused → active: Resumes the experiment
    """
    request_id = get_request_id()

    try:
        experiment = await service.update_experiment(experiment_id, data)
        if not experiment:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"code": "EXPERIMENT_NOT_FOUND", "message": "Experiment not found"}
            )

        return SuccessResponse(
            data=experiment,
            meta=MetaInfo(request_id=request_id)
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "INVALID_UPDATE", "message": str(e)}
        )


@router.post(
    "/experiments/{experiment_id}/start",
    response_model=SuccessResponse[RAGExperiment],
    summary="Start Experiment",
    description="Start an A/B experiment (changes status to active)"
)
async def start_experiment(
    experiment_id: UUID,
    admin_user: dict = Depends(get_admin_user),
    service = Depends(get_rag_config_service)
):
    """Start an A/B experiment"""
    request_id = get_request_id()

    experiment = await service.update_experiment(
        experiment_id,
        ExperimentUpdate(status=ExperimentStatus.ACTIVE)
    )

    if not experiment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "EXPERIMENT_NOT_FOUND", "message": "Experiment not found"}
        )

    return SuccessResponse(
        data=experiment,
        meta=MetaInfo(request_id=request_id)
    )


@router.post(
    "/experiments/{experiment_id}/stop",
    response_model=SuccessResponse[RAGExperiment],
    summary="Stop Experiment",
    description="Stop an A/B experiment (changes status to completed)"
)
async def stop_experiment(
    experiment_id: UUID,
    admin_user: dict = Depends(get_admin_user),
    service = Depends(get_rag_config_service)
):
    """Stop and complete an A/B experiment"""
    request_id = get_request_id()

    experiment = await service.update_experiment(
        experiment_id,
        ExperimentUpdate(status=ExperimentStatus.COMPLETED)
    )

    if not experiment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "EXPERIMENT_NOT_FOUND", "message": "Experiment not found"}
        )

    return SuccessResponse(
        data=experiment,
        meta=MetaInfo(request_id=request_id)
    )


@router.get(
    "/experiments/{experiment_id}/metrics",
    response_model=SuccessResponse[ExperimentMetricsComparison],
    summary="Get Experiment Metrics",
    description="Get aggregated metrics comparison for an experiment"
)
async def get_experiment_metrics(
    experiment_id: UUID,
    days: int = Query(7, ge=1, le=90, description="Analysis period in days"),
    admin_user: dict = Depends(get_admin_user),
    service = Depends(get_rag_config_service)
):
    """Get metrics comparison for A/B experiment"""
    request_id = get_request_id()

    metrics = await service.get_experiment_metrics(experiment_id, days)
    if not metrics:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "EXPERIMENT_NOT_FOUND", "message": "Experiment not found"}
        )

    return SuccessResponse(
        data=metrics,
        meta=MetaInfo(request_id=request_id)
    )


# =============================================================================
# Active Profile Endpoint (for query routing)
# =============================================================================

@router.get(
    "/active-profile",
    response_model=SuccessResponse[RAGProfile],
    summary="Get Active Profile",
    description="Get the currently active profile for query routing (includes A/B test selection)"
)
async def get_active_profile(
    space_id: Optional[str] = Query(None),
    project_id: Optional[str] = Query(None),
    user_id: Optional[str] = Query(None, description="User ID for deterministic A/B routing"),
    admin_user: dict = Depends(get_admin_user),
    service = Depends(get_rag_config_service)
):
    """
    Get the active RAG profile for query routing.

    If an A/B experiment is active, returns the selected variant based on
    traffic allocation. User ID enables deterministic selection (same user
    always gets the same variant).
    """
    request_id = get_request_id()

    profile = await service.get_active_profile(
        space_id=space_id,
        project_id=project_id,
        user_id=user_id
    )

    if not profile:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "NO_ACTIVE_PROFILE", "message": "No active RAG profile found"}
        )

    return SuccessResponse(
        data=profile,
        meta=MetaInfo(request_id=request_id)
    )
