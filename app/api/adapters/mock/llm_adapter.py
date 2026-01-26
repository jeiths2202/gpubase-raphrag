"""
Mock LLM Adapter
Mock implementation for testing and development.
"""
from typing import Optional, List, Dict, Any, AsyncGenerator
import asyncio
import random

from ...ports.llm_port import (
    LLMPort,
    LLMMessage,
    LLMConfig,
    LLMResponse,
    LLMStreamChunk,
    LLMTokenUsage,
    LLMRole
)


class MockLLMAdapter(LLMPort):
    """
    Mock LLM adapter for testing and development.

    Generates predictable responses without calling external APIs.
    """

    def __init__(
        self,
        model: str = "mock-gpt-4",
        response_template: Optional[str] = None,
        simulate_delay: bool = True,
        delay_ms: int = 100
    ):
        self.model = model
        self.response_template = response_template or "This is a mock response to: {question}"
        self.simulate_delay = simulate_delay
        self.delay_ms = delay_ms
        self._call_count = 0
        self._call_history: List[Dict[str, Any]] = []

    async def generate(
        self,
        messages: List[LLMMessage],
        config: Optional[LLMConfig] = None
    ) -> LLMResponse:
        """Generate mock response"""
        self._call_count += 1

        if self.simulate_delay:
            await asyncio.sleep(self.delay_ms / 1000)

        # Get last user message
        last_user_msg = ""
        for msg in reversed(messages):
            if msg.role == LLMRole.USER:
                last_user_msg = msg.content
                break

        # Generate response
        content = self.response_template.format(question=last_user_msg)

        # Calculate mock tokens
        prompt_tokens = sum(len(m.content) // 4 for m in messages)
        completion_tokens = len(content) // 4

        # Record call
        self._call_history.append({
            "messages": [m.content for m in messages],
            "response": content,
            "config": config
        })

        return LLMResponse(
            content=content,
            model=self.model,
            usage=LLMTokenUsage(
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                total_tokens=prompt_tokens + completion_tokens
            ),
            finish_reason="stop"
        )

    async def generate_stream(
        self,
        messages: List[LLMMessage],
        config: Optional[LLMConfig] = None
    ) -> AsyncGenerator[LLMStreamChunk, None]:
        """Stream mock response word by word"""
        self._call_count += 1

        # Get last user message
        last_user_msg = ""
        for msg in reversed(messages):
            if msg.role == LLMRole.USER:
                last_user_msg = msg.content
                break

        content = self.response_template.format(question=last_user_msg)
        words = content.split()

        for i, word in enumerate(words):
            if self.simulate_delay:
                await asyncio.sleep(self.delay_ms / 1000 / len(words))

            yield LLMStreamChunk(
                content=word + " ",
                is_final=False
            )

        yield LLMStreamChunk(
            content="",
            is_final=True,
            finish_reason="stop"
        )

    async def count_tokens(self, text: str) -> int:
        """Count tokens (mock implementation)"""
        return len(text) // 4

    async def get_available_models(self) -> List[str]:
        """Return mock models"""
        return ["mock-gpt-4", "mock-gpt-3.5", "mock-claude"]

    async def generate_with_functions(
        self,
        messages: List[LLMMessage],
        functions: List[Dict[str, Any]],
        config: Optional[LLMConfig] = None
    ) -> LLMResponse:
        """Generate with mock function call"""
        response = await self.generate(messages, config)

        # Randomly decide whether to call a function
        if functions and random.random() > 0.5:
            func = random.choice(functions)
            response.metadata["tool_calls"] = [{
                "function": {
                    "name": func.get("name", "mock_function"),
                    "arguments": "{}"
                }
            }]

        return response

    async def health_check(self) -> bool:
        """Always healthy"""
        return True

    # ==================== Test Helpers ====================

    def get_call_count(self) -> int:
        """Get number of calls made"""
        return self._call_count

    def get_call_history(self) -> List[Dict[str, Any]]:
        """Get call history"""
        return self._call_history

    def reset(self) -> None:
        """Reset mock state"""
        self._call_count = 0
        self._call_history = []

    def set_response_template(self, template: str) -> None:
        """Set response template"""
        self.response_template = template
