"""
Learning LLM vLLM Adapter

외부 vLLM 서버에 연결하여 추론을 수행합니다.
Docker 컨테이너로 배포된 Learning LLM 서비스에 연결합니다.

Multi-LoRA v2 지원 (2026-02-03):
- GPU 5 (Port 12815): 대형 제품 8개
- GPU 6 (Port 12816): 중형 제품 8개
- GPU 7 (Port 12817): 소형 제품 8개

Usage:
    from app.api.adapters.learning_llm.vllm_adapter import get_vllm_adapter

    adapter = get_vllm_adapter()
    result = await adapter.generate_with_confidence(
        question="에러코드 -5212의 원인은?",
        context="TJES 관련 문서",
        product="tibero7"  # 제품 지정 시 해당 어댑터 사용
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


# Multi-LoRA v2 제품별 어댑터 매핑 (2026-02-04 수정)
# 24개 QLoRA v2 어댑터가 단일 vLLM 서버(Port 12815)에 로드됨
MULTI_LORA_PORT = 12815  # 모든 어댑터가 이 포트에 있음

MULTI_LORA_PRODUCT_MAPPING = {
    # =========================================================================
    # 대형 제품 (예제 수 많음)
    # =========================================================================
    "tibero7_v2": {"port": MULTI_LORA_PORT},
    "tibero7": {"port": MULTI_LORA_PORT},
    "tibero": {"port": MULTI_LORA_PORT, "adapter": "tibero7_v2"},
    "jeus_v2": {"port": MULTI_LORA_PORT},
    "jeus": {"port": MULTI_LORA_PORT},
    "tmax_v2": {"port": MULTI_LORA_PORT},
    "tmax": {"port": MULTI_LORA_PORT},
    "openframe_common_v2": {"port": MULTI_LORA_PORT},
    "openframe_common": {"port": MULTI_LORA_PORT},
    "openframe_batch_v2": {"port": MULTI_LORA_PORT},
    "openframe_batch": {"port": MULTI_LORA_PORT},
    "batch": {"port": MULTI_LORA_PORT, "adapter": "openframe_batch_v2"},
    "webtob_v2": {"port": MULTI_LORA_PORT},
    "webtob": {"port": MULTI_LORA_PORT},
    "openframe_vos3_v2": {"port": MULTI_LORA_PORT},
    "openframe_vos3": {"port": MULTI_LORA_PORT},
    "vos3": {"port": MULTI_LORA_PORT, "adapter": "openframe_vos3_v2"},
    "vos3_openframe": {"port": MULTI_LORA_PORT, "adapter": "openframe_vos3_v2"},
    "openframe_osc_v2": {"port": MULTI_LORA_PORT},
    "openframe_osc": {"port": MULTI_LORA_PORT},
    "osc": {"port": MULTI_LORA_PORT, "adapter": "openframe_osc_v2"},
    # --- ProductId 매핑 (OpenFrame RAG 라우터에서 사용) ---
    # openframe_mvs는 일반적인 OpenFrame 쿼리이므로 base 어댑터를 기본으로 사용
    # (OSC 전용 쿼리는 detect_product_from_query에서 osc/cics 키워드로 감지됨)
    "openframe_mvs_v2": {"port": MULTI_LORA_PORT, "adapter": "openframe_base_v2"},
    "openframe_mvs": {"port": MULTI_LORA_PORT, "adapter": "openframe_base_v2"},
    "mvs": {"port": MULTI_LORA_PORT, "adapter": "openframe_base_v2"},
    "msp_openframe": {"port": MULTI_LORA_PORT, "adapter": "openframe_batch_v2"},
    "msp": {"port": MULTI_LORA_PORT, "adapter": "openframe_batch_v2"},
    "xsp_openframe": {"port": MULTI_LORA_PORT, "adapter": "openframe_common_v2"},
    "xsp": {"port": MULTI_LORA_PORT, "adapter": "openframe_common_v2"},
    # =========================================================================
    # 중형 제품
    # =========================================================================
    "openframe_base_v2": {"port": MULTI_LORA_PORT},
    "openframe_base": {"port": MULTI_LORA_PORT},
    "base": {"port": MULTI_LORA_PORT, "adapter": "openframe_base_v2"},
    "ofmanager_v2": {"port": MULTI_LORA_PORT},
    "ofmanager": {"port": MULTI_LORA_PORT},
    "manager": {"port": MULTI_LORA_PORT, "adapter": "ofmanager_v2"},
    "openframe_aim_v2": {"port": MULTI_LORA_PORT},
    "openframe_aim": {"port": MULTI_LORA_PORT},
    "aim": {"port": MULTI_LORA_PORT, "adapter": "openframe_aim_v2"},
    "protrieve_v2": {"port": MULTI_LORA_PORT},
    "protrieve": {"port": MULTI_LORA_PORT},
    "openframe_osi_v2": {"port": MULTI_LORA_PORT},
    "openframe_osi": {"port": MULTI_LORA_PORT},
    "osi": {"port": MULTI_LORA_PORT, "adapter": "openframe_osi_v2"},
    "openframe_tacf_v2": {"port": MULTI_LORA_PORT},
    "openframe_tacf": {"port": MULTI_LORA_PORT},
    "tacf": {"port": MULTI_LORA_PORT, "adapter": "openframe_tacf_v2"},
    "openframe_gateway_v2": {"port": MULTI_LORA_PORT},
    "openframe_gateway": {"port": MULTI_LORA_PORT},
    "gateway": {"port": MULTI_LORA_PORT, "adapter": "openframe_gateway_v2"},
    "ofpli_v2": {"port": MULTI_LORA_PORT},
    "ofpli": {"port": MULTI_LORA_PORT},
    "pli": {"port": MULTI_LORA_PORT, "adapter": "ofpli_v2"},
    # =========================================================================
    # 소형 제품
    # =========================================================================
    "ofcobol_v2": {"port": MULTI_LORA_PORT},
    "ofcobol": {"port": MULTI_LORA_PORT},
    "cobol": {"port": MULTI_LORA_PORT, "adapter": "ofcobol_v2"},
    "prosync_v2": {"port": MULTI_LORA_PORT},
    "prosync": {"port": MULTI_LORA_PORT},
    "openframe_ndb_v2": {"port": MULTI_LORA_PORT},
    "openframe_ndb": {"port": MULTI_LORA_PORT},
    "ndb": {"port": MULTI_LORA_PORT, "adapter": "openframe_ndb_v2"},
    "ofstudio_v2": {"port": MULTI_LORA_PORT},
    "ofstudio": {"port": MULTI_LORA_PORT},
    "studio": {"port": MULTI_LORA_PORT, "adapter": "ofstudio_v2"},
    "ofminer_v2": {"port": MULTI_LORA_PORT},
    "ofminer": {"port": MULTI_LORA_PORT},
    "miner": {"port": MULTI_LORA_PORT, "adapter": "ofminer_v2"},
    "prosort_v2": {"port": MULTI_LORA_PORT},
    "prosort": {"port": MULTI_LORA_PORT},
    "sort": {"port": MULTI_LORA_PORT, "adapter": "prosort_v2"},
    "openframe_hidb_v2": {"port": MULTI_LORA_PORT},
    "openframe_hidb": {"port": MULTI_LORA_PORT},
    "hidb": {"port": MULTI_LORA_PORT, "adapter": "openframe_hidb_v2"},
    "ofasm_v2": {"port": MULTI_LORA_PORT},
    "ofasm": {"port": MULTI_LORA_PORT},
    "asm": {"port": MULTI_LORA_PORT, "adapter": "ofasm_v2"},
    # =========================================================================
    # 동적 product_id (Agentic RAG ManualRegistry에서 사용)
    # =========================================================================
    "mvs_openframe_7.1": {"port": MULTI_LORA_PORT, "adapter": "openframe_base_v2"},
    "msp_openframe_7.3": {"port": MULTI_LORA_PORT, "adapter": "openframe_batch_v2"},
    "vos3_openframe_2.0": {"port": MULTI_LORA_PORT, "adapter": "openframe_vos3_v2"},
    "xsp_openframe_7.3": {"port": MULTI_LORA_PORT, "adapter": "openframe_common_v2"},
    "tibero_7fixset01": {"port": MULTI_LORA_PORT, "adapter": "tibero7_v2"},
    "tmax_6.0": {"port": MULTI_LORA_PORT, "adapter": "tmax_v2"},
    "ofasm_4": {"port": MULTI_LORA_PORT, "adapter": "ofasm_v2"},
    "ofcobol_4": {"port": MULTI_LORA_PORT, "adapter": "ofcobol_v2"},
    "jeus_8.5": {"port": MULTI_LORA_PORT, "adapter": "jeus_v2"},
    "jeus_8": {"port": MULTI_LORA_PORT, "adapter": "jeus_v2"},
    "webtob_5.0": {"port": MULTI_LORA_PORT, "adapter": "webtob_v2"},
    "protrieve_7": {"port": MULTI_LORA_PORT, "adapter": "protrieve_v2"},
    "ofstudio_7": {"port": MULTI_LORA_PORT, "adapter": "ofstudio_v2"},
    "ofmanager_7": {"port": MULTI_LORA_PORT, "adapter": "ofmanager_v2"},
    "openframe_aim_7": {"port": MULTI_LORA_PORT, "adapter": "openframe_aim_v2"},
    "openframe_tacf_7": {"port": MULTI_LORA_PORT, "adapter": "openframe_tacf_v2"},
    "openframe_hidb_7": {"port": MULTI_LORA_PORT, "adapter": "openframe_hidb_v2"},
    "openframe_ndb_7": {"port": MULTI_LORA_PORT, "adapter": "openframe_ndb_v2"},
    "openframe_osi_7": {"port": MULTI_LORA_PORT, "adapter": "openframe_osi_v2"},
}

# 단일 vLLM 서버 URL (모든 24개 어댑터가 12815에 로드됨)
MULTI_LORA_BASE_URL = os.getenv("MULTI_LORA_URL", "http://192.168.8.11:12815/v1")


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

    Multi-LoRA v2 지원 (2026-02-03):
    - 제품별로 적절한 GPU/포트로 자동 라우팅
    - tibero7_v2, jeus_v2 등 어댑터 이름 직접 지정 가능
    """

    def __init__(
        self,
        base_url: Optional[str] = None,
        model: str = "Qwen/Qwen2.5-7B-Instruct",
        timeout: int = 60,
    ):
        self.base_url = base_url or os.getenv(
            "LEARNING_LLM_URL",
            "http://192.168.8.11:12815/v1"  # 기본: GPU 5
        )
        self.model = model
        self.timeout = timeout
        self.is_loaded = False
        self.current_adapter = "vllm-server"
        self._remote_host = os.getenv("REMOTE_HOST", "192.168.8.11")

    def get_url_for_product(self, product: Optional[str] = None) -> tuple[str, str]:
        """
        제품에 맞는 URL과 모델명 반환

        모든 24개 어댑터가 단일 vLLM 서버(Port 12815)에 로드되어 있음.

        Args:
            product: 제품명 (예: "tibero7", "jeus", "openframe_base")

        Returns:
            (base_url, model_name) 튜플
        """
        # 단일 vLLM 서버 URL 사용
        base_url = MULTI_LORA_BASE_URL

        if not product:
            return base_url, self.model

        product_lower = product.lower().strip()

        # 제품명 매핑 확인
        if product_lower in MULTI_LORA_PRODUCT_MAPPING:
            mapping = MULTI_LORA_PRODUCT_MAPPING[product_lower]

            # adapter 필드가 있으면 그것을 사용 (openframe_mvs -> openframe_osc_v2)
            if "adapter" in mapping:
                model_name = mapping["adapter"]
            # 모델명 결정 (v2 suffix 추가)
            elif not product_lower.endswith("_v2"):
                model_name = f"{product_lower}_v2"
            else:
                model_name = product_lower

            logger.info(f"Multi-LoRA routing: {product} -> {base_url} (adapter: {model_name})")
            return base_url, model_name

        # 매핑에 없으면 기본 어댑터 사용 (Base는 일반적인 OpenFrame 문서를 다룸)
        logger.warning(f"Unknown product '{product}', using default adapter: openframe_base_v2")
        return base_url, "openframe_base_v2"

    def detect_product_from_query(self, query: str) -> Optional[str]:
        """
        질문에서 제품명 감지

        Args:
            query: 사용자 질문

        Returns:
            감지된 제품명 또는 None
        """
        query_lower = query.lower()

        # 제품명 패턴 매칭 (우선순위 순)
        # 참고: re.ASCII 플래그를 사용하여 \b가 일본어/한국어 문자에서도
        # 올바르게 단어 경계를 인식하도록 함 (Unicode 기본값 문제 해결)
        product_patterns = [
            (r'\btibero\b', 'tibero7'),
            (r'\bjeus\b', 'jeus'),
            (r'\btmax\s*(tp)?\b', 'tmax'),
            (r'\bwebtob\b', 'webtob'),
            (r'\bosc\b|\bcics\b', 'openframe_osc'),
            (r'\bvos3\b', 'openframe_vos3'),
            (r'\bbatch\b', 'openframe_batch'),
            (r'\bbase\b', 'openframe_base'),
            (r'\bofmanager\b', 'ofmanager'),
            (r'\baim\b', 'openframe_aim'),
            (r'\bprotrieve\b', 'protrieve'),
            (r'\bosi\b', 'openframe_osi'),
            (r'\btacf\b', 'openframe_tacf'),
            (r'\bgateway\b', 'openframe_gateway'),
            (r'\bpli\b|\bofpli\b', 'ofpli'),
            (r'\bcobol\b|\bofcobol\b', 'ofcobol'),
            (r'\bprosync\b', 'prosync'),
            (r'\bndb\b', 'openframe_ndb'),
            (r'\bstudio\b|\bofstudio\b', 'ofstudio'),
            (r'\bminer\b|\bofminer\b', 'ofminer'),
            (r'\bprosort\b|\bsort\b', 'prosort'),
            (r'\bhidb\b', 'openframe_hidb'),
            (r'\basm\b|\bofasm\b', 'ofasm'),
        ]

        for pattern, product in product_patterns:
            # re.ASCII 플래그로 일본어/한국어 문자 다음에도 단어 경계 인식
            if re.search(pattern, query_lower, re.ASCII):
                logger.debug(f"detect_product_from_query: '{pattern}' matched -> {product}")
                return product

        return None

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
        product: Optional[str] = None,  # Multi-LoRA 제품 지정
        **kwargs
    ) -> str:
        """
        vLLM 서버를 통한 응답 생성 (Multi-LoRA v2 지원)

        Args:
            question: 사용자 질문
            context: 추가 컨텍스트
            max_new_tokens: 최대 생성 토큰
            temperature: 샘플링 온도
            product: Multi-LoRA 제품명 (예: "tibero7", "jeus")

        Returns:
            생성된 응답
        """
        # 쿼리 기반 제품 감지를 항상 먼저 시도 (더 정확한 어댑터 선택)
        detected_product = self.detect_product_from_query(question)
        if detected_product:
            product = detected_product
            logger.info(f"Query-based product detection: '{detected_product}' from query")
        elif not product:
            product = None  # 기본 어댑터 사용

        # Multi-LoRA 라우팅
        base_url, model_name = self.get_url_for_product(product)

        # lora-api-server-v3 API 형식 (v2 suffix 제거)
        adapter_name = model_name.replace("_v2", "")

        # context를 message에 통합 (lora-api-server-v3는 context 필드 미지원)
        if context:
            message = f"以下の参考資料に基づいて質問に回答してください。\n\n{context}\n\n質問: {question}"
        else:
            message = question

        # lora-api-server-v3 API: /chat endpoint with {adapter, message, max_tokens, temperature}
        payload = {
            "adapter": adapter_name,
            "message": message,
            "max_tokens": max_new_tokens,
            "temperature": temperature,
        }

        try:
            # /v1 prefix 제거하고 /chat 엔드포인트 사용
            chat_url = base_url.replace("/v1", "") + "/chat"

            async with aiohttp.ClientSession() as session:
                async with session.post(
                    chat_url,
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=self.timeout)
                ) as resp:
                    if resp.status != 200:
                        error_text = await resp.text()
                        logger.error(f"vLLM error: {resp.status} - {error_text}")
                        return ""

                    data = await resp.json()
                    # lora-api-server-v3 응답 형식: {"adapter", "response", "tokens_generated", "accuracy"}
                    return data.get("response", "")

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
        product: Optional[str] = None,  # Multi-LoRA 제품 지정
    ) -> AsyncGenerator[str, None]:
        """
        스트리밍 응답 생성 (Multi-LoRA v2 지원)

        lora-api-server-v3는 스트리밍을 지원하지 않으므로,
        전체 응답을 받아서 한 번에 yield합니다.

        Args:
            question: 사용자 질문
            context: 추가 컨텍스트
            max_new_tokens: 최대 생성 토큰
            temperature: 샘플링 온도
            product: Multi-LoRA 제품명 (예: "tibero7", "openframe_osc")
        """
        # 쿼리 기반 제품 감지를 항상 먼저 시도 (더 정확한 어댑터 선택)
        detected_product = self.detect_product_from_query(question)
        if detected_product:
            product = detected_product
            logger.info(f"Query-based product detection: '{detected_product}' from query")
        elif not product:
            product = None  # 기본 어댑터 사용

        # Multi-LoRA 라우팅
        base_url, model_name = self.get_url_for_product(product)

        # lora-api-server-v3 API 형식 (v2 suffix 제거)
        adapter_name = model_name.replace("_v2", "")

        # context를 message에 통합 (lora-api-server-v3는 context 필드 미지원)
        if context:
            message = f"以下の参考資料に基づいて質問に回答してください。\n\n{context}\n\n質問: {question}"
        else:
            message = question

        logger.info(f"generate_stream: product={product}, adapter={adapter_name}, context_len={len(context) if context else 0}")

        # lora-api-server-v3 API: /chat endpoint (스트리밍 미지원, 전체 응답 반환)
        payload = {
            "adapter": adapter_name,
            "message": message,
            "max_tokens": max_new_tokens,
            "temperature": temperature,
        }

        try:
            # /v1 prefix 제거하고 /chat 엔드포인트 사용
            chat_url = base_url.replace("/v1", "") + "/chat"

            async with aiohttp.ClientSession() as session:
                async with session.post(
                    chat_url,
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=self.timeout)
                ) as resp:
                    if resp.status != 200:
                        error_text = await resp.text()
                        logger.error(f"vLLM stream error: {resp.status} - {error_text}")
                        return

                    data = await resp.json()
                    # lora-api-server-v3 응답 형식: {"adapter", "response", "tokens_generated", "accuracy"}
                    response = data.get("response", "")
                    if response:
                        # 전체 응답을 한 번에 yield (스트리밍 미지원)
                        yield response
                        logger.info(f"Non-streaming response from {chat_url}, yielded {len(response)} chars")

        except Exception as e:
            logger.error(f"vLLM streaming failed: {e}")

    def _build_messages(
        self,
        question: str,
        context: Optional[str] = None,
        product: Optional[str] = None
    ) -> list:
        """
        OpenAI 형식 메시지 빌드 (학습 데이터 형식 준수)

        학습 데이터 형식과 정확히 일치하게 프롬프트를 구성합니다:
        - system: "あなたはOpenFrame KMSのアシスタントです。技術的な質問に正確に回答してください。"
        - user: "XXXとは何ですか？"

        중요: context는 무시합니다 (모델이 학습 시 context 없이 학습됨)
        """
        # 학습 데이터와 동일한 시스템 프롬프트
        system_prompt = "あなたはOpenFrame KMSのアシスタントです。技術的な質問に正確に回答してください。"

        messages = [
            {
                "role": "system",
                "content": system_prompt
            }
        ]

        # 질문을 학습 데이터 형식에 맞게 정규화
        user_content = question.strip()

        # 이미 "とは何ですか" 형식인지 확인
        if "とは何ですか" not in user_content:
            user_content = f"{user_content}とは何ですか？"

        messages.append({
            "role": "user",
            "content": user_content
        })

        logger.debug(f"_build_messages: '{question[:30]}...' -> '{user_content[:50]}...'")

        return messages

    def _extract_core_content(self, context: str) -> str:
        """컨텍스트에서 메타데이터를 제거하고 핵심 내용 추출"""
        if not context:
            return ""

        lines = []
        for line in context.split('\n'):
            line = line.strip()
            # 메타데이터 라인 제거
            if line.startswith('[Document:') or line.startswith('[Cross-Product:'):
                continue
            if line.startswith('[Entity:'):
                continue
            if '**製品/Product**' in line or '**出典/Source**' in line:
                continue
            if line:
                lines.append(line)

        return '\n'.join(lines[:20])  # 최대 20줄

    def _get_product_display_name(self, product: str) -> str:
        """제품 ID를 표시 이름으로 변환"""
        product_names = {
            "openframe_base": "OpenFrame/Base",
            "openframe_mvs": "OpenFrame/Base",
            "openframe_osc": "OpenFrame/OSC",
            "openframe_batch": "OpenFrame/Batch",
            "openframe_vos3": "OpenFrame/VOS3",
            "openframe_tacf": "OpenFrame/TACF",
            "openframe_aim": "OpenFrame/AIM",
            "openframe_hidb": "OpenFrame/HiDB",
            "openframe_ndb": "OpenFrame/NDB",
            "openframe_osi": "OpenFrame/OSI",
            "openframe_gateway": "OpenFrame/Gateway",
            "tibero7": "Tibero",
            "tibero": "Tibero",
            "jeus": "JEUS",
            "tmax": "Tmax",
            "webtob": "WebtoB",
            "ofcobol": "OFCOBOL",
            "ofasm": "OFASM",
            "ofpli": "OFPLI",
            "ofstudio": "OFStudio",
            "ofminer": "OFMiner",
            "ofmanager": "OFManager",
            "prosort": "ProSort",
            "prosync": "ProSync",
            "protrieve": "ProTrieve",
        }
        return product_names.get(product.lower(), product)

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
        product: Optional[str] = None,  # Multi-LoRA 제품 지정
    ) -> LearningLLMResponse:
        """
        신뢰도 점수와 함께 응답 생성 (Multi-LoRA v2 지원)

        Fine-tuned Learning LLM이 학습된 도메인 지식을 바탕으로
        답변을 생성하고 신뢰도 점수를 반환합니다.

        Args:
            question: 사용자 질문
            context: 추가 컨텍스트 (선택)
            max_new_tokens: 최대 생성 토큰
            temperature: 샘플링 온도 (낮을수록 일관성)
            product: Multi-LoRA 제품명 (예: "tibero7", "jeus", "openframe_base")
                     지정하지 않으면 질문에서 자동 감지 시도

        Returns:
            LearningLLMResponse with answer, confidence, mentioned entities
        """
        # 쿼리 기반 제품 감지를 항상 먼저 시도 (더 정확한 어댑터 선택)
        detected_product = self.detect_product_from_query(question)
        if detected_product:
            product = detected_product
            logger.info(f"Query-based product detection: '{detected_product}' from query")
        elif not product:
            product = None  # 기본 어댑터 사용

        # Multi-LoRA 라우팅
        base_url, model_name = self.get_url_for_product(product)

        # lora-api-server-v3 API 형식 (v2 suffix 제거)
        adapter_name = model_name.replace("_v2", "")

        # lora-api-server-v3 API: /chat endpoint
        payload = {
            "adapter": adapter_name,
            "message": question,
            "max_tokens": max_new_tokens,
            "temperature": temperature,
        }

        try:
            # /v1 prefix 제거하고 /chat 엔드포인트 사용
            chat_url = base_url.replace("/v1", "") + "/chat"

            async with aiohttp.ClientSession() as session:
                async with session.post(
                    chat_url,
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
                    # lora-api-server-v3 응답 형식
                    raw_answer = data.get("response", "")
                    server_accuracy = data.get("accuracy", 0.0) / 100.0  # 0-100 -> 0-1

                    # Parse response to extract confidence and mentions
                    response = self._parse_confidence_response(raw_answer)

                    # 서버에서 반환한 accuracy를 confidence로 사용
                    if server_accuracy > 0:
                        response.confidence = server_accuracy

                    # 사용된 어댑터 정보 추가
                    if product:
                        logger.info(f"Multi-LoRA response from {adapter_name} via {chat_url}, accuracy={server_accuracy:.2f}")

                    return response

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
        """상태 반환 (Multi-LoRA v2 정보 포함)"""
        return {
            "type": "vllm",
            "is_loaded": self.is_loaded,
            "base_url": MULTI_LORA_BASE_URL,
            "model": self.model,
            "current_adapter": self.current_adapter,
            "multi_lora_v2": {
                "enabled": True,
                "server_url": MULTI_LORA_BASE_URL,
                "adapters": [
                    "tibero7_v2", "jeus_v2", "tmax_v2", "openframe_common_v2",
                    "openframe_batch_v2", "webtob_v2", "openframe_vos3_v2", "openframe_osc_v2",
                    "openframe_base_v2", "ofmanager_v2", "openframe_aim_v2", "protrieve_v2",
                    "openframe_osi_v2", "openframe_tacf_v2", "openframe_gateway_v2", "ofpli_v2",
                    "ofcobol_v2", "prosync_v2", "openframe_ndb_v2", "ofstudio_v2",
                    "ofminer_v2", "prosort_v2", "openframe_hidb_v2", "ofasm_v2",
                ],
                "total_adapters": 24,
            },
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
