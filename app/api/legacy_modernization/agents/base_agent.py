"""BaseAgent - Abstract base class for all autonomous agents.

Every agent has:
- An AgentId (role + instance_id)
- EventBus access (publish/subscribe)
- Status tracking
- ChangeRequest handling
"""

import logging
from abc import ABC, abstractmethod
from typing import AsyncGenerator

from ..core.event_bus import EventBus
from ..core.protocol import (
    AgentId,
    AgentMessage,
    AgentResult,
    AgentTask,
    ChangeRequest,
    ChangeRequestResponse,
)
from ..models.enums import AgentStatus

logger = logging.getLogger(__name__)


class BaseAgent(ABC):
    """Abstract base class for all agents in the platform."""

    def __init__(self, agent_id: AgentId, event_bus: EventBus) -> None:
        self.agent_id = agent_id
        self.event_bus = event_bus
        self.status = AgentStatus.IDLE

    @abstractmethod
    async def execute(self, task: AgentTask) -> AgentResult:
        """Main execution logic. Subclasses must implement."""
        ...

    @abstractmethod
    async def handle_change_request(self, cr: ChangeRequest) -> ChangeRequestResponse:
        """Handle incoming change requests. Subclasses must implement."""
        ...

    async def publish(self, message: AgentMessage) -> str:
        """Publish a message to the event bus."""
        return await self.event_bus.publish(
            stream=f"agent.{self.agent_id.role.value}",
            message=message,
        )

    async def subscribe(self, stream: str) -> AsyncGenerator[tuple[str, AgentMessage], None]:
        """Subscribe to a stream via consumer group (at-least-once delivery).

        Consumer group and name are auto-generated from the agent's role and instance_id.
        """
        consumer_group = f"group.{self.agent_id.role.value}"
        consumer_name = f"{self.agent_id.role.value}.{self.agent_id.instance_id[:8]}"
        async for msg_id, message in self.event_bus.subscribe(
            stream, consumer_group, consumer_name
        ):
            yield (msg_id, message)

    async def run(self, task: AgentTask) -> AgentResult:
        """Execute with status tracking and error handling."""
        self.status = AgentStatus.PROCESSING
        logger.info(
            "[%s] Starting task %s for asset %s",
            self.agent_id.role.value, task.task_id, task.asset_id,
        )
        try:
            result = await self.execute(task)
            self.status = AgentStatus.COMPLETED if result.status == AgentStatus.COMPLETED else AgentStatus.ERROR
            logger.info(
                "[%s] Task %s completed with status %s",
                self.agent_id.role.value, task.task_id, result.status.value,
            )
            return result
        except Exception as exc:
            self.status = AgentStatus.ERROR
            logger.error(
                "[%s] Task %s failed: %s",
                self.agent_id.role.value, task.task_id, exc,
            )
            return AgentResult(
                agent_id=self.agent_id,
                status=AgentStatus.ERROR,
                workspace_id=task.asset_id,
                error_message=str(exc),
            )
