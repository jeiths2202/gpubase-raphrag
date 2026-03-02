"""
Agent Teams - vLLM 기반 멀티에이전트 패턴 (Claude API 미사용)

5가지 패턴:
- Pattern A: Parallel Retrieval (Web Doc + PDF 병렬 검색)
- Pattern B: Competitive Hypothesis (다중 가설 경쟁 검증)
- Pattern C: Domain Specialist (멀티 QLoRA 전문가 팀)
- Pattern D: Multi-Product Collaboration (멀티제품 DAG 협업)
- Pattern E: Self-Improvement (피드백 축적 → 학습 데이터)
"""
from .team_orchestrator import TeamOrchestrator, get_team_orchestrator
from .parallel_retrieval import ParallelRetrievalService, RetrievalResult
from .domain_specialist import DomainSpecialistTeam, SpecialistAnswer
from .multi_product_collab import MultiProductCollaborationService
from .competitive_hypothesis import CompetitiveHypothesisService
from .self_improvement import SelfImprovementService

__all__ = [
    "TeamOrchestrator",
    "get_team_orchestrator",
    "ParallelRetrievalService",
    "RetrievalResult",
    "DomainSpecialistTeam",
    "SpecialistAnswer",
    "MultiProductCollaborationService",
    "CompetitiveHypothesisService",
    "SelfImprovementService",
]
