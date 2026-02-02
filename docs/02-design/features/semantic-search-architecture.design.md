# Semantic Search Architecture Design

> **Feature**: semantic-search-architecture
> **Version**: v1.0
> **Created**: 2026-01-31
> **Plan Reference**: `docs/01-plan/features/semantic-search-architecture.plan.md`

---

## 1. Overview

### 1.1 목적
BM25 키워드 매칭의 한계를 극복하고 LLM 기반 Query Understanding + Hybrid Retrieval을 통한 의미 기반 검색 시스템 구축

### 1.2 핵심 변경 사항
| 현재 | 변경 후 |
|------|---------|
| Rule-based 전처리 | LLM Query Understanding |
| BM25 단독 검색 | Hybrid Retrieval (Vector + Keyword + Entity) |
| 단일 랭킹 | Reciprocal Rank Fusion (RRF) |
| 언어별 성능 차이 | 다국어 동등 성능 |

---

## 2. System Architecture

### 2.1 High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                              User Query                                  │
│                "ofasmifコマンドについて説明してください"                    │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                    QueryUnderstandingService                             │
│  ┌───────────────────────────────────────────────────────────────────┐ │
│  │  LLM Analysis (MiniCPM-V / Ollama)                                 │ │
│  │  ┌─────────────┐ ┌─────────────┐ ┌─────────────┐ ┌─────────────┐ │ │
│  │  │   Intent    │ │   Entity    │ │  Language   │ │   Query     │ │ │
│  │  │ Classifier  │ │  Extractor  │ │  Detector   │ │  Rewriter   │ │ │
│  │  └─────────────┘ └─────────────┘ └─────────────┘ └─────────────┘ │ │
│  └───────────────────────────────────────────────────────────────────┘ │
│  Output: QueryAnalysis {                                                │
│    intent: "explanation_request",                                       │
│    entities: [{type: "command", value: "ofasmif"}],                    │
│    language: "ja",                                                      │
│    rewritten_query: "ofasmif command syntax usage manual"              │
│  }                                                                      │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                       HybridRetriever                                    │
│  ┌─────────────────┐ ┌─────────────────┐ ┌─────────────────────────┐   │
│  │  VectorSearch   │ │  KeywordSearch  │ │    EntityLookup         │   │
│  │  ─────────────  │ │  ─────────────  │ │  ─────────────────────  │   │
│  │  multilingual   │ │  BM25 with      │ │  Direct index lookup    │   │
│  │  -e5-large      │ │  rewritten      │ │  command_index,         │   │
│  │  embedding      │ │  query          │ │  error_index, etc.      │   │
│  │                 │ │                 │ │                         │   │
│  │  → Top 20      │ │  → Top 20      │ │  → Exact matches        │   │
│  └─────────────────┘ └─────────────────┘ └─────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                    ResultFusionService                                   │
│  ┌───────────────────────────────────────────────────────────────────┐ │
│  │  Reciprocal Rank Fusion (RRF)                                      │ │
│  │  score(d) = Σ 1/(k + rank_i(d))  where k=60                       │ │
│  │                                                                    │ │
│  │  Merge → Deduplicate → RRF Score → Sort                          │ │
│  └───────────────────────────────────────────────────────────────────┘ │
│                              │                                          │
│                              ▼                                          │
│  ┌───────────────────────────────────────────────────────────────────┐ │
│  │  Cross-Encoder Re-ranker (Optional, Phase 2)                       │ │
│  │  Query-Document pair scoring for fine-grained relevance           │ │
│  └───────────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                         Final Results                                    │
│  Top-K documents with confidence scores, sources, related images        │
└─────────────────────────────────────────────────────────────────────────┘
```

### 2.2 Component Diagram

```
app/api/services/
├── query_understanding_service.py    [NEW] LLM 기반 쿼리 분석
├── hybrid_retriever_service.py       [NEW] 하이브리드 검색 조합
├── result_fusion_service.py          [NEW] RRF 기반 결과 통합
├── vector_search_service.py          [MODIFY] 다국어 임베딩 지원
├── summary_bm25_service.py           [MODIFY] rewritten query 수신
└── entity_lookup_service.py          [NEW] Entity 직접 조회

app/api/models/
├── query_analysis.py                 [NEW] QueryAnalysis 모델
└── search_result.py                  [MODIFY] RRF 점수 필드 추가

