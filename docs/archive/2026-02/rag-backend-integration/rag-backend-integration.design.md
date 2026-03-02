# PDCA Design: RAG Backend Integration

> **Feature**: rag-backend-integration
> **Plan Document**: `docs/01-plan/features/rag-backend-integration.plan.md`
> **Created**: 2026-02-03
> **Version**: v1.0
> **Status**: Design Phase

---

## 1. Design Overview

### 1.1 Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                      RAG Anti-Hallucination Architecture                         │
├─────────────────────────────────────────────────────────────────────────────────┤
│                                                                                  │
│  User Request (POST /api/v1/query/rag)                                          │
│      │                                                                           │
│      ▼                                                                           │
│  ┌────────────────────────────────────────────────────────────────────────┐     │
│  │                        RAGQueryRouter                                   │     │
│  │  app/api/routers/query_rag.py                                          │     │
│  │  ┌────────────────┐  ┌────────────────┐  ┌────────────────────────┐   │     │
│  │  │ Authentication │  │ Request        │  │ Response               │   │     │
│  │  │ (JWT/Cookie)   │  │ Validation     │  │ Formatting             │   │     │
│  │  └────────────────┘  └────────────────┘  └────────────────────────┘   │     │
│  └───────────────────────────────┬────────────────────────────────────────┘     │
│                                  │                                               │
│                                  ▼                                               │
│  ┌────────────────────────────────────────────────────────────────────────┐     │
│  │                   RAGAntiHallucinationService                           │     │
│  │  app/api/services/rag_anti_hallucination_service.py                    │     │
│  │                                                                         │     │
│  │  ┌─────────────────────────────────────────────────────────────────┐   │     │
│  │  │                      ImprovedRAG Wrapper                         │   │     │
│  │  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────────┐  │   │     │
│  │  │  │ Keyword     │  │ Score-based │  │ Mode Selection          │  │   │     │
│  │  │  │ Extraction  │  │ Search      │  │ (Direct/LLM/Hybrid)     │  │   │     │
│  │  │  └─────────────┘  └─────────────┘  └─────────────────────────┘  │   │     │
│  │  └─────────────────────────────────────────────────────────────────┘   │     │
│  │                                                                         │     │
│  │  ┌─────────────────────────────────────────────────────────────────┐   │     │
│  │  │                      Statistics Collector                        │   │     │
│  │  │  - Total queries      - Search time tracking                    │   │     │
│  │  │  - Mode usage stats   - LLM time tracking                       │   │     │
│  │  └─────────────────────────────────────────────────────────────────┘   │     │
│  └───────────────────────────────┬────────────────────────────────────────┘     │
│                                  │                                               │
│                  ┌───────────────┼───────────────┐                              │
│                  │               │               │                              │
│                  ▼               ▼               ▼                              │
│  ┌──────────────────┐  ┌──────────────┐  ┌────────────────────────────┐        │
│  │  Training Data   │  │  Multi-LoRA  │  │  Statistics Storage        │        │
│  │  (JSONL Files)   │  │  LLMs        │  │  (In-Memory Cache)         │        │
│  │  13,594 docs     │  │  GPU 5-7     │  │                            │        │
│  │  24 products     │  │  Port 12815- │  │                            │        │
│  │                  │  │  12817       │  │                            │        │
│  └──────────────────┘  └──────────────┘  └────────────────────────────┘        │
│                                                                                  │
└─────────────────────────────────────────────────────────────────────────────────┘
```

### 1.2 Decision Flow (Hybrid Mode)

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                          Hybrid Mode Decision Flow                               │
├─────────────────────────────────────────────────────────────────────────────────┤
│                                                                                  │
│  User Query: "DFSURGL0について説明してください"                                   │
│      │                                                                           │
│      ▼                                                                           │
│  ┌────────────────────────────────────────┐                                     │
│  │     Keyword Extraction                  │                                     │
│  │     "DFSURGL0について..." → "DFSURGL0"  │                                     │
│  └────────────────────────┬───────────────┘                                     │
│                           │                                                      │
│                           ▼                                                      │
│  ┌────────────────────────────────────────┐                                     │
│  │     Training Data Search                │                                     │
│  │     keyword_search("DFSURGL0", top_k=1) │                                     │
│  └────────────────────────┬───────────────┘                                     │
│                           │                                                      │
│                           ▼                                                      │
│  ┌────────────────────────────────────────┐                                     │
│  │     Results Found?                      │                                     │
│  └────────────┬───────────────────────────┘                                     │
│               │                                                                  │
│       ┌───────┴───────┐                                                         │
│       │               │                                                         │
│       ▼ NO            ▼ YES                                                     │
│  ┌─────────────┐  ┌──────────────────────────────┐                              │
│  │ mode:       │  │     Check Score              │                              │
│  │ no_sources  │  │     best_result['score']     │                              │
│  │ "情報なし"   │  └──────────────┬───────────────┘                              │
│  └─────────────┘                 │                                              │
│                         ┌────────┴────────┐                                     │
│                         │                 │                                     │
│                   Score >= 10        Score < 10                                 │
│                         │                 │                                     │
│                         ▼                 ▼                                     │
│                 ┌───────────────┐  ┌───────────────────┐                       │
│                 │ DIRECT MODE   │  │ LLM_WITH_CONTEXT  │                       │
│                 │               │  │                   │                       │
│                 │ Return data   │  │ Pass context to   │                       │
│                 │ directly      │  │ LLM for natural   │                       │
│                 │               │  │ response          │                       │
│                 │ ✅ 100%       │  │ ✅ 85% accurate   │                       │
│                 │ accurate      │  │                   │                       │
│                 │ ✅ No LLM     │  │ ⚠️ LLM required   │                       │
│                 │ ✅ ~45ms      │  │ ⚠️ ~200ms         │                       │
│                 └───────────────┘  └───────────────────┘                       │
│                                                                                  │
└─────────────────────────────────────────────────────────────────────────────────┘
```

