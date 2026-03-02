# Semantic Search Architecture Plan

## 1. 문제 정의

### 현재 상태
- **BM25 기반 검색**: 키워드 토큰 매칭에 의존
- **CJK 토큰화**: bi-gram/tri-gram 생성 → 실제 단어와 불일치
- **Rule-based 전처리**: 특정 패턴만 처리, 확장 불가
- **결과**: "ofasmifコマンドについて説明してください" 같은 일반적인 쿼리 실패

### 근본 원인
| 문제 | 원인 | 영향 |
|------|------|------|
| 키워드 불일치 | BM25는 정확한 토큰 매칭 필요 | CJK에서 bi-gram이 원하는 단어와 안맞음 |
| 의미 이해 부재 | 통계적 매칭만 수행 | "説明してください"가 어떤 문서와도 매칭 |
| 필러 구문 영향 | 모든 토큰이 점수에 기여 | 관련없는 문서가 높은 점수 획득 |
| 패턴 폭발 | 사용자 쿼리 패턴 무한대 | Rule-based로 커버 불가능 |

## 2. 목표

1. **언어 독립적 검색**: 한국어/일본어/영어 쿼리 동일하게 처리
2. **의미 기반 매칭**: 키워드가 아닌 개념/의도 기반 검색
3. **Rule-free**: 새로운 쿼리 패턴에 자동 대응
4. **정확도 향상**: Top-3 결과에 정답 포함율 90% 이상

## 3. 제안 아키텍처

### 3.1 Multi-Stage Retrieval Pipeline

```
┌─────────────────────────────────────────────────────────────────┐
│                        User Query                                │
│              "ofasmifコマンドについて説明してください"              │
└─────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│                   Stage 1: Query Understanding                   │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │  LLM Query Analyzer                                      │   │
│  │  - Intent: "explanation_request"                         │   │
│  │  - Entity: "ofasmif" (command)                          │   │
│  │  - Topic: "command usage/syntax"                        │   │
│  │  - Language: Japanese                                    │   │
│  │  - Rewritten: "ofasmif command syntax usage manual"     │   │
│  └─────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│                   Stage 2: Parallel Retrieval                    │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────────┐ │
│  │  Vector     │  │  Keyword    │  │  Direct Lookup          │ │
│  │  Search     │  │  Search     │  │  (Entity → Index)       │ │
│  │             │  │             │  │                         │ │
│  │  Query      │  │  Rewritten  │  │  "ofasmif" →            │ │
│  │  Embedding  │  │  Query +    │  │  command_index          │ │
│  │  → Top 20   │  │  BM25       │  │  → Exact matches        │ │
│  └─────────────┘  └─────────────┘  └─────────────────────────┘ │
└─────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│                   Stage 3: Fusion & Re-ranking                   │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │  Reciprocal Rank Fusion (RRF)                           │   │
│  │  - Merge results from all retrievers                     │   │
│  │  - Remove duplicates                                     │   │
│  │  - Initial ranking by RRF score                         │   │
│  └─────────────────────────────────────────────────────────┘   │
│                              │                                   │
│                              ▼                                   │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │  Cross-Encoder Re-ranker (Optional)                      │   │
│  │  - Query-Document relevance scoring                      │   │
│  │  - Fine-grained semantic matching                       │   │
│  └─────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│                   Stage 4: Result Delivery                       │
│  - Top-K results with confidence scores                         │
│  - Source citations (PDF, page numbers)                         │
│  - Related images/tables                                        │
└─────────────────────────────────────────────────────────────────┘
```

### 3.2 핵심 컴포넌트

#### Component 1: Query Understanding Service
```python
class QueryUnderstandingService:
    """
    LLM 기반 쿼리 분석 서비스
    - 언어 감지
    - 의도 분류 (정의, 사용법, 에러해결, 비교 등)
    - 엔티티 추출 (명령어, 제품명, 에러코드 등)
    - 쿼리 재작성 (검색 최적화 형태로)
    """

    async def analyze(self, query: str) -> QueryAnalysis:
        # LLM으로 분석
        # 캐싱으로 동일 쿼리 재분석 방지
        pass

    async def rewrite_for_search(self, query: str) -> str:
        # 검색에 최적화된 형태로 재작성
        # "ofasmifコマンドについて説明してください"
        # → "ofasmif command syntax usage parameters examples"
        pass
```

#### Component 2: Hybrid Retriever
```python
class HybridRetriever:
    """
    다중 검색 전략 조합
    """

    def __init__(self):
        self.vector_retriever = VectorRetriever()  # Embedding 기반
        self.keyword_retriever = KeywordRetriever()  # BM25 기반
        self.entity_retriever = EntityRetriever()  # Direct lookup

    async def retrieve(
        self,
        query: str,
        query_analysis: QueryAnalysis,
        top_k: int = 20
    ) -> List[Document]:
        # 병렬 검색 실행
        vector_results = await self.vector_retriever.search(query, top_k)
        keyword_results = await self.keyword_retriever.search(
            query_analysis.rewritten_query, top_k
        )
        entity_results = await self.entity_retriever.lookup(
            query_analysis.entities
        )

        # Reciprocal Rank Fusion
        return self.fuse_results(
            vector_results,
            keyword_results,
            entity_results
        )
```

