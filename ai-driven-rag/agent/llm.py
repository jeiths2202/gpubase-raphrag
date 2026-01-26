"""LLM Client with OpenAI-compatible API."""
import json
from dataclasses import dataclass
from typing import AsyncIterator

import httpx

from config import config


@dataclass
class ToolCall:
    """Represents a tool call from the LLM."""
    id: str
    name: str
    arguments: dict


@dataclass
class LLMResponse:
    """Response from LLM."""
    content: str | None
    tool_calls: list[ToolCall] | None
    finish_reason: str


class LLMClient:
    """OpenAI-compatible LLM client with tool calling support."""

    def __init__(
        self,
        api_url: str | None = None,
        model: str | None = None,
        temperature: float | None = None,
    ):
        base_url = (api_url or config.llm_api_url).rstrip("/")
        # Handle URL that already includes /chat/completions
        if base_url.endswith("/chat/completions"):
            self.chat_url = base_url
        elif base_url.endswith("/v1"):
            self.chat_url = f"{base_url}/chat/completions"
        else:
            self.chat_url = f"{base_url}/v1/chat/completions"
        self.model = model or config.llm_model
        self.temperature = temperature if temperature is not None else config.llm_temperature

    async def chat(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
        stream: bool = False,
    ) -> LLMResponse:
        """Send chat completion request."""
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": self.temperature,
            "max_tokens": config.llm_max_tokens,
        }

        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"

        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.post(
                self.chat_url,
                json=payload,
            )
            response.raise_for_status()
            data = response.json()

        choice = data["choices"][0]
        message = choice["message"]

        # Parse tool calls if present
        tool_calls = None
        if message.get("tool_calls"):
            tool_calls = []
            for tc in message["tool_calls"]:
                try:
                    args = json.loads(tc["function"]["arguments"])
                except json.JSONDecodeError:
                    args = {"raw": tc["function"]["arguments"]}

                tool_calls.append(ToolCall(
                    id=tc["id"],
                    name=tc["function"]["name"],
                    arguments=args,
                ))

        return LLMResponse(
            content=message.get("content"),
            tool_calls=tool_calls,
            finish_reason=choice.get("finish_reason", "stop"),
        )

    async def chat_stream(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
    ) -> AsyncIterator[str]:
        """Stream chat completion response."""
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": self.temperature,
            "max_tokens": config.llm_max_tokens,
            "stream": True,
        }

        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"

        async with httpx.AsyncClient(timeout=120.0) as client:
            async with client.stream(
                "POST",
                self.chat_url,
                json=payload,
            ) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if line.startswith("data: "):
                        data_str = line[6:]
                        if data_str == "[DONE]":
                            break
                        try:
                            data = json.loads(data_str)
                            delta = data["choices"][0].get("delta", {})
                            if content := delta.get("content"):
                                yield content
                        except json.JSONDecodeError:
                            continue
