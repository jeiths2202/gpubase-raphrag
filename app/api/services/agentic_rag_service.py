"""
Agentic RAG Service (Orchestrator)

제품별 Agent 기반 RAG 시스템의 메인 오케스트레이터.
QueryRouter → ProductAgent → QueryTypeClassifier → TemplateResponse/LLM+Verification 파이프라인을 조율합니다.
동적 제품(str) 기반으로 동작합니다.
"""
import asyncio
import json
import logging
import os
import re
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Any, AsyncGenerator, Dict, List, Optional

from ..core.config import get_api_settings
from ..core.logging_framework import get_logger
from ..models.agentic_rag import (
    AgenticRAGRequest,
    AgenticRAGResponse,
    AgenticRAGHealth,
    AgentMode,
    QueryType,
    RouterResult,
    RouterDecision,
    VerifiedSentence,
)
from ..models.openframe_rag import (
    ConfidenceLevel,
    ProductSources,
    VectorSource,
)
from ..models.web_doc import WebDocSource
from .web_doc_search_service import (
    WebDocSearchService,
    WebDocSearchResult,
    get_web_doc_search_service,
    WEB_DOC_THRESHOLD,
)
from .query_router_service import QueryRouter, get_query_router
from .product_agent_service import (
    BaseProductAgent,
    get_product_agent,
    get_all_product_agents,
)
from .structured_knowledge_store import SearchResult, ProductSearchContext
from .query_type_classifier import QueryTypeClassifier, get_query_type_classifier
from .template_response_builder import TemplateResponseBuilder, get_template_response_builder
from .response_verifier import ResponseVerifier, get_response_verifier
from .product_context_memory import ProductContextMemory, get_product_context_memory

logger = get_logger("kms.agentic_rag")

# 동적 product_id → VLLMAdapter가 인식하는 제품명 매핑
_DYNAMIC_TO_ADAPTER_MAP = {
    "mvs_openframe_7.1": "openframe_base",
    "msp_openframe_7.3": "msp_openframe",
    "vos3_openframe_2.0": "openframe_vos3",
    "xsp_openframe_7.3": "xsp_openframe",
    "tibero_7fixset01": "tibero7",
    "tmax_6.0": "tmax",
    "ofasm_4": "ofasm",
    "ofcobol_4": "ofcobol",
    "jeus_8.5": "jeus",
    "jeus_8": "jeus",
    "webtob_5.0": "webtob",
    "protrieve_7": "protrieve",
    "ofstudio_7": "ofstudio",
    "ofmanager_7": "ofmanager",
    "openframe_aim_7": "openframe_aim",
    "openframe_tacf_7": "openframe_tacf",
    "openframe_hidb_7": "openframe_hidb",
    "openframe_ndb_7": "openframe_ndb",
    "openframe_osi_7": "openframe_osi",
}




# Intent re-ranking: 제품명/문맥 토큰과 사용자 의도 토큰을 분리하여 검색 결과 재순위
_PRODUCT_TERMS = frozenset({
    "tjes", "tacf", "osc", "osi", "hidb", "ndb", "ofasm", "ofcobol",
    "ofstudio", "ofmanager", "openframe", "tibero", "jeus", "webtob",
    "tmax", "protrieve", "xsp", "msp", "vos3", "mvs", "aim",
    "tjesmgr", "tacfmgr", "oscmgr", "osimgr", "hidbmgr", "ndbmgr",
    "volmgr", "catmgr", "ofmanager",
})
_GENERIC_MODIFIERS = frozenset({
    # 일본어 고빈도 일반 수식어
    "機能", "設定", "説明", "エラー", "方法", "使い方", "コマンド",
    "確認", "手順", "一覧", "詳細", "情報", "問題", "対処",
    # 일본어 카타카나 일반 수식어 (제품 고유명사가 아닌 일반 용어)
    "ユーティリティ", "ツール", "プログラム", "オプション", "パラメータ",
    "インストール", "サーバー", "クライアント", "システム", "プロセス",
    "ファイル", "データ", "テーブル", "リスト", "ガイド",
    # 일본어 히라가나 문법 조각 (intent가 아닌 조사/보조동사)
    "について", "してください", "ください", "ている", "された",
    "される", "している", "できる", "ことが", "ものです",
    "ありません", "あります", "なります",
    # 영어 고빈도 일반 수식어
    "function", "setting", "error", "command", "config", "how",
    "feature", "description", "list", "detail", "info",
    "utility", "tool", "program", "option", "parameter",
    "install", "server", "client", "system", "process",
    "file", "guide", "manual", "reference",
})
_OVERVIEW_PATTERN = re.compile(
    r'概要|overview|紹介|introduction|一覧|about|全体|summary', re.IGNORECASE
)
_TOKENIZE_RE = re.compile(
    r'[a-z0-9][a-z0-9_\-]*[a-z0-9]|[a-z0-9]'
    r'|[\u30a0-\u30ff]{2,}'
    r'|[\u4e00-\u9fff]+'
    r'|[\uac00-\ud7af]{2,}'
    r'|[\u3040-\u309f]{2,}'
)


# =========================================================================
# Agent Mode 인텐트 분류용 키워드 (Code / Planner 감지)
# =========================================================================
_CODE_KEYWORDS = frozenset({
    # 영어
    "code", "script", "program", "function", "class", "implement",
    "debug", "compile", "algorithm", "sample code", "example code",
    # 일본어
    "コード", "スクリプト", "プログラム", "関数", "クラス", "実装",
    "デバッグ", "コンパイル", "アルゴリズム", "サンプルコード",
    # 한국어
    "코드", "스크립트", "프로그램", "함수", "클래스", "구현",
    "디버그", "컴파일", "알고리즘", "샘플코드",
    # 제품 고유 코드 관련
    "jcl", "cobol", "assembler", "rexx", "clist",
})
_PLANNER_KEYWORDS = frozenset({
    # 영어
    "plan", "strategy", "approach", "steps", "roadmap",
    "breakdown", "decompose", "organize", "schedule", "migration",
    # 일본어
    "計画", "戦略", "アプローチ", "ステップ", "ロードマップ",
    "手順", "マイグレーション", "移行", "段階", "方針",
    # 한국어
    "계획", "전략", "접근", "단계", "로드맵",
    "분해", "마이그레이션", "이전", "이행", "방침",
})

_METADATA_PREFIXES = (
    '製品/product', '**製品/product',
    '出典/source', '**出典/source',
)

# PDF 우선 검색: primary(PDF) / fallback(요약본·학습데이터) 2단계 분리
_PRIMARY_DOMAINS = frozenset({"pdf_manuals"})


def _partition_results(
    results: List[SearchResult],
) -> tuple:
    """PDF(primary)와 요약본/학습데이터(fallback)를 분리"""
    primary = [r for r in results if r.domain in _PRIMARY_DOMAINS]
    fallback = [r for r in results if r.domain not in _PRIMARY_DOMAINS]
    return primary, fallback


def _select_tiered_results(
    results: List[SearchResult],
    min_primary: int = 1,
) -> List[SearchResult]:
    """PDF 결과가 min_primary개 이상이면 PDF만, 아니면 전체 결과 사용"""
    primary, fallback = _partition_results(results)
    if len(primary) >= min_primary:
        return primary
    return results


def _clean_inline_metadata(content: str) -> str:
    """인라인 메타데이터 행(製品/Product, 出典/Source) 제거"""
    lines = content.split('\n')
    cleaned = [l for l in lines if not l.strip().lower().startswith(_METADATA_PREFIXES)]
    return '\n'.join(cleaned).strip()


# =========================================================================
# Query Pattern Analysis (Parallel / Pipeline / Single)
# =========================================================================

class QueryPatternType(str, Enum):
    PARALLEL = "parallel"
    PIPELINE = "pipeline"
    SINGLE = "single"


@dataclass
class QueryPatternResult:
    pattern: QueryPatternType
    subjects: List[str]
    confidence: float


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _task_status_event(
    task_id: str, status: str, *, latency_ms: int | None = None,
) -> dict:
    _EVENT_MAP = {"running": "task_start", "completed": "task_complete", "failed": "task_failed"}
    event_name = _EVENT_MAP.get(status, f"task_{status}")
    time_key = "start_time" if status == "running" else "end_time"
    extra: dict = {}
    if status == "completed":
        extra["success"] = True
    if latency_ms is not None:
        extra["latency_ms"] = latency_ms
    current_task: dict = {"task_id": task_id, "status": status, time_key: _iso_now()}
    if latency_ms is not None:
        current_task["latency_ms"] = latency_ms
    return {
        "type": "trace_data",
        "trace_data": {
            "current_task": current_task,
            "timeline_event": {
                "event": event_name, "task_id": task_id,
                "agent_type": "rag", "timestamp": _iso_now(),
                **extra,
            },
        },
    }


# Subject extraction patterns (for comparison queries)
_COMPARISON_SUBJECT_PATTERNS = [
    # Japanese: AとBを比較 / AとBの違い
    re.compile(r'(.+?)と(.+?)(?:を|の)(?:比較|対比|違い|差|相違)', re.IGNORECASE),
    # Japanese: AとBについて...比較 — capture only up to の/について boundary
    re.compile(r'(.+?)と(.+?)(?:の|について|に関して)', re.IGNORECASE),
    # Korean: A와 B 비교 / A과 B 차이
    re.compile(r'(.+?)(?:와|과|랑)\s*(.+?)(?:를|을|의)?\s*(?:비교|대조|차이|다른|구분)', re.IGNORECASE),
    re.compile(r'(.+?)(?:와|과|랑)\s*(.+?)(?:에\s*대해|관해)', re.IGNORECASE),
    # English: compare A and B / A vs B
    re.compile(r'(?:compare|contrast)\s+(.+?)\s+(?:and|with|vs\.?|versus)\s+(.+?)(?:\s|$)', re.IGNORECASE),
    re.compile(r'(.+?)\s+(?:vs\.?|versus)\s+(.+?)(?:\s|$)', re.IGNORECASE),
]

# Sequential task extraction patterns
_SEQUENTIAL_TASK_PATTERNS = [
    # Japanese: AをリストしてからB生成
    re.compile(r'(.+?)(?:を検索|をリスト|を調べ|を探).+?(?:して|してから|した後)\s*(.+?)(?:して|を生成|を作成|してください|$)', re.IGNORECASE),
    # Korean: A 리스트업하고 B 생성해줘
    re.compile(r'(.+?)(?:리스트업|검색|조회|찾아).+?(?:하고|한\s*후)\s*(.+?)(?:생성|작성|만들어|해줘|해주세요|$)', re.IGNORECASE),
    # English: first A then B / find A and then generate B
    re.compile(r'(?:first|find|search|list)\s+(.+?)(?:and\s+then|then)\s+(.+?)$', re.IGNORECASE),
]


