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
from ..core.protocol import AgentId, AgentMessage, AgentResult, AgentTask
from ..core.shared_state import SharedStateStore, SharedWorkspaceState
from ..models.enums import AgentRole, AgentStatus, AssetType, MessageType, PipelineStatus
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

# XSP JCL statement prefixes (Fujitsu OSIV/XSP)
# XSP uses "\" prefix instead of "//" for JOB/EX/FD/JEND etc.
_XSP_STMT_PATTERNS = {r"\ JOB", r"\ EX ", r"\ FD ", r"\ JEND", "/EXPAN", "/ SET", "/ DEFEND"}


def _is_xsp_jcl(upper_source: str) -> bool:
    """Detect Fujitsu XSP JCL by characteristic statement prefixes."""
    return any(pat in upper_source for pat in _XSP_STMT_PATTERNS)


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


class BatchSession:
    """In-memory tracking for a multi-file batch analysis."""

    def __init__(self, batch_id: str, file_names: List[str]) -> None:
        self.batch_id = batch_id
        self.file_names = file_names
        self.analysis_map: Dict[str, str] = {}  # file_name → analysis_id
        self.started_at = time.monotonic()
        self.created_at = datetime.utcnow()


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
        self._batches: Dict[str, BatchSession] = {}
        self._legacy_repo = None  # Lazy-loaded PostgreSQL repository

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
        asset_type = self._detect_asset_type(file_name, source_code)
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

        # Create task for pipeline
        task = AgentTask(
            asset_id=asset_id,
            source_code=source_code,
            file_path=file_name,
            assigned_to=AgentRole.ORCHESTRATOR,
            metadata={
                "analysis_id": analysis_id,
                "vendors": vendors,
                "options": options,
                "target_product": target_product,
                "target_version": target_version,
            },
        )

        logger.info(
            "Analysis started: id=%s, asset=%s, type=%s",
            analysis_id, asset_id, asset_type.value,
        )

        # Run pipeline in background (no event bus consumer needed)
        bg_task = asyncio.create_task(
            self._run_pipeline(session, task, workspace),
            name=f"pipeline-{analysis_id[:8]}",
        )
        bg_task.add_done_callback(self._pipeline_done_callback)

        return {
            "analysis_id": analysis_id,
            "status": PipelineStatus.PENDING.value,
            "message": f"Analysis started for {file_name} ({asset_type.value})",
            "estimated_duration_minutes": self._estimate_duration(
                source_code, asset_type,
            ),
        }

    @staticmethod
    def _pipeline_done_callback(task: asyncio.Task) -> None:
        """Log unhandled exceptions from background pipeline tasks."""
        if task.cancelled():
            logger.warning("Pipeline task %s was cancelled", task.get_name())
            return
        exc = task.exception()
        if exc:
            logger.error(
                "Pipeline task %s failed with unhandled exception: %s",
                task.get_name(), exc, exc_info=exc,
            )

    async def _run_pipeline(
        self,
        session: AnalysisSession,
        task: AgentTask,
        workspace: SharedWorkspaceState,
    ) -> None:
        """Run the analysis pipeline sequentially in background.

        Pipeline stages:
        PENDING → PARSING → KNOWLEDGE_ENRICHMENT → COMPATIBILITY_ANALYSIS →
        RISK_ASSESSMENT → REVIEWING → QA_VALIDATION → E2E_TESTING →
        REPORT_GENERATION → COMPLETED
        """
        from ..agents.domain.cobol_expert import COBOLExpertAgent
        from ..agents.domain.jcl_expert import JCLExpertAgent
        from ..agents.domain.map_expert import MAPExpertAgent
        from ..agents.domain.asm_expert import ASMExpertAgent

        try:
            # --- Phase 1: PARSING ---
            self._pipeline.transition(workspace, PipelineStatus.PARSING)
            await self._shared_state.save_workspace(
                workspace, AgentRole.ORCHESTRATOR,
                changed_fields={"pipeline_status"},
            )

            # Select domain expert by asset type
            expert_map = {
                AssetType.COBOL: lambda: COBOLExpertAgent(
                    self._event_bus, self._shared_state,
                ),
                AssetType.JCL: lambda: JCLExpertAgent(
                    self._event_bus, self._shared_state,
                ),
                AssetType.MAP: lambda: MAPExpertAgent(
                    self._event_bus, self._shared_state,
                ),
                AssetType.ASSEMBLER: lambda: ASMExpertAgent(
                    self._event_bus, self._shared_state,
                ),
            }

            expert_factory = expert_map.get(session.asset_type)
            if not expert_factory:
                raise ValueError(f"No expert for asset type: {session.asset_type}")

            expert = expert_factory()
            parse_result = await expert.execute(task)

            # Refresh workspace after expert modified it (version incremented)
            workspace = await self._shared_state.get_workspace(task.asset_id)

            if parse_result.status != AgentStatus.COMPLETED:
                self._pipeline.transition(workspace, PipelineStatus.FAILED)
                await self._shared_state.save_workspace(
                    workspace, AgentRole.ORCHESTRATOR,
                    changed_fields={"pipeline_status"},
                )
                return

            # --- Phase 2..7: Specialist agents ---
            specialist_stages = [
                (PipelineStatus.KNOWLEDGE_ENRICHMENT, AgentRole.LEGACY_KNOWLEDGE),
                (PipelineStatus.COMPATIBILITY_ANALYSIS, AgentRole.COMPETITOR_INTELLIGENCE),
                (PipelineStatus.RISK_ASSESSMENT, AgentRole.RISK_INTELLIGENCE),
                (PipelineStatus.REVIEWING, AgentRole.REVIEWER),
                (PipelineStatus.QA_VALIDATION, AgentRole.QA),
                (PipelineStatus.E2E_TESTING, AgentRole.E2E_TEST),
            ]

            for stage_status, agent_role in specialist_stages:
                self._pipeline.transition(workspace, stage_status)
                await self._shared_state.save_workspace(
                    workspace, AgentRole.ORCHESTRATOR,
                    changed_fields={"pipeline_status"},
                )

                agent = self._create_agent(agent_role)
                if agent:
                    stage_task = AgentTask(
                        asset_id=task.asset_id,
                        source_code=task.source_code,
                        file_path=task.file_path,
                        assigned_to=agent_role,
                        metadata=task.metadata,
                    )
                    result = await agent.execute(stage_task)
                    # Refresh workspace after agent modified it
                    workspace = await self._shared_state.get_workspace(task.asset_id)
                    if result.status == AgentStatus.ERROR:
                        logger.warning(
                            "Agent %s returned error in stage %s, continuing...",
                            agent_role.value, stage_status.value,
                        )

            # --- Phase 8: REPORT_GENERATION ---
            self._pipeline.transition(workspace, PipelineStatus.REPORT_GENERATION)
            await self._shared_state.save_workspace(
                workspace, AgentRole.ORCHESTRATOR,
                changed_fields={"pipeline_status"},
            )

            session.reports = await self._report_generator.generate_all(workspace)

            # Refresh workspace for final transition
            workspace = await self._shared_state.get_workspace(task.asset_id)

            # --- COMPLETED ---
            self._pipeline.transition(workspace, PipelineStatus.COMPLETED)
            await self._shared_state.save_workspace(
                workspace, AgentRole.ORCHESTRATOR,
                changed_fields={"pipeline_status"},
            )

            logger.info(
                "Pipeline completed: asset=%s, features=%d",
                task.asset_id, len(workspace.features),
            )

            # Persist to PostgreSQL (non-blocking, failure won't affect pipeline)
            await self._persist_to_db(session, workspace)

        except Exception as exc:
            logger.error("Pipeline failed for %s: %s", task.asset_id, exc, exc_info=True)
            # Refresh workspace to get latest version for failure status save
            try:
                workspace = await self._shared_state.get_workspace(task.asset_id)
            except Exception:
                pass  # use stale workspace as last resort
            try:
                self._pipeline.transition(workspace, PipelineStatus.FAILED)
            except ValueError:
                workspace.pipeline_status = PipelineStatus.FAILED
            try:
                await self._shared_state.save_workspace(
                    workspace, AgentRole.ORCHESTRATOR,
                    changed_fields={"pipeline_status"},
                )
            except Exception as save_exc:
                logger.error("Failed to save FAILED status: %s", save_exc)

    async def _get_legacy_repo(self):
        """Lazy-load the PostgreSQL legacy analysis repository."""
        if self._legacy_repo is None:
            try:
                from ...infrastructure.postgres.legacy_analysis_repository import LegacyAnalysisRepository
                from ...core.deps import get_postgres_pool
                pool = await get_postgres_pool()
                if pool:
                    self._legacy_repo = LegacyAnalysisRepository(pool)
                    await self._legacy_repo.initialize()
                    logger.info("Legacy analysis repo initialized successfully")
                else:
                    logger.warning("PostgreSQL pool is None, cannot create legacy repo")
            except Exception as exc:
                logger.warning("Legacy analysis repo not available: %s", exc, exc_info=True)
        return self._legacy_repo

    async def _persist_to_db(
        self,
        session: AnalysisSession,
        workspace: SharedWorkspaceState,
    ) -> None:
        """Persist completed analysis results to PostgreSQL."""
        repo = await self._get_legacy_repo()
        if not repo:
            logger.warning("No legacy repo available, skipping DB persistence")
            return

        logger.info("Starting DB persistence for analysis %s", session.analysis_id)

        try:
            from ..reports.incompatibility_builder import get_incompatibility_builder

            features = workspace.features
            findings = workspace.compatibility_findings
            # STMT_ERROR 피처도 비호환으로 카운트 (parse error = HIGH risk)
            error_feature_count = sum(
                1 for feat in features
                if isinstance(feat, dict) and feat.get("subcategory") == "STMT_ERROR"
            )
            incomp = len(findings) + error_feature_count
            supp = max(len(features) - incomp, 0)
            rate = round((supp / max(len(features), 1)) * 100, 1)

            risk_counts = {"HIGH": 0, "MEDIUM": 0, "LOW": 0}
            for f in findings:
                sev = f.get("severity", "info").upper() if isinstance(f, dict) else "LOW"
                if sev in risk_counts:
                    risk_counts[sev] += 1
            # STMT_ERROR는 HIGH risk로 카운트
            risk_counts["HIGH"] += error_feature_count

            # Build incompatibility report
            incompat_report = None
            try:
                builder = get_incompatibility_builder()
                incompat_report = await builder.build(workspace.model_dump())
            except Exception:
                pass

            elapsed = time.monotonic() - session.started_at

            # Determine batch_id if this session belongs to a batch
            batch_id = None
            for bid, batch in self._batches.items():
                if session.analysis_id in batch.analysis_map.values():
                    batch_id = bid
                    break

            # Serialize reports (mode='json' converts datetime → ISO string)
            reports_dict = {}
            for rt, rpt in session.reports.items():
                try:
                    reports_dict[rt.value] = rpt.model_dump(mode='json')
                except Exception:
                    reports_dict[rt.value if hasattr(rt, 'value') else str(rt)] = str(rpt)

            data = {
                "id": session.analysis_id,
                "user_id": session.tenant_id,
                "batch_id": batch_id,
                "file_name": session.file_name,
                "asset_type": session.asset_type.value,
                "loc_count": workspace.loc_count,
                "target_product": workspace.target_product,
                "target_version": workspace.target_version,
                "vendors": session.vendors,
                "status": "completed",
                "total_features": len(features),
                "supported_count": supp,
                "incompatible_count": incomp,
                "support_rate": rate,
                "risk_high": risk_counts["HIGH"],
                "risk_medium": risk_counts["MEDIUM"],
                "risk_low": risk_counts["LOW"],
                "incompatibility_report": incompat_report,
                "reports": reports_dict,
                "analysis_duration_seconds": round(elapsed, 1),
                "pipeline_status": workspace.pipeline_status.value,
                "created_at": session.created_at,
            }

            await repo.save_analysis(data)
            logger.info("Persisted analysis %s to PostgreSQL", session.analysis_id)

        except Exception as exc:
            logger.error(
                "Failed to persist analysis %s to DB: %s",
                session.analysis_id, exc, exc_info=True,
            )

    def _create_agent(self, role: AgentRole) -> Optional[Any]:
        """Create an agent instance by role. Returns None if not available."""
        from ..agents.legacy_knowledge import LegacyKnowledgeExpert
        from ..agents.competitor_intelligence import CompetitorIntelligenceAgent
        from ..agents.risk_intelligence import LLMRiskIntelligenceAgent
        from ..agents.reviewer import ReviewerAgent
        from ..agents.qa_agent import QAAgent
        from ..agents.e2e_test import E2ETestAgent

        agent_map = {
            AgentRole.LEGACY_KNOWLEDGE: lambda: LegacyKnowledgeExpert(
                self._event_bus, self._shared_state,
            ),
            AgentRole.COMPETITOR_INTELLIGENCE: lambda: CompetitorIntelligenceAgent(
                self._event_bus, self._shared_state,
            ),
            AgentRole.RISK_INTELLIGENCE: lambda: LLMRiskIntelligenceAgent(
                self._event_bus, self._shared_state,
            ),
            AgentRole.REVIEWER: lambda: ReviewerAgent(
                self._event_bus, self._shared_state,
            ),
            AgentRole.QA: lambda: QAAgent(
                self._event_bus, self._shared_state,
            ),
            AgentRole.E2E_TEST: lambda: E2ETestAgent(
                self._event_bus, self._shared_state,
            ),
        }

        factory = agent_map.get(role)
        if factory:
            try:
                return factory()
            except Exception as exc:
                logger.warning("Failed to create agent %s: %s", role.value, exc)
        return None

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
    # Batch analysis
    # ------------------------------------------------------------------

    async def start_batch_analysis(
        self,
        files: List[Dict[str, str]],
        tenant_id: str,
        target_product: Optional[str] = None,
        target_version: Optional[str] = None,
        vendors: Optional[List[str]] = None,
        options: Optional[dict] = None,
    ) -> Dict[str, Any]:
        """Start analysis for multiple files concurrently.

        Args:
            files: List of {"file_name": str, "source_code": str} dicts.

        Returns:
            Dict with batch_id, total_files, analysis_ids, status, message.
        """
        batch_id = str(uuid4())
        file_names = [f["file_name"] for f in files]
        batch = BatchSession(batch_id, file_names)

        sem = asyncio.Semaphore(3)

        async def _analyze_one(file_item: Dict[str, str]) -> str:
            async with sem:
                result = await self.start_analysis(
                    file_name=file_item["file_name"],
                    source_code=file_item["source_code"],
                    tenant_id=tenant_id,
                    target_product=target_product,
                    target_version=target_version,
                    vendors=vendors,
                    options=options,
                )
                return result["analysis_id"]

        analysis_ids = await asyncio.gather(
            *[_analyze_one(f) for f in files],
        )

        for fname, aid in zip(file_names, analysis_ids):
            batch.analysis_map[fname] = aid

        self._batches[batch_id] = batch
        logger.info("Batch started: id=%s, files=%d", batch_id, len(files))

        return {
            "batch_id": batch_id,
            "total_files": len(files),
            "analysis_ids": list(analysis_ids),
            "status": "started",
            "message": f"Batch analysis started for {len(files)} files",
        }

    async def get_batch_status(self, batch_id: str) -> Optional[Dict[str, Any]]:
        """Get current batch progress."""
        batch = self._batches.get(batch_id)
        if not batch:
            return None

        file_statuses = []
        completed = 0
        failed = 0
        in_progress = 0

        for fname, aid in batch.analysis_map.items():
            status_info = await self.get_status(aid)
            st = status_info.get("status", "pending")
            progress = status_info.get("progress_percent", 0.0)

            if st == "completed":
                completed += 1
            elif st == "failed":
                failed += 1
            else:
                in_progress += 1

            file_statuses.append({
                "file_name": fname,
                "analysis_id": aid,
                "status": st,
                "progress_percent": progress,
            })

        total = len(batch.file_names)
        overall = (completed / max(total, 1)) * 100

        return {
            "batch_id": batch_id,
            "total_files": total,
            "completed": completed,
            "failed": failed,
            "in_progress": in_progress,
            "overall_progress": round(overall, 1),
            "file_statuses": file_statuses,
        }

    async def get_batch_results(self, batch_id: str) -> Optional[Dict[str, Any]]:
        """Get full batch results with summary and per-file details."""
        batch = self._batches.get(batch_id)
        if not batch:
            return None

        from ..reports.incompatibility_builder import get_incompatibility_builder
        builder = get_incompatibility_builder()

        file_results = []
        total_features = 0
        total_supported = 0
        total_incompatible = 0
        risk_total = {"HIGH": 0, "MEDIUM": 0, "LOW": 0}
        all_incompatible_items: List[Dict[str, Any]] = []

        for fname, aid in batch.analysis_map.items():
            result = await self.get_results(aid)
            if "error" in result:
                file_results.append({
                    "file_name": fname,
                    "analysis_id": aid,
                    "status": "failed",
                    "asset_type": "",
                    "total_features": 0,
                    "supported_count": 0,
                    "incompatible_count": 0,
                    "support_rate": 0.0,
                    "risk_summary": {"HIGH": 0, "MEDIUM": 0, "LOW": 0},
                    "incompatibility_report": None,
                })
                continue

            ws = result.get("workspace", {})
            features = ws.get("features", [])
            findings = ws.get("compatibility_findings", [])

            risk_counts = {"HIGH": 0, "MEDIUM": 0, "LOW": 0}
            for f in findings:
                sev = f.get("severity", "info").upper()
                if sev in risk_counts:
                    risk_counts[sev] += 1

            # STMT_ERROR 피처도 비호환으로 카운트
            error_feature_count = sum(
                1 for feat in features
                if isinstance(feat, dict) and feat.get("subcategory") == "STMT_ERROR"
            )
            incomp = len(findings) + error_feature_count
            supp = max(len(features) - incomp, 0)
            rate = round((supp / max(len(features), 1)) * 100, 1)
            risk_counts["HIGH"] += error_feature_count

            # Build incompatibility report
            incompat_report = await builder.build(ws)

            asset_type = ws.get("asset_type", "")
            if isinstance(asset_type, dict):
                asset_type = asset_type.get("value", asset_type)

            file_results.append({
                "file_name": fname,
                "analysis_id": aid,
                "status": "completed",
                "asset_type": str(asset_type),
                "total_features": len(features),
                "supported_count": supp,
                "incompatible_count": incomp,
                "support_rate": rate,
                "risk_summary": risk_counts,
                "incompatibility_report": incompat_report,
            })

            total_features += len(features)
            total_supported += supp
            total_incompatible += incomp
            for k in risk_total:
                risk_total[k] += risk_counts.get(k, 0)

            for f in findings:
                feat = f.get("feature", {})
                feat_name = feat.get("name", "unknown") if isinstance(feat, dict) else str(feat)
                all_incompatible_items.append({
                    "file_name": fname,
                    "item": feat_name,
                    "risk": f.get("severity", "info").upper(),
                    "description": f.get("description", ""),
                })

        # Sort by risk priority
        risk_order = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}
        all_incompatible_items.sort(key=lambda x: risk_order.get(x["risk"], 3))

        overall_rate = round(
            (total_supported / max(total_features, 1)) * 100, 1,
        )
        completed_count = sum(1 for fr in file_results if fr["status"] == "completed")
        failed_count = sum(1 for fr in file_results if fr["status"] == "failed")

        summary = {
            "batch_id": batch_id,
            "total_files": len(batch.file_names),
            "completed_files": completed_count,
            "failed_files": failed_count,
            "total_features": total_features,
            "total_supported": total_supported,
            "total_incompatible": total_incompatible,
            "overall_support_rate": overall_rate,
            "risk_breakdown": risk_total,
            "top_incompatible_items": all_incompatible_items[:10],
        }

        return {
            "batch_id": batch_id,
            "summary": summary,
            "file_results": file_results,
        }

    async def stream_batch_events(
        self,
        batch_id: str,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """SSE event stream for batch analysis progress."""
        batch = self._batches.get(batch_id)
        if not batch:
            yield {"event": "error", "data": {"message": "Batch not found"}}
            return

        completed_files: set = set()
        failed_files: set = set()

        while True:
            all_done = True
            for fname, aid in batch.analysis_map.items():
                if fname in completed_files or fname in failed_files:
                    continue

                status_info = await self.get_status(aid)
                st = status_info.get("status", "pending")
                progress = status_info.get("progress_percent", 0.0)

                if st == "completed":
                    # Get results for support_rate
                    results = await self.get_results(aid)
                    ws = results.get("workspace", {})
                    features = ws.get("features", [])
                    findings = ws.get("compatibility_findings", [])
                    # STMT_ERROR 피처도 비호환으로 카운트
                    error_feat_count = sum(
                        1 for feat in features
                        if isinstance(feat, dict) and feat.get("subcategory") == "STMT_ERROR"
                    )
                    incomp = len(findings) + error_feat_count
                    supp = max(len(features) - incomp, 0)
                    rate = round((supp / max(len(features), 1)) * 100, 1)

                    yield {
                        "event": "file_completed",
                        "data": {
                            "batch_id": batch_id,
                            "file_name": fname,
                            "analysis_id": aid,
                            "support_rate": rate,
                            "incompatible_count": incomp,
                        },
                    }
                    completed_files.add(fname)
                elif st == "failed":
                    yield {
                        "event": "file_failed",
                        "data": {
                            "batch_id": batch_id,
                            "file_name": fname,
                            "analysis_id": aid,
                            "error": "Analysis failed",
                        },
                    }
                    failed_files.add(fname)
                else:
                    all_done = False
                    yield {
                        "event": "file_progress",
                        "data": {
                            "batch_id": batch_id,
                            "file_name": fname,
                            "analysis_id": aid,
                            "progress_percent": progress,
                            "current_agent": status_info.get("current_agent"),
                        },
                    }

            if all_done:
                total = len(batch.file_names)
                completed = len(completed_files)
                failed = len(failed_files)
                overall_rate = round((completed / max(total, 1)) * 100, 1)
                yield {
                    "event": "batch_completed",
                    "data": {
                        "batch_id": batch_id,
                        "total_files": total,
                        "completed": completed,
                        "failed": failed,
                        "overall_progress": overall_rate,
                    },
                }
                return

            await asyncio.sleep(1.0)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _detect_asset_type(file_name: str, source_code: str = "") -> AssetType:
        """Detect asset type from file extension, with content-based fallback."""
        lower = file_name.lower()
        for ext, atype in _EXTENSION_MAP.items():
            if lower.endswith(ext):
                return atype
        # Content-based fallback for ambiguous extensions
        if source_code:
            asset = AnalysisService._detect_from_content(source_code)
            if asset:
                return asset
        return AssetType.COBOL  # Default

    @staticmethod
    def _detect_from_content(source_code: str) -> Optional[AssetType]:
        """Detect asset type from source content heuristics."""
        upper = source_code[:1000].upper()
        # XSP JCL: \ JOB, \ EX, \ FD, /EXPAN, / SET, / DEFEND
        if _is_xsp_jcl(upper):
            return AssetType.JCL
        # MVS JCL: // prefix
        if upper.lstrip().startswith("//") and ("JOB" in upper or "EXEC" in upper):
            return AssetType.JCL
        # COBOL
        if "IDENTIFICATION DIVISION" in upper or "PROCEDURE DIVISION" in upper:
            return AssetType.COBOL
        # MAP/BMS
        if "DFHMSD" in upper or "DFHMDI" in upper:
            return AssetType.MAP
        # Assembler
        if " CSECT" in upper or " USING " in upper:
            return AssetType.ASSEMBLER
        return None

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
