"""LLM Risk Intelligence Agent - Risk scoring and migration cost estimation.

Constraints:
- JSON input only (no raw source code access)
- Cannot modify deterministic parser results
- Output limited to risk_scores and migration_cost fields

Input: SharedWorkspaceState features + compatibility_findings (JSON)
Output: RiskScoreSet + MigrationCostEstimate
"""

import logging
import math
from typing import Any, Dict, List, Optional

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
    EffortLevel,
    FeatureCategory,
    MessageType,
    Severity,
    SupportLevel,
)
from .base_agent import BaseAgent

logger = logging.getLogger(__name__)

# Effort → person-days mapping
_EFFORT_DAYS: Dict[str, float] = {
    EffortLevel.NONE.value: 0.0,
    EffortLevel.LOW.value: 0.5,
    EffortLevel.MEDIUM.value: 2.0,
    EffortLevel.HIGH.value: 5.0,
}

# Severity → risk weight
_SEVERITY_WEIGHT: Dict[str, float] = {
    Severity.INFO.value: 0.0,
    Severity.WARNING.value: 0.3,
    Severity.ERROR.value: 0.7,
    Severity.CRITICAL.value: 1.0,
}


class LLMRiskIntelligenceAgent(BaseAgent):
    """Risk scoring and cost estimation agent (JSON input only)."""

    def __init__(
        self,
        event_bus: EventBus,
        shared_state: SharedStateStore,
        llm_client: Optional[Any] = None,
    ) -> None:
        super().__init__(AgentId(role=AgentRole.RISK_INTELLIGENCE), event_bus)
        self.shared_state = shared_state
        self._llm_client = llm_client

    async def execute(self, task: AgentTask) -> AgentResult:
        workspace = await self.shared_state.get_workspace(task.asset_id)

        # Build JSON-only input (no raw source code)
        json_input = {
            "features": workspace.features,
            "findings": workspace.compatibility_findings,
            "stats": workspace.stats or {},
            "loc_count": workspace.loc_count,
            "asset_type": workspace.asset_type.value,
        }

        # Estimate risk scores (deterministic baseline + optional LLM enhancement)
        risk_scores = await self._estimate_risk(json_input)
        migration_cost = self._estimate_cost(json_input)

        # Write results
        workspace.risk_scores = risk_scores
        workspace.migration_cost = migration_cost
        await self.shared_state.save_workspace(
            workspace, AgentRole.RISK_INTELLIGENCE,
            changed_fields={"risk_scores", "migration_cost"},
        )

        # Publish completion
        await self.publish(AgentMessage(
            sender=self.agent_id,
            recipient=AgentId(role=AgentRole.ORCHESTRATOR),
            message_type=MessageType.RESULT,
            payload={
                "asset_id": task.asset_id,
                "overall_risk": risk_scores.get("overall_risk", 0.0),
                "total_person_days": migration_cost.get("total_person_days", 0.0),
            },
            correlation_id=task.correlation_id,
        ))

        return AgentResult(
            agent_id=self.agent_id,
            status=AgentStatus.COMPLETED,
            workspace_id=task.asset_id,
            metadata={
                "overall_risk": risk_scores.get("overall_risk", 0.0),
                "total_person_days": migration_cost.get("total_person_days", 0.0),
            },
        )

    async def handle_change_request(self, cr: ChangeRequest) -> ChangeRequestResponse:
        """Risk Intelligence can modify risk_scores and migration_cost."""
        allowed = {"risk_scores", "migration_cost"}
        if any(cr.target_field.startswith(f) for f in allowed):
            return ChangeRequestResponse(
                request_id=cr.request_id,
                approved=True,
                reason="Risk Intelligence owns risk and cost fields",
                agent_id=self.agent_id,
            )
        return ChangeRequestResponse(
            request_id=cr.request_id,
            approved=False,
            reason="Risk Intelligence can only modify risk/cost fields",
            agent_id=self.agent_id,
        )

    # --- Risk estimation ---

    async def _estimate_risk(self, json_input: dict) -> dict:
        """Calculate risk scores from findings and features.

        Returns RiskScoreSet as dict:
        - overall_risk: 0.0-1.0
        - complexity_score: 0.0-1.0
        - effort_score: 0.0-1.0
        - compatibility_score: 0.0-1.0
        - category_risks: {FeatureCategory: float}
        """
        findings = json_input.get("findings", [])
        features = json_input.get("features", [])
        loc = json_input.get("loc_count", 0)

        # Compatibility risk: ratio of unsupported/error findings
        total_findings = len(findings)
        if total_findings == 0:
            compat_risk = 0.0
        else:
            severe_count = sum(
                1 for f in findings
                if f.get("severity") in (Severity.ERROR.value, Severity.CRITICAL.value)
            )
            compat_risk = severe_count / total_findings

        # Complexity score: based on feature count and LOC
        feature_count = len(features)
        complexity = min(1.0, (feature_count / 100.0) * 0.5 + (loc / 10000.0) * 0.5)

        # Effort score: average effort level of findings
        effort_scores = [
            _EFFORT_DAYS.get(f.get("migration_effort", "none"), 0.0) / 5.0
            for f in findings
        ]
        effort_avg = sum(effort_scores) / max(len(effort_scores), 1)

        # Category-specific risks
        category_risks: Dict[str, float] = {}
        for finding in findings:
            feat = finding.get("feature", {})
            cat = feat.get("category", "unknown")
            weight = _SEVERITY_WEIGHT.get(finding.get("severity", "info"), 0.0)
            if cat not in category_risks:
                category_risks[cat] = 0.0
            category_risks[cat] = max(category_risks[cat], weight)

        # Overall risk: weighted combination
        overall = min(1.0, compat_risk * 0.4 + complexity * 0.3 + effort_avg * 0.3)

        risk_scores = {
            "overall_risk": round(overall, 3),
            "complexity_score": round(complexity, 3),
            "effort_score": round(effort_avg, 3),
            "compatibility_score": round(1.0 - compat_risk, 3),
            "category_risks": category_risks,
        }

        # Optional LLM enhancement
        if self._llm_client:
            try:
                llm_risk = await self._llm_enhance_risk(json_input, risk_scores)
                risk_scores.update(llm_risk)
            except Exception as exc:
                logger.warning("LLM risk enhancement failed: %s", exc)

        return risk_scores

    def _estimate_cost(self, json_input: dict) -> dict:
        """Calculate migration cost estimate from findings.

        Returns MigrationCostEstimate as dict:
        - total_person_days: float
        - breakdown: {FeatureCategory: float}
        - confidence: 0.0-1.0
        - assumptions: List[str]
        - risk_factors: List[str]
        """
        findings = json_input.get("findings", [])

        # Cost breakdown by category
        breakdown: Dict[str, float] = {}
        for finding in findings:
            feat = finding.get("feature", {})
            cat = feat.get("category", "unknown")
            effort_str = finding.get("migration_effort", EffortLevel.NONE.value)
            days = _EFFORT_DAYS.get(effort_str, 0.0)
            breakdown[cat] = breakdown.get(cat, 0.0) + days

        total = sum(breakdown.values())

        # LOC-based baseline cost (1 person-day per 200 LOC for complex migration)
        loc = json_input.get("loc_count", 0)
        loc_baseline = loc / 200.0

        # Use max of finding-based and LOC-based estimate
        total_days = max(total, loc_baseline)

        # Confidence based on data quality
        features_count = len(json_input.get("features", []))
        findings_count = len(findings)
        coverage = findings_count / max(features_count, 1)
        confidence = min(1.0, coverage * 0.8 + 0.2)

        assumptions = [
            "Cost based on individual feature migration effort estimates",
            f"LOC baseline: {loc} lines / 200 = {loc_baseline:.1f} person-days",
            "Does not include testing, deployment, or training costs",
            "Assumes experienced migration engineers",
        ]

        risk_factors: List[str] = []
        if any(f.get("severity") == Severity.CRITICAL.value for f in findings):
            risk_factors.append("Critical severity findings may require architectural changes")
        if features_count > 50:
            risk_factors.append(f"High feature count ({features_count}) increases integration complexity")

        return {
            "total_person_days": round(total_days, 1),
            "breakdown": breakdown,
            "confidence": round(confidence, 3),
            "assumptions": assumptions,
            "risk_factors": risk_factors,
        }

    async def _llm_enhance_risk(self, json_input: dict, base_risk: dict) -> dict:
        """Optional LLM enhancement for risk estimation."""
        # Placeholder for vLLM integration
        return {}