### 1.3 Component Summary

| Component | Type | File | Description |
|-----------|------|------|-------------|
| RAGAntiHallucinationService | NEW | `services/rag_anti_hallucination_service.py` | RAG 서비스 (ImprovedRAG 래퍼) |
| RAGQueryRouter | NEW | `routers/query_rag.py` | REST API 엔드포인트 |
| RAGQueryRequest | NEW | `routers/query_rag.py` | Pydantic 요청 모델 |
| RAGQueryResponse | NEW | `routers/query_rag.py` | Pydantic 응답 모델 |
| ImprovedRAG | EXISTING | `test_0203/rag_solution_improved.py` | 핵심 RAG 로직 |
| TmaxProductRAG | EXISTING | `test_0203/rag_solution.py` | 기본 RAG 클래스 |
| main.py | MODIFY | `app/api/main.py` | 라우터 등록 |

---

## 2. Data Models

### 2.1 Request Models

```python
# app/api/routers/query_rag.py

from pydantic import BaseModel, Field
from typing import Optional, List, Dict
from enum import Enum


class RAGMode(str, Enum):
    """RAG 쿼리 모드"""
    DIRECT = "direct"      # LLM 우회, 100% 정확
    LLM = "llm"            # LLM으로 재구성
    HYBRID = "hybrid"      # 자동 선택 (권장)


class RAGQueryRequest(BaseModel):
    """RAG 쿼리 요청"""
    query: str = Field(
        ...,
        description="사용자 질문",
        min_length=1,
        max_length=1000,
        example="DFSURGL0について説明してください。"
    )
    mode: RAGMode = Field(
        default=RAGMode.HYBRID,
        description="RAG 모드: direct (100% 정확), llm (자연스러운 답변), hybrid (자동 선택)"
    )
    model: Optional[str] = Field(
        default="openframe_common_v2",
        description="LLM 모델 이름 (llm/hybrid 모드에서 사용)"
    )
    max_tokens: int = Field(
        default=500,
        ge=50,
        le=2000,
        description="최대 토큰 수"
    )
    temperature: float = Field(
        default=0.2,
        ge=0.0,
        le=2.0,
        description="Temperature (낮을수록 정확, 높을수록 창의적)"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "query": "DFSURGL0について説明してください。",
                "mode": "hybrid",
                "model": "openframe_common_v2",
                "max_tokens": 500,
                "temperature": 0.2
            }
        }


class RAGSearchRequest(BaseModel):
    """RAG 검색 요청 (디버깅용)"""
    query: str = Field(..., min_length=1, max_length=1000)
    top_k: int = Field(default=5, ge=1, le=20)
```

