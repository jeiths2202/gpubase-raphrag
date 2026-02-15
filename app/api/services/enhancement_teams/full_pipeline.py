"""
Pattern H: Full Pipeline Runner

원클릭으로 분석 → 설계 → 구현 계획을 순차 실행.
각 단계 사이에 Quality Gate 검증을 수행하며, SSE로 진행 상황을 스트리밍합니다.
"""
import json
import logging
import re
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List, AsyncGenerator

from ...models.enhancement import (
    AIAnalysisResult,
    ArchitectureProposal,
    ImplementationPlan,
    ImplementationPhase,
    TestStrategy,
)
from .parallel_analysis import ParallelAnalysisTeam
from .architecture_crossval import ArchitectureCrossValidator
from .quality_gate import QualityGate

logger = logging.getLogger(__name__)

IMPLEMENTATION_PROMPT = """You are an Implementation Planner. Create a detailed implementation plan based on the architecture proposal.

Break down the work into phases with clear tasks, dependencies, and a comprehensive test strategy.

Respond with ONLY a JSON object:
{
    "phases": [
        {
            "phase_number": 1,
            "title": "Phase title",
            "description": "Phase description",
            "tasks": ["task1", "task2"],
            "dependencies": [],
            "estimated_effort": "2 hours"
        }
    ],
    "test_strategy": {
        "unit_tests": ["test description 1"],
        "integration_tests": ["test description 1"],
        "e2e_tests": ["test description 1"],
        "manual_tests": ["test description 1"]
    },
    "rollback_plan": "Description of how to rollback if issues arise"
}"""


