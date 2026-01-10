"""
Agent Executor
Implements the ReAct (Reasoning + Acting) loop for agent execution.
"""
from typing import Dict, List, Any, Optional, AsyncGenerator
import asyncio
import logging
import time
import json

from .types import (
    AgentContext, AgentResult, AgentMessage, ToolCall,
    ToolResult, MessageRole, ToolStatus, AgentStreamChunk,
    ToolDefinition
)
from .base import BaseAgent
from .registry import ToolRegistry, get_tool_registry
from .permissions import PermissionManager, get_permission_manager

logger = logging.getLogger(__name__)


class MaxStepsExceeded(Exception):
    """Raised when agent exceeds maximum steps"""
    pass


class DoomLoopDetected(Exception):
    """Raised when agent is stuck in a doom loop"""
    pass


class AgentExecutor:
    """
    Executes agent tasks using the ReAct loop.

    The ReAct loop:
    1. Think: Agent reasons about the task and decides what to do
    2. Act: Execute tool calls if any
    3. Observe: Process tool results
    4. Repeat until task is complete or max steps reached
    """

    DOOM_LOOP_THRESHOLD = 3  # Consecutive identical tool calls

    def __init__(
        self,
        tool_registry: Optional[ToolRegistry] = None,
        permission_manager: Optional[PermissionManager] = None,
        llm_adapter = None
    ):
        self.tool_registry = tool_registry or get_tool_registry()
        self.permission_manager = permission_manager or get_permission_manager()
        self._llm_adapter = llm_adapter

    @property
    def llm_adapter(self):
        """Lazy load LLM adapter"""
        if self._llm_adapter is None:
            # Try Ollama first (local LLM with tool calling support)
            try:
                from .adapters.ollama_adapter import get_ollama_adapter
                self._llm_adapter = get_ollama_adapter()
                logger.info("Using Ollama LLM adapter")
            except ImportError:
                # Fallback to LangChain adapter
                try:
                    from ..adapters.langchain.llm_adapter import get_langchain_llm
                    self._llm_adapter = get_langchain_llm()
                    logger.info("Using LangChain LLM adapter")
                except ImportError:
                    logger.warning("No LLM adapter available")
        return self._llm_adapter

    async def run(
        self,
        agent: BaseAgent,
        task: str,
        context: AgentContext
    ) -> AgentResult:
        """
        Execute a task using the ReAct loop.

        Args:
            agent: The agent to execute with
            task: The user's task or question
            context: Execution context

        Returns:
            AgentResult with answer and metadata
        """
        start_time = time.time()

        # Initialize messages with system prompt and user task
        messages: List[AgentMessage] = [
            AgentMessage(role=MessageRole.SYSTEM, content=agent.system_prompt),
            AgentMessage(role=MessageRole.USER, content=task)
        ]

        # Add conversation history
        for hist in context.conversation_history[-5:]:
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

        # Get available tools for this agent
        available_tools = self.tool_registry.get_tools_for_agent(agent.agent_type)
        tool_definitions = [tool.get_definition() for tool in available_tools]

        tool_calls_made: List[ToolCall] = []
        tool_results: List[ToolResult] = []
        recent_tool_calls: List[Dict] = []  # For doom loop detection

        step = 0
        final_answer = ""

        while step < context.max_steps:
            step += 1
            logger.debug(f"Step {step}/{context.max_steps}")

            # Think: Get LLM response
            response = await self._call_llm(messages, tool_definitions)

            if response is None:
                final_answer = "I encountered an error while processing your request."
                break

            # Add assistant message
            messages.append(response)

            # Check if we have tool calls
            if response.tool_calls:
                # Doom loop detection
                for tool_call in response.tool_calls:
                    call_signature = {
                        "tool": tool_call.tool_name,
                        "args": json.dumps(tool_call.arguments, sort_keys=True)
                    }
                    recent_tool_calls.append(call_signature)

                    # Check for repeated calls
                    if len(recent_tool_calls) >= self.DOOM_LOOP_THRESHOLD:
                        last_n = recent_tool_calls[-self.DOOM_LOOP_THRESHOLD:]
                        if all(c == last_n[0] for c in last_n):
                            logger.warning(f"Doom loop detected: {tool_call.tool_name}")
                            # Break the loop
                            final_answer = (
                                f"I noticed I was repeating the same action. "
                                f"Based on the information gathered: {response.content or 'Unable to provide answer.'}"
                            )
                            break

                # Act: Execute tool calls
                for tool_call in response.tool_calls:
                    tool_calls_made.append(tool_call)

                    # Check permissions
                    if not self.permission_manager.check_permission(
                        tool_call.tool_name,
                        agent.agent_type,
                        context.user_id
                    ):
                        result = ToolResult(
                            success=False,
                            output="",
                            error=f"Permission denied for tool: {tool_call.tool_name}",
                            metadata=None
                        )
                    else:
                        # Execute tool
                        result = await self._execute_tool(tool_call, context)

                    tool_results.append(result)

                    # Add tool result message
                    messages.append(AgentMessage(
                        role=MessageRole.TOOL,
                        content=result["output"] if result["success"] else f"Error: {result['error']}",
                        tool_call_id=tool_call.call_id,
                        name=tool_call.tool_name
                    ))

                # Check if we broke out due to doom loop
                if final_answer:
                    break
            else:
                # No tool calls - agent has finished reasoning
                final_answer = response.content or "I couldn't generate a response."
                break

        execution_time = time.time() - start_time

        # Extract sources from tool results
        sources = self._extract_sources(tool_results)

        return AgentResult(
            answer=final_answer,
            agent_type=agent.agent_type,
            steps=step,
            tool_calls=tool_calls_made,
            tool_results=tool_results,
            sources=sources,
            execution_time=execution_time,
            success=True,
            metadata={
                "max_steps": context.max_steps,
                "tools_used": list(set(tc.tool_name for tc in tool_calls_made))
            }
        )

    async def stream(
        self,
        agent: BaseAgent,
        task: str,
        context: AgentContext
    ) -> AsyncGenerator[AgentStreamChunk, None]:
        """
        Stream execution of a task.

        Yields events as the agent thinks and acts.
        """
        start_time = time.time()

        # Initialize messages
        messages: List[AgentMessage] = [
            AgentMessage(role=MessageRole.SYSTEM, content=agent.system_prompt),
            AgentMessage(role=MessageRole.USER, content=task)
        ]

        available_tools = self.tool_registry.get_tools_for_agent(agent.agent_type)
        tool_definitions = [tool.get_definition() for tool in available_tools]

        sources = []
        step = 0

        yield AgentStreamChunk(chunk_type="thinking", content="Analyzing your request...")

        while step < context.max_steps:
            step += 1

            # Think
            response = await self._call_llm(messages, tool_definitions)

            if response is None:
                yield AgentStreamChunk(chunk_type="error", content="LLM call failed")
                return

            messages.append(response)

            if response.tool_calls:
                # Stream tool execution
                for tool_call in response.tool_calls:
                    yield AgentStreamChunk(
                        chunk_type="tool_call",
                        tool_name=tool_call.tool_name,
                        tool_input=tool_call.arguments
                    )

                    result = await self._execute_tool(tool_call, context)

                    yield AgentStreamChunk(
                        chunk_type="tool_result",
                        tool_name=tool_call.tool_name,
                        tool_output=result["output"][:500] if result["success"] else result["error"]
                    )

                    messages.append(AgentMessage(
                        role=MessageRole.TOOL,
                        content=result["output"] if result["success"] else f"Error: {result['error']}",
                        tool_call_id=tool_call.call_id,
                        name=tool_call.tool_name
                    ))

                    # Collect sources
                    if result.get("metadata") and "sources" in result["metadata"]:
                        sources.extend(result["metadata"]["sources"])
            else:
                # Stream final answer
                answer = response.content or ""
                chunk_size = 50

                for i in range(0, len(answer), chunk_size):
                    chunk = answer[i:i + chunk_size]
                    yield AgentStreamChunk(chunk_type="text", content=chunk)
                    await asyncio.sleep(0.02)

                break

        # Yield sources and done
        if sources:
            yield AgentStreamChunk(chunk_type="sources", sources=sources[:10])

        yield AgentStreamChunk(
            chunk_type="done",
            metadata={
                "steps": step,
                "execution_time": time.time() - start_time
            }
        )

    async def _call_llm(
        self,
        messages: List[AgentMessage],
        tools: List[ToolDefinition]
    ) -> Optional[AgentMessage]:
        """Call the LLM with messages and tools"""
        try:
            if self.llm_adapter is None:
                # Mock response for testing
                return AgentMessage(
                    role=MessageRole.ASSISTANT,
                    content="LLM adapter not configured. This is a mock response."
                )

            # Format messages for LLM
            formatted_messages = []
            for msg in messages:
                formatted = {"role": msg.role.value, "content": msg.content}
                if msg.tool_calls:
                    formatted["tool_calls"] = [
                        {
                            "id": tc.call_id,
                            "type": "function",
                            "function": {
                                "name": tc.tool_name,
                                "arguments": json.dumps(tc.arguments)
                            }
                        }
                        for tc in msg.tool_calls
                    ]
                if msg.tool_call_id:
                    formatted["tool_call_id"] = msg.tool_call_id
                if msg.name:
                    formatted["name"] = msg.name
                formatted_messages.append(formatted)

            # Format tools for LLM
            formatted_tools = [
                {
                    "type": "function",
                    "function": {
                        "name": tool.name,
                        "description": tool.description,
                        "parameters": tool.parameters
                    }
                }
                for tool in tools
            ]

            # Call LLM
            response = await self.llm_adapter.generate(
                messages=formatted_messages,
                tools=formatted_tools if formatted_tools else None
            )

            # Parse response
            content = response.get("content", "")
            tool_calls = []

            if "tool_calls" in response:
                for tc in response["tool_calls"]:
                    func = tc.get("function", {})
                    args = func.get("arguments", "{}")
                    if isinstance(args, str):
                        args = json.loads(args)

                    tool_calls.append(ToolCall(
                        tool_name=func.get("name", ""),
                        arguments=args,
                        call_id=tc.get("id", "")
                    ))

            return AgentMessage(
                role=MessageRole.ASSISTANT,
                content=content,
                tool_calls=tool_calls if tool_calls else None
            )

        except Exception as e:
            logger.error(f"LLM call failed: {e}")
            return None

    async def _execute_tool(
        self,
        tool_call: ToolCall,
        context: AgentContext
    ) -> ToolResult:
        """Execute a tool call"""
        tool = self.tool_registry.get(tool_call.tool_name)

        if tool is None:
            return ToolResult(
                success=False,
                output="",
                error=f"Unknown tool: {tool_call.tool_name}",
                metadata=None
            )

        # Validate parameters
        is_valid, error = tool.validate_params(tool_call.arguments)
        if not is_valid:
            return ToolResult(
                success=False,
                output="",
                error=f"Invalid parameters: {error}",
                metadata=None
            )

        try:
            result = await tool.execute(context, **tool_call.arguments)
            return result
        except Exception as e:
            logger.error(f"Tool execution failed: {e}")
            return ToolResult(
                success=False,
                output="",
                error=f"Tool execution failed: {str(e)}",
                metadata=None
            )

    def _extract_sources(self, tool_results: List[ToolResult]) -> List[Dict[str, Any]]:
        """Extract sources from tool results"""
        sources = []
        for result in tool_results:
            if result["success"] and result.get("metadata"):
                if "sources" in result["metadata"]:
                    sources.extend(result["metadata"]["sources"])

            # Also try to parse output for sources
            try:
                output = result.get("output", "")
                if isinstance(output, str) and output.startswith("{"):
                    data = json.loads(output)
                    if "results" in data:
                        for r in data["results"]:
                            if "source" in r:
                                sources.append({
                                    "content": r.get("content", "")[:200],
                                    "source": r["source"],
                                    "score": r.get("score", 0)
                                })
            except (json.JSONDecodeError, TypeError):
                pass

        # Deduplicate sources
        seen = set()
        unique_sources = []
        for s in sources:
            key = s.get("source", "")
            if key and key not in seen:
                seen.add(key)
                unique_sources.append(s)

        return unique_sources[:10]  # Limit to 10 sources


# Convenience function
def get_executor() -> AgentExecutor:
    """Get a configured executor instance"""
    return AgentExecutor()