### 2.2 Response Models

```python
# app/api/routers/query_rag.py (continued)

class SourceInfo(BaseModel):
    """출처 정보"""
    product: str = Field(..., description="제품명")
    name: str = Field(..., description="항목명")
    score: int = Field(..., description="검색 점수")


class MetadataInfo(BaseModel):
    """메타데이터"""
    search_time_ms: float = Field(..., description="검색 시간 (ms)")
    llm_time_ms: float = Field(..., description="LLM 처리 시간 (ms)")
    total_time_ms: float = Field(..., description="총 처리 시간 (ms)")


class RAGQueryResponse(BaseModel):
    """RAG 쿼리 응답"""
    answer: str = Field(..., description="응답 내용")
    mode_used: str = Field(
        ...,
        description="실제 사용된 모드: direct_answer, llm_with_context, no_sources"
    )
    search_score: int = Field(..., description="검색 점수 (0-23)")
    sources: List[SourceInfo] = Field(default_factory=list, description="출처 목록")
    keyword_extracted: Optional[str] = Field(None, description="추출된 키워드")
    metadata: MetadataInfo = Field(..., description="처리 메타데이터")

    class Config:
        json_schema_extra = {
            "example": {
                "answer": "DFSURGL0は、HD再編成アンロード・ユーティリティ...",
                "mode_used": "direct_answer",
                "search_score": 23,
                "sources": [
                    {"product": "openframe_common", "name": "DFSURGL0", "score": 23}
                ],
                "keyword_extracted": "DFSURGL0",
                "metadata": {
                    "search_time_ms": 45.0,
                    "llm_time_ms": 0.0,
                    "total_time_ms": 45.0
                }
            }
        }


class RAGSearchResponse(BaseModel):
    """RAG 검색 응답 (디버깅용)"""
    query: str
    keyword_extracted: str
    results_count: int
    results: List[Dict]


class RAGStatsResponse(BaseModel):
    """RAG 통계 응답"""
    total_documents: int = Field(..., description="총 문서 수")
    products: Dict[str, int] = Field(..., description="제품별 문서 수")
    total_queries: int = Field(..., description="총 쿼리 수")
    modes_usage: Dict[str, int] = Field(..., description="모드별 사용 횟수")
    avg_search_time_ms: float = Field(..., description="평균 검색 시간")
    avg_llm_time_ms: float = Field(..., description="평균 LLM 처리 시간")


class RAGHealthResponse(BaseModel):
    """RAG 상태 응답"""
    status: str = Field(..., description="healthy 또는 unhealthy")
    documents_loaded: int = Field(..., description="로드된 문서 수")
    available_modes: List[str] = Field(..., description="사용 가능한 모드")
```

---

## 3. Service Specifications

### 3.1 RAGAntiHallucinationService

