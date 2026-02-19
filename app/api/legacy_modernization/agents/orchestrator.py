"""Orchestrator Agent - Team Coordinator for the legacy analysis pipeline.

Responsibilities:
- Asset reception -> type classification -> Domain Expert assignment
- Pipeline state machine management
- Conflict resolution (delegates to ConflictResolver)
- Audit trail recording
- Final report assembly

The Orchestrator is the only agent that can transition the pipeline state.
"""

import logging
from typing import Optional

from ..core.conflict_resolver import ConflictResolver
from ..core.event_bus import EventBus
from ..core.pipeline import PipelineStateMachine
from ..core.protocol import (
    AgentId,
    AgentMessage,
    AgentResult,
    AgentTask,
    AuditEntry,
    ChangeRequest,
    ChangeRequestResponse,
    Resolution,
)
from ..core.shared_state import SharedStateStore, SharedWorkspaceState
from ..models.enums import (
    AgentRole,
    AgentStatus,
    AssetType,
    AuditAction,
    ChangeRequestStatus,
    MessageType,
    PipelineStatus,
)
from .base_agent import BaseAgent

logger = logging.getLogger(__name__)

# Simple asset-type detection based on file extension and content heuristics
_EXTENSION_MAP = {
    ".cbl": AssetType.COBOL,
    ".cob": AssetType.COBOL,
    ".cobol": AssetType.COBOL,
    ".jcl": AssetType.JCL,
    ".map": AssetType.MAP,
    ".bms": AssetType.MAP,
    ".mfs": AssetType.MAP,
    ".asm": AssetType.ASSEMBLER,
    ".hlasm": AssetType.ASSEMBLER,
}

# XSP JCL statement prefixes (Fujitsu OSIV/XSP)
_XSP_STMT_PATTERNS = {"\ JOB", "\ EX ", "\ FD ", "\ JEND", "/EXPAN", "/ SET", "/ DEFEND"}


