"""
Product Agent Service

제품별 Agent 기반 검색 서비스.
ManualRegistryService에서 발견된 제품으로 Agent를 동적 생성합니다.
기존 요약본(summaries) + 신규 PDF(manuals) 모두 지원.
"""
import logging
import os
from typing import Dict, List, Optional

from ..models.agentic_rag import QueryType
from .structured_knowledge_store import (
    StructuredKnowledgeStore,
    ProductSearchContext,
    SUMMARIES_BASE,
)

logger = logging.getLogger(__name__)


class BaseProductAgent:
    """
    제품별 Agent 베이스 클래스

    각 Agent는:
    - 자신의 product_id (str)를 갖는다
    - 구조화 데이터 소스 경로를 안다 (summaries + PDF)
    - LLM 없이 키워드 기반 구조화 검색을 수행한다
    """

    def __init__(
        self,
        product_id: str,
        knowledge_domains: List[str],
        summary_paths: Dict[str, List[str]],
    ):
        self.product_id = product_id
        self.knowledge_domains = knowledge_domains
        self.summary_paths = summary_paths
        self._knowledge_store: Optional[StructuredKnowledgeStore] = None

    @property
    def knowledge_store(self) -> StructuredKnowledgeStore:
        if self._knowledge_store is None:
            self._knowledge_store = StructuredKnowledgeStore(
                product_id=self.product_id,
                summary_paths=self.summary_paths,
            )
        return self._knowledge_store

    async def search(
        self,
        query: str,
        query_type: Optional[QueryType] = None,
        top_k: int = 5,
    ) -> ProductSearchContext:
        """제품별 구조화 검색 실행"""
        results = ProductSearchContext(product=self.product_id)

        # 질문 유형에 따라 도메인 필터링
        domains = self._get_domains_for_query_type(query_type)

        results.structured_results = await self.knowledge_store.search(
            query=query,
            domains=domains,
            top_k=top_k,
        )

        return results

    def _get_domains_for_query_type(
        self,
        query_type: Optional[QueryType],
    ) -> Optional[List[str]]:
        """질문 유형에 따른 검색 도메인 결정"""
        if query_type is None:
            return None

        domain_map = {
            QueryType.COMMAND: ["commands"],
            QueryType.ERROR_CODE: ["error_codes"],
            QueryType.PARAMETER: ["configs"],
            QueryType.CONFIG: ["configs"],
            QueryType.FREEFORM: None,
        }
        return domain_map.get(query_type)

    def get_stats(self) -> Dict[str, int]:
        """Agent 지식 저장소 통계"""
        return self.knowledge_store.get_stats()

    @property
    def is_available(self) -> bool:
        return True


# =============================================================================
# Dynamic Product Agent Service
# =============================================================================

# QLoRA 학습 데이터 경로 접두사
_LEARNING_BASE = "multi_lora_v9_improved"

