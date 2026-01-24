"""
Code LLM Service

경량 코드 생성 LLM 서비스 (Mistral NeMo 12B → CodeQwen 3B 교체 지원)

Features:
- Primary: NIM/vLLM endpoint (CodeQwen 3B)
- Fallback: Ollama (qwen2.5-coder:3b)
- Automatic model switching based on availability
"""
import os
import logging
import asyncio
import aiohttp
from typing import Optional, Dict, Any, List, AsyncGenerator

logger = logging.getLogger(__name__)


class CodeLLMService:
    """
    Code LLM 서비스

    경량 코드 생성 모델을 사용하여 코드 관련 작업을 처리합니다.
    GPU 메모리 효율을 위해 Mistral NeMo 12B에서 CodeQwen 3B로 교체 지원.
    """

    def __init__(
        self,
        primary_api_url: Optional[str] = None,
        primary_model: Optional[str] = None,
        ollama_url: Optional[str] = None,
        ollama_model: Optional[str] = None,
        use_ollama_fallback: bool = True,
        timeout: float = 60.0,
    ):
        # Primary endpoint (NIM/vLLM)
        self.primary_api_url = primary_api_url or os.getenv(
            "CODE_LLM_API_URL",
            "http://codeqwen-graphrag:8000/v1/chat/completions"
        )
        self.primary_model = primary_model or os.getenv(
            "CODE_LLM_MODEL",
            "Qwen/Qwen2.5-Coder-3B-Instruct"
        )

        # Ollama fallback
        self.ollama_url = ollama_url or os.getenv(
            "OLLAMA_BASE_URL",
            "http://192.168.8.11:11434"
        )
        self.ollama_model = ollama_model or os.getenv(
            "CODE_LLM_OLLAMA_MODEL",
            "qwen2.5-coder:3b"
        )
        self.use_ollama_fallback = use_ollama_fallback

        self.timeout = timeout
        self._primary_available = None
        self._ollama_available = None
        self._last_check_time = 0
        self._check_interval = 60  # Check every 60 seconds

    async def _check_primary_health(self) -> bool:
        """Primary endpoint 상태 확인"""
        try:
            async with aiohttp.ClientSession() as session:
                # Try models endpoint for OpenAI-compatible API
                async with session.get(
                    f"{self.primary_api_url.rsplit('/', 2)[0]}/models",
                    timeout=aiohttp.ClientTimeout(total=5)
                ) as response:
                    return response.status == 200
        except Exception:
            return False

    async def _check_ollama_health(self) -> bool:
        """Ollama 상태 확인"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self.ollama_url}/api/tags",
                    timeout=aiohttp.ClientTimeout(total=5)
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        models = [m.get("name", "") for m in data.get("models", [])]
                        return any(self.ollama_model.split(":")[0] in m for m in models)
        except Exception:
            return False
        return False

    async def _ensure_availability(self) -> str:
        """사용 가능한 서비스 확인 및 반환"""
        import time
        current_time = time.time()

        # Cache health check results
        if current_time - self._last_check_time > self._check_interval:
            self._primary_available = await self._check_primary_health()
            if self.use_ollama_fallback:
                self._ollama_available = await self._check_ollama_health()
            self._last_check_time = current_time

        if self._primary_available:
            return "primary"
        elif self.use_ollama_fallback and self._ollama_available:
            return "ollama"
        else:
            raise RuntimeError("No Code LLM service available")

    async def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        max_tokens: int = 2048,
        temperature: float = 0.1,
        stop: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        코드 생성

        Args:
            prompt: 사용자 프롬프트
            system_prompt: 시스템 프롬프트
            max_tokens: 최대 토큰 수
            temperature: 샘플링 온도
            stop: 중지 시퀀스

        Returns:
            생성 결과
        """
        try:
            service = await self._ensure_availability()

            if service == "primary":
                return await self._generate_primary(
                    prompt, system_prompt, max_tokens, temperature, stop
                )
            else:
                return await self._generate_ollama(
                    prompt, system_prompt, max_tokens, temperature, stop
                )

        except Exception as e:
            logger.error(f"Code LLM generation failed: {e}")
            raise

    async def _generate_primary(
        self,
        prompt: str,
        system_prompt: Optional[str],
        max_tokens: int,
        temperature: float,
        stop: Optional[List[str]],
    ) -> Dict[str, Any]:
        """Primary endpoint로 생성"""
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        payload = {
            "model": self.primary_model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        if stop:
            payload["stop"] = stop

        async with aiohttp.ClientSession() as session:
            async with session.post(
                self.primary_api_url,
                json=payload,
                timeout=aiohttp.ClientTimeout(total=self.timeout)
            ) as response:
                if response.status != 200:
                    error_text = await response.text()
                    raise RuntimeError(f"Primary API error: {error_text}")

                data = await response.json()
                content = data["choices"][0]["message"]["content"]

                return {
                    "content": content,
                    "model": self.primary_model,
                    "service": "primary",
                    "usage": data.get("usage", {}),
                }

    async def _generate_ollama(
        self,
        prompt: str,
        system_prompt: Optional[str],
        max_tokens: int,
        temperature: float,
        stop: Optional[List[str]],
    ) -> Dict[str, Any]:
        """Ollama로 생성"""
        full_prompt = prompt
        if system_prompt:
            full_prompt = f"{system_prompt}\n\n{prompt}"

        payload = {
            "model": self.ollama_model,
            "prompt": full_prompt,
            "stream": False,
            "options": {
                "num_predict": max_tokens,
                "temperature": temperature,
            }
        }
        if stop:
            payload["options"]["stop"] = stop

        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{self.ollama_url}/api/generate",
                json=payload,
                timeout=aiohttp.ClientTimeout(total=self.timeout)
            ) as response:
                if response.status != 200:
                    error_text = await response.text()
                    raise RuntimeError(f"Ollama API error: {error_text}")

                data = await response.json()
                content = data.get("response", "")

                return {
                    "content": content,
                    "model": self.ollama_model,
                    "service": "ollama",
                    "usage": {
                        "prompt_tokens": data.get("prompt_eval_count", 0),
                        "completion_tokens": data.get("eval_count", 0),
                    },
                }

    async def generate_stream(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        max_tokens: int = 2048,
        temperature: float = 0.1,
    ) -> AsyncGenerator[str, None]:
        """스트리밍 코드 생성"""
        try:
            service = await self._ensure_availability()

            if service == "primary":
                async for token in self._stream_primary(
                    prompt, system_prompt, max_tokens, temperature
                ):
                    yield token
            else:
                async for token in self._stream_ollama(
                    prompt, system_prompt, max_tokens, temperature
                ):
                    yield token

        except Exception as e:
            logger.error(f"Code LLM streaming failed: {e}")
            raise

    async def _stream_primary(
        self,
        prompt: str,
        system_prompt: Optional[str],
        max_tokens: int,
        temperature: float,
    ) -> AsyncGenerator[str, None]:
        """Primary endpoint 스트리밍"""
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        payload = {
            "model": self.primary_model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "stream": True,
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(
                self.primary_api_url,
                json=payload,
                timeout=aiohttp.ClientTimeout(total=self.timeout)
            ) as response:
                async for line in response.content:
                    line = line.decode("utf-8").strip()
                    if line.startswith("data: "):
                        data = line[6:]
                        if data == "[DONE]":
                            break
                        try:
                            import json
                            chunk = json.loads(data)
                            delta = chunk.get("choices", [{}])[0].get("delta", {})
                            if "content" in delta:
                                yield delta["content"]
                        except Exception:
                            continue

    async def _stream_ollama(
        self,
        prompt: str,
        system_prompt: Optional[str],
        max_tokens: int,
        temperature: float,
    ) -> AsyncGenerator[str, None]:
        """Ollama 스트리밍"""
        full_prompt = prompt
        if system_prompt:
            full_prompt = f"{system_prompt}\n\n{prompt}"

        payload = {
            "model": self.ollama_model,
            "prompt": full_prompt,
            "stream": True,
            "options": {
                "num_predict": max_tokens,
                "temperature": temperature,
            }
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{self.ollama_url}/api/generate",
                json=payload,
                timeout=aiohttp.ClientTimeout(total=self.timeout)
            ) as response:
                async for line in response.content:
                    try:
                        import json
                        data = json.loads(line.decode("utf-8"))
                        if data.get("response"):
                            yield data["response"]
                        if data.get("done"):
                            break
                    except Exception:
                        continue

    def get_status(self) -> Dict[str, Any]:
        """서비스 상태 반환"""
        return {
            "primary": {
                "url": self.primary_api_url,
                "model": self.primary_model,
                "available": self._primary_available,
            },
            "ollama": {
                "url": self.ollama_url,
                "model": self.ollama_model,
                "available": self._ollama_available,
                "fallback_enabled": self.use_ollama_fallback,
            },
            "active_service": "primary" if self._primary_available else (
                "ollama" if self._ollama_available else "none"
            ),
        }


# ============================================
# Singleton Instance
# ============================================

_code_llm_service: Optional[CodeLLMService] = None


def get_code_llm_service() -> Optional[CodeLLMService]:
    """Get Code LLM service singleton"""
    global _code_llm_service
    return _code_llm_service


def initialize_code_llm_service(
    primary_api_url: Optional[str] = None,
    primary_model: Optional[str] = None,
    ollama_url: Optional[str] = None,
    ollama_model: Optional[str] = None,
    use_ollama_fallback: bool = True,
) -> CodeLLMService:
    """Initialize Code LLM service"""
    global _code_llm_service

    _code_llm_service = CodeLLMService(
        primary_api_url=primary_api_url,
        primary_model=primary_model,
        ollama_url=ollama_url,
        ollama_model=ollama_model,
        use_ollama_fallback=use_ollama_fallback,
    )

    logger.info(f"Code LLM service initialized (primary: {_code_llm_service.primary_model})")
    return _code_llm_service
