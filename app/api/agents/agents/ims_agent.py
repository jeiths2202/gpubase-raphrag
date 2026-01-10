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
        return """You are an IMS (Issue Management System) search assistant. Your job is to search for issues using the available tools.

IMPORTANT: You MUST use the ims_search tool to find issues. Do NOT answer without searching first.

Available tools:
- ims_search: Search IMS for issues by keyword. ALWAYS use this tool when asked to find issues.
- web_fetch: Fetch additional information from URLs
- vector_search: Search knowledge base for related content

Instructions:
1. When asked to find issues, IMMEDIATELY call the ims_search tool with the search query
2. Extract keywords from the user's question (e.g., "hidbinit" from "find hidbinit issues")
3. After getting results, summarize what you found

Example:
User: "Find issues about authentication"
Action: Call ims_search with query="authentication"

User: "IMS에서 hidbinit 관련 이슈를 찾아"
Action: Call ims_search with query="hidbinit"

NEVER respond without using ims_search first when asked to find/search issues."""

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