class OrchestratorAgent(BaseAgent):
    """Central coordinator for the 8-agent analysis pipeline."""

    def __init__(
        self,
        event_bus: EventBus,
        shared_state: SharedStateStore,
    ) -> None:
        super().__init__(AgentId(role=AgentRole.ORCHESTRATOR), event_bus)
        self.shared_state = shared_state
        self.conflict_resolver = ConflictResolver()
        self.pipeline = PipelineStateMachine()

    async def execute(self, task: AgentTask) -> AgentResult:
        """Execute the full analysis pipeline for an asset."""
        # 1. Create workspace
        workspace = await self.shared_state.create_workspace(
            asset_id=task.asset_id,
            tenant_id=task.metadata.get("tenant_id", "default"),
        )

        # Record workspace creation
        await self._record_audit(
            workspace, AuditAction.WORKSPACE_CREATED,
            {"file_path": task.file_path},
        )

        # 2. Classify asset type
        asset_type = self._classify_asset(task.file_path, task.source_code)
        workspace.asset_type = asset_type
        workspace.file_path = task.file_path
        workspace.file_name = task.file_path.rsplit("/", 1)[-1] if "/" in task.file_path else task.file_path
        workspace.loc_count = len(task.source_code.splitlines())
        await self.shared_state.save_workspace(
            workspace, AgentRole.ORCHESTRATOR,
            changed_fields={"asset_type", "file_path", "file_name", "loc_count"},
        )

        # 3. Start pipeline
        try:
            self.pipeline.transition(workspace, PipelineStatus.PARSING)
            await self._record_audit(
                workspace, AuditAction.PIPELINE_STATE_CHANGED,
                {"from": PipelineStatus.PENDING.value, "to": PipelineStatus.PARSING.value},
            )
            await self.shared_state.save_workspace(
                workspace, AgentRole.ORCHESTRATOR,
                changed_fields={"pipeline_status"},
            )
        except Exception as exc:
            logger.error("Pipeline start failed: %s", exc)
            return AgentResult(
                agent_id=self.agent_id,
                status=AgentStatus.ERROR,
                workspace_id=workspace.asset_id,
                error_message=str(exc),
            )

        # 4. Assign domain expert
        expert_role = self.pipeline.get_expert_for_asset(asset_type)
        await self._assign_task(expert_role, task, workspace)

        return AgentResult(
            agent_id=self.agent_id,
            status=AgentStatus.COMPLETED,
            workspace_id=workspace.asset_id,
            metadata={
                "asset_type": asset_type.value,
                "expert_assigned": expert_role.value,
                "pipeline_status": workspace.pipeline_status.value,
            },
        )

    async def advance_pipeline(
        self,
        workspace: SharedWorkspaceState,
        agent_result: AgentResult,
    ) -> PipelineStatus:
        """Advance the pipeline based on an agent's result.

        Called by the Orchestrator after each agent completes.
        """
        current = workspace.pipeline_status
        next_status = self.pipeline.determine_next_status(
            current, agent_result.status, workspace,
        )

        try:
            self.pipeline.transition(workspace, next_status)
        except Exception as exc:
            logger.error("Pipeline advance failed: %s", exc)
            workspace.pipeline_status = PipelineStatus.FAILED
            next_status = PipelineStatus.FAILED

        await self._record_audit(
            workspace, AuditAction.PIPELINE_STATE_CHANGED,
            {"from": current.value, "to": next_status.value},
        )
        await self.shared_state.save_workspace(
            workspace, AgentRole.ORCHESTRATOR,
            changed_fields={"pipeline_status", "audit_trail"},
        )

        # If not terminal, assign next agent
        if next_status not in (PipelineStatus.COMPLETED, PipelineStatus.FAILED):
            agent_role = self.pipeline.get_agent_for_state(next_status)
            if agent_role:
                await self._publish_task(
                    agent_role, workspace.asset_id, workspace.asset_id,
                )
            elif next_status == PipelineStatus.PARSING:
                # Re-parsing: assign domain expert again
                expert = self.pipeline.get_expert_for_asset(workspace.asset_type)
                await self._publish_task(
                    expert, workspace.asset_id, workspace.asset_id,
                )

        return next_status

    async def handle_change_request(self, cr: ChangeRequest) -> ChangeRequestResponse:
        """Route change requests through the 5-rule ConflictResolver."""
        workspace = await self.shared_state.get_workspace(
            cr.request_id  # correlation to asset_id via metadata
        )
        resolution = await self.conflict_resolver.resolve(cr, workspace)

        # Record audit
        await self._record_audit(
            workspace,
            AuditAction.CHANGE_REQUEST_RESOLVED,
            {
                "request_id": cr.request_id,
                "rule": resolution.rule_applied,
                "status": resolution.status.value,
            },
        )

        # If reanalysis required, trigger pipeline restart
        if resolution.status == ChangeRequestStatus.REANALYSIS_REQUIRED:
            await self._trigger_reanalysis(workspace)

        return ChangeRequestResponse(
            request_id=cr.request_id,
            approved=resolution.status == ChangeRequestStatus.APPROVED,
            reason=resolution.reason,
            agent_id=self.agent_id,
        )

    async def handle_veto(
        self, workspace: SharedWorkspaceState, veto_message: AgentMessage
    ) -> None:
        """Handle a QA VETO — block the pipeline."""
        logger.warning(
            "QA VETO received for asset %s: %s",
            workspace.asset_id, veto_message.payload,
        )
        try:
            self.pipeline.transition(workspace, PipelineStatus.BLOCKED)
        except ValueError:
            workspace.pipeline_status = PipelineStatus.BLOCKED

        await self._record_audit(
            workspace, AuditAction.QA_VETOED,
            {"veto_payload": veto_message.payload},
        )
        await self.shared_state.save_workspace(
            workspace, AgentRole.ORCHESTRATOR,
            changed_fields={"pipeline_status", "audit_trail"},
        )

    # --- Private helpers ---

    def _classify_asset(self, file_path: str, source_code: str) -> AssetType:
        """Classify asset type from file extension and content heuristics."""
        lower = file_path.lower()
        for ext, asset_type in _EXTENSION_MAP.items():
            if lower.endswith(ext):
                return asset_type

        # Content-based fallback
        upper = source_code[:1000].upper()
        # XSP JCL: \ JOB, \ EX, \ FD, /EXPAN, / SET, / DEFEND
        if any(pat in upper for pat in _XSP_STMT_PATTERNS):
            return AssetType.JCL
        if "IDENTIFICATION DIVISION" in upper or "PROCEDURE DIVISION" in upper:
            return AssetType.COBOL
        if upper.lstrip().startswith("//") and ("JOB" in upper or "EXEC" in upper):
            return AssetType.JCL
        if "DFHMSD" in upper or "DFHMDI" in upper:
            return AssetType.MAP
        if " CSECT" in upper or " USING " in upper:
            return AssetType.ASSEMBLER

        return AssetType.COBOL  # default

    async def _assign_task(
        self, expert_role: AgentRole, task: AgentTask, workspace: SharedWorkspaceState,
    ) -> None:
        """Assign a task to a specific agent and record audit."""
        await self._publish_task(expert_role, task.asset_id, task.correlation_id)
        await self._record_audit(
            workspace, AuditAction.TASK_ASSIGNED,
            {"agent": expert_role.value, "asset_id": task.asset_id},
        )

    async def _publish_task(
        self, target_role: AgentRole, asset_id: str, correlation_id: str,
    ) -> None:
        """Publish a TASK message to a target agent's stream."""
        await self.event_bus.publish(
            stream=target_role.value,
            message=AgentMessage(
                sender=self.agent_id,
                recipient=AgentId(role=target_role),
                message_type=MessageType.TASK,
                payload={"asset_id": asset_id},
                correlation_id=correlation_id,
            ),
        )

    async def _trigger_reanalysis(self, workspace: SharedWorkspaceState) -> None:
        """Trigger pipeline restart from REVIEWING/BLOCKED → PARSING."""
        await self._record_audit(
            workspace, AuditAction.REANALYSIS_TRIGGERED,
            {"iteration": self.pipeline.get_reanalysis_count(workspace.asset_id)},
        )

    async def _record_audit(
        self,
        workspace: SharedWorkspaceState,
        action: AuditAction,
        details: dict,
    ) -> None:
        """Append an audit entry to the workspace."""
        entry = AuditEntry(
            actor=self.agent_id,
            action=action,
            target_asset_id=workspace.asset_id,
            details=details,
        )
        workspace.audit_trail.append(entry.model_dump())
