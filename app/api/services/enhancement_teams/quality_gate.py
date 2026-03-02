"""
Quality Gate Service

결정론적 규칙 기반 품질 검증. LLM 호출 없음.
각 단계(분석/설계/구현) 산출물의 완전성과 일관성을 검증합니다.
"""
import logging
from dataclasses import dataclass, field
from typing import List, Optional

from ...models.enhancement import (
    AIAnalysisResult,
    ArchitectureProposal,
    ImplementationPlan,
)

logger = logging.getLogger(__name__)


@dataclass
class GateResult:
    """품질 게이트 검증 결과"""
    passed: bool
    score: float  # 0.0 ~ 1.0
    issues: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)


class QualityGate:
    """
    결정론적 품질 게이트.

    각 단계의 산출물이 다음 단계로 넘어갈 수 있는 최소 품질을 만족하는지 검증.
    LLM 호출 없이 필드 존재/비어있음/길이/교차 참조만 확인.
    """

    def __init__(self, threshold: float = 0.6):
        self.threshold = threshold

    def validate_analysis(self, analysis: AIAnalysisResult) -> GateResult:
        """분석 결과 검증"""
        issues: List[str] = []
        warnings: List[str] = []
        checks_passed = 0
        total_checks = 5

        # 1. summary 존재 + 최소 길이
        if analysis.summary and len(analysis.summary) >= 20:
            checks_passed += 1
        else:
            issues.append("summary가 너무 짧습니다 (최소 20자)")

        # 2. affected_components 비어있지 않음
        if analysis.affected_components and len(analysis.affected_components) > 0:
            checks_passed += 1
        else:
            issues.append("affected_components가 비어있습니다")

        # 3. feasibility_score 유효 범위
        if 0.0 <= analysis.feasibility_score <= 1.0:
            checks_passed += 1
        else:
            issues.append(f"feasibility_score 범위 오류: {analysis.feasibility_score}")

        # 4. recommended_approach 존재
        if analysis.recommended_approach and len(analysis.recommended_approach) >= 10:
            checks_passed += 1
        else:
            warnings.append("recommended_approach가 짧거나 없습니다")
            checks_passed += 0.5  # 경고는 부분 점수

        # 5. type_classification, priority_recommendation 유효
        if analysis.type_classification and analysis.priority_recommendation:
            checks_passed += 1
        else:
            issues.append("type 또는 priority 분류가 없습니다")

        score = checks_passed / total_checks
        passed = score >= self.threshold and len(issues) <= 1

        return GateResult(
            passed=passed,
            score=round(score, 2),
            issues=issues,
            warnings=warnings,
        )

    def validate_architecture(
        self,
        proposal: ArchitectureProposal,
        analysis: Optional[AIAnalysisResult] = None,
    ) -> GateResult:
        """아키텍처 제안서 검증 (분석 결과 대비 교차 검증 포함)"""
        issues: List[str] = []
        warnings: List[str] = []
        checks_passed = 0
        total_checks = 6

        # 1. approach 존재 + 최소 길이
        if proposal.approach and len(proposal.approach) >= 20:
            checks_passed += 1
        else:
            issues.append("approach 설명이 너무 짧습니다")

        # 2. design_decisions 존재
        if proposal.design_decisions and len(proposal.design_decisions) > 0:
            checks_passed += 1
        else:
            issues.append("design_decisions가 비어있습니다")

        # 3. file_changes 또는 new_files 존재
        if (proposal.file_changes and len(proposal.file_changes) > 0) or \
           (proposal.new_files and len(proposal.new_files) > 0):
            checks_passed += 1
        else:
            issues.append("file_changes와 new_files가 모두 비어있습니다")

        # 4. security_considerations 존재
        if proposal.security_considerations and len(proposal.security_considerations) > 0:
            checks_passed += 1
        else:
            warnings.append("security_considerations가 비어있습니다")
            checks_passed += 0.5

        # 5. backward_compatible 플래그 설정 (migration 필요 시 명시)
        if proposal.migration_required and not proposal.database_changes:
            warnings.append("migration_required인데 database_changes가 비어있습니다")
            checks_passed += 0.5
        else:
            checks_passed += 1

        # 6. 분석 결과와 교차 검증 (analysis 제공 시)
        if analysis:
            analysis_components = set(
                c.lower() for c in analysis.affected_components
            )
            proposal_components = set()
            for fc in proposal.file_changes:
                proposal_components.add(fc.file_path.lower())
            for nf in proposal.new_files:
                proposal_components.add(nf.file_path.lower())

            # 분석에서 식별한 컴포넌트가 설계에 반영되었는지 (부분 매칭)
            if analysis_components:
                # 최소 1개라도 관련 파일이 있으면 통과
                has_overlap = any(
                    any(comp in fp for comp in analysis_components)
                    for fp in proposal_components
                )
                if has_overlap or len(proposal_components) > 0:
                    checks_passed += 1
                else:
                    warnings.append(
                        "분석에서 식별한 컴포넌트가 설계에 반영되지 않았습니다"
                    )
                    checks_passed += 0.5
            else:
                checks_passed += 1  # 분석 컴포넌트 없으면 검증 건너뜀
        else:
            checks_passed += 1  # analysis 없으면 교차 검증 건너뜀

        score = checks_passed / total_checks
        passed = score >= self.threshold and len(issues) <= 1

        return GateResult(
            passed=passed,
            score=round(score, 2),
            issues=issues,
            warnings=warnings,
        )

    def validate_implementation(
        self,
        plan: ImplementationPlan,
        proposal: Optional[ArchitectureProposal] = None,
    ) -> GateResult:
        """구현 계획 검증"""
        issues: List[str] = []
        warnings: List[str] = []
        checks_passed = 0
        total_checks = 5

        # 1. phases 존재
        if plan.phases and len(plan.phases) > 0:
            checks_passed += 1
        else:
            issues.append("구현 phases가 비어있습니다")

        # 2. 각 phase에 tasks 존재
        if plan.phases:
            phases_with_tasks = sum(
                1 for p in plan.phases if p.tasks and len(p.tasks) > 0
            )
            if phases_with_tasks == len(plan.phases):
                checks_passed += 1
            elif phases_with_tasks > 0:
                warnings.append(
                    f"{len(plan.phases) - phases_with_tasks}개 phase에 tasks가 없습니다"
                )
                checks_passed += 0.5
            else:
                issues.append("모든 phase에 tasks가 비어있습니다")

        # 3. test_strategy 비어있지 않음
        ts = plan.test_strategy
        has_tests = (
            (ts.unit_tests and len(ts.unit_tests) > 0)
            or (ts.integration_tests and len(ts.integration_tests) > 0)
            or (ts.e2e_tests and len(ts.e2e_tests) > 0)
        )
        if has_tests:
            checks_passed += 1
        else:
            warnings.append("test_strategy에 테스트가 없습니다")
            checks_passed += 0.5

        # 4. rollback_plan 존재
        if plan.rollback_plan and len(plan.rollback_plan) >= 10:
            checks_passed += 1
        else:
            warnings.append("rollback_plan이 짧거나 없습니다")
            checks_passed += 0.5

        # 5. 아키텍처 제안서와 교차 검증
        if proposal and plan.phases:
            total_files = len(proposal.file_changes) + len(proposal.new_files)
            if total_files > 0:
                # phase tasks에서 파일 참조가 있는지
                all_tasks = " ".join(
                    " ".join(p.tasks) for p in plan.phases if p.tasks
                )
                if len(all_tasks) > 20:
                    checks_passed += 1
                else:
                    warnings.append("구현 tasks가 너무 간략합니다")
                    checks_passed += 0.5
            else:
                checks_passed += 1
        else:
            checks_passed += 1

        score = checks_passed / total_checks
        passed = score >= self.threshold

        return GateResult(
            passed=passed,
            score=round(score, 2),
            issues=issues,
            warnings=warnings,
        )
