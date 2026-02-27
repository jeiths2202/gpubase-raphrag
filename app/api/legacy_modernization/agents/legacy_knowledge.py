"""Legacy Knowledge Expert - LLM-assisted dialect analysis and pattern matching.

Responsibilities:
- Dialect-specific syntax analysis (LLM-assisted)
- Idiomatic pattern recognition (e.g., "WORKING-STORAGE SECTION level 88 patterns")
- Migration pattern matching from historical case database

Constraints:
- READ-ONLY: Cannot modify parser results (ast, features, trace_evidence)
- LLM output is attached as annotations only
- If changes are needed, must submit a change_request
"""

import logging
from typing import Any, Dict, List, Optional
from uuid import uuid4

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
from ..models.enums import AgentRole, AgentStatus, MessageType
from .base_agent import BaseAgent

logger = logging.getLogger(__name__)

# Known COBOL dialect patterns that require special analysis
_DIALECT_PATTERNS: Dict[str, List[Dict[str, str]]] = {
    "ibm_enterprise": [
        {"pattern": "EXEC SQL", "category": "db2", "note": "DB2 embedded SQL"},
        {"pattern": "EXEC CICS", "category": "cics", "note": "CICS transaction commands"},
        {"pattern": "EXEC DLI", "category": "ims", "note": "IMS/DLI database calls"},
        {"pattern": "GOBACK", "category": "flow_control", "note": "IBM GOBACK (vs STOP RUN)"},
    ],
    "micro_focus": [
        {"pattern": ">>DEFINE", "category": "special", "note": "Micro Focus compiler directive"},
        {"pattern": "$SET", "category": "special", "note": "Micro Focus $SET directive"},
    ],
    "fujitsu": [
        {"pattern": "EXIT PROGRAM", "category": "flow_control", "note": "Fujitsu EXIT PROGRAM variant"},
    ],
}

# Known migration patterns from historical case database
_MIGRATION_PATTERNS: List[Dict[str, Any]] = [
    {
        "pattern_id": "MP-001",
        "name": "CICS_SEND_MAP_TO_WEB",
        "trigger_features": ["cics", "screen_layout"],
        "description": "CICS SEND MAP can be migrated to web-based screen rendering",
        "recommendation": "Use OpenFrame CICS web bridge for screen-to-HTML conversion",
    },
    {
        "pattern_id": "MP-002",
        "name": "DB2_TO_TIBERO",
        "trigger_features": ["db2"],
        "description": "DB2 SQL can be migrated to Tibero with minor syntax adjustments",
        "recommendation": "Most DB2 SQL is compatible; check MERGE and LATERAL JOIN usage",
    },
    {
        "pattern_id": "MP-003",
        "name": "IMS_DLI_TO_HIDB",
        "trigger_features": ["ims"],
        "description": "IMS/DLI calls can be migrated to OpenFrame HIDB",
        "recommendation": "Verify PSB/DBD configurations are converted using dsmigout",
    },
    {
        "pattern_id": "MP-004",
        "name": "VSAM_TO_TSAM",
        "trigger_features": ["vsam"],
        "description": "VSAM datasets migrate to OpenFrame TSAM or Tibero VSAM support",
        "recommendation": "Use dsmigin for VSAM dataset migration; verify KSDS key definitions",
    },
    {
        "pattern_id": "MP-005",
        "name": "JES2_TO_TJES",
        "trigger_features": ["jes_control"],
        "description": "JES2/JES3 controls migrate to TJES (Tmax Job Entry Subsystem)",
        "recommendation": "Map JES JECL statements to TJES equivalents; check spool configuration",
    },
]