class FullPipelineRunner:
    """
    원클릭 전체 파이프라인.

    1. 분석 (Pattern F 또는 단일)
    2. Quality Gate: 분석 완료도
    3. 설계 (Pattern G 또는 단일)
    4. Quality Gate: 설계-분석 일관성
    5. 구현 계획
    6. Quality Gate: 구현 완전성
    """

    def __init__(
        self,
        parallel_analysis: bool = False,
        crossval: bool = False,
        quality_threshold: float = 0.6,
    ):
        self._parallel_analysis_enabled = parallel_analysis
        self._crossval_enabled = crossval
        self._quality_gate = QualityGate(threshold=quality_threshold)
        self._analysis_team = ParallelAnalysisTeam()
        self._crossval = ArchitectureCrossValidator()

    async def stream_pipeline(
        self,
        enhancement_id: str,
        title: str,
        description: str,
        attachments_text: Optional[str] = None,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """전체 파이프라인 SSE 스트리밍 실행"""
        from ...adapters.learning_llm.vllm_adapter import get_vllm_adapter

        adapter = get_vllm_adapter()
        if adapter is None:
            yield {"event": "error", "data": {"message": "VLLMAdapter not available"}}
            return

        yield {
            "event": "pipeline_started",
            "data": {
                "enhancement_id": enhancement_id,
                "phases": ["analysis", "architecture", "implementation"],
                "parallel_analysis": self._parallel_analysis_enabled,
                "crossval": self._crossval_enabled,
            },
        }

        # =====================================================
        # Phase 1: Analysis
        # =====================================================
        yield {"event": "phase", "data": {"phase": "analysis", "status": "started"}}

        try:
            if self._parallel_analysis_enabled:
                analysis = await self._analysis_team.analyze(
                    title, description, attachments_text
                )
            else:
                analysis = await self._single_analysis(
                    adapter, title, description, attachments_text
                )
        except Exception as e:
            logger.error(f"Analysis phase failed: {e}")
            yield {"event": "phase_error", "data": {"phase": "analysis", "error": str(e)}}
            return

        # Quality Gate: 분석
        gate_result = self._quality_gate.validate_analysis(analysis)
        yield {
            "event": "quality_gate",
            "data": {
                "phase": "analysis",
                "passed": gate_result.passed,
                "score": gate_result.score,
                "issues": gate_result.issues,
                "warnings": gate_result.warnings,
            },
        }

        if not gate_result.passed:
            yield {
                "event": "pipeline_stopped",
                "data": {
                    "reason": "analysis_quality_gate_failed",
                    "phase": "analysis",
                    "analysis": analysis.model_dump(mode="json"),
                },
            }
            return

        yield {
            "event": "phase",
            "data": {
                "phase": "analysis",
                "status": "complete",
                "result": analysis.model_dump(mode="json"),
            },
        }

        # =====================================================
        # Phase 2: Architecture
        # =====================================================
        yield {"event": "phase", "data": {"phase": "architecture", "status": "started"}}

        try:
            if self._crossval_enabled:
                proposal = await self._crossval.design_and_validate(
                    title, description, analysis
                )
            else:
                proposal = await self._single_architecture(
                    adapter, title, description, analysis
                )
        except Exception as e:
            logger.error(f"Architecture phase failed: {e}")
            yield {
                "event": "phase_error",
                "data": {"phase": "architecture", "error": str(e)},
            }
            # 분석까지 결과는 사용 가능
            yield {
                "event": "pipeline_partial",
                "data": {
                    "completed_phases": ["analysis"],
                    "analysis": analysis.model_dump(mode="json"),
                },
            }
            return

        # Quality Gate: 설계
        gate_result = self._quality_gate.validate_architecture(proposal, analysis)
        yield {
            "event": "quality_gate",
            "data": {
                "phase": "architecture",
                "passed": gate_result.passed,
                "score": gate_result.score,
                "issues": gate_result.issues,
                "warnings": gate_result.warnings,
            },
        }

        if not gate_result.passed:
            yield {
                "event": "pipeline_stopped",
                "data": {
                    "reason": "architecture_quality_gate_failed",
                    "phase": "architecture",
                    "analysis": analysis.model_dump(mode="json"),
                    "proposal": proposal.model_dump(mode="json"),
                },
            }
            return

        yield {
            "event": "phase",
            "data": {
                "phase": "architecture",
                "status": "complete",
                "result": proposal.model_dump(mode="json"),
            },
        }

        # =====================================================
        # Phase 3: Implementation Plan
        # =====================================================
        yield {"event": "phase", "data": {"phase": "implementation", "status": "started"}}

        try:
            impl_plan = await self._create_implementation(
                adapter, title, description, analysis, proposal
            )
        except Exception as e:
            logger.error(f"Implementation phase failed: {e}")
            yield {
                "event": "phase_error",
                "data": {"phase": "implementation", "error": str(e)},
            }
            yield {
                "event": "pipeline_partial",
                "data": {
                    "completed_phases": ["analysis", "architecture"],
                    "analysis": analysis.model_dump(mode="json"),
                    "proposal": proposal.model_dump(mode="json"),
                },
            }
            return

        # Quality Gate: 구현
        gate_result = self._quality_gate.validate_implementation(impl_plan, proposal)
        yield {
            "event": "quality_gate",
            "data": {
                "phase": "implementation",
                "passed": gate_result.passed,
                "score": gate_result.score,
                "issues": gate_result.issues,
                "warnings": gate_result.warnings,
            },
        }

        yield {
            "event": "phase",
            "data": {
                "phase": "implementation",
                "status": "complete",
                "result": impl_plan.model_dump(mode="json"),
            },
        }

        # Pipeline complete
        yield {
            "event": "pipeline_complete",
            "data": {
                "enhancement_id": enhancement_id,
                "phases_completed": 3,
                "analysis": analysis.model_dump(mode="json"),
                "proposal": proposal.model_dump(mode="json"),
                "implementation_plan": impl_plan.model_dump(mode="json"),
            },
        }

    async def _single_analysis(
        self,
        adapter: Any,
        title: str,
        description: str,
        attachments_text: Optional[str] = None,
    ) -> AIAnalysisResult:
        """단일 관점 분석 (Pattern F 비활성 시)"""
        # ParallelAnalysisTeam의 component 관점만 사용
        team = ParallelAnalysisTeam(max_parallel=1)
        return await team.analyze(title, description, attachments_text)

    async def _single_architecture(
        self,
        adapter: Any,
        title: str,
        description: str,
        analysis: AIAnalysisResult,
    ) -> ArchitectureProposal:
        """단일 설계 (Pattern G 비활성 시, 검증 없이 설계만)"""
        crossval = ArchitectureCrossValidator()
        # 검증 없이 설계만 수행하기 위해 design_and_validate 호출
        # (내부적으로 검증 실패해도 초기 설계를 반환)
        return await crossval.design_and_validate(title, description, analysis)

    async def _create_implementation(
        self,
        adapter: Any,
        title: str,
        description: str,
        analysis: AIAnalysisResult,
        proposal: ArchitectureProposal,
    ) -> ImplementationPlan:
        """구현 계획 생성"""
        proposal_summary = (
            f"Approach: {proposal.approach}\n"
            f"File changes: {len(proposal.file_changes)}\n"
            f"New files: {len(proposal.new_files)}\n"
            f"API changes: {len(proposal.api_changes)}\n"
            f"Backward compatible: {proposal.backward_compatible}\n"
            f"Migration required: {proposal.migration_required}"
        )

        question = (
            f"{IMPLEMENTATION_PROMPT}\n\n"
            f"## Enhancement: {title}\n{description}\n\n"
            f"## Analysis Summary\n{analysis.summary}\n"
            f"Complexity: {analysis.estimated_complexity.value}\n"
            f"Priority: {analysis.priority_recommendation.value}\n\n"
            f"## Architecture Proposal\n{proposal_summary}"
        )

        response = await adapter.generate(
            question=question,
            max_new_tokens=2048,
            temperature=0.3,
        )

        data = self._extract_json(response)
        if not data:
            return ImplementationPlan(
                phases=[ImplementationPhase(
                    phase_number=1,
                    title="Implementation",
                    description="Implement the enhancement as designed",
                    tasks=["Implement changes per architecture proposal"],
                )],
                test_strategy=TestStrategy(
                    unit_tests=["Verify core functionality"],
                ),
                rollback_plan="Revert commits if issues are found",
                created_at=datetime.now(timezone.utc),
                created_by_agent="enhancement_teams.full_pipeline",
            )

        return self._parse_implementation(data)

    def _parse_implementation(self, data: Dict[str, Any]) -> ImplementationPlan:
        """JSON dict → ImplementationPlan"""
        phases = []
        for p in data.get("phases", []):
            if isinstance(p, dict):
                phases.append(ImplementationPhase(
                    phase_number=p.get("phase_number", len(phases) + 1),
                    title=p.get("title", f"Phase {len(phases) + 1}"),
                    description=p.get("description", ""),
                    tasks=p.get("tasks", []),
                    dependencies=p.get("dependencies", []),
                    estimated_effort=p.get("estimated_effort", ""),
                ))

        ts_data = data.get("test_strategy", {})
        test_strategy = TestStrategy(
            unit_tests=ts_data.get("unit_tests", []) if isinstance(ts_data, dict) else [],
            integration_tests=ts_data.get("integration_tests", []) if isinstance(ts_data, dict) else [],
            e2e_tests=ts_data.get("e2e_tests", []) if isinstance(ts_data, dict) else [],
            manual_tests=ts_data.get("manual_tests", []) if isinstance(ts_data, dict) else [],
        )

        return ImplementationPlan(
            phases=phases,
            test_strategy=test_strategy,
            rollback_plan=data.get("rollback_plan", ""),
            created_at=datetime.now(timezone.utc),
            created_by_agent="enhancement_teams.full_pipeline",
        )

    def _extract_json(self, text: str) -> Optional[Dict[str, Any]]:
        """텍스트에서 JSON 객체 추출"""
        if not text:
            return None
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass
        match = re.search(r'\{[\s\S]*\}', text)
        if match:
            try:
                return json.loads(match.group())
            except json.JSONDecodeError:
                pass
        return None