app/api/agents/tools/
├── unified_search.py                 [MODIFY] HybridRetriever 통합
└── vector_search.py                  [MODIFY] 다국어 임베딩 호출
```

---

## 3. Detailed Component Design

### 3.1 QueryUnderstandingService

#### 3.1.1 Class Definition

```python
# app/api/services/query_understanding_service.py

from dataclasses import dataclass
from typing import List, Optional
from enum import Enum

class QueryIntent(Enum):
    EXPLANATION = "explanation"      # ~について説明して
    DEFINITION = "definition"        # ~とは？
    USAGE = "usage"                  # ~の使い方
    ERROR_RESOLUTION = "error"       # エラー解決
    COMPARISON = "comparison"        # ~と~の違い
    PROCEDURE = "procedure"          # ~の手順
    CONFIGURATION = "configuration"  # ~の設定方法
    SEARCH = "search"               # 一般検索

@dataclass
class ExtractedEntity:
    type: str       # "command", "error_code", "product", "config", "term"
    value: str      # "ofasmif", "-5212", "TJES", etc.
    confidence: float

@dataclass
class QueryAnalysis:
    original_query: str
    intent: QueryIntent
    entities: List[ExtractedEntity]
    language: str                    # "ja", "ko", "en"
    rewritten_query: str             # 검색 최적화된 쿼리
    keywords: List[str]              # 핵심 키워드 목록

class QueryUnderstandingService:
    """LLM 기반 쿼리 이해 서비스"""

    def __init__(self, llm_client, cache_service):
        self.llm = llm_client
        self.cache = cache_service
        self.prompt_template = self._load_prompt()

    async def analyze(self, query: str) -> QueryAnalysis:
        """쿼리 분석 메인 함수"""
        # 1. 캐시 확인
        cached = await self.cache.get(f"query_analysis:{query}")
        if cached:
            return cached

        # 2. LLM 분석
        analysis = await self._llm_analyze(query)

        # 3. 캐시 저장 (TTL: 1시간)
        await self.cache.set(f"query_analysis:{query}", analysis, ttl=3600)

        return analysis

    async def _llm_analyze(self, query: str) -> QueryAnalysis:
        """LLM을 통한 쿼리 분석"""
        prompt = self.prompt_template.format(query=query)

        response = await self.llm.generate(
            prompt=prompt,
            max_tokens=500,
            temperature=0.1  # 일관성을 위해 낮은 temperature
        )

        return self._parse_response(query, response)
```

#### 3.1.2 LLM Prompt Design

```python
QUERY_UNDERSTANDING_PROMPT = """
You are a query analyzer for a technical documentation search system.
Analyze the following query and extract structured information.

Query: {query}

Respond in JSON format:
{{
  "intent": "<one of: explanation, definition, usage, error, comparison, procedure, configuration, search>",
  "entities": [
    {{"type": "<command|error_code|product|config|term>", "value": "<extracted value>", "confidence": <0.0-1.0>}}
  ],
  "language": "<ja|ko|en>",
  "rewritten_query": "<search-optimized English query with key terms>",
  "keywords": ["<keyword1>", "<keyword2>", ...]
}}

Rules:
1. Extract product names: TJES, TACF, OSC, OFASM, HIDB, OpenFrame, etc.
2. Extract commands: tjesmgr, tacfmgr, ofasmif, oscmgr, etc.
3. Extract error codes: patterns like -5212, ABEND S0C7, etc.
4. Remove filler phrases in rewritten_query
5. Keywords should be in both original language and English

Example:
Query: "ofasmifコマンドについて説明してください"
Response:
{{
  "intent": "explanation",
  "entities": [{{"type": "command", "value": "ofasmif", "confidence": 0.95}}],
  "language": "ja",
  "rewritten_query": "ofasmif command syntax usage parameters manual OFASM",
  "keywords": ["ofasmif", "command", "OFASM", "コマンド"]
}}
"""
```

#### 3.1.3 Caching Strategy

```python
# 캐싱 레이어
class QueryAnalysisCache:
    """쿼리 분석 결과 캐싱"""

    def __init__(self, redis_client=None):
        self.redis = redis_client
        self.local_cache = {}  # Fallback LRU cache
        self.max_local_size = 1000

    async def get(self, key: str) -> Optional[QueryAnalysis]:
        # Redis 우선, 없으면 로컬 캐시
        if self.redis:
            data = await self.redis.get(key)
            if data:
                return QueryAnalysis.from_json(data)
        return self.local_cache.get(key)

    async def set(self, key: str, value: QueryAnalysis, ttl: int = 3600):
        if self.redis:
            await self.redis.setex(key, ttl, value.to_json())
        else:
            self._local_set(key, value)
