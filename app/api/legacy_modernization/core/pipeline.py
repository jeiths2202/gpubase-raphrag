"""PipelineStateMachine - 12-state pipeline for legacy asset analysis.

State flow:
  PENDING → PARSING → KNOWLEDGE_ENRICHMENT → COMPATIBILITY_ANALYSIS
  → RISK_ASSESSMENT → REVIEWING → QA_VALIDATION → E2E_TESTING
  → REPORT_GENERATION → COMPLETED

Special transitions:
  REVIEWING → PARSING (reanalysis, max 5 iterations)
  QA_VALIDATION → BLOCKED (QA VETO)
  BLOCKED → PARSING (after fix)
  E2E_TESTING → PARSING (regression detected)
  Any → FAILED (unrecoverable error)
"""

import logging
from typing import ClassVar, Optional

from ..core.errors import MaxReanalysisExceededError
from ..core.shared_state import SharedWorkspaceState
from ..models.enums import AgentRole, AgentStatus, AssetType, PipelineStatus

logger = logging.getLogger(__name__)


# Ordered pipeline stages (for next-status lookup)
_ORDERED_STAGES = [
    PipelineStatus.PARSING,
    PipelineStatus.KNOWLEDGE_ENRICHMENT,
    PipelineStatus.COMPATIBILITY_ANALYSIS,
    PipelineStatus.RISK_ASSESSMENT,
    PipelineStatus.REVIEWING,
    PipelineStatus.QA_VALIDATION,
    PipelineStatus.E2E_TESTING,
    PipelineStatus.REPORT_GENERATION,
    PipelineStatus.COMPLETED,
]


