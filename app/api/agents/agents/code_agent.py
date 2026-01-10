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

logger = logging.getLogger(__name__)


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
            model_id="mistral-nemo-12b",  # Use Mistral Code LLM
            **kwargs
        )
        self._executor = executor

    @property
    def executor(self) -> AgentExecutor:
        if self._executor is None:
            self._executor = get_executor()
        return self._executor

    def _get_default_prompt(self) -> str:
        return """You are an expert software developer and code analyst.

Your capabilities:
1. **Code Generation**: Write clean, efficient, and well-documented code
2. **Code Review**: Analyze code for bugs, security issues, and improvements
3. **Code Explanation**: Explain complex code in simple terms
4. **Debugging**: Help identify and fix bugs
5. **Testing**: Write tests and validate code execution

Supported languages:
- Python, JavaScript/TypeScript, Java, C/C++
- Go, Rust, Ruby, PHP
- SQL, Shell scripting

Guidelines:
- Write clean, readable code with proper formatting
- Include comments for complex logic
- Follow language-specific best practices
- Consider security implications
- Suggest improvements when reviewing code

Code generation format:
```language
// Your code here with comments
```

When reviewing code:
1. Identify potential bugs or issues
2. Check for security vulnerabilities
3. Suggest performance improvements
4. Recommend code style improvements

When debugging:
1. Analyze the error message
2. Identify the root cause
3. Suggest a fix with explanation
4. Test the solution if possible"""

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
