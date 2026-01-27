"""
LLM Agent Adapter for Agent System
Provides tool-calling support using OpenAI-compatible API.

Supports:
- NVIDIA NIM LLM (primary) - port 12800
- Ollama (fallback) - port 11434

Both use OpenAI-compatible /v1/chat/completions endpoint.
"""
from typing import Dict, List, Any, Optional
import logging
import json
import asyncio
import os
import aiohttp

logger = logging.getLogger(__name__)

# RAG Large Context Mode
# When true: Uses Mistral NeMo 12B (128K context) for better RAG accuracy
# When false: Uses Nemotron Nano 9B (8K context) - faster but may truncate results
USE_LARGE_CONTEXT = os.getenv("RAG_LLM_USE_LARGE_CONTEXT", "false").lower() == "true"

# NIM LLM settings (primary)
if USE_LARGE_CONTEXT:
    # Large context mode: Mistral NeMo 12B (128K context)
    NIM_API_URL = os.getenv("CODE_LLM_API_URL")
    NIM_MODEL = os.getenv("CODE_LLM_MODEL", "mistralai/Mistral-Nemo-Instruct-2407")
    logger.info(f"RAG LLM: Large Context Mode (128K) - Model: {NIM_MODEL}")
else:
    # Standard mode: Nemotron Nano 9B (8K context)
    NIM_API_URL = os.getenv("LLM_API_URL")
    NIM_MODEL = os.getenv("LLM_MODEL", "nvidia/nvidia-nemotron-nano-9b-v2")

# Ollama settings (fallback)
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5:3b")

# Disable Ollama fallback if not available
DISABLE_OLLAMA_FALLBACK = os.getenv("DISABLE_OLLAMA_FALLBACK", "false").lower() == "true"


