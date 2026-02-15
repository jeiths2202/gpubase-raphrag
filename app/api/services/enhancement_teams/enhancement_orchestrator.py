"""
Enhancement Team Orchestrator

Enhancement Request 처리를 위한 Agent Teams 오케스트레이터.
Feature flag에 따라 패턴 F/G/H를 활성화하며,
모두 비활성 시 기존 개별 Agent 로직으로 폴백합니다.
"""
import json
import logging
from typing import Optional, Dict, Any, AsyncGenerator

from ...core.config import get_settings
from ...models.enhancement import (
    AIAnalysisResult,
    ArchitectureProposal,
    ImplementationPlan,
    EnhancementStatus,
)
from ...services.enhancement_service import get_enhancement_service
from .parallel_analysis import ParallelAnalysisTeam
from .architecture_crossval import ArchitectureCrossValidator
from .full_pipeline import FullPipelineRunner
from .quality_gate import QualityGate

logger = logging.getLogger(__name__)


class EnhancementTeamOrchestrator:
    """
    Enhancement Teams 메인 오케스트레이터.

    RAG Agent Teams의 TeamOrchestrator와 동일한 패턴:
    - Singleton + lazy init
    - Feature flag 기반 활성화
    - 비활성 시 기존 로직 폴백
    """

    def __init__(self):
        self._settings = get_settings()
        self._analysis_team: Optional[ParallelAnalysisTeam] = None
        self._crossval: Optional[ArchitectureCrossValidator] = None
        self._pipeline: Optional[FullPipelineRunner] = None
        self._quality_gate: Optional[QualityGate] = None

    @property
    def analysis_team(self) -> ParallelAnalysisTeam:
        if self._analysis_team is None:
            self._analysis_team = ParallelAnalysisTeam(
                max_parallel=self._settings.ENHANCEMENT_TEAMS_MAX_PARALLEL_LLM
            )
        return self._analysis_team

    @property
    def crossval(self) -> ArchitectureCrossValidator:
        if self._crossval is None:
            self._crossval = ArchitectureCrossValidator()
        return self._crossval

    @property
    def pipeline(self) -> FullPipelineRunner:
        if self._pipeline is None:
            self._pipeline = FullPipelineRunner(
                parallel_analysis=self._settings.ENHANCEMENT_TEAMS_PARALLEL_ANALYSIS,
                crossval=self._settings.ENHANCEMENT_TEAMS_CROSSVAL,
                quality_threshold=self._settings.ENHANCEMENT_TEAMS_QUALITY_GATE_THRESHOLD,
            )
        return self._pipeline

    @property
    def quality_gate(self) -> QualityGate:
        if self._quality_gate is None:
            self._quality_gate = QualityGate(
                threshold=self._settings.ENHANCEMENT_TEAMS_QUALITY_GATE_THRESHOLD
            )
        return self._quality_gate

    # =========================================================================
    # Pattern F: Team Analysis
    # =========================================================================

    async def stream_team_analyze(
        self,
        enhancement_id: str,
    ) -> AsyncGenerator[str, None]:
        """
        Pattern F: 팀 분석 SSE 스트림.

        PARALLEL_ANALYSIS=true → 3 관점 병렬 분석
        PARALLEL_ANALYSIS=false → 단일 분석
        """
        service = get_enhancement_service()
        enhancement = await service.get_enhancement(enhancement_id)

        if not enhancement:
            yield _sse_event("error", {"message": f"Enhancement {enhancement_id} not found"})
            return

        # 상태 업데이트: ANALYZING
        await service.update_status(
            enhancement_id,
            EnhancementStatus.ANALYZING,
            actor_id="enhancement_teams",
            actor_name="Enhancement Teams",
            actor_type="agent",
        )

        yield _sse_event("analysis_started", {
            "enhancement_id": enhancement_id,
            "mode": "parallel" if self._settings.ENHANCEMENT_TEAMS_PARALLEL_ANALYSIS else "single",
        })

        # 첨부파일 텍스트 추출
        attachments_text = None
        if enhancement.attachments:
            texts = [a.extracted_text for a in enhancement.attachments if a.extracted_text]
            if texts:
                attachments_text = "\n\n".join(texts)

        try:
            # 스트리밍 분석
            async for event in self.analysis_team.stream_analyze(
                title=enhancement.title,
                description=enhancement.description,
                attachments_text=attachments_text,
            ):
                yield _sse_event(event["event"], event.get("data", {}))

                # team_analysis_complete 이벤트에서 결과 저장
                if event["event"] == "team_analysis_complete":
                    analysis = AIAnalysisResult(**event["data"])
                    await service.add_analysis(enhancement_id, analysis)

        except Exception as e:
            logger.error(f"Team analysis failed for {enhancement_id}: {e}")
            yield _sse_event("error", {"message": str(e)})

        yield _sse_event("done", {"enhancement_id": enhancement_id})

    # =========================================================================
    # Pattern G: Team Architecture
    # =========================================================================

    async def stream_team_architecture(
        self,
        enhancement_id: str,
    ) -> AsyncGenerator[str, None]:
        """
        Pattern G: 팀 아키텍처 SSE 스트림.

        CROSSVAL=true → 설계 + 검증 + 수정
        CROSSVAL=false → 설계만
        """
        service = get_enhancement_service()
        enhancement = await service.get_enhancement(enhancement_id)

        if not enhancement:
            yield _sse_event("error", {"message": f"Enhancement {enhancement_id} not found"})
            return

        if not enhancement.ai_analysis:
            yield _sse_event("error", {"message": "Analysis must be completed before architecture design"})
            return

        # 상태 업데이트
        await service.update_status(
            enhancement_id,
            EnhancementStatus.ARCHITECTURE_REVIEW,
            actor_id="enhancement_teams",
            actor_name="Enhancement Teams",
            actor_type="agent",
        )

        yield _sse_event("architecture_started", {
            "enhancement_id": enhancement_id,
            "mode": "crossval" if self._settings.ENHANCEMENT_TEAMS_CROSSVAL else "single",
        })

        try:
            async for event in self.crossval.stream_design_and_validate(
                title=enhancement.title,
                description=enhancement.description,
                analysis=enhancement.ai_analysis,
            ):
                yield _sse_event(event["event"], event.get("data", {}))

                # crossval_complete 이벤트에서 결과 저장
                if event["event"] == "crossval_complete":
                    proposal = ArchitectureProposal(**event["data"])
                    await service.add_architecture_proposal(
                        enhancement_id, proposal,
                        user_id="enhancement_teams",
                        user_name="Enhancement Teams",
                    )

        except Exception as e:
            logger.error(f"Team architecture failed for {enhancement_id}: {e}")
            yield _sse_event("error", {"message": str(e)})

        yield _sse_event("done", {"enhancement_id": enhancement_id})

    # =========================================================================
    # Pattern H: Full Pipeline
    # =========================================================================

    async def stream_team_pipeline(
        self,
        enhancement_id: str,
    ) -> AsyncGenerator[str, None]:
        """
        Pattern H: 전체 파이프라인 SSE 스트림.

        분석 → 설계 → 구현 계획을 한 번에 실행.
        각 단계 완료 시 enhancement_service에 결과 저장.
        """
        service = get_enhancement_service()
        enhancement = await service.get_enhancement(enhancement_id)

        if not enhancement:
            yield _sse_event("error", {"message": f"Enhancement {enhancement_id} not found"})
            return

        # 상태 업데이트: ANALYZING
        await service.update_status(
            enhancement_id,
            EnhancementStatus.ANALYZING,
            actor_id="enhancement_teams",
            actor_name="Enhancement Teams",
            actor_type="agent",
        )

        # 첨부파일 텍스트
        attachments_text = None
        if enhancement.attachments:
            texts = [a.extracted_text for a in enhancement.attachments if a.extracted_text]
            if texts:
                attachments_text = "\n\n".join(texts)

        try:
            async for event in self.pipeline.stream_pipeline(
                enhancement_id=enhancement_id,
                title=enhancement.title,
                description=enhancement.description,
                attachments_text=attachments_text,
            ):
                event_name = event["event"]
                event_data = event.get("data", {})
                yield _sse_event(event_name, event_data)

                # 각 단계 완료 시 결과 저장
                if event_name == "phase" and event_data.get("status") == "complete":
                    phase = event_data.get("phase")
                    result = event_data.get("result")

                    if phase == "analysis" and result:
                        analysis = AIAnalysisResult(**result)
                        await service.add_analysis(enhancement_id, analysis)

                    elif phase == "architecture" and result:
                        proposal = ArchitectureProposal(**result)
                        await service.add_architecture_proposal(
                            enhancement_id, proposal,
                            user_id="enhancement_teams",
                            user_name="Enhancement Teams",
                        )

                    elif phase == "implementation" and result:
                        plan = ImplementationPlan(**result)
                        await service.add_implementation_plan(
                            enhancement_id, plan
                        )
                        # 구현 계획까지 완료 → APPROVED 상태
                        await service.update_status(
                            enhancement_id,
                            EnhancementStatus.APPROVED,
                            actor_id="enhancement_teams",
                            actor_name="Enhancement Teams",
                            actor_type="agent",
                            details={"pipeline": "complete"},
                        )

        except Exception as e:
            logger.error(f"Full pipeline failed for {enhancement_id}: {e}")
            yield _sse_event("error", {"message": str(e)})

        yield _sse_event("done", {"enhancement_id": enhancement_id})

    # =========================================================================
    # Feature Flag 상태 조회
    # =========================================================================

    def get_status(self) -> Dict[str, Any]:
        """현재 Enhancement Teams 설정 상태"""
        return {
            "parallel_analysis": self._settings.ENHANCEMENT_TEAMS_PARALLEL_ANALYSIS,
            "crossval": self._settings.ENHANCEMENT_TEAMS_CROSSVAL,
            "full_pipeline": self._settings.ENHANCEMENT_TEAMS_FULL_PIPELINE,
            "max_parallel_llm": self._settings.ENHANCEMENT_TEAMS_MAX_PARALLEL_LLM,
            "quality_gate_threshold": self._settings.ENHANCEMENT_TEAMS_QUALITY_GATE_THRESHOLD,
        }


def _sse_event(event: str, data: Dict[str, Any]) -> str:
    """SSE 이벤트 포맷"""
    return f"data: {json.dumps({'event': event, **data}, ensure_ascii=False, default=str)}\n\n"


# Singleton
_orchestrator: Optional[EnhancementTeamOrchestrator] = None


def get_enhancement_orchestrator() -> EnhancementTeamOrchestrator:
    """Get the global enhancement team orchestrator instance."""
    global _orchestrator
    if _orchestrator is None:
        _orchestrator = EnhancementTeamOrchestrator()
    return _orchestrator
