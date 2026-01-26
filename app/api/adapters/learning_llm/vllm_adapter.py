"""
Learning LLM vLLM Adapter

외부 vLLM 서버에 연결하여 추론을 수행합니다.
Docker 컨테이너로 배포된 Learning LLM 서비스에 연결합니다.
"""
import os
import logging
import aiohttp
from typing import Optional, Dict, Any, AsyncGenerator

logger = logging.getLogger(__name__)


class VLLMAdapter:
    """
    vLLM 서버 연결 어댑터

    OpenAI 호환 API를 통해 외부 vLLM 서버에 연결합니다.
    """

    def __init__(
        self,
        base_url: Optional[str] = None,
        model: str = "Qwen/Qwen2.5-7B-Instruct",
        timeout: int = 60,
    ):
        self.base_url = base_url or os.getenv(
            "LEARNING_LLM_URL",
            "http://learning-llm-graphrag:8000/v1"
        )
        self.model = model
        self.timeout = timeout
        self.is_loaded = False
        self.current_adapter = "vllm-server"

    async def health_check(self) -> Dict[str, Any]:
        """vLLM 서버 헬스 체크"""
        try:
            # Try /health endpoint first
            health_url = self.base_url.replace("/v1", "/health")
            async with aiohttp.ClientSession() as session:
                async with session.get(health_url, timeout=5) as resp:
                    if resp.status == 200:
                        self.is_loaded = True
                        return {"status": "healthy", "url": self.base_url}
        except Exception as e:
            logger.debug(f"Health endpoint failed: {e}")

        # Try /v1/models as fallback
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(f"{self.base_url}/models", timeout=5) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        self.is_loaded = True
                        return {
                            "status": "healthy",
                            "url": self.base_url,
                            "models": data.get("data", [])
                        }
        except Exception as e:
            logger.error(f"vLLM health check failed: {e}")

        self.is_loaded = False
        return {"status": "unhealthy", "url": self.base_url, "error": str(e)}

    async def load(self) -> bool:
        """연결 확인 (vLLM은 항상 로드된 상태)"""
        result = await self.health_check()
        return result.get("status") == "healthy"

    async def unload(self):
        """연결 해제 (no-op for vLLM)"""
        self.is_loaded = False

    async def generate(
        self,
        question: str,
        context: Optional[str] = None,
        max_new_tokens: int = 512,
        temperature: float = 0.7,
        top_p: float = 0.9,
        **kwargs
    ) -> str:
        """
        vLLM 서버를 통한 응답 생성

        Args:
            question: 사용자 질문
            context: 추가 컨텍스트
            max_new_tokens: 최대 생성 토큰
            temperature: 샘플링 온도

        Returns:
            생성된 응답
        """
        messages = self._build_messages(question, context)

        payload = {
            "model": self.model,
            "messages": messages,
            "max_tokens": max_new_tokens,
            "temperature": temperature,
            "top_p": top_p,
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.base_url}/chat/completions",
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=self.timeout)
                ) as resp:
                    if resp.status != 200:
                        error_text = await resp.text()
                        logger.error(f"vLLM error: {resp.status} - {error_text}")
                        return ""

                    data = await resp.json()
                    return data["choices"][0]["message"]["content"]

        except Exception as e:
            logger.error(f"vLLM generation failed: {e}")
            return ""

    async def generate_stream(
        self,
        question: str,
        context: Optional[str] = None,
        max_new_tokens: int = 512,
        temperature: float = 0.7,
        top_p: float = 0.9,
    ) -> AsyncGenerator[str, None]:
        """스트리밍 응답 생성"""
        messages = self._build_messages(question, context)

        payload = {
            "model": self.model,
            "messages": messages,
            "max_tokens": max_new_tokens,
            "temperature": temperature,
            "top_p": top_p,
            "stream": True,
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.base_url}/chat/completions",
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=self.timeout)
                ) as resp:
                    if resp.status != 200:
                        return

                    async for line in resp.content:
                        line = line.decode("utf-8").strip()
                        if line.startswith("data: "):
                            data_str = line[6:]
                            if data_str == "[DONE]":
                                break
                            try:
                                import json
                                data = json.loads(data_str)
                                delta = data["choices"][0].get("delta", {})
                                if "content" in delta:
                                    yield delta["content"]
                            except:
                                continue

        except Exception as e:
            logger.error(f"vLLM streaming failed: {e}")

    def _build_messages(self, question: str, context: Optional[str] = None) -> list:
        """OpenAI 형식 메시지 빌드"""
        messages = [
            {
                "role": "system",
                "content": "You are a helpful KMS assistant that provides accurate answers based on verified knowledge."
            }
        ]

        if context:
            user_content = f"{question}\n\nContext:\n{context}"
        else:
            user_content = question

        messages.append({
            "role": "user",
            "content": user_content
        })

        return messages

    def get_status(self) -> Dict[str, Any]:
        """상태 반환"""
        return {
            "type": "vllm",
            "is_loaded": self.is_loaded,
            "base_url": self.base_url,
            "model": self.model,
            "current_adapter": self.current_adapter,
        }


# Singleton
_vllm_adapter: Optional[VLLMAdapter] = None


def get_vllm_adapter() -> Optional[VLLMAdapter]:
    """Get vLLM adapter singleton"""
    global _vllm_adapter
    return _vllm_adapter


async def initialize_vllm_adapter(
    base_url: Optional[str] = None,
    model: str = "Qwen/Qwen2.5-7B-Instruct",
) -> VLLMAdapter:
    """Initialize vLLM adapter"""
    global _vllm_adapter

    _vllm_adapter = VLLMAdapter(base_url=base_url, model=model)
    await _vllm_adapter.load()

    logger.info(f"vLLM adapter initialized: {_vllm_adapter.base_url}")
    return _vllm_adapter