```python
# app/api/services/rag_anti_hallucination_service.py

"""
RAG Anti-Hallucination Service
할루시네이션 방지를 위한 RAG 서비스

Dependencies:
- test_0203/rag_solution_improved.py (ImprovedRAG)
- test_0203/rag_solution.py (TmaxProductRAG)
"""

import logging
import time
from typing import Dict, List, Optional
from pathlib import Path

logger = logging.getLogger(__name__)


class RAGAntiHallucinationService:
    """
    FastAPI 백엔드용 RAG Anti-Hallucination 서비스

    Responsibilities:
    1. ImprovedRAG 클래스 래핑 및 FastAPI 통합
    2. 3가지 RAG 모드 지원 (direct, llm, hybrid)
    3. 통계 수집 및 모니터링
    4. 에러 핸들링 및 로깅

    Usage:
        service = RAGAntiHallucinationService.get_instance()
        result = await service.query_hybrid("DFSURGL0について")
    """

    _instance: Optional['RAGAntiHallucinationService'] = None

    def __init__(self, training_data_dir: str):
        """
        Initialize RAG service

        Args:
            training_data_dir: 학습 데이터 디렉토리 (JSONL 파일들)
        """
        # Import ImprovedRAG
        import sys
        rag_path = Path(__file__).parent.parent.parent.parent / "test_0203" / "test_0203"
        sys.path.insert(0, str(rag_path))

        from rag_solution_improved import ImprovedRAG
        self.rag = ImprovedRAG(training_data_dir)

        # Statistics
        self.stats = {
            'total_queries': 0,
            'modes_usage': {
                'direct_answer': 0,
                'llm_with_context': 0,
                'no_sources': 0
            },
            'total_search_time_ms': 0,
            'total_llm_time_ms': 0
        }

        logger.info(f"✅ RAG service initialized with {len(self.rag.documents)} documents")

    @classmethod
    def get_instance(cls, training_data_dir: Optional[str] = None) -> 'RAGAntiHallucinationService':
        """싱글톤 인스턴스 반환"""
        if cls._instance is None:
            if training_data_dir is None:
                # 기본 경로 (환경변수 또는 기본값)
                import os
                training_data_dir = os.getenv(
                    'RAG_TRAINING_DATA_DIR',
                    str(Path(__file__).parent.parent.parent.parent / "test_0203" / "test_0203" / "training_data_v2")
                )
            cls._instance = cls(training_data_dir)
        return cls._instance

    async def query_hybrid(
        self,
        query: str,
        model: str = "openframe_common_v2",
        llm_url: str = "http://localhost:12815/v1",
        max_tokens: int = 500,
        temperature: float = 0.2
    ) -> Dict:
        """
        Hybrid 모드 쿼리 (권장)

        Score >= 10 → Direct Answer (100% 정확)
        Score < 10  → LLM with Context (85% 정확)

        Args:
            query: 사용자 질문
            model: LLM 모델 이름
            llm_url: LLM 서버 URL
            max_tokens: 최대 토큰 수
            temperature: Temperature

        Returns:
            {
                'answer': str,
                'mode_used': str,
                'search_score': int,
                'sources': List[Dict],
                'keyword_extracted': str,
                'metadata': Dict
            }
        """
        start_time = time.time()
        search_start = time.time()

        try:
            # Hybrid 모드 실행
            result = self.rag.query_mode_3_hybrid(
                query=query,
                model=model,
                llm_url=llm_url
            )

            search_time = (time.time() - search_start) * 1000

            # 키워드 추출
            keyword = self.rag.extract_keyword(query)

            # 통계 업데이트
            self._update_stats(result.get('mode', 'unknown'), search_time)

            total_time = (time.time() - start_time) * 1000
            llm_time = total_time - search_time if result.get('mode') == 'llm_with_context' else 0

            return {
                'answer': result['answer'],
                'mode_used': result.get('mode', 'unknown'),
                'search_score': result.get('search_score', 0),
                'sources': self._format_sources(result.get('sources', [])),
                'keyword_extracted': keyword,
                'metadata': {
                    'search_time_ms': round(search_time, 2),
                    'llm_time_ms': round(llm_time, 2),
                    'total_time_ms': round(total_time, 2)
                }
            }

        except Exception as e:
            logger.error(f"RAG hybrid query failed: {e}", exc_info=True)
            raise

    async def query_direct(self, query: str) -> Dict:
        """
        Direct Answer 모드 (LLM 우회, 100% 정확)

        학습 데이터의 응답을 그대로 반환합니다.
        환각이 절대 발생하지 않습니다.

        Args:
            query: 사용자 질문

        Returns:
            RAG 응답 딕셔너리
        """
        start_time = time.time()

        try:
            result = self.rag.query_mode_2_direct_answer(query)
            keyword = self.rag.extract_keyword(query)

            total_time = (time.time() - start_time) * 1000

            self._update_stats(result.get('mode', 'direct_answer'), total_time)

            return {
                'answer': result['answer'],
                'mode_used': result.get('mode', 'direct_answer'),
                'search_score': result.get('score', 0),
                'sources': self._format_sources(result.get('sources', [])),
                'keyword_extracted': keyword,
                'metadata': {
                    'search_time_ms': round(total_time, 2),
                    'llm_time_ms': 0,
                    'total_time_ms': round(total_time, 2)
                }
            }

        except Exception as e:
            logger.error(f"RAG direct query failed: {e}", exc_info=True)
            raise

    async def query_llm(
        self,
        query: str,
        model: str = "openframe_common_v2",
        llm_url: str = "http://localhost:12815/v1",
        max_tokens: int = 500,
        temperature: float = 0.2
    ) -> Dict:
        """
        LLM 모드 (검색 결과를 LLM으로 재구성)

        자연스러운 답변이 필요할 때 사용합니다.
        약간의 환각 가능성이 있습니다 (5% 미만).

        Args:
            query: 사용자 질문
            model: LLM 모델 이름
            llm_url: LLM 서버 URL
            max_tokens: 최대 토큰 수
            temperature: Temperature

        Returns:
            RAG 응답 딕셔너리
        """
        start_time = time.time()
        search_start = time.time()

        try:
            result = self.rag.query_mode_1_strict_prompt(
                query=query,
                model=model,
                llm_url=llm_url
            )

            search_time = (time.time() - search_start) * 1000
            keyword = self.rag.extract_keyword(query)

            total_time = (time.time() - start_time) * 1000
            llm_time = total_time - search_time

            self._update_stats('llm_with_context', search_time)
            self.stats['total_llm_time_ms'] += llm_time

            return {
                'answer': result['answer'],
                'mode_used': result.get('mode', 'strict_prompt'),
                'search_score': 0,  # LLM 모드는 score 없음
                'sources': self._format_sources(result.get('sources', [])),
                'keyword_extracted': keyword,
                'metadata': {
                    'search_time_ms': round(search_time, 2),
                    'llm_time_ms': round(llm_time, 2),
                    'total_time_ms': round(total_time, 2)
                }
            }

        except Exception as e:
            logger.error(f"RAG LLM query failed: {e}", exc_info=True)
            raise

    async def search_only(self, query: str, top_k: int = 5) -> Dict:
        """
        검색만 수행 (디버깅용)

        LLM을 사용하지 않고 검색 결과만 반환합니다.

        Args:
            query: 검색 쿼리
            top_k: 반환할 결과 수

        Returns:
            검색 결과 딕셔너리
        """
        try:
            keyword = self.rag.extract_keyword(query)
            results = self.rag.keyword_search(keyword, top_k=top_k)

            return {
                'query': query,
                'keyword_extracted': keyword,
                'results_count': len(results),
                'results': [
                    {
                        'product': r.get('product', 'unknown'),
                        'name': r.get('name', 'N/A'),
                        'score': r.get('score', 0),
                        'instruction': r.get('instruction', ''),
                        'response': r.get('response', '')[:200] + '...' if len(r.get('response', '')) > 200 else r.get('response', '')
                    }
                    for r in results
                ]
            }

        except Exception as e:
            logger.error(f"RAG search failed: {e}", exc_info=True)
            raise

    def get_stats(self) -> Dict:
        """통계 반환"""
        # 제품별 문서 수
        products = {}
        for doc in self.rag.documents:
            product = doc.get('product', 'unknown')
            products[product] = products.get(product, 0) + 1

        # 평균 시간
        total_queries = self.stats['total_queries']
        avg_search_time = self.stats['total_search_time_ms'] / total_queries if total_queries > 0 else 0
        avg_llm_time = self.stats['total_llm_time_ms'] / total_queries if total_queries > 0 else 0

        return {
            'total_documents': len(self.rag.documents),
            'products': products,
            'total_queries': total_queries,
            'modes_usage': self.stats['modes_usage'],
            'avg_search_time_ms': round(avg_search_time, 2),
            'avg_llm_time_ms': round(avg_llm_time, 2)
        }

    def _update_stats(self, mode: str, search_time: float):
        """통계 업데이트"""
        self.stats['total_queries'] += 1
        self.stats['modes_usage'][mode] = self.stats['modes_usage'].get(mode, 0) + 1
        self.stats['total_search_time_ms'] += search_time

    def _format_sources(self, sources: List[Dict]) -> List[Dict]:
        """출처 포맷팅"""
        return [
            {
                'product': src.get('product', 'unknown'),
                'name': src.get('name', 'N/A'),
                'score': src.get('score', 0)
            }
            for src in sources
        ]


# Dependency Injection용
def get_rag_service() -> RAGAntiHallucinationService:
    """FastAPI 의존성 주입용"""
    return RAGAntiHallucinationService.get_instance()
```

