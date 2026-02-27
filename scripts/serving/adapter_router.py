#!/usr/bin/env python3
"""
Multi-LoRA Adapter Router.

Dynamic adapter routing for 22 TmaxSoft product LoRA adapters.
Supports:
- Keyword-based product routing
- Adapter hot-swap with GPU memory optimization
- Health checks & latency metrics
- Per-product isolation
- Governance gate integration (block unapproved adapters)

Architecture:
    Base Model (shared, 4-bit quantized)
        ↓
    Product Router (keyword matching)
        ↓
    LoRA Adapter (per-product, ~8MB each)
        ↓
    Response Generation

Usage:
    from scripts.serving.adapter_router import AdapterRouter
    router = AdapterRouter(base_model_name, adapter_base_dir)
    router.load_adapter("jeus_v2")
    response = router.generate("jeus_v2", prompt)
"""

import re
import time
import json
import logging
from dataclasses import dataclass, asdict, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Set

from scripts.governance.governance_config import PRODUCT_REGISTRY, ALL_PRODUCT_IDS

logger = logging.getLogger(__name__)


@dataclass
class AdapterInfo:
    """어댑터 메타데이터."""
    product_id: str
    name: str
    category: str
    language: str
    adapter_path: str
    is_loaded: bool = False
    is_approved: bool = True
    load_time_ms: float = 0.0
    last_used: Optional[str] = None
    total_requests: int = 0
    avg_latency_ms: float = 0.0
    error_count: int = 0

    def to_dict(self) -> Dict:
        return asdict(self)


@dataclass
class RoutingResult:
    """라우팅 결과."""
    product_id: str
    confidence: float
    matched_keywords: List[str]
    fallback: bool = False

    def to_dict(self) -> Dict:
        return asdict(self)


@dataclass
class GenerationResult:
    """생성 결과 (메트릭 포함)."""
    product_id: str
    response: str
    latency_ms: float
    tokens_generated: int
    adapter_loaded: bool

    def to_dict(self) -> Dict:
        return asdict(self)


@dataclass
class HealthCheckResult:
    """어댑터 헬스체크 결과."""
    product_id: str
    healthy: bool
    adapter_loaded: bool
    is_approved: bool
    avg_latency_ms: float
    error_rate: float
    last_used: Optional[str]
    issues: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict:
        return asdict(self)