```

---

### 3.2 HybridRetrieverService

#### 3.2.1 Class Definition

```python
# app/api/services/hybrid_retriever_service.py

from typing import List, Dict, Any
from dataclasses import dataclass

@dataclass
class RetrievalResult:
    doc_id: str
    content: str
    source: str           # "vector", "keyword", "entity"
    score: float
    metadata: Dict[str, Any]

class HybridRetrieverService:
    """다중 검색 전략 조합 서비스"""

    def __init__(
        self,
        vector_service,      # VectorSearchService
        keyword_service,     # SummaryBM25Service
        entity_service,      # EntityLookupService
        weights: Dict[str, float] = None
    ):
        self.vector = vector_service
        self.keyword = keyword_service
        self.entity = entity_service
        self.weights = weights or {
            "vector": 1.0,
            "keyword": 0.8,
            "entity": 1.2  # Entity 직접 매칭에 높은 가중치
        }

    async def retrieve(
        self,
        query: str,
        analysis: QueryAnalysis,
        top_k: int = 20
    ) -> List[RetrievalResult]:
        """병렬 하이브리드 검색 실행"""

        # 1. 병렬 검색 실행
        vector_task = self._vector_search(query, top_k)
        keyword_task = self._keyword_search(analysis.rewritten_query, top_k)
        entity_task = self._entity_lookup(analysis.entities)

        vector_results, keyword_results, entity_results = await asyncio.gather(
            vector_task, keyword_task, entity_task
        )

        # 2. 결과에 소스 태깅
        for r in vector_results:
            r.source = "vector"
        for r in keyword_results:
            r.source = "keyword"
        for r in entity_results:
            r.source = "entity"

        return vector_results + keyword_results + entity_results

    async def _vector_search(self, query: str, top_k: int) -> List[RetrievalResult]:
        """벡터 유사도 검색"""
        results = await self.vector.search(
            query=query,
            top_k=top_k,
            use_multilingual=True  # multilingual-e5-large
        )
        return [RetrievalResult(
            doc_id=r.doc_id,
            content=r.content,
            source="vector",
            score=r.similarity,
            metadata=r.metadata
        ) for r in results]

    async def _keyword_search(self, query: str, top_k: int) -> List[RetrievalResult]:
        """BM25 키워드 검색 (rewritten query 사용)"""
        results = await self.keyword.search(query, top_k=top_k)
        return [RetrievalResult(
            doc_id=r.doc_id,
            content=r.content,
            source="keyword",
            score=r.bm25_score,
            metadata=r.metadata
        ) for r in results]

    async def _entity_lookup(self, entities: List[ExtractedEntity]) -> List[RetrievalResult]:
        """Entity 직접 조회"""
        results = []
        for entity in entities:
            docs = await self.entity.lookup(
                entity_type=entity.type,
                entity_value=entity.value
            )
            results.extend(docs)
        return results
```

#### 3.2.2 Entity Lookup Service

```python
# app/api/services/entity_lookup_service.py

