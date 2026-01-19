"""
Verifier Agent

Validates multi-agent execution results for quality, grounding, and consistency.
Decides whether to accept, partially retry, or fully replan.
"""
import json
import logging
import re
import uuid
from pathlib import Path
from typing import Optional, Dict, Any, List, AsyncGenerator

from ..base import BaseAgent
from ..types import (
    AgentType, AgentContext, AgentResult, AgentStreamChunk
)
from .types import (
    VerificationResult, VerificationDecision, Issue, IssueType, IssueSeverity
)

logger = logging.getLogger(__name__)


class VerifierAgent(BaseAgent):
    """
    Verifier Agent for the Auto Agent orchestration system.

    Responsibilities:
    - Check execution failures (timeout, empty, exception)
    - Validate grounding (claims vs sources)
    - Check consistency (contradictions between agents)
    - Check completeness (answer vs task)
    - Make decision: ACCEPT, PARTIAL_RETRY, or FULL_REPLAN
    """

    def __init__(
        self,
        llm_adapter=None,
        name: str = "VerifierAgent",
        description: str = "Validates and verifies multi-agent execution results"
    ):
        """
        Initialize the Verifier Agent.

        Args:
            llm_adapter: LLM adapter for verification reasoning
            name: Agent name
            description: Agent description
        """
        super().__init__(
            name=name,
            agent_type=AgentType.PLANNER,  # Reuse planner type internally
            description=description,
            tools=[],
        )
        self._llm_adapter = llm_adapter
        self._system_prompt = self._load_verifier_prompt()

    @property
    def llm_adapter(self):
        """Lazy load LLM adapter"""
        if self._llm_adapter is None:
            from ..registry import get_llm_adapter
            self._llm_adapter = get_llm_adapter()
        return self._llm_adapter

    def _load_verifier_prompt(self) -> str:
        """Load the verifier system prompt"""
        prompt_file = Path(__file__).parent / "prompts" / "verifier.txt"
        if prompt_file.exists():
            return prompt_file.read_text(encoding="utf-8")
        return self._get_default_prompt()

    def _get_default_prompt(self) -> str:
        """Fallback prompt if file not found"""
        return """You are a Verifier Agent. Validate multi-agent results for:
1. Execution success
2. Grounding in sources
3. Consistency between agents
4. Completeness of answer

Return JSON with decision (accept/partial_retry/full_replan) and scores."""

    async def verify(
        self,
        original_task: str,
        aggregated_results: Dict[str, AgentResult],
        sources: List[Dict[str, Any]],
        context: Optional[AgentContext] = None
    ) -> VerificationResult:
        """
        Verify aggregated agent results.

        Args:
            original_task: The user's original task
            aggregated_results: Dict of task_id -> AgentResult
            sources: Collected sources from all agents
            context: Agent context

        Returns:
            VerificationResult with decision and issues
        """
        # First, do quick rule-based checks
        quick_result = self._quick_validation(aggregated_results)

        # If quick check finds critical issues, return early
        if quick_result.decision == VerificationDecision.FULL_REPLAN:
            logger.warning("[VerifierAgent] Quick validation found critical issues")
            return quick_result

        # Use LLM for deeper verification
        try:
            llm_result = await self._llm_verification(
                original_task, aggregated_results, sources, context
            )

            # Merge quick and LLM results
            merged_result = self._merge_verification_results(quick_result, llm_result)

            logger.info(
                f"[VerifierAgent] Verification complete: decision={merged_result.decision.value}, "
                f"score={merged_result.overall_score:.2f}"
            )

            return merged_result

        except Exception as e:
            logger.error(f"[VerifierAgent] LLM verification failed: {e}")
            # Fall back to quick result
            return quick_result

    def _quick_validation(
        self,
        aggregated_results: Dict[str, AgentResult]
    ) -> VerificationResult:
        """
        Quick rule-based validation before LLM verification.
        Catches obvious failures quickly.
        """
        issues: List[Issue] = []
        critical_issues: List[str] = []
        tasks_to_retry: List[str] = []

        failed_count = 0
        empty_count = 0
        total_count = len(aggregated_results)

        for task_id, result in aggregated_results.items():
            # Check execution failure
            if not result.success:
                issue = Issue(
                    issue_id=str(uuid.uuid4()),
                    issue_type=IssueType.EXECUTION_FAILURE,
                    severity=IssueSeverity.CRITICAL,
                    task_id=task_id,
                    description=f"Task {task_id} failed: {result.error}",
                    evidence=result.error,
                    retryable=True
                )
                issues.append(issue)
                critical_issues.append(issue.issue_id)
                tasks_to_retry.append(task_id)
                failed_count += 1

            # Check empty result
            elif not result.answer or len(result.answer.strip()) < 10:
                issue = Issue(
                    issue_id=str(uuid.uuid4()),
                    issue_type=IssueType.EMPTY_RESULT,
                    severity=IssueSeverity.MAJOR,
                    task_id=task_id,
                    description=f"Task {task_id} returned empty or very short result",
                    retryable=True
                )
                issues.append(issue)
                tasks_to_retry.append(task_id)
                empty_count += 1

            # Check for no sources (for RAG/IMS agents)
            elif result.agent_type in [AgentType.RAG, AgentType.IMS]:
                if not result.sources:
                    issue = Issue(
                        issue_id=str(uuid.uuid4()),
                        issue_type=IssueType.UNGROUNDED_CLAIM,
                        severity=IssueSeverity.MAJOR,
                        task_id=task_id,
                        description=f"Task {task_id} has no source citations",
                        suggested_fix="Retry with emphasis on citing sources",
                        retryable=True
                    )
                    issues.append(issue)

        # Calculate execution score
        if total_count == 0:
            execution_score = 0.0
        else:
            execution_score = 1.0 - (failed_count + empty_count * 0.5) / total_count

        # Determine decision based on failure rate
        if failed_count == total_count:
            decision = VerificationDecision.FULL_REPLAN
        elif failed_count > 0 or empty_count > 0:
            decision = VerificationDecision.PARTIAL_RETRY
        else:
            decision = VerificationDecision.ACCEPT

        return VerificationResult(
            decision=decision,
            overall_score=execution_score,
            grounding_score=1.0,  # Will be updated by LLM
            consistency_score=1.0,  # Will be updated by LLM
            completeness_score=1.0,  # Will be updated by LLM
            execution_score=execution_score,
            issues=issues,
            critical_issues=critical_issues,
            tasks_to_retry=tasks_to_retry
        )

    async def _llm_verification(
        self,
        original_task: str,
        aggregated_results: Dict[str, AgentResult],
        sources: List[Dict[str, Any]],
        context: Optional[AgentContext]
    ) -> VerificationResult:
        """Use LLM for deep verification"""
        # Build verification prompt
        verification_prompt = self._build_verification_prompt(
            original_task, aggregated_results, sources
        )

        messages = [
            {"role": "system", "content": self._system_prompt},
            {"role": "user", "content": verification_prompt}
        ]

        response = await self.llm_adapter.generate(messages)
        verification_json = self._parse_verification_response(response.get("content", ""))

        return self._build_verification_result(verification_json)

    def _build_verification_prompt(
        self,
        original_task: str,
        aggregated_results: Dict[str, AgentResult],
        sources: List[Dict[str, Any]]
    ) -> str:
        """Build the prompt for LLM verification"""
        parts = [
            f"## Original Task\n{original_task}",
            "\n## Agent Results"
        ]

        for task_id, result in aggregated_results.items():
            result_summary = {
                "task_id": task_id,
                "agent_type": result.agent_type.value,
                "success": result.success,
                "answer_preview": result.answer[:500] if result.answer else "",
                "source_count": len(result.sources),
                "execution_time": result.execution_time
            }
            parts.append(f"\n### {task_id}\n```json\n{json.dumps(result_summary, ensure_ascii=False, indent=2)}\n```")

        # Add sources summary
        if sources:
            parts.append(f"\n## Available Sources ({len(sources)} total)")
            for i, source in enumerate(sources[:10]):  # Limit to first 10
                source_type = source.get("type", "unknown")
                source_title = source.get("title", source.get("doc_name", "Untitled"))
                parts.append(f"- [{source_type}] {source_title}")

        parts.append("\n## Instructions\nVerify the results and return the verification JSON.")

        return "\n".join(parts)

    def _parse_verification_response(self, content: str) -> Dict[str, Any]:
        """Parse LLM verification response"""
        content = content.strip()

        # Remove markdown code blocks
        if content.startswith("```"):
            content = re.sub(r'^```(?:json)?\s*', '', content)
            content = re.sub(r'\s*```$', '', content)

        # Find JSON object
        json_match = re.search(r'\{.*\}', content, re.DOTALL)
        if not json_match:
            raise ValueError("No JSON object found in verification response")

        return json.loads(json_match.group())

    def _build_verification_result(
        self,
        verification_json: Dict[str, Any]
    ) -> VerificationResult:
        """Build VerificationResult from parsed JSON"""
        # Map decision string to enum
        decision_str = verification_json.get("decision", "accept").lower()
        decision_map = {
            "accept": VerificationDecision.ACCEPT,
            "partial_retry": VerificationDecision.PARTIAL_RETRY,
            "full_replan": VerificationDecision.FULL_REPLAN
        }
        decision = decision_map.get(decision_str, VerificationDecision.ACCEPT)

        # Parse issues
        issues: List[Issue] = []
        for issue_data in verification_json.get("issues", []):
            issue_type_str = issue_data.get("issue_type", "low_confidence")
            issue_type = self._map_issue_type(issue_type_str)

            severity_str = issue_data.get("severity", "minor")
            severity = self._map_severity(severity_str)

            issue = Issue(
                issue_id=issue_data.get("issue_id", str(uuid.uuid4())),
                issue_type=issue_type,
                severity=severity,
                task_id=issue_data.get("task_id"),
                description=issue_data.get("description", ""),
                evidence=issue_data.get("evidence"),
                suggested_fix=issue_data.get("suggested_fix"),
                retryable=issue_data.get("retryable", True)
            )
            issues.append(issue)

        return VerificationResult(
            decision=decision,
            overall_score=verification_json.get("overall_score", 0.8),
            grounding_score=verification_json.get("grounding_score", 0.8),
            consistency_score=verification_json.get("consistency_score", 1.0),
            completeness_score=verification_json.get("completeness_score", 0.8),
            execution_score=verification_json.get("execution_score", 1.0),
            issues=issues,
            critical_issues=verification_json.get("critical_issues", []),
            tasks_to_retry=verification_json.get("tasks_to_retry", []),
            retry_hints=verification_json.get("retry_hints", {}),
            internal_reasoning=verification_json.get("internal_reasoning")
        )

    def _map_issue_type(self, issue_type_str: str) -> IssueType:
        """Map issue type string to enum"""
        type_map = {
            "ungrounded_claim": IssueType.UNGROUNDED_CLAIM,
            "contradiction": IssueType.CONTRADICTION,
            "incomplete": IssueType.INCOMPLETE,
            "execution_failure": IssueType.EXECUTION_FAILURE,
            "timeout": IssueType.TIMEOUT,
            "empty_result": IssueType.EMPTY_RESULT,
            "low_confidence": IssueType.LOW_CONFIDENCE,
            "hallucination": IssueType.HALLUCINATION,
        }
        return type_map.get(issue_type_str.lower(), IssueType.LOW_CONFIDENCE)

    def _map_severity(self, severity_str: str) -> IssueSeverity:
        """Map severity string to enum"""
        severity_map = {
            "critical": IssueSeverity.CRITICAL,
            "major": IssueSeverity.MAJOR,
            "minor": IssueSeverity.MINOR,
            "info": IssueSeverity.INFO,
        }
        return severity_map.get(severity_str.lower(), IssueSeverity.MINOR)

    def _merge_verification_results(
        self,
        quick_result: VerificationResult,
        llm_result: VerificationResult
    ) -> VerificationResult:
        """Merge quick and LLM verification results"""
        # Combine issues (avoid duplicates by task_id + issue_type)
        seen_issues = set()
        merged_issues = []

        for issue in quick_result.issues + llm_result.issues:
            key = (issue.task_id, issue.issue_type)
            if key not in seen_issues:
                seen_issues.add(key)
                merged_issues.append(issue)

        # Use more conservative (lower) scores
        merged_grounding = min(quick_result.grounding_score, llm_result.grounding_score)
        merged_consistency = min(quick_result.consistency_score, llm_result.consistency_score)
        merged_completeness = min(quick_result.completeness_score, llm_result.completeness_score)
        merged_execution = min(quick_result.execution_score, llm_result.execution_score)

        # Calculate overall score
        overall_score = (
            merged_grounding * 0.3 +
            merged_consistency * 0.2 +
            merged_completeness * 0.3 +
            merged_execution * 0.2
        )

        # Determine final decision
        if quick_result.decision == VerificationDecision.FULL_REPLAN:
            decision = VerificationDecision.FULL_REPLAN
        elif llm_result.decision == VerificationDecision.FULL_REPLAN:
            decision = VerificationDecision.FULL_REPLAN
        elif (quick_result.decision == VerificationDecision.PARTIAL_RETRY or
              llm_result.decision == VerificationDecision.PARTIAL_RETRY):
            decision = VerificationDecision.PARTIAL_RETRY
        else:
            decision = VerificationDecision.ACCEPT

        # Override based on overall score
        if overall_score < 0.4:
            decision = VerificationDecision.FULL_REPLAN
        elif overall_score < 0.6 and decision == VerificationDecision.ACCEPT:
            decision = VerificationDecision.PARTIAL_RETRY

        # Merge tasks to retry
        tasks_to_retry = list(set(
            quick_result.tasks_to_retry + llm_result.tasks_to_retry
        ))

        # Merge critical issues
        critical_issues = list(set(
            quick_result.critical_issues + llm_result.critical_issues
        ))

        # Merge retry hints
        retry_hints = {**quick_result.retry_hints, **llm_result.retry_hints}

        return VerificationResult(
            decision=decision,
            overall_score=overall_score,
            grounding_score=merged_grounding,
            consistency_score=merged_consistency,
            completeness_score=merged_completeness,
            execution_score=merged_execution,
            issues=merged_issues,
            critical_issues=critical_issues,
            tasks_to_retry=tasks_to_retry,
            retry_hints=retry_hints,
            internal_reasoning=llm_result.internal_reasoning
        )

    async def execute(
        self,
        task: str,
        context: AgentContext
    ) -> AgentResult:
        """Execute is not the primary interface - use verify() instead"""
        import time
        return AgentResult(
            answer="Verifier Agent should be called via verify() method",
            agent_type=AgentType.PLANNER,
            steps=0,
            execution_time=0.0,
            success=False,
            error="Use verify() method instead of execute()"
        )

    async def stream(
        self,
        task: str,
        context: AgentContext
    ) -> AsyncGenerator[AgentStreamChunk, None]:
        """Stream is not the primary interface"""
        yield AgentStreamChunk(
            chunk_type="error",
            content="Verifier Agent should be called via verify() method"
        )


# Singleton instance
_verifier_agent: Optional[VerifierAgent] = None


def get_verifier_agent(llm_adapter=None) -> VerifierAgent:
    """Get or create the Verifier Agent instance"""
    global _verifier_agent
    if _verifier_agent is None:
        _verifier_agent = VerifierAgent(llm_adapter=llm_adapter)
    elif llm_adapter and _verifier_agent._llm_adapter is None:
        _verifier_agent._llm_adapter = llm_adapter
    return _verifier_agent
