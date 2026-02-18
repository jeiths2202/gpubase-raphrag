"""AnalysisService — bridges API ↔ Agent pipeline.

Responsibilities:
- Accept source file uploads, create workspace + kick off pipeline
- Track analysis progress (status, current agent, elapsed time)
- Provide SSE event stream for real-time updates
- Retrieve completed results + generated reports
"""

import asyncio
import json
import logging
import time
from datetime import datetime
from typing import Any, AsyncGenerator, Dict, List, Optional
from uuid import uuid4

from ..agents.orchestrator import OrchestratorAgent
from ..core.event_bus import EventBus
from ..core.pipeline import PipelineStateMachine
from ..core.protocol import AgentId, AgentMessage, AgentTask
from ..core.shared_state import SharedStateStore, SharedWorkspaceState
from ..models.enums import AgentRole, AssetType, MessageType, PipelineStatus
from ..models.reports import Report, ReportType
from ..reports.generator import ReportGenerator

logger = logging.getLogger(__name__)

# Asset type detection by file extension
_EXTENSION_MAP: Dict[str, AssetType] = {
    ".cbl": AssetType.COBOL,
    ".cob": AssetType.COBOL,
    ".cobol": AssetType.COBOL,
    ".jcl": AssetType.JCL,
    ".map": AssetType.MAP,
    ".bms": AssetType.MAP,
    ".asm": AssetType.ASSEMBLER,
    ".s": AssetType.ASSEMBLER,
}


class AnalysisSession:
    """In-memory tracking for an active analysis session."""

    def __init__(
        self,
        analysis_id: str,
        asset_id: str,
        tenant_id: str,
        file_name: str,
        asset_type: AssetType,
        vendors: List[str],
        options: dict,
    ) -> None:
        self.analysis_id = analysis_id
        self.asset_id = asset_id
        self.tenant_id = tenant_id
        self.file_name = file_name
        self.asset_type = asset_type
        self.vendors = vendors
        self.options = options
        self.started_at = time.monotonic()
        self.created_at = datetime.utcnow()
        self.reports: Dict[ReportType, Report] = {}