---

## 4. API Router Specification

### 4.1 RAG Query Router

```python
# app/api/routers/query_rag.py

"""
RAG Query Router
할루시네이션 방지 RAG 엔드포인트
"""

from fastapi import APIRouter, Depends, HTTPException, status
import logging

from ..services.rag_anti_hallucination_service import (
    RAGAntiHallucinationService,
    get_rag_service
)
from ..core.deps import get_current_user
from ..models.user import User

# Import models (defined above in section 2)
# RAGQueryRequest, RAGQueryResponse, RAGSearchRequest, etc.

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/query/rag", tags=["RAG Query"])


@router.post("", response_model=RAGQueryResponse)
async def query_with_rag(
    request: RAGQueryRequest,
    current_user: User = Depends(get_current_user),
    rag_service: RAGAntiHallucinationService = Depends(get_rag_service)
):
    """
    RAG 기반 쿼리 (할루시네이션 방지)

    **Modes:**
    - `direct`: 학습 데이터 직접 반환 (100% 정확, 환각 불가능)
    - `llm`: LLM으로 재구성 (자연스러운 답변)
    - `hybrid`: 자동 선택 (권장) - 정확한 키워드면 direct, 애매하면 llm

    **Score 기준:**
    - instruction에 키워드 포함: +10점
    - response에 키워드 포함: +5점
    - name에 키워드 포함: +8점
    - Score >= 10 → Direct Answer
    - Score < 10 → LLM with Context

    **Example:**
    ```bash
    curl -X POST http://localhost:9000/api/v1/query/rag \\
      -H "Authorization: Bearer <token>" \\
      -H "Content-Type: application/json" \\
      -d '{"query": "DFSURGL0について説明してください。", "mode": "hybrid"}'
    ```
    """
    try:
        logger.info(f"RAG query from user {current_user.username}: {request.query[:50]}...")

        if request.mode == "direct":
            result = await rag_service.query_direct(request.query)
        elif request.mode == "llm":
            result = await rag_service.query_llm(
                query=request.query,
                model=request.model,
                max_tokens=request.max_tokens,
                temperature=request.temperature
            )
        else:  # hybrid (default)
            result = await rag_service.query_hybrid(
                query=request.query,
                model=request.model,
                max_tokens=request.max_tokens,
                temperature=request.temperature
            )

        logger.info(f"RAG query completed: mode={result['mode_used']}, score={result['search_score']}")
        return result

    except Exception as e:
        logger.error(f"RAG query failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"RAG query failed: {str(e)}"
        )


@router.post("/search", response_model=RAGSearchResponse)
async def search_training_data(
    request: RAGSearchRequest,
    current_user: User = Depends(get_current_user),
    rag_service: RAGAntiHallucinationService = Depends(get_rag_service)
):
    """
    학습 데이터 검색만 수행 (LLM 사용 안 함)

    디버깅 및 검색 품질 확인용입니다.
    keyword_extracted와 results_count를 확인하여
    검색 로직을 디버깅할 수 있습니다.
    """
    try:
        result = await rag_service.search_only(request.query, request.top_k)
        return result

    except Exception as e:
        logger.error(f"RAG search failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Search failed: {str(e)}"
        )


@router.get("/stats", response_model=RAGStatsResponse)
async def get_rag_stats(
    current_user: User = Depends(get_current_user),
    rag_service: RAGAntiHallucinationService = Depends(get_rag_service)
):
    """
    RAG 서비스 통계

    제품별 문서 수, 모드별 사용 횟수, 평균 처리 시간 등을 반환합니다.
    """
    try:
        stats = rag_service.get_stats()
        return stats

    except Exception as e:
        logger.error(f"Get stats failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Get stats failed: {str(e)}"
        )


@router.get("/health", response_model=RAGHealthResponse)
async def rag_health():
    """
    RAG 서비스 상태 확인

    인증 없이 접근 가능합니다.
    서비스 모니터링용입니다.
    """
    try:
        rag_service = get_rag_service()
        return {
            "status": "healthy",
            "documents_loaded": len(rag_service.rag.documents),
            "available_modes": ["direct", "llm", "hybrid"]
        }
    except Exception as e:
        return {
            "status": "unhealthy",
            "documents_loaded": 0,
            "available_modes": [],
            "error": str(e)
        }
```