#### Component 3: Document Embedder
```python
class DocumentEmbedder:
    """
    문서 임베딩 생성 및 관리
    - Multilingual embedding model 사용
    - Chunk-level embedding
    - 증분 업데이트 지원
    """

    def __init__(self, model: str = "intfloat/multilingual-e5-large"):
        self.model = SentenceTransformer(model)

    async def embed_documents(self, documents: List[Document]):
        # 청크 단위로 임베딩 생성
        # Vector DB에 저장
        pass

    async def embed_query(self, query: str) -> np.ndarray:
        # 쿼리 임베딩 생성
        pass
```

### 3.3 데이터 흐름

```
[Document Ingestion]
PDF/MD → Parse → Chunk → Embed → Vector DB (Neo4j/Qdrant)
                    ↓
              Extract Entities → Entity Index (Commands, Errors, Terms)
                    ↓
              Generate Keywords → BM25 Index

[Query Processing]
User Query → Query Understanding → Parallel Retrieval → Fusion → Re-rank → Results
```

## 4. 기술 스택

| 컴포넌트 | 현재 | 제안 |
|----------|------|------|
| Query Understanding | Rule-based + 부분적 LLM | **Full LLM-based** |
| Vector Search | Neo4j Vector Index | Neo4j Vector Index (유지) |
| Keyword Search | BM25 (rank_bm25) | BM25 (유지, 보조 역할) |
| Embedding Model | NV-EmbedQA-Mistral | **multilingual-e5-large** (다국어 지원) |
| Re-ranker | 없음 | **Cross-encoder** (선택적) |
| Result Fusion | 없음 | **Reciprocal Rank Fusion** |

## 5. 구현 단계

### Phase 1: Query Understanding 고도화 (1주)
- [ ] QueryUnderstandingService 구현
- [ ] Intent classification 프롬프트 설계
- [ ] Entity extraction 프롬프트 설계
- [ ] Query rewriting 프롬프트 설계
- [ ] 캐싱 레이어 추가

### Phase 2: Hybrid Retrieval 구현 (1주)
- [ ] HybridRetriever 클래스 구현
- [ ] Reciprocal Rank Fusion 구현
- [ ] Vector/Keyword/Entity 검색 통합
- [ ] unified_search.py 리팩토링

### Phase 3: Embedding 파이프라인 개선 (1주)
- [ ] multilingual-e5-large 모델 통합
- [ ] 기존 문서 재임베딩 스크립트
- [ ] 증분 업데이트 로직

### Phase 4: 평가 및 튜닝 (1주)
- [ ] 테스트 쿼리셋 구축 (100+ 쿼리)
- [ ] Precision@K, Recall@K 측정
- [ ] 가중치 튜닝 (Vector vs Keyword vs Entity)
- [ ] A/B 테스트

## 6. 예상 결과

### Before (현재)
```
Query: "ofasmifコマンドについて説明してください"
Result: "No relevant content found"
```

### After (개선 후)
```
Query: "ofasmifコマンドについて説明してください"

[Query Understanding]
- Intent: explanation_request
- Entity: ofasmif (command)
- Rewritten: "ofasmif command syntax usage manual"

[Retrieval Results]
1. [0.92] ofasmif - OF_ASM_Reference_Guide (Commands)
2. [0.87] OFASM 명령어 개요 - OF_ASM_User_Guide (Concepts)
3. [0.81] ofasmif 실행 예제 - OF_ASM_Examples (Procedures)
```

## 7. 리스크 및 대응

| 리스크 | 영향 | 대응 |
|--------|------|------|
| LLM 응답 지연 | 검색 속도 저하 | 캐싱, 비동기 처리 |
| 임베딩 품질 | 검색 정확도 저하 | 모델 평가/교체, 파인튜닝 |
| 인덱스 재생성 비용 | 다운타임 | 증분 업데이트, 백그라운드 처리 |

## 8. 성공 지표

| 지표 | 현재 | 목표 |
|------|------|------|
| Top-3 Hit Rate | ~60% | **90%+** |
| 평균 응답 시간 | 500ms | **< 1000ms** |
| Rule 유지보수 | 수동 추가 필요 | **Zero maintenance** |
| 언어별 성능 차이 | 큼 (JA/KO 낮음) | **동등** |

---

**Author**: Claude Code
**Date**: 2026-01-31
**Status**: Draft - Pending Review