class AnalysisService:
    """Service layer for legacy modernization analysis."""

    def __init__(
        self,
        shared_state: SharedStateStore,
        event_bus: EventBus,
    ) -> None:
        self._shared_state = shared_state
        self._event_bus = event_bus
        self._pipeline = PipelineStateMachine()
        self._report_generator = ReportGenerator()
        self._sessions: Dict[str, AnalysisSession] = {}

    async def start_analysis(
        self,
        file_name: str,
        source_code: str,
        tenant_id: str,
        vendors: Optional[List[str]] = None,
        options: Optional[dict] = None,
        target_product: Optional[str] = None,
        target_version: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Create a workspace and start the analysis pipeline.

        Args:
            target_product: OpenFrame 제품 ID (e.g., 'osc', 'batch')
            target_version: 제품 버전 (e.g., '7.1', '8.0')

        Returns:
            Dict with analysis_id, status, message.
        """
        # Validate target product/version if provided
        if target_product and target_version:
            from ..capabilities.registry import get_product_registry
            registry = get_product_registry()
            if not registry.validate_product(target_product, target_version):
                available = registry.get_versions(target_product)
                return {
                    "analysis_id": "",
                    "status": "validation_error",
                    "message": (
                        f"Invalid product/version: {target_product} {target_version}. "
                        f"Available versions: {', '.join(available) if available else 'none'}"
                    ),
                    "estimated_duration_minutes": None,
                }

        analysis_id = str(uuid4())
        asset_id = f"asset_{analysis_id[:8]}"
        asset_type = self._detect_asset_type(file_name)
        vendors = vendors or ["openframe"]
        options = options or {}

        # Create workspace with target product info
        workspace = SharedWorkspaceState(
            asset_id=asset_id,
            tenant_id=tenant_id,
            asset_type=asset_type,
            file_path=file_name,
            file_name=file_name,
            loc_count=source_code.count("\n") + 1,
            target_product=target_product,
            target_version=target_version,
        )
        changed_fields = {
            "asset_id", "tenant_id", "asset_type", "file_path",
            "file_name", "loc_count",
        }
        if target_product:
            changed_fields.add("target_product")
        if target_version:
            changed_fields.add("target_version")

        await self._shared_state.save_workspace(
            workspace, AgentRole.ORCHESTRATOR,
            changed_fields=changed_fields,
        )

        # Track session
        session = AnalysisSession(
            analysis_id=analysis_id,
            asset_id=asset_id,
            tenant_id=tenant_id,
            file_name=file_name,
            asset_type=asset_type,
            vendors=vendors,
            options=options,
        )
        self._sessions[analysis_id] = session

        # Publish start task to orchestrator
        task = AgentTask(
            asset_id=asset_id,
            source_code=source_code,
            assigned_to=AgentRole.ORCHESTRATOR,
            metadata={
                "analysis_id": analysis_id,
                "vendors": vendors,
                "options": options,
                "target_product": target_product,
                "target_version": target_version,
            },
        )
        await self._event_bus.publish(
            "orchestrator",
            AgentMessage(
                sender=AgentId(role=AgentRole.ORCHESTRATOR),
                recipient=AgentId(role=AgentRole.ORCHESTRATOR),
                message_type=MessageType.TASK,
                payload=task.model_dump(),
                correlation_id=task.correlation_id,
            ),
        )

        logger.info(
            "Analysis started: id=%s, asset=%s, type=%s",
            analysis_id, asset_id, asset_type.value,
        )

        return {
            "analysis_id": analysis_id,
            "status": PipelineStatus.PENDING.value,
            "message": f"Analysis started for {file_name} ({asset_type.value})",
            "estimated_duration_minutes": self._estimate_duration(
                source_code, asset_type,
            ),
        }

    async def get_status(self, analysis_id: str) -> Dict[str, Any]:
        """Get current analysis status."""
        session = self._sessions.get(analysis_id)
        if not session:
            return {
                "analysis_id": analysis_id,
                "status": "not_found",
                "progress_percent": 0.0,
                "current_agent": None,
                "elapsed_seconds": 0.0,
            }

        workspace = await self._shared_state.get_workspace(session.asset_id)
        status = workspace.pipeline_status
        elapsed = time.monotonic() - session.started_at

        return {
            "analysis_id": analysis_id,
            "status": status.value,
            "progress_percent": self._calculate_progress(status),
            "current_agent": self._current_agent_name(status, workspace),
            "elapsed_seconds": round(elapsed, 1),
        }

    async def get_results(self, analysis_id: str) -> Dict[str, Any]:
        """Get analysis results including workspace state and reports."""
        session = self._sessions.get(analysis_id)
        if not session:
            return {"analysis_id": analysis_id, "error": "not_found"}

        workspace = await self._shared_state.get_workspace(session.asset_id)

        # Generate reports if not yet done
        if not session.reports and workspace.pipeline_status in (
            PipelineStatus.COMPLETED,
            PipelineStatus.REPORT_GENERATION,
        ):
            session.reports = await self._report_generator.generate_all(workspace)

        return {
            "analysis_id": analysis_id,
            "workspace": workspace.model_dump(),
            "reports": {
                rt.value: rpt.model_dump() for rt, rpt in session.reports.items()
            },
            "audit_trail": workspace.audit_trail,
        }

    async def stream_events(
        self,
        analysis_id: str,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """SSE event stream for real-time progress updates.

        Yields dicts with: event, data fields.
        """
        session = self._sessions.get(analysis_id)
        if not session:
            yield {"event": "error", "data": {"message": "Analysis not found"}}
            return

        last_status: Optional[PipelineStatus] = None

        while True:
            workspace = await self._shared_state.get_workspace(session.asset_id)
            status = workspace.pipeline_status

            if status != last_status:
                yield {
                    "event": "status_change",
                    "data": {
                        "status": status.value,
                        "progress_percent": self._calculate_progress(status),
                        "current_agent": self._current_agent_name(status, workspace),
                    },
                }
                last_status = status

            # Terminal states
            if status == PipelineStatus.COMPLETED:
                # Generate reports
                if not session.reports:
                    session.reports = await self._report_generator.generate_all(
                        workspace,
                    )
                yield {
                    "event": "completed",
                    "data": {
                        "status": "completed",
                        "total_findings": len(workspace.compatibility_findings),
                        "qa_passed": workspace.qa_passed,
                        "report_types": [
                            rt.value for rt in session.reports.keys()
                        ],
                    },
                }
                return

            if status == PipelineStatus.FAILED:
                yield {
                    "event": "failed",
                    "data": {
                        "status": "failed",
                        "errors": workspace.parse_errors[:5],
                    },
                }
                return

            if status == PipelineStatus.BLOCKED:
                yield {
                    "event": "blocked",
                    "data": {
                        "status": "blocked",
                        "qa_flags": workspace.qa_flags[:10],
                    },
                }

            await asyncio.sleep(1.0)

    async def get_report(
        self,
        analysis_id: str,
        report_type: ReportType,
    ) -> Optional[Report]:
        """Get a specific report by type."""
        session = self._sessions.get(analysis_id)
        if not session:
            return None

        # If report already cached
        if report_type in session.reports:
            return session.reports[report_type]

        # Generate on demand
        workspace = await self._shared_state.get_workspace(session.asset_id)
        report = await self._report_generator.generate_single(workspace, report_type)
        if report:
            session.reports[report_type] = report
        return report

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _detect_asset_type(file_name: str) -> AssetType:
        """Detect asset type from file extension."""
        lower = file_name.lower()
        for ext, atype in _EXTENSION_MAP.items():
            if lower.endswith(ext):
                return atype
        return AssetType.COBOL  # Default

    @staticmethod
    def _calculate_progress(status: PipelineStatus) -> float:
        """Map pipeline status to progress percentage."""
        progress_map: Dict[PipelineStatus, float] = {
            PipelineStatus.PENDING: 0.0,
            PipelineStatus.PARSING: 10.0,
            PipelineStatus.KNOWLEDGE_ENRICHMENT: 25.0,
            PipelineStatus.COMPATIBILITY_ANALYSIS: 40.0,
            PipelineStatus.RISK_ASSESSMENT: 55.0,
            PipelineStatus.REVIEWING: 65.0,
            PipelineStatus.QA_VALIDATION: 75.0,
            PipelineStatus.E2E_TESTING: 85.0,
            PipelineStatus.REPORT_GENERATION: 95.0,
            PipelineStatus.COMPLETED: 100.0,
            PipelineStatus.FAILED: 0.0,
            PipelineStatus.BLOCKED: 75.0,
        }
        return progress_map.get(status, 0.0)

    @staticmethod
    def _current_agent_name(
        status: PipelineStatus,
        workspace: SharedWorkspaceState,
    ) -> Optional[str]:
        """Get human-readable name of the currently active agent."""
        agent_names: Dict[PipelineStatus, str] = {
            PipelineStatus.PARSING: f"{workspace.asset_type.value.upper()} Expert",
            PipelineStatus.KNOWLEDGE_ENRICHMENT: "Legacy Knowledge Expert",
            PipelineStatus.COMPATIBILITY_ANALYSIS: "Competitor Intelligence",
            PipelineStatus.RISK_ASSESSMENT: "Risk Intelligence",
            PipelineStatus.REVIEWING: "Reviewer",
            PipelineStatus.QA_VALIDATION: "QA Agent",
            PipelineStatus.E2E_TESTING: "E2E Test Agent",
            PipelineStatus.REPORT_GENERATION: "Report Generator",
        }
        return agent_names.get(status)

    @staticmethod
    def _estimate_duration(source_code: str, asset_type: AssetType) -> int:
        """Rough duration estimate in minutes."""
        loc = source_code.count("\n") + 1
        # ~200 LOC/min base rate
        base_minutes = max(1, loc // 200)
        return min(base_minutes, 30)  # Cap at 30 min


# Singleton
_instance: Optional[AnalysisService] = None


def get_analysis_service() -> AnalysisService:
    """Get or create the singleton AnalysisService."""
    global _instance
    if _instance is None:
        from ..core.event_bus import EventBus
        from ..core.shared_state import SharedStateStore

        _instance = AnalysisService(
            shared_state=SharedStateStore(),
            event_bus=EventBus(),
        )
    return _instance