---

## 5. Integration Points

### 5.1 main.py Integration

```python
# app/api/main.py 에 추가할 내용

# === 추가할 import ===
from .routers import query_rag

# === 기존 router 등록 후 추가 ===
app.include_router(query_rag.router)

logger.info("✅ RAG Anti-Hallucination endpoints registered")
```

### 5.2 Environment Variables

```bash
# .env 에 추가할 항목

# === RAG Anti-Hallucination Service ===
RAG_TRAINING_DATA_DIR=/path/to/test_0203/training_data_v2
RAG_ENABLE=true
RAG_DEFAULT_MODE=hybrid

# LLM URLs for RAG (Multi-LoRA)
RAG_LLM_URL_COMMON=http://localhost:12815/v1
RAG_LLM_URL_OSI=http://localhost:12816/v1
RAG_LLM_URL_TIBERO=http://localhost:12817/v1
```

---

## 6. Testing Strategy

### 6.1 Unit Tests

```python
# tests/api/test_rag_service.py

import pytest
from app.api.services.rag_anti_hallucination_service import RAGAntiHallucinationService


@pytest.fixture
def rag_service():
    """RAG 서비스 픽스처"""
    return RAGAntiHallucinationService.get_instance()


@pytest.mark.asyncio
async def test_query_hybrid_exact_keyword(rag_service):
    """정확한 키워드 - Direct Answer 모드 선택"""
    result = await rag_service.query_hybrid("DFSURGL0について説明してください。")

    assert result['mode_used'] == 'direct_answer'
    assert result['search_score'] >= 10
    assert len(result['sources']) > 0
    assert 'DFSURGL0' in result['keyword_extracted']


@pytest.mark.asyncio
async def test_query_hybrid_no_results(rag_service):
    """존재하지 않는 키워드 - no_sources 모드"""
    result = await rag_service.query_hybrid("XYZ9999について")

    assert result['mode_used'] == 'no_sources'
    assert result['search_score'] == 0
    assert len(result['sources']) == 0


@pytest.mark.asyncio
async def test_query_direct_100_percent_accurate(rag_service):
    """Direct 모드 - LLM 미사용 확인"""
    result = await rag_service.query_direct("DFSURGL0について")

    assert result['mode_used'] == 'direct_answer'
    assert result['metadata']['llm_time_ms'] == 0
    # 학습 데이터의 내용이 그대로 포함되어야 함
    assert '再編成' in result['answer'] or 'リロード' in result['answer']


@pytest.mark.asyncio
async def test_search_only(rag_service):
    """검색만 테스트"""
    result = await rag_service.search_only("DFSURGL0", top_k=3)

    assert result['results_count'] > 0
    assert result['keyword_extracted'] == "DFSURGL0"
    assert len(result['results']) <= 3


@pytest.mark.asyncio
async def test_get_stats(rag_service):
    """통계 테스트"""
    # 먼저 몇 개의 쿼리 실행
    await rag_service.query_hybrid("test query")

    stats = rag_service.get_stats()

    assert stats['total_documents'] > 0
    assert 'openframe_common' in stats['products']
    assert stats['total_queries'] >= 1
```

