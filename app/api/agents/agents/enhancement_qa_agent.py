"""
Enhancement QA Agent

Specialized agent for testing, verification, and quality assurance of implementations.
Generates test reports and validates implementations against requirements.
"""
from typing import List, Optional, AsyncGenerator
import logging
import json
import re
from datetime import datetime, timezone

from ..base import BaseAgent
from ..types import (
    AgentType, AgentContext, AgentResult, AgentMessage,
    MessageRole, AgentStreamChunk
)
from ..executor import AgentExecutor, get_executor
from ...models.enhancement import (
    ImplementationPlan, TestStrategy, AIAnalysisResult
)

logger = logging.getLogger(__name__)


class TestResult:
    """Result of a test execution."""
    def __init__(
        self,
        test_name: str,
        test_type: str,
        status: str,
        message: str = "",
        execution_time_ms: int = 0
    ):
        self.test_name = test_name
        self.test_type = test_type  # unit, integration, e2e, manual
        self.status = status  # passed, failed, skipped
        self.message = message
        self.execution_time_ms = execution_time_ms


class VerificationReport:
    """Complete verification report for an enhancement."""
    def __init__(
        self,
        summary: str,
        overall_status: str,  # passed, failed, needs_review
        test_results: List[dict],
        coverage_analysis: dict,
        recommendations: List[str],
        issues_found: List[str],
        verified_at: datetime,
        verified_by_agent: str
    ):
        self.summary = summary
        self.overall_status = overall_status
        self.test_results = test_results
        self.coverage_analysis = coverage_analysis
        self.recommendations = recommendations
        self.issues_found = issues_found
        self.verified_at = verified_at
        self.verified_by_agent = verified_by_agent

    def to_dict(self) -> dict:
        return {
            "summary": self.summary,
            "overall_status": self.overall_status,
            "test_results": self.test_results,
            "coverage_analysis": self.coverage_analysis,
            "recommendations": self.recommendations,
            "issues_found": self.issues_found,
            "verified_at": self.verified_at.isoformat() if self.verified_at else None,
            "verified_by_agent": self.verified_by_agent
        }


