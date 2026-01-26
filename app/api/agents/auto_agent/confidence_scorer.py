"""
Confidence Scorer

Calculates confidence scores for agent results and overall execution quality.
"""
import logging
from typing import Dict, List, Optional, Any

from ..types import AgentType, AgentResult
from .types import ExecutionPlan, VerificationResult

logger = logging.getLogger(__name__)


class ConfidenceScorer:
    """
    Calculates confidence scores for Auto Agent execution.

    Considers:
    - Agent execution success rate
    - Source grounding quality
    - Result consistency
    - Answer completeness
    """

    # Base confidence weights per agent type
    AGENT_BASE_CONFIDENCE = {
        AgentType.RAG: 0.85,
        AgentType.IMS: 0.80,
        AgentType.CODE: 0.75,
        AgentType.VISION: 0.70,
        AgentType.PLANNER: 0.90,
    }

    # Score component weights
    WEIGHT_EXECUTION = 0.25
    WEIGHT_GROUNDING = 0.30
    WEIGHT_CONSISTENCY = 0.20
    WEIGHT_COMPLETENESS = 0.25

    def __init__(self):
        """Initialize the confidence scorer"""
        pass

    def calculate_execution_confidence(
        self,
        task_results: Dict[str, AgentResult]
    ) -> float:
        """
        Calculate confidence based on execution success rate.

        Args:
            task_results: Results from all executed tasks

        Returns:
            Execution confidence score (0.0-1.0)
        """
        if not task_results:
            return 0.0

        success_count = sum(1 for r in task_results.values() if r.success)
        total = len(task_results)

        # Penalize more heavily for failed tasks
        failure_penalty = (total - success_count) * 0.15
        base_score = success_count / total
        adjusted_score = max(0.0, base_score - failure_penalty)

        return adjusted_score

    def calculate_grounding_confidence(
        self,
        task_results: Dict[str, AgentResult]
    ) -> float:
        """
        Calculate confidence based on source grounding.

        Args:
            task_results: Results from all executed tasks

        Returns:
            Grounding confidence score (0.0-1.0)
        """
        if not task_results:
            return 0.0

        # For RAG and IMS agents, sources are expected
        rag_ims_results = [
            r for r in task_results.values()
            if r.agent_type in [AgentType.RAG, AgentType.IMS] and r.success
        ]

        if not rag_ims_results:
            # No RAG/IMS tasks, assume good grounding
            return 0.85

        # Count results with sources
        with_sources = sum(1 for r in rag_ims_results if r.sources)
        total = len(rag_ims_results)

        # Base score from source presence
        source_ratio = with_sources / total

        # Bonus for multiple sources
        avg_source_count = sum(
            len(r.sources) for r in rag_ims_results
        ) / total if total > 0 else 0

        bonus = min(0.1, avg_source_count * 0.02)  # Up to 0.1 bonus

        return min(1.0, source_ratio * 0.9 + bonus)

    def calculate_consistency_confidence(
        self,
        task_results: Dict[str, AgentResult]
    ) -> float:
        """
        Calculate confidence based on consistency between results.

        Args:
            task_results: Results from all executed tasks

        Returns:
            Consistency confidence score (0.0-1.0)
        """
        if len(task_results) < 2:
            return 1.0  # Single result is always consistent

        # Simple heuristic: check for contradictory keywords
        # This is a simplified implementation - could use embeddings
        answers = [r.answer.lower() for r in task_results.values() if r.success and r.answer]

        if not answers:
            return 0.5

        # Check for explicit contradiction markers
        contradiction_markers = [
            ("yes", "no"),
            ("correct", "incorrect"),
            ("true", "false"),
            ("exists", "does not exist"),
            ("found", "not found"),
            ("있습니다", "없습니다"),
            ("가능", "불가능"),
        ]

        contradiction_count = 0
        for pos, neg in contradiction_markers:
            has_positive = any(pos in a for a in answers)
            has_negative = any(neg in a for a in answers)
            if has_positive and has_negative:
                contradiction_count += 1

        # Penalize for contradictions
        if contradiction_count == 0:
            return 1.0
        elif contradiction_count <= 2:
            return 0.7
        else:
            return 0.5

    def calculate_completeness_confidence(
        self,
        plan: ExecutionPlan,
        task_results: Dict[str, AgentResult]
    ) -> float:
        """
        Calculate confidence based on answer completeness.

        Args:
            plan: The execution plan
            task_results: Results from all executed tasks

        Returns:
            Completeness confidence score (0.0-1.0)
        """
        if not task_results:
            return 0.0

        # Check if all planned tasks were executed
        planned_ids = {t.task_id for t in plan.decomposed_tasks}
        executed_ids = set(task_results.keys())

        execution_ratio = len(executed_ids & planned_ids) / len(planned_ids) if planned_ids else 1.0

        # Check answer length/quality
        total_length = sum(len(r.answer) for r in task_results.values() if r.success)
        avg_length = total_length / len(task_results) if task_results else 0

        # Penalize very short answers
        if avg_length < 50:
            length_score = 0.5
        elif avg_length < 100:
            length_score = 0.7
        elif avg_length < 500:
            length_score = 0.85
        else:
            length_score = 1.0

        return execution_ratio * 0.6 + length_score * 0.4

    def calculate_overall_confidence(
        self,
        plan: ExecutionPlan,
        task_results: Dict[str, AgentResult],
        verification: Optional[VerificationResult] = None
    ) -> float:
        """
        Calculate overall confidence score.

        Args:
            plan: The execution plan
            task_results: Results from all executed tasks
            verification: Optional verification result

        Returns:
            Overall confidence score (0.0-1.0)
        """
        # Calculate component scores
        execution_score = self.calculate_execution_confidence(task_results)
        grounding_score = self.calculate_grounding_confidence(task_results)
        consistency_score = self.calculate_consistency_confidence(task_results)
        completeness_score = self.calculate_completeness_confidence(plan, task_results)

        # Weighted average
        overall = (
            execution_score * self.WEIGHT_EXECUTION +
            grounding_score * self.WEIGHT_GROUNDING +
            consistency_score * self.WEIGHT_CONSISTENCY +
            completeness_score * self.WEIGHT_COMPLETENESS
        )

        # If verification provided, incorporate its score
        if verification:
            # Average with verification score
            overall = (overall + verification.overall_score) / 2

        logger.debug(
            f"[ConfidenceScorer] Scores: exec={execution_score:.2f}, "
            f"ground={grounding_score:.2f}, consist={consistency_score:.2f}, "
            f"complete={completeness_score:.2f}, overall={overall:.2f}"
        )

        return overall

    def get_confidence_breakdown(
        self,
        plan: ExecutionPlan,
        task_results: Dict[str, AgentResult]
    ) -> Dict[str, float]:
        """
        Get detailed confidence breakdown.

        Args:
            plan: The execution plan
            task_results: Results from all executed tasks

        Returns:
            Dict with component scores
        """
        return {
            "execution": self.calculate_execution_confidence(task_results),
            "grounding": self.calculate_grounding_confidence(task_results),
            "consistency": self.calculate_consistency_confidence(task_results),
            "completeness": self.calculate_completeness_confidence(plan, task_results),
            "overall": self.calculate_overall_confidence(plan, task_results)
        }


# Singleton instance
_confidence_scorer: Optional[ConfidenceScorer] = None


def get_confidence_scorer() -> ConfidenceScorer:
    """Get or create the confidence scorer instance"""
    global _confidence_scorer
    if _confidence_scorer is None:
        _confidence_scorer = ConfidenceScorer()
    return _confidence_scorer
