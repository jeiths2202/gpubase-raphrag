"""
Enhancement Architect Agent

Specialized agent for designing architecture proposals for approved enhancements.
Evaluates implementation approaches, identifies affected components, and creates
detailed technical specifications.
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
    ArchitectureProposal, DesignDecision, FileChange, NewFile, APIChange
)

logger = logging.getLogger(__name__)


class EnhancementArchitectAgent(BaseAgent):
    """
    Agent specialized for designing architecture proposals.

    Responsibilities:
    - Analyze enhancement requirements and existing codebase
    - Design implementation approach
    - Identify files to modify/create
    - Define API changes if needed
    - Consider security and backward compatibility
    - Create migration plans if required
    """

    def __init__(
        self,
        executor: Optional[AgentExecutor] = None,
        **kwargs
    ):
        super().__init__(
            name="Enhancement Architect",
            agent_type=AgentType.ENHANCEMENT_ARCHITECT,
            description="Designs architecture proposals and implementation plans for enhancements",
            tools=["vector_search", "graph_query", "document_read", "bash"],
            **kwargs
        )
        self._executor = executor

    @property
    def executor(self) -> AgentExecutor:
        if self._executor is None:
            self._executor = get_executor()
        return self._executor

    def _get_default_prompt(self) -> str:
        return """You are an Enhancement Architect Agent responsible for designing technical solutions
for approved enhancement requests. You have deep knowledge of software architecture patterns
and best practices.

## Your Capabilities

1. **Codebase Analysis**: Search and understand the existing codebase structure
2. **Architecture Design**: Create detailed technical proposals
3. **Component Identification**: Identify affected files and components
4. **API Design**: Design new or modified API endpoints
5. **Security Review**: Consider security implications
6. **Migration Planning**: Plan data migrations if needed

## Available Tools

You MUST use these tools to analyze the codebase before designing:

1. **bash** - Execute shell commands to explore the codebase:
   - `find . -name "*.py" -path "*/app/*"` - Find Python files
   - `find . -name "*.tsx" -path "*/src/*"` - Find React components
   - `grep -r "keyword" --include="*.py" ./app` - Search for patterns
   - `cat path/to/file.py` - Read file contents
   - `ls -la directory/` - List directory contents

2. **vector_search** - Search knowledge base for related documentation
3. **document_read** - Read documents from the knowledge base

## Analysis Protocol

IMPORTANT: You MUST use the bash tool to explore the actual codebase before proposing any architecture.

1. Use `find` command to discover project structure and relevant files
2. Use `grep` to search for related code patterns and existing implementations
3. Use `cat` to read specific files that are relevant to the enhancement
4. Based on ACTUAL code found, design a solution that fits the existing architecture
5. List REAL file paths from the codebase (not imaginary ones)
6. Define API changes if needed
7. Consider backward compatibility and migration needs
8. Document security considerations

## Output Format

You MUST respond with a structured JSON architecture proposal:

```json
{
  "approach": "High-level description of the implementation approach",
  "design_decisions": [
    {
      "title": "Decision title",
      "description": "What we decided",
      "rationale": "Why we chose this approach",
      "alternatives_considered": ["Alt 1", "Alt 2"],
      "trade_offs": "What we gain vs what we lose"
    }
  ],
  "file_changes": [
    {
      "file_path": "path/to/existing/file.py",
      "change_type": "modify",
      "description": "What changes need to be made",
      "estimated_lines": 50
    }
  ],
  "new_files": [
    {
      "file_path": "path/to/new/file.py",
      "purpose": "Purpose of this new file",
      "template": "Optional template or skeleton code"
    }
  ],
  "api_changes": [
    {
      "endpoint": "/api/v1/example",
      "method": "POST",
      "change_type": "add",
      "description": "Description of the API change"
    }
  ],
  "database_changes": ["List of database schema changes if any"],
  "security_considerations": ["Security aspects to consider"],
  "backward_compatible": true,
  "migration_required": false
}
```

Be thorough and specific. Include actual file paths from the codebase."""

    async def design_architecture(
        self,
        title: str,
        description: str,
        ai_analysis: Optional[dict] = None,
        context: Optional[AgentContext] = None
    ) -> ArchitectureProposal:
        """
        Design an architecture proposal for an enhancement.

        Args:
            title: Enhancement title
            description: Detailed description
            ai_analysis: Previous AI analysis results
            context: Agent execution context

        Returns:
            ArchitectureProposal with detailed technical design
        """
        from datetime import datetime, timezone
        import uuid

        # Build the design task
        task = f"""Design an architecture proposal for the following enhancement:

## Title
{title}

## Description
{description}
"""
        if ai_analysis:
            task += f"""
## Previous AI Analysis
- Type: {ai_analysis.get('type_classification', 'unknown')}
- Priority: {ai_analysis.get('priority_recommendation', 'unknown')}
- Complexity: {ai_analysis.get('estimated_complexity', 'unknown')}
- Affected Components: {', '.join(ai_analysis.get('affected_components', []))}
- Recommended Approach: {ai_analysis.get('recommended_approach', 'Not provided')}
"""

        task += """
