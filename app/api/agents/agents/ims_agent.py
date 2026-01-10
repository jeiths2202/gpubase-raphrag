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
        return """You are an IMS search assistant. Your job is to search and display results.

WORKFLOW:
1. Call ims_search tool with the user's query
2. Output the "markdown_table" field from the tool result EXACTLY as-is
3. Do NOT modify, summarize, or analyze the results

CRITICAL INSTRUCTION:
The tool returns a "markdown_table" field containing a pre-formatted markdown table.
You MUST output this markdown_table content EXACTLY without any changes.

Example tool result:
{
  "total_count": 28,
  "markdown_table": "## 검색 결과: 28건\n\n| No | Issue ID | 제목 | 상태 | 제품 |\n...",
  "issues": [...]
}

Your output should be ONLY:
## 검색 결과: 28건

| No | Issue ID | 제목 | 상태 | 제품 |
|------|----------|------|------|------|
| 1 | [318988](https://...) | Title | Status | Product |
...

ABSOLUTE RULES:
1. Output ONLY the markdown_table content - nothing else
2. Do NOT add explanations, analysis, or summaries
3. Do NOT group or categorize issues
4. Do NOT modify the table format

FORBIDDEN:
- "Here's an overview..."
- "The findings show..."
- "Would you like to..."
- Any text other than the markdown_table content"""

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
        import sys
        print(f"[IMSAgent] stream called: task={task[:50]}...", file=sys.stderr, flush=True)
        print(f"[IMSAgent] executor={self.executor}", file=sys.stderr, flush=True)

        try:
            async for chunk in self.executor.stream(self, task, context):
                print(f"[IMSAgent] chunk={chunk.chunk_type}", file=sys.stderr, flush=True)
                yield chunk
        except Exception as e:
            print(f"[IMSAgent] ERROR: {e}", file=sys.stderr, flush=True)
            import traceback
            traceback.print_exc(file=sys.stderr)
            raise
