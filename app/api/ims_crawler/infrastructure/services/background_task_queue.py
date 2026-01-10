"""
Background task queue for async job processing
Simple asyncio-based task queue without external dependencies
"""
import asyncio
import logging

logger = logging.getLogger(__name__)
from typing import Dict, Callable, Any, Optional
from datetime import datetime
from uuid import UUID, uuid4
from enum import Enum


class TaskStatus(Enum):
    """Task status enumeration"""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class BackgroundTask:
    """Background task representation"""

    def __init__(
        self,
        task_id: UUID,
        task_name: str,
        task_func: Callable,
        args: tuple = (),
        kwargs: dict = None
    ):
        self.task_id = task_id
        self.task_name = task_name
        self.task_func = task_func
        self.args = args
        self.kwargs = kwargs or {}
        self.status = TaskStatus.PENDING
        self.created_at = datetime.utcnow()
        self.started_at: Optional[datetime] = None
        self.completed_at: Optional[datetime] = None
        self.error: Optional[str] = None
        self.result: Any = None
        self._task: Optional[asyncio.Task] = None

    def to_dict(self) -> dict:
        """Convert to dictionary representation"""
        return {
            'task_id': str(self.task_id),
            'task_name': self.task_name,
            'status': self.status.value,
            'created_at': self.created_at.isoformat(),
            'started_at': self.started_at.isoformat() if self.started_at else None,
            'completed_at': self.completed_at.isoformat() if self.completed_at else None,
            'error': self.error
        }