class LLMAgentAdapter:
    """
    LLM adapter for agent tool calling.
    Uses the OpenAI-compatible /v1/chat/completions endpoint.

    Supports NIM (primary) and Ollama (fallback) backends.
    """

    _instance: Optional['LLMAgentAdapter'] = None

    def __init__(
        self,
        base_url: str = None,
        model: str = None,
        temperature: float = 0.1,  # Low temperature for accurate RAG responses
        timeout: int = 300,
        use_nim: bool = True
    ):
        """
        Initialize LLM adapter.

        Args:
            base_url: API base URL (auto-detected if None)
            model: Model name (auto-detected if None)
            temperature: Generation temperature
            timeout: Request timeout in seconds
            use_nim: Try NIM first if available (default: True)
        """
        self.temperature = temperature
        self.timeout = timeout
        self.use_nim = use_nim and NIM_API_URL is not None

        # Configure backend
        if self.use_nim:
            # NIM backend
            nim_base = NIM_API_URL.replace("/chat/completions", "").replace("/v1", "").rstrip("/")
            self.base_url = base_url or nim_base
            self.model = model or NIM_MODEL
            self.backend = "nim"
        else:
            # Ollama backend
            self.base_url = (base_url or OLLAMA_BASE_URL).rstrip('/')
            self.model = model or OLLAMA_MODEL
            self.backend = "ollama"

        # Fallback configuration
        self._fallback_base_url = OLLAMA_BASE_URL.rstrip('/')
        self._fallback_model = OLLAMA_MODEL

        logger.info(f"LLMAgentAdapter initialized: backend={self.backend}, model={self.model}")

    @classmethod
    def get_instance(cls) -> 'LLMAgentAdapter':
        """Get singleton instance"""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @classmethod
    def reset_instance(cls):
        """Reset singleton instance (for testing)"""
        cls._instance = None

    async def generate(
        self,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
        temperature: Optional[float] = None,
        tool_choice: Optional[Any] = "auto"  # str or dict for specific tool
    ) -> Dict[str, Any]:
        """
        Generate a response using LLM with tool calling support.

        Args:
            messages: List of messages in OpenAI format
            tools: Optional list of tools for function calling
            temperature: Optional temperature override
            tool_choice: "auto", "none", or {"type": "function", "function": {"name": "tool_name"}}

        Returns:
            Dict with 'content' and optionally 'tool_calls'
        """
        # Try primary backend
        result = await self._generate_internal(
            base_url=self.base_url,
            model=self.model,
            messages=messages,
            tools=tools,
            temperature=temperature,
            backend_name=self.backend,
            tool_choice=tool_choice
        )

        # Check if we need fallback (connection/timeout/400 errors)
        if self._is_error_response(result) and self.use_nim and not DISABLE_OLLAMA_FALLBACK:
            error_content = result.get("content", "")
            # Fallback on connection, timeout, or 400 errors (NIM payload issues)
            if ("Connection error:" in error_content or
                "Timeout error:" in error_content or
                "LLM error: 400" in error_content):
                logger.warning(f"NIM request failed, falling back to Ollama: {error_content[:100]}")
                result = await self._generate_internal(
                    base_url=self._fallback_base_url,
                    model=self._fallback_model,
                    messages=messages,
                    tools=tools,
                    temperature=temperature,
                    backend_name="ollama",
                    tool_choice=tool_choice
                )
            else:
                # Don't fallback for other errors
                logger.warning(f"NIM request failed with non-recoverable error: {error_content[:100]}")

        return result

    def _is_error_response(self, result: Dict[str, Any]) -> bool:
        """Check if response indicates an error"""
        content = result.get("content", "")
        return (
            content.startswith("LLM error:") or
            content.startswith("Connection error:") or
            content.startswith("Timeout error:") or
            content.startswith("Error:")
        )

    async def _generate_internal(
        self,
        base_url: str,
        model: str,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
        temperature: Optional[float] = None,
        backend_name: str = "unknown",
        tool_choice: Optional[Any] = "auto"  # str or dict for specific tool
    ) -> Dict[str, Any]:
        """
        Internal generation method for a specific backend.

        Both NIM and Ollama use OpenAI-compatible API format.
        tool_choice can be: "auto", "none", or {"type": "function", "function": {"name": "tool_name"}}
        """
        url = f"{base_url}/v1/chat/completions"

        payload = {
            "model": model,
            "messages": messages,
            "temperature": temperature or self.temperature,
            "stream": False
        }

        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = tool_choice or "auto"

        try:
            # Log payload metrics (size, message count) for monitoring
            payload_size = len(json.dumps(payload, ensure_ascii=False))
            message_count = len(payload.get('messages', []))
            logger.debug(
                f"LLM request to {backend_name}: {payload_size} chars, {message_count} messages"
            )

            # Warn on very large payloads that may cause issues
            if payload_size > 50000:
                logger.warning(
                    f"Large payload ({payload_size} chars) to {backend_name} - "
                    "may cause timeout or truncation"
                )

            async with aiohttp.ClientSession() as session:
                async with session.post(
                    url,
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=self.timeout)
                ) as response:
                    if response.status != 200:
                        error_text = await response.text()
                        logger.error(f"{backend_name} API error: {response.status} - {error_text}")
                        return {"content": f"LLM error: {response.status}"}

                    data = await response.json()
                    result = self._parse_response(data)
                    result["_backend"] = backend_name
                    return result

        except aiohttp.ClientError as e:
            logger.error(f"{backend_name} connection error: {type(e).__name__}: {e}")
            return {"content": f"Connection error: {str(e)}"}
        except asyncio.TimeoutError:
            logger.error(f"{backend_name} timeout: Request exceeded {self.timeout}s")
            return {"content": f"Timeout error: Request exceeded {self.timeout}s"}
        except Exception as e:
            logger.error(f"{backend_name} adapter error: {type(e).__name__}: {e}", exc_info=True)
            return {"content": f"Error: {type(e).__name__}: {str(e)}"}

    def _parse_response(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Parse OpenAI-compatible response to extract content and tool calls"""
        result = {"content": ""}

        choices = data.get("choices", [])
        if not choices:
            return result

        message = choices[0].get("message", {})
        result["content"] = message.get("content", "") or ""

        # Extract tool calls if present
        tool_calls = message.get("tool_calls", [])
        if tool_calls:
            result["tool_calls"] = []
            for tc in tool_calls:
                func = tc.get("function", {})
                args = func.get("arguments", "{}")

                # Parse arguments if string
                if isinstance(args, str):
                    try:
                        args = json.loads(args)
                    except json.JSONDecodeError:
                        args = {}

                result["tool_calls"].append({
                    "id": tc.get("id", ""),
                    "function": {
                        "name": func.get("name", ""),
                        "arguments": args
                    }
                })

        return result

    async def health_check(self) -> bool:
        """Check if LLM backend is available"""
        # Check primary backend
        if await self._check_backend_health(self.base_url, self.backend):
            return True

        # Check fallback if primary is NIM
        if self.use_nim:
            return await self._check_backend_health(self._fallback_base_url, "ollama")

        return False

    async def _check_backend_health(self, base_url: str, backend_name: str) -> bool:
        """Check health of a specific backend"""
        try:
            async with aiohttp.ClientSession() as session:
                if backend_name == "nim":
                    # NIM uses OpenAI-compatible health endpoint
                    health_url = f"{base_url}/v1/models"
                else:
                    # Ollama uses /api/tags
                    health_url = f"{base_url}/api/tags"

                async with session.get(
                    health_url,
                    timeout=aiohttp.ClientTimeout(total=5)
                ) as response:
                    if response.status == 200:
                        logger.debug(f"{backend_name} health check passed")
                        return True
                    return False
        except Exception as e:
            logger.debug(f"{backend_name} health check failed: {e}")
            return False

    def get_backend_info(self) -> Dict[str, Any]:
        """Get current backend configuration info"""
        return {
            "backend": self.backend,
            "base_url": self.base_url,
            "model": self.model,
            "use_nim": self.use_nim,
            "fallback_available": self.use_nim,
            "fallback_url": self._fallback_base_url if self.use_nim else None,
            "fallback_model": self._fallback_model if self.use_nim else None
        }


# Backward compatibility alias
OllamaAgentAdapter = LLMAgentAdapter


def get_llm_adapter() -> LLMAgentAdapter:
    """Get the LLM adapter instance (NIM primary, Ollama fallback)"""
    return LLMAgentAdapter.get_instance()


# Backward compatibility alias
def get_ollama_adapter() -> LLMAgentAdapter:
    """Get the LLM adapter instance (backward compatibility alias)"""
    return get_llm_adapter()
