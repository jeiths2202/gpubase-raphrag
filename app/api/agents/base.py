"""
Base Agent Abstract Class
Defines the interface for all specialized agents.
"""
from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional, AsyncGenerator
import asyncio
import logging
from pathlib import Path

from .types import (
    AgentType, AgentContext, AgentResult, AgentMessage,
    ToolCall, ToolResult, ToolDefinition, MessageRole,
    AgentStreamChunk
)

logger = logging.getLogger(__name__)


class BaseAgent(ABC):
    """
    Abstract base class for all agents.

    Each agent has:
    - A specific type (RAG, IMS, Vision, etc.)
    - A set of tools it can use
    - A system prompt defining its behavior
    - Methods for thinking (LLM reasoning) and acting (tool execution)
    """

    def __init__(
        self,
        name: str,
        agent_type: AgentType,
        description: str,
        tools: Optional[List[str]] = None,
        system_prompt: Optional[str] = None,
        model_id: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 4096
    ):
        self.name = name
        self.agent_type = agent_type
        self.description = description
        self.tools = tools or []
        self._system_prompt = system_prompt
        self.model_id = model_id
        self.temperature = temperature
        self.max_tokens = max_tokens

        # Load system prompt from file if not provided
        if self._system_prompt is None:
            self._system_prompt = self._load_prompt_file()

    @property
    def system_prompt(self) -> str:
        """Get the system prompt for this agent"""
        if self._system_prompt:
            return self._system_prompt
        return self._get_default_prompt()

    def _load_prompt_file(self) -> Optional[str]:
        """Load system prompt from prompts directory"""
        prompt_dir = Path(__file__).parent / "prompts"
        prompt_file = prompt_dir / f"{self.agent_type.value}_agent.txt"

        if prompt_file.exists():
            return prompt_file.read_text(encoding="utf-8")
        return None

    def _get_default_prompt(self) -> str:
        """Get default system prompt"""
        return f"""You are {self.name}, a specialized AI agent.

Your role: {self.description}

Available tools: {', '.join(self.tools) if self.tools else 'None'}

Instructions:
1. Analyze the user's request carefully
2. Use available tools when needed to gather information
3. Provide accurate, helpful responses based on the information gathered
4. Always cite sources when applicable
5. If you cannot answer, explain why and suggest alternatives

Respond in the user's preferred language when specified."""

    @abstractmethod
    async def execute(
        self,
        task: str,
        context: AgentContext
    ) -> AgentResult:
        """
        Execute a task and return the result.

        Args:
            task: The user's task or question
            context: Execution context with session info

        Returns:
            AgentResult with answer and metadata
        """
        pass

    @abstractmethod
    async def stream(
        self,
        task: str,
        context: AgentContext
    ) -> AsyncGenerator[AgentStreamChunk, None]:
        """
        Stream execution of a task.

        Args:
            task: The user's task or question
            context: Execution context with session info

        Yields:
            AgentStreamChunk with incremental results
        """
        pass

    async def think(
        self,
        messages: List[AgentMessage],
        tools: Optional[List[ToolDefinition]] = None
    ) -> AgentMessage:
        """
        Generate a response using the LLM.

        Args:
            messages: Conversation history
            tools: Available tools for function calling

        Returns:
            AgentMessage with response and optional tool calls
        """
        # This will be implemented by subclasses or use the LLM adapter
        raise NotImplementedError("Subclass must implement think()")

    async def act(
        self,
        tool_call: ToolCall,
        context: AgentContext
    ) -> ToolResult:
        """
        Execute a tool call.

        Args:
            tool_call: The tool call to execute
            context: Execution context

        Returns:
            ToolResult with output or error
        """
        # This will be implemented by the executor using the tool registry
        raise NotImplementedError("Tool execution handled by AgentExecutor")

    def get_tool_definitions(self) -> List[ToolDefinition]:
        """Get tool definitions for LLM function calling"""
        # This will be populated by the registry
        return []

    def format_messages_for_llm(
        self,
        messages: List[AgentMessage]
    ) -> List[Dict[str, Any]]:
        """Format messages for LLM API call"""
        formatted = []
        for msg in messages:
            formatted_msg = {
                "role": msg.role.value,
                "content": msg.content
            }
            if msg.tool_calls:
                formatted_msg["tool_calls"] = [
                    {
                        "id": tc.call_id,
                        "type": "function",
                        "function": {
                            "name": tc.tool_name,
                            "arguments": tc.arguments
                        }
                    }
                    for tc in msg.tool_calls
                ]
            if msg.tool_call_id:
                formatted_msg["tool_call_id"] = msg.tool_call_id
            if msg.name:
                formatted_msg["name"] = msg.name
            formatted.append(formatted_msg)
        return formatted

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(name='{self.name}', type={self.agent_type.value})"


class SimpleAgent(BaseAgent):
    """
    Simple agent implementation that doesn't use tools.
    Useful for basic question answering or as a fallback.
    """

    def __init__(
        self,
        name: str = "SimpleAgent",
        agent_type: AgentType = AgentType.RAG,
        description: str = "A simple agent for basic tasks",
        llm_adapter = None
    ):
        super().__init__(name=name, agent_type=agent_type, description=description)
        self.llm_adapter = llm_adapter

    async def execute(
        self,
        task: str,
        context: AgentContext
    ) -> AgentResult:
        """Execute without tools - direct LLM call"""
        import time
        start_time = time.time()

        messages = [
            AgentMessage(role=MessageRole.SYSTEM, content=self.system_prompt),
            AgentMessage(role=MessageRole.USER, content=task)
        ]

        # Add conversation history if available
        for hist in context.conversation_history[-5:]:  # Last 5 turns
            if "question" in hist:
                messages.insert(-1, AgentMessage(
                    role=MessageRole.USER,
                    content=hist["question"]
                ))
            if "answer" in hist:
                messages.insert(-1, AgentMessage(
                    role=MessageRole.ASSISTANT,
                    content=hist["answer"]
                ))

        # Generate response
        if self.llm_adapter:
            response = await self.llm_adapter.generate(
                self.format_messages_for_llm(messages)
            )
            answer = response.get("content", "I couldn't generate a response.")
        else:
            answer = "LLM adapter not configured."

        execution_time = time.time() - start_time

        return AgentResult(
            answer=answer,
            agent_type=self.agent_type,
            steps=1,
            execution_time=execution_time
        )

    async def stream(
        self,
        task: str,
        context: AgentContext
    ) -> AsyncGenerator[AgentStreamChunk, None]:
        """Stream execution"""
        # Start thinking
        yield AgentStreamChunk(chunk_type="thinking", content="Processing...")

        # Execute and yield result
        result = await self.execute(task, context)

        # Stream answer in chunks
        chunk_size = 50
        for i in range(0, len(result.answer), chunk_size):
            chunk = result.answer[i:i + chunk_size]
            yield AgentStreamChunk(chunk_type="text", content=chunk)
            await asyncio.sleep(0.02)

        # Done
        yield AgentStreamChunk(
            chunk_type="done",
            metadata={"execution_time": result.execution_time}
        )
