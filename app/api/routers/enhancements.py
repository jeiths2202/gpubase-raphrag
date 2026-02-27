"""
Enhancement Request Router

API endpoints for the AI-Driven Enhancement & Improvement Management System.
"""
import logging
import uuid
import os
import aiofiles
from datetime import datetime, timezone
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, Query, status, UploadFile, File, Form
from fastapi.responses import StreamingResponse
import json

from ..core.deps import get_current_user
from ..models.base import SuccessResponse, PaginatedResponse, PaginationMeta, MetaInfo
from ..models.enhancement import (
    EnhancementStatus, EnhancementType, EnhancementPriority,
    EnhancementListItem, EnhancementDetail, CreateEnhancementRequest,
    UpdateEnhancementRequest, CreateEnhancementResponse, AnalysisResponse,
    ApproveRejectRequest, Comment, AttachmentInfo, EnhancementDashboardStats,
    ArchitectureProposal, ArchitectureResponse,
    ImplementationPlan, ImplementationResponse
)
from ..services.enhancement_service import (
    get_enhancement_service, EnhancementService,
    export_enhancement_to_knowledge, search_similar_enhancements
)
from ..services.enhancement_queue_manager import (
    get_queue_manager, EnhancementQueueManager,
    AgentType as QueueAgentType, TaskStatus
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/enhancements", tags=["Enhancements"])

# Upload directory for attachments
ATTACHMENT_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "..", "uploads", "enhancements")
os.makedirs(ATTACHMENT_DIR, exist_ok=True)


def get_service() -> EnhancementService:
    """Get the enhancement service."""
    return get_enhancement_service()


def get_queue() -> EnhancementQueueManager:
    """Get the enhancement queue manager."""
    return get_queue_manager()


# ============================================================================
# CRUD Endpoints
# ============================================================================

