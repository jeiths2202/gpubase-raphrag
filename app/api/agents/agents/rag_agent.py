"""
RAG Agent
Specialized agent for knowledge base queries using Hybrid RAG.
"""
from typing import List, Optional, AsyncGenerator
import logging

from ..base import BaseAgent
from ..types import (
    AgentType, AgentContext, AgentResult, AgentMessage,
    MessageRole, AgentStreamChunk
)
from ..executor import AgentExecutor, get_executor

logger = logging.getLogger(__name__)


class RAGAgent(BaseAgent):
    """
    Agent specialized for answering questions using the knowledge base.
    Uses vector search and graph queries to find relevant information.
    """

    def __init__(
        self,
        executor: Optional[AgentExecutor] = None,
        **kwargs
    ):
        super().__init__(
            name="RAG Agent",
            agent_type=AgentType.RAG,
            description="Knowledge base query agent using Hybrid RAG (vector + graph retrieval)",
            tools=["vector_search", "graph_query", "document_read"],
            **kwargs
        )
        self._executor = executor

    @property
    def executor(self) -> AgentExecutor:
        if self._executor is None:
            self._executor = get_executor()
        return self._executor

    def _get_default_prompt(self) -> str:
        return """You are an intelligent knowledge assistant powered by a Hybrid RAG system.

Your capabilities:
1. **Vector Search**: Find semantically similar content in the knowledge base
2. **Graph Query**: Explore relationships between concepts and entities
3. **Document Reading**: Access uploaded documents for detailed information

Guidelines:
- Always search the knowledge base before answering questions
- Use vector_search for general queries and finding relevant documents
- Use graph_query when the question involves relationships or connections
- Cite sources when providing information
- If information is not found, clearly state that
- Respond in the user's preferred language

When answering:
1. First, search for relevant information using appropriate tools
2. Analyze the results to find the best answer
3. Synthesize a clear, accurate response
4. Include source references

If multiple sources conflict, note the discrepancy and explain different perspectives."""

    async def execute(
        self,
        task: str,
        context: AgentContext
    ) -> AgentResult:
        """Execute a knowledge query task"""
        return await self.executor.run(self, task, context)

    async def stream(
        self,
        task: str,
        context: AgentContext
    ) -> AsyncGenerator[AgentStreamChunk, None]:
        """Stream execution of knowledge query"""
        async for chunk in self.executor.stream(self, task, context):
            yield chunk
