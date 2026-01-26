"""
Enhancement Coder Agent

Specialized agent for generating implementation plans and code for approved enhancements.
Creates detailed implementation phases, tasks, and test strategies.
"""
from typing import List, Optional, AsyncGenerator
import logging
import json
import re

from ..base import BaseAgent
from ..types import (
    AgentType, AgentContext, AgentResult, AgentMessage,
    MessageRole, AgentStreamChunk
)
from ..executor import AgentExecutor, get_executor
from ...models.enhancement import (
    ImplementationPlan, ImplementationPhase, TestStrategy,
    ArchitectureProposal
)

logger = logging.getLogger(__name__)


class EnhancementCoderAgent(BaseAgent):
    """
    Agent specialized for generating implementation plans and code.

    Responsibilities:
    - Create detailed implementation plans with phases
    - Break down work into manageable tasks
    - Define test strategies (unit, integration, e2e)
    - Create rollback plans
    - Generate code snippets for key implementations
    """

    def __init__(
        self,
        executor: Optional[AgentExecutor] = None,
        **kwargs
    ):
        super().__init__(
            name="Enhancement Coder",
            agent_type=AgentType.ENHANCEMENT_CODER,
            description="Generates implementation plans and code for approved enhancements",
            tools=["vector_search", "document_read", "bash"],
            **kwargs
        )
        self._executor = executor

    @property
    def executor(self) -> AgentExecutor:
        if self._executor is None:
            self._executor = get_executor()
        return self._executor

    def _get_default_prompt(self) -> str:
        """Fallback prompt if external file not found."""
        return """You are an Enhancement Coder Agent.
Create implementation plans with phases and tasks. Define test strategies.
Output structured JSON with phases, tests, and rollback plans."""

    async def create_implementation_plan(
        self,
        title: str,
        description: str,
        architecture_proposal: Optional[ArchitectureProposal] = None,
        context: Optional[AgentContext] = None
    ) -> ImplementationPlan:
        """
        Create an implementation plan for an enhancement.

        Args:
            title: Enhancement title
            description: Detailed description
            architecture_proposal: Architecture proposal from architect agent
            context: Agent execution context

        Returns:
            ImplementationPlan with phases, tests, and rollback plan
        """
        from datetime import datetime, timezone
        import uuid

        # Build the planning task
        task = f"""Create an implementation plan for the following enhancement:

## Title
{title}

## Description
{description}
"""
        if architecture_proposal:
            task += f"""
## Architecture Proposal

### Approach
{architecture_proposal.approach}

### File Changes
"""
            for fc in architecture_proposal.file_changes:
                task += f"- {fc.change_type.upper()}: {fc.file_path} - {fc.description}\n"

            if architecture_proposal.new_files:
                task += "\n### New Files\n"
                for nf in architecture_proposal.new_files:
                    task += f"- {nf.file_path} - {nf.purpose}\n"

            if architecture_proposal.api_changes:
                task += "\n### API Changes\n"
                for api in architecture_proposal.api_changes:
                    task += f"- {api.method} {api.endpoint} ({api.change_type}): {api.description}\n"

            if architecture_proposal.database_changes:
                task += "\n### Database Changes\n"
                for db in architecture_proposal.database_changes:
                    task += f"- {db}\n"

        task += """
Search the codebase to understand existing patterns, then create a detailed implementation plan.
Respond with ONLY the JSON implementation plan, no additional text."""

        if context is None:
            context = AgentContext(
                session_id=str(uuid.uuid4()),
                user_id="system",
                conversation_history=[],
                language="en"
            )

        try:
            # Execute planning task
            result = await self.execute(task, context)

            # Parse the response
            response_text = result.answer if result else ""

            # Extract JSON from response
            plan_data = self._extract_json(response_text)

            if plan_data:
                return ImplementationPlan(
                    phases=self._parse_phases(plan_data.get("phases", [])),
                    test_strategy=self._parse_test_strategy(plan_data.get("test_strategy", {})),
                    rollback_plan=plan_data.get("rollback_plan", "Revert changes and restore from backup"),
                    created_at=datetime.now(timezone.utc),
                    created_by_agent=str(self.agent_type.value)
                )
            else:
                # Fallback to default plan
                return self._create_default_plan(title)

        except Exception as e:
            logger.error(f"Error creating implementation plan: {e}")
            return self._create_default_plan(title)

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

    def _parse_phases(self, phases: List[dict]) -> List[ImplementationPhase]:
        """Parse implementation phases from response."""
        result = []
        for p in phases:
            try:
                result.append(ImplementationPhase(
                    phase_number=p.get("phase_number", len(result) + 1),
                    title=p.get("title", f"Phase {len(result) + 1}"),
                    description=p.get("description", ""),
                    tasks=p.get("tasks", []),
                    dependencies=p.get("dependencies", []),
                    estimated_effort=p.get("estimated_effort", "")
                ))
            except Exception:
                pass
        return result

    def _parse_test_strategy(self, strategy: dict) -> TestStrategy:
        """Parse test strategy from response."""
        return TestStrategy(
            unit_tests=strategy.get("unit_tests", []),
            integration_tests=strategy.get("integration_tests", []),
            e2e_tests=strategy.get("e2e_tests", []),
            manual_tests=strategy.get("manual_tests", [])
        )

    def _create_default_plan(self, title: str) -> ImplementationPlan:
        """Create a default implementation plan when parsing fails."""
        from datetime import datetime, timezone

        return ImplementationPlan(
            phases=[
                ImplementationPhase(
                    phase_number=1,
                    title="Setup & Preparation",
                    description="Prepare the development environment and review requirements",
                    tasks=[
                        "Review enhancement requirements",
                        "Set up development branch",
                        "Review architecture proposal"
                    ],
                    dependencies=[],
                    estimated_effort="1-2 hours"
                ),
                ImplementationPhase(
                    phase_number=2,
                    title="Core Implementation",
                    description="Implement the main functionality",
                    tasks=[
                        "Implement core features",
                        "Add necessary models/schemas",
                        "Create API endpoints if needed"
                    ],
                    dependencies=[1],
                    estimated_effort="To be determined"
                ),
                ImplementationPhase(
                    phase_number=3,
                    title="Testing & Verification",
                    description="Write tests and verify implementation",
                    tasks=[
                        "Write unit tests",
                        "Write integration tests",
                        "Manual testing"
                    ],
                    dependencies=[2],
                    estimated_effort="To be determined"
                ),
                ImplementationPhase(
                    phase_number=4,
                    title="Review & Documentation",
                    description="Code review and documentation updates",
                    tasks=[
                        "Code review",
                        "Update documentation",
                        "Create pull request"
                    ],
                    dependencies=[3],
                    estimated_effort="1-2 hours"
                )
            ],
            test_strategy=TestStrategy(
                unit_tests=["Unit tests for new functionality"],
                integration_tests=["Integration tests for API endpoints"],
                e2e_tests=["End-to-end workflow tests"],
                manual_tests=["Manual verification of UI changes"]
            ),
            rollback_plan="Revert the changes by reverting the PR or deployment. Restore any database changes from backup if needed.",
            created_at=datetime.now(timezone.utc),
            created_by_agent=str(self.agent_type.value)
        )

    async def execute(
        self,
        task: str,
        context: AgentContext
    ) -> AgentResult:
        """Execute an implementation planning task."""
        return await self.executor.run(self, task, context)

    async def stream(
        self,
        task: str,
        context: AgentContext
    ) -> AsyncGenerator[AgentStreamChunk, None]:
        """Stream execution of planning task."""
        async for chunk in self.executor.stream(self, task, context):
            yield chunk


# Singleton instance
_coder_agent: Optional[EnhancementCoderAgent] = None


def get_coder_agent() -> EnhancementCoderAgent:
    """Get the global coder agent instance."""
    global _coder_agent
    if _coder_agent is None:
        _coder_agent = EnhancementCoderAgent()
    return _coder_agent