class EntityLookupService:
    """Entity 기반 직접 조회 서비스"""

    def __init__(self, neo4j_driver, summary_service):
        self.neo4j = neo4j_driver
        self.summary = summary_service

        # Entity 인덱스 (사전 로드)
        self.command_index = {}    # command name → doc_ids
        self.error_index = {}      # error code → doc_ids
        self.product_index = {}    # product name → doc_ids

    async def initialize(self):
        """Entity 인덱스 초기화"""
        # Neo4j에서 Entity 노드 로드
        query = """
        MATCH (e:Entity)-[:MENTIONS]->(c:Chunk)
        RETURN e.type as type, e.value as value, collect(c.id) as chunk_ids
        """
        records = await self.neo4j.run(query)

        for record in records:
            entity_type = record["type"]
            entity_value = record["value"].lower()
            chunk_ids = record["chunk_ids"]

            if entity_type == "command":
                self.command_index[entity_value] = chunk_ids
            elif entity_type == "error_code":
                self.error_index[entity_value] = chunk_ids
            elif entity_type == "product":
                self.product_index[entity_value] = chunk_ids

    async def lookup(
        self,
        entity_type: str,
        entity_value: str
    ) -> List[RetrievalResult]:
        """Entity 직접 조회"""
        index = self._get_index(entity_type)
        value_lower = entity_value.lower()

        if value_lower not in index:
            return []

        chunk_ids = index[value_lower]

        # Chunk 내용 조회
        results = []
        for chunk_id in chunk_ids[:10]:  # 최대 10개
            chunk = await self._get_chunk(chunk_id)
            if chunk:
                results.append(RetrievalResult(
                    doc_id=chunk_id,
                    content=chunk.content,
                    source="entity",
                    score=1.0,  # 직접 매칭은 최고 점수
                    metadata={"entity_type": entity_type, "entity_value": entity_value}
                ))

        return results
```

---

### 3.3 ResultFusionService (RRF)

#### 3.3.1 Class Definition

```python
# app/api/services/result_fusion_service.py

class ResultFusionService:
    """Reciprocal Rank Fusion 기반 결과 통합"""

    def __init__(self, k: int = 60):
        self.k = k  # RRF 상수 (일반적으로 60 사용)

    def fuse(
        self,
        result_lists: List[List[RetrievalResult]],
        weights: Dict[str, float] = None
    ) -> List[RetrievalResult]:
        """
        RRF 알고리즘으로 여러 검색 결과 통합

        RRF Score = Σ (weight_i / (k + rank_i))
        """
        weights = weights or {"vector": 1.0, "keyword": 0.8, "entity": 1.2}

        # 1. 문서별 RRF 점수 계산
        doc_scores: Dict[str, float] = {}
        doc_data: Dict[str, RetrievalResult] = {}

        for result_list in result_lists:
            for rank, result in enumerate(result_list, start=1):
                doc_id = result.doc_id
                source = result.source
                weight = weights.get(source, 1.0)

                # RRF 점수 누적
                rrf_score = weight / (self.k + rank)
                doc_scores[doc_id] = doc_scores.get(doc_id, 0) + rrf_score

                # 첫 번째 등장 결과 저장 (메타데이터용)
                if doc_id not in doc_data:
                    doc_data[doc_id] = result

        # 2. 중복 제거 및 정렬
        fused_results = []
        for doc_id, rrf_score in sorted(doc_scores.items(), key=lambda x: -x[1]):
            result = doc_data[doc_id]
            result.score = rrf_score  # RRF 점수로 업데이트
            fused_results.append(result)

        return fused_results

    def deduplicate(self, results: List[RetrievalResult]) -> List[RetrievalResult]:
        """중복 문서 제거 (내용 기반)"""
        seen_hashes = set()
        unique_results = []

        for result in results:
            content_hash = hash(result.content[:200])  # 앞부분만 해시
            if content_hash not in seen_hashes:
                seen_hashes.add(content_hash)
                unique_results.append(result)

        return unique_results
```

---

### 3.4 Integration with Existing System

#### 3.4.1 unified_search.py 수정

```python
# app/api/agents/tools/unified_search.py

