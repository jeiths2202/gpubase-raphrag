"""
IMS Crawl Jobs Router - SSE streaming for real-time progress

Endpoints for managing crawl jobs with Server-Sent Events (SSE) progress updates.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from typing import Optional, AsyncGenerator, List
from uuid import UUID
import json
import asyncio

from ....core.deps import get_current_user
from ...application.use_cases import CrawlJobsUseCase
from ...infrastructure.dependencies import get_crawl_jobs_use_case


router = APIRouter(prefix="/ims-jobs", tags=["IMS Crawler"])


# ============================================================================
# Request/Response Models
# ============================================================================

class CrawlJobCreateRequest(BaseModel):
    """Request model for creating a crawl job"""
    query: str = Field(..., min_length=1, description="Natural language query")
    include_attachments: bool = Field(default=True)
    include_related_issues: bool = Field(default=True)
    max_issues: Optional[int] = Field(default=None, description="Maximum issues to crawl (None = unlimited)")
    product_codes: Optional[List[str]] = Field(default=None, description="Product codes to filter search (e.g., ['128', '520'])")
    force_refresh: bool = Field(default=False, description="Skip cache and force new crawl")


class CrawlJobResponse(BaseModel):
    """Response model for crawl job status"""
    id: UUID
    user_id: UUID
    raw_query: str
    parsed_query: Optional[str]
    status: str
    current_step: str
    progress_percentage: int
    issues_found: int
    issues_crawled: int
    attachments_processed: int
    created_at: str
    started_at: Optional[str]
    completed_at: Optional[str]
    error_message: Optional[str]
    is_cached: bool = Field(default=False, description="True if results are from cache")
    result_issue_ids: Optional[List[str]] = Field(default=None, description="Issue IDs for cached results")


# ============================================================================
# Endpoints
# ============================================================================

@router.post("/", response_model=CrawlJobResponse, status_code=status.HTTP_201_CREATED)
async def create_crawl_job(
    request: CrawlJobCreateRequest,
    current_user: dict = Depends(get_current_user),
    use_case: CrawlJobsUseCase = Depends(get_crawl_jobs_use_case)
):
    """
    Create a new IMS crawl job or return cached results.

    If a completed crawl job with the same query exists within the cache period
    (configured by IMS_QUERY_CACHE_HOURS, default 24h), returns the cached job.
    Use `force_refresh=true` to skip cache and force a new crawl.

    The job is created in PENDING status and can be monitored via SSE stream.

    Returns job ID, initial status, and is_cached flag.
    - If is_cached=true, the job is already completed (no need to stream)
    - If is_cached=false, use GET /ims-jobs/{job_id}/stream to monitor real-time progress.
    """
    user_id = UUID(current_user["id"])

    try:
        # Create crawl job or get cached results
        job, is_cached = await use_case.create_crawl_job(
            user_id=user_id,
            search_query=request.query,
            max_results=request.max_issues if request.max_issues else 10000,  # Unlimited (use high number)
            download_attachments=request.include_attachments,
            crawl_related=request.include_related_issues,
            max_depth=2 if request.include_related_issues else 0,
            product_codes=request.product_codes,
            force_refresh=request.force_refresh
        )

        # Calculate progress for cached jobs
        progress = 0
        if is_cached and job.issues_found > 0:
            progress = int((job.issues_crawled / job.issues_found) * 100)

        # Return job response
        # For cached jobs, include result_issue_ids so frontend can fetch results directly
        cached_issue_ids = None
        if is_cached and job.result_issue_ids:
            cached_issue_ids = [str(iid) for iid in job.result_issue_ids]

        return CrawlJobResponse(
            id=job.id,
            user_id=job.user_id,
            raw_query=job.raw_query,
            parsed_query=job.parsed_query if is_cached else None,
            status=job.status.value,
            current_step=job.current_step if is_cached else "pending",
            progress_percentage=progress if is_cached else 0,
            issues_found=job.issues_found if is_cached else 0,
            issues_crawled=job.issues_crawled if is_cached else 0,
            attachments_processed=job.attachments_processed if is_cached else 0,
            created_at=job.created_at.isoformat(),
            started_at=job.started_at.isoformat() if job.started_at else None,
            completed_at=job.completed_at.isoformat() if job.completed_at else None,
            error_message=job.error_message if is_cached else None,
            is_cached=is_cached,
            result_issue_ids=cached_issue_ids
        )

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create crawl job: {str(e)}"
        )


@router.get("/{job_id}/stream")
async def stream_job_progress(
    job_id: UUID,
    current_user: dict = Depends(get_current_user),
    use_case: CrawlJobsUseCase = Depends(get_crawl_jobs_use_case)
):
    """
    Stream real-time progress updates for a crawl job using Server-Sent Events (SSE).

    **Event Format**:
    ```
    data: {"status": "crawling", "progress": 45, "step": "Processing issue IMS-123"}

    data: {"status": "completed", "progress": 100, "issues_crawled": 50}
    ```

    **Status Flow**:
    pending → authenticating → parsing_query → crawling → processing_attachments → embedding → completed/failed

    **Client Usage** (JavaScript):
    ```javascript
    const eventSource = new EventSource('/api/v1/ims-jobs/{job_id}/stream');
    eventSource.onmessage = (event) => {
        const progress = JSON.parse(event.data);
        console.log(progress);
    };
    ```
    """
    user_id = UUID(current_user["id"])

    async def event_generator() -> AsyncGenerator[str, None]:
        """
        Generate SSE events for job progress.

        Executes the crawl job and yields progress updates.
        """
        try:
            # Validate job belongs to current user
            job = await use_case.get_job_status(job_id)
            if job.user_id != user_id:
                error_data = {"event": "error", "message": "Unauthorized"}
                yield f"data: {json.dumps(error_data)}\n\n"
                return

            # Execute crawl job and stream progress
            async for progress_event in use_case.execute_crawl_job(job_id):
                yield f"data: {json.dumps(progress_event)}\n\n"

        except ValueError as e:
            error_data = {"event": "error", "message": str(e)}
            yield f"data: {json.dumps(error_data)}\n\n"
        except Exception as e:
            error_data = {"event": "error", "message": f"Internal error: {str(e)}"}
            yield f"data: {json.dumps(error_data)}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"  # Disable nginx buffering
        }
    )


@router.get("/{job_id}", response_model=CrawlJobResponse)
async def get_job_status(
    job_id: UUID,
    current_user: dict = Depends(get_current_user),
    use_case: CrawlJobsUseCase = Depends(get_crawl_jobs_use_case)
):
    """
    Get current status of a crawl job (non-streaming).

    Use this for polling-based clients that don't support SSE.
    """
    user_id = UUID(current_user["id"])

    try:
        # Get job status
        job = await use_case.get_job_status(job_id)

        # Validate job belongs to user
        if job.user_id != user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You don't have permission to access this job"
            )

        # Return job response
        progress = 0
        if job.issues_found > 0:
            progress = int((job.issues_crawled / job.issues_found) * 100)

        return CrawlJobResponse(
            id=job.id,
            user_id=job.user_id,
            raw_query=job.raw_query,
            parsed_query=job.parsed_query,
            status=job.status.value,
            current_step=job.current_step,
            progress_percentage=progress,
            issues_found=job.issues_found,
            issues_crawled=job.issues_crawled,
            attachments_processed=job.attachments_processed,
            created_at=job.created_at.isoformat(),
            started_at=job.started_at.isoformat() if job.started_at else None,
            completed_at=job.completed_at.isoformat() if job.completed_at else None,
            error_message=job.error_message,
            is_cached=False  # Status endpoint always returns current state, not cached
        )

    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job {job_id} not found"
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve job status: {str(e)}"
        )


@router.get("/", response_model=list[CrawlJobResponse])
async def list_jobs(
    limit: int = 20,
    current_user: dict = Depends(get_current_user)
):
    """
    List recent crawl jobs for the current user.

    Returns jobs sorted by created_at descending.
    """
    # TODO: Implement job listing
    # 1. Get user_id
    # 2. Query repository for user's jobs
    # 3. Return list

    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Job listing not yet implemented"
    )


@router.delete("/{job_id}", status_code=status.HTTP_204_NO_CONTENT)
async def cancel_job(
    job_id: UUID,
    current_user: dict = Depends(get_current_user),
    use_case: CrawlJobsUseCase = Depends(get_crawl_jobs_use_case)
):
    """
    Cancel a running crawl job.

    Sets job status to CANCELLED and stops background task.
    """
    user_id = UUID(current_user["id"])

    try:
        # Get job status
        job = await use_case.get_job_status(job_id)

        # Validate job belongs to user
        if job.user_id != user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You don't have permission to cancel this job"
            )

        # Cancel job
        await use_case.cancel_job(job_id)

    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job {job_id} not found"
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to cancel job: {str(e)}"
        )
