"""
Ollama LLM Adapter

LLM adapter for local Ollama models (Gemma, Llama, Mistral, etc.)
Useful for local testing without GPU-based NIM containers.
"""
import aiohttp
import json
import logging
from typing import Optional, List, Dict, Any, AsyncGenerator

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


class OllamaLLMAdapter(LLMPort):
    """
    Ollama LLM adapter for local model inference.

    Supports:
    - gemma3:1b, gemma:2b, gemma:7b
    - llama2, llama3
    - mistral, mixtral
    - And other Ollama-compatible models
    """

    def __init__(
        self,
        model: str = "gemma3:1b",
        base_url: str = "http://localhost:11434",
        default_config: Optional[LLMConfig] = None
    ):
        """
        Initialize Ollama adapter.

        Args:
            model: Model name (e.g., "gemma3:1b", "llama3:8b")
            base_url: Ollama API base URL
            default_config: Default LLM configuration
        """
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.default_config = default_config or LLMConfig(
            model=model,
            temperature=0.7,
            max_tokens=2048
        )
        logger.info(f"[Ollama] Initialized with model={model}, base_url={base_url}")

    def _convert_messages(self, messages: List[LLMMessage]) -> List[Dict[str, str]]:
        """Convert LLMMessage to Ollama format."""
        result = []
        for msg in messages:
            role = msg.role.value  # system, user, assistant
            result.append({
                "role": role,
                "content": msg.content
            })
        return result

    async def generate(
        self,
        messages: List[LLMMessage],
        config: Optional[LLMConfig] = None
    ) -> LLMResponse:
        """Generate response using Ollama API."""
        cfg = config or self.default_config

        ollama_messages = self._convert_messages(messages)

        payload = {
            "model": self.model,
            "messages": ollama_messages,
            "stream": False,
            "options": {
                "temperature": cfg.temperature,
                "num_predict": cfg.max_tokens
            }
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.base_url}/api/chat",
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=cfg.timeout or 120)
                ) as response:
                    if response.status != 200:
                        error_text = await response.text()
                        raise Exception(f"Ollama API error: {response.status} - {error_text}")

                    result = await response.json()

            content = result.get("message", {}).get("content", "")

            # Extract token usage
            prompt_tokens = result.get("prompt_eval_count", 0)
            completion_tokens = result.get("eval_count", 0)

            return LLMResponse(
                content=content,
                model=self.model,
                usage=LLMTokenUsage(
                    prompt_tokens=prompt_tokens,
                    completion_tokens=completion_tokens,
                    total_tokens=prompt_tokens + completion_tokens
                ),
                finish_reason="stop",
                metadata={
                    "total_duration": result.get("total_duration"),
                    "load_duration": result.get("load_duration"),
                    "eval_duration": result.get("eval_duration")
                }
            )

        except aiohttp.ClientError as e:
            logger.error(f"Ollama connection error: {e}")
            raise Exception(f"Failed to connect to Ollama at {self.base_url}: {e}")
        except Exception as e:
            logger.error(f"Ollama generation failed: {e}")
            raise

    async def generate_stream(
        self,
        messages: List[LLMMessage],
        config: Optional[LLMConfig] = None
    ) -> AsyncGenerator[LLMStreamChunk, None]:
        """Stream response using Ollama API."""
        cfg = config or self.default_config

        ollama_messages = self._convert_messages(messages)

        payload = {
            "model": self.model,
            "messages": ollama_messages,
            "stream": True,
            "options": {
                "temperature": cfg.temperature,
                "num_predict": cfg.max_tokens
            }
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.base_url}/api/chat",
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=cfg.timeout or 300)
                ) as response:
                    if response.status != 200:
                        error_text = await response.text()
                        raise Exception(f"Ollama API error: {response.status} - {error_text}")

                    async for line in response.content:
                        if not line:
                            continue

                        try:
                            chunk_data = json.loads(line.decode("utf-8"))
                            content = chunk_data.get("message", {}).get("content", "")
                            done = chunk_data.get("done", False)

                            if content:
                                yield LLMStreamChunk(
                                    content=content,
                                    is_final=False
                                )

                            if done:
                                yield LLMStreamChunk(
                                    content="",
                                    is_final=True,
                                    finish_reason="stop",
                                    metadata={
                                        "total_duration": chunk_data.get("total_duration"),
                                        "eval_count": chunk_data.get("eval_count")
                                    }
                                )
                                break

                        except json.JSONDecodeError:
                            continue

        except aiohttp.ClientError as e:
            logger.error(f"Ollama streaming error: {e}")
            raise Exception(f"Failed to stream from Ollama at {self.base_url}: {e}")
        except Exception as e:
            logger.error(f"Ollama streaming failed: {e}")
            raise

    async def count_tokens(self, text: str) -> int:
        """
        Estimate token count.

        Note: Ollama doesn't have a dedicated tokenization endpoint,
        so we use a rough estimate (4 chars per token for English).
        """
        return len(text) // 4

    async def get_available_models(self) -> List[str]:
        """Get list of locally available Ollama models."""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self.base_url}/api/tags",
                    timeout=aiohttp.ClientTimeout(total=10)
                ) as response:
                    if response.status != 200:
                        return [self.model]

                    result = await response.json()
                    models = result.get("models", [])
                    return [m.get("name", "") for m in models if m.get("name")]

        except Exception as e:
            logger.warning(f"Failed to get Ollama models: {e}")
            return [self.model]

    async def health_check(self) -> bool:
        """Check if Ollama is running and model is available."""
        try:
            async with aiohttp.ClientSession() as session:
                # Check if Ollama is running
                async with session.get(
                    f"{self.base_url}/api/tags",
                    timeout=aiohttp.ClientTimeout(total=5)
                ) as response:
                    if response.status != 200:
                        return False

                    result = await response.json()
                    models = [m.get("name", "") for m in result.get("models", [])]

                    # Check if our model is available
                    return any(self.model in m for m in models)

        except Exception:
            return False


# Factory function for easy instantiation
def get_ollama_llm(
    model: str = "gemma3:1b",
    base_url: str = "http://localhost:11434"
) -> OllamaLLMAdapter:
    """
    Get Ollama LLM adapter instance.

    Args:
        model: Model name
        base_url: Ollama API URL

    Returns:
        OllamaLLMAdapter instance
    """
    return OllamaLLMAdapter(model=model, base_url=base_url)
