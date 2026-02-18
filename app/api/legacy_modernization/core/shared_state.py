"""SharedWorkspaceState + SharedStateStore (Redis or in-memory fallback).

All agents can read the workspace; writes are restricted by role-based ACL.
Version field prevents concurrent modification (optimistic locking).
"""

import json
import logging
from datetime import datetime
from typing import Any, ClassVar, List, Optional, Set

from pydantic import BaseModel, Field

from ..core.errors import PermissionDeniedError, WorkspaceNotFoundError
from ..core.protocol import AuditEntry, ChangeRequest
from ..models.enums import AgentRole, AssetType, PipelineStatus
from ..parsers.base import NormalizedFeature, ParseError, ParseStats, TraceEvidence

logger = logging.getLogger(__name__)


class SharedWorkspaceState(BaseModel):
    """에이전트간 공유 작업 공간 — 모든 중간 분석 결과를 저장."""

    # === Identity ===
    asset_id: str = ""
    tenant_id: str = "default"
    version: int = 0
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    # === Source metadata ===
    asset_type: AssetType = AssetType.COBOL
    dialect: str = ""
    file_path: str = ""
    file_name: str = ""
    loc_count: int = 0
    uploaded_at: Optional[datetime] = None

    # === Parser outputs (immutable after parsing) ===
    ast: List[dict] = Field(default_factory=list)
    features: List[dict] = Field(default_factory=list)
    trace_evidence: List[dict] = Field(default_factory=list)
    parse_errors: List[dict] = Field(default_factory=list)
    confidence: Optional[dict] = None
    stats: Optional[dict] = None

    # === Pipeline status ===
    pipeline_status: PipelineStatus = PipelineStatus.PENDING

    # === Agent outputs ===
    annotations: List[dict] = Field(default_factory=list)
    review_notes: List[dict] = Field(default_factory=list)
    qa_flags: List[dict] = Field(default_factory=list)
    qa_passed: Optional[bool] = None
    e2e_results: Optional[dict] = None
    risk_scores: Optional[dict] = None
    migration_cost: Optional[dict] = None
    vendor_comparison: List[dict] = Field(default_factory=list)
    compatibility_findings: List[dict] = Field(default_factory=list)

    # === Orchestrator fields ===
    change_requests: List[dict] = Field(default_factory=list)
    audit_trail: List[dict] = Field(default_factory=list)


class WritePermission:
    """역할별 쓰기 권한 매핑 (ACL)."""

    PERMISSIONS: ClassVar[dict[AgentRole, Set[str]]] = {
        AgentRole.ORCHESTRATOR: {
            "asset_id", "tenant_id", "asset_type", "dialect",
            "pipeline_status", "change_requests", "audit_trail",
            "file_path", "file_name", "loc_count", "uploaded_at",
        },
        AgentRole.COBOL_EXPERT: {
            "ast", "features", "trace_evidence", "parse_errors", "confidence", "stats",
        },
        AgentRole.JCL_EXPERT: {
            "ast", "features", "trace_evidence", "parse_errors", "confidence", "stats",
        },
        AgentRole.MAP_EXPERT: {
            "ast", "features", "trace_evidence", "parse_errors", "confidence", "stats",
        },
        AgentRole.ASM_EXPERT: {
            "ast", "features", "trace_evidence", "parse_errors", "confidence", "stats",
        },
        AgentRole.LEGACY_KNOWLEDGE: {"annotations"},
        AgentRole.REVIEWER: {"review_notes"},
        AgentRole.QA: {"qa_flags", "qa_passed"},
        AgentRole.E2E_TEST: {"e2e_results"},
        AgentRole.RISK_INTELLIGENCE: {"risk_scores", "migration_cost"},
        AgentRole.COMPETITOR_INTELLIGENCE: {"vendor_comparison", "compatibility_findings"},
    }

    @classmethod
    def allowed_fields(cls, role: AgentRole) -> Set[str]:
        return cls.PERMISSIONS.get(role, set())

    @classmethod
    def check(cls, role: AgentRole, fields: Set[str]) -> None:
        """쓰기 권한 검증. 위반 시 PermissionDeniedError."""
        allowed = cls.allowed_fields(role)
        denied = fields - allowed
        if denied:
            raise PermissionDeniedError(
                agent_role=role.value,
                field=", ".join(sorted(denied)),
            )


