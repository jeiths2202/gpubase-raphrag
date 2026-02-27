"""
TRT-LLM NIM Adapter for OpenFrame RAG

NVIDIA TRT-LLM NIM 컨테이너 기반 OpenFrame 8제품 전용 LLM 어댑터.
OpenAI 호환 API를 통해 추론을 수행합니다.

Usage:
    from app.api.adapters.openframe_llm import get_trtllm_adapter

    adapter = get_trtllm_adapter()
    result = await adapter.generate(
        question="tjesmgr BOOT 명령어 설명해줘",
        context="TJES 관련 문서",
        product="openframe_mvs"
    )
"""
import os
import re
import json
import logging
import aiohttp
from typing import Optional, Dict, Any, AsyncGenerator, List
from dataclasses import dataclass, field, asdict

logger = logging.getLogger(__name__)


# =============================================================================
# Product-specific System Prompts
# =============================================================================

PRODUCT_SYSTEM_PROMPTS = {
    "openframe_mvs": """You are an expert on OpenFrame MVS (Mainframe Virtual System).
You have deep knowledge of:
- TJES (Tmax Job Entry Subsystem): tjesmgr, job management, JCL processing
- TACF (Tmax Access Control Facility): tacfmgr, security, user management
- OSC (Online System for CICS): oscmgr, transaction management
- MVS utilities: IDCAMS, IEBGENER, IEBCOPY, DFSORT
- System commands: tmboot, tmdown, ofboot, ofdown, jesinit, jesdown
- Error codes and troubleshooting

Always provide accurate, technical responses based on OpenFrame documentation.""",

    "msp_openframe": """You are an expert on MSP OpenFrame.
You have deep knowledge of MSP-specific features including JES2, JES3, SMS, HSM, DFHSM.
Provide accurate technical guidance for MSP migration and operations.""",

    "vos3_openframe": """You are an expert on VOS3 OpenFrame.
You have deep knowledge of VOS3-specific features for NEC ACOS compatibility.
Provide accurate technical guidance for VOS3 migration and operations.""",

    "tibero7": """You are an expert on Tibero 7 database.
You have deep knowledge of:
- Tibero SQL and administration: tbsql, tbcli, tbadmin
- Data migration: tbexport, tbimport, tbloader
- Oracle compatibility features
- SQL optimization and tuning
- TAC (Tibero Active Cluster), TAF

Provide accurate database administration and SQL guidance.""",

    "ofasm": """You are an expert on OFASM (OpenFrame Assembler).
You have deep knowledge of:
- HLASM compatible assembler
- CSECT, DSECT, USING, BALR instructions
- Macro processing
- Migration from mainframe assembler

Provide accurate assembler programming guidance.""",

    "ofcobol": """You are an expert on OFCOBOL (OpenFrame COBOL).
You have deep knowledge of:
- COBOL compilation: ofcobol, cobc, cobrun
- COPYBOOK management
- WORKING-STORAGE, PROCEDURE DIVISION
- File handling (VSAM, sequential)
- Migration from mainframe COBOL

Provide accurate COBOL programming guidance.""",

    "xsp_openframe": """You are an expert on XSP OpenFrame.
You have deep knowledge of XSP transaction processing and online system features.
Provide accurate technical guidance for XSP migration and operations.""",

    "tmax": """You are an expert on Tmax middleware.
You have deep knowledge of:
- Tmax server configuration: domain, svrgroup, server
- API functions: tpacall, tpcall, tpreturn
- Configuration files and ULOG
- GW/Domain management

Provide accurate Tmax middleware guidance.""",
}

DEFAULT_SYSTEM_PROMPT = """You are an expert on OpenFrame and Tmax products.
Provide accurate technical responses based on your training knowledge.
If you're unsure about something, clearly indicate that."""


# =============================================================================
# Product ID to TRT-LLM Model Name Mapping
# =============================================================================