### 6.2 Integration Tests

```python
# tests/api/test_rag_endpoints.py

import pytest
from fastapi.testclient import TestClient
from app.api.main import app


client = TestClient(app)


@pytest.fixture
def auth_headers(auth_token):
    """인증 헤더"""
    return {"Authorization": f"Bearer {auth_token}"}


def test_rag_query_endpoint_with_auth(auth_headers):
    """인증된 RAG 쿼리"""
    response = client.post(
        "/api/v1/query/rag",
        headers=auth_headers,
        json={
            "query": "DFSURGL0について説明してください。",
            "mode": "hybrid"
        }
    )

    assert response.status_code == 200
    data = response.json()

    assert 'answer' in data
    assert 'mode_used' in data
    assert 'sources' in data
    assert data['search_score'] >= 0


def test_rag_query_without_auth():
    """인증 없는 RAG 쿼리 - 401"""
    response = client.post(
        "/api/v1/query/rag",
        json={"query": "test"}
    )

    assert response.status_code == 401


def test_rag_health_no_auth_required():
    """Health 엔드포인트 - 인증 불필요"""
    response = client.get("/api/v1/query/rag/health")

    assert response.status_code == 200
    data = response.json()

    assert data['status'] == 'healthy'
    assert data['documents_loaded'] > 0


def test_rag_stats_endpoint(auth_headers):
    """통계 엔드포인트"""
    response = client.get(
        "/api/v1/query/rag/stats",
        headers=auth_headers
    )

    assert response.status_code == 200
    data = response.json()

    assert 'total_documents' in data
    assert 'products' in data


def test_rag_search_endpoint(auth_headers):
    """검색 엔드포인트"""
    response = client.post(
        "/api/v1/query/rag/search",
        headers=auth_headers,
        json={"query": "Tibero", "top_k": 5}
    )

    assert response.status_code == 200
    data = response.json()

    assert 'keyword_extracted' in data
    assert 'results_count' in data
```

