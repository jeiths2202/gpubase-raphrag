"""
Learning LLM vLLM Adapter

외부 vLLM 서버에 연결하여 추론을 수행합니다.
Docker 컨테이너로 배포된 Learning LLM 서비스에 연결합니다.

Usage:
    from app.api.adapters.learning_llm.vllm_adapter import get_vllm_adapter

    adapter = get_vllm_adapter()
    result = await adapter.generate_with_confidence(
        question="에러코드 -5212의 원인은?",
        context="TJES 관련 문서"
    )
    print(result["answer"], result["confidence"])
"""
import os
import re
import json
import logging
import aiohttp
from typing import Optional, Dict, Any, AsyncGenerator, List
from dataclasses import dataclass, field, asdict

logger = logging.getLogger(__name__)


@dataclass
class LearningLLMResponse:
    """Learning LLM 응답 결과"""
    answer: str
    confidence: float
    mentioned_codes: List[str] = field(default_factory=list)
    mentioned_terms: List[str] = field(default_factory=list)
    mentioned_commands: List[str] = field(default_factory=list)
    raw_response: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


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

    def _build_confidence_messages(
        self,
        question: str,
        context: Optional[str] = None
    ) -> list:
        """신뢰도 점수 포함 응답을 위한 메시지 빌드"""
        system_prompt = """You are a domain expert KMS assistant for OpenFrame/Tmax products.
Answer questions accurately based on your training knowledge.

IMPORTANT: For each answer, include a confidence score at the end in this format:
[CONFIDENCE: 0.XX]

Where 0.XX is between 0.00 (no confidence) and 1.00 (fully confident).
- Use 0.90+ only if you have exact knowledge about this topic
- Use 0.70-0.89 if you have good knowledge but some uncertainty
- Use 0.50-0.69 if you have partial knowledge
- Use below 0.50 if you are uncertain

Also tag any error codes, commands, or technical terms you mention.
Format: [CODES: -5212, -9001] [TERMS: TJES, TACF] [COMMANDS: tjesmgr, hidbmgr]"""

        messages = [{"role": "system", "content": system_prompt}]

        if context:
            user_content = f"{question}\n\n참고 컨텍스트:\n{context}"
        else:
            user_content = question

        messages.append({"role": "user", "content": user_content})
        return messages

    async def generate_with_confidence(
        self,
        question: str,
        context: Optional[str] = None,
        max_new_tokens: int = 1024,
        temperature: float = 0.3,  # 낮은 temperature로 일관된 답변
        top_p: float = 0.9,
    ) -> LearningLLMResponse:
        """
        신뢰도 점수와 함께 응답 생성

        Fine-tuned Learning LLM이 학습된 도메인 지식을 바탕으로
        답변을 생성하고 신뢰도 점수를 반환합니다.

        Args:
            question: 사용자 질문
            context: 추가 컨텍스트 (선택)
            max_new_tokens: 최대 생성 토큰
            temperature: 샘플링 온도 (낮을수록 일관성)

        Returns:
            LearningLLMResponse with answer, confidence, mentioned entities
        """
        messages = self._build_confidence_messages(question, context)

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
                        logger.error(f"vLLM confidence generation error: {resp.status} - {error_text}")
                        return LearningLLMResponse(
                            answer="",
                            confidence=0.0,
                            raw_response=error_text
                        )

                    data = await resp.json()
                    raw_answer = data["choices"][0]["message"]["content"]

                    # Parse response to extract confidence and mentions
                    return self._parse_confidence_response(raw_answer)

        except Exception as e:
            logger.error(f"vLLM confidence generation failed: {e}")
            return LearningLLMResponse(
                answer="",
                confidence=0.0,
                raw_response=str(e)
            )

    def _parse_confidence_response(self, raw_answer: str) -> LearningLLMResponse:
        """
        LLM 응답에서 신뢰도 점수와 언급된 엔티티 추출

        Expected format in response:
        - [CONFIDENCE: 0.XX]
        - [CODES: -5212, -9001]
        - [TERMS: TJES, TACF]
        - [COMMANDS: tjesmgr, hidbmgr]
        """
        answer = raw_answer
        confidence = 0.5  # 기본값

        # Extract confidence score
        confidence_match = re.search(r'\[CONFIDENCE:\s*([\d.]+)\]', raw_answer)
        if confidence_match:
            try:
                confidence = float(confidence_match.group(1))
                confidence = max(0.0, min(1.0, confidence))
                answer = re.sub(r'\[CONFIDENCE:\s*[\d.]+\]', '', answer)
            except ValueError:
                pass

        # Extract mentioned codes
        mentioned_codes = []
        codes_match = re.search(r'\[CODES?:\s*([^\]]+)\]', raw_answer, re.IGNORECASE)
        if codes_match:
            codes_str = codes_match.group(1)
            mentioned_codes = [c.strip() for c in codes_str.split(',') if c.strip()]
            answer = re.sub(r'\[CODES?:\s*[^\]]+\]', '', answer, flags=re.IGNORECASE)

        # Also extract codes from text (pattern: -XXXX or -XXXXX)
        text_codes = re.findall(r'-\d{4,5}', answer)
        mentioned_codes = list(set(mentioned_codes + text_codes))

        # Extract mentioned terms
        mentioned_terms = []
        terms_match = re.search(r'\[TERMS?:\s*([^\]]+)\]', raw_answer, re.IGNORECASE)
        if terms_match:
            terms_str = terms_match.group(1)
            mentioned_terms = [t.strip() for t in terms_str.split(',') if t.strip()]
            answer = re.sub(r'\[TERMS?:\s*[^\]]+\]', '', answer, flags=re.IGNORECASE)

        # Also extract OpenFrame terms from text
        text_terms = re.findall(
            r'\b(TJES|TACF|TSO|JCL|VSAM|COBOL|CICS|IMS|OSC|OSI|HiDB|NDB|'
            r'OpenFrame|Tmax|PSAM|KSAM|OSCOBOL|OFCOBOL)\b',
            answer, re.IGNORECASE
        )
        mentioned_terms = list(set(mentioned_terms + [t.upper() for t in text_terms]))

        # Extract mentioned commands
        mentioned_commands = []
        cmds_match = re.search(r'\[COMMANDS?:\s*([^\]]+)\]', raw_answer, re.IGNORECASE)
        if cmds_match:
            cmds_str = cmds_match.group(1)
            mentioned_commands = [c.strip() for c in cmds_str.split(',') if c.strip()]
            answer = re.sub(r'\[COMMANDS?:\s*[^\]]+\]', '', answer, flags=re.IGNORECASE)

        # Also extract common commands from text
        text_cmds = re.findall(
            r'\b(tjesmgr|hidbmgr|tacfmgr|oscmgr|tjesprpt|'
            r'BOOT|SHUTDOWN|CANCEL|SUBMIT|START|STOP|HOLD|RELEASE)\b',
            answer, re.IGNORECASE
        )
        mentioned_commands = list(set(mentioned_commands + [c.lower() for c in text_cmds]))

        # Clean up answer
        answer = answer.strip()

        # If confidence was not explicit, estimate from answer quality
        if not confidence_match:
            confidence = self._estimate_confidence(answer, mentioned_codes, mentioned_terms)

        return LearningLLMResponse(
            answer=answer,
            confidence=confidence,
            mentioned_codes=mentioned_codes,
            mentioned_terms=mentioned_terms,
            mentioned_commands=mentioned_commands,
            raw_response=raw_answer
        )

    def _estimate_confidence(
        self,
        answer: str,
        codes: List[str],
        terms: List[str]
    ) -> float:
        """
        답변 품질에 따라 신뢰도 추정

        명시적 confidence tag가 없을 때 사용
        """
        confidence = 0.5

        # 답변 길이에 따른 보정
        if len(answer) < 50:
            confidence -= 0.1  # 너무 짧은 답변
        elif len(answer) > 200:
            confidence += 0.1  # 상세한 답변

        # 구체적 에러코드 언급
        if codes:
            confidence += 0.15

        # 기술 용어 언급
        if terms:
            confidence += 0.1

        # 불확실한 표현 감지
        uncertainty_patterns = [
            r'모르겠',
            r'확실하지 않',
            r'추측',
            r'아마',
            r'maybe',
            r'not sure',
            r'I think',
            r'possibly',
        ]
        for pattern in uncertainty_patterns:
            if re.search(pattern, answer, re.IGNORECASE):
                confidence -= 0.15
                break

        # 확신 표현 감지
        certainty_patterns = [
            r'정확히',
            r'확실히',
            r'반드시',
            r'specifically',
            r'definitely',
        ]
        for pattern in certainty_patterns:
            if re.search(pattern, answer, re.IGNORECASE):
                confidence += 0.1
                break

        return max(0.0, min(1.0, confidence))

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
