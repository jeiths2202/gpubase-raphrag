"""ConflictResolver - 5-Rule Priority Conflict Resolution.

Rules (in priority order):
  Rule 1: Parser results immutable → REJECT any non-parser modification
  Rule 2: QA veto → APPROVE immediately (veto authority)
  Rule 3: Reviewer escalation → REANALYZE (up to MAX_REANALYSIS_ITERATIONS)
  Rule 4: Confidence-based → APPROVE if confidence improvement > 0.1
  Rule 5: Otherwise → ESCALATE to Orchestrator for manual resolution
"""

import logging
from typing import ClassVar

from ..core.protocol import ChangeRequest, Resolution
from ..core.shared_state import SharedWorkspaceState
from ..models.enums import AgentRole, ChangeRequestStatus

logger = logging.getLogger(__name__)

# Parser-owned fields that are immutable by non-parser agents
_IMMUTABLE_PREFIXES = ("ast", "features", "trace_evidence", "parse_errors")

# Roles that own parser fields
_PARSER_ROLES = frozenset({
    AgentRole.COBOL_EXPERT,
    AgentRole.JCL_EXPERT,
    AgentRole.MAP_EXPERT,
    AgentRole.ASM_EXPERT,
})


class ConflictResolver:
    """5-rule priority conflict resolution engine."""

    MAX_REANALYSIS_ITERATIONS: ClassVar[int] = 5

    async def resolve(
        self,
        change_request: ChangeRequest,
        workspace: SharedWorkspaceState,
    ) -> Resolution:
        """Resolve a change request using 5-rule priority chain."""

        # Rule 1: Parser immutable — non-parser agents cannot modify parser fields
        if any(change_request.target_field.startswith(p) for p in _IMMUTABLE_PREFIXES):
            if change_request.requester.role not in _PARSER_ROLES:
                logger.info(
                    "RULE-1 REJECT: %s tried to modify %s",
                    change_request.requester.role.value,
                    change_request.target_field,
                )
                return Resolution(
                    status=ChangeRequestStatus.REJECTED,
                    reason="Parser results are immutable by non-parser agents",
                    rule_applied="RULE-1-PARSER-IMMUTABLE",
                )

        # Rule 2: QA veto authority — always approved
        if change_request.requester.role == AgentRole.QA:
            logger.info("RULE-2 APPROVE: QA veto on %s", change_request.target_field)
            return Resolution(
                status=ChangeRequestStatus.APPROVED,
                reason="QA has veto authority",
                rule_applied="RULE-2-QA-VETO",
            )

        # Rule 3: Reviewer escalation → reanalysis (with iteration limit)
        if (
            change_request.requester.role == AgentRole.REVIEWER
            and change_request.status == ChangeRequestStatus.REANALYSIS_REQUIRED
        ):
            iteration_count = self._count_reanalysis(workspace, change_request.target_field)
            if iteration_count >= self.MAX_REANALYSIS_ITERATIONS:
                logger.warning(
                    "RULE-3 MAX-ITER: %d iterations reached for %s, accepting",
                    iteration_count, change_request.target_field,
                )
                return Resolution(
                    status=ChangeRequestStatus.APPROVED,
                    reason=(
                        f"Max reanalysis iterations ({self.MAX_REANALYSIS_ITERATIONS}) "
                        f"reached, accepting current value"
                    ),
                    rule_applied="RULE-3-MAX-ITERATION",
                )
            logger.info(
                "RULE-3 REANALYZE: Reviewer requested reanalysis for %s (iter %d)",
                change_request.target_field, iteration_count + 1,
            )
            return Resolution(
                status=ChangeRequestStatus.REANALYSIS_REQUIRED,
                reason="Reviewer requested reanalysis",
                rule_applied="RULE-3-REVIEWER-ESCALATION",
            )

        # Rule 4: Confidence-based — approve if significant improvement
        if change_request.confidence_delta > 0.1:
            logger.info(
                "RULE-4 APPROVE: Confidence improvement +%.2f for %s",
                change_request.confidence_delta, change_request.target_field,
            )
            return Resolution(
                status=ChangeRequestStatus.APPROVED,
                reason=f"Confidence improvement: +{change_request.confidence_delta:.2f}",
                rule_applied="RULE-4-CONFIDENCE-BASED",
            )

        # Rule 5: Escalate to Orchestrator for manual resolution
        logger.info(
            "RULE-5 ESCALATE: %s change to %s escalated to Orchestrator",
            change_request.requester.role.value, change_request.target_field,
        )
        return Resolution(
            status=ChangeRequestStatus.PENDING,
            reason="Escalated to Orchestrator for manual resolution",
            rule_applied="RULE-5-ORCHESTRATOR-ESCALATION",
        )

    @staticmethod
    def _count_reanalysis(workspace: SharedWorkspaceState, target_field: str) -> int:
        """Count how many reanalysis requests have been made for a field."""
        count = 0
        for cr_data in workspace.change_requests:
            cr_target = cr_data.get("target_field", "") if isinstance(cr_data, dict) else ""
            cr_status = cr_data.get("status", "") if isinstance(cr_data, dict) else ""
            if cr_target == target_field and cr_status == ChangeRequestStatus.REANALYSIS_REQUIRED.value:
                count += 1
        return count
