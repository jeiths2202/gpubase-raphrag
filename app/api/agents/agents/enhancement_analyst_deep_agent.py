"""
Enhancement Analyst Deep Agent

Deep Agents 기반 개선요청 분석 에이전트.
DeepAgentAdapter를 사용하여 기존 EnhancementAnalystAgent와 동일한 인터페이스 제공.
"""
from typing import Optional
import logging
import json
import re
from datetime import datetime, timezone
import uuid

from ..adapters.deep_agent_adapter import DeepAgentAdapter
from ..types import AgentType, AgentContext
from ..middleware import get_rag_tools, get_code_tools, RAG_SYSTEM_PROMPT
from ...models.enhancement import (
    EnhancementType, EnhancementPriority, ComplexityLevel,
    AIAnalysisResult
)

logger = logging.getLogger(__name__)

# Deep Agents 의존성 체크
try:
    from deepagents import create_deep_agent
    DEEPAGENTS_AVAILABLE = True
except ImportError:
    DEEPAGENTS_AVAILABLE = False


ENHANCEMENT_ANALYST_PROMPT = """You are an Enhancement Analyst Agent responsible for analyzing improvement requests
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

1. Search the knowledge base to understand the system architecture
2. Identify ACTUAL affected components based on search results
3. Analyze the request against existing architecture
4. Identify potential risks and dependencies
5. Formulate a recommended approach
6. Generate clarifying questions if the request is ambiguous

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

Be thorough but concise. Focus on actionable insights.
"""


class EnhancementAnalystDeepAgent:
    """
    Deep Agents 기반 개선요청 분석 에이전트.

    기존 EnhancementAnalystAgent와 동일한 인터페이스를 제공하면서
    Deep Agents 프레임워크를 사용합니다.
    """

    def __init__(self):
        self._deep_agent: Optional[DeepAgentAdapter] = None

    @property
    def deep_agent(self) -> DeepAgentAdapter:
        """Lazy-initialize the Deep Agent."""
        if self._deep_agent is None:
            # RAG tools로 지식베이스 검색 기능 제공
            tools = get_rag_tools()

            self._deep_agent = DeepAgentAdapter(
                name="EnhancementAnalystDeepAgent",
                agent_type=AgentType.ENHANCEMENT_ANALYST,
                description="Deep Agents 기반 개선요청 분석 에이전트",
                tools=tools,
                subagents=None,  # 분석 에이전트는 SubAgent 불필요
                system_prompt=RAG_SYSTEM_PROMPT + "\n\n" + ENHANCEMENT_ANALYST_PROMPT,
            )
            logger.info("[EnhancementAnalystDeepAgent] Deep Agent initialized")

        return self._deep_agent

    async def analyze_enhancement(
        self,
        title: str,
        description: str,
        attachments_text: Optional[str] = None,
        context: Optional[AgentContext] = None
    ) -> AIAnalysisResult:
        """
        Deep Agents를 사용하여 개선요청 분석.

        Args:
            title: 개선요청 제목
            description: 상세 설명
            attachments_text: 첨부파일에서 추출한 텍스트
            context: Agent 실행 컨텍스트

        Returns:
            AIAnalysisResult with analysis details
        """
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
Search the knowledge base to identify relevant components, then provide a comprehensive analysis.
Respond with ONLY the JSON analysis object, no additional text."""

        if context is None:
            context = AgentContext(
                session_id=str(uuid.uuid4()),
                user_id="system",
                conversation_history=[],
                language="en"
            )

        try:
            # Execute analysis via Deep Agent
            result = await self.deep_agent.execute(task, context)

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
                    agent_id="enhancement_analyst_deep"
                )
            else:
                # Fallback to default analysis
                logger.warning("[EnhancementAnalystDeepAgent] Failed to parse JSON, using default")
                return self._create_default_analysis(title)

        except Exception as e:
            logger.error(f"[EnhancementAnalystDeepAgent] Error analyzing enhancement: {e}")
            return self._create_default_analysis(title)

    def _extract_json(self, text: str) -> Optional[dict]:
        """Extract JSON object from text response."""
        try:
            # Try direct parse first
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
            agent_id="enhancement_analyst_deep"
        )


# Singleton instance
_deep_analyst_agent: Optional[EnhancementAnalystDeepAgent] = None


def get_deep_analyst_agent() -> EnhancementAnalystDeepAgent:
    """Get the global Deep Agents based analyst agent instance."""
    global _deep_analyst_agent
    if _deep_analyst_agent is None:
        _deep_analyst_agent = EnhancementAnalystDeepAgent()
    return _deep_analyst_agent
