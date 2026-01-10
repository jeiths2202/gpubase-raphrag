"""
Ollama LLM Adapter for Agent System
Provides tool-calling support using Ollama's OpenAI-compatible API.
"""
from typing import Dict, List, Any, Optional
import logging
import json
import aiohttp

logger = logging.getLogger(__name__)

# Default Ollama settings
OLLAMA_BASE_URL = "http://localhost:11434"
OLLAMA_MODEL = "qwen2.5:3b"  # Supports tool calling


class OllamaAgentAdapter:
    """
    Ollama LLM adapter for agent tool calling.
    Uses the OpenAI-compatible /v1/chat/completions endpoint.
    """

    _instance: Optional['OllamaAgentAdapter'] = None

    def __init__(
        self,
        base_url: str = OLLAMA_BASE_URL,
        model: str = OLLAMA_MODEL,
        temperature: float = 0.7,
        timeout: int = 120
    ):
        self.base_url = base_url.rstrip('/')
        self.model = model
        self.temperature = temperature
        self.timeout = timeout

    @classmethod
    def get_instance(cls) -> 'OllamaAgentAdapter':
        """Get singleton instance"""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    async def generate(
        self,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
        temperature: Optional[float] = None
    ) -> Dict[str, Any]:
        """
        Generate a response using Ollama.

        Args:
            messages: List of messages in OpenAI format
            tools: Optional list of tools for function calling
            temperature: Optional temperature override

        Returns:
            Dict with 'content' and optionally 'tool_calls'
        """
        url = f"{self.base_url}/v1/chat/completions"

        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature or self.temperature,
            "stream": False
        }

        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    url,
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=self.timeout)
                ) as response:
                    if response.status != 200:
                        error_text = await response.text()
                        logger.error(f"Ollama API error: {response.status} - {error_text}")
                        return {"content": f"LLM error: {response.status}"}

                    data = await response.json()
                    return self._parse_response(data)

        except aiohttp.ClientError as e:
            logger.error(f"Ollama connection error: {e}")
            return {"content": f"Connection error: {str(e)}"}
        except Exception as e:
            logger.error(f"Ollama adapter error: {e}")
            return {"content": f"Error: {str(e)}"}

    def _parse_response(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Parse Ollama response to extract content and tool calls"""
        result = {"content": ""}

        choices = data.get("choices", [])
        if not choices:
            return result

        message = choices[0].get("message", {})
        result["content"] = message.get("content", "")

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
        """Check if Ollama is available"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self.base_url}/api/tags",
                    timeout=aiohttp.ClientTimeout(total=5)
                ) as response:
                    return response.status == 200
        except Exception:
            return False


# Convenience function
def get_ollama_adapter() -> OllamaAgentAdapter:
    """Get the Ollama adapter instance"""
    return OllamaAgentAdapter.get_instance()
