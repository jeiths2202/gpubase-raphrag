"""
Enhancement Analyst Agent

Specialized agent for analyzing enhancement requests.
Classifies, assesses, and provides recommendations for improvement requests.
"""
from typing import List, Optional, AsyncGenerator
import logging
import json

from ..base import BaseAgent
from ..types import (
    AgentType, AgentContext, AgentResult, AgentMessage,
    MessageRole, AgentStreamChunk
)
from ..executor import AgentExecutor, get_executor
from ...models.enhancement import (
    EnhancementType, EnhancementPriority, ComplexityLevel,
    AIAnalysisResult
)

logger = logging.getLogger(__name__)


class EnhancementAnalystAgent(BaseAgent):
    """
    Agent specialized for analyzing enhancement requests.

    Responsibilities:
    - Understand and summarize enhancement requests
    - Classify request types (feature, bug, improvement, etc.)
    - Assess priority based on impact and urgency
    - Identify affected system components
    - Evaluate feasibility and complexity
    - Generate clarifying questions if needed
    """

    def __init__(
        self,
        executor: Optional[AgentExecutor] = None,
        **kwargs
    ):
        super().__init__(
            name="Enhancement Analyst",
            agent_type=AgentType.ENHANCEMENT_ANALYST,
            description="Analyzes enhancement requests, classifies them, and provides recommendations",
            tools=["vector_search", "graph_query", "code_search"],
            **kwargs
        )
        self._executor = executor

    @property
    def executor(self) -> AgentExecutor:
        if self._executor is None:
            self._executor = get_executor()
        return self._executor

    def _get_default_prompt(self) -> str:
        return """You are an Enhancement Analyst Agent responsible for analyzing improvement requests
for a software system. Your role is to thoroughly understand, classify, and assess enhancement requests.

## Your Capabilities

1. **Understanding**: Parse and comprehend the user's enhancement request
2. **Classification**: Determine the type of request:
   - feature: New functionality
   - bug_fix: Bug correction
   - improvement: Enhancement to existing features
   - refactor: Code restructuring
   - documentation: Documentation updates
   - security: Security improvements
   - performance: Performance optimization

3. **Priority Assessment**: Evaluate priority based on:
   - Business impact
   - User value
   - Technical urgency
   - Dependencies

4. **Component Analysis**: Identify affected system components using code search

5. **Feasibility Evaluation**: Assess implementation feasibility (0.0-1.0 score)

6. **Complexity Estimation**: Rate complexity as low, medium, high, or very_high

## Analysis Protocol

1. First, search the codebase to understand the relevant components
2. Analyze the request against existing architecture
3. Identify potential risks and dependencies
4. Formulate a recommended approach
5. Generate clarifying questions if the request is ambiguous

## Output Format

You MUST respond with a structured JSON analysis:

```json
{
  "summary": "Brief summary of the enhancement request",
  "type_classification": "feature|bug_fix|improvement|refactor|documentation|security|performance",
  "priority_recommendation": "critical|high|medium|low",
  "affected_components": ["list", "of", "affected", "components"],
  "potential_risks": ["list", "of", "potential", "risks"],
  "dependencies": ["external", "dependencies", "if any"],
  "estimated_complexity": "low|medium|high|very_high",
  "feasibility_score": 0.8,
  "recommended_approach": "Detailed recommended implementation approach",
  "questions_for_submitter": ["Optional clarifying questions"]
}
```

Be thorough but concise. Focus on actionable insights."""

    async def analyze_enhancement(
        self,
        title: str,
        description: str,
        attachments_text: Optional[str] = None,
        context: Optional[AgentContext] = None
    ) -> AIAnalysisResult:
        """
        Analyze an enhancement request and return structured results.

        Args:
            title: Enhancement title
            description: Detailed description
            attachments_text: Extracted text from attachments
            context: Agent execution context

        Returns:
            AIAnalysisResult with analysis details
        """
        from datetime import datetime, timezone
        import uuid

        # Build the analysis task
        task = f"""Analyze the following enhancement request:

## Title
{title}

## Description
{description}
"""
        if attachments_text:
            task += f"""
## Attached Documents
{attachments_text}
"""

        task += """
Search the codebase to identify relevant components, then provide a comprehensive analysis.
Respond with ONLY the JSON analysis object, no additional text."""

        if context is None:
            context = AgentContext(
                session_id=str(uuid.uuid4()),
                user_id="system",
                conversation_history=[],
                language="en"
            )

        try:
            # Execute analysis
            result = await self.execute(task, context)

            # Parse the response
            response_text = result.answer if result else ""

            # Extract JSON from response
            analysis_data = self._extract_json(response_text)

            if analysis_data:
                return AIAnalysisResult(
                    summary=analysis_data.get("summary", f"Analysis of: {title}"),
                    type_classification=self._parse_type(analysis_data.get("type_classification")),
                    priority_recommendation=self._parse_priority(analysis_data.get("priority_recommendation")),
                    affected_components=analysis_data.get("affected_components", []),
                    potential_risks=analysis_data.get("potential_risks", []),
                    dependencies=analysis_data.get("dependencies", []),
                    estimated_complexity=self._parse_complexity(analysis_data.get("estimated_complexity")),
                    feasibility_score=float(analysis_data.get("feasibility_score", 0.7)),
                    recommended_approach=analysis_data.get("recommended_approach", ""),
                    questions_for_submitter=analysis_data.get("questions_for_submitter", []),
                    analyzed_at=datetime.now(timezone.utc),
                    agent_id=str(self.agent_type.value)
                )
            else:
                # Fallback to default analysis
                return self._create_default_analysis(title)

        except Exception as e:
            logger.error(f"Error analyzing enhancement: {e}")
            return self._create_default_analysis(title)

    def _extract_json(self, text: str) -> Optional[dict]:
        """Extract JSON object from text response."""
        try:
            # Try direct parse first
            return json.loads(text)
        except json.JSONDecodeError:
            pass

        # Try to find JSON block in text
        import re
        json_match = re.search(r'\{[\s\S]*\}', text)
        if json_match:
            try:
                return json.loads(json_match.group())
            except json.JSONDecodeError:
                pass

        return None

    def _parse_type(self, type_str: Optional[str]) -> EnhancementType:
        """Parse type string to enum."""
        if type_str:
            try:
                return EnhancementType(type_str.lower())
            except ValueError:
                pass
        return EnhancementType.IMPROVEMENT

    def _parse_priority(self, priority_str: Optional[str]) -> EnhancementPriority:
        """Parse priority string to enum."""
        if priority_str:
            try:
                return EnhancementPriority(priority_str.lower())
            except ValueError:
                pass
        return EnhancementPriority.MEDIUM

    def _parse_complexity(self, complexity_str: Optional[str]) -> ComplexityLevel:
        """Parse complexity string to enum."""
        if complexity_str:
            try:
                return ComplexityLevel(complexity_str.lower())
            except ValueError:
                pass
        return ComplexityLevel.MEDIUM

    def _create_default_analysis(self, title: str) -> AIAnalysisResult:
        """Create a default analysis when parsing fails."""
        from datetime import datetime, timezone

        return AIAnalysisResult(
            summary=f"Analysis of: {title}",
            type_classification=EnhancementType.IMPROVEMENT,
            priority_recommendation=EnhancementPriority.MEDIUM,
            affected_components=["Analysis pending - please retry"],
            potential_risks=[],
            dependencies=[],
            estimated_complexity=ComplexityLevel.MEDIUM,
            feasibility_score=0.7,
            recommended_approach="Detailed analysis could not be completed. Please retry or provide more details.",
            questions_for_submitter=[],
            analyzed_at=datetime.now(timezone.utc),
            agent_id=str(self.agent_type.value)
        )

    async def execute(
        self,
        task: str,
        context: AgentContext
    ) -> AgentResult:
        """Execute an analysis task."""
        return await self.executor.run(self, task, context)

    async def stream(
        self,
        task: str,
        context: AgentContext
    ) -> AsyncGenerator[AgentStreamChunk, None]:
        """Stream execution of analysis task."""
        async for chunk in self.executor.stream(self, task, context):
            yield chunk


# Singleton instance
_analyst_agent: Optional[EnhancementAnalystAgent] = None


def get_analyst_agent() -> EnhancementAnalystAgent:
    """Get the global analyst agent instance."""
    global _analyst_agent
    if _analyst_agent is None:
        _analyst_agent = EnhancementAnalystAgent()
    return _analyst_agent