class PipelineStateMachine:
    """12-state pipeline state machine with reanalysis loop protection."""

    MAX_REANALYSIS_ITERATIONS: ClassVar[int] = 5

    # Valid state transitions
    TRANSITIONS: ClassVar[dict[PipelineStatus, set[PipelineStatus]]] = {
        PipelineStatus.PENDING: {PipelineStatus.PARSING, PipelineStatus.FAILED},
        PipelineStatus.PARSING: {PipelineStatus.KNOWLEDGE_ENRICHMENT, PipelineStatus.FAILED},
        PipelineStatus.KNOWLEDGE_ENRICHMENT: {PipelineStatus.COMPATIBILITY_ANALYSIS, PipelineStatus.FAILED},
        PipelineStatus.COMPATIBILITY_ANALYSIS: {PipelineStatus.RISK_ASSESSMENT, PipelineStatus.FAILED},
        PipelineStatus.RISK_ASSESSMENT: {PipelineStatus.REVIEWING, PipelineStatus.FAILED},
        PipelineStatus.REVIEWING: {PipelineStatus.QA_VALIDATION, PipelineStatus.PARSING, PipelineStatus.FAILED},
        PipelineStatus.QA_VALIDATION: {PipelineStatus.E2E_TESTING, PipelineStatus.BLOCKED, PipelineStatus.FAILED},
        PipelineStatus.BLOCKED: {PipelineStatus.PARSING, PipelineStatus.FAILED},
        PipelineStatus.E2E_TESTING: {PipelineStatus.REPORT_GENERATION, PipelineStatus.PARSING, PipelineStatus.FAILED},
        PipelineStatus.REPORT_GENERATION: {PipelineStatus.COMPLETED, PipelineStatus.FAILED},
        PipelineStatus.COMPLETED: set(),
        PipelineStatus.FAILED: set(),
    }

    # State → agent role to execute (None = Orchestrator handles directly)
    STATE_AGENTS: ClassVar[dict[PipelineStatus, Optional[AgentRole]]] = {
        PipelineStatus.PARSING: None,  # Orchestrator selects expert by asset_type
        PipelineStatus.KNOWLEDGE_ENRICHMENT: AgentRole.LEGACY_KNOWLEDGE,
        PipelineStatus.COMPATIBILITY_ANALYSIS: AgentRole.COMPETITOR_INTELLIGENCE,
        PipelineStatus.RISK_ASSESSMENT: AgentRole.RISK_INTELLIGENCE,
        PipelineStatus.REVIEWING: AgentRole.REVIEWER,
        PipelineStatus.QA_VALIDATION: AgentRole.QA,
        PipelineStatus.E2E_TESTING: AgentRole.E2E_TEST,
        PipelineStatus.REPORT_GENERATION: None,  # Orchestrator calls ReportGenerator
    }

    # Asset type → domain expert role
    EXPERT_MAP: ClassVar[dict[AssetType, AgentRole]] = {
        AssetType.COBOL: AgentRole.COBOL_EXPERT,
        AssetType.JCL: AgentRole.JCL_EXPERT,
        AssetType.MAP: AgentRole.MAP_EXPERT,
        AssetType.ASSEMBLER: AgentRole.ASM_EXPERT,
    }

    def __init__(self) -> None:
        self._reanalysis_counts: dict[str, int] = {}

    def can_transition(self, current: PipelineStatus, target: PipelineStatus) -> bool:
        """Check if a transition is valid."""
        return target in self.TRANSITIONS.get(current, set())

    def transition(
        self, workspace: SharedWorkspaceState, target: PipelineStatus
    ) -> None:
        """Execute a state transition with validation and reanalysis guard.

        Raises:
            ValueError: If transition is invalid.
            MaxReanalysisExceededError: If reanalysis iteration limit reached.
        """
        current = workspace.pipeline_status

        if not self.can_transition(current, target):
            raise ValueError(
                f"Invalid transition: {current.value} -> {target.value}"
            )

        # Reanalysis loop guard
        if target == PipelineStatus.PARSING and current in (
            PipelineStatus.REVIEWING,
            PipelineStatus.BLOCKED,
            PipelineStatus.E2E_TESTING,
        ):
            count = self._reanalysis_counts.get(workspace.asset_id, 0)
            if count >= self.MAX_REANALYSIS_ITERATIONS:
                raise MaxReanalysisExceededError(
                    workspace.asset_id, self.MAX_REANALYSIS_ITERATIONS,
                )
            self._reanalysis_counts[workspace.asset_id] = count + 1
            logger.warning(
                "Reanalysis iteration %d/%d for %s",
                count + 1, self.MAX_REANALYSIS_ITERATIONS, workspace.asset_id,
            )

        logger.info(
            "Pipeline transition: %s -> %s (asset=%s)",
            current.value, target.value, workspace.asset_id,
        )
        workspace.pipeline_status = target

    def get_reanalysis_count(self, asset_id: str) -> int:
        """Get current reanalysis iteration count for an asset."""
        return self._reanalysis_counts.get(asset_id, 0)

    def get_agent_for_state(self, state: PipelineStatus) -> Optional[AgentRole]:
        """Get the agent role responsible for a given pipeline state."""
        return self.STATE_AGENTS.get(state)

    def get_expert_for_asset(self, asset_type: AssetType) -> AgentRole:
        """Get the domain expert role for an asset type."""
        role = self.EXPERT_MAP.get(asset_type)
        if not role:
            raise ValueError(f"No expert agent for asset type: {asset_type.value}")
        return role

    def determine_next_status(
        self,
        current: PipelineStatus,
        agent_status: AgentStatus,
        workspace: SharedWorkspaceState,
    ) -> PipelineStatus:
        """Determine the next pipeline status based on agent result.

        Args:
            current: Current pipeline status.
            agent_status: Result status from the agent.
            workspace: Current workspace state.
        """
        if agent_status == AgentStatus.ERROR:
            # QA validation failure → BLOCKED
            if current == PipelineStatus.QA_VALIDATION and not workspace.qa_passed:
                return PipelineStatus.BLOCKED

            # Reviewer requested reanalysis
            if current == PipelineStatus.REVIEWING:
                has_reanalysis = any(
                    (n.get("type") if isinstance(n, dict) else "") == "reanalysis_requested"
                    for n in workspace.review_notes
                )
                if has_reanalysis:
                    return PipelineStatus.PARSING

            return PipelineStatus.FAILED

        # Normal progression: advance to next stage
        try:
            idx = _ORDERED_STAGES.index(current)
            return _ORDERED_STAGES[idx + 1]
        except (ValueError, IndexError):
            return PipelineStatus.COMPLETED

    def reset_reanalysis(self, asset_id: str) -> None:
        """Reset reanalysis count for an asset (e.g., after successful completion)."""
        self._reanalysis_counts.pop(asset_id, None)