class LegacyKnowledgeExpert(BaseAgent):
    """LLM-assisted legacy knowledge analysis — read-only to parser data."""

    def __init__(
        self,
        event_bus: EventBus,
        shared_state: SharedStateStore,
        llm_client: Optional[Any] = None,
    ) -> None:
        super().__init__(AgentId(role=AgentRole.LEGACY_KNOWLEDGE), event_bus)
        self.shared_state = shared_state
        self._llm_client = llm_client  # vLLM client for dialect analysis

    async def execute(self, task: AgentTask) -> AgentResult:
        workspace = await self.shared_state.get_workspace(task.asset_id)

        annotations: List[dict] = list(workspace.annotations)

        # 1. Dialect-specific pattern analysis
        dialect = workspace.dialect or "ibm_enterprise"
        dialect_annotations = self._analyze_dialect_patterns(
            workspace.features, dialect,
        )
        annotations.extend(dialect_annotations)

        # 2. Migration pattern matching
        pattern_annotations = self._match_migration_patterns(workspace.features)
        annotations.extend(pattern_annotations)

        # 3. LLM-assisted analysis (if client available)
        if self._llm_client:
            llm_annotations = await self._llm_analyze(
                workspace.features, workspace.ast, dialect,
            )
            annotations.extend(llm_annotations)

        # Write annotations (annotations field is owned by LEGACY_KNOWLEDGE)
        workspace.annotations = annotations
        await self.shared_state.save_workspace(
            workspace, AgentRole.LEGACY_KNOWLEDGE,
            changed_fields={"annotations"},
        )

        # Publish completion
        await self.publish(AgentMessage(
            sender=self.agent_id,
            recipient=AgentId(role=AgentRole.ORCHESTRATOR),
            message_type=MessageType.RESULT,
            payload={
                "asset_id": task.asset_id,
                "annotations_added": len(annotations) - len(workspace.annotations) + len(annotations),
                "dialect": dialect,
                "patterns_matched": len(pattern_annotations),
            },
            correlation_id=task.correlation_id,
        ))

        return AgentResult(
            agent_id=self.agent_id,
            status=AgentStatus.COMPLETED,
            workspace_id=task.asset_id,
            metadata={
                "annotations_count": len(annotations),
                "dialect": dialect,
            },
        )

    async def handle_change_request(self, cr: ChangeRequest) -> ChangeRequestResponse:
        """Legacy Knowledge can only modify annotations."""
        if cr.target_field.startswith("annotations"):
            return ChangeRequestResponse(
                request_id=cr.request_id,
                approved=True,
                reason="Legacy Knowledge Expert can modify annotations",
                agent_id=self.agent_id,
            )
        return ChangeRequestResponse(
            request_id=cr.request_id,
            approved=False,
            reason="Legacy Knowledge Expert is read-only for non-annotation fields",
            agent_id=self.agent_id,
        )

    # --- Private helpers ---

    def _analyze_dialect_patterns(
        self, features: List[dict], dialect: str,
    ) -> List[dict]:
        """Match features against known dialect-specific patterns."""
        annotations: List[dict] = []
        patterns = _DIALECT_PATTERNS.get(dialect, [])

        feature_names = {f.get("name", "").upper() for f in features}
        for dp in patterns:
            if dp["pattern"].upper() in feature_names:
                annotations.append({
                    "annotation_id": str(uuid4()),
                    "source": "rule",
                    "type": "dialect_pattern",
                    "text": f"[{dialect}] {dp['note']}",
                    "category": dp["category"],
                    "confidence": 0.95,
                    "metadata": {"dialect": dialect, "pattern": dp["pattern"]},
                })

        return annotations

    def _match_migration_patterns(self, features: List[dict]) -> List[dict]:
        """Match features against historical migration pattern database."""
        annotations: List[dict] = []
        feature_categories = {f.get("category", "") for f in features}

        for mp in _MIGRATION_PATTERNS:
            if any(trigger in feature_categories for trigger in mp["trigger_features"]):
                annotations.append({
                    "annotation_id": str(uuid4()),
                    "source": "rule",
                    "type": "migration_pattern",
                    "text": f"[{mp['pattern_id']}] {mp['description']}",
                    "recommendation": mp["recommendation"],
                    "confidence": 0.9,
                    "metadata": {
                        "pattern_id": mp["pattern_id"],
                        "pattern_name": mp["name"],
                    },
                })

        return annotations

    async def _llm_analyze(
        self,
        features: List[dict],
        ast: Optional[dict],
        dialect: str,
    ) -> List[dict]:
        """Use LLM to analyze complex dialect-specific patterns.

        LLM output is strictly annotation-only (no parser field modifications).
        """
        annotations: List[dict] = []

        # Prepare JSON-serializable input for LLM
        feature_summary = [
            {"name": f.get("name"), "category": f.get("category")}
            for f in features[:50]  # Limit to 50 features for context window
        ]

        try:
            prompt = (
                f"Analyze these {dialect} COBOL features for migration complexity.\n"
                f"Features: {feature_summary}\n"
                f"Identify any unusual patterns, deprecated constructs, or "
                f"migration-critical idioms. Respond in JSON array format."
            )

            # LLM call placeholder — actual integration via vLLM client
            if self._llm_client:
                response = await self._llm_client.generate(prompt)
                # Parse and validate LLM response
                if isinstance(response, list):
                    for item in response:
                        annotations.append({
                            "annotation_id": str(uuid4()),
                            "source": "llm",
                            "type": "dialect_analysis",
                            "text": str(item.get("analysis", "")),
                            "confidence": 0.7,  # LLM output has lower confidence
                            "metadata": {"llm_model": "vllm_qlora"},
                        })
        except Exception as exc:
            logger.warning("LLM analysis failed: %s", exc)
            annotations.append({
                "annotation_id": str(uuid4()),
                "source": "llm",
                "type": "error",
                "text": f"LLM analysis failed: {exc}",
                "confidence": 0.0,
            })

        return annotations
