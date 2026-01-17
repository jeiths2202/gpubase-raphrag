"""
Enhancement Queue Manager

Manages queue of enhancement agent tasks, monitors running agents,
and provides control functions for force stop and queue clearing.
"""
import asyncio
import logging
import uuid
from datetime import datetime, timezone
from typing import Optional, Dict, List, Any, Callable, Awaitable
from dataclasses import dataclass, field
from enum import Enum
from collections import deque

logger = logging.getLogger(__name__)


class TaskStatus(str, Enum):
    """Status of a queued task."""
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class AgentType(str, Enum):
    """Types of enhancement agents."""
    ANALYST = "analyst"
    ARCHITECT = "architect"
    CODER = "coder"
    QA = "qa"


@dataclass
class QueuedTask:
    """Represents a task in the queue."""
    id: str
    enhancement_id: str
    agent_type: AgentType
    operation: str  # analyze, design_architecture, implement, verify
    status: TaskStatus
    created_at: datetime
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    user_id: str = ""
    user_name: str = ""
    error_message: Optional[str] = None
    result: Optional[Any] = None

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "enhancement_id": self.enhancement_id,
            "agent_type": self.agent_type.value,
            "operation": self.operation,
            "status": self.status.value,
            "created_at": self.created_at.isoformat(),
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "user_id": self.user_id,
            "user_name": self.user_name,
            "error_message": self.error_message,
            "duration_ms": self._get_duration_ms()
        }

    def _get_duration_ms(self) -> Optional[int]:
        if self.started_at:
            end_time = self.completed_at or datetime.now(timezone.utc)
            return int((end_time - self.started_at).total_seconds() * 1000)
        return None


@dataclass
class AgentStatus:
    """Status of an enhancement agent."""
    agent_type: AgentType
    is_running: bool = False
    current_task: Optional[QueuedTask] = None
    total_processed: int = 0
    total_failed: int = 0
    last_activity: Optional[datetime] = None

    def to_dict(self) -> dict:
        return {
            "agent_type": self.agent_type.value,
            "is_running": self.is_running,
            "current_task": self.current_task.to_dict() if self.current_task else None,
            "total_processed": self.total_processed,
            "total_failed": self.total_failed,
            "last_activity": self.last_activity.isoformat() if self.last_activity else None
        }