class UnifiedSearchTool:
    """통합 검색 도구 (Semantic Search 통합)"""

    def __init__(
        self,
        query_understanding: QueryUnderstandingService,
        hybrid_retriever: HybridRetrieverService,
        result_fusion: ResultFusionService,
        # Legacy services (fallback)
        vector_search: VectorSearchService,
        summary_bm25: SummaryBM25Service,
    ):
        self.query_understanding = query_understanding
        self.hybrid_retriever = hybrid_retriever
        self.result_fusion = result_fusion
        # Legacy
        self.vector_search = vector_search
        self.summary_bm25 = summary_bm25

        # Feature flag
        self.use_semantic_search = os.getenv("USE_SEMANTIC_SEARCH", "true").lower() == "true"

    async def search(
        self,
        query: str,
        top_k: int = 10,
        **kwargs
    ) -> List[SearchResult]:
        """통합 검색 실행"""

        if self.use_semantic_search:
            return await self._semantic_search(query, top_k, **kwargs)
        else:
            return await self._legacy_search(query, top_k, **kwargs)

    async def _semantic_search(
        self,
        query: str,
        top_k: int,
        **kwargs
    ) -> List[SearchResult]:
        """새로운 Semantic Search 파이프라인"""

        # Stage 1: Query Understanding
        analysis = await self.query_understanding.analyze(query)

        # Stage 2: Hybrid Retrieval
        retrieval_results = await self.hybrid_retriever.retrieve(
            query=query,
            analysis=analysis,
            top_k=top_k * 2  # 융합 후 필터링을 위해 더 많이 가져옴
        )

        # Stage 3: Result Fusion (RRF)
        fused_results = self.result_fusion.fuse(
            result_lists=[
                [r for r in retrieval_results if r.source == "vector"],
                [r for r in retrieval_results if r.source == "keyword"],
                [r for r in retrieval_results if r.source == "entity"],
            ]
        )

        # Stage 4: Top-K 반환
        return fused_results[:top_k]

    async def _legacy_search(self, query: str, top_k: int, **kwargs) -> List[SearchResult]:
        """기존 검색 로직 (Fallback)"""
        # 기존 코드 유지
        pass
```

---

## 4. Data Models

### 4.1 QueryAnalysis Model

```python
# app/api/models/query_analysis.py

from pydantic import BaseModel, Field
from typing import List, Optional
from enum import Enum

class QueryIntent(str, Enum):
    EXPLANATION = "explanation"
    DEFINITION = "definition"
    USAGE = "usage"
    ERROR_RESOLUTION = "error"
    COMPARISON = "comparison"
    PROCEDURE = "procedure"
    CONFIGURATION = "configuration"
    SEARCH = "search"

class ExtractedEntity(BaseModel):
    type: str = Field(..., description="Entity type: command, error_code, product, config, term")
    value: str = Field(..., description="Extracted entity value")
    confidence: float = Field(ge=0.0, le=1.0, description="Extraction confidence")

class QueryAnalysis(BaseModel):
    original_query: str = Field(..., description="Original user query")
    intent: QueryIntent = Field(..., description="Classified query intent")
    entities: List[ExtractedEntity] = Field(default_factory=list)
    language: str = Field(..., description="Detected language code (ja, ko, en)")
    rewritten_query: str = Field(..., description="Search-optimized query")
    keywords: List[str] = Field(default_factory=list)

    class Config:
        json_schema_extra = {
            "example": {
                "original_query": "ofasmifコマンドについて説明してください",
                "intent": "explanation",
                "entities": [{"type": "command", "value": "ofasmif", "confidence": 0.95}],
                "language": "ja",
                "rewritten_query": "ofasmif command syntax usage parameters manual OFASM",
                "keywords": ["ofasmif", "command", "OFASM", "コマンド"]
            }
        }
```

### 4.2 SearchResult Model 확장

```python
# app/api/models/search_result.py (수정)

class SearchResult(BaseModel):
    doc_id: str
    content: str
    source: str = Field(..., description="Result source: vector, keyword, entity")
    score: float = Field(..., description="Final RRF score")
    original_scores: Dict[str, float] = Field(
        default_factory=dict,
        description="Original scores from each retriever"
    )
    metadata: Dict[str, Any] = Field(default_factory=dict)

    # 기존 필드 유지
    document_title: Optional[str] = None
    page_number: Optional[int] = None
    chunk_index: Optional[int] = None
```

---

## 5. Configuration

### 5.1 Environment Variables

```bash
# .env 추가 항목

# Semantic Search 설정
USE_SEMANTIC_SEARCH=true              # Semantic Search 활성화
QUERY_ANALYSIS_CACHE_TTL=3600         # 쿼리 분석 캐시 TTL (초)

# Hybrid Retrieval 가중치
RETRIEVAL_WEIGHT_VECTOR=1.0           # Vector search 가중치
RETRIEVAL_WEIGHT_KEYWORD=0.8          # Keyword search 가중치
RETRIEVAL_WEIGHT_ENTITY=1.2           # Entity lookup 가중치

# RRF 설정
RRF_K_CONSTANT=60                     # RRF k 상수

