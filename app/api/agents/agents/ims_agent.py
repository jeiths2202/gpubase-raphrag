"""
IMS Agent
Specialized agent for searching and analyzing IMS issues.
"""
from typing import List, Optional, AsyncGenerator
import logging

from ..base import BaseAgent
from ..types import (
    AgentType, AgentContext, AgentResult, AgentStreamChunk
)
from ..executor import AgentExecutor, get_executor

logger = logging.getLogger(__name__)


class IMSAgent(BaseAgent):
    """
    Agent specialized for IMS (Issue Management System) queries.
    Searches issues, analyzes patterns, and finds related problems.
    """

    def __init__(
        self,
        executor: Optional[AgentExecutor] = None,
        **kwargs
    ):
        super().__init__(
            name="IMS Agent",
            agent_type=AgentType.IMS,
            description="Issue Management System search and analysis agent",
            tools=["ims_search", "web_fetch", "vector_search"],
            **kwargs
        )
        self._executor = executor

    @property
    def executor(self) -> AgentExecutor:
        if self._executor is None:
            self._executor = get_executor()
        return self._executor

    def _get_default_prompt(self) -> str:
        return """You are an expert at searching and analyzing issues in the Issue Management System (IMS).

Your capabilities:
1. **IMS Search**: Search for bugs, feature requests, and technical issues
2. **Web Fetch**: Retrieve additional information from external sources
3. **Vector Search**: Find related knowledge base content

Guidelines:
- Search IMS with relevant keywords and filters
- Identify patterns across similar issues
- Find related issues that might provide solutions
- Summarize issue status and progress
- Suggest workarounds or solutions based on similar resolved issues

When analyzing issues:
1. Search for the specific issue or related keywords
2. Check issue status, priority, and assigned teams
3. Look for related issues that might have solutions
4. Provide a summary with actionable insights

Response format:
- Issue ID and title
- Current status and priority
- Key details and description
- Related issues and potential solutions
- Recommendations for next steps"""

    async def execute(
        self,
        task: str,
        context: AgentContext
    ) -> AgentResult:
        """Execute an IMS search task"""
        return await self.executor.run(self, task, context)

    async def stream(
        self,
        task: str,
        context: AgentContext
    ) -> AsyncGenerator[AgentStreamChunk, None]:
        """Stream execution of IMS search"""
        async for chunk in self.executor.stream(self, task, context):
            yield chunk
