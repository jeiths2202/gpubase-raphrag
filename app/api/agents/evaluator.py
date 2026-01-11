"""
Result Evaluator
Evaluates agent results for quality and determines retry decisions.
"""
from typing import Optional, Dict, Any, List
import logging
import re

from .types import (
    AgentResult, AgentType, EvaluationResult, EvaluationCriteria,
    RetryConfig, SubTask
)

logger = logging.getLogger(__name__)


class ResultEvaluator:
    """
    Evaluates agent execution results for quality.

    Determines if results meet quality thresholds and provides
    retry recommendations based on configurable criteria.
    """

    def __init__(self, llm_adapter=None):
        """
        Initialize the evaluator.

        Args:
            llm_adapter: Optional LLM adapter for advanced quality evaluation
        """
        self.llm_adapter = llm_adapter

    async def evaluate(
        self,
        result: AgentResult,
        task: str,
        criteria: EvaluationCriteria,
        subtask: Optional[SubTask] = None
    ) -> EvaluationResult:
        """
        Evaluate an agent result against quality criteria.

        Args:
            result: The agent execution result
            task: Original task description
            criteria: Evaluation criteria to apply
            subtask: Optional subtask metadata

        Returns:
            EvaluationResult with pass/fail status, score, and issues
        """
        issues: List[str] = []
        score = 1.0  # Start with perfect score, deduct for issues

        # Check execution success
        if not result.success:
            issues.append(f"Execution failed: {result.error or 'Unknown error'}")
            score -= 0.5

        # Check answer length
        answer_length = len(result.answer.strip()) if result.answer else 0
        if answer_length < criteria.min_answer_length:
            issues.append(
                f"Answer too short: {answer_length} chars "
                f"(minimum: {criteria.min_answer_length})"
            )
            score -= 0.2

        # Check for sources if required
        if criteria.require_sources and not result.sources:
            issues.append("Sources required but not provided")
            score -= 0.15

        # Check execution time
        if criteria.max_execution_time is not None:
            if result.execution_time > criteria.max_execution_time:
                issues.append(
                    f"Execution time exceeded: {result.execution_time:.1f}s "
                    f"(max: {criteria.max_execution_time}s)"
                )
                score -= 0.1

        # Check for error indicators in answer
        error_patterns = self._check_error_patterns(result.answer)
        if error_patterns:
            issues.extend(error_patterns)
            score -= 0.15 * len(error_patterns)

        # Check answer relevance (basic heuristic)
        relevance_score = self._check_relevance(result.answer, task)
        if relevance_score < 0.3:
            issues.append("Answer may not be relevant to the task")
            score -= 0.2

        # Normalize score
        score = max(0.0, min(1.0, score))

        # Determine if passed
        passed = score >= criteria.min_confidence and result.success

        # Determine retry recommendation
        retry_recommended = False
        retry_reason = None

        if not passed:
            # Recommend retry if score is close to threshold
            if score >= criteria.min_confidence - 0.2:
                retry_recommended = True
                retry_reason = "Score close to threshold, retry may succeed"
            elif result.error and self._is_transient_error(result.error):
                retry_recommended = True
                retry_reason = "Transient error detected"

        evaluation = EvaluationResult(
            passed=passed,
            score=score,
            issues=issues,
            retry_recommended=retry_recommended,
            retry_reason=retry_reason
        )

        logger.info(
            f"[Evaluator] Result evaluation: passed={passed}, score={score:.2f}, "
            f"issues={len(issues)}, retry={retry_recommended}"
        )

        return evaluation

    async def evaluate_with_llm(
        self,
        result: AgentResult,
        task: str,
        criteria: EvaluationCriteria
    ) -> EvaluationResult:
        """
        Use LLM for advanced quality evaluation.

        Falls back to rule-based evaluation if LLM is not available.
        """
        if self.llm_adapter is None:
            return await self.evaluate(result, task, criteria)

        try:
            prompt = f"""Evaluate the quality of this agent response.

Task: {task}

Response: {result.answer[:2000]}

Evaluate on these criteria:
1. Relevance: Does the response directly address the task?
2. Completeness: Is the response comprehensive?
3. Accuracy: Does the response appear factually correct?
4. Clarity: Is the response clear and well-structured?

Provide your evaluation in this format:
SCORE: [0.0-1.0]
ISSUES: [comma-separated list of issues, or "none"]
RETRY: [yes/no]

Be strict but fair. Only recommend retry if the response is close to acceptable."""

            response = await self.llm_adapter.generate([
                {"role": "user", "content": prompt}
            ])

            content = response.get("content", "")
            return self._parse_llm_evaluation(content, result, task, criteria)

        except Exception as e:
            logger.warning(f"[Evaluator] LLM evaluation failed: {e}, falling back to rules")
            return await self.evaluate(result, task, criteria)

    def should_retry(
        self,
        evaluation: EvaluationResult,
        retry_count: int,
        config: RetryConfig
    ) -> tuple[bool, float]:
        """
        Determine if a task should be retried based on evaluation.

        Args:
            evaluation: The evaluation result
            retry_count: Current retry count
            config: Retry configuration

        Returns:
            Tuple of (should_retry, delay_seconds)
        """
        # Check max retries
        if retry_count >= config.max_retries:
            logger.info(f"[Evaluator] Max retries ({config.max_retries}) reached")
            return False, 0.0

        # Check if retry is enabled for this failure type
        if not evaluation.passed and not config.retry_on_failure:
            return False, 0.0

        if evaluation.passed and evaluation.score < 0.8 and not config.retry_on_low_quality:
            return False, 0.0

        # Retry if recommended
        if evaluation.retry_recommended:
            # Calculate exponential backoff delay
            delay = config.initial_delay * (config.backoff_factor ** retry_count)
            logger.info(
                f"[Evaluator] Retry recommended: attempt {retry_count + 1}, "
                f"delay {delay:.1f}s"
            )
            return True, delay

        return False, 0.0

    def _check_error_patterns(self, answer: str) -> List[str]:
        """Check for common error indicators in the answer."""
        if not answer:
            return ["Empty answer"]

        issues = []
        answer_lower = answer.lower()

        # Common error phrases
        error_phrases = [
            (r"i don't know", "Response indicates uncertainty"),
            (r"i cannot|i can't", "Response indicates inability"),
            (r"no information|no data", "Response indicates missing information"),
            (r"error occurred|exception", "Response mentions errors"),
            (r"unable to|failed to", "Response indicates failure"),
            # Korean
            (r"모르겠|알 수 없", "Response indicates uncertainty (Korean)"),
            (r"정보가 없|데이터가 없", "Response indicates missing information (Korean)"),
            # Japanese
            (r"わかりません|分かりません", "Response indicates uncertainty (Japanese)"),
            (r"情報がありません", "Response indicates missing information (Japanese)"),
        ]

        for pattern, issue in error_phrases:
            if re.search(pattern, answer_lower):
                issues.append(issue)

        return issues

    def _check_relevance(self, answer: str, task: str) -> float:
        """
        Basic relevance check between answer and task.

        Returns a score from 0.0 to 1.0.
        """
        if not answer or not task:
            return 0.0

        # Extract key terms from task
        task_words = set(
            word.lower() for word in re.findall(r'\w+', task)
            if len(word) > 3
        )

        if not task_words:
            return 0.5  # Cannot evaluate

        # Check how many task words appear in answer
        answer_lower = answer.lower()
        matches = sum(1 for word in task_words if word in answer_lower)

        return min(1.0, matches / max(1, len(task_words) * 0.3))

    def _is_transient_error(self, error: str) -> bool:
        """Check if an error is likely transient and worth retrying."""
        if not error:
            return False

        error_lower = error.lower()
        transient_patterns = [
            "timeout",
            "connection",
            "temporarily",
            "retry",
            "rate limit",
            "503",
            "502",
            "504",
            "overloaded",
        ]

        return any(pattern in error_lower for pattern in transient_patterns)

    def _parse_llm_evaluation(
        self,
        content: str,
        result: AgentResult,
        task: str,
        criteria: EvaluationCriteria
    ) -> EvaluationResult:
        """Parse LLM evaluation response into EvaluationResult."""
        # Default values
        score = 0.5
        issues = []
        retry = False

        try:
            # Parse score
            score_match = re.search(r'SCORE:\s*([\d.]+)', content)
            if score_match:
                score = float(score_match.group(1))
                score = max(0.0, min(1.0, score))

            # Parse issues
            issues_match = re.search(r'ISSUES:\s*(.+?)(?:\n|$)', content)
            if issues_match:
                issues_text = issues_match.group(1).strip()
                if issues_text.lower() != "none":
                    issues = [
                        issue.strip()
                        for issue in issues_text.split(',')
                        if issue.strip()
                    ]

            # Parse retry
            retry_match = re.search(r'RETRY:\s*(yes|no)', content, re.IGNORECASE)
            if retry_match:
                retry = retry_match.group(1).lower() == 'yes'

        except Exception as e:
            logger.warning(f"[Evaluator] Failed to parse LLM response: {e}")
            # Fall back to rule-based
            return self.evaluate(result, task, criteria)

        passed = score >= criteria.min_confidence and result.success

        return EvaluationResult(
            passed=passed,
            score=score,
            issues=issues,
            retry_recommended=retry,
            retry_reason="LLM recommends retry" if retry else None
        )


