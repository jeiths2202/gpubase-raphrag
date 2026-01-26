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
        """Fallback prompt if external file not found."""
        return """You are an IMS search assistant. Search, display, and summarize IMS issues.
Use EXACT keywords from user queries. Output markdown tables for list requests.
Provide structured summaries for detail requests."""

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