# Embedding 모델 (Phase 3에서 전환)
# EMBEDDING_MODEL=intfloat/multilingual-e5-large
```

### 5.2 Config Class

```python
# app/api/core/config.py (추가)

class SemanticSearchSettings(BaseSettings):
    use_semantic_search: bool = True
    query_analysis_cache_ttl: int = 3600

    retrieval_weight_vector: float = 1.0
    retrieval_weight_keyword: float = 0.8
    retrieval_weight_entity: float = 1.2

    rrf_k_constant: int = 60

    class Config:
        env_prefix = ""
```

---

## 6. Implementation Order

### Phase 1: Query Understanding (Week 1)

| # | Task | Files | Priority |
|---|------|-------|----------|
| 1.1 | QueryAnalysis 모델 생성 | `models/query_analysis.py` | High |
| 1.2 | QueryUnderstandingService 구현 | `services/query_understanding_service.py` | High |
| 1.3 | LLM Prompt 설계 및 테스트 | `prompts/query_understanding.txt` | High |
| 1.4 | 캐싱 레이어 구현 | `services/query_analysis_cache.py` | Medium |
| 1.5 | Unit Tests | `tests/test_query_understanding.py` | High |

### Phase 2: Hybrid Retrieval (Week 2)

| # | Task | Files | Priority |
|---|------|-------|----------|
| 2.1 | EntityLookupService 구현 | `services/entity_lookup_service.py` | High |
| 2.2 | HybridRetrieverService 구현 | `services/hybrid_retriever_service.py` | High |
| 2.3 | ResultFusionService (RRF) 구현 | `services/result_fusion_service.py` | High |
| 2.4 | unified_search.py 통합 | `agents/tools/unified_search.py` | High |
| 2.5 | Integration Tests | `tests/test_hybrid_retrieval.py` | High |

### Phase 3: Embedding Pipeline (Week 3)

| # | Task | Files | Priority |
|---|------|-------|----------|
| 3.1 | multilingual-e5-large 모델 통합 | `services/embedding_service.py` | Medium |
| 3.2 | 기존 문서 재임베딩 스크립트 | `scripts/reembed_documents.py` | Medium |
| 3.3 | 증분 업데이트 로직 | `services/document_indexer.py` | Medium |

### Phase 4: Evaluation & Tuning (Week 4)

| # | Task | Files | Priority |
|---|------|-------|----------|
| 4.1 | 테스트 쿼리셋 구축 (100+) | `e2e/semantic_search_queries.json` | High |
| 4.2 | Precision@K, Recall@K 측정 | `scripts/evaluate_search.py` | High |
| 4.3 | 가중치 튜닝 | Config 조정 | Medium |
| 4.4 | E2E 테스트 업데이트 | `e2e/e2e_semantic_test.js` | High |

---

## 7. Dependencies

### 7.1 New Python Packages

```txt
# requirements-api.txt 추가

# Semantic Search
sentence-transformers>=2.2.0    # Embedding 모델
redis>=4.0.0                    # 캐싱 (선택사항)
```

### 7.2 Existing Dependencies (활용)

- `langchain` - LLM 호출
- `neo4j` - Vector Index, Entity 저장소
- `rank_bm25` - BM25 검색 (유지)

---

## 8. Testing Strategy

### 8.1 Unit Tests

```python
# tests/test_query_understanding.py

@pytest.mark.asyncio
async def test_intent_classification():
    service = QueryUnderstandingService(mock_llm, mock_cache)

    # Japanese explanation query
    analysis = await service.analyze("ofasmifコマンドについて説明してください")
    assert analysis.intent == QueryIntent.EXPLANATION
    assert any(e.value == "ofasmif" for e in analysis.entities)
    assert analysis.language == "ja"

@pytest.mark.asyncio
async def test_entity_extraction():
    service = QueryUnderstandingService(mock_llm, mock_cache)

    # Error code query
    analysis = await service.analyze("에러코드 -5212 원인이 뭐야?")
    assert any(e.type == "error_code" and e.value == "-5212" for e in analysis.entities)
```

### 8.2 Integration Tests

```python
# tests/test_hybrid_retrieval.py

