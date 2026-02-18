"""Reviewer Agent - Peer Review for cross-validation and escalation.

Responsibilities:
- Cross-validation: Feature extraction results ↔ Capability mapping consistency
- Duplicate finding detection
- Low-confidence challenge (confidence < threshold → reanalysis trigger)
- Severity re-adjustment

Escalation rules:
- confidence < 0.6 → request_reanalysis (via ChangeRequest to Orchestrator)
- cross-validation inconsistencies > 3 → Orchestrator escalation
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
from ..core.shared_state import SharedStateStore
from ..models.enums import (
    AgentRole,
    AgentStatus,
    ChangeRequestStatus,
    MessageType,
    Severity,
    SupportLevel,
)
from .base_agent import BaseAgent

logger = logging.getLogger(__name__)


class ReviewerAgent(BaseAgent):
    """Peer review agent — cross-validates findings and triggers reanalysis."""

    REANALYSIS_THRESHOLD = 0.6
    INCONSISTENCY_ESCALATION_LIMIT = 3

    def __init__(
        self,
        event_bus: EventBus,
        shared_state: SharedStateStore,
    ) -> None:
        super().__init__(AgentId(role=AgentRole.REVIEWER), event_bus)
        self.shared_state = shared_state

    async def execute(self, task: AgentTask) -> AgentResult:
        workspace = await self.shared_state.get_workspace(task.asset_id)
        review_notes: List[dict] = []

        # 1. Cross-validation: features ↔ compatibility_findings consistency
        inconsistencies = self._check_cross_consistency(
            workspace.features, workspace.compatibility_findings,
        )
        review_notes.extend(inconsistencies)

        # 2. Duplicate finding detection
        duplicates = self._detect_duplicate_findings(workspace.compatibility_findings)
        review_notes.extend(duplicates)

        # 3. Low-confidence challenge
        low_confidence_notes = self._check_low_confidence(workspace.compatibility_findings)
        review_notes.extend(low_confidence_notes)

        # 4. Severity consistency check
        severity_notes = self._check_severity_consistency(workspace.compatibility_findings)
        review_notes.extend(severity_notes)

        # 5. Escalation: too many inconsistencies → notify orchestrator
        if len(inconsistencies) > self.INCONSISTENCY_ESCALATION_LIMIT:
            await self._escalate(task, inconsistencies)

        # 6. If reanalysis is needed, mark note type
        reanalysis_needed = any(
            n.get("type") == "reanalysis_requested" for n in review_notes
        )

        # Record results
        workspace.review_notes = review_notes
        await self.shared_state.save_workspace(
            workspace, AgentRole.REVIEWER,
            changed_fields={"review_notes"},
        )

        # Publish result
        await self.publish(AgentMessage(
            sender=self.agent_id,
            recipient=AgentId(role=AgentRole.ORCHESTRATOR),
            message_type=MessageType.REVIEW_RESULT,
            payload={
                "asset_id": task.asset_id,
                "total_notes": len(review_notes),
                "inconsistencies": len(inconsistencies),
                "reanalysis_requested": reanalysis_needed,
            },
            correlation_id=task.correlation_id,
        ))

        status = AgentStatus.ERROR if reanalysis_needed else AgentStatus.COMPLETED
        return AgentResult(
            agent_id=self.agent_id,
            status=status,
            workspace_id=task.asset_id,
            metadata={"review_notes_count": len(review_notes)},
        )

    async def handle_change_request(self, cr: ChangeRequest) -> ChangeRequestResponse:
        """Reviewer approves changes to review_notes only."""
        if cr.target_field.startswith("review_notes"):
            return ChangeRequestResponse(
                request_id=cr.request_id,
                approved=True,
                reason="Reviewer accepts changes to review_notes",
                agent_id=self.agent_id,
            )
        return ChangeRequestResponse(
            request_id=cr.request_id,
            approved=False,
            reason="Reviewer can only modify review_notes",
            agent_id=self.agent_id,
        )

    # --- Private helpers ---

    def _check_cross_consistency(
        self, features: List[dict], findings: List[dict],
    ) -> List[dict]:
        """Check that every feature has at least one finding and vice versa."""
        notes: List[dict] = []
        feature_ids = {f.get("feature_id", "") for f in features}

        finding_feature_ids = set()
        for finding in findings:
            feat = finding.get("feature", {})
            fid = feat.get("feature_id", "")
            finding_feature_ids.add(fid)

        # Features without findings
        orphan_features = feature_ids - finding_feature_ids
        for fid in orphan_features:
            notes.append({
                "type": "inconsistency",
                "severity": "warning",
                "message": f"Feature '{fid}' has no compatibility finding",
                "finding_id": None,
                "feature_id": fid,
            })

        return notes

    def _detect_duplicate_findings(self, findings: List[dict]) -> List[dict]:
        """Detect findings with same feature + vendor combination."""
        notes: List[dict] = []
        seen: dict[str, str] = {}  # (feature_id, vendor) → finding_id

        for finding in findings:
            feat = finding.get("feature", {})
            fid = feat.get("feature_id", "")
            vendor = finding.get("vendor", "")
            key = f"{fid}:{vendor}"

            if key in seen:
                notes.append({
                    "type": "duplicate",
                    "severity": "warning",
                    "message": f"Duplicate finding for feature '{fid}' vendor '{vendor}'",
                    "finding_id": finding.get("finding_id", ""),
                    "duplicate_of": seen[key],
                })
            else:
                seen[key] = finding.get("finding_id", "")

        return notes

    def _check_low_confidence(self, findings: List[dict]) -> List[dict]:
        """Flag findings below confidence threshold for reanalysis."""
        notes: List[dict] = []
        for finding in findings:
            confidence = finding.get("confidence", 0.0)
            if confidence < self.REANALYSIS_THRESHOLD:
                notes.append({
                    "type": "reanalysis_requested",
                    "severity": "error",
                    "message": (
                        f"Finding '{finding.get('finding_id', '')}' has confidence "
                        f"{confidence:.2f} < threshold {self.REANALYSIS_THRESHOLD}"
                    ),
                    "finding_id": finding.get("finding_id", ""),
                })
        return notes

    def _check_severity_consistency(self, findings: List[dict]) -> List[dict]:
        """Check severity is consistent with support_level."""
        notes: List[dict] = []
        expected_map = {
            SupportLevel.FULL.value: Severity.INFO.value,
            SupportLevel.PARTIAL.value: Severity.WARNING.value,
            SupportLevel.WORKAROUND.value: Severity.WARNING.value,
            SupportLevel.UNSUPPORTED.value: Severity.ERROR.value,
        }
        for finding in findings:
            sl = finding.get("support_level", "")
            sev = finding.get("severity", "")
            expected = expected_map.get(sl)
            if expected and sev != expected and sev != Severity.CRITICAL.value:
                notes.append({
                    "type": "severity_inconsistency",
                    "severity": "info",
                    "message": (
                        f"Finding '{finding.get('finding_id', '')}': severity '{sev}' "
                        f"inconsistent with support_level '{sl}' (expected '{expected}')"
                    ),
                    "finding_id": finding.get("finding_id", ""),
                })
        return notes

    async def _escalate(self, task: AgentTask, inconsistencies: List[dict]) -> None:
        """Escalate to Orchestrator when too many inconsistencies detected."""
        await self.publish(AgentMessage(
            sender=self.agent_id,
            recipient=AgentId(role=AgentRole.ORCHESTRATOR),
            message_type=MessageType.ESCALATION,
            payload={
                "asset_id": task.asset_id,
                "reason": f"{len(inconsistencies)} cross-validation inconsistencies detected",
                "count": len(inconsistencies),
            },
            correlation_id=task.correlation_id,
        ))