# 기존 요약본 매핑 (product_id → summary_paths)
# ManualRegistry가 발견하는 제품과 병합됨
_LEGACY_SUMMARY_PATHS: Dict[str, Dict[str, List[str]]] = {
    "mvs_openframe_7.1": {
        "commands": [
            "commands/OpenFrame_TJES_MVS.md",
            "commands/OpenFrame_Batch_MVS.md",
            "commands/OpenFrame_OSC_MVS.md",
            "commands/OpenFrame_OSI_MVS.md",
            "commands/OpenFrame_TACF_MVS.md",
            "commands/OpenFrame_HiDB_MVS.md",
            "commands/OpenFrame_Common_MVS.md",
            "commands/OpenFrame_Base_MVS.md",
            "commands/OpenFrame_MVS.md",
        ],
        "error_codes": ["error-codes/BASE-*.md", "error-codes/BATCH-*.md", "error-codes/TACF-*.md"],
        "configs": [
            "configs/OpenFrame_TJES_MVS.md",
            "configs/OpenFrame_Batch_MVS.md",
            "configs/OpenFrame_OSC_MVS.md",
            "configs/OpenFrame_TACF_MVS.md",
            "configs/OpenFrame_Base_MVS.md",
            "configs/OpenFrame_Common_MVS.md",
            "configs/OpenFrame_MVS.md",
        ],
        "glossary": ["glossary/*.md"],
        "learning_qa": [
            f"{_LEARNING_BASE}/openframe_base_v2/train.json",
            f"{_LEARNING_BASE}/openframe_batch_v2/train.json",
            f"{_LEARNING_BASE}/openframe_osc_v2/train.json",
            f"{_LEARNING_BASE}/openframe_osi_v2/train.json",
            f"{_LEARNING_BASE}/openframe_tacf_v2/train.json",
            f"{_LEARNING_BASE}/openframe_hidb_v2/train.json",
            f"{_LEARNING_BASE}/openframe_common_v2/train.json",
            f"{_LEARNING_BASE}/openframe_aim_v2/train.json",
        ],
    },
    "msp_openframe_7.3": {
        "commands": [
            "commands/OpenFrame_MSP.md",
            "commands/OpenFrame_Batch_MSP.md",
            "commands/OpenFrame_AIM_MSP.md",
            "commands/OpenFrame_TACF_MSP.md",
            "commands/OpenFrame_Base_MSP.md",
        ],
        "error_codes": ["error-codes/BASE-*.md", "error-codes/AIM-*.md"],
        "configs": [
            "configs/OpenFrame_MSP.md",
            "configs/OpenFrame_Batch_MSP.md",
            "configs/OpenFrame_AIM_MSP.md",
            "configs/OpenFrame_TACF_MSP.md",
            "configs/OpenFrame_Base_MSP.md",
        ],
        "learning_qa": [
            f"{_LEARNING_BASE}/openframe_base_v2/train.json",
            f"{_LEARNING_BASE}/openframe_aim_v2/train.json",
        ],
    },
    "vos3_openframe_2.0": {
        "commands": [
            "commands/OpenFrame_VOS3.md",
            "commands/OpenFrame_Batch_VOS3.md",
            "commands/OpenFrame_TJES_VOS3.md",
        ],
        "error_codes": ["error-codes/BASE-*.md"],
        "configs": [
            "configs/OpenFrame_VOS3.md",
            "configs/OpenFrame_Batch_VOS3.md",
            "configs/OpenFrame_TJES_VOS3.md",
        ],
        "learning_qa": [
            f"{_LEARNING_BASE}/openframe_vos3_v2/train.json",
        ],
    },
    "xsp_openframe_7.3": {
        "commands": [
            "commands/OpenFrame_XSP.md",
            "commands/OpenFrame_Batch_XSP.md",
            "commands/OpenFrame_AIM_XSP.md",
            "commands/OpenFrame_TACF_XSP.md",
            "commands/OpenFrame_Base_XSP.md",
        ],
        "error_codes": ["error-codes/BASE-*.md"],
        "configs": [
            "configs/OpenFrame_XSP.md",
            "configs/OpenFrame_Batch_XSP.md",
            "configs/OpenFrame_AIM_XSP.md",
            "configs/OpenFrame_TACF_XSP.md",
            "configs/OpenFrame_Base_XSP.md",
        ],
        "learning_qa": [
            f"{_LEARNING_BASE}/openframe_base_v2/train.json",
        ],
    },
    "tibero_7fixset01": {
        "commands": ["commands/Tibero.md"],
        "configs": ["configs/Tibero.md"],
        "learning_qa": [
            f"{_LEARNING_BASE}/tibero7_v2/train.json",
        ],
    },
    "tmax_6.0": {
        "commands": ["commands/Tmax.md"],
        "configs": ["configs/Tmax.md"],
        "learning_qa": [
            f"{_LEARNING_BASE}/tmax_v2/train.json",
        ],
    },
    "ofasm_4": {
        "commands": ["commands/O.md", "commands/OpenFrame.md"],
        "configs": ["configs/OpenFrame.md"],
    },
    "ofcobol_4": {
        "commands": ["commands/O.md", "commands/OpenFrame.md"],
        "configs": ["configs/OpenFrame.md"],
        "learning_qa": [
            f"{_LEARNING_BASE}/ofcobol_v2/train.json",
        ],
    },
}