class AgenticRAGService:
    """
    Agentic RAG 오케스트레이터

    파이프라인:
    1. QueryRouter.classify() → 제품 확정/되묻기/매칭없음
    2. ProductAgent.search() → 구조화 검색 (LLM 없음)
    3. QueryTypeClassifier.classify() → 정형/비정형 판별
    4a. 정형 → TemplateResponseBuilder.build() (환각 0%)
    4b. 비정형 → LLM 생성 + ResponseVerifier.verify()
    5. (NEW) 비교/순차 패턴 → 병렬/파이프라인 DAG 실행
    """

    def __init__(
        self,
        query_router: Optional[QueryRouter] = None,
        query_type_classifier: Optional[QueryTypeClassifier] = None,
        template_builder: Optional[TemplateResponseBuilder] = None,
        response_verifier: Optional[ResponseVerifier] = None,
        product_memory: Optional[ProductContextMemory] = None,
        web_doc_search: Optional[WebDocSearchService] = None,
    ):
        self.query_router = query_router or get_query_router()
        self.query_type_classifier = query_type_classifier or get_query_type_classifier()
        self.template_builder = template_builder or get_template_response_builder()
        self.response_verifier = response_verifier or get_response_verifier()
        self.product_memory = product_memory or get_product_context_memory()
        self.web_doc_search = web_doc_search or get_web_doc_search_service()
        self._product_patterns: Optional[List[tuple]] = None

    def _get_product_patterns(self) -> List[tuple]:
        """ManualRegistry에서 동적 라우팅 패턴 로드"""
        if self._product_patterns is not None:
            return self._product_patterns
        try:
            from .manual_registry_service import get_manual_registry_service
            registry = get_manual_registry_service()
            self._product_patterns = registry.get_routing_patterns()
        except Exception:
            self._product_patterns = []
        return self._product_patterns

    def _detect_products_in_query(self, query: str) -> List[str]:
        """쿼리에서 언급된 모든 제품 감지"""
        detected: List[str] = []
        query_lower = query.lower()
        for pattern, pid in self._get_product_patterns():
            if re.search(pattern, query_lower):
                if pid not in detected:
                    detected.append(pid)
        return detected

    def _classify_agent_mode(self, query: str, agent_mode: AgentMode) -> AgentMode:
        """
        Agent 모드 분류. AUTO이면 키워드 기반 감지, 아니면 그대로 반환.
        2개 이상의 키워드 매칭 시 해당 모드, 아니면 RAG 기본값.
        """
        if agent_mode != AgentMode.AUTO:
            return agent_mode

        tokens = set(_TOKENIZE_RE.findall(query.lower()))
        # 카타카나·한글 토큰도 포함 (원문에서 추출)
        katakana_tokens = set(re.findall(r'[\u30a0-\u30ff]{2,}', query))
        hangul_tokens = set(re.findall(r'[\uac00-\ud7af]{2,}', query))
        all_tokens = tokens | katakana_tokens | hangul_tokens

        code_hits = len(all_tokens & _CODE_KEYWORDS)
        planner_hits = len(all_tokens & _PLANNER_KEYWORDS)

        if code_hits >= 2 and code_hits > planner_hits:
            logger.info(f"Auto-detected agent_mode=CODE (hits={code_hits})")
            return AgentMode.CODE
        if planner_hits >= 2 and planner_hits > code_hits:
            logger.info(f"Auto-detected agent_mode=PLANNER (hits={planner_hits})")
            return AgentMode.PLANNER
        # 1개라도 매칭되면 해당 모드 (동률 시 RAG)
        if code_hits == 1 and planner_hits == 0:
            logger.info(f"Auto-detected agent_mode=CODE (single hit)")
            return AgentMode.CODE
        if planner_hits == 1 and code_hits == 0:
            logger.info(f"Auto-detected agent_mode=PLANNER (single hit)")
            return AgentMode.PLANNER
        return AgentMode.RAG

    # ------------------------------------------------------------------
    # Query Pattern Analysis (parallel / pipeline / single)
    # ------------------------------------------------------------------

    def _analyze_query_pattern(self, message: str) -> QueryPatternResult:
        """쿼리 패턴 분석: 비교(병렬) / 순차(파이프라인) / 단일 판별"""
        # 1) 비교 패턴 (PARALLEL)
        for pat in _COMPARISON_SUBJECT_PATTERNS:
            m = pat.search(message)
            if m:
                subjects = [g.strip() for g in m.groups() if g and g.strip()]
                if len(subjects) >= 2:
                    logger.info(
                        f"Query pattern=PARALLEL, subjects={subjects}"
                    )
                    return QueryPatternResult(
                        pattern=QueryPatternType.PARALLEL,
                        subjects=subjects,
                        confidence=0.85,
                    )

        # 2) 순차 패턴 (PIPELINE)
        for pat in _SEQUENTIAL_TASK_PATTERNS:
            m = pat.search(message)
            if m:
                tasks = [g.strip() for g in m.groups() if g and g.strip()]
                if len(tasks) >= 2:
                    logger.info(
                        f"Query pattern=PIPELINE, tasks={tasks}"
                    )
                    return QueryPatternResult(
                        pattern=QueryPatternType.PIPELINE,
                        subjects=tasks,
                        confidence=0.80,
                    )

        # 3) 기본값: 단일
        return QueryPatternResult(
            pattern=QueryPatternType.SINGLE,
            subjects=[],
            confidence=1.0,
        )

    async def _resolve_search_products(
        self,
        request: AgenticRAGRequest,
    ) -> tuple:
        """
        통합 제품 해석. (product_ids, router_result) 반환.

        Case 1: selected_product → [selected_product], CONFIRMED
        Case 2: products 리스트 → products, CONFIRMED
        Case 3: product != "auto" → [product], CONFIRMED
        Case 4: Auto 모드 → classify() 기반 해석 + Long-term Memory 보강
        """
        # Case 1~3: 명시적 제품 선택
        effective = request.effective_products
        if effective:
            return effective, RouterResult(
                decision=RouterDecision.CONFIRMED,
                product=effective[0],
                confidence=1.0,
            )

        # Case 4: Auto 모드 → QueryRouter (async: LLM 우선 + 키워드 fallback)
        router_result = await self.query_router.classify(
            request.message, request.language or "ja",
            history=request.history,
        )

        if router_result.decision == RouterDecision.CONFIRMED:
            # 확정 + 쿼리에서 추가 제품 감지
            products = [router_result.product]
            additional = [
                p for p in self._detect_products_in_query(request.message)
                if p != router_result.product
            ]
            products.extend(additional)
            return products, router_result

        if router_result.decision == RouterDecision.CLARIFICATION_NEEDED:
            # 후보가 1개이거나, top과 2nd 간의 차이가 큰 경우 자동 확정
            candidates = router_result.candidates
            if (
                router_result.product
                and router_result.confidence >= 0.35
                and (len(candidates) <= 1
                     or (len(candidates) >= 2
                         and candidates[0].confidence - candidates[1].confidence >= 0.15))
            ):
                logger.info(
                    f"[AgenticRAG] Auto-confirming single/dominant candidate: "
                    f"{router_result.product} (conf={router_result.confidence:.2f})"
                )
                products = [router_result.product]
                additional = [
                    p for p in self._detect_products_in_query(request.message)
                    if p != router_result.product
                ]
                products.extend(additional)
                return products, RouterResult(
                    decision=RouterDecision.CONFIRMED,
                    product=router_result.product,
                    confidence=router_result.confidence,
                    candidates=router_result.candidates,
                    all_scores=router_result.all_scores,
                )
            return [], router_result

        # NO_MATCH → 1차: all_scores에서 점수가 있는 제품 사용 (router가 일부 매칭)
        if router_result.all_scores:
            top_products = sorted(
                router_result.all_scores.items(),
                key=lambda x: x[1],
                reverse=True,
            )
            fallback = [p for p, s in top_products[:5] if s > 0]
            if fallback:
                return fallback, router_result

        # NO_MATCH → 2차: Long-term Memory에서 최근 제품 컨텍스트 보강
        # (router 점수가 전혀 없을 때만 → 후속 질문, 대명사 사용 등)
        memory_product = self._resolve_from_memory(request)
        if memory_product:
            logger.info(
                f"[AgenticRAG] Memory-based product resolution: {memory_product}"
            )
            return [memory_product], RouterResult(
                decision=RouterDecision.CONFIRMED,
                product=memory_product,
                confidence=0.6,  # 메모리 기반이므로 중간 confidence
            )

        return [], router_result

    def _resolve_from_memory(self, request: AgenticRAGRequest) -> Optional[str]:
        """
        Long-term Memory에서 최근 제품 컨텍스트를 조회하여 제품을 해석.

        후속 질문 패턴 (それは?, 詳しく, 그거, that 등) 에서 특히 효과적.
        """
        if not self.product_memory or not self.product_memory.available:
            return None

        user_id = getattr(request, "user_id", None) or "anonymous"
        session_id = getattr(request, "session_id", None) or "default"

        # 1. 현재 세션의 최근 제품 확인
        session_product = self.product_memory.get_session_product(user_id, session_id)
        if session_product:
            return session_product

        # 2. 사용자 글로벌 최근 제품 확인
        recent_product = self.product_memory.get_recent_product(user_id)
        if recent_product:
            return recent_product

        return None

    def _rerank_by_intent(
        self,
        query: str,
        product_ids: List[str],
        results: List[SearchResult],
    ) -> List[SearchResult]:
        """
        검색 의도 기반 재순위.

        쿼리 토큰을 context(제품명) / generic(수식어) / intent(핵심 의도)로 분리하고,
        intent 토큰이 제목에 포함된 결과에 보너스를 부여하며 개요 섹션에 페널티를 적용합니다.
        """
        if len(results) <= 1:
            return results

        tokens = _TOKENIZE_RE.findall(query.lower())
        # product_ids에서 추출한 추가 context terms
        pid_terms = set()
        for pid in product_ids:
            for part in pid.replace("-", "_").split("_"):
                if len(part) >= 2:
                    pid_terms.add(part.lower())

        intent_tokens = [
            t for t in tokens
            if t not in _PRODUCT_TERMS
            and t not in pid_terms
            and t not in _GENERIC_MODIFIERS
            and len(t) >= 2
        ]

        if not intent_tokens:
            return results

        logger.debug(f"Intent re-ranking: tokens={tokens}, intent={intent_tokens}")

        for r in results:
            title_lower = r.title.lower()
            bonus = 0.0

            for token in intent_tokens:
                if token in title_lower:
                    bonus += 5.0
                elif token in r.content[:200].lower():
                    bonus += 1.0

            if _OVERVIEW_PATTERN.search(title_lower):
                r.relevance_score *= 0.7

            r.relevance_score += bonus

        results.sort(key=lambda r: r.relevance_score, reverse=True)

        if intent_tokens:
            logger.info(
                f"Intent re-ranked: intent={intent_tokens}, "
                f"top={results[0].title}({results[0].relevance_score:.2f})"
            )
        return results

    async def _multi_product_search(
        self,
        query: str,
        product_ids: List[str],
        query_type: Optional[QueryType],
        top_k_per_product: Optional[int] = None,
        max_total: int = 8,
    ) -> ProductSearchContext:
        """복수 Product Agent 병렬 검색 + 결과 병합."""
        # per-product top_k 자동 조절
        if top_k_per_product is None:
            n = len(product_ids)
            if n <= 2:
                top_k_per_product = 5
            elif n <= 5:
                top_k_per_product = 3
            else:
                top_k_per_product = 2

        agents = []
        for pid in product_ids:
            agent = get_product_agent(pid)
            if agent:
                agents.append((pid, agent))

        if not agents:
            return ProductSearchContext(product=product_ids[0] if product_ids else "auto")

        sem = asyncio.Semaphore(5)

        async def _search_one(pid: str, agent: BaseProductAgent) -> List[SearchResult]:
            async with sem:
                ctx = await agent.search(query=query, query_type=query_type, top_k=top_k_per_product)
                for r in ctx.structured_results:
                    r.product = pid
                return ctx.structured_results

        tasks = [_search_one(pid, agent) for pid, agent in agents]
        results_lists = await asyncio.gather(*tasks, return_exceptions=True)

        all_results: List[SearchResult] = []
        for result in results_lists:
            if isinstance(result, list):
                all_results.extend(result)

        all_results.sort(key=lambda r: r.relevance_score, reverse=True)

        # Intent-based re-ranking: 의도 토큰이 제목에 있는 결과를 상위로
        all_results = self._rerank_by_intent(query, product_ids, all_results)

        # fingerprint dedup
        deduped: List[SearchResult] = []
        seen_fp: set = set()
        for r in all_results:
            raw_fp = r.content[:120].strip().lower()
            fp = re.sub(r"[^a-z0-9\u3040-\u9fff\uac00-\ud7af]", "", raw_fp)
            if fp in seen_fp:
                continue
            seen_fp.add(fp)
            deduped.append(r)
            if len(deduped) >= max_total:
                break

        merged = ProductSearchContext(product=product_ids[0] if product_ids else "auto")
        merged.structured_results = deduped
        logger.info(
            f"Multi-product search: {product_ids} → "
            f"{len(all_results)} total, {len(deduped)} after dedup"
        )
        return merged

    async def health_check(self) -> AgenticRAGHealth:
        """서비스 상태 확인"""
        agents = get_all_product_agents()
        agent_status = {
            pid: agent.is_available
            for pid, agent in agents.items()
        }

        knowledge_stats: Dict[str, int] = {}
        for pid, agent in agents.items():
            try:
                stats = agent.get_stats()
                knowledge_stats[pid] = sum(stats.values())
            except Exception:
                knowledge_stats[pid] = 0

        return AgenticRAGHealth(
            available=True,
            message="Agentic RAG service is running",
            agents=agent_status,
            knowledge_store_status=knowledge_stats,
            supported_products=list(agents.keys()),
        )

    async def chat(self, request: AgenticRAGRequest) -> AgenticRAGResponse:
        """동기식 채팅 처리"""
        start = time.time()

        # 1. 통합 제품 해석
        product_ids, router_result = await self._resolve_search_products(request)

        # Long-term Memory에 제품 라우팅 결과 저장
        if product_ids and self.product_memory and self.product_memory.available:
            user_id = getattr(request, "user_id", None) or "anonymous"
            session_id = getattr(request, "session_id", None) or "default"
            self.product_memory.save_product_context(
                user_id=user_id,
                session_id=session_id,
                product_id=product_ids[0],
                query=request.message,
                confidence=router_result.confidence,
            )

        # 되묻기 필요
        if not product_ids and router_result.decision == RouterDecision.CLARIFICATION_NEEDED:
            return AgenticRAGResponse(
                success=True,
                response="",
                product=router_result.product or "auto",
                query_type=QueryType.FREEFORM,
                router_result=router_result,
                confidence=ConfidenceLevel.LOW,
                processing_time_ms=int((time.time() - start) * 1000),
            )

        # 매칭 없음
        if not product_ids:
            return AgenticRAGResponse(
                success=True,
                response="該当する製品を特定できませんでした。質問を具体的にしていただくか、製品を選択してください。",
                product="auto",
                query_type=QueryType.FREEFORM,
                router_result=router_result,
                confidence=ConfidenceLevel.LOW,
                processing_time_ms=int((time.time() - start) * 1000),
            )

        primary_product = product_ids[0]

        # === Web Doc Fast Path ===
        web_doc_response = await self._try_web_doc_fast_path(
            request, product_ids, primary_product, router_result, start,
        )
        if web_doc_response:
            return web_doc_response
        # === End Web Doc Fast Path ===

        # 2. 질문 유형 분류
        query_type = self.query_type_classifier.classify(request.message)

        # 3. 통합 검색
        search_context = await self._multi_product_search(
            query=request.message,
            product_ids=product_ids,
            query_type=query_type,
        )

        # 4. 응답 생성
        if query_type != QueryType.FREEFORM and search_context.structured_results:
            template_response = self.template_builder.build(
                query=request.message,
                query_type=query_type,
                results=search_context.structured_results,
                language=request.language or "ja",
            )
            if template_response:
                table_supplement = self._build_table_supplement(search_context.structured_results)
                if table_supplement:
                    template_response += table_supplement
                return AgenticRAGResponse(
                    success=True,
                    response=template_response,
                    product=primary_product,
                    query_type=query_type,
                    router_result=router_result,
                    confidence=ConfidenceLevel.HIGH,
                    sources=self._build_sources(search_context.structured_results),
                    processing_time_ms=int((time.time() - start) * 1000),
                )

        # 비정형 질문 또는 템플릿 실패: LLM 생성
        llm_response = await self._generate_with_llm(
            request.message,
            primary_product,
            search_context,
            request.language or "ja",
            history=request.history,
        )

        # LLM 응답에 테이블 보충
        if llm_response and search_context.structured_results:
            table_supplement = self._build_table_supplement(search_context.structured_results)
            if table_supplement:
                llm_response += table_supplement

        verification = None
        if llm_response and search_context.structured_results:
            verification = self.response_verifier.verify(
                llm_response,
                search_context.structured_results,
            )

        confidence = self._calculate_confidence(verification)

        return AgenticRAGResponse(
            success=True,
            response=llm_response or "情報が見つかりませんでした。質問を変更してお試しください。",
            product=primary_product,
            query_type=query_type,
            router_result=router_result,
            verification=verification,
            sources=self._build_sources(search_context.structured_results),
            confidence=confidence,
            processing_time_ms=int((time.time() - start) * 1000),
        )

    async def stream_chat(
        self,
        request: AgenticRAGRequest,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """SSE 스트리밍 채팅"""
        start = time.time()

        # 0. Query Pattern Analysis (비교/순차 → DAG 실행)
        # Special Agent 모드에서는 패턴 분석 건너뛰기 (모든 질문을 Special Agent로 처리)
        try:
            if request.agent_mode == AgentMode.SPECIAL:
                pattern = QueryPatternResult(pattern=QueryPatternType.SINGLE, subjects=[], confidence=0.0)
            else:
                pattern = self._analyze_query_pattern(request.message)
            if pattern.pattern == QueryPatternType.PARALLEL:
                _dag_done = False
                async for event in self._stream_parallel_comparison(
                    request, pattern, start,
                ):
                    yield event
                    if event.get("type") == "done":
                        _dag_done = True
                if _dag_done:
                    return
                # fallback: 병렬 검색 실패 → 단일 모드로 계속 진행
                logger.info("Parallel comparison fallback → single mode")
            if pattern.pattern == QueryPatternType.PIPELINE:
                _dag_done = False
                async for event in self._stream_pipeline(
                    request, pattern, start,
                ):
                    yield event
                    if event.get("type") == "done":
                        _dag_done = True
                if _dag_done:
                    return
                logger.info("Pipeline fallback → single mode")
        except Exception as e:
            logger.warning(f"Pattern analysis failed, falling back to SINGLE: {e}")

        # 1. 통합 제품 해석
        product_ids, router_result = await self._resolve_search_products(request)

        primary_product = product_ids[0] if product_ids else "auto"

        # Long-term Memory에 제품 라우팅 결과 저장
        if product_ids and self.product_memory and self.product_memory.available:
            user_id = getattr(request, "user_id", None) or "anonymous"
            session_id = getattr(request, "session_id", None) or "default"
            self.product_memory.save_product_context(
                user_id=user_id,
                session_id=session_id,
                product_id=primary_product,
                query=request.message,
                confidence=router_result.confidence,
            )

        # 분류 결과 전송 (products 리스트 포함)
        yield {
            "type": "classification",
            "product": primary_product,
            "products": product_ids,
            "decision": router_result.decision.value,
            "confidence": router_result.confidence,
        }

        # 되묻기 필요
        if not product_ids and router_result.decision == RouterDecision.CLARIFICATION_NEEDED:
            yield {
                "type": "clarification_needed",
                "candidates": [
                    {
                        "product": c.product,
                        "confidence": c.confidence,
                        "reason": c.reason,
                        "matched_keywords": c.matched_keywords,
                    }
                    for c in router_result.candidates
                ],
                "message": "どの製品に関する質問ですか？",
            }
            return

        # 매칭 없음
        if not product_ids:
            yield {
                "type": "error",
                "message": "該当する製品を特定できませんでした。製品を選択してください。",
            }
            return

        # === Agent Mode 분기 ===
        effective_mode = self._classify_agent_mode(
            request.message, request.agent_mode,
        )
        if effective_mode != AgentMode.RAG:
            yield {
                "type": "agent_mode",
                "mode": effective_mode.value,
                "auto_detected": request.agent_mode == AgentMode.AUTO,
            }

        if effective_mode == AgentMode.SPECIAL:
            async for event in self._stream_special_agent(
                request, product_ids, router_result, start,
            ):
                yield event
            return

        if effective_mode == AgentMode.CODE:
            async for event in self._stream_code_agent(
                request, product_ids, router_result, start,
            ):
                yield event
            return

        if effective_mode == AgentMode.PLANNER:
            async for event in self._stream_planner_agent(
                request, product_ids, router_result, start,
            ):
                yield event
            return

        # 2. 검색 진행
        yield {
            "type": "search_progress",
            "product": primary_product,
            "products": product_ids,
            "step": "vllm_search",
            "progress": 0.2,
        }

        # === vLLM Direct Search (QLoRA 학습된 도메인 지식으로 직접 응답, feature flag로 제어) ===
        settings = get_api_settings()
        if settings.VLLM_DIRECT_SEARCH_ENABLED:
            vllm_done = False
            async for event in self._try_vllm_direct_search(
                request, primary_product, product_ids, start,
            ):
                yield event
                if event.get("type") == "done":
                    vllm_done = True
            if vllm_done:
                return
        # === End vLLM Direct Search ===

        yield {
            "type": "search_progress",
            "product": primary_product,
            "products": product_ids,
            "step": "structured_search",
            "progress": 0.3,
        }

        # === Web Doc Fast Path (streaming) ===
        web_doc_result = self._search_web_doc(
            request.message, request.language or "ja", product_ids,
        )
        if web_doc_result:
            yield {
                "type": "web_doc_match",
                "url": web_doc_result.url,
                "title": web_doc_result.title,
                "component": web_doc_result.component,
                "score": web_doc_result.normalized_score,
            }
            web_content = await self._fetch_web_doc_content(web_doc_result.url)
            if web_content:
                query_type = self.query_type_classifier.classify(request.message)
                yield {
                    "type": "search_progress",
                    "product": primary_product,
                    "products": product_ids,
                    "step": "web_doc_generating",
                    "progress": 0.6,
                }
                # LLM 스트리밍 (web content를 context로)
                web_context = f"[Web Documentation: {web_doc_result.title}]\nURL: {web_doc_result.url}\n\n{web_content}"
                if len(web_context) > self._MAX_LLM_CONTEXT_CHARS:
                    web_context = web_context[:self._MAX_LLM_CONTEXT_CHARS] + "..."
                full_response = ""
                async for token in self._stream_llm_from_context(
                    request.message, primary_product, web_context,
                    request.language or "ja", history=request.history,
                ):
                    full_response += token
                    yield {"type": "llm_token", "token": token}
                # 소스 정보 (URL 포함)
                yield {
                    "type": "sources",
                    "results": [{
                        "doc_name": web_doc_result.title,
                        "source_page": web_doc_result.url,
                        "content": web_content[:200],
                        "score": web_doc_result.normalized_score,
                        "domain": "web_doc",
                        "product": web_doc_result.product_id,
                        "url": web_doc_result.url,
                    }],
                    "total": 1,
                }
                yield {
                    "type": "done",
                    "processing_time_ms": int((time.time() - start) * 1000),
                    "product": primary_product,
                    "products": product_ids,
                    "query_type": query_type.value,
                    "web_doc_url": web_doc_result.url,
                }
                return
        # === End Web Doc Fast Path ===

        # 3. 질문 유형 분류
        query_type = self.query_type_classifier.classify(request.message)

        # 4. 통합 검색
        search_context = await self._multi_product_search(
            query=request.message,
            product_ids=product_ids,
            query_type=query_type,
        )

        yield {
            "type": "search_progress",
            "product": primary_product,
            "products": product_ids,
            "step": "search_complete",
            "progress": 0.6,
        }

        # 저관련 경고 (best score < 0.3)
        if search_context.structured_results:
            best_score = search_context.structured_results[0].relevance_score
            if best_score < 0.3:
                yield {
                    "type": "low_relevance_warning",
                    "message": "検索結果の関連性が低い可能性があります。質問を具体的にしてお試しください。",
                    "best_score": best_score,
                    "searched_products": product_ids,
                }

        # 5. 응답 생성
        if query_type != QueryType.FREEFORM and search_context.structured_results:
            template_response = self.template_builder.build(
                query=request.message,
                query_type=query_type,
                results=search_context.structured_results,
                language=request.language or "ja",
            )
            if template_response:
                table_supplement = self._build_table_supplement(search_context.structured_results)
                if table_supplement:
                    template_response += table_supplement
                yield {
                    "type": "template_response",
                    "content": template_response,
                    "query_type": query_type.value,
                }
                yield self._build_sources_event(search_context.structured_results)
                yield {
                    "type": "done",
                    "processing_time_ms": int((time.time() - start) * 1000),
                    "product": primary_product,
                    "products": product_ids,
                    "query_type": query_type.value,
                }
                return

        # 비정형: LLM 스트리밍 생성
        yield {
            "type": "search_progress",
            "product": primary_product,
            "products": product_ids,
            "step": "generating",
            "progress": 0.7,
        }

        full_response = ""
        async for token in self._stream_llm(
            request.message, primary_product, search_context, request.language or "ja",
            history=request.history,
        ):
            full_response += token
            yield {"type": "llm_token", "token": token}

        # LLM 응답 후 테이블 보충 (LLM이 재현하지 못한 표 데이터 추가)
        if search_context.structured_results:
            table_supplement = self._build_table_supplement(search_context.structured_results)
            if table_supplement:
                yield {"type": "llm_token", "token": table_supplement}
                full_response += table_supplement

        # 사후 검증
        if full_response and search_context.structured_results:
            verification = self.response_verifier.verify(
                full_response,
                search_context.structured_results,
            )
            if verification:
                yield {
                    "type": "verification",
                    "sentences": [
                        {
                            "text": v.text,
                            "level": v.level.value,
                            "similarity": v.similarity,
                            "source_chunk": v.source_chunk,
                            "source_doc": v.source_doc,
                        }
                        for v in verification
                    ],
                }

        # 관련 엔티티 그래프 추출 (Neo4j → ReactFlow JSON)
        try:
            from .graph_visualization_service import get_graph_visualization_service
            graph_service = get_graph_visualization_service()
            graph_data = await graph_service.get_query_graph(
                query=request.message, product_ids=product_ids, limit=15
            )
            if graph_data and graph_data.get("nodes"):
                yield {
                    "type": "graph_data",
                    "nodes": graph_data["nodes"],
                    "edges": graph_data["edges"],
                }
        except Exception as e:
            logger.debug(f"Graph data extraction skipped: {e}")

        yield self._build_sources_event(search_context.structured_results)
        yield {
            "type": "done",
            "processing_time_ms": int((time.time() - start) * 1000),
            "product": primary_product,
            "products": product_ids,
            "query_type": query_type.value,
        }

    # ------------------------------------------------------------------
    # Parallel Comparison Streaming (DAG: 병렬 검색 → 합성)
    # ------------------------------------------------------------------

    async def _stream_parallel_comparison(
        self,
        request: AgenticRAGRequest,
        pattern: QueryPatternResult,
        start: float,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """비교 쿼리를 병렬 검색 + LLM 합성으로 처리"""
        subjects = pattern.subjects
        language = request.language or "ja"
        dag_id = f"dag-{uuid.uuid4().hex[:8]}"

        # DAG 구조 정의
        task_ids = [f"search-{i}" for i in range(len(subjects))]
        synthesis_id = "synthesis"
        dag_tasks = [
            {
                "task_id": tid,
                "description": f"Search: {subj}",
                "agent_type": "rag",
                "status": "pending",
                "dependencies": [],
            }
            for tid, subj in zip(task_ids, subjects)
        ] + [
            {
                "task_id": synthesis_id,
                "description": "Compare & Synthesize",
                "agent_type": "rag",
                "status": "pending",
                "dependencies": task_ids,
            },
        ]

        # DAG 구조 전송
        yield {
            "type": "trace_data",
            "trace_data": {
                "trace_id": dag_id,
                "dag": {
                    "tasks": dag_tasks,
                    "execution_batches": [task_ids, [synthesis_id]],
                    "parallelism_type": "full",
                },
            },
        }

        # 각 subject별 제품 라우팅 + 검색 (병렬)
        query_type = self.query_type_classifier.classify(request.message)
        llm_sem = asyncio.Semaphore(2)  # vLLM 동시 요청 제한

        async def _search_subject(idx: int, subject: str):
            """개별 subject 검색: 라우팅 → 에이전트 검색"""
            async with llm_sem:
                # 원본 질문 전체를 검색 쿼리로 사용 (subject는 라우팅 힌트)
                search_query = request.message

                # subject 기반으로 제품 라우팅
                sub_result = await self.query_router.classify(
                    subject, language, history=request.history,
                )
                pids = []
                if sub_result.decision == RouterDecision.CONFIRMED:
                    pids = [sub_result.product]
                elif sub_result.all_scores:
                    top_pid = max(sub_result.all_scores, key=sub_result.all_scores.get)
                    pids = [top_pid]
                # 명시적 제품 선택이 있으면 우선
                if request.effective_products:
                    pids = request.effective_products

                if not pids:
                    logger.info(f"Parallel search: no products for subject '{subject}'")
                    return idx, subject, None

                ctx = await self._multi_product_search(
                    query=search_query,
                    product_ids=pids,
                    query_type=query_type,
                )
                return idx, subject, ctx

        # 검색 시작 이벤트
        for i, tid in enumerate(task_ids):
            yield _task_status_event(tid, "running")

        # 병렬 실행
        search_tasks = [
            _search_subject(i, subj) for i, subj in enumerate(subjects)
        ]
        results = await asyncio.gather(*search_tasks, return_exceptions=True)

        # 검색 완료 이벤트 + context 수집
        contexts: List[str] = []
        all_search_results: List = []
        product_ids_used: List[str] = []
        _search_start = time.time()
        _completed_indices: set = set()
        for result in results:
            if isinstance(result, (Exception, BaseException)):
                logger.warning(
                    f"Parallel search error: {type(result).__name__}: {result}",
                    exc_info=result,
                )
                continue
            idx, subject, ctx = result
            _completed_indices.add(idx)
            tid = task_ids[idx]
            _elapsed = int((time.time() - _search_start) * 1000)
            n_results = len(ctx.structured_results) if ctx and ctx.structured_results else 0
            yield _task_status_event(tid, "completed", latency_ms=_elapsed)
            # Evaluation: 검색 결과 품질 평가
            yield {
                "type": "trace_data",
                "trace_data": {
                    "evaluations": {
                        tid: {
                            "passed": n_results > 0,
                            "score": min(n_results / 5.0, 1.0),
                            "issues": [] if n_results > 0 else [f"No results for '{subject}'"],
                        }
                    }
                },
            }
            if ctx and ctx.structured_results:
                all_search_results.extend(ctx.structured_results)
                section = self._build_llm_context(ctx.structured_results)
                contexts.append(f"【{subject}】\n{section}")
                if ctx.product and ctx.product not in product_ids_used:
                    product_ids_used.append(ctx.product)

        # 미완료 태스크에 failed 상태 전송
        for i, tid in enumerate(task_ids):
            if i not in _completed_indices:
                yield _task_status_event(tid, "failed")

        if not contexts:
            # 병렬 검색 실패 → 단일 모드 fallback (원래 stream_chat 흐름)
            logger.info("Parallel comparison: no results, falling back to single mode")
            return

        # 합성タスク開始
        _synth_start = time.time()
        yield _task_status_event(synthesis_id, "running")

        # LLM 合成: 各 subject の検索結果をまとめて比較回答生成
        combined_context = "\n\n".join(contexts)
        if len(combined_context) > self._MAX_LLM_CONTEXT_CHARS:
            combined_context = combined_context[: self._MAX_LLM_CONTEXT_CHARS] + "..."

        comparison_prompt = (
            f"以下の情報を基に、{' と '.join(subjects)} を比較してください。\n\n"
            f"質問: {request.message}\n\n{combined_context}"
        )

        primary_product = product_ids_used[0] if product_ids_used else "auto"
        full_response = ""
        async for token in self._stream_llm_from_context(
            comparison_prompt, primary_product, combined_context, language,
            history=request.history,
        ):
            full_response += token
            yield {"type": "llm_token", "token": token}

        _synth_elapsed = int((time.time() - _synth_start) * 1000)
        yield _task_status_event(synthesis_id, "completed", latency_ms=_synth_elapsed)
        # Evaluation: 합성 결과 평가
        yield {
            "type": "trace_data",
            "trace_data": {
                "evaluations": {
                    synthesis_id: {
                        "passed": len(full_response) > 50,
                        "score": min(len(full_response) / 500.0, 1.0),
                        "issues": [] if len(full_response) > 50 else ["Response too short"],
                    }
                }
            },
        }

        yield self._build_sources_event(all_search_results)
        yield {
            "type": "done",
            "processing_time_ms": int((time.time() - start) * 1000),
            "product": primary_product,
            "products": product_ids_used,
            "query_type": query_type.value,
            "dag_id": dag_id,
        }

    # ------------------------------------------------------------------
    # Pipeline Streaming (DAG: 순차 실행, Task2에 Task1 결과 전달)
    # ------------------------------------------------------------------

    async def _stream_pipeline(
        self,
        request: AgenticRAGRequest,
        pattern: QueryPatternResult,
        start: float,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """순차 쿼리를 파이프라인 실행으로 처리"""
        tasks_desc = pattern.subjects
        language = request.language or "ja"
        dag_id = f"dag-{uuid.uuid4().hex[:8]}"

        # DAG 구조: task-0 → task-1 → ...
        task_ids = [f"task-{i}" for i in range(len(tasks_desc))]
        dag_tasks = []
        for i, (tid, desc) in enumerate(zip(task_ids, tasks_desc)):
            dag_tasks.append({
                "task_id": tid,
                "description": desc,
                "agent_type": "rag",
                "status": "pending",
                "dependencies": [task_ids[i - 1]] if i > 0 else [],
            })

        yield {
            "type": "trace_data",
            "trace_data": {
                "trace_id": dag_id,
                "dag": {
                    "tasks": dag_tasks,
                    "execution_batches": [[tid] for tid in task_ids],
                    "parallelism_type": "pipeline",
                },
            },
        }

        # 순차 실행
        query_type = self.query_type_classifier.classify(request.message)
        prev_context = ""
        all_search_results: List = []
        product_ids_used: List[str] = []

        for i, (tid, task_text) in enumerate(zip(task_ids, tasks_desc)):
            _step_start = time.time()
            yield _task_status_event(tid, "running")

            # 이전 태스크 결과를 컨텍스트에 추가
            enriched_query = task_text
            if prev_context:
                enriched_query = f"{task_text}\n\n[前の結果]\n{prev_context}"

            # 제품 라우팅
            sub_result = await self.query_router.classify(
                task_text, language, history=request.history,
            )
            pids = []
            if sub_result.decision == RouterDecision.CONFIRMED:
                pids = [sub_result.product]
            elif sub_result.all_scores:
                top_pid = max(sub_result.all_scores, key=sub_result.all_scores.get)
                pids = [top_pid]
            if request.effective_products:
                pids = request.effective_products

            n_results = 0
            if pids:
                ctx = await self._multi_product_search(
                    query=enriched_query,
                    product_ids=pids,
                    query_type=query_type,
                )
                if ctx and ctx.structured_results:
                    n_results = len(ctx.structured_results)
                    all_search_results.extend(ctx.structured_results)
                    prev_context = self._build_llm_context(ctx.structured_results)
                    if ctx.product and ctx.product not in product_ids_used:
                        product_ids_used.append(ctx.product)

            _step_elapsed = int((time.time() - _step_start) * 1000)
            yield _task_status_event(tid, "completed", latency_ms=_step_elapsed)
            yield {
                "type": "trace_data",
                "trace_data": {
                    "evaluations": {
                        tid: {
                            "passed": n_results > 0,
                            "score": min(n_results / 5.0, 1.0),
                            "issues": [] if n_results > 0 else [f"No results for '{task_text}'"],
                        }
                    }
                },
            }

        # 最終応答: LLM ストリーミング
        if prev_context:
            if len(prev_context) > self._MAX_LLM_CONTEXT_CHARS:
                prev_context = prev_context[: self._MAX_LLM_CONTEXT_CHARS] + "..."
            primary_product = product_ids_used[0] if product_ids_used else "auto"
            async for token in self._stream_llm_from_context(
                request.message, primary_product, prev_context, language,
                history=request.history,
            ):
                yield {"type": "llm_token", "token": token}
        else:
            yield {
                "type": "error",
                "message": "パイプライン実行で結果が得られませんでした。",
            }
            return

        yield self._build_sources_event(all_search_results)
        yield {
            "type": "done",
            "processing_time_ms": int((time.time() - start) * 1000),
            "product": primary_product,
            "products": product_ids_used,
            "query_type": query_type.value,
            "dag_id": dag_id,
        }

    async def _generate_with_llm(
        self,
        query: str,
        product_id: str,
        search_context,
        language: str,
        history=None,
    ) -> Optional[str]:
        """LLM으로 비정형 응답 생성"""
        try:
            from .learning_llm_service import get_learning_llm_service
            llm_service = get_learning_llm_service()

            if not llm_service:
                logger.warning("LLM skipped (generate): get_learning_llm_service() returned None")
            elif not llm_service.is_available:
                logger.warning(
                    f"LLM skipped (generate): is_available=False "
                    f"(enabled={llm_service.enabled}, initialized={llm_service._is_initialized})"
                )

            if not llm_service or not llm_service.is_available:
                if search_context.structured_results:
                    return self._fallback_from_structured(search_context.structured_results)
                return None

            adapter_product = self._map_product_for_llm(product_id)
            context = self._build_llm_context(search_context.structured_results, history=history)
            logger.info(
                f"LLM generate: product={product_id}, adapter_product={adapter_product}, "
                f"context_len={len(context)}"
            )

            result = await llm_service.generate(
                question=query,
                context=context,
                max_tokens=2048,
                temperature=0.3,
                product=adapter_product,
            )

            if result and result.get("response"):
                return result["response"]

        except Exception as e:
            logger.warning(f"LLM generation failed: {type(e).__name__}: {e}")

        if search_context.structured_results:
            return self._fallback_from_structured(search_context.structured_results)
        return None

    async def _stream_llm(
        self,
        query: str,
        product_id: str,
        search_context,
        language: str,
        history=None,
    ) -> AsyncGenerator[str, None]:
        """LLM 스트리밍 생성"""
        try:
            from .learning_llm_service import get_learning_llm_service
            llm_service = get_learning_llm_service()

            if not llm_service:
                logger.warning("LLM skipped (stream): get_learning_llm_service() returned None")
            elif not llm_service.is_available:
                logger.warning(
                    f"LLM skipped (stream): is_available=False "
                    f"(enabled={llm_service.enabled}, initialized={llm_service._is_initialized})"
                )

            if not llm_service or not llm_service.is_available:
                fallback = self._fallback_from_structured(
                    search_context.structured_results
                ) if search_context.structured_results else "情報が見つかりませんでした。"
                yield fallback
                return

            adapter_product = self._map_product_for_llm(product_id)
            context = self._build_llm_context(search_context.structured_results, history=history)
            logger.info(
                f"LLM streaming: product={product_id}, adapter_product={adapter_product}, "
                f"context_len={len(context)}"
            )

            async for token in llm_service.generate_stream(
                question=query,
                context=context,
                max_tokens=2048,
                temperature=0.3,
                product=adapter_product,
            ):
                yield token

        except Exception as e:
            logger.warning(f"LLM streaming failed: {type(e).__name__}: {e}")
            fallback = self._fallback_from_structured(
                search_context.structured_results
            ) if search_context.structured_results else f"生成エラー: {str(e)}"
            yield fallback

    # =========================================================================
    # vLLM Direct Search (QLoRA 학습 지식 기반 직접 응답)
    # =========================================================================

    # vLLM 직접 응답의 최소 품질 기준 (문자 수)
    _VLLM_DIRECT_MIN_CHARS = 80

    async def _try_vllm_direct_search(
        self,
        request: AgenticRAGRequest,
        primary_product: str,
        product_ids: List[str],
        start: float,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        vLLM 직접 검색: QLoRA 학습된 모델에 RAG 컨텍스트 없이 직접 질문.

        학습된 도메인 지식이 있으면 즉시 응답하고, 없으면 빈 스트림(fallthrough).
        """
        try:
            from .learning_llm_service import get_learning_llm_service
            llm_service = get_learning_llm_service()

            if not llm_service or not llm_service.is_available:
                logger.debug("vLLM direct search skipped: service unavailable")
                return

            adapter_product = self._map_product_for_llm(primary_product)
            language = request.language or "ja"

            # 대화 이력 포함
            history_section = self._format_history_for_context(request.history)

            # vLLM에 RAG 컨텍스트 없이 직접 질문 (학습된 지식만 사용)
            direct_context = (
                f"あなたは{adapter_product}製品の専門家です。"
                f"学習済みの知識のみを使って、正確に回答してください。"
                f"確信がない場合は「情報が不足しています」と回答してください。"
            )
            if history_section:
                direct_context = history_section + "\n\n" + direct_context

            logger.info(
                f"vLLM direct search: product={primary_product}, "
                f"adapter={adapter_product}, query={request.message[:80]}"
            )

            yield {
                "type": "search_progress",
                "product": primary_product,
                "products": product_ids,
                "step": "vllm_direct_search",
                "progress": 0.25,
            }

            full_response = ""
            repetition_detected = False
            async for token in llm_service.generate_stream(
                question=request.message,
                context=direct_context,
                max_tokens=2048,
                temperature=0.3,
                product=adapter_product,
                repetition_penalty=1.15,
            ):
                full_response += token
                yield {"type": "llm_token", "token": token}

                # 스트리밍 중 반복 감지: 200자 이상 생성 후 체크
                if len(full_response) > 200:
                    tail = full_response[-150:]
                    head = full_response[:-150]
                    if tail in head:
                        logger.warning(
                            f"vLLM direct search: repetition detected at {len(full_response)} chars, stopping"
                        )
                        repetition_detected = True
                        full_response = full_response[:-150]
                        break

            # 응답 품질 검증: 충분한 내용이 있는지 확인
            stripped = full_response.strip()
            _insufficient_markers = [
                "情報が不足", "わかりません", "不明です",
                "情報がありません", "確認できません",
                "該当する情報", "見つかりません",
            ]
            is_insufficient = (
                len(stripped) < self._VLLM_DIRECT_MIN_CHARS
                or any(m in stripped for m in _insufficient_markers)
            )

            if is_insufficient:
                # vLLM 응답 불충분 → fallthrough (이미 출력된 토큰 클리어)
                logger.info(
                    f"vLLM direct search: insufficient response "
                    f"(len={len(stripped)}), falling through to RAG"
                )
                # 이미 스트리밍된 불충분 응답을 클리어하고 RAG로 전환
                yield {
                    "type": "vllm_direct_fallthrough",
                    "reason": "insufficient_response",
                    "response_length": len(stripped),
                }
                return

            # vLLM 직접 응답 성공
            query_type = self.query_type_classifier.classify(request.message)

            yield {
                "type": "sources",
                "results": [{
                    "doc_name": f"Learning LLM ({adapter_product})",
                    "source_page": "",
                    "content": stripped[:200],
                    "score": 1.0,
                    "domain": "learning_llm",
                    "product": primary_product,
                }],
                "total": 1,
            }
            yield {
                "type": "done",
                "processing_time_ms": int((time.time() - start) * 1000),
                "product": primary_product,
                "products": product_ids,
                "query_type": query_type.value,
                "search_method": "vllm_direct",
            }

        except Exception as e:
            logger.warning(f"vLLM direct search failed: {type(e).__name__}: {e}")
            # 예외 발생 시 조용히 fallthrough → 기존 RAG 파이프라인 진행

    # =========================================================================
    # Web Doc Fast Path (docs.tmaxsoft.com 실시간 검색)
    # =========================================================================

    # 구 ProductId(라우터 출력) → web doc index product_id 매핑 (1:N)
    # openframe_mvs는 MVS 본체 + 하위 컴포넌트(HiDB, NDB, TACF, OSI, AIM) 포함
    _LEGACY_TO_WEB_DOC_PIDS: Dict[str, List[str]] = {
        "openframe_mvs": [
            "mvs_openframe_7.1",
            "openframe_hidb_7", "openframe_ndb_7",
            "openframe_tacf_7", "openframe_aim_7",
        ],
        "openframe_base": ["mvs_openframe_7.1"],
        "msp_openframe": ["msp_openframe_7.3"],
        "vos3_openframe": ["vos3_openframe_2.0"],
        "tibero7": ["tibero_7fixset01"],
        "ofasm": ["ofasm_4"],
        "ofcobol": ["ofcobol_4"],
        "xsp_openframe": ["xsp_openframe_7.3"],
        "tmax": ["tmax_6.0"],
    }

    def _search_web_doc(
        self,
        query: str,
        language: str,
        product_ids: List[str],
    ) -> Optional[WebDocSearchResult]:
        """웹 문서 인덱스 검색. score >= threshold이면 결과 반환."""
        try:
            # 라우터 product_id → web doc index product_id 변환 (1:N)
            mapped_pids = []
            for pid in (product_ids or []):
                mapped_list = self._LEGACY_TO_WEB_DOC_PIDS.get(pid)
                if mapped_list:
                    mapped_pids.extend(mapped_list)
                else:
                    mapped_pids.append(pid)
            results = self.web_doc_search.search(
                query=query,
                language=language,
                product_ids=mapped_pids if mapped_pids else None,
                top_k=1,
            )
            if results:
                logger.debug(
                    f"Web doc top: score={results[0].normalized_score:.4f}, "
                    f"title='{results[0].title}'"
                )
            if results and results[0].normalized_score >= WEB_DOC_THRESHOLD:
                logger.info(
                    f"Web doc match: score={results[0].normalized_score:.4f}, "
                    f"url={results[0].url}"
                )
                return results[0]
        except Exception as e:
            logger.debug(f"Web doc search skipped: {e}")
        return None

    async def _fetch_web_doc_content(self, url: str) -> Optional[str]:
        """docs.tmaxsoft.com 페이지를 fetch하여 <article> 내용 추출"""
        try:
            import httpx
            async with httpx.AsyncClient(
                timeout=10.0,
                verify=False,
                follow_redirects=True,
            ) as client:
                resp = await client.get(url)
                if resp.status_code != 200:
                    logger.warning(f"Web doc fetch failed: HTTP {resp.status_code}")
                    return None

            html = resp.text

            # <article> 태그에서 내용 추출 (정규식 기반)
            import re as _re
            article_match = _re.search(r'<article[^>]*>(.*?)</article>', html, _re.DOTALL)
            if article_match:
                article_html = article_match.group(1)
                # HTML 태그 제거, 줄바꿈 정리
                text = _re.sub(r'<[^>]+>', '\n', article_html)
                text = _re.sub(r'\n\s*\n+', '\n\n', text).strip()
                return text

            # fallback: body에서 추출
            body_match = _re.search(r'<body[^>]*>(.*?)</body>', html, _re.DOTALL)
            if body_match:
                text = _re.sub(r'<[^>]+>', '\n', body_match.group(1))
                text = _re.sub(r'\n\s*\n+', '\n\n', text).strip()
                return text[:5000]

        except Exception as e:
            logger.warning(f"Web doc fetch error: {e}")
        return None

    async def _try_web_doc_fast_path(
        self,
        request: "AgenticRAGRequest",
        product_ids: List[str],
        primary_product: str,
        router_result: "RouterResult",
        start: float,
    ) -> Optional[AgenticRAGResponse]:
        """chat()용 Web Doc Fast Path. score >= 0.9이면 응답 생성."""
        web_doc_result = self._search_web_doc(
            request.message, request.language or "ja", product_ids,
        )
        if not web_doc_result:
            return None

        web_content = await self._fetch_web_doc_content(web_doc_result.url)
        if not web_content:
            return None  # fetch 실패 → PDF RAG fallback

        query_type = self.query_type_classifier.classify(request.message)

        # Web content를 LLM context로 사용하여 응답 생성
        web_context = (
            f"[Web Documentation: {web_doc_result.title}]\n"
            f"URL: {web_doc_result.url}\n\n{web_content}"
        )
        if len(web_context) > self._MAX_LLM_CONTEXT_CHARS:
            web_context = web_context[:self._MAX_LLM_CONTEXT_CHARS] + "..."

        llm_response = await self._generate_with_llm_from_context(
            request.message, primary_product, web_context,
            request.language or "ja", history=request.history,
        )

        sources = ProductSources(
            web_doc=WebDocSource(
                url=web_doc_result.url,
                title=web_doc_result.title,
                component=web_doc_result.component,
                product_id=web_doc_result.product_id,
                score=web_doc_result.normalized_score,
                content_preview=web_content[:200],
                headings=web_doc_result.headings,
            ),
        )

        return AgenticRAGResponse(
            success=True,
            response=llm_response or web_content[:2000],
            product=primary_product,
            query_type=query_type,
            router_result=router_result,
            sources=sources,
            confidence=ConfidenceLevel.HIGH,
            processing_time_ms=int((time.time() - start) * 1000),
        )

    async def _generate_with_llm_from_context(
        self,
        query: str,
        product_id: str,
        context: str,
        language: str,
        history=None,
    ) -> Optional[str]:
        """사전 구축된 context로 LLM 응답 생성 (web doc용)"""
        try:
            from .learning_llm_service import get_learning_llm_service
            llm_service = get_learning_llm_service()
            if not llm_service or not llm_service.is_available:
                return None

            adapter_product = self._map_product_for_llm(product_id)
            history_section = self._format_history_for_context(history)
            full_context = (history_section + "\n\n" + context) if history_section else context

            result = await llm_service.generate(
                question=query,
                context=full_context,
                max_tokens=2048,
                temperature=0.3,
                product=adapter_product,
            )
            if result and result.get("response"):
                return result["response"]
        except Exception as e:
            logger.warning(f"LLM from web context failed: {e}")
        return None

    async def _stream_llm_from_context(
        self,
        query: str,
        product_id: str,
        context: str,
        language: str,
        history=None,
    ) -> AsyncGenerator[str, None]:
        """사전 구축된 context로 LLM 스트리밍 (web doc용)"""
        try:
            from .learning_llm_service import get_learning_llm_service
            llm_service = get_learning_llm_service()
            if not llm_service or not llm_service.is_available:
                yield context[:2000]  # LLM 없으면 원문 반환
                return

            adapter_product = self._map_product_for_llm(product_id)
            history_section = self._format_history_for_context(history)
            full_context = (history_section + "\n\n" + context) if history_section else context

            async for token in llm_service.generate_stream(
                question=query,
                context=full_context,
                max_tokens=2048,
                temperature=0.3,
                product=adapter_product,
            ):
                yield token
        except Exception as e:
            logger.warning(f"LLM streaming from web context failed: {e}")
            yield context[:2000]

    # =========================================================================
    # LLM Context Building
    # =========================================================================

    # LLM 컨텍스트 총 문자 수 제한 (모델 context window 고려, ~1500 tokens)
    _MAX_LLM_CONTEXT_CHARS = 4000
    _MAX_HISTORY_CHARS = 800

    def _build_llm_context(self, results, history=None) -> str:
        """검색 결과를 LLM 컨텍스트 문자열로 변환 (PDF 우선 + 대화 이력 + 테이블 포함, 예산 관리)"""
        # 대화 이력 포맷팅
        history_section = self._format_history_for_context(history)
        history_len = len(history_section)
        search_budget = self._MAX_LLM_CONTEXT_CHARS - history_len

        if not results:
            return history_section

        # PDF 우선: PDF가 있으면 요약본/학습데이터 제외
        results = _select_tiered_results(results, min_primary=1)

        from .structured_knowledge_store import enrich_content_with_tables

        top_score = results[0].relevance_score if results else 0
        threshold = top_score * 0.5
        filtered = [r for r in results[:5] if r.relevance_score >= threshold]
        if not filtered:
            filtered = results[:1]

        parts = []
        total_chars = 0
        per_result_limit = min(2000, search_budget // max(len(filtered), 1))

        for i, r in enumerate(filtered, 1):
            if total_chars >= search_budget:
                break
            content = enrich_content_with_tables(r)
            if len(content) > per_result_limit:
                # 이미지 마크다운(![...)은 끝에 위치 → 분리 후 텍스트만 잘라냄
                img_marker = "\n\n!["
                img_idx = content.find(img_marker)
                if img_idx > 0:
                    text_part = content[:img_idx]
                    img_part = content[img_idx:]
                    text_budget = per_result_limit - len(img_part)
                    if text_budget > 200:
                        content = text_part[:text_budget] + "..." + img_part
                    else:
                        content = content[:per_result_limit] + "..."
                else:
                    content = content[:per_result_limit] + "..."
            part = content
            parts.append(part)
            total_chars += len(part)

        search_section = "\n\n---\n\n".join(parts)

        if history_section and search_section:
            # 검색 결과를 앞에 배치 → _extract_core_content() 절단 시 검색 결과 보존
            return search_section + "\n\n===会話履歴===\n" + history_section
        return search_section or history_section

    def _format_history_for_context(self, history) -> str:
        """대화 이력을 LLM 컨텍스트용 텍스트로 포맷 (최근 2~3턴, 예산 내)"""
        if not history:
            return ""

        # 최근 3턴(user+assistant 쌍) = 최대 6메시지를 역순으로 수집
        recent_messages = []
        for msg in reversed(history):
            if len(recent_messages) >= 6:
                break
            role = msg.get("role") if isinstance(msg, dict) else getattr(msg, "role", None)
            content = msg.get("content") if isinstance(msg, dict) else getattr(msg, "content", None)
            if role and content:
                recent_messages.append((role, content))

        if not recent_messages:
            return ""

        # 원래 순서로 복원
        recent_messages.reverse()

        lines = ["[会話履歴]"]
        total = len(lines[0])
        for role, content in recent_messages:
            label = "ユーザー" if role == "user" else "アシスタント"
            # 개별 메시지 길이 제한
            truncated = content[:300] if len(content) > 300 else content
            line = f"{label}: {truncated}"
            if total + len(line) + 1 > self._MAX_HISTORY_CHARS:
                break
            lines.append(line)
            total += len(line) + 1

        if len(lines) <= 1:
            return ""
        return "\n".join(lines)

    def _fallback_from_structured(self, results) -> str:
        """구조화 결과로 폴백 응답 생성 (PDF 우선 + 마크다운 포맷)"""
        if not results:
            return ""

        # PDF 우선: PDF가 있으면 요약본/학습데이터 제외
        results = _select_tiered_results(results, min_primary=1)

        from .structured_knowledge_store import enrich_content_with_tables
        from .template_response_builder import format_as_markdown

        top_score = results[0].relevance_score if results else 0
        threshold = top_score * 0.5
        filtered = [r for r in results[:3] if r.relevance_score >= threshold]
        if not filtered:
            filtered = results[:1]
        parts = []
        for r in filtered:
            content = format_as_markdown(_clean_inline_metadata(enrich_content_with_tables(r)))
            if len(content) > 2000:
                cut = content[:2000]
                last_break = max(cut.rfind('。'), cut.rfind('\n'), cut.rfind('. '))
                if last_break > 800:
                    cut = cut[:last_break + 1]
                content = cut + "\n..."
            parts.append(f"### {r.title}\n\n{content}")

        output = "\n\n---\n\n".join(parts)

        # 중복 행 제거 (여러 검색 결과 간 페이지 겹침으로 인한 중복 방지)
        seen_lines: set = set()
        deduped: list = []
        for line in output.split('\n'):
            stripped = line.strip()
            if len(stripped) > 30:
                if stripped in seen_lines:
                    continue
                seen_lines.add(stripped)
            deduped.append(line)
        return '\n'.join(deduped)

    def _build_table_supplement(self, results) -> str:
        """LLM 응답 후 검색 결과의 테이블과 이미지를 보충 자료로 추가"""
        from .structured_knowledge_store import (
            _resolve_pdf_path_and_page,
            StructuredKnowledgeStore,
        )

        tables_md: list = []
        images_md: list = []
        seen_tables: set = set()
        seen_images: set = set()

        # 최상위 결과만 사용 + 최소 점수 요건 (저관련 결과에서 무관한 테이블/이미지 추출 방지)
        for r in results[:1]:
            if r.relevance_score < 3.0:
                continue
            pdf_path, page_num = _resolve_pdf_path_and_page(r)
            if not pdf_path or page_num < 0:
                continue
            try:
                import pymupdf
                doc = pymupdf.open(pdf_path)
                product_id = r.product or "unknown"
                # 해당 페이지 + 다음 1페이지만 스캔 (인접 무관 테이블 방지)
                for p in range(page_num, min(page_num + 2, len(doc))):
                    try:
                        tables = doc[p].find_tables()
                        for table in tables:
                            data = table.extract()
                            md = StructuredKnowledgeStore._table_to_markdown(data)
                            if md and md not in seen_tables:
                                seen_tables.add(md)
                                tables_md.append(md)
                    except Exception:
                        pass
                    try:
                        imgs = StructuredKnowledgeStore._extract_page_images(
                            doc, p, product_id,
                            pdf_name=os.path.basename(pdf_path),
                        )
                        for img_md in imgs:
                            if img_md not in seen_images:
                                seen_images.add(img_md)
                                images_md.append(img_md)
                    except Exception:
                        pass
                doc.close()
            except Exception:
                continue

        parts: list = []
        if tables_md:
            parts.append("**参考テーブル:**\n\n" + "\n\n".join(tables_md[:5]))
        if images_md:
            parts.append("**参考図:**\n\n" + "\n\n".join(images_md[:8]))

        if not parts:
            return ""

        return "\n\n---\n\n" + "\n\n".join(parts)

    def _map_product_for_llm(self, product_id: str) -> str:
        """동적 product_id를 VLLMAdapter가 인식할 수 있는 제품명으로 변환"""
        if product_id in _DYNAMIC_TO_ADAPTER_MAP:
            return _DYNAMIC_TO_ADAPTER_MAP[product_id]
        # Fallback: '_' 기준 첫 부분 (family) 사용
        family = product_id.split("_")[0] if "_" in product_id else product_id
        return family

    def _build_sources(self, results) -> ProductSources:
        """검색 결과에서 출처 정보 생성 (PDF 우선: PDF가 있으면 요약본 제외)"""
        tiered = _select_tiered_results(results, min_primary=1)
        vector_sources = []
        for i, r in enumerate(tiered[:5]):
            vector_sources.append(VectorSource(
                chunk_id=f"structured_{i}",
                doc_id=r.source_file or f"doc_{i}",
                doc_name=r.source_file or "",
                content=r.content[:200] if r.content else "",
                score=r.relevance_score,
                product=r.product or r.domain,
            ))
        return ProductSources(vector_search=vector_sources)

    def _build_sources_event(self, results) -> Dict[str, Any]:
        """출처 정보 SSE 이벤트 생성 (PDF 우선: PDF가 있으면 요약본 제외)"""
        tiered = _select_tiered_results(results, min_primary=1)
        sources = []
        for r in tiered[:5]:
            sources.append({
                "doc_name": r.source_file or "",
                "source_page": r.source_page or "",
                "content": r.content[:200] if r.content else "",
                "score": r.relevance_score,
                "domain": r.domain,
                "product": r.product,
            })
        return {
            "type": "sources",
            "results": sources,
            "total": len(results),
        }

    # =========================================================================
    # Code Agent Branch
    # =========================================================================

    async def _stream_code_agent(
        self,
        request: AgenticRAGRequest,
        product_ids: List[str],
        router_result: RouterResult,
        start: float,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        Code Agent 스트리밍 브랜치.
        제품 컨텍스트 + 코드 생성 시스템 프롬프트로 LLM 스트리밍.
        """
        primary_product = product_ids[0] if product_ids else "auto"

        yield {
            "type": "search_progress",
            "product": primary_product,
            "products": product_ids,
            "step": "code_search",
            "progress": 0.3,
        }

        # 제품 컨텍스트 수집
        search_context = await self._multi_product_search(
            query=request.message,
            product_ids=product_ids,
            query_type=QueryType.FREEFORM,
        )

        yield {
            "type": "search_progress",
            "product": primary_product,
            "products": product_ids,
            "step": "code_generating",
            "progress": 0.6,
        }

        # 코드 시스템 프롬프트 로드
        try:
            from ..agents.middleware.code_middleware import CODE_SYSTEM_PROMPT
            code_prompt = CODE_SYSTEM_PROMPT
        except ImportError:
            code_prompt = "You are an expert code generation assistant."

        # 검색 결과를 코드 컨텍스트로 변환
        product_context = self._build_llm_context(
            search_context.structured_results, history=request.history,
        )
        code_context = (
            f"{code_prompt}\n\n"
            f"## Product Documentation Context\n\n{product_context}\n\n"
            f"## Instructions\n"
            f"Based on the above product documentation, generate code or provide "
            f"code examples that address the user's request. Include comments "
            f"explaining the code and reference the relevant product documentation."
        )

        if len(code_context) > self._MAX_LLM_CONTEXT_CHARS * 2:
            code_context = code_context[:self._MAX_LLM_CONTEXT_CHARS * 2]

        # LLM 스트리밍
        full_response = ""
        async for token in self._stream_llm_from_context(
            request.message, primary_product, code_context,
            request.language or "ja", history=request.history,
        ):
            full_response += token
            yield {"type": "llm_token", "token": token}

        # 소스 정보
        if search_context.structured_results:
            yield self._build_sources_event(search_context.structured_results)

        yield {
            "type": "done",
            "processing_time_ms": int((time.time() - start) * 1000),
            "product": primary_product,
            "products": product_ids,
            "agent_mode": "code",
        }

    # =========================================================================
    # Planner Agent Branch
    # =========================================================================

    async def _stream_planner_agent(
        self,
        request: AgenticRAGRequest,
        product_ids: List[str],
        router_result: RouterResult,
        start: float,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        Planner Agent 스트리밍 브랜치.
        제품 컨텍스트 + 플랜 생성 + TracePanel(DAG) 이벤트 방출.
        """
        import uuid
        from datetime import datetime

        primary_product = product_ids[0] if product_ids else "auto"
        trace_id = str(uuid.uuid4())

        yield {
            "type": "search_progress",
            "product": primary_product,
            "products": product_ids,
            "step": "plan_search",
            "progress": 0.3,
        }

        # 제품 컨텍스트 수집
        search_context = await self._multi_product_search(
            query=request.message,
            product_ids=product_ids,
            query_type=QueryType.FREEFORM,
        )

        yield {
            "type": "plan_start",
            "trace_id": trace_id,
            "objective": request.message,
            "products": product_ids,
        }

        # Planner 시스템 프롬프트
        try:
            from ..agents.middleware.planner_middleware import PLANNER_SYSTEM_PROMPT
            planner_prompt = PLANNER_SYSTEM_PROMPT
        except ImportError:
            planner_prompt = "You are a strategic planning assistant."

        # 검색 결과를 플래너 컨텍스트로 변환
        product_context = self._build_llm_context(
            search_context.structured_results, history=request.history,
        )
        plan_context = (
            f"{planner_prompt}\n\n"
            f"## Product Documentation Context\n\n{product_context}\n\n"
            f"## Instructions\n"
            f"Based on the above product documentation, create a detailed execution plan "
            f"for the user's request. Break it down into clear, actionable steps with "
            f"dependencies. For each step, specify:\n"
            f"- Step number and description\n"
            f"- Agent type (rag, code, or planner)\n"
            f"- Dependencies (which steps must complete first)\n"
            f"- Estimated complexity (low, medium, high)\n\n"
            f"Format as a numbered list of steps."
        )

        if len(plan_context) > self._MAX_LLM_CONTEXT_CHARS * 2:
            plan_context = plan_context[:self._MAX_LLM_CONTEXT_CHARS * 2]

        yield {
            "type": "search_progress",
            "product": primary_product,
            "products": product_ids,
            "step": "plan_generating",
            "progress": 0.6,
        }

        # LLM 스트리밍으로 플랜 생성
        full_response = ""
        async for token in self._stream_llm_from_context(
            request.message, primary_product, plan_context,
            request.language or "ja", history=request.history,
        ):
            full_response += token
            yield {"type": "llm_token", "token": token}

        # 플랜에서 단계 추출 → DAG 구조 생성
        plan_steps = self._parse_plan_steps(full_response)

        if plan_steps:
            # DAG 구조 생성
            tasks = []
            execution_batches = []
            current_batch = []

            for i, step in enumerate(plan_steps):
                task_id = f"step_{i + 1}"
                tasks.append({
                    "task_id": task_id,
                    "description": step["description"],
                    "agent_type": step.get("agent_type", "rag"),
                    "status": "completed",
                    "dependencies": step.get("dependencies", []),
                    "latency_ms": None,
                })
                current_batch.append(task_id)
                # 의존성이 있으면 새 배치 시작
                if step.get("dependencies"):
                    if current_batch[:-1]:
                        execution_batches.append(current_batch[:-1])
                    current_batch = [task_id]

            if current_batch:
                execution_batches.append(current_batch)

            parallelism = "none"
            if len(execution_batches) > 1:
                max_batch = max(len(b) for b in execution_batches)
                parallelism = "full" if max_batch > 1 else "pipeline"

            # TracePanel DAG 이벤트
            yield {
                "type": "trace_data",
                "trace_data": {
                    "trace_id": trace_id,
                    "dag": {
                        "tasks": tasks,
                        "execution_batches": execution_batches,
                        "parallelism_type": parallelism,
                    },
                },
            }

            # 각 단계별 plan_step 이벤트
            for i, step in enumerate(plan_steps):
                yield {
                    "type": "plan_step",
                    "step_index": i,
                    "total_steps": len(plan_steps),
                    "description": step["description"],
                    "agent_type": step.get("agent_type", "rag"),
                    "complexity": step.get("complexity", "medium"),
                }

        # 소스 정보
        if search_context.structured_results:
            yield self._build_sources_event(search_context.structured_results)

        yield {
            "type": "done",
            "processing_time_ms": int((time.time() - start) * 1000),
            "product": primary_product,
            "products": product_ids,
            "agent_mode": "planner",
            "total_steps": len(plan_steps) if plan_steps else 0,
        }

    def _parse_plan_steps(self, plan_text: str) -> List[Dict[str, Any]]:
        """LLM 플랜 응답에서 단계별 구조 추출"""
        steps = []
        if not plan_text:
            return steps

        # 번호 매긴 리스트 패턴 매칭 (1. xxx, 2. xxx, ...)
        step_pattern = re.compile(
            r'(?:^|\n)\s*(\d+)[.)]\s*(.+?)(?=\n\s*\d+[.)]|\Z)',
            re.DOTALL,
        )
        matches = step_pattern.findall(plan_text)

        if not matches:
            # 대시/불릿 리스트 패턴도 시도
            bullet_pattern = re.compile(
                r'(?:^|\n)\s*[-*•・]\s*\*?\*?(?:Step\s*\d*:?\s*)?(.+?)(?=\n\s*[-*•・]|\Z)',
                re.DOTALL | re.IGNORECASE,
            )
            bullet_matches = bullet_pattern.findall(plan_text)
            for i, desc in enumerate(bullet_matches[:10]):
                desc_clean = desc.strip().split('\n')[0].strip()
                if len(desc_clean) > 5:
                    steps.append({
                        "description": desc_clean[:200],
                        "agent_type": self._infer_step_agent_type(desc_clean),
                        "complexity": "medium",
                        "dependencies": [f"step_{i}"] if i > 0 else [],
                    })
            return steps

        for idx, (num, desc) in enumerate(matches[:10]):
            desc_clean = desc.strip().split('\n')[0].strip()
            if len(desc_clean) > 5:
                steps.append({
                    "description": desc_clean[:200],
                    "agent_type": self._infer_step_agent_type(desc_clean),
                    "complexity": "medium",
                    "dependencies": [f"step_{idx}"] if idx > 0 else [],
                })

        return steps

    def _infer_step_agent_type(self, description: str) -> str:
        """단계 설명에서 적절한 agent type 추론"""
        desc_lower = description.lower()
        code_indicators = {"code", "script", "implement", "program", "jcl", "cobol",
                           "コード", "スクリプト", "実装", "코드", "구현"}
        if any(kw in desc_lower for kw in code_indicators):
            return "code"
        plan_indicators = {"plan", "analyze", "design", "review",
                           "計画", "分析", "設計", "계획", "분석"}
        if any(kw in desc_lower for kw in plan_indicators):
            return "planner"
        return "rag"

    def _calculate_confidence(
        self,
        verification: Optional[List[VerifiedSentence]],
    ) -> ConfidenceLevel:
        """검증 결과 기반 전체 신뢰도 계산"""
        if not verification:
            return ConfidenceLevel.LOW

        verified_count = sum(
            1 for v in verification if v.level.value == "verified"
        )
        total = len(verification)

        if total == 0:
            return ConfidenceLevel.LOW

        ratio = verified_count / total
        if ratio >= 0.7:
            return ConfidenceLevel.HIGH
        elif ratio >= 0.4:
            return ConfidenceLevel.MEDIUM
        return ConfidenceLevel.LOW

    # =========================================================================
    # Special Agent Branch (Anthropic Claude API)
    # =========================================================================

    async def _stream_special_agent(
        self,
        request: AgenticRAGRequest,
        product_ids: List[str],
        router_result: RouterResult,
        start: float,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        Special Agent: 요약본 + PDF + Web Doc 검색 → Claude API 응답 생성.
        vLLM 완전 우회. Anthropic Claude API 사용.
        전체 제품을 대상으로 검색 (라우터 결과에 제한되지 않음).
        """
        primary_product = product_ids[0] if product_ids else "auto"
        language = request.language or "ja"

        # Special Agent는 전체 제품을 대상으로 검색
        try:
            from .manual_registry_service import get_manual_registry_service
            registry = get_manual_registry_service()
            all_product_ids = list(registry.get_all_products().keys())
        except Exception:
            all_product_ids = product_ids
        search_product_ids = all_product_ids if all_product_ids else product_ids

        yield {
            "type": "search_progress",
            "product": primary_product,
            "step": "special_search",
            "progress": 0.2,
        }

        # Phase 1: 3개 소스 병렬 검색 (전체 제품 대상)
        summary_task = self._search_summaries(request.message, search_product_ids)
        pdf_task = self._multi_product_search(
            request.message, search_product_ids, QueryType.FREEFORM,
        )
        web_task = self._search_web_docs(request.message, search_product_ids)

        summary_results, pdf_context, web_results = await asyncio.gather(
            summary_task, pdf_task, web_task,
        )

        yield {
            "type": "search_progress",
            "product": primary_product,
            "step": "special_generating",
            "progress": 0.6,
        }

        # Phase 2: 컨텍스트 조합
        context_parts: List[str] = []
        if summary_results:
            context_parts.append(f"## Summary Knowledge\n{summary_results}")
        if pdf_context and pdf_context.structured_results:
            pdf_text = self._build_llm_context(pdf_context.structured_results)
            context_parts.append(f"## PDF Documentation\n{pdf_text}")
        if web_results:
            context_parts.append(f"## Web Documentation\n{web_results}")
        combined = "\n\n".join(context_parts) or "No relevant documents found."

        # Phase 3: Claude API 스트리밍
        full_response = ""
        async for token in self._stream_claude_response(
            request.message, combined, language, history=request.history,
        ):
            full_response += token
            yield {"type": "llm_token", "token": token}

        # Phase 4: 소스 정보
        if pdf_context and pdf_context.structured_results:
            yield self._build_sources_event(pdf_context.structured_results)

        yield {
            "type": "done",
            "processing_time_ms": int((time.time() - start) * 1000),
            "product": primary_product,
            "products": product_ids,
            "agent_mode": "special",
            "search_method": "special_agent",
        }

    async def _search_summaries(self, query: str, product_ids: List[str]) -> str:
        """요약본(commands, error-codes, glossary 등) BM25 검색"""
        from .summary_bm25_service import get_summary_bm25_service
        from .summary_search_service import get_summary_search_service

        results: List[str] = []
        try:
            # BM25 검색
            bm25 = get_summary_bm25_service()
            bm25_results = await bm25.search(query, top_k=5)
            for r in bm25_results:
                doc = r.document
                source = doc.source_file if doc else ""
                content = doc.content[:500] if doc and doc.content else ""
                results.append(f"[{source}] {content}")

            # 에러/용어 보강
            summary_svc = get_summary_search_service()
            enriched = await summary_svc.enrich_query(query)
            if enriched != query:
                results.append(f"[Enriched] {enriched[len(query):]}")
        except Exception as e:
            logger.warning(f"Summary search error: {e}")

        return "\n\n".join(results) if results else ""

    async def _search_web_docs(self, query: str, product_ids: List[str]) -> str:
        """docs.tmaxsoft.com 웹 문서 검색"""
        from .web_doc_search_service import get_web_doc_search_service

        try:
            web_svc = get_web_doc_search_service()
            results = web_svc.search(query, product_ids=product_ids, top_k=3)
            parts: List[str] = []
            for r in results:
                parts.append(f"[{r.title}] ({r.url})\n{r.snippet[:300]}")
            return "\n\n".join(parts) if parts else ""
        except Exception as e:
            logger.warning(f"Web doc search error: {e}")
            return ""

    async def _stream_claude_response(
        self,
        query: str,
        context: str,
        language: str,
        history: Optional[List] = None,
    ) -> AsyncGenerator[str, None]:
        """Anthropic Claude API를 사용한 응답 생성 (vLLM 우회)"""
        import anthropic

        settings = get_api_settings()
        if not settings.ANTHROPIC_API_KEY:
            yield "Error: ANTHROPIC_API_KEY not configured."
            return

        client = anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)

        lang_map = {"ja": "Japanese", "ko": "Korean", "en": "English"}
        lang_name = lang_map.get(language, "Japanese")

        system_prompt = (
            f"You are an OpenFrame KMS expert assistant. "
            f"You have access to documentation from ALL OpenFrame products "
            f"(MVS, MSP, VOS3, OSC, OSI, HiDB, TACF, Batch, Base, etc.). "
            f"Answer based on the provided documentation context. "
            f"When comparing features across products or components, "
            f"synthesize information from multiple sources in the context. "
            f"If the context contains partial information, provide what is available "
            f"and clearly indicate what additional information would be helpful. "
            f"Use markdown formatting with headers, tables, and bullet points. "
            f"Respond in {lang_name}."
        )

        messages: List[Dict[str, str]] = []
        if history:
            for h in history[-6:]:
                role = h.role if hasattr(h, "role") else h.get("role", "user")
                content = h.content if hasattr(h, "content") else h.get("content", "")
                if role in ("user", "assistant"):
                    messages.append({"role": role, "content": content})
        messages.append({
            "role": "user",
            "content": f"Context:\n{context[:12000]}\n\nQuestion: {query}",
        })

        try:
            async with client.messages.stream(
                model=settings.SPECIAL_AGENT_MODEL,
                max_tokens=4096,
                system=system_prompt,
                messages=messages,
            ) as stream:
                async for text in stream.text_stream:
                    yield text
        except Exception as e:
            logger.error(f"Claude API error: {e}")
            yield f"Error generating response: {e}"


# =============================================================================
# Singleton
# =============================================================================

_service_instance: Optional[AgenticRAGService] = None


def get_agentic_rag_service() -> AgenticRAGService:
    """Get singleton AgenticRAGService"""
    global _service_instance
    if _service_instance is None:
        _service_instance = AgenticRAGService()
    return _service_instance


async def initialize_agentic_rag_service() -> AgenticRAGService:
    """Initialize AgenticRAGService"""
    global _service_instance
    _service_instance = AgenticRAGService()
    logger.info("AgenticRAGService initialized")
    return _service_instance
