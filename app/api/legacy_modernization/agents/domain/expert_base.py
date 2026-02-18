"""DomainExpertBase - Shared logic for all 4 domain expert agents.

All domain experts follow the same pattern:
1. Parse source code (deterministic parser)
2. Write results to SharedWorkspaceState
3. Publish completion event to orchestrator

Parser results (ast, features, trace_evidence) are IMMUTABLE by non-parser agents.
"""

import logging
from typing import List

from ...core.event_bus import EventBus
from ...core.protocol import (
    AgentId,
    AgentMessage,
    AgentResult,
    AgentTask,
    ChangeRequest,
    ChangeRequestResponse,
)
from ...core.shared_state import SharedStateStore
from ...models.enums import AgentRole, AgentStatus, MessageType
from ...parsers.base import BaseParser, NormalizedFeature, ParserResult
from ..base_agent import BaseAgent

logger = logging.getLogger(__name__)


class DomainExpertBase(BaseAgent):
    """Base class for COBOL/JCL/MAP/ASM domain expert agents."""

    def __init__(
        self,
        role: AgentRole,
        parser: BaseParser,
        event_bus: EventBus,
        shared_state: SharedStateStore,
    ) -> None:
        super().__init__(AgentId(role=role), event_bus)
        self.parser = parser
        self.shared_state = shared_state

    async def execute(self, task: AgentTask) -> AgentResult:
        # 1. Deterministic parsing
        result = await self.parser.parse(task.source_code, task.file_path)

        # 2. Write to SharedWorkspaceState (ACL-enforced)
        workspace = await self.shared_state.get_workspace(task.asset_id)
        workspace.ast = result.ast.model_dump()
        workspace.features = [f.model_dump() for f in result.features]
        workspace.trace_evidence = [e.model_dump() for e in result.trace_evidence]
        workspace.parse_errors = [e.model_dump() for e in result.parse_errors]
        workspace.confidence = self._calculate_confidence(result)
        workspace.stats = result.stats.model_dump()
        workspace.dialect = result.dialect

        await self.shared_state.save_workspace(
            workspace,
            agent_role=self.agent_id.role,
            changed_fields={
                "ast", "features", "trace_evidence", "parse_errors",
                "confidence", "stats",
            },
        )

        # 3. Publish completion event
        await self.publish(AgentMessage(
            sender=self.agent_id,
            recipient=AgentId(role=AgentRole.ORCHESTRATOR),
            message_type=MessageType.RESULT,
            payload={
                "asset_id": task.asset_id,
                "feature_count": len(result.features),
                "dialect": result.dialect,
                "parse_errors": len(result.parse_errors),
            },
            correlation_id=task.correlation_id,
        ))

        return AgentResult(
            agent_id=self.agent_id,
            status=AgentStatus.COMPLETED,
            workspace_id=task.asset_id,
            metadata={
                "feature_count": len(result.features),
                "dialect": result.dialect,
            },
        )

    async def handle_change_request(self, cr: ChangeRequest) -> ChangeRequestResponse:
        """Domain experts reject all external change requests to parser fields."""
        return ChangeRequestResponse(
            request_id=cr.request_id,
            approved=False,
            reason="Parser results are immutable. Submit a change_request to the Orchestrator.",
            agent_id=self.agent_id,
        )

    @staticmethod
    def _calculate_confidence(result: ParserResult) -> float:
        """Calculate parser confidence based on error ratio."""
        if not result.features:
            return 0.0
        error_ratio = len(result.parse_errors) / max(len(result.features), 1)
        return max(0.0, min(1.0, 1.0 - error_ratio))