class AdapterRouter:
    """Multi-LoRA 동적 어댑터 라우터."""

    # 제품별 키워드 매핑 (라우팅용)
    PRODUCT_KEYWORDS: Dict[str, List[str]] = {
        "jeus_v2": ["jeus", "was", "웹로직", "서블릿", "servlet", "jsp", "웹엔진", "webengine"],
        "tibero7_v2": ["tibero", "티베로", "tbrmgr", "tbi", "tsql", "database", "데이터베이스"],
        "ofpli_v2": ["pli", "pl/i", "ofpli", "plimake"],
        "openframe_aim_v2": ["aim", "openframe aim", "aimmgr"],
        "prosync_v2": ["prosync", "동기화", "프로싱크"],
        "protrieve_v2": ["protrieve", "프로트리브"],
        "openframe_hidb_v2": ["hidb", "hidbmgr", "계층형", "hierarchical"],
        "openframe_tacf_v2": ["tacf", "tacfmgr", "보안", "인증", "security"],
        "openframe_vos3_v2": ["vos3", "vos", "메인프레임"],
        "ofmanager_v2": ["ofmanager", "매니저", "manager gui"],
        "openframe_base_v2": ["openframe base", "ofbase", "openframe 기본"],
        "ofcobol_v2": ["cobol", "코볼", "ofcobol", "cobmake"],
        "openframe_common_v2": ["openframe common", "공통", "ofcommon"],
        "webtob_v2": ["webtob", "웹투비", "wscfl", "wsadmin"],
        "openframe_batch_v2": ["batch", "배치", "jcl", "job", "tjesmgr", "tjes"],
        "prosort_v2": ["prosort", "프로소트", "sort", "정렬"],
        "openframe_osc_v2": ["osc", "oscmgr", "온라인", "cics"],
        "ofstudio_v2": ["ofstudio", "스튜디오", "studio ide"],
        "openframe_osi_v2": ["osi", "osimgr", "ims dc"],
        "tmax_v2": ["tmax", "티맥스", "tp monitor", "tmboot", "tmdown"],
        "ofminer_v2": ["ofminer", "마이너", "데이터 마이닝"],
        "openframe_gateway_v2": ["gateway", "게이트웨이", "gwmgr"],
    }

    def __init__(
        self,
        base_model_name: str = "Qwen/Qwen2.5-7B-Instruct",
        adapter_base_dir: str = "/raid/users/ofuser/qlora/outputs",
        max_loaded_adapters: int = 5,
        governance_gate_path: Optional[str] = None,
    ):
        self.base_model_name = base_model_name
        self.adapter_base_dir = Path(adapter_base_dir)
        self.max_loaded_adapters = max_loaded_adapters
        self.governance_gate_path = governance_gate_path

        self._model = None
        self._tokenizer = None
        self._loaded_adapters: Dict[str, bool] = {}
        self._adapter_registry: Dict[str, AdapterInfo] = {}
        self._blocked_adapters: Set[str] = set()

        self._init_registry()
        self._load_governance_gate()

    def _init_registry(self):
        """어댑터 레지스트리 초기화."""
        for product in PRODUCT_REGISTRY:
            pid = product["id"]
            adapter_path = self.adapter_base_dir / f"{pid}_adapter"

            # 대체 경로 탐색
            if not adapter_path.exists():
                adapter_path = self.adapter_base_dir / pid
            if not adapter_path.exists():
                # final_adapter 하위 디렉토리
                alt = self.adapter_base_dir / pid / "final_adapter"
                if alt.exists():
                    adapter_path = alt

            self._adapter_registry[pid] = AdapterInfo(
                product_id=pid,
                name=product["name"],
                category=product["category"],
                language=product["lang"],
                adapter_path=str(adapter_path),
            )

    def _load_governance_gate(self):
        """Governance gate 결과를 로드하여 차단 어댑터 설정."""
        if not self.governance_gate_path:
            return

        gate_path = Path(self.governance_gate_path)
        if not gate_path.exists():
            return

        try:
            data = json.loads(gate_path.read_text(encoding="utf-8"))
            for pr in data.get("product_results", []):
                if not pr.get("overall_pass", True):
                    pid = pr["product_id"]
                    self._blocked_adapters.add(pid)
                    if pid in self._adapter_registry:
                        self._adapter_registry[pid].is_approved = False
                    logger.warning(f"Adapter blocked by governance: {pid}")

            logger.info(f"Governance gate loaded: {len(self._blocked_adapters)} blocked")
        except Exception as e:
            logger.error(f"Failed to load governance gate: {e}")

    # ──────────────────────────────────────
    # Model & Adapter Loading
    # ──────────────────────────────────────

    def load_base_model(self, device_map: str = "auto", gpu_id: Optional[str] = None):
        """베이스 모델 로드 (최초 1회)."""
        import torch
        from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig

        if gpu_id:
            import os
            os.environ["CUDA_VISIBLE_DEVICES"] = gpu_id

        logger.info(f"Loading base model: {self.base_model_name}")

        self._tokenizer = AutoTokenizer.from_pretrained(
            self.base_model_name, trust_remote_code=True
        )

        bnb_config = BitsAndBytesConfig(
            load_in_4bit=True,
            bnb_4bit_quant_type="nf4",
            bnb_4bit_use_double_quant=True,
            bnb_4bit_compute_dtype=torch.float16,
        )

        self._model = AutoModelForCausalLM.from_pretrained(
            self.base_model_name,
            quantization_config=bnb_config,
            device_map=device_map,
            trust_remote_code=True,
        )

        logger.info("Base model loaded successfully")

    def load_adapter(self, product_id: str) -> bool:
        """
        특정 제품의 LoRA 어댑터 로드.
        LRU 방식으로 오래된 어댑터 해제.
        """
        if product_id in self._blocked_adapters:
            logger.warning(f"Adapter {product_id} is blocked by governance gate")
            return False

        if product_id in self._loaded_adapters:
            return True

        if self._model is None:
            logger.error("Base model not loaded. Call load_base_model() first.")
            return False

        info = self._adapter_registry.get(product_id)
        if not info:
            logger.error(f"Unknown product: {product_id}")
            return False

        adapter_path = Path(info.adapter_path)
        if not adapter_path.exists():
            logger.error(f"Adapter path not found: {adapter_path}")
            return False

        # LRU eviction
        if len(self._loaded_adapters) >= self.max_loaded_adapters:
            self._evict_oldest_adapter()

        from peft import PeftModel

        start = time.time()
        try:
            if not self._loaded_adapters:
                # 첫 어댑터: PeftModel.from_pretrained
                self._model = PeftModel.from_pretrained(
                    self._model,
                    str(adapter_path),
                    adapter_name=product_id,
                )
            else:
                # 추가 어댑터: load_adapter
                self._model.load_adapter(str(adapter_path), adapter_name=product_id)

            self._loaded_adapters[product_id] = True
            load_time = (time.time() - start) * 1000

            info.is_loaded = True
            info.load_time_ms = load_time
            logger.info(f"Adapter loaded: {product_id} ({load_time:.0f}ms)")
            return True
        except Exception as e:
            info.error_count += 1
            logger.error(f"Failed to load adapter {product_id}: {e}")
            return False

    def _evict_oldest_adapter(self):
        """가장 오래 사용된 어댑터 해제 (LRU)."""
        if not self._loaded_adapters:
            return

        oldest_pid = None
        oldest_time = None

        for pid in self._loaded_adapters:
            info = self._adapter_registry.get(pid)
            if info and (oldest_time is None or
                         (info.last_used or "") < (oldest_time or "")):
                oldest_pid = pid
                oldest_time = info.last_used

        if oldest_pid:
            try:
                self._model.delete_adapter(oldest_pid)
                del self._loaded_adapters[oldest_pid]
                self._adapter_registry[oldest_pid].is_loaded = False
                logger.info(f"Evicted adapter: {oldest_pid}")
            except Exception as e:
                logger.error(f"Failed to evict adapter {oldest_pid}: {e}")

    # ──────────────────────────────────────
    # Routing
    # ──────────────────────────────────────

    def route(self, query: str) -> RoutingResult:
        """
        쿼리에서 가장 적합한 제품 어댑터를 선택.
        키워드 매칭 기반.
        """
        query_lower = query.lower()
        best_product = None
        best_score = 0
        best_keywords = []

        for product_id, keywords in self.PRODUCT_KEYWORDS.items():
            matched = []
            for kw in keywords:
                if kw.lower() in query_lower:
                    matched.append(kw)

            score = len(matched)
            # 정확한 매치에 보너스
            for kw in matched:
                if re.search(r'\b' + re.escape(kw) + r'\b', query_lower):
                    score += 0.5

            if score > best_score:
                best_score = score
                best_product = product_id
                best_keywords = matched

        if best_product is None:
            return RoutingResult(
                product_id="openframe_base_v2",  # 기본 폴백
                confidence=0.0,
                matched_keywords=[],
                fallback=True,
            )

        confidence = min(1.0, best_score / 3.0)
        return RoutingResult(
            product_id=best_product,
            confidence=confidence,
            matched_keywords=best_keywords,
            fallback=False,
        )

    # ──────────────────────────────────────
    # Generation
    # ──────────────────────────────────────

    def generate(
        self,
        product_id: str,
        prompt: str,
        max_new_tokens: int = 512,
        temperature: float = 0.7,
        system_prompt: Optional[str] = None,
    ) -> GenerationResult:
        """
        지정된 제품 어댑터로 응답 생성.

        Args:
            product_id: 사용할 어댑터의 제품 ID
            prompt: 사용자 쿼리
            max_new_tokens: 최대 생성 토큰 수
            temperature: 샘플링 온도
            system_prompt: 시스템 프롬프트 (없으면 제품별 기본값)
        """
        import torch

        # 어댑터 로드 확인
        if product_id not in self._loaded_adapters:
            loaded = self.load_adapter(product_id)
            if not loaded:
                return GenerationResult(
                    product_id=product_id,
                    response="[ERROR] Adapter not available",
                    latency_ms=0,
                    tokens_generated=0,
                    adapter_loaded=False,
                )

        # 어댑터 활성화
        self._model.set_adapter(product_id)

        # 프롬프트 구성
        if system_prompt is None:
            info = self._adapter_registry[product_id]
            system_prompt = self._get_default_system_prompt(info)

        full_prompt = (
            f"<|im_start|>system\n{system_prompt}<|im_end|>\n"
            f"<|im_start|>user\n{prompt}<|im_end|>\n"
            f"<|im_start|>assistant\n"
        )

        start = time.time()
        input_ids = self._tokenizer(
            full_prompt, return_tensors="pt", truncation=True, max_length=2048
        )["input_ids"].to(self._model.device)

        with torch.no_grad():
            output_ids = self._model.generate(
                input_ids,
                max_new_tokens=max_new_tokens,
                temperature=temperature,
                do_sample=temperature > 0,
                top_p=0.9,
            )

        gen_ids = output_ids[0][input_ids.shape[1]:]
        response = self._tokenizer.decode(gen_ids, skip_special_tokens=True)
        latency = (time.time() - start) * 1000

        # 메트릭 업데이트
        info = self._adapter_registry[product_id]
        info.total_requests += 1
        info.last_used = datetime.now(timezone.utc).isoformat()
        info.avg_latency_ms = (
            (info.avg_latency_ms * (info.total_requests - 1) + latency)
            / info.total_requests
        )

        return GenerationResult(
            product_id=product_id,
            response=response,
            latency_ms=round(latency, 1),
            tokens_generated=len(gen_ids),
            adapter_loaded=True,
        )

    def _get_default_system_prompt(self, info: AdapterInfo) -> str:
        """언어별 기본 시스템 프롬프트."""
        prompts = {
            "ko": f"당신은 {info.name} 전문 기술 어시스턴트입니다. {info.name}에 관한 질문에 정확하게 답변해주세요.",
            "ja": f"あなたは{info.name}の専門技術アシスタントです。{info.name}に関する質問に正確に回答してください。",
            "en": f"You are a {info.name} technical expert. Answer questions about {info.name} accurately.",
        }
        return prompts.get(info.language, prompts["en"])

    # ──────────────────────────────────────
    # Health Check
    # ──────────────────────────────────────

    def health_check(self, product_id: Optional[str] = None) -> List[HealthCheckResult]:
        """어댑터 헬스체크."""
        products = [product_id] if product_id else ALL_PRODUCT_IDS
        results = []

        for pid in products:
            info = self._adapter_registry.get(pid)
            if not info:
                results.append(HealthCheckResult(
                    product_id=pid,
                    healthy=False,
                    adapter_loaded=False,
                    is_approved=False,
                    avg_latency_ms=0,
                    error_rate=0,
                    last_used=None,
                    issues=["Product not registered"],
                ))
                continue

            issues = []
            error_rate = (
                info.error_count / max(1, info.total_requests + info.error_count)
            )

            # 어댑터 파일 존재 확인
            if not Path(info.adapter_path).exists():
                issues.append("Adapter files missing")

            # 승인 상태
            if not info.is_approved:
                issues.append("Blocked by governance gate")

            # 레이턴시
            if info.avg_latency_ms > 5000:
                issues.append(f"High latency: {info.avg_latency_ms:.0f}ms")

            # 에러율
            if error_rate > 0.1:
                issues.append(f"High error rate: {error_rate:.1%}")

            results.append(HealthCheckResult(
                product_id=pid,
                healthy=len(issues) == 0,
                adapter_loaded=info.is_loaded,
                is_approved=info.is_approved,
                avg_latency_ms=info.avg_latency_ms,
                error_rate=error_rate,
                last_used=info.last_used,
                issues=issues,
            ))

        return results

    def get_status(self) -> Dict:
        """전체 라우터 상태 조회."""
        return {
            "base_model": self.base_model_name,
            "base_model_loaded": self._model is not None,
            "total_adapters": len(self._adapter_registry),
            "loaded_adapters": list(self._loaded_adapters.keys()),
            "blocked_adapters": list(self._blocked_adapters),
            "max_loaded": self.max_loaded_adapters,
            "adapters": {
                pid: info.to_dict()
                for pid, info in self._adapter_registry.items()
            },
        }

    def export_metrics_json(self, output_path: str):
        """어댑터 메트릭 JSON 내보내기."""
        data = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "router_status": self.get_status(),
            "health_checks": [h.to_dict() for h in self.health_check()],
        }

        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        Path(output_path).write_text(
            json.dumps(data, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