Search the codebase to understand the existing architecture, then provide a detailed proposal.
Respond with ONLY the JSON architecture proposal, no additional text."""

        if context is None:
            context = AgentContext(
                session_id=str(uuid.uuid4()),
                user_id="system",
                conversation_history=[],
                language="en"
            )

        try:
            # Execute design task
            result = await self.execute(task, context)

            # Parse the response
            response_text = result.answer if result else ""

            # Extract JSON from response
            proposal_data = self._extract_json(response_text)

            if proposal_data:
                return ArchitectureProposal(
                    approach=proposal_data.get("approach", f"Implementation approach for: {title}"),
                    design_decisions=self._parse_design_decisions(
                        proposal_data.get("design_decisions", [])
                    ),
                    file_changes=self._parse_file_changes(
                        proposal_data.get("file_changes", [])
                    ),
                    new_files=self._parse_new_files(
                        proposal_data.get("new_files", [])
                    ),
                    api_changes=self._parse_api_changes(
                        proposal_data.get("api_changes", [])
                    ),
                    database_changes=proposal_data.get("database_changes", []),
                    security_considerations=proposal_data.get("security_considerations", []),
                    backward_compatible=proposal_data.get("backward_compatible", True),
                    migration_required=proposal_data.get("migration_required", False),
                    reviewed_at=datetime.now(timezone.utc),
                    reviewer_agent_id=str(self.agent_type.value)
                )
            else:
                # Fallback to default proposal
                return self._create_default_proposal(title)

        except Exception as e:
            logger.error(f"Error designing architecture: {e}")
            return self._create_default_proposal(title)

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

    def _parse_design_decisions(self, decisions: List[dict]) -> List[DesignDecision]:
        """Parse design decisions from response."""
        result = []
        for d in decisions:
            try:
                result.append(DesignDecision(
                    title=d.get("title", "Design Decision"),
                    description=d.get("description", ""),
                    rationale=d.get("rationale", ""),
                    alternatives_considered=d.get("alternatives_considered", []),
                    trade_offs=d.get("trade_offs", "")
                ))
            except Exception:
                pass
        return result

    def _parse_file_changes(self, changes: List[dict]) -> List[FileChange]:
        """Parse file changes from response."""
        result = []
        for c in changes:
            try:
                result.append(FileChange(
                    file_path=c.get("file_path", ""),
                    change_type=c.get("change_type", "modify"),
                    description=c.get("description", ""),
                    estimated_lines=c.get("estimated_lines", 0)
                ))
            except Exception:
                pass
        return result

    def _parse_new_files(self, files: List[dict]) -> List[NewFile]:
        """Parse new files from response."""
        result = []
        for f in files:
            try:
                result.append(NewFile(
                    file_path=f.get("file_path", ""),
                    purpose=f.get("purpose", ""),
                    template=f.get("template")
                ))
            except Exception:
                pass
        return result

    def _parse_api_changes(self, changes: List[dict]) -> List[APIChange]:
        """Parse API changes from response."""
        result = []
        for c in changes:
            try:
                result.append(APIChange(
                    endpoint=c.get("endpoint", ""),
                    method=c.get("method", "GET"),
                    change_type=c.get("change_type", "add"),
                    description=c.get("description", "")
                ))
            except Exception:
                pass
        return result

    def _create_default_proposal(self, title: str) -> ArchitectureProposal:
        """Create a default proposal when parsing fails."""
        from datetime import datetime, timezone

        return ArchitectureProposal(
            approach=f"Architecture proposal for: {title}",
            design_decisions=[
                DesignDecision(
                    title="Implementation Approach",
                    description="Detailed architecture analysis required",
                    rationale="Initial proposal - please review and refine",
                    alternatives_considered=[],
                    trade_offs="To be determined after detailed analysis"
                )
            ],
            file_changes=[],
            new_files=[],
            api_changes=[],
            database_changes=[],
            security_considerations=["Security review pending"],
            backward_compatible=True,
            migration_required=False,
            reviewed_at=datetime.now(timezone.utc),
            reviewer_agent_id=str(self.agent_type.value)
        )

    async def execute(
        self,
        task: str,
        context: AgentContext
    ) -> AgentResult:
        """Execute an architecture design task."""
        return await self.executor.run(self, task, context)

    async def stream(
        self,
        task: str,
        context: AgentContext
    ) -> AsyncGenerator[AgentStreamChunk, None]:
        """Stream execution of design task."""
        async for chunk in self.executor.stream(self, task, context):
            yield chunk


# Singleton instance
_architect_agent: Optional[EnhancementArchitectAgent] = None


def get_architect_agent() -> EnhancementArchitectAgent:
    """Get the global architect agent instance."""
    global _architect_agent
    if _architect_agent is None:
        _architect_agent = EnhancementArchitectAgent()
    return _architect_agent