@router.post("", response_model=SuccessResponse[CreateEnhancementResponse], status_code=status.HTTP_201_CREATED)
async def create_enhancement(
    request: CreateEnhancementRequest,
    current_user: dict = Depends(get_current_user),
    service: EnhancementService = Depends(get_service)
):
    """
    Create a new enhancement request.

    Submit a feature request, bug report, or improvement suggestion.
    The AI will analyze the request and provide recommendations.
    """
    try:
        user_id = current_user.get("id", current_user.get("user_id", "unknown"))
        user_name = current_user.get("name", current_user.get("username", "Unknown User"))

        enhancement = await service.create(request, user_id, user_name)

        return SuccessResponse(
            data=CreateEnhancementResponse(
                id=enhancement.id,
                title=enhancement.title,
                status=enhancement.status,
                created_at=enhancement.created_at,
                message="Enhancement request submitted successfully. AI analysis will begin shortly."
            ),
            meta=MetaInfo(request_id=str(uuid.uuid4()))
        )
    except Exception as e:
        logger.error(f"Error creating enhancement: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("", response_model=PaginatedResponse[dict])
async def list_enhancements(
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=100),
    status_filter: Optional[EnhancementStatus] = Query(None, alias="status"),
    type_filter: Optional[EnhancementType] = Query(None, alias="type"),
    priority: Optional[EnhancementPriority] = None,
    author_id: Optional[str] = None,
    my_requests: bool = Query(default=False),
    search: Optional[str] = None,
    current_user: dict = Depends(get_current_user),
    service: EnhancementService = Depends(get_service)
):
    """
    List enhancement requests with filtering and pagination.

    Supports filtering by status, type, priority, and author.
    Use my_requests=true to see only your own requests.
    """
    try:
        # If my_requests is true, filter by current user
        if my_requests:
            author_id = current_user.get("id", current_user.get("user_id"))

        items, total = await service.list(
            page=page,
            limit=limit,
            status=status_filter,
            type_filter=type_filter,
            priority=priority,
            author_id=author_id,
            search=search
        )

        total_pages = (total + limit - 1) // limit

        return PaginatedResponse(
            data={"items": [item.model_dump() for item in items]},
            meta=MetaInfo(request_id=str(uuid.uuid4())),
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
        logger.error(f"Error listing enhancements: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/dashboard", response_model=SuccessResponse[EnhancementDashboardStats])
async def get_dashboard_stats(
    current_user: dict = Depends(get_current_user),
    service: EnhancementService = Depends(get_service)
):
    """
    Get dashboard statistics for enhancements.

    Returns aggregate counts by status, type, and priority.
    """
    try:
        stats = await service.get_dashboard_stats()
        return SuccessResponse(
            data=stats,
            meta=MetaInfo(request_id=str(uuid.uuid4()))
        )
    except Exception as e:
        logger.error(f"Error getting dashboard stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{enhancement_id}", response_model=SuccessResponse[EnhancementDetail])
async def get_enhancement(
    enhancement_id: str,
    current_user: dict = Depends(get_current_user),
    service: EnhancementService = Depends(get_service)
):
    """
    Get full details of an enhancement request.

    Includes AI analysis, architecture proposal, timeline, and comments.
    """
    try:
        enhancement = await service.get(enhancement_id)
        if not enhancement:
            raise HTTPException(status_code=404, detail="Enhancement not found")

        return SuccessResponse(
            data=enhancement,
            meta=MetaInfo(request_id=str(uuid.uuid4()))
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting enhancement: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/{enhancement_id}", response_model=SuccessResponse[EnhancementDetail])
async def update_enhancement(
    enhancement_id: str,
    request: UpdateEnhancementRequest,
    current_user: dict = Depends(get_current_user),
    service: EnhancementService = Depends(get_service)
):
    """
    Update an enhancement request.

    Only the author or admin can update an enhancement.
    """
    try:
        user_id = current_user.get("id", current_user.get("user_id", "unknown"))
        user_name = current_user.get("name", current_user.get("username", "Unknown User"))

        enhancement = await service.update(enhancement_id, request, user_id, user_name)
        if not enhancement:
            raise HTTPException(status_code=404, detail="Enhancement not found")

        return SuccessResponse(
            data=enhancement,
            meta=MetaInfo(request_id=str(uuid.uuid4()))
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating enhancement: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{enhancement_id}")
async def delete_enhancement(
    enhancement_id: str,
    current_user: dict = Depends(get_current_user),
    service: EnhancementService = Depends(get_service)
):
    """
    Delete an enhancement request.

    Only the author or admin can delete an enhancement.
    """
    try:
        user_id = current_user.get("id", current_user.get("user_id", "unknown"))

        success = await service.delete(enhancement_id, user_id)
        if not success:
            raise HTTPException(status_code=404, detail="Enhancement not found")

        return {"status": "deleted", "id": enhancement_id}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting enhancement: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# Status Transition Endpoints
# ============================================================================

@router.post("/{enhancement_id}/approve", response_model=SuccessResponse[EnhancementDetail])
async def approve_enhancement(
    enhancement_id: str,
    request: ApproveRejectRequest = None,
    current_user: dict = Depends(get_current_user),
    service: EnhancementService = Depends(get_service)
):
    """
    Approve an enhancement for implementation.

    Transitions status from ANALYZED to APPROVED.
    """
    try:
        user_id = current_user.get("id", current_user.get("user_id", "unknown"))
        user_name = current_user.get("name", current_user.get("username", "Unknown User"))

        enhancement = await service.update_status(
            enhancement_id,
            EnhancementStatus.APPROVED,
            user_id,
            user_name,
            "user",
            details={"reason": request.reason if request else None}
        )

        if not enhancement:
            raise HTTPException(status_code=404, detail="Enhancement not found")

        return SuccessResponse(
            data=enhancement,
            meta=MetaInfo(request_id=str(uuid.uuid4()))
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error approving enhancement: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{enhancement_id}/reject", response_model=SuccessResponse[EnhancementDetail])
async def reject_enhancement(
    enhancement_id: str,
    request: ApproveRejectRequest,
    current_user: dict = Depends(get_current_user),
    service: EnhancementService = Depends(get_service)
):
    """
    Reject an enhancement request.

    Requires a reason for rejection.
    """
    try:
        if not request or not request.reason:
            raise HTTPException(status_code=400, detail="Rejection reason is required")

        user_id = current_user.get("id", current_user.get("user_id", "unknown"))
        user_name = current_user.get("name", current_user.get("username", "Unknown User"))

        enhancement = await service.update_status(
            enhancement_id,
            EnhancementStatus.REJECTED,
            user_id,
            user_name,
            "user",
            details={"reason": request.reason}
        )

        if not enhancement:
            raise HTTPException(status_code=404, detail="Enhancement not found")

        return SuccessResponse(
            data=enhancement,
            meta=MetaInfo(request_id=str(uuid.uuid4()))
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error rejecting enhancement: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# AI Analysis Endpoints
# ============================================================================

@router.post("/{enhancement_id}/analyze", response_model=SuccessResponse[AnalysisResponse])
async def analyze_enhancement(
    enhancement_id: str,
    use_deep_agent: bool = Query(default=False, description="Use Deep Agents framework for analysis"),
    current_user: dict = Depends(get_current_user),
    service: EnhancementService = Depends(get_service)
):
    """
    Trigger AI analysis of an enhancement request.

    The Analyst Agent will classify, assess, and provide recommendations.

    Args:
        enhancement_id: ID of the enhancement to analyze
        use_deep_agent: If true, uses Deep Agents framework for analysis
    """
    try:
        enhancement = await service.get(enhancement_id)
        if not enhancement:
            raise HTTPException(status_code=404, detail="Enhancement not found")

        # Update status to analyzing
        user_id = current_user.get("id", current_user.get("user_id", "unknown"))
        user_name = current_user.get("name", current_user.get("username", "Unknown User"))

        await service.update_status(
            enhancement_id,
            EnhancementStatus.ANALYZING,
            user_id,
            user_name,
            "user"
        )

        # Collect attachment text if available
        attachments_text = None
        if enhancement.attachments:
            texts = [att.extracted_text for att in enhancement.attachments if att.extracted_text]
            if texts:
                attachments_text = "\n\n".join(texts)

        # Select agent based on use_deep_agent flag
        if use_deep_agent:
            from ..agents.agents.enhancement_analyst_deep_agent import get_deep_analyst_agent
            analyst = get_deep_analyst_agent()
            logger.info(f"[Enhancement] Using Deep Agent for analysis: {enhancement_id}")
        else:
            from ..agents.agents.enhancement_analyst_agent import get_analyst_agent
            analyst = get_analyst_agent()
            logger.info(f"[Enhancement] Using regular agent for analysis: {enhancement_id}")

        # Run analysis
        analysis = await analyst.analyze_enhancement(
            title=enhancement.title,
            description=enhancement.description,
            attachments_text=attachments_text
        )

        await service.add_analysis(enhancement_id, analysis)

        return SuccessResponse(
            data=AnalysisResponse(
                enhancement_id=enhancement_id,
                analysis=analysis,
                status=EnhancementStatus.ANALYZED,
                next_steps=["Review analysis", "Approve or request changes", "Start implementation"]
            ),
            meta=MetaInfo(request_id=str(uuid.uuid4()))
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error analyzing enhancement: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{enhancement_id}/analyze/stream")
async def stream_analyze_enhancement(
    enhancement_id: str,
    current_user: dict = Depends(get_current_user),
    service: EnhancementService = Depends(get_service)
):
    """
    Stream AI analysis of an enhancement request.

    Returns Server-Sent Events with analysis progress.
    """
    try:
        enhancement = await service.get(enhancement_id)
        if not enhancement:
            raise HTTPException(status_code=404, detail="Enhancement not found")

        async def generate():
            # Initial event
            yield f"data: {json.dumps({'type': 'start', 'message': 'Starting analysis...'})}\n\n"

            # Placeholder streaming - will be replaced with actual agent
            steps = [
                "Parsing enhancement request...",
                "Classifying request type...",
                "Assessing priority...",
                "Identifying affected components...",
                "Evaluating feasibility...",
                "Generating recommendations...",
                "Analysis complete."
            ]

            import asyncio
            for step in steps:
                yield f"data: {json.dumps({'type': 'progress', 'message': step})}\n\n"
                await asyncio.sleep(0.5)

            # Final analysis
            from ..models.enhancement import AIAnalysisResult, ComplexityLevel

            analysis = AIAnalysisResult(
                summary=f"Analysis of: {enhancement.title}",
                type_classification=enhancement.type or EnhancementType.IMPROVEMENT,
                priority_recommendation=enhancement.priority or EnhancementPriority.MEDIUM,
                affected_components=["Component analysis pending"],
                potential_risks=[],
                dependencies=[],
                estimated_complexity=ComplexityLevel.MEDIUM,
                feasibility_score=0.8,
                recommended_approach="Detailed analysis pending agent integration.",
                questions_for_submitter=[],
                analyzed_at=datetime.now(timezone.utc),
                agent_id="analyst-agent-placeholder"
            )

            await service.add_analysis(enhancement_id, analysis)

            yield f"data: {json.dumps({'type': 'complete', 'analysis': analysis.model_dump(mode='json')})}\n\n"

        return StreamingResponse(
            generate(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
            }
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error streaming analysis: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# Architecture Proposal Endpoints
# ============================================================================

@router.post("/{enhancement_id}/architecture", response_model=SuccessResponse[ArchitectureResponse])
async def design_architecture(
    enhancement_id: str,
    current_user: dict = Depends(get_current_user),
    service: EnhancementService = Depends(get_service)
):
    """
    Trigger architecture proposal design for an enhancement.

    The Architect Agent will analyze requirements and design a technical solution.
    Requires the enhancement to be in ANALYZED or APPROVED status.
    """
    try:
        enhancement = await service.get(enhancement_id)
        if not enhancement:
            raise HTTPException(status_code=404, detail="Enhancement not found")

        # Check if enhancement has been analyzed
        if enhancement.status not in [EnhancementStatus.ANALYZED, EnhancementStatus.APPROVED]:
            raise HTTPException(
                status_code=400,
                detail=f"Enhancement must be analyzed before architecture design. Current status: {enhancement.status}"
            )

        user_id = current_user.get("id", current_user.get("user_id", "unknown"))
        user_name = current_user.get("name", current_user.get("username", "Unknown User"))

        # Add timeline event for architecture design start
        from ..models.enhancement import TimelineEvent
        timeline_event = TimelineEvent(
            id=str(uuid.uuid4()),
            event_type="architecture_started",
            description="Architecture design initiated",
            actor_id=user_id,
            actor_name=user_name,
            actor_type="user"
        )
        await service.add_timeline_event(enhancement_id, timeline_event)

        # Trigger architect agent
        from ..agents.agents.enhancement_architect_agent import get_architect_agent

        architect = get_architect_agent()

        # Prepare AI analysis data if available
        ai_analysis_data = None
        if enhancement.ai_analysis:
            ai_analysis_data = {
                "type_classification": str(enhancement.ai_analysis.type_classification.value) if enhancement.ai_analysis.type_classification else None,
                "priority_recommendation": str(enhancement.ai_analysis.priority_recommendation.value) if enhancement.ai_analysis.priority_recommendation else None,
                "estimated_complexity": str(enhancement.ai_analysis.estimated_complexity.value) if enhancement.ai_analysis.estimated_complexity else None,
                "affected_components": enhancement.ai_analysis.affected_components,
                "recommended_approach": enhancement.ai_analysis.recommended_approach
            }

        # Run architecture design
        proposal = await architect.design_architecture(
            title=enhancement.title,
            description=enhancement.description,
            ai_analysis=ai_analysis_data
        )

        # Save the proposal
        await service.add_architecture_proposal(enhancement_id, proposal, user_id, user_name)

        return SuccessResponse(
            data=ArchitectureResponse(
                enhancement_id=enhancement_id,
                proposal=proposal,
                status=enhancement.status,
                next_steps=[
                    "Review architecture proposal",
                    "Approve design decisions",
                    "Proceed to implementation"
                ]
            ),
            meta=MetaInfo(request_id=str(uuid.uuid4()))
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error designing architecture: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{enhancement_id}/architecture/stream")
async def stream_architecture_design(
    enhancement_id: str,
    current_user: dict = Depends(get_current_user),
    service: EnhancementService = Depends(get_service)
):
    """
    Stream architecture proposal design.

    Returns Server-Sent Events with design progress.
    """
    try:
        enhancement = await service.get(enhancement_id)
        if not enhancement:
            raise HTTPException(status_code=404, detail="Enhancement not found")

        if enhancement.status not in [EnhancementStatus.ANALYZED, EnhancementStatus.APPROVED]:
            raise HTTPException(
                status_code=400,
                detail=f"Enhancement must be analyzed before architecture design. Current status: {enhancement.status}"
            )

        async def generate():
            yield f"data: {json.dumps({'type': 'start', 'message': 'Starting architecture design...'})}\n\n"

            steps = [
                "Analyzing enhancement requirements...",
                "Searching codebase for existing patterns...",
                "Identifying affected components...",
                "Designing technical approach...",
                "Defining file changes...",
                "Evaluating security considerations...",
                "Generating architecture proposal..."
            ]

            import asyncio
            for step in steps:
                yield f"data: {json.dumps({'type': 'progress', 'message': step})}\n\n"
                await asyncio.sleep(0.5)

            # Generate proposal
            from ..agents.agents.enhancement_architect_agent import get_architect_agent

            architect = get_architect_agent()

            ai_analysis_data = None
            if enhancement.ai_analysis:
                ai_analysis_data = {
                    "type_classification": str(enhancement.ai_analysis.type_classification.value) if enhancement.ai_analysis.type_classification else None,
                    "priority_recommendation": str(enhancement.ai_analysis.priority_recommendation.value) if enhancement.ai_analysis.priority_recommendation else None,
                    "estimated_complexity": str(enhancement.ai_analysis.estimated_complexity.value) if enhancement.ai_analysis.estimated_complexity else None,
                    "affected_components": enhancement.ai_analysis.affected_components,
                    "recommended_approach": enhancement.ai_analysis.recommended_approach
                }

            proposal = await architect.design_architecture(
                title=enhancement.title,
                description=enhancement.description,
                ai_analysis=ai_analysis_data
            )

            user_id = current_user.get("id", current_user.get("user_id", "unknown"))
            user_name = current_user.get("name", current_user.get("username", "Unknown User"))
            await service.add_architecture_proposal(enhancement_id, proposal, user_id, user_name)

            yield f"data: {json.dumps({'type': 'complete', 'proposal': proposal.model_dump(mode='json')})}\n\n"

        return StreamingResponse(
            generate(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
            }
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error streaming architecture design: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# Implementation Plan Endpoints
# ============================================================================

@router.post("/{enhancement_id}/implement", response_model=SuccessResponse[ImplementationResponse])
async def create_implementation_plan(
    enhancement_id: str,
    current_user: dict = Depends(get_current_user),
    service: EnhancementService = Depends(get_service)
):
    """
    Create an implementation plan for an approved enhancement.

    The Coder Agent will generate a detailed implementation plan with phases,
    tasks, test strategy, and rollback plan.
    Requires the enhancement to be in APPROVED status.
    """
    try:
        enhancement = await service.get(enhancement_id)
        if not enhancement:
            raise HTTPException(status_code=404, detail="Enhancement not found")

        # Check if enhancement is approved
        if enhancement.status != EnhancementStatus.APPROVED:
            raise HTTPException(
                status_code=400,
                detail=f"Enhancement must be approved before implementation planning. Current status: {enhancement.status}"
            )

        user_id = current_user.get("id", current_user.get("user_id", "unknown"))
        user_name = current_user.get("name", current_user.get("username", "Unknown User"))

        # Update status to implementing
        await service.update_status(
            enhancement_id,
            EnhancementStatus.IMPLEMENTING,
            user_id,
            user_name,
            "user"
        )

        # Add timeline event
        from ..models.enhancement import TimelineEvent
        timeline_event = TimelineEvent(
            id=str(uuid.uuid4()),
            event_type="implementation_started",
            description="Implementation planning initiated",
            actor_id=user_id,
            actor_name=user_name,
            actor_type="user"
        )
        await service.add_timeline_event(enhancement_id, timeline_event)

        # Trigger coder agent
        from ..agents.agents.enhancement_coder_agent import get_coder_agent

        coder = get_coder_agent()

        # Run implementation planning
        plan = await coder.create_implementation_plan(
            title=enhancement.title,
            description=enhancement.description,
            architecture_proposal=enhancement.architecture_proposal
        )

        # Save the plan
        await service.add_implementation_plan(enhancement_id, plan)

        return SuccessResponse(
            data=ImplementationResponse(
                enhancement_id=enhancement_id,
                plan=plan,
                status=EnhancementStatus.IMPLEMENTING,
                next_steps=[
                    "Review implementation plan",
                    "Assign developers to phases",
                    "Begin implementation",
                    "Submit for code review"
                ]
            ),
            meta=MetaInfo(request_id=str(uuid.uuid4()))
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating implementation plan: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{enhancement_id}/implement/stream")
async def stream_implementation_plan(
    enhancement_id: str,
    current_user: dict = Depends(get_current_user),
    service: EnhancementService = Depends(get_service)
):
    """
    Stream implementation plan creation.

    Returns Server-Sent Events with planning progress.
    """
    try:
        enhancement = await service.get(enhancement_id)
        if not enhancement:
            raise HTTPException(status_code=404, detail="Enhancement not found")

        if enhancement.status != EnhancementStatus.APPROVED:
            raise HTTPException(
                status_code=400,
                detail=f"Enhancement must be approved before implementation planning. Current status: {enhancement.status}"
            )

        async def generate():
            yield f"data: {json.dumps({'type': 'start', 'message': 'Starting implementation planning...'})}\n\n"

            steps = [
                "Reviewing enhancement requirements...",
                "Analyzing architecture proposal...",
                "Breaking down into phases...",
                "Defining implementation tasks...",
                "Creating test strategy...",
                "Generating rollback plan...",
                "Finalizing implementation plan..."
            ]

            import asyncio
            for step in steps:
                yield f"data: {json.dumps({'type': 'progress', 'message': step})}\n\n"
                await asyncio.sleep(0.5)

            # Generate plan
            from ..agents.agents.enhancement_coder_agent import get_coder_agent

            coder = get_coder_agent()

            plan = await coder.create_implementation_plan(
                title=enhancement.title,
                description=enhancement.description,
                architecture_proposal=enhancement.architecture_proposal
            )

            user_id = current_user.get("id", current_user.get("user_id", "unknown"))
            user_name = current_user.get("name", current_user.get("username", "Unknown User"))

            # Update status
            await service.update_status(
                enhancement_id,
                EnhancementStatus.IMPLEMENTING,
                user_id,
                user_name,
                "user"
            )

            await service.add_implementation_plan(enhancement_id, plan)

            yield f"data: {json.dumps({'type': 'complete', 'plan': plan.model_dump(mode='json')})}\n\n"

        return StreamingResponse(
            generate(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
            }
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error streaming implementation plan: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{enhancement_id}/code-review", response_model=SuccessResponse[EnhancementDetail])
async def submit_for_code_review(
    enhancement_id: str,
    current_user: dict = Depends(get_current_user),
    service: EnhancementService = Depends(get_service)
):
    """
    Submit an enhancement implementation for code review.

    Transitions status from IMPLEMENTING to CODE_REVIEW.
    """
    try:
        enhancement = await service.get(enhancement_id)
        if not enhancement:
            raise HTTPException(status_code=404, detail="Enhancement not found")

        if enhancement.status != EnhancementStatus.IMPLEMENTING:
            raise HTTPException(
                status_code=400,
                detail=f"Enhancement must be in implementing status. Current status: {enhancement.status}"
            )

        user_id = current_user.get("id", current_user.get("user_id", "unknown"))
        user_name = current_user.get("name", current_user.get("username", "Unknown User"))

        updated = await service.update_status(
            enhancement_id,
            EnhancementStatus.CODE_REVIEW,
            user_id,
            user_name,
            "user",
            details={"action": "Submitted for code review"}
        )

        return SuccessResponse(
            data=updated,
            meta=MetaInfo(request_id=str(uuid.uuid4()))
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error submitting for code review: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{enhancement_id}/complete-review", response_model=SuccessResponse[EnhancementDetail])
async def complete_code_review(
    enhancement_id: str,
    approved: bool = True,
    feedback: Optional[str] = None,
    current_user: dict = Depends(get_current_user),
    service: EnhancementService = Depends(get_service)
):
    """
    Complete code review for an enhancement.

    If approved, transitions to TESTING status.
    If not approved, transitions back to IMPLEMENTING.
    """
    try:
        enhancement = await service.get(enhancement_id)
        if not enhancement:
            raise HTTPException(status_code=404, detail="Enhancement not found")

        if enhancement.status != EnhancementStatus.CODE_REVIEW:
            raise HTTPException(
                status_code=400,
                detail=f"Enhancement must be in code review status. Current status: {enhancement.status}"
            )

        user_id = current_user.get("id", current_user.get("user_id", "unknown"))
        user_name = current_user.get("name", current_user.get("username", "Unknown User"))

        new_status = EnhancementStatus.TESTING if approved else EnhancementStatus.IMPLEMENTING
        action = "Code review approved" if approved else "Code review requested changes"

        updated = await service.update_status(
            enhancement_id,
            new_status,
            user_id,
            user_name,
            "user",
            details={"action": action, "feedback": feedback}
        )

        return SuccessResponse(
            data=updated,
            meta=MetaInfo(request_id=str(uuid.uuid4()))
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error completing code review: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# Comment Endpoints
# ============================================================================

@router.post("/{enhancement_id}/comments", response_model=SuccessResponse[Comment])
async def add_comment(
    enhancement_id: str,
    content: str = Form(...),
    current_user: dict = Depends(get_current_user),
    service: EnhancementService = Depends(get_service)
):
    """
    Add a comment to an enhancement request.
    """
    try:
        user_id = current_user.get("id", current_user.get("user_id", "unknown"))
        user_name = current_user.get("name", current_user.get("username", "Unknown User"))

        comment = await service.add_comment(
            enhancement_id,
            content,
            user_id,
            user_name
        )

        if not comment:
            raise HTTPException(status_code=404, detail="Enhancement not found")

        return SuccessResponse(
            data=comment,
            meta=MetaInfo(request_id=str(uuid.uuid4()))
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error adding comment: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# Attachment Endpoints
# ============================================================================

@router.post("/{enhancement_id}/attachments", response_model=SuccessResponse[AttachmentInfo])
async def upload_attachment(
    enhancement_id: str,
    file: UploadFile = File(...),
    current_user: dict = Depends(get_current_user),
    service: EnhancementService = Depends(get_service)
):
    """
    Upload an attachment to an enhancement request.

    Supports PDF, DOCX, images, and code files.
    """
    try:
        enhancement = await service.get(enhancement_id)
        if not enhancement:
            raise HTTPException(status_code=404, detail="Enhancement not found")

        # Generate unique filename
        attachment_id = str(uuid.uuid4())
        file_ext = os.path.splitext(file.filename)[1] if file.filename else ""
        storage_filename = f"{enhancement_id}_{attachment_id}{file_ext}"
        storage_path = os.path.join(ATTACHMENT_DIR, storage_filename)

        # Save file
        content = await file.read()
        async with aiofiles.open(storage_path, "wb") as f:
            await f.write(content)

        # Create attachment info
        attachment = AttachmentInfo(
            id=attachment_id,
            filename=storage_filename,
            original_name=file.filename or "unknown",
            file_size=len(content),
            mime_type=file.content_type or "application/octet-stream",
            storage_path=storage_path,
            uploaded_at=datetime.now(timezone.utc)
        )

        # TODO: Extract text from PDF/DOCX for AI analysis
        # attachment.extracted_text = extract_text(storage_path)

        user_id = current_user.get("id", current_user.get("user_id", "unknown"))
        user_name = current_user.get("name", current_user.get("username", "Unknown User"))

        await service.add_attachment(enhancement_id, attachment, user_id, user_name)

        return SuccessResponse(
            data=attachment,
            meta=MetaInfo(request_id=str(uuid.uuid4()))
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error uploading attachment: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{enhancement_id}/attachments", response_model=SuccessResponse[List[AttachmentInfo]])
async def list_attachments(
    enhancement_id: str,
    current_user: dict = Depends(get_current_user),
    service: EnhancementService = Depends(get_service)
):
    """
    List all attachments for an enhancement.
    """
    try:
        enhancement = await service.get(enhancement_id)
        if not enhancement:
            raise HTTPException(status_code=404, detail="Enhancement not found")

        return SuccessResponse(
            data=enhancement.attachments,
            meta=MetaInfo(request_id=str(uuid.uuid4()))
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error listing attachments: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# Testing & Verification Endpoints
# ============================================================================

@router.post("/{enhancement_id}/run-tests", response_model=SuccessResponse[dict])
async def run_tests(
    enhancement_id: str,
    current_user: dict = Depends(get_current_user),
    service: EnhancementService = Depends(get_service)
):
    """
    Run tests for an enhancement implementation.

    The QA Agent will execute tests based on the test strategy.
    Requires the enhancement to be in TESTING status.
    """
    try:
        enhancement = await service.get(enhancement_id)
        if not enhancement:
            raise HTTPException(status_code=404, detail="Enhancement not found")

        if enhancement.status != EnhancementStatus.TESTING:
            raise HTTPException(
                status_code=400,
                detail=f"Enhancement must be in testing status. Current status: {enhancement.status}"
            )

        if not enhancement.implementation_plan or not enhancement.implementation_plan.test_strategy:
            raise HTTPException(
                status_code=400,
                detail="No test strategy found. Create an implementation plan first."
            )

        user_id = current_user.get("id", current_user.get("user_id", "unknown"))
        user_name = current_user.get("name", current_user.get("username", "Unknown User"))

        # Add timeline event
        from ..models.enhancement import TimelineEvent
        timeline_event = TimelineEvent(
            id=str(uuid.uuid4()),
            event_type="tests_started",
            description="Test execution initiated",
            actor_id=user_id,
            actor_name=user_name,
            actor_type="user"
        )
        await service.add_timeline_event(enhancement_id, timeline_event)

        # Run tests using QA agent
        from ..agents.agents.enhancement_qa_agent import get_qa_agent

        qa_agent = get_qa_agent()
        test_report = await qa_agent.generate_test_report(
            enhancement.implementation_plan.test_strategy
        )

        # Add test results timeline event
        test_summary = test_report.get("summary", {})
        overall_status = test_summary.get("overall_status", "unknown")
        pass_rate = test_summary.get("pass_rate", 0)

        results_event = TimelineEvent(
            id=str(uuid.uuid4()),
            event_type="tests_completed",
            description=f"Test execution completed: {overall_status} ({pass_rate:.1f}% pass rate)",
            actor_id="qa-agent",
            actor_name="QA Agent",
            actor_type="agent",
            details=test_report
        )
        await service.add_timeline_event(enhancement_id, results_event)

        return SuccessResponse(
            data=test_report,
            meta=MetaInfo(request_id=str(uuid.uuid4()))
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error running tests: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{enhancement_id}/verify", response_model=SuccessResponse[dict])
async def verify_implementation(
    enhancement_id: str,
    current_user: dict = Depends(get_current_user),
    service: EnhancementService = Depends(get_service)
):
    """
    Verify an enhancement implementation.

    The QA Agent will analyze test results, code changes, and requirements
    to generate a comprehensive verification report.
    """
    try:
        enhancement = await service.get(enhancement_id)
        if not enhancement:
            raise HTTPException(status_code=404, detail="Enhancement not found")

        if enhancement.status not in [EnhancementStatus.TESTING, EnhancementStatus.CODE_REVIEW]:
            raise HTTPException(
                status_code=400,
                detail=f"Enhancement must be in testing or code review status. Current status: {enhancement.status}"
            )

        user_id = current_user.get("id", current_user.get("user_id", "unknown"))
        user_name = current_user.get("name", current_user.get("username", "Unknown User"))

        # Add timeline event
        from ..models.enhancement import TimelineEvent
        timeline_event = TimelineEvent(
            id=str(uuid.uuid4()),
            event_type="verification_started",
            description="Implementation verification initiated",
            actor_id=user_id,
            actor_name=user_name,
            actor_type="user"
        )
        await service.add_timeline_event(enhancement_id, timeline_event)

        # Run verification using QA agent
        from ..agents.agents.enhancement_qa_agent import get_qa_agent

        qa_agent = get_qa_agent()
        verification_report = await qa_agent.verify_implementation(
            title=enhancement.title,
            description=enhancement.description,
            analysis=enhancement.ai_analysis,
            implementation_plan=enhancement.implementation_plan
        )

        # Add verification results timeline event
        results_event = TimelineEvent(
            id=str(uuid.uuid4()),
            event_type="verification_completed",
            description=f"Verification completed: {verification_report.overall_status}",
            actor_id="qa-agent",
            actor_name="QA Agent",
            actor_type="agent",
            details=verification_report.to_dict()
        )
        await service.add_timeline_event(enhancement_id, results_event)

        return SuccessResponse(
            data=verification_report.to_dict(),
            meta=MetaInfo(request_id=str(uuid.uuid4()))
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error verifying implementation: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{enhancement_id}/mark-verified", response_model=SuccessResponse[EnhancementDetail])
async def mark_verified(
    enhancement_id: str,
    current_user: dict = Depends(get_current_user),
    service: EnhancementService = Depends(get_service)
):
    """
    Mark an enhancement as verified.

    Transitions status from TESTING to VERIFIED.
    """
    try:
        enhancement = await service.get(enhancement_id)
        if not enhancement:
            raise HTTPException(status_code=404, detail="Enhancement not found")

        if enhancement.status != EnhancementStatus.TESTING:
            raise HTTPException(
                status_code=400,
                detail=f"Enhancement must be in testing status. Current status: {enhancement.status}"
            )

        user_id = current_user.get("id", current_user.get("user_id", "unknown"))
        user_name = current_user.get("name", current_user.get("username", "Unknown User"))

        updated = await service.update_status(
            enhancement_id,
            EnhancementStatus.VERIFIED,
            user_id,
            user_name,
            "user",
            details={"action": "Enhancement implementation verified"}
        )

        return SuccessResponse(
            data=updated,
            meta=MetaInfo(request_id=str(uuid.uuid4()))
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error marking as verified: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{enhancement_id}/release", response_model=SuccessResponse[EnhancementDetail])
async def release_enhancement(
    enhancement_id: str,
    release_notes: Optional[str] = None,
    current_user: dict = Depends(get_current_user),
    service: EnhancementService = Depends(get_service)
):
    """
    Release an enhancement.

    Transitions status from VERIFIED to RELEASED.
    """
    try:
        enhancement = await service.get(enhancement_id)
        if not enhancement:
            raise HTTPException(status_code=404, detail="Enhancement not found")

        if enhancement.status != EnhancementStatus.VERIFIED:
            raise HTTPException(
                status_code=400,
                detail=f"Enhancement must be verified before release. Current status: {enhancement.status}"
            )

        user_id = current_user.get("id", current_user.get("user_id", "unknown"))
        user_name = current_user.get("name", current_user.get("username", "Unknown User"))

        updated = await service.update_status(
            enhancement_id,
            EnhancementStatus.RELEASED,
            user_id,
            user_name,
            "user",
            details={"action": "Enhancement released", "release_notes": release_notes}
        )

        return SuccessResponse(
            data=updated,
            meta=MetaInfo(request_id=str(uuid.uuid4()))
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error releasing enhancement: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{enhancement_id}/close", response_model=SuccessResponse[EnhancementDetail])
async def close_enhancement(
    enhancement_id: str,
    reason: Optional[str] = None,
    current_user: dict = Depends(get_current_user),
    service: EnhancementService = Depends(get_service)
):
    """
    Close an enhancement.

    Transitions status to CLOSED from RELEASED or any other terminal state.
    """
    try:
        enhancement = await service.get(enhancement_id)
        if not enhancement:
            raise HTTPException(status_code=404, detail="Enhancement not found")

        user_id = current_user.get("id", current_user.get("user_id", "unknown"))
        user_name = current_user.get("name", current_user.get("username", "Unknown User"))

        updated = await service.update_status(
            enhancement_id,
            EnhancementStatus.CLOSED,
            user_id,
            user_name,
            "user",
            details={"action": "Enhancement closed", "reason": reason}
        )

        return SuccessResponse(
            data=updated,
            meta=MetaInfo(request_id=str(uuid.uuid4()))
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error closing enhancement: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# Knowledge Integration Endpoints
# ============================================================================

@router.post("/{enhancement_id}/export-knowledge", response_model=SuccessResponse[dict])
async def export_to_knowledge(
    enhancement_id: str,
    current_user: dict = Depends(get_current_user),
    service: EnhancementService = Depends(get_service)
):
    """
    Export a completed enhancement as knowledge content.

    Generates structured knowledge from the enhancement data including
    problem description, AI analysis, architecture proposal, and implementation plan.
    Only available for RELEASED or CLOSED enhancements.
    """
    try:
        enhancement = await service.get(enhancement_id)
        if not enhancement:
            raise HTTPException(status_code=404, detail="Enhancement not found")

        if enhancement.status not in [EnhancementStatus.RELEASED, EnhancementStatus.CLOSED]:
            raise HTTPException(
                status_code=400,
                detail=f"Only released or closed enhancements can be exported. Current status: {enhancement.status}"
            )

        # Export to knowledge content
        knowledge_content = await export_enhancement_to_knowledge(enhancement)

        # Add timeline event
        from ..models.enhancement import TimelineEvent
        user_id = current_user.get("id", current_user.get("user_id", "unknown"))
        user_name = current_user.get("name", current_user.get("username", "Unknown User"))

        timeline_event = TimelineEvent(
            id=str(uuid.uuid4()),
            event_type="knowledge_exported",
            description="Enhancement exported to knowledge base",
            actor_id=user_id,
            actor_name=user_name,
            actor_type="user"
        )
        await service.add_timeline_event(enhancement_id, timeline_event)

        return SuccessResponse(
            data=knowledge_content,
            meta=MetaInfo(request_id=str(uuid.uuid4()))
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error exporting to knowledge: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/search/similar", response_model=SuccessResponse[List[dict]])
async def find_similar_enhancements(
    query: str = Query(..., description="Search query - title or description of the issue"),
    limit: int = Query(default=5, ge=1, le=20, description="Maximum number of results"),
    current_user: dict = Depends(get_current_user),
    service: EnhancementService = Depends(get_service)
):
    """
    Search for similar past enhancements.

    Finds completed enhancements that are similar to the provided query.
    Useful for finding existing solutions to similar problems.
    """
    try:
        similar = await search_similar_enhancements(query, service, limit)

        return SuccessResponse(
            data=similar,
            meta=MetaInfo(request_id=str(uuid.uuid4()))
        )
    except Exception as e:
        logger.error(f"Error searching similar enhancements: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/knowledge/recent", response_model=SuccessResponse[List[dict]])
async def get_recent_learnings(
    limit: int = Query(default=10, ge=1, le=50, description="Maximum number of results"),
    current_user: dict = Depends(get_current_user),
    service: EnhancementService = Depends(get_service)
):
    """
    Get recent enhancement learnings.

    Returns recently completed enhancements that can serve as learning resources.
    """
    try:
        all_enhancements = await service._list_all_enhancements()

        # Filter to completed enhancements only
        completed = [
            enh for enh in all_enhancements
            if enh.get("status") in ["verified", "released", "closed"]
        ]

        # Sort by updated_at descending
        completed.sort(key=lambda x: x.get("updated_at", ""), reverse=True)

        # Return top results with summary info
        results = []
        for enh in completed[:limit]:
            results.append({
                "id": enh["id"],
                "title": enh["title"],
                "type": enh.get("type"),
                "priority": enh.get("priority"),
                "status": enh["status"],
                "completed_at": enh.get("updated_at"),
                "summary": enh.get("description", "")[:200] + "..." if len(enh.get("description", "")) > 200 else enh.get("description", ""),
                "has_analysis": enh.get("ai_analyzed", False),
                "has_architecture": enh.get("architecture_proposal") is not None,
                "has_implementation": enh.get("implementation_plan") is not None
            })

        return SuccessResponse(
            data=results,
            meta=MetaInfo(request_id=str(uuid.uuid4()))
        )
    except Exception as e:
        logger.error(f"Error getting recent learnings: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# Queue Monitoring & Control Endpoints
# ============================================================================

@router.get("/queue/status", response_model=SuccessResponse[dict])
async def get_queue_status(
    current_user: dict = Depends(get_current_user),
    queue: EnhancementQueueManager = Depends(get_queue)
):
    """
    Get the current status of the enhancement agent queue.

    Returns information about:
    - All queued tasks waiting to be processed
    - Currently running tasks for each agent
    - Agent status (busy/idle, statistics)
    - Recent task history
    """
    try:
        status = await queue.get_queue_status()
        return SuccessResponse(
            data=status,
            meta=MetaInfo(request_id=str(uuid.uuid4()))
        )
    except Exception as e:
        logger.error(f"Error getting queue status: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/queue/agent/{agent_type}", response_model=SuccessResponse[dict])
async def get_agent_status(
    agent_type: str,
    current_user: dict = Depends(get_current_user),
    queue: EnhancementQueueManager = Depends(get_queue)
):
    """
    Get the status of a specific enhancement agent.

    Args:
        agent_type: Type of agent (analyst, architect, coder, qa)

    Returns agent status including current task, statistics, and last activity.
    """
    try:
        try:
            agent = QueueAgentType(agent_type.lower())
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid agent type: {agent_type}. Must be one of: analyst, architect, coder, qa"
            )

        status = await queue.get_agent_status(agent)
        return SuccessResponse(
            data=status,
            meta=MetaInfo(request_id=str(uuid.uuid4()))
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting agent status: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/queue/task/{task_id}", response_model=SuccessResponse[dict])
async def get_task_status(
    task_id: str,
    current_user: dict = Depends(get_current_user),
    queue: EnhancementQueueManager = Depends(get_queue)
):
    """
    Get the status of a specific queued or running task.

    Args:
        task_id: ID of the task

    Returns task details including status, position in queue, and timing information.
    """
    try:
        task = await queue.get_task_by_id(task_id)
        if not task:
            raise HTTPException(status_code=404, detail="Task not found")

        task_dict = task.to_dict()

        # Add queue position if queued
        if task.status == TaskStatus.QUEUED:
            position = await queue.get_queue_position(task_id)
            task_dict["queue_position"] = position

        return SuccessResponse(
            data=task_dict,
            meta=MetaInfo(request_id=str(uuid.uuid4()))
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting task status: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/queue/force-stop/{task_id}", response_model=SuccessResponse[dict])
async def force_stop_task(
    task_id: str,
    current_user: dict = Depends(get_current_user),
    queue: EnhancementQueueManager = Depends(get_queue)
):
    """
    Force stop a running task.

    This will request cancellation of the task. The actual agent must check
    for cancellation and handle it gracefully.

    Args:
        task_id: ID of the task to stop

    Note: Only admin users should be able to force stop tasks.
    """
    try:
        # Check if user is admin
        user_role = current_user.get("role", "user")
        if user_role != "admin":
            raise HTTPException(
                status_code=403,
                detail="Only administrators can force stop tasks"
            )

        success = await queue.force_stop_task(task_id)

        if not success:
            raise HTTPException(
                status_code=404,
                detail="Task not found or not currently running"
            )

        user_id = current_user.get("id", current_user.get("user_id", "unknown"))
        user_name = current_user.get("name", current_user.get("username", "Unknown User"))

        logger.info(f"Task {task_id} force stopped by {user_name} ({user_id})")

        return SuccessResponse(
            data={
                "task_id": task_id,
                "status": "cancelled",
                "message": "Task has been force stopped"
            },
            meta=MetaInfo(request_id=str(uuid.uuid4()))
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error force stopping task: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/queue/force-stop-agent/{agent_type}", response_model=SuccessResponse[dict])
async def force_stop_agent(
    agent_type: str,
    current_user: dict = Depends(get_current_user),
    queue: EnhancementQueueManager = Depends(get_queue)
):
    """
    Force stop the currently running task for a specific agent type.

    Args:
        agent_type: Type of agent (analyst, architect, coder, qa)

    Note: Only admin users should be able to force stop agents.
    """
    try:
        # Check if user is admin
        user_role = current_user.get("role", "user")
        if user_role != "admin":
            raise HTTPException(
                status_code=403,
                detail="Only administrators can force stop agents"
            )

        try:
            agent = QueueAgentType(agent_type.lower())
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid agent type: {agent_type}. Must be one of: analyst, architect, coder, qa"
            )

        success = await queue.force_stop_agent(agent)

        user_id = current_user.get("id", current_user.get("user_id", "unknown"))
        user_name = current_user.get("name", current_user.get("username", "Unknown User"))

        if success:
            logger.info(f"Agent {agent_type} force stopped by {user_name} ({user_id})")
            return SuccessResponse(
                data={
                    "agent_type": agent_type,
                    "status": "stopped",
                    "message": f"Agent {agent_type} has been force stopped"
                },
                meta=MetaInfo(request_id=str(uuid.uuid4()))
            )
        else:
            return SuccessResponse(
                data={
                    "agent_type": agent_type,
                    "status": "idle",
                    "message": f"Agent {agent_type} was not running"
                },
                meta=MetaInfo(request_id=str(uuid.uuid4()))
            )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error force stopping agent: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/queue/clear", response_model=SuccessResponse[dict])
async def clear_queue(
    agent_type: Optional[str] = Query(None, description="Optional: clear only tasks for specific agent type"),
    current_user: dict = Depends(get_current_user),
    queue: EnhancementQueueManager = Depends(get_queue)
):
    """
    Clear all queued tasks.

    Args:
        agent_type: Optional - if provided, only clear tasks for this agent type

    Note: Only admin users should be able to clear the queue.
    """
    try:
        # Check if user is admin
        user_role = current_user.get("role", "user")
        if user_role != "admin":
            raise HTTPException(
                status_code=403,
                detail="Only administrators can clear the queue"
            )

        target_agent = None
        if agent_type:
            try:
                target_agent = QueueAgentType(agent_type.lower())
            except ValueError:
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid agent type: {agent_type}. Must be one of: analyst, architect, coder, qa"
                )

        cleared_count = await queue.clear_queue(target_agent)

        user_id = current_user.get("id", current_user.get("user_id", "unknown"))
        user_name = current_user.get("name", current_user.get("username", "Unknown User"))

        logger.info(f"Queue cleared by {user_name} ({user_id}): {cleared_count} tasks removed")

        return SuccessResponse(
            data={
                "cleared_count": cleared_count,
                "agent_type": agent_type,
                "message": f"Cleared {cleared_count} queued task(s)"
            },
            meta=MetaInfo(request_id=str(uuid.uuid4()))
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error clearing queue: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/queue/enhancement/{enhancement_id}", response_model=SuccessResponse[List[dict]])
async def get_enhancement_tasks(
    enhancement_id: str,
    current_user: dict = Depends(get_current_user),
    queue: EnhancementQueueManager = Depends(get_queue)
):
    """
    Get all queued, running, and historical tasks for an enhancement.

    Args:
        enhancement_id: ID of the enhancement

    Returns all tasks associated with this enhancement.
    """
    try:
        tasks = await queue.get_enhancement_tasks(enhancement_id)
        return SuccessResponse(
            data=[task.to_dict() for task in tasks],
            meta=MetaInfo(request_id=str(uuid.uuid4()))
        )
    except Exception as e:
        logger.error(f"Error getting enhancement tasks: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# Enhancement Teams Endpoints (vLLM-based Agent Teams)
# ============================================================================

@router.post("/{enhancement_id}/teams/analyze/stream")
async def stream_team_analyze(
    enhancement_id: str,
    current_user: dict = Depends(get_current_user),
):
    """
    Pattern F: 팀 분석 SSE 스트림.

    ENHANCEMENT_TEAMS_PARALLEL_ANALYSIS=true → 3 관점 병렬 분석
    false → 단일 분석
    """
    from ..services.enhancement_teams.enhancement_orchestrator import get_enhancement_orchestrator

    orchestrator = get_enhancement_orchestrator()

    async def generate():
        async for event in orchestrator.stream_team_analyze(enhancement_id):
            yield event

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/{enhancement_id}/teams/architecture/stream")
async def stream_team_architecture(
    enhancement_id: str,
    current_user: dict = Depends(get_current_user),
):
    """
    Pattern G: 팀 아키텍처 SSE 스트림.

    ENHANCEMENT_TEAMS_CROSSVAL=true → 설계 + 검증 + 수정
    false → 설계만
    """
    from ..services.enhancement_teams.enhancement_orchestrator import get_enhancement_orchestrator

    orchestrator = get_enhancement_orchestrator()

    async def generate():
        async for event in orchestrator.stream_team_architecture(enhancement_id):
            yield event

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/{enhancement_id}/teams/pipeline/stream")
async def stream_team_pipeline(
    enhancement_id: str,
    current_user: dict = Depends(get_current_user),
):
    """
    Pattern H: 전체 파이프라인 SSE 스트림.

    분석 → 설계 → 구현 계획을 한 번에 실행.
    ENHANCEMENT_TEAMS_FULL_PIPELINE=true 필요.
    """
    from ..services.enhancement_teams.enhancement_orchestrator import get_enhancement_orchestrator
    from ..core.config import get_settings

    settings = get_settings()
    if not settings.ENHANCEMENT_TEAMS_FULL_PIPELINE:
        raise HTTPException(
            status_code=400,
            detail="Full pipeline is not enabled. Set ENHANCEMENT_TEAMS_FULL_PIPELINE=true",
        )

    orchestrator = get_enhancement_orchestrator()

    async def generate():
        async for event in orchestrator.stream_team_pipeline(enhancement_id):
            yield event

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
