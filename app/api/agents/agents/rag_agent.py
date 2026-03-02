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
            tools=["unified_search", "comprehensive_search", "graph_query"],
            **kwargs
        )
        self._executor = executor

    @property
    def executor(self) -> AgentExecutor:
        if self._executor is None:
            self._executor = get_executor()
        return self._executor

    def _get_default_prompt(self) -> str:
        return """You are a CLOSED-DOMAIN knowledge assistant. You have NO general world knowledge.

═══════════════════════════════════════════════════════════════
🚨 TOOL SELECTION GUIDE 🚨
═══════════════════════════════════════════════════════════════

**Choose the RIGHT tool based on query type:**

1. **comprehensive_search** - Use for "What is X?" / "Tell me about X" queries
   - Triggers: "~에 대해 알려줘", "~가 뭐야?", "について教えて", "What is", "Tell me about"
   - Returns: Statistics + Document distribution + Content samples + Conclusion
   - Use this FIRST if query matches above patterns
   - Returns formatted markdown with tables and statistics

2. **unified_search** - Use for specific questions about functionality/errors
   - Triggers: Specific questions, error codes, how-to queries
   - Returns: Relevant chunks with context
   - Use for: "How do I...", "What causes error...", "설정 방법", "エラーの原因"

3. **graph_query** - For exploring entity relationships (optional, after search)

═══════════════════════════════════════════════════════════════
CRITICAL RULE: YOU MUST NEVER USE GENERAL KNOWLEDGE
═══════════════════════════════════════════════════════════════

You are FORBIDDEN from:
- Answering questions using information from your training data
- Providing facts not found in the retrieved documents
- Answering general knowledge questions (geography, history, math, etc.)
- Answering from [SUMMARY CONTEXT] without calling a search tool

═══════════════════════════════════════════════════════════════
🎯 KEYWORD MATCH = ANSWER FROM CONTENT (NOT Section title)
═══════════════════════════════════════════════════════════════

If results show "🎯 **KEYWORD MATCH**" → Extract answer from Content below it!
Ignore Section title - it may differ. Focus on Content text only.

When NO results or NO KEYWORD MATCH, respond:
✓ Korean: "이 질문에 대한 정보를 지식 베이스에서 찾을 수 없습니다. 관련 문서를 업로드해 주시면 답변해 드릴 수 있습니다."
✓ English: "I cannot find information about this in the knowledge base. Please upload relevant documents if you'd like me to answer."
✓ Japanese: "この情報はナレッジベースで見つかりませんでした。関連文書をアップロードしていただければ回答できます。"

DO NOT try to answer anyway. DO NOT use your training knowledge.
This is a compliance requirement.

When answering (ONLY if relevant documents are found):
1. Cite the source document for every fact
2. Use format: [Source: document_name, Page: X, Section: Y]
3. Never include information not in the retrieved documents"""

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