PRODUCT_TO_MODEL_MAP = {
    "openframe_mvs": "openframe-mvs",
    "msp_openframe": "msp-openframe",
    "vos3_openframe": "vos3-openframe",
    "tibero7": "tibero7",
    "ofasm": "ofasm",
    "ofcobol": "ofcobol",
    "xsp_openframe": "xsp-openframe",
    "tmax": "tmax",
}


@dataclass
class TRTLLMResponse:
    """TRT-LLM 응답 결과"""
    answer: str
    confidence: float
    product: str
    model: str = "trtllm-nim"  # 실제 사용된 모델명 (예: openframe-mvs)
    mentioned_codes: List[str] = field(default_factory=list)
    mentioned_terms: List[str] = field(default_factory=list)
    mentioned_commands: List[str] = field(default_factory=list)
    raw_response: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class TRTLLMAdapter:
    """
    TRT-LLM NIM 연결 어댑터

    NVIDIA TRT-LLM NIM 컨테이너의 OpenAI 호환 API를 통해 연결합니다.
    OpenFrame 8개 제품에 특화된 시스템 프롬프트를 사용합니다.
    """

    def __init__(
        self,
        base_url: Optional[str] = None,
        model: str = "ensemble",  # TRT-LLM ensemble model
        timeout: int = 120,
    ):
        self.base_url = base_url or os.getenv(
            "TRTLLM_NIM_URL",
            "http://192.168.8.11:12820/v1"
        )
        self.model = model
        self.timeout = timeout
        self.is_loaded = False
        self.current_adapter = "trtllm-nim"
        self._available_models: List[str] = []

    async def health_check(self) -> Dict[str, Any]:
        """TRT-LLM NIM 서버 헬스 체크"""
        try:
            # Try /health endpoint first
            health_url = self.base_url.replace("/v1", "/health")
            async with aiohttp.ClientSession() as session:
                async with session.get(health_url, timeout=10) as resp:
                    if resp.status == 200:
                        self.is_loaded = True
                        return {"status": "healthy", "url": self.base_url}
        except Exception as e:
            logger.debug(f"TRT-LLM health endpoint failed: {e}")

        # Try /v1/models as fallback
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(f"{self.base_url}/models", timeout=10) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        self._available_models = [
                            m.get("id", "unknown") for m in data.get("data", [])
                        ]
                        self.is_loaded = True
                        return {
                            "status": "healthy",
                            "url": self.base_url,
                            "models": self._available_models
                        }
        except Exception as e:
            logger.error(f"TRT-LLM health check failed: {e}")

        self.is_loaded = False
        return {"status": "unhealthy", "url": self.base_url}

    async def load(self) -> bool:
        """연결 확인"""
        result = await self.health_check()
        return result.get("status") == "healthy"

    async def unload(self):
        """연결 해제"""
        self.is_loaded = False

    def _get_system_prompt(self, product: Optional[str] = None) -> str:
        """제품별 시스템 프롬프트 반환"""
        if product and product in PRODUCT_SYSTEM_PROMPTS:
            return PRODUCT_SYSTEM_PROMPTS[product]
        return DEFAULT_SYSTEM_PROMPT

    def _build_messages(
        self,
        question: str,
        context: Optional[str] = None,
        product: Optional[str] = None,
        language: str = "ja",
    ) -> List[Dict[str, str]]:
        """OpenAI 형식 메시지 빌드"""
        system_prompt = self._get_system_prompt(product)

        # Add language instruction
        if language == "ja":
            system_prompt += "\n\nIMPORTANT: Always respond in Japanese (日本語で回答してください)."
        elif language == "ko":
            system_prompt += "\n\nIMPORTANT: Always respond in Korean (한국어로 답변해주세요)."
        else:
            system_prompt += "\n\nIMPORTANT: Always respond in English."

        messages = [{"role": "system", "content": system_prompt}]

        # Build user message with context
        if context:
            user_content = f"{question}\n\n参考情報:\n{context}"
        else:
            user_content = question

        messages.append({"role": "user", "content": user_content})

        return messages

    def _get_model_name(self, product: Optional[str] = None) -> str:
        """
        제품 ID를 TRT-LLM 모델명으로 변환

        Args:
            product: 제품 ID (openframe_mvs, tibero7 등)

        Returns:
            TRT-LLM 모델명 (openframe-mvs, tibero7 등)
        """
        if product and product in PRODUCT_TO_MODEL_MAP:
            return PRODUCT_TO_MODEL_MAP[product]
        return self.model  # 기본 모델 (ensemble)

    async def generate(
        self,
        question: str,
        context: Optional[str] = None,
        product: Optional[str] = None,
        language: str = "ja",
        max_tokens: int = 1024,
        temperature: float = 0.7,
        top_p: float = 0.9,
        **kwargs
    ) -> str:
        """
        TRT-LLM NIM을 통한 응답 생성

        Args:
            question: 사용자 질문
            context: 추가 컨텍스트
            product: 제품 ID (시스템 프롬프트 선택용)
            language: 응답 언어 (ja, ko, en)
            max_tokens: 최대 생성 토큰
            temperature: 샘플링 온도

        Returns:
            생성된 응답
        """
        messages = self._build_messages(question, context, product, language)

        # 제품별 모델 선택
        model_name = self._get_model_name(product)

        payload = {
            "model": model_name,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "top_p": top_p,
        }

        logger.info(f"TRT-LLM NIM request: model={model_name}, product={product}")

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.base_url}/chat/completions",
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=self.timeout)
                ) as resp:
                    if resp.status != 200:
                        error_text = await resp.text()
                        logger.error(f"TRT-LLM error: {resp.status} - {error_text}")
                        return ""

                    data = await resp.json()
                    return data["choices"][0]["message"]["content"]

        except Exception as e:
            logger.error(f"TRT-LLM generation failed: {e}")
            return ""

    async def generate_stream(
        self,
        question: str,
        context: Optional[str] = None,
        product: Optional[str] = None,
        language: str = "ja",
        max_tokens: int = 1024,
        temperature: float = 0.7,
        top_p: float = 0.9,
    ) -> AsyncGenerator[str, None]:
        """스트리밍 응답 생성"""
        messages = self._build_messages(question, context, product, language)

        # 제품별 모델 선택
        model_name = self._get_model_name(product)

        payload = {
            "model": model_name,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "top_p": top_p,
            "stream": True,
        }

        logger.info(f"TRT-LLM NIM streaming: model={model_name}, product={product}")

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.base_url}/chat/completions",
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=self.timeout)
                ) as resp:
                    if resp.status != 200:
                        error_text = await resp.text()
                        logger.error(f"TRT-LLM streaming error: {resp.status} - {error_text}")
                        return

                    async for line in resp.content:
                        line = line.decode("utf-8").strip()
                        if line.startswith("data: "):
                            data_str = line[6:]
                            if data_str == "[DONE]":
                                break
                            try:
                                data = json.loads(data_str)
                                delta = data["choices"][0].get("delta", {})
                                if "content" in delta:
                                    yield delta["content"]
                            except json.JSONDecodeError:
                                continue

        except Exception as e:
            logger.error(f"TRT-LLM streaming failed: {e}")

    async def generate_with_metadata(
        self,
        question: str,
        context: Optional[str] = None,
        product: Optional[str] = None,
        language: str = "ja",
        max_tokens: int = 1024,
        temperature: float = 0.5,
    ) -> TRTLLMResponse:
        """
        메타데이터와 함께 응답 생성

        응답에서 에러코드, 명령어, 용어를 추출합니다.
        """
        # Get actual model name used for this request
        model_name = self._get_model_name(product)

        answer = await self.generate(
            question=question,
            context=context,
            product=product,
            language=language,
            max_tokens=max_tokens,
            temperature=temperature,
        )

        if not answer:
            return TRTLLMResponse(
                answer="",
                confidence=0.0,
                product=product or "unknown",
                model=model_name,
            )

        # Extract metadata from answer
        return self._parse_response(answer, product, model_name)

    def _parse_response(self, answer: str, product: Optional[str] = None, model: Optional[str] = None) -> TRTLLMResponse:
        """응답에서 메타데이터 추출"""
        # Extract error codes (pattern: -XXXX or -XXXXX)
        mentioned_codes = list(set(re.findall(r'-\d{4,5}', answer)))

        # Extract OpenFrame terms
        text_terms = re.findall(
            r'\b(TJES|TACF|TSO|JCL|VSAM|COBOL|CICS|IMS|OSC|OSI|HiDB|NDB|'
            r'OpenFrame|Tmax|PSAM|KSAM|OSCOBOL|OFCOBOL|OFASM|MSP|VOS3|Tibero)\b',
            answer, re.IGNORECASE
        )
        mentioned_terms = list(set([t.upper() for t in text_terms]))

        # Extract commands
        text_cmds = re.findall(
            r'\b(tjesmgr|hidbmgr|tacfmgr|oscmgr|osimgr|ndbmgr|volmgr|catmgr|'
            r'tjesprpt|tbsql|tbcli|tbadmin|tbexport|tbimport|'
            r'ofcobol|ofasm|cobc|cobrun|'
            r'idcams|iebgener|iebcopy|dfsort|'
            r'tmboot|tmdown|ofboot|ofdown|jesinit|jesdown|'
            r'BOOT|SHUTDOWN|CANCEL|SUBMIT|START|STOP|HOLD|RELEASE)\b',
            answer, re.IGNORECASE
        )
        mentioned_commands = list(set([c.lower() for c in text_cmds]))

        # Estimate confidence based on answer quality
        confidence = self._estimate_confidence(answer, mentioned_codes, mentioned_terms)

        return TRTLLMResponse(
            answer=answer,
            confidence=confidence,
            product=product or "unknown",
            model=model or self.model,
            mentioned_codes=mentioned_codes,
            mentioned_terms=mentioned_terms,
            mentioned_commands=mentioned_commands,
            raw_response=answer,
        )

    def _estimate_confidence(
        self,
        answer: str,
        codes: List[str],
        terms: List[str]
    ) -> float:
        """답변 품질에 따라 신뢰도 추정"""
        confidence = 0.6  # TRT-LLM NIM은 기본 신뢰도 높음

        # 답변 길이에 따른 보정
        if len(answer) < 50:
            confidence -= 0.1
        elif len(answer) > 300:
            confidence += 0.1

        # 구체적 에러코드 언급
        if codes:
            confidence += 0.1

        # 기술 용어 언급
        if len(terms) >= 2:
            confidence += 0.1

        # 불확실한 표현 감지
        uncertainty_patterns = [
            r'わかりません', r'不明', r'確認できません',
            r'모르겠', r'확실하지 않',
            r'not sure', r'I think', r'maybe',
        ]
        for pattern in uncertainty_patterns:
            if re.search(pattern, answer, re.IGNORECASE):
                confidence -= 0.15
                break

        return max(0.0, min(1.0, confidence))

    def get_status(self) -> Dict[str, Any]:
        """상태 반환"""
        return {
            "type": "trtllm-nim",
            "is_loaded": self.is_loaded,
            "base_url": self.base_url,
            "model": self.model,
            "available_models": self._available_models,
            "supported_products": list(PRODUCT_SYSTEM_PROMPTS.keys()),
        }


# =============================================================================
# Singleton Instance
# =============================================================================

_trtllm_adapter: Optional[TRTLLMAdapter] = None


def get_trtllm_adapter() -> Optional[TRTLLMAdapter]:
    """Get TRT-LLM adapter singleton"""
    global _trtllm_adapter
    return _trtllm_adapter


async def initialize_trtllm_adapter(
    base_url: Optional[str] = None,
    model: str = "ensemble",
) -> TRTLLMAdapter:
    """Initialize TRT-LLM adapter"""
    global _trtllm_adapter

    _trtllm_adapter = TRTLLMAdapter(base_url=base_url, model=model)
    await _trtllm_adapter.load()

    logger.info(f"TRT-LLM NIM adapter initialized: {_trtllm_adapter.base_url}")
    return _trtllm_adapter
