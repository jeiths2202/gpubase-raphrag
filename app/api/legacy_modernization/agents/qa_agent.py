"""QA Agent - Quality Control with VETO authority.

VETO power:
- When critical rule violations are found, the pipeline is BLOCKED
- VETO cannot be overridden by the Orchestrator — only fix-and-rerun

Validation rules (7):
- RULE-01: Every finding must have trace_evidence
- RULE-02: No zero-confidence findings
- RULE-03: No duplicate findings
- RULE-04: Severity ↔ support_level consistency
- RULE-05: Source line references within LOC range
- RULE-06: No hallucination patterns in LLM annotations
- RULE-07: All required workspace fields populated
"""

import logging
from typing import List

from ..core.event_bus import EventBus
from ..core.protocol import (
    AgentId,
    AgentMessage,
    AgentResult,
    AgentTask,
    ChangeRequest,
    ChangeRequestResponse,
)
from ..core.qa_rules import QARuleResult, get_all_rules
from ..core.shared_state import SharedStateStore
from ..models.enums import AgentRole, AgentStatus, MessageType, Severity
from .base_agent import BaseAgent

logger = logging.getLogger(__name__)


class QAAgent(BaseAgent):
    """Quality assurance agent with VETO authority over the pipeline."""

    def __init__(
        self,
        event_bus: EventBus,
        shared_state: SharedStateStore,
    ) -> None:
        super().__init__(AgentId(role=AgentRole.QA), event_bus)
        self.shared_state = shared_state

    async def execute(self, task: AgentTask) -> AgentResult:
        workspace = await self.shared_state.get_workspace(task.asset_id)
        qa_flags: List[dict] = []

        # Run all 7 QA rules
        rules = get_all_rules()
        for rule in rules:
            result: QARuleResult = await rule.validate(workspace)
            if not result.passed:
                qa_flags.append({
                    "rule_id": result.rule_id,
                    "severity": result.severity.value,
                    "message": result.message,
                    "affected_findings": result.affected_findings,
                })
                logger.warning(
                    "[QA] %s FAILED: %s (%d affected)",
                    result.rule_id, result.message, len(result.affected_findings),
                )
            else:
                logger.info("[QA] %s PASSED: %s", result.rule_id, result.message)

        # VETO decision: any CRITICAL severity failure → block pipeline
        critical_flags = [
            f for f in qa_flags if f["severity"] == Severity.CRITICAL.value
        ]

        if critical_flags:
            # Issue VETO — blocks pipeline
            await self.publish(AgentMessage(
                sender=self.agent_id,
                recipient=AgentId(role=AgentRole.ORCHESTRATOR),
                message_type=MessageType.VETO,
                payload={
                    "asset_id": task.asset_id,
                    "critical_flags": critical_flags,
                    "action": "PIPELINE_BLOCKED",
                    "total_flags": len(qa_flags),
                },
                correlation_id=task.correlation_id,
            ))
            logger.warning(
                "[QA] VETO issued for asset %s — %d critical violations",
                task.asset_id, len(critical_flags),
            )
        else:
            # QA PASS
            await self.publish(AgentMessage(
                sender=self.agent_id,
                recipient=AgentId(role=AgentRole.ORCHESTRATOR),
                message_type=MessageType.QA_PASS,
                payload={
                    "asset_id": task.asset_id,
                    "total_flags": len(qa_flags),
                    "non_critical_flags": len(qa_flags),
                },
                correlation_id=task.correlation_id,
            ))

        # Record results in workspace
        workspace.qa_flags = qa_flags
        workspace.qa_passed = len(critical_flags) == 0
        await self.shared_state.save_workspace(
            workspace, AgentRole.QA,
            changed_fields={"qa_flags", "qa_passed"},
        )

        return AgentResult(
            agent_id=self.agent_id,
            status=AgentStatus.COMPLETED if workspace.qa_passed else AgentStatus.ERROR,
            workspace_id=task.asset_id,
            metadata={
                "qa_passed": workspace.qa_passed,
                "total_flags": len(qa_flags),
                "critical_flags": len(critical_flags),
            },
        )

    async def handle_change_request(self, cr: ChangeRequest) -> ChangeRequestResponse:
        """QA agent always approves its own change requests (VETO authority)."""
        return ChangeRequestResponse(
            request_id=cr.request_id,
            approved=True,
            reason="QA has veto authority",
            agent_id=self.agent_id,
        )