# 구 ProductId → 신 product_id 매핑 (하위 호환성)
_LEGACY_ID_MAP: Dict[str, str] = {
    "openframe_mvs": "mvs_openframe_7.1",
    "openframe_base": "mvs_openframe_7.1",  # Base는 MVS에 통합
    "msp_openframe": "msp_openframe_7.3",
    "vos3_openframe": "vos3_openframe_2.0",
    "tibero7": "tibero_7fixset01",
    "ofasm": "ofasm_4",
    "ofcobol": "ofcobol_4",
    "xsp_openframe": "xsp_openframe_7.3",
    "tmax": "tmax_6.0",
}


class DynamicProductAgentService:
    """
    ManualRegistryService 기반 동적 Agent 관리

    1. ManualRegistry에서 발견된 제품 목록으로 Agent 자동 생성
    2. 기존 요약본(summaries) 경로와 PDF 경로를 병합
    3. 구 ProductId 호환성 유지 (legacy mapping)
    """

    def __init__(self):
        self._agents: Dict[str, BaseProductAgent] = {}
        self._initialized = False

    def _ensure_initialized(self):
        if self._initialized:
            return
        self._build_agents()
        self._initialized = True

    def _build_agents(self):
        """ManualRegistry + Legacy summaries로 Agent 생성"""
        from .manual_registry_service import get_manual_registry_service

        registry = get_manual_registry_service()
        all_products = registry.get_all_products()

        for product_id, product in all_products.items():
            # 기존 요약본 경로
            legacy_paths = _LEGACY_SUMMARY_PATHS.get(product_id, {})

            # PDF 경로 (manuals 디렉토리)
            pdf_paths: Dict[str, List[str]] = {}
            if product.pdf_files:
                pdf_glob_pattern = os.path.join(product.directory_path, "*.pdf")
                pdf_paths["pdf_manuals"] = [pdf_glob_pattern]

            # 병합: 기존 요약본 + PDF
            merged_paths: Dict[str, List[str]] = {}
            for domain, paths in legacy_paths.items():
                merged_paths[domain] = list(paths)
            for domain, paths in pdf_paths.items():
                if domain in merged_paths:
                    merged_paths[domain].extend(paths)
                else:
                    merged_paths[domain] = list(paths)

            # 모든 제품에 glossary 추가
            if "glossary" not in merged_paths:
                merged_paths["glossary"] = ["glossary/*.md"]

            domains = list(merged_paths.keys())

            self._agents[product_id] = BaseProductAgent(
                product_id=product_id,
                knowledge_domains=domains,
                summary_paths=merged_paths,
            )

        logger.info(
            f"DynamicProductAgentService: built {len(self._agents)} agents"
        )

    def get_agent(self, product_id: str) -> Optional[BaseProductAgent]:
        """product_id (str) 로 Agent 조회. 구 ProductId도 지원."""
        self._ensure_initialized()
        # 직접 매칭
        agent = self._agents.get(product_id)
        if agent:
            return agent
        # 구 ProductId → 신 product_id 매핑
        mapped_id = _LEGACY_ID_MAP.get(product_id)
        if mapped_id:
            return self._agents.get(mapped_id)
        return None

    def get_all_agents(self) -> Dict[str, BaseProductAgent]:
        """전체 Agent 목록"""
        self._ensure_initialized()
        return dict(self._agents)

    def get_product_id_for_legacy(self, legacy_id: str) -> Optional[str]:
        """구 ProductId를 신 product_id로 변환"""
        if legacy_id in _LEGACY_ID_MAP:
            return _LEGACY_ID_MAP[legacy_id]
        self._ensure_initialized()
        if legacy_id in self._agents:
            return legacy_id
        return None


# =============================================================================
# Singleton
# =============================================================================

_dynamic_service: Optional[DynamicProductAgentService] = None


def _get_dynamic_service() -> DynamicProductAgentService:
    global _dynamic_service
    if _dynamic_service is None:
        _dynamic_service = DynamicProductAgentService()
    return _dynamic_service


def get_product_agent(product_id) -> Optional[BaseProductAgent]:
    """Get product agent by product_id (str or ProductId enum)"""
    # ProductId enum → str 변환
    pid_str = product_id.value if hasattr(product_id, 'value') else str(product_id)
    return _get_dynamic_service().get_agent(pid_str)


def get_all_product_agents() -> Dict[str, BaseProductAgent]:
    """Get all product agents (str keys)"""
    return _get_dynamic_service().get_all_agents()