class BackgroundTaskQueue:
    """
    Simple background task queue using asyncio

    Features:
    - Async task execution
    - Task status tracking
    - Concurrent task limit
    - Task cancellation
    - Task result retrieval
    """

    def __init__(self, max_concurrent_tasks: int = 3):
        """
        Initialize background task queue

        Args:
            max_concurrent_tasks: Maximum concurrent tasks
        """
        self.max_concurrent_tasks = max_concurrent_tasks
        self.tasks: Dict[UUID, BackgroundTask] = {}
        self.queue: asyncio.Queue = asyncio.Queue()
        self.running_tasks: set = set()
        self._worker_task: Optional[asyncio.Task] = None
        self._running = False

    async def start(self):
        """Start the task queue worker"""
        if self._running:
            return

        self._running = True
        self._worker_task = asyncio.create_task(self._worker())
        logger.info(f"[OK] Background task queue started (max concurrent: {self.max_concurrent_tasks})")

    async def stop(self):
        """Stop the task queue worker"""
        self._running = False

        # Cancel all running tasks
        for task_id in list(self.running_tasks):
            await self.cancel_task(task_id)

        # Wait for worker to finish
        if self._worker_task:
            self._worker_task.cancel()
            try:
                await self._worker_task
            except asyncio.CancelledError:
                pass

        logger.info("[OK] Background task queue stopped")

    async def submit_task(
        self,
        task_name: str,
        task_func: Callable,
        *args,
        **kwargs
    ) -> UUID:
        """
        Submit a task to the queue

        Args:
            task_name: Task name for tracking
            task_func: Async function to execute
            *args: Positional arguments
            **kwargs: Keyword arguments

        Returns:
            Task ID
        """
        task_id = uuid4()

        task = BackgroundTask(
            task_id=task_id,
            task_name=task_name,
            task_func=task_func,
            args=args,
            kwargs=kwargs
        )

        self.tasks[task_id] = task
        await self.queue.put(task_id)

        return task_id

    async def _worker(self):
        """Background worker that processes tasks from queue"""
        while self._running:
            try:
                # Wait for task with timeout
                try:
                    task_id = await asyncio.wait_for(
                        self.queue.get(),
                        timeout=1.0
                    )
                except asyncio.TimeoutError:
                    continue

                # Check if we have capacity
                while len(self.running_tasks) >= self.max_concurrent_tasks:
                    await asyncio.sleep(0.5)

                # Execute task
                task = self.tasks.get(task_id)
                if task:
                    asyncio.create_task(self._execute_task(task))

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Worker error: {e}")

    async def _execute_task(self, task: BackgroundTask):
        """Execute a single task"""
        task_id = task.task_id
        self.running_tasks.add(task_id)

        try:
            task.status = TaskStatus.RUNNING
            task.started_at = datetime.utcnow()

            # Execute the task function
            result = await task.task_func(*task.args, **task.kwargs)

            task.status = TaskStatus.COMPLETED
            task.completed_at = datetime.utcnow()
            task.result = result

        except asyncio.CancelledError:
            task.status = TaskStatus.CANCELLED
            task.completed_at = datetime.utcnow()
            task.error = "Task was cancelled"

        except Exception as e:
            task.status = TaskStatus.FAILED
            task.completed_at = datetime.utcnow()
            task.error = str(e)
            logger.error(f"Task {task.task_name} ({task_id}) failed: {e}")

        finally:
            self.running_tasks.discard(task_id)

    async def cancel_task(self, task_id: UUID) -> bool:
        """
        Cancel a running task

        Args:
            task_id: Task ID

        Returns:
            True if cancelled successfully
        """
        task = self.tasks.get(task_id)
        if not task:
            return False

        if task.status == TaskStatus.RUNNING and task._task:
            task._task.cancel()
            return True

        return False

    def get_task_status(self, task_id: UUID) -> Optional[dict]:
        """
        Get task status

        Args:
            task_id: Task ID

        Returns:
            Task status dict or None
        """
        task = self.tasks.get(task_id)
        if not task:
            return None

        return task.to_dict()

    def get_all_tasks(self, status_filter: Optional[TaskStatus] = None) -> list:
        """
        Get all tasks

        Args:
            status_filter: Optional status filter

        Returns:
            List of task status dicts
        """
        tasks = self.tasks.values()

        if status_filter:
            tasks = [t for t in tasks if t.status == status_filter]

        return [t.to_dict() for t in tasks]

    def get_queue_stats(self) -> dict:
        """Get queue statistics"""
        return {
            'total_tasks': len(self.tasks),
            'pending_tasks': sum(1 for t in self.tasks.values() if t.status == TaskStatus.PENDING),
            'running_tasks': len(self.running_tasks),
            'completed_tasks': sum(1 for t in self.tasks.values() if t.status == TaskStatus.COMPLETED),
            'failed_tasks': sum(1 for t in self.tasks.values() if t.status == TaskStatus.FAILED),
            'cancelled_tasks': sum(1 for t in self.tasks.values() if t.status == TaskStatus.CANCELLED),
            'max_concurrent': self.max_concurrent_tasks,
            'queue_size': self.queue.qsize()
        }

    async def wait_for_task(self, task_id: UUID, timeout: Optional[float] = None) -> Any:
        """
        Wait for task completion and return result

        Args:
            task_id: Task ID
            timeout: Optional timeout in seconds

        Returns:
            Task result

        Raises:
            TimeoutError: If timeout exceeded
            ValueError: If task not found
            RuntimeError: If task failed
        """
        task = self.tasks.get(task_id)
        if not task:
            raise ValueError(f"Task {task_id} not found")

        start_time = asyncio.get_event_loop().time()

        while True:
            if task.status == TaskStatus.COMPLETED:
                return task.result

            if task.status == TaskStatus.FAILED:
                raise RuntimeError(f"Task failed: {task.error}")

            if task.status == TaskStatus.CANCELLED:
                raise RuntimeError("Task was cancelled")

            if timeout and (asyncio.get_event_loop().time() - start_time) > timeout:
                raise TimeoutError(f"Task {task_id} timed out after {timeout}s")

            await asyncio.sleep(0.1)


# Global task queue instance
_task_queue: Optional[BackgroundTaskQueue] = None


def get_task_queue(max_concurrent: int = 3) -> BackgroundTaskQueue:
    """
    Get or create global task queue

    Args:
        max_concurrent: Maximum concurrent tasks

    Returns:
        Background task queue instance
    """
    global _task_queue

    if _task_queue is None:
        _task_queue = BackgroundTaskQueue(max_concurrent_tasks=max_concurrent)

    return _task_queue
