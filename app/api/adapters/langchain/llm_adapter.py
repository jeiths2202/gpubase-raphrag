"""
LangChain LLM Adapter
Implements LLMPort using LangChain's ChatOpenAI.
"""
from typing import Optional, List, Dict, Any, AsyncGenerator
import logging

from ...ports.llm_port import (
    LLMPort,
    LLMMessage,
    LLMConfig,
    LLMResponse,
    LLMStreamChunk,
    LLMTokenUsage,
    LLMRole
)

logger = logging.getLogger(__name__)


class LangChainLLMAdapter(LLMPort):
    """
    LLM adapter using LangChain's ChatOpenAI.

    This adapter wraps LangChain's OpenAI integration to provide
    a clean interface that conforms to our LLMPort specification.
    """

    def __init__(
        self,
        api_key: str,
        model: str = "gpt-4",
        base_url: Optional[str] = None,
        default_config: Optional[LLMConfig] = None
    ):
        self.api_key = api_key
        self.model = model
        self.base_url = base_url
        self.default_config = default_config or LLMConfig(model=model)
        self._client = None

    def _get_client(self, config: LLMConfig):
        """Get or create LangChain ChatOpenAI client"""
        try:
            from langchain_openai import ChatOpenAI

            return ChatOpenAI(
                api_key=self.api_key,
                model=config.model,
                temperature=config.temperature,
                max_tokens=config.max_tokens,
                base_url=self.base_url,
                timeout=config.timeout,
                **config.extra_params
            )
        except ImportError:
            raise ImportError("langchain_openai is required for LangChainLLMAdapter")

    def _convert_messages(self, messages: List[LLMMessage]) -> List:
        """Convert LLMMessage to LangChain message format"""
        from langchain_core.messages import HumanMessage, AIMessage, SystemMessage

        result = []
        for msg in messages:
            if msg.role == LLMRole.SYSTEM:
                result.append(SystemMessage(content=msg.content))
            elif msg.role == LLMRole.USER:
                result.append(HumanMessage(content=msg.content))
            elif msg.role == LLMRole.ASSISTANT:
                result.append(AIMessage(content=msg.content))
        return result

    async def generate(
        self,
        messages: List[LLMMessage],
        config: Optional[LLMConfig] = None
    ) -> LLMResponse:
        """Generate response using LangChain ChatOpenAI"""
        cfg = config or self.default_config
        client = self._get_client(cfg)

        try:
            langchain_messages = self._convert_messages(messages)
            response = await client.ainvoke(langchain_messages)

            # Extract token usage if available
            usage = LLMTokenUsage()
            if hasattr(response, 'response_metadata'):
                token_usage = response.response_metadata.get('token_usage', {})
                usage = LLMTokenUsage(
                    prompt_tokens=token_usage.get('prompt_tokens', 0),
                    completion_tokens=token_usage.get('completion_tokens', 0),
                    total_tokens=token_usage.get('total_tokens', 0)
                )

            return LLMResponse(
                content=response.content,
                model=cfg.model,
                usage=usage,
                finish_reason="stop",
                metadata=getattr(response, 'response_metadata', {})
            )

        except Exception as e:
            logger.error(f"LLM generation failed: {e}")
            raise

    async def generate_stream(
        self,
        messages: List[LLMMessage],
        config: Optional[LLMConfig] = None
    ) -> AsyncGenerator[LLMStreamChunk, None]:
        """Stream response using LangChain ChatOpenAI"""
        cfg = config or self.default_config
        client = self._get_client(cfg)

        try:
            langchain_messages = self._convert_messages(messages)

            async for chunk in client.astream(langchain_messages):
                content = chunk.content if hasattr(chunk, 'content') else str(chunk)
                yield LLMStreamChunk(
                    content=content,
                    is_final=False
                )

            yield LLMStreamChunk(
                content="",
                is_final=True,
                finish_reason="stop"
            )

        except Exception as e:
            logger.error(f"LLM streaming failed: {e}")
            raise

    async def count_tokens(self, text: str) -> int:
        """Count tokens using tiktoken"""
        try:
            import tiktoken

            encoding = tiktoken.encoding_for_model(self.model)
            return len(encoding.encode(text))
        except Exception:
            # Fallback: rough estimate
            return len(text) // 4

    async def get_available_models(self) -> List[str]:
        """Return available OpenAI models"""
        return [
            "gpt-4",
            "gpt-4-turbo",
            "gpt-4o",
            "gpt-4o-mini",
            "gpt-3.5-turbo"
        ]

    async def generate_with_functions(
        self,
        messages: List[LLMMessage],
        functions: List[Dict[str, Any]],
        config: Optional[LLMConfig] = None
    ) -> LLMResponse:
        """Generate with function calling"""
        cfg = config or self.default_config
        client = self._get_client(cfg)

        try:
            langchain_messages = self._convert_messages(messages)
            client_with_tools = client.bind_tools(functions)
            response = await client_with_tools.ainvoke(langchain_messages)

            return LLMResponse(
                content=response.content,
                model=cfg.model,
                metadata={
                    "tool_calls": getattr(response, 'tool_calls', [])
                }
            )

        except Exception as e:
            logger.error(f"Function calling failed: {e}")
            raise

    async def health_check(self) -> bool:
        """Check if OpenAI API is accessible"""
        try:
            await self.count_tokens("health check")
            return True
        except Exception:
            return False