class EnhancementQueueManager:
    """
    Manages the queue of enhancement agent tasks.

    Features:
    - Queue new tasks when agents are busy
    - Monitor running agent tasks
    - Force stop running tasks
    - Clear all queued tasks
    - Track agent statistics
    """

    _instance: Optional["EnhancementQueueManager"] = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return

        self._initialized = True

        # Task queue (FIFO)
        self._queue: deque[QueuedTask] = deque()

        # Currently running tasks by agent type
        self._running_tasks: Dict[AgentType, QueuedTask] = {}

        # Agent status tracking
        self._agent_status: Dict[AgentType, AgentStatus] = {
            AgentType.ANALYST: AgentStatus(agent_type=AgentType.ANALYST),
            AgentType.ARCHITECT: AgentStatus(agent_type=AgentType.ARCHITECT),
            AgentType.CODER: AgentStatus(agent_type=AgentType.CODER),
            AgentType.QA: AgentStatus(agent_type=AgentType.QA),
        }

        # Cancellation flags for running tasks
        self._cancellation_flags: Dict[str, bool] = {}

        # Task history (recent completed/failed tasks)
        self._task_history: List[QueuedTask] = []
        self._max_history_size = 100

        # Lock for thread-safe operations
        self._lock = asyncio.Lock()

        # Background processor task
        self._processor_task: Optional[asyncio.Task] = None
        self._processor_running = False

        logger.info("EnhancementQueueManager initialized")

    async def start_processor(self):
        """Start the background queue processor."""
        if not self._processor_running:
            self._processor_running = True
            self._processor_task = asyncio.create_task(self._process_queue())
            logger.info("Queue processor started")

    async def stop_processor(self):
        """Stop the background queue processor."""
        self._processor_running = False
        if self._processor_task:
            self._processor_task.cancel()
            try:
                await self._processor_task
            except asyncio.CancelledError:
                pass
            logger.info("Queue processor stopped")

    async def _process_queue(self):
        """Background task to process queued tasks."""
        while self._processor_running:
            try:
                async with self._lock:
                    # Check if there are queued tasks
                    if self._queue:
                        task = self._queue[0]
                        agent_type = task.agent_type

                        # Check if the agent is available
                        if agent_type not in self._running_tasks:
                            # Dequeue and start processing
                            task = self._queue.popleft()
                            await self._start_task(task)

                # Wait before checking again
                await asyncio.sleep(0.5)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in queue processor: {e}")
                await asyncio.sleep(1)

    async def enqueue_task(
        self,
        enhancement_id: str,
        agent_type: AgentType,
        operation: str,
        user_id: str = "",
        user_name: str = "",
        task_func: Optional[Callable[[], Awaitable[Any]]] = None
    ) -> QueuedTask:
        """
        Add a task to the queue.

        If the agent is available, the task starts immediately.
        If busy, the task is queued.

        Args:
            enhancement_id: ID of the enhancement
            agent_type: Type of agent to use
            operation: Operation name (analyze, design_architecture, etc.)
            user_id: ID of the user requesting the task
            user_name: Name of the user
            task_func: Async function to execute (optional, for direct execution)

        Returns:
            QueuedTask object
        """
        task = QueuedTask(
            id=str(uuid.uuid4()),
            enhancement_id=enhancement_id,
            agent_type=agent_type,
            operation=operation,
            status=TaskStatus.QUEUED,
            created_at=datetime.now(timezone.utc),
            user_id=user_id,
            user_name=user_name
        )

        async with self._lock:
            # Check if agent is available
            if agent_type not in self._running_tasks:
                # Start immediately
                task.status = TaskStatus.RUNNING
                task.started_at = datetime.now(timezone.utc)
                self._running_tasks[agent_type] = task
                self._agent_status[agent_type].is_running = True
                self._agent_status[agent_type].current_task = task
                self._agent_status[agent_type].last_activity = datetime.now(timezone.utc)
                self._cancellation_flags[task.id] = False

                logger.info(f"Task {task.id} started immediately for {agent_type.value}")
            else:
                # Add to queue
                self._queue.append(task)
                logger.info(f"Task {task.id} queued for {agent_type.value}. Queue position: {len(self._queue)}")

        return task

    async def _start_task(self, task: QueuedTask):
        """Start a queued task."""
        task.status = TaskStatus.RUNNING
        task.started_at = datetime.now(timezone.utc)
        self._running_tasks[task.agent_type] = task
        self._agent_status[task.agent_type].is_running = True
        self._agent_status[task.agent_type].current_task = task
        self._agent_status[task.agent_type].last_activity = datetime.now(timezone.utc)
        self._cancellation_flags[task.id] = False

        logger.info(f"Task {task.id} started from queue for {task.agent_type.value}")

    async def complete_task(
        self,
        task_id: str,
        success: bool = True,
        result: Any = None,
        error_message: Optional[str] = None
    ):
        """
        Mark a task as completed.

        Args:
            task_id: ID of the task
            success: Whether the task completed successfully
            result: Task result (if successful)
            error_message: Error message (if failed)
        """
        async with self._lock:
            # Find the running task
            for agent_type, task in list(self._running_tasks.items()):
                if task.id == task_id:
                    task.completed_at = datetime.now(timezone.utc)
                    task.status = TaskStatus.COMPLETED if success else TaskStatus.FAILED
                    task.result = result
                    task.error_message = error_message

                    # Update agent status
                    self._agent_status[agent_type].is_running = False
                    self._agent_status[agent_type].current_task = None
                    self._agent_status[agent_type].total_processed += 1
                    if not success:
                        self._agent_status[agent_type].total_failed += 1
                    self._agent_status[agent_type].last_activity = datetime.now(timezone.utc)

                    # Remove from running tasks
                    del self._running_tasks[agent_type]

                    # Remove cancellation flag
                    self._cancellation_flags.pop(task_id, None)

                    # Add to history
                    self._task_history.insert(0, task)
                    if len(self._task_history) > self._max_history_size:
                        self._task_history = self._task_history[:self._max_history_size]

                    logger.info(f"Task {task_id} completed with status: {task.status.value}")
                    return

            logger.warning(f"Task {task_id} not found in running tasks")

    def is_cancellation_requested(self, task_id: str) -> bool:
        """Check if cancellation was requested for a task."""
        return self._cancellation_flags.get(task_id, False)

    async def force_stop_task(self, task_id: str) -> bool:
        """
        Request cancellation of a running task.

        The actual task must check for cancellation and handle it.

        Args:
            task_id: ID of the task to stop

        Returns:
            True if cancellation was requested, False if task not found
        """
        async with self._lock:
            if task_id in self._cancellation_flags:
                self._cancellation_flags[task_id] = True
                logger.info(f"Cancellation requested for task {task_id}")

                # Find and update the task
                for agent_type, task in self._running_tasks.items():
                    if task.id == task_id:
                        task.status = TaskStatus.CANCELLED
                        task.completed_at = datetime.now(timezone.utc)
                        task.error_message = "Task was force stopped by user"

                        # Update agent status
                        self._agent_status[agent_type].is_running = False
                        self._agent_status[agent_type].current_task = None
                        self._agent_status[agent_type].last_activity = datetime.now(timezone.utc)

                        # Remove from running
                        del self._running_tasks[agent_type]

                        # Add to history
                        self._task_history.insert(0, task)
                        if len(self._task_history) > self._max_history_size:
                            self._task_history = self._task_history[:self._max_history_size]

                        break

                return True
            return False

    async def force_stop_agent(self, agent_type: AgentType) -> bool:
        """
        Force stop the currently running task for an agent.

        Args:
            agent_type: Type of agent to stop

        Returns:
            True if a task was stopped, False if no task was running
        """
        async with self._lock:
            if agent_type in self._running_tasks:
                task = self._running_tasks[agent_type]
                return await self.force_stop_task(task.id)
            return False

    async def clear_queue(self, agent_type: Optional[AgentType] = None) -> int:
        """
        Clear all queued tasks.

        Args:
            agent_type: Optional - only clear tasks for specific agent type

        Returns:
            Number of tasks cleared
        """
        async with self._lock:
            if agent_type is None:
                count = len(self._queue)
                # Mark all as cancelled and add to history
                for task in self._queue:
                    task.status = TaskStatus.CANCELLED
                    task.completed_at = datetime.now(timezone.utc)
                    task.error_message = "Task was cleared from queue"
                    self._task_history.insert(0, task)

                self._queue.clear()
                logger.info(f"Cleared all {count} queued tasks")
                return count
            else:
                # Clear only tasks for specific agent type
                original_queue = list(self._queue)
                self._queue.clear()
                count = 0
                for task in original_queue:
                    if task.agent_type == agent_type:
                        task.status = TaskStatus.CANCELLED
                        task.completed_at = datetime.now(timezone.utc)
                        task.error_message = "Task was cleared from queue"
                        self._task_history.insert(0, task)
                        count += 1
                    else:
                        self._queue.append(task)

                logger.info(f"Cleared {count} queued tasks for {agent_type.value}")
                return count

    async def get_queue_status(self) -> dict:
        """
        Get the current status of the queue and all agents.

        Returns:
            Dictionary with queue and agent status information
        """
        async with self._lock:
            return {
                "queue": {
                    "total_queued": len(self._queue),
                    "tasks": [task.to_dict() for task in self._queue]
                },
                "agents": {
                    agent_type.value: status.to_dict()
                    for agent_type, status in self._agent_status.items()
                },
                "running_tasks": [
                    task.to_dict() for task in self._running_tasks.values()
                ],
                "recent_history": [
                    task.to_dict() for task in self._task_history[:20]
                ]
            }

    async def get_agent_status(self, agent_type: AgentType) -> dict:
        """Get status of a specific agent."""
        async with self._lock:
            return self._agent_status[agent_type].to_dict()

    async def is_agent_busy(self, agent_type: AgentType) -> bool:
        """Check if an agent is currently busy."""
        async with self._lock:
            return agent_type in self._running_tasks

    async def get_queue_position(self, task_id: str) -> Optional[int]:
        """Get the position of a task in the queue (1-indexed)."""
        async with self._lock:
            for i, task in enumerate(self._queue):
                if task.id == task_id:
                    return i + 1
            return None

    async def get_task_by_id(self, task_id: str) -> Optional[QueuedTask]:
        """Get a task by its ID (from queue, running, or history)."""
        async with self._lock:
            # Check queue
            for task in self._queue:
                if task.id == task_id:
                    return task

            # Check running tasks
            for task in self._running_tasks.values():
                if task.id == task_id:
                    return task

            # Check history
            for task in self._task_history:
                if task.id == task_id:
                    return task

            return None

    async def get_enhancement_tasks(self, enhancement_id: str) -> List[QueuedTask]:
        """Get all tasks (queued, running, history) for an enhancement."""
        async with self._lock:
            tasks = []

            # From queue
            for task in self._queue:
                if task.enhancement_id == enhancement_id:
                    tasks.append(task)

            # From running
            for task in self._running_tasks.values():
                if task.enhancement_id == enhancement_id:
                    tasks.append(task)

            # From history
            for task in self._task_history:
                if task.enhancement_id == enhancement_id:
                    tasks.append(task)

            return tasks


# Global instance
_queue_manager: Optional[EnhancementQueueManager] = None


def get_queue_manager() -> EnhancementQueueManager:
    """Get the global queue manager instance."""
    global _queue_manager
    if _queue_manager is None:
        _queue_manager = EnhancementQueueManager()
    return _queue_manager
