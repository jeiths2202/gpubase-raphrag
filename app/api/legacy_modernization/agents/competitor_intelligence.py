"""Competitor Intelligence Agent - Multi-vendor compatibility comparison.

Compares feature support across 4 vendors:
- OpenFrame (TmaxSoft)
- IBM z/OS (native)
- Micro Focus Enterprise Server
- Fujitsu ASP (Interstage)

Output: VendorComparisonMatrix written to workspace.vendor_comparison
        CompatibilityFindings written to workspace.compatibility_findings
"""

import logging
from typing import List, Optional

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
from ..models.capability_model import (
    CapabilityModel,
    CompatibilityEngine,
    CompatibilityFinding,
    VendorComparisonMatrix,
)
from ..models.enums import AgentRole, AgentStatus, MessageType
from ..parsers.base import NormalizedFeature, TraceEvidence
from .base_agent import BaseAgent

logger = logging.getLogger(__name__)

# Default vendors for comparison
DEFAULT_VENDORS = ["openframe", "ibm_zos", "micro_focus", "fujitsu_asp"]


class CompetitorIntelligenceAgent(BaseAgent):
    """Vendor compatibility comparison agent."""

    def __init__(
        self,
        event_bus: EventBus,
        shared_state: SharedStateStore,
        capability_models: Optional[dict[str, CapabilityModel]] = None,
    ) -> None:
        super().__init__(AgentId(role=AgentRole.COMPETITOR_INTELLIGENCE), event_bus)
        self.shared_state = shared_state
        self.compatibility_engine = CompatibilityEngine(capability_models or {})

    async def execute(self, task: AgentTask) -> AgentResult:
        workspace = await self.shared_state.get_workspace(task.asset_id)

        # Deserialize features and evidence from workspace dicts
        features = self._deserialize_features(workspace.features)
        evidence = self._deserialize_evidence(workspace.trace_evidence)

        # Determine vendors from task metadata or use defaults
        vendors = task.metadata.get("vendors", DEFAULT_VENDORS)

        # Run compatibility analysis for all vendors
        findings: List[CompatibilityFinding] = await self.compatibility_engine.analyze(
            features=features,
            evidence=evidence,
            vendors=vendors,
        )

        # Build vendor comparison matrix
        matrix: VendorComparisonMatrix = self.compatibility_engine.build_comparison_matrix(
            asset_id=task.asset_id,
            findings=findings,
            vendors=vendors,
        )

        # Write results to workspace
        workspace.compatibility_findings = [f.model_dump() for f in findings]
        workspace.vendor_comparison = matrix.model_dump()
        await self.shared_state.save_workspace(
            workspace, AgentRole.COMPETITOR_INTELLIGENCE,
            changed_fields={"compatibility_findings", "vendor_comparison"},
        )

        # Publish completion
        await self.publish(AgentMessage(
            sender=self.agent_id,
            recipient=AgentId(role=AgentRole.ORCHESTRATOR),
            message_type=MessageType.RESULT,
            payload={
                "asset_id": task.asset_id,
                "findings_count": len(findings),
                "vendors_analyzed": vendors,
                "recommended_vendor": (
                    matrix.summary.recommended_vendor if matrix.summary else "unknown"
                ),
            },
            correlation_id=task.correlation_id,
        ))

        return AgentResult(
            agent_id=self.agent_id,
            status=AgentStatus.COMPLETED,
            workspace_id=task.asset_id,
            metadata={
                "findings_count": len(findings),
                "vendors": vendors,
            },
        )

    async def handle_change_request(self, cr: ChangeRequest) -> ChangeRequestResponse:
        """Competitor Intelligence can modify compatibility_findings and vendor_comparison."""
        allowed = {"compatibility_findings", "vendor_comparison"}
        if any(cr.target_field.startswith(f) for f in allowed):
            return ChangeRequestResponse(
                request_id=cr.request_id,
                approved=True,
                reason="Competitor Intelligence owns compatibility fields",
                agent_id=self.agent_id,
            )
        return ChangeRequestResponse(
            request_id=cr.request_id,
            approved=False,
            reason="Competitor Intelligence can only modify compatibility fields",
            agent_id=self.agent_id,
        )

    @staticmethod
    def _deserialize_features(feature_dicts: List[dict]) -> List[NormalizedFeature]:
        """Convert workspace dict features back to NormalizedFeature models."""
        features: List[NormalizedFeature] = []
        for fd in feature_dicts:
            try:
                features.append(NormalizedFeature.model_validate(fd))
            except Exception:
                logger.warning("Failed to deserialize feature: %s", fd.get("feature_id"))
        return features

    @staticmethod
    def _deserialize_evidence(evidence_dicts: List[dict]) -> List[TraceEvidence]:
        """Convert workspace dict evidence back to TraceEvidence models."""
        evidence: List[TraceEvidence] = []
        for ed in evidence_dicts:
            try:
                evidence.append(TraceEvidence.model_validate(ed))
            except Exception:
                logger.warning("Failed to deserialize evidence")
        return evidence
