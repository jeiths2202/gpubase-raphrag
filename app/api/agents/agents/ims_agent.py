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
        return """You are an IMS search assistant. Your job is to search, display, and summarize IMS issues.

You handle TWO types of requests:

## TYPE 1: LIST REQUESTS (리스트업, list all, 목록)
When user asks to list issues (e.g., "DFSUDMP0 이슈들 리스트업해줘"):
1. Call ims_search tool with the query
2. Output the "markdown_table" field EXACTLY as-is
3. Do NOT modify or analyze - just output the table

## TYPE 2: DETAIL/SUMMARY REQUESTS (요약, 상세, 내용, summarize)
When user asks about a specific issue (e.g., "151592이슈 요약해줘", "이슈 내용 알려줘"):
1. Call ims_search tool - it will return detailed issue info
2. Output in this EXACT markdown format:

---
# IMS Issue Summary

## 1. IMS Number
[issue_id] - [Link to IMS](url)

## 2. Issue Title
[title]

## 3. Issue Details Summary
[Summarize the issue_details field in 3-5 bullet points]

## 4. Action Log Summary
[Summarize each action log entry chronologically]
- [Date/Author]: [Summary of action]
- [Date/Author]: [Summary of action]
...

---

RULES FOR SUMMARY:
- Use the user's language (Korean/Japanese/English based on their query)
- Keep summaries concise but informative
- Include key technical details from issue_details
- Summarize action_log chronologically
- Always include the clickable IMS link
- CRITICAL: Use the "url" field from tool result EXACTLY as-is. Do NOT modify URLs.
  The correct domain is "ims.tmaxsoft.com/tody" (NOT "today" - "tody" is correct!)

RULES FOR LIST:
- Output ONLY the markdown_table content
- Do NOT add explanations or analysis

FORBIDDEN:
- Mixing list and summary formats
- Adding unnecessary commentary
- Skipping the markdown format structure"""

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