@pytest.mark.asyncio
async def test_hybrid_search_finds_ofasmif():
    retriever = HybridRetrieverService(...)
    analysis = QueryAnalysis(
        original_query="ofasmifコマンドについて説明してください",
        intent=QueryIntent.EXPLANATION,
        entities=[ExtractedEntity(type="command", value="ofasmif", confidence=0.95)],
        language="ja",
        rewritten_query="ofasmif command syntax usage manual OFASM",
        keywords=["ofasmif", "command", "OFASM"]
    )

    results = await retriever.retrieve("ofasmifコマンドについて説明してください", analysis)

    # ofasmif 관련 문서가 상위에 있어야 함
    assert any("ofasmif" in r.content.lower() for r in results[:3])
```

### 8.3 E2E Tests

```javascript
// e2e/e2e_semantic_test.js

const semanticTestCases = [
  {
    query: "ofasmifコマンドについて説明してください",
    expected: ["ofasmif", "OFASM"],
    notExpected: ["tjesmgr", "oscmgr"]
  },
  {
    query: "TJES가 뭐야?",
    expected: ["TJES", "Job Entry Subsystem"],
    notExpected: ["OSC", "HIDB"]
  },
  {
    query: "에러 -5212 해결방법",
    expected: ["-5212", "DATASET_NOT_FOUND"],
    notExpected: []
  }
];
```

---

## 9. Rollback Strategy

### 9.1 Feature Flag

```python
# 환경변수로 즉시 롤백 가능
USE_SEMANTIC_SEARCH=false  # Legacy 검색으로 즉시 전환
```

### 9.2 Gradual Rollout

```python
# 점진적 배포 (사용자 비율)
SEMANTIC_SEARCH_ROLLOUT_PERCENT=10  # 10% 사용자만 새 검색 사용
```

---

## 10. Success Metrics

| Metric | Current | Target | Measurement |
|--------|---------|--------|-------------|
| Top-3 Hit Rate | ~60% | **90%+** | E2E 테스트 |
| 평균 응답 시간 | 500ms | **< 1000ms** | API 로그 |
| Hallucination Rate | ~45% | **< 10%** | E2E 테스트 |
| 언어별 성능 차이 | 큼 | **±5% 이내** | 언어별 E2E 테스트 |

---

## 11. Appendix

### A. LLM Prompt Template 전문

```text
# Query Understanding System Prompt

You are a query analyzer for OpenFrame technical documentation search.

## Your Tasks:
1. Classify the query intent
2. Extract named entities (commands, error codes, products)
3. Detect the language
4. Rewrite the query for optimal search (remove filler phrases)
5. Extract key search keywords

## Known Products:
TJES, TACF, OSC, OFASM, HIDB, OpenFrame, OFMiner, OFManager, JEUS, Tibero, ProObject

## Known Commands:
tjesmgr, tacfmgr, oscmgr, ofasmif, hidbmgr, ndbmgr, volmgr, catmgr, idcams, dfsort

## Error Code Patterns:
- Numeric: -5212, -5001
- ABEND: S0C7, S0C4, S806
- Module prefix: DSALC_, SPAR_, etc.

## Output JSON Format:
{
  "intent": "explanation|definition|usage|error|comparison|procedure|configuration|search",
  "entities": [{"type": "command|error_code|product|config|term", "value": "...", "confidence": 0.0-1.0}],
  "language": "ja|ko|en",
  "rewritten_query": "English search-optimized query",
  "keywords": ["keyword1", "keyword2"]
}
```

### B. RRF 알고리즘 상세

```
Reciprocal Rank Fusion (RRF)

For each document d appearing in any result list:
  RRF_score(d) = Σ (1 / (k + rank_i(d)))

Where:
  - k = 60 (constant, prevents division by small numbers)
  - rank_i(d) = position of d in result list i (1-indexed)
  - If d not in list i, that term is 0

Weighted RRF:
  RRF_score(d) = Σ (weight_i / (k + rank_i(d)))

Example:
  Document X appears at:
  - Vector search: rank 1, weight 1.0
  - Keyword search: rank 5, weight 0.8
  - Entity lookup: rank 1, weight 1.2

  RRF(X) = 1.0/(60+1) + 0.8/(60+5) + 1.2/(60+1)
         = 0.0164 + 0.0123 + 0.0197
         = 0.0484
```

---

**Author**: Claude Code
**Date**: 2026-01-31
**Status**: Design Complete - Ready for Implementation
