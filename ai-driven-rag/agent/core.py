"""Core AI Agent with tool calling loop."""
import json
from dataclasses import dataclass, field
from typing import AsyncIterator

from .llm import LLMClient, ToolCall
from .prompts import SYSTEM_PROMPT
from tools import ToolRegistry, VectorSearchTool, GraphQueryTool, DocumentReadTool, KeywordSearchTool, WebSearchTool, RerankTool, IMSSearchTool, IMSDetailTool, IMSLoginTool, IMSLogoutTool
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
        registry.register(KeywordSearchTool())
        registry.register(WebSearchTool())
        registry.register(IMSSearchTool())
        registry.register(IMSDetailTool())
        registry.register(IMSLoginTool())
        registry.register(IMSLogoutTool())
        registry.register(GraphQueryTool())
        registry.register(DocumentReadTool())
        registry.register(RerankTool())
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

            # If no tool calls, check for tool_call in text (Qwen fallback)
            if not response.tool_calls:
                # Check if there's a tool_call embedded in the text
                text_tool_call, clean_content = self._extract_tool_call_from_text(
                    response.content or ""
                )

                if text_tool_call:
                    # Execute the tool call found in text
                    tool_name = text_tool_call["name"]
                    tool_args = text_tool_call["arguments"]

                    result = await self.tools.execute(tool_name, **tool_args)

                    tool_calls_made.append({
                        "tool": tool_name,
                        "arguments": tool_args,
                        "result_summary": self._summarize_result(result),
                    })

                    # Extract sources from result
                    if isinstance(result, dict) and "results" in result:
                        for r in result["results"]:
                            source_name = r.get("title") or r.get("doc_title") or r.get("doc_id")
                            if source_name:
                                sources.add(source_name)

                    # Add result to messages and continue loop
                    messages.append({"role": "assistant", "content": clean_content})
                    messages.append({
                        "role": "user",
                        "content": f"Tool {tool_name} result:\n{json.dumps(result, ensure_ascii=False, default=str)[:3000]}\n\nBased on these results, please provide the final answer."
                    })
                    continue

                # No tool calls - return final answer
                answer = self._clean_response(response.content or "I couldn't generate a response.")
                return AgentResponse(
                    answer=answer,
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
                            # Try multiple fields for source name
                            source_name = (
                                r.get("doc_title") or
                                r.get("title") or
                                r.get("url") or
                                r.get("doc_id")
                            )
                            if source_name:
                                sources.add(source_name)
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

    def _extract_tool_call_from_text(self, content: str) -> tuple[dict | None, str]:
        """Extract tool call from <tool_call> tags in content."""
        import re
        # Find <tool_call>...</tool_call> or <tool_call>...
        match = re.search(r'<tool_call>\s*(\{[\s\S]*?\})\s*(?:</tool_call>|$)', content)
        if match:
            try:
                tool_call_json = json.loads(match.group(1))
                if "name" in tool_call_json and "arguments" in tool_call_json:
                    # Remove the tool_call from content
                    clean_content = re.sub(r'<tool_call>[\s\S]*?(?:</tool_call>|$)', '', content).strip()
                    return tool_call_json, clean_content
            except json.JSONDecodeError:
                pass
        return None, content

    def _clean_response(self, content: str) -> str:
        """Clean up response content - remove leaked tool_call JSON."""
        import re
        # Remove <tool_call>...</tool_call> blocks (greedy)
        content = re.sub(r'<tool_call>[\s\S]*?</tool_call>', '', content)
        # Remove <tool_call>... without closing tag (to end of string)
        content = re.sub(r'<tool_call>[\s\S]*$', '', content)
        # Remove standalone {"name": "xxx", "arguments": {...}} JSON blocks
        content = re.sub(r'\{"name":\s*"[^"]+",\s*"arguments":\s*\{[\s\S]*?\}\}', '', content)
        # Remove ``` code blocks containing tool calls
        content = re.sub(r'```json\s*\{[\s\S]*?"name"[\s\S]*?\}\s*```', '', content)
        # Clean up multiple newlines
        content = re.sub(r'\n{3,}', '\n\n', content)
        return content.strip()

    async def close(self):
        """Clean up resources."""
        for tool in self.tools.get_all():
            if hasattr(tool, "close"):
                await tool.close()