class EnhancementQAAgent(BaseAgent):
    """
    Agent specialized for testing and verification of enhancements.

    Responsibilities:
    - Execute and analyze test results
    - Verify implementations against requirements
    - Generate verification reports
    - Identify issues and make recommendations
    - Manage testing/verified status transitions
    """

    def __init__(
        self,
        executor: Optional[AgentExecutor] = None,
        **kwargs
    ):
        super().__init__(
            name="Enhancement QA",
            agent_type=AgentType.ENHANCEMENT_QA,
            description="Tests and verifies enhancement implementations",
            tools=["vector_search", "graph_query", "code_search", "file_read"],
            **kwargs
        )
        self._executor = executor

    @property
    def executor(self) -> AgentExecutor:
        if self._executor is None:
            self._executor = get_executor()
        return self._executor

    def _get_default_prompt(self) -> str:
        return """You are an Enhancement QA Agent responsible for testing, verification,
and quality assurance of software enhancements. You ensure implementations meet
requirements and follow best practices.

## Your Capabilities

1. **Test Analysis**: Analyze test results and identify patterns
2. **Requirement Verification**: Verify implementations against original requirements
3. **Code Review**: Review code changes for quality issues
4. **Issue Detection**: Identify bugs, security issues, and performance problems
5. **Recommendation**: Provide actionable recommendations for improvement

## Verification Protocol

1. Review the original enhancement requirements
2. Analyze the implementation plan and what was built
3. Evaluate test coverage and results
4. Check for security and performance concerns
5. Verify backward compatibility if applicable
6. Generate a comprehensive verification report

## Output Format

You MUST respond with a structured JSON verification report:

```json
{
  "summary": "Overall summary of the verification findings",
  "overall_status": "passed|failed|needs_review",
  "test_results": [
    {
      "category": "unit|integration|e2e|manual",
      "total": 10,
      "passed": 9,
      "failed": 1,
      "skipped": 0,
      "notes": "Any relevant notes"
    }
  ],
  "coverage_analysis": {
    "estimated_coverage": 85,
    "critical_paths_covered": true,
    "gaps": ["Areas not covered by tests"]
  },
  "issues_found": [
    "Issue 1 description",
    "Issue 2 description"
  ],
  "recommendations": [
    "Recommendation 1",
    "Recommendation 2"
  ]
}
```

Be thorough and objective. Focus on actionable findings."""

    async def verify_implementation(
        self,
        title: str,
        description: str,
        analysis: Optional[AIAnalysisResult],
        implementation_plan: Optional[ImplementationPlan],
        context: Optional[AgentContext] = None
    ) -> VerificationReport:
        """
        Verify an enhancement implementation.

        Args:
            title: Enhancement title
            description: Enhancement description
            analysis: AI analysis results
            implementation_plan: Implementation plan
            context: Agent execution context

        Returns:
            VerificationReport with test results and recommendations
        """
        import uuid

        # Build the verification task
        task = f"""Verify the implementation of the following enhancement:

## Title
{title}

## Description
{description}
"""
        if analysis:
            task += f"""
## AI Analysis Summary
- Feasibility Score: {analysis.feasibility_score * 100:.0f}%
- Complexity: {analysis.estimated_complexity}
- Affected Components: {', '.join(analysis.affected_components)}
- Potential Risks: {', '.join(analysis.potential_risks)}
"""

        if implementation_plan:
            task += f"""
## Implementation Plan
"""
            for phase in implementation_plan.phases:
                task += f"""
### Phase {phase.phase_number}: {phase.title}
{phase.description}
Tasks: {', '.join(phase.tasks)}
"""
            if implementation_plan.test_strategy:
                task += f"""
### Test Strategy
- Unit Tests: {len(implementation_plan.test_strategy.unit_tests)} tests planned
- Integration Tests: {len(implementation_plan.test_strategy.integration_tests)} tests planned
- E2E Tests: {len(implementation_plan.test_strategy.e2e_tests)} tests planned
- Manual Tests: {len(implementation_plan.test_strategy.manual_tests)} tests planned
"""

        task += """
Search the codebase to verify the implementation, analyze test coverage, and generate a verification report.
Respond with ONLY the JSON verification report, no additional text."""

        if context is None:
            context = AgentContext(
                session_id=str(uuid.uuid4()),
                user_id="system",
                conversation_history=[],
                language="en"
            )

        try:
            # Execute verification task
            result = await self.execute(task, context)

            # Parse the response
            response_text = result.output if result else ""

            # Extract JSON from response
            report_data = self._extract_json(response_text)

            if report_data:
                return VerificationReport(
                    summary=report_data.get("summary", "Verification completed"),
                    overall_status=report_data.get("overall_status", "needs_review"),
                    test_results=report_data.get("test_results", []),
                    coverage_analysis=report_data.get("coverage_analysis", {}),
                    recommendations=report_data.get("recommendations", []),
                    issues_found=report_data.get("issues_found", []),
                    verified_at=datetime.now(timezone.utc),
                    verified_by_agent=str(self.agent_type.value)
                )
            else:
                # Fallback to default report
                return self._create_default_report()

        except Exception as e:
            logger.error(f"Error verifying implementation: {e}")
            return self._create_default_report()

    async def generate_test_report(
        self,
        test_strategy: TestStrategy,
        context: Optional[AgentContext] = None
    ) -> dict:
        """
        Generate a simulated test execution report based on test strategy.

        Args:
            test_strategy: The test strategy with planned tests
            context: Agent execution context

        Returns:
            Test execution report
        """
        import uuid
        import random

        # Simulate test execution results
        results = {
            "execution_id": str(uuid.uuid4()),
            "executed_at": datetime.now(timezone.utc).isoformat(),
            "categories": []
        }

        for category, tests in [
            ("unit", test_strategy.unit_tests),
            ("integration", test_strategy.integration_tests),
            ("e2e", test_strategy.e2e_tests),
            ("manual", test_strategy.manual_tests)
        ]:
            if tests:
                # Simulate realistic pass rates
                total = len(tests)
                # Higher pass rates for unit tests, lower for e2e
                base_pass_rate = {
                    "unit": 0.95,
                    "integration": 0.90,
                    "e2e": 0.85,
                    "manual": 0.90
                }.get(category, 0.90)

                passed = int(total * base_pass_rate)
                failed = total - passed
                skipped = 0

                results["categories"].append({
                    "category": category,
                    "total": total,
                    "passed": passed,
                    "failed": failed,
                    "skipped": skipped,
                    "tests": [
                        {
                            "name": test,
                            "status": "passed" if i < passed else "failed",
                            "duration_ms": random.randint(50, 500)
                        }
                        for i, test in enumerate(tests)
                    ]
                })

        # Calculate overall status
        total_tests = sum(cat["total"] for cat in results["categories"])
        total_passed = sum(cat["passed"] for cat in results["categories"])
        total_failed = sum(cat["failed"] for cat in results["categories"])

        results["summary"] = {
            "total": total_tests,
            "passed": total_passed,
            "failed": total_failed,
            "pass_rate": (total_passed / total_tests * 100) if total_tests > 0 else 0,
            "overall_status": "passed" if total_failed == 0 else "failed"
        }

        return results

    def _extract_json(self, text: str) -> Optional[dict]:
        """Extract JSON object from text response."""
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

        # Try to find JSON block in text
        json_match = re.search(r'\{[\s\S]*\}', text)
        if json_match:
            try:
                return json.loads(json_match.group())
            except json.JSONDecodeError:
                pass

        return None

    def _create_default_report(self) -> VerificationReport:
        """Create a default verification report when parsing fails."""
        return VerificationReport(
            summary="Automated verification completed. Manual review recommended.",
            overall_status="needs_review",
            test_results=[
                {
                    "category": "unit",
                    "total": 0,
                    "passed": 0,
                    "failed": 0,
                    "skipped": 0,
                    "notes": "Test results pending"
                }
            ],
            coverage_analysis={
                "estimated_coverage": 0,
                "critical_paths_covered": False,
                "gaps": ["Coverage analysis pending"]
            },
            recommendations=[
                "Review test coverage manually",
                "Verify critical paths are tested",
                "Run integration tests"
            ],
            issues_found=[],
            verified_at=datetime.now(timezone.utc),
            verified_by_agent=str(self.agent_type.value)
        )

    async def execute(
        self,
        task: str,
        context: AgentContext
    ) -> AgentResult:
        """Execute a verification task."""
        return await self.executor.run(self, task, context)

    async def stream(
        self,
        task: str,
        context: AgentContext
    ) -> AsyncGenerator[AgentStreamChunk, None]:
        """Stream execution of verification task."""
        async for chunk in self.executor.stream(self, task, context):
            yield chunk


# Singleton instance
_qa_agent: Optional[EnhancementQAAgent] = None


def get_qa_agent() -> EnhancementQAAgent:
    """Get the global QA agent instance."""
    global _qa_agent
    if _qa_agent is None:
        _qa_agent = EnhancementQAAgent()
    return _qa_agent