class SharedStateStore:
    """공유 상태 저장소 (Redis available -> Redis, otherwise -> in-memory)."""

    TTL_SECONDS: ClassVar[int] = 86400  # 24시간

    def __init__(self, redis_url: str = "redis://localhost:6379") -> None:
        self._redis_url = redis_url
        self._redis: Any = None
        self._use_memory: bool = False
        self._memory: dict[str, str] = {}
        self._key_prefix = "workspace:"

    async def _get_redis(self) -> Any:
        if self._use_memory:
            return None
        if self._redis is None:
            try:
                import redis.asyncio as aioredis
                self._redis = aioredis.from_url(self._redis_url, decode_responses=True)
                await self._redis.ping()
                logger.info("SharedStateStore: connected to Redis at %s", self._redis_url)
            except Exception:
                logger.warning("SharedStateStore: Redis unavailable, using in-memory fallback")
                self._use_memory = True
                self._redis = None
                return None
        return self._redis

    async def create_workspace(
        self, asset_id: str, tenant_id: str, **kwargs: Any
    ) -> SharedWorkspaceState:
        """새 작업 공간 생성."""
        workspace = SharedWorkspaceState(
            asset_id=asset_id, tenant_id=tenant_id, **kwargs
        )
        await self._save(workspace)
        logger.info("Workspace created: %s (tenant=%s)", asset_id, tenant_id)
        return workspace

    async def get_workspace(self, asset_id: str) -> SharedWorkspaceState:
        """작업 공간 조회. 없으면 WorkspaceNotFoundError."""
        key = f"{self._key_prefix}{asset_id}"
        r = await self._get_redis()
        data = (await r.get(key)) if r else self._memory.get(key)
        if not data:
            raise WorkspaceNotFoundError(asset_id)
        return SharedWorkspaceState.model_validate_json(data)

    async def save_workspace(
        self,
        workspace: SharedWorkspaceState,
        agent_role: AgentRole,
        changed_fields: Optional[Set[str]] = None,
    ) -> SharedWorkspaceState:
        """작업 공간 저장 with ACL 검증 + optimistic locking."""
        if changed_fields:
            WritePermission.check(agent_role, changed_fields)

        key = f"{self._key_prefix}{workspace.asset_id}"
        r = await self._get_redis()
        current_data = (await r.get(key)) if r else self._memory.get(key)

        if current_data:
            current = SharedWorkspaceState.model_validate_json(current_data)
            if current.version != workspace.version:
                raise PermissionDeniedError(
                    agent_role=agent_role.value,
                    field="version",
                )

        workspace.version += 1
        workspace.updated_at = datetime.utcnow()
        await self._save(workspace)
        logger.debug(
            "Workspace saved: %s v%d by %s",
            workspace.asset_id, workspace.version, agent_role.value,
        )
        return workspace

    async def delete_workspace(self, asset_id: str) -> bool:
        """작업 공간 삭제."""
        key = f"{self._key_prefix}{asset_id}"
        r = await self._get_redis()
        if r:
            return bool(await r.delete(key))
        return self._memory.pop(key, None) is not None

    async def list_workspaces(self, tenant_id: Optional[str] = None) -> List[str]:
        """활성 workspace ID 목록 반환."""
        r = await self._get_redis()
        keys = []
        if r:
            async for key in r.scan_iter(f"{self._key_prefix}*"):
                asset_id = key.removeprefix(self._key_prefix)
                if tenant_id:
                    try:
                        ws = await self.get_workspace(asset_id)
                        if ws.tenant_id == tenant_id:
                            keys.append(asset_id)
                    except WorkspaceNotFoundError:
                        continue
                else:
                    keys.append(asset_id)
        else:
            for key in self._memory:
                if key.startswith(self._key_prefix):
                    asset_id = key[len(self._key_prefix):]
                    if tenant_id:
                        try:
                            ws = await self.get_workspace(asset_id)
                            if ws.tenant_id == tenant_id:
                                keys.append(asset_id)
                        except WorkspaceNotFoundError:
                            continue
                    else:
                        keys.append(asset_id)
        return keys

    async def _save(self, workspace: SharedWorkspaceState) -> None:
        """내부 저장 (Redis or memory)."""
        key = f"{self._key_prefix}{workspace.asset_id}"
        data = workspace.model_dump_json()
        r = await self._get_redis()
        if r:
            await r.set(key, data, ex=self.TTL_SECONDS)
        else:
            self._memory[key] = data

    async def close(self) -> None:
        """Redis 연결 해제."""
        if self._redis:
            await self._redis.close()
            self._redis = None
