"""
Code Agent
Specialized agent for code generation and analysis.
"""
from typing import List, Optional, AsyncGenerator
import logging

from ..base import BaseAgent
from ..types import (
    AgentType, AgentContext, AgentResult, AgentStreamChunk
)
from ..executor import AgentExecutor, get_executor
from ...core.config import get_api_settings

logger = logging.getLogger(__name__)

_settings = get_api_settings()


class CodeAgent(BaseAgent):
    """
    Agent specialized for code-related tasks.
    Generates, reviews, and explains code.
    """

    def __init__(
        self,
        executor: Optional[AgentExecutor] = None,
        **kwargs
    ):
        super().__init__(
            name="Code Agent",
            agent_type=AgentType.CODE,
            description="Code generation and analysis agent using Mistral Code LLM",
            tools=["document_read", "bash", "vector_search"],
            model_id=_settings.CODE_AGENT_MODEL,  # Load from environment
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
        return """You are an expert software developer and code analyst.
Write clean, efficient code. Review for bugs and security issues.
Supported: Python, JavaScript/TypeScript, Java, Go, Rust, SQL, Shell."""

    async def execute(
        self,
        task: str,
        context: AgentContext
    ) -> AgentResult:
        """Execute a code-related task"""
        return await self.executor.run(self, task, context)

    async def stream(
        self,
        task: str,
        context: AgentContext
    ) -> AsyncGenerator[AgentStreamChunk, None]:
        """Stream execution of code task"""
        async for chunk in self.executor.stream(self, task, context):
            yield chunk
