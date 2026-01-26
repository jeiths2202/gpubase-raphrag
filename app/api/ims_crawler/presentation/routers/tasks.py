"""
Background Tasks API Router

Provides endpoints for background task management.
"""
from typing import Optional, List
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from app.api.ims_crawler.infrastructure.services import get_task_queue, BackgroundTaskQueue
from app.api.ims_crawler.infrastructure.services.background_task_queue import TaskStatus


router = APIRouter(prefix="/ims-tasks", tags=["IMS Background Tasks"])


# ============================================================================
# Response Models
# ============================================================================


class TaskStatusResponse(BaseModel):
    """Task status response"""
    task_id: str
    task_name: str
    status: str
    created_at: str
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    error: Optional[str] = None


class QueueStatsResponse(BaseModel):
    """Queue statistics response"""
    total_tasks: int = Field(..., description="Total tasks in queue")
    pending_tasks: int = Field(..., description="Tasks waiting to run")
    running_tasks: int = Field(..., description="Currently running tasks")
    completed_tasks: int = Field(..., description="Successfully completed tasks")
    failed_tasks: int = Field(..., description="Failed tasks")
    cancelled_tasks: int = Field(..., description="Cancelled tasks")
    max_concurrent: int = Field(..., description="Maximum concurrent tasks")
    queue_size: int = Field(..., description="Current queue size")


# ============================================================================
# API Endpoints
# ============================================================================


@router.get(
    "/",
    response_model=List[TaskStatusResponse],
    summary="List all tasks",
    description="""
    Get list of all background tasks with optional status filter.

    **Status values**: pending, running, completed, failed, cancelled
    """
)
async def list_tasks(
    status: Optional[str] = Query(None, description="Filter by task status"),
    task_queue: BackgroundTaskQueue = Depends(get_task_queue)
) -> List[TaskStatusResponse]:
    """
    List all background tasks

    Args:
        status: Optional status filter
        task_queue: Background task queue

    Returns:
        List of task status responses
    """
    # Validate status if provided
    status_filter = None
    if status:
        try:
            status_filter = TaskStatus(status.lower())
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid status '{status}'. Must be one of: pending, running, completed, failed, cancelled"
            )

    # Get tasks from queue
    tasks = task_queue.get_all_tasks(status_filter=status_filter)

    return [TaskStatusResponse(**task) for task in tasks]


@router.get(
    "/{task_id}",
    response_model=TaskStatusResponse,
    summary="Get task status",
    description="Get detailed status information for a specific task"
)
async def get_task_status(
    task_id: UUID,
    task_queue: BackgroundTaskQueue = Depends(get_task_queue)
) -> TaskStatusResponse:
    """
    Get task status by ID

    Args:
        task_id: Task ID
        task_queue: Background task queue

    Returns:
        Task status response

    Raises:
        HTTPException: If task not found
    """
    task_status = task_queue.get_task_status(task_id)

    if task_status is None:
        raise HTTPException(
            status_code=404,
            detail=f"Task {task_id} not found"
        )

    return TaskStatusResponse(**task_status)


@router.delete(
    "/{task_id}",
    summary="Cancel task",
    description="Cancel a running background task"
)
async def cancel_task(
    task_id: UUID,
    task_queue: BackgroundTaskQueue = Depends(get_task_queue)
) -> dict:
    """
    Cancel a running task

    Args:
        task_id: Task ID
        task_queue: Background task queue

    Returns:
        Cancellation result

    Raises:
        HTTPException: If task not found or cannot be cancelled
    """
    success = await task_queue.cancel_task(task_id)

    if not success:
        # Check if task exists
        task_status = task_queue.get_task_status(task_id)
        if task_status is None:
            raise HTTPException(
                status_code=404,
                detail=f"Task {task_id} not found"
            )

        # Task exists but cannot be cancelled (not running)
        raise HTTPException(
            status_code=400,
            detail=f"Task {task_id} cannot be cancelled (status: {task_status['status']})"
        )

    return {
        "success": True,
        "message": f"Task {task_id} cancelled successfully"
    }


@router.get(
    "/stats/queue",
    response_model=QueueStatsResponse,
    summary="Get queue statistics",
    description="Get comprehensive statistics about the background task queue"
)
async def get_queue_stats(
    task_queue: BackgroundTaskQueue = Depends(get_task_queue)
) -> QueueStatsResponse:
    """
    Get queue statistics

    Args:
        task_queue: Background task queue

    Returns:
        Queue statistics
    """
    stats = task_queue.get_queue_stats()

    return QueueStatsResponse(**stats)
