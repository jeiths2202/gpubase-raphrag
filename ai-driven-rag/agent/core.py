"""Core AI Agent with tool calling loop."""
import json
from dataclasses import dataclass, field
from typing import AsyncIterator

from .llm import LLMClient, ToolCall
from .prompts import SYSTEM_PROMPT
from tools import ToolRegistry, VectorSearchTool, GraphQueryTool, DocumentReadTool
from config import config


@dataclass
class AgentResponse:
    """Final response from the agent."""
    answer: str
    tool_calls_made: list[dict] = field(default_factory=list)
    sources: list[str] = field(default_factory=list)


class AIAgent:
    """AI Agent with autonomous tool calling."""

    def __init__(
        self,
        llm_client: LLMClient | None = None,
        tool_registry: ToolRegistry | None = None,
    ):
        self.llm = llm_client or LLMClient()
        self.tools = tool_registry or self._create_default_tools()
        self.max_iterations = config.max_tool_calls

    def _create_default_tools(self) -> ToolRegistry:
        """Create default tool registry with all tools."""
        registry = ToolRegistry()
        registry.register(VectorSearchTool())
        registry.register(GraphQueryTool())
        registry.register(DocumentReadTool())
        return registry

    async def run(self, query: str, conversation_history: list[dict] | None = None) -> AgentResponse:
        """Run the agent with a user query."""
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
        ]

        # Add conversation history if provided
        if conversation_history:
            messages.extend(conversation_history)

        # Add current query
        messages.append({"role": "user", "content": query})

        tool_calls_made = []
        sources = set()

        # Tool calling loop
        for iteration in range(self.max_iterations):
            response = await self.llm.chat(
                messages=messages,
                tools=self.tools.to_openai_tools(),
            )

            # If no tool calls, we have the final answer
            if not response.tool_calls:
                return AgentResponse(
                    answer=response.content or "I couldn't generate a response.",
                    tool_calls_made=tool_calls_made,
                    sources=list(sources),
                )

            # Process tool calls
            messages.append({
                "role": "assistant",
                "content": response.content,
                "tool_calls": [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.name,
                            "arguments": json.dumps(tc.arguments),
                        },
                    }
                    for tc in response.tool_calls
                ],
            })

            # Execute each tool call
            for tool_call in response.tool_calls:
                result = await self.tools.execute(tool_call.name, **tool_call.arguments)

                # Track tool calls and sources
                tool_calls_made.append({
                    "tool": tool_call.name,
                    "arguments": tool_call.arguments,
                    "result_summary": self._summarize_result(result),
                })

                # Extract sources from results
                if isinstance(result, dict):
                    if "results" in result:
                        for r in result["results"]:
                            if doc_title := r.get("doc_title"):
                                sources.add(doc_title)
                    if doc_id := result.get("doc_id"):
                        sources.add(doc_id)

                # Add tool result to messages
                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": json.dumps(result, ensure_ascii=False, default=str),
                })

        # Max iterations reached
        return AgentResponse(
            answer="I reached the maximum number of tool calls. Here's what I found so far based on my searches.",
            tool_calls_made=tool_calls_made,
            sources=list(sources),
        )

    async def run_stream(self, query: str, conversation_history: list[dict] | None = None) -> AsyncIterator[str]:
        """Run the agent with streaming response."""
        # First, run the agent to get tool results
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
        ]

        if conversation_history:
            messages.extend(conversation_history)

        messages.append({"role": "user", "content": query})

        # Tool calling loop (non-streaming for tool calls)
        for iteration in range(self.max_iterations):
            response = await self.llm.chat(
                messages=messages,
                tools=self.tools.to_openai_tools(),
            )

            if not response.tool_calls:
                # Stream the final response
                async for chunk in self.llm.chat_stream(messages=messages):
                    yield chunk
                return

            # Process tool calls
            messages.append({
                "role": "assistant",
                "content": response.content,
                "tool_calls": [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.name,
                            "arguments": json.dumps(tc.arguments),
                        },
                    }
                    for tc in response.tool_calls
                ],
            })

            # Execute tools and add results
            for tool_call in response.tool_calls:
                yield f"\n[Tool: {tool_call.name}({tool_call.arguments})]\n"

                result = await self.tools.execute(tool_call.name, **tool_call.arguments)

                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": json.dumps(result, ensure_ascii=False, default=str),
                })

    def _summarize_result(self, result: dict) -> str:
        """Create a brief summary of tool result."""
        if "error" in result:
            return f"Error: {result['error']}"
        if "results" in result:
            return f"Found {len(result['results'])} results"
        if "content" in result:
            return f"Retrieved document ({len(result['content'])} chars)"
        if "related_nodes" in result:
            return f"Found {len(result['related_nodes'])} related nodes"
        return "Completed"

    async def close(self):
        """Clean up resources."""
        for tool in self.tools.get_all():
            if hasattr(tool, "close"):
                await tool.close()