### 6.3 E2E Test Cases

```javascript
// e2e/e2e_rag_anti_hallucination.js

const RAG_TEST_CASES = [
    {
        keyword: 'DFSURGL0',
        query: 'DFSURGL0について説明してください。',
        expected: ['DFSURGL0', '再編成', 'リロード', 'HIDAM', 'HISAM'],
        notExpected: ['OSI', 'TACF', 'セキュリティ'],  // 환각 키워드
        expectedMode: 'direct_answer',
        minScore: 10,
    },
    {
        keyword: 'Tibero',
        query: 'Tiberoの主要な特徴を教えてください。',
        expected: ['Tibero', 'データベース', 'RDBMS'],
        notExpected: ['OpenFrame', 'TJES'],
        expectedMode: 'direct_answer',
    },
    {
        keyword: 'XYZ_NOT_EXISTS',
        query: 'XYZ_NOT_EXISTSについて',
        expected: ['見つかりませんでした'],
        notExpected: [],
        expectedMode: 'no_sources',
    },
];
```

---

## 7. Implementation Order

### Phase 1: Core Service (Day 1)
1. [ ] `test_0203/test_0203/` 디렉토리 구조 확인
2. [ ] `app/api/services/rag_anti_hallucination_service.py` 생성
3. [ ] ImprovedRAG import 경로 설정
4. [ ] 서비스 싱글톤 패턴 구현
5. [ ] Unit tests 작성 및 실행

### Phase 2: API Router (Day 2)
6. [ ] `app/api/routers/query_rag.py` 생성
7. [ ] Pydantic 모델 정의 (Request/Response)
8. [ ] 4개 엔드포인트 구현
9. [ ] `app/api/main.py`에 라우터 등록
10. [ ] Integration tests 작성 및 실행

### Phase 3: Testing & Verification (Day 3)
11. [ ] 수동 테스트 (curl)
12. [ ] E2E 테스트 작성
13. [ ] 할루시네이션 감소 검증
14. [ ] 성능 측정 (응답 시간)

### Phase 4: Documentation (Day 4)
15. [ ] `.env.example` 업데이트
16. [ ] OpenAPI 문서 확인 (`/docs`)
17. [ ] README 업데이트

---

## 8. Success Metrics

| Metric | Target | Measurement |
|--------|--------|-------------|
| 정확도 | >= 95% | E2E 테스트 pass rate |
| 할루시네이션 | < 5% | notExpected 키워드 발생률 |
| Direct 응답시간 | < 100ms | metadata.total_time_ms |
| Hybrid 응답시간 | < 500ms | metadata.total_time_ms |
| 문서 로드 시간 | < 5s | 서비스 시작 로그 |
| 테스트 커버리지 | >= 80% | pytest --cov |

---

## 9. File Structure Summary

```
app/api/
├── main.py                                      # [MODIFY] 라우터 등록 추가
├── routers/
│   └── query_rag.py                             # [NEW] RAG 엔드포인트
└── services/
    └── rag_anti_hallucination_service.py        # [NEW] RAG 서비스

test_0203/
└── test_0203/
    ├── rag_solution.py                          # [EXISTING] 기본 RAG 클래스
    ├── rag_solution_improved.py                 # [EXISTING] 개선된 RAG
    └── training_data_v2/                        # [EXISTING] 학습 데이터
        ├── openframe_common_v2.jsonl
        ├── tibero7_v2.jsonl
        └── ... (24 products)

tests/api/
├── test_rag_service.py                          # [NEW] 서비스 단위 테스트
└── test_rag_endpoints.py                        # [NEW] 엔드포인트 통합 테스트

e2e/
└── e2e_rag_anti_hallucination.js               # [NEW] E2E 테스트
```

---

**Next Step**: `/pdca do rag-backend-integration`

---

> **Design Version**: v1.0
> **Created by**: Claude Code + bkit PDCA
> **Last Updated**: 2026-02-03