class SynthesisEvaluator:
    """
    Evaluates synthesized multi-agent results.

    Checks that synthesis properly integrates all sub-results.
    """

    async def evaluate_synthesis(
        self,
        synthesized_answer: str,
        sub_results: Dict[str, AgentResult],
        original_task: str
    ) -> EvaluationResult:
        """
        Evaluate the quality of a synthesized answer.

        Args:
            synthesized_answer: The combined answer
            sub_results: Individual agent results
            original_task: The original task description

        Returns:
            EvaluationResult for the synthesis
        """
        issues = []
        score = 1.0

        # Check synthesis is not empty
        if not synthesized_answer or len(synthesized_answer.strip()) < 50:
            issues.append("Synthesized answer is too short")
            score -= 0.3

        # Check that synthesis includes content from successful sub-results
        successful_results = {
            task_id: result
            for task_id, result in sub_results.items()
            if result.success
        }

        if not successful_results:
            issues.append("No successful sub-results to synthesize")
            return EvaluationResult(
                passed=False,
                score=0.0,
                issues=issues,
                retry_recommended=False,
                retry_reason=None
            )

        # Check coverage of sub-results in synthesis
        coverage_score = self._check_coverage(synthesized_answer, successful_results)
        if coverage_score < 0.5:
            issues.append(f"Synthesis may not cover all sub-results (coverage: {coverage_score:.0%})")
            score -= 0.2

        # Check coherence (basic)
        if self._has_incoherence_markers(synthesized_answer):
            issues.append("Synthesis may have coherence issues")
            score -= 0.15

        score = max(0.0, min(1.0, score))
        passed = score >= 0.6

        return EvaluationResult(
            passed=passed,
            score=score,
            issues=issues,
            retry_recommended=not passed and score >= 0.4,
            retry_reason="Synthesis quality below threshold" if not passed else None
        )

    def _check_coverage(
        self,
        synthesis: str,
        sub_results: Dict[str, AgentResult]
    ) -> float:
        """Check what percentage of sub-results are reflected in synthesis."""
        if not sub_results:
            return 1.0

        synthesis_lower = synthesis.lower()
        covered = 0

        for task_id, result in sub_results.items():
            # Extract key terms from each result
            if result.answer:
                # Check if at least some content from this result appears
                result_words = set(
                    word.lower() for word in re.findall(r'\w{5,}', result.answer[:500])
                )
                if result_words:
                    matches = sum(1 for word in result_words if word in synthesis_lower)
                    if matches >= len(result_words) * 0.2:
                        covered += 1
                else:
                    covered += 1  # Cannot evaluate, assume covered

        return covered / len(sub_results)

    def _has_incoherence_markers(self, text: str) -> bool:
        """Check for markers of incoherent text."""
        incoherence_patterns = [
            r'\.\s*\.',  # Double periods
            r'(?:however|but|although)\s*,?\s*(?:however|but|although)',  # Repeated conjunctions
            r'\b(\w+)\s+\1\s+\1\b',  # Triple word repetition
        ]

        for pattern in incoherence_patterns:
            if re.search(pattern, text, re.IGNORECASE):
                return True

        return False


# Singleton accessor
_evaluator_instance: Optional[ResultEvaluator] = None
_synthesis_evaluator_instance: Optional[SynthesisEvaluator] = None


def get_evaluator(llm_adapter=None) -> ResultEvaluator:
    """Get the global evaluator instance."""
    global _evaluator_instance
    if _evaluator_instance is None:
        _evaluator_instance = ResultEvaluator(llm_adapter)
    return _evaluator_instance


def get_synthesis_evaluator() -> SynthesisEvaluator:
    """Get the global synthesis evaluator instance."""
    global _synthesis_evaluator_instance
    if _synthesis_evaluator_instance is None:
        _synthesis_evaluator_instance = SynthesisEvaluator()
    return _synthesis_evaluator_instance
