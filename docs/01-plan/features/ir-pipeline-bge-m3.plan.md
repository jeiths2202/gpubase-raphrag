# Plan: BGE-M3 IR Pipeline Integration

> **Feature**: BGE-M3 기반 Hybrid IR Pipeline (Sparse + Dense + Reranker) 도입 및 Agentic RAG 연동
> **Created**: 2026-02-25
> **Status**: Draft
> **Priority**: High

---

## 1. 현재 상태 분석 (As-Is)

### 1.1 현재 검색 파이프라인

```
Query
  ↓
[1] Keyword Search (structured_knowledge_store.py)
    - CJK-aware 토큰화 + IDF 가중치
    - Title match: +3.0*IDF, Content match: +1.0*IDF
    - Domain boosting (pdf_manuals: 1.5, commands: 1.3, ...)
    - Progressive pruning (top_k * 20 후보)
  ↓
[2] Semantic Reranking (_apply_semantic_reranking)
    - 상위 20개 후보에 NV-EmbedQA (4096 dims) 적용
    - Hybrid: 60% keyword + 40% semantic (cosine similarity)
    - 3초 timeout, 실패 시 keyword fallback
  ↓
[3] Top-K 결과 → LLM 생성
```

### 1.2 현재 Embedding 인프라

| 항목 | 현재 값 | 문제점 |
|------|---------|--------|
| 모델 | NV-EmbedQA-Mistral 7B v2 | 4096 dims → 메모리/속도 부담 |
| 포트 | 192.168.8.11:12801 | **BGE-M3로 교체 완료** |
| Sparse 검색 | 자체 keyword/IDF 구현 | BM25 미지원, 정밀도 한계 |
| Reranker | cross_encoder_reranker.py (미사용) | 파이프라인 미연결 |
| 사전 임베딩 | 없음 (on-the-fly만) | 매 쿼리마다 doc 임베딩 반복 |

### 1.3 BGE-M3 서버 현황 (이미 배포됨)

| 항목 | 값 |
|------|-----|
| Container | `bge-m3-server` (docker_bge-m3) |
| Host | 192.168.8.11:12801 |
| Health | `GET /v1/health/ready` → `{"status":"ready","model":"bge-m3","device":"cuda"}` |
| Dense | `POST /v1/embeddings` → 1024 dims |
| Sparse | `POST /v1/sparse` → token_id:weight dict |
| Hybrid | `POST /v1/hybrid` → dense(1024) + sparse_weights |
| Input | `{"input": "text" \| ["text1","text2"], "model": "bge-m3"}` |

---

## 2. 목표 상태 (To-Be)

### 2.1 목표 IR 파이프라인

```
Query
  ↓
[1] BGE-M3 Hybrid Encoding
    - POST /v1/hybrid → {dense: [1024], sparse_weights: {token_id: weight}}
  ↓
[2] Dual Retrieval (병렬)
    ├── [Sparse] BGE-M3 sparse weights → 기존 문서 sparse vectors와 dot product
    └── [Dense] BGE-M3 dense embedding → 사전 계산된 문서 embeddings와 cosine sim
  ↓
[3] Reciprocal Rank Fusion (RRF)
    - RRF(d) = Σ 1/(k + rank_sparse(d)) + 1/(k + rank_dense(d))
    - k=60 (standard)
  ↓
[4] Reranker (Top-N 후보)
    - BGE-M3 dense similarity로 fine-grained reranking
    - 또는 cross-encoder (향후 확장)
  ↓
[5] Top-K 문서 → LLM 생성
```

### 2.2 핵심 변경 사항

| 구분 | Before | After |
|------|--------|-------|
| Embedding 모델 | NV-EmbedQA (4096d) | BGE-M3 (1024d) |
| Sparse 검색 | 자체 keyword/IDF | BGE-M3 learned sparse |
| Dense 검색 | On-the-fly only | **사전 임베딩 + 실시간 쿼리** |
| 후보 병합 | Hybrid α blend | **RRF (Reciprocal Rank Fusion)** |
| Reranker | 미사용 | **BGE-M3 dense reranking** |
| config.py | NV-EmbedQA defaults | BGE-M3 defaults (1024d) |

---

## 3. 구현 계획

### Phase 1: BGE-M3 IR Service 생성 (신규)

**파일**: `app/api/services/bge_m3_ir_service.py` (신규)

```python
class BgeM3IRService:
    """BGE-M3 기반 Hybrid IR (Sparse + Dense + Reranker) 서비스"""

    # Singleton 패턴
    _instance = None

    # 사전 계산된 임베딩 캐시
    _doc_dense_cache: Dict[str, List[float]]    # doc_key → dense vector
    _doc_sparse_cache: Dict[str, Dict[str, float]]  # doc_key → sparse weights

    async def encode_hybrid(self, texts: List[str]) -> List[HybridEmbedding]:
        """BGE-M3 /v1/hybrid 호출 → dense + sparse 동시 반환"""

    async def encode_dense(self, texts: List[str]) -> List[List[float]]:
        """BGE-M3 /v1/embeddings 호출 → dense vectors"""

    async def encode_sparse(self, texts: List[str]) -> List[Dict[str, float]]:
        """BGE-M3 /v1/sparse 호출 → sparse weights"""

    async def precompute_document_embeddings(self, sections: List[Section]):
        """서비스 초기화 시 모든 문서 섹션의 dense+sparse 임베딩 사전 계산"""

    async def hybrid_search(
        self, query: str, candidates: List[Section], top_k: int
    ) -> List[SearchResult]:
        """
        1) query hybrid encoding
        2) dense similarity + sparse similarity 각각 계산
        3) RRF 병합
        4) top-k 반환
        """

    async def rerank(
        self, query: str, results: List[SearchResult], top_k: int
    ) -> List[SearchResult]:
        """dense similarity 기반 정밀 reranking"""

    def _rrf_fusion(
        self, sparse_ranks: List, dense_ranks: List, k: int = 60
    ) -> List:
        """Reciprocal Rank Fusion"""
```

### Phase 2: StructuredKnowledgeStore 수정

**파일**: `app/api/services/structured_knowledge_store.py`

변경 내용:
1. `_embed_texts()` → BGE-M3 호출로 변경 (model: "bge-m3", dim: 1024)
2. `_apply_semantic_reranking()` → `BgeM3IRService.hybrid_search()` 호출로 대체
3. `search()` → IR 파이프라인 통합
4. 초기화 시 `precompute_document_embeddings()` 호출 (lazy)

```python
# Before (line 929):
"model": "NV-Embed-QA",

# After:
"model": "bge-m3",
```

```python
# Before: _apply_semantic_reranking에서 단순 cosine similarity
# After: BgeM3IRService.hybrid_search() 사용
async def search(self, query, domains, top_k, skip_semantic_reranking):
    # Phase 1: Keyword search (기존 유지 - fast path)
    keyword_results = self._keyword_search(query, domains, top_k * 5)

    if skip_semantic_reranking:
        return keyword_results[:top_k]

    # Phase 2: BGE-M3 Hybrid IR Pipeline
    ir_service = get_bge_m3_ir_service()
    return await ir_service.hybrid_search(query, keyword_results, top_k)
```

### Phase 3: 환경 설정 업데이트

**파일**: `.env.local`, `app/api/core/config.py`

```env
# .env.local 변경
EMBEDDING_API_URL=http://192.168.8.11:12801/v1
EMBEDDING_MODEL=bge-m3
EMBEDDING_DIMENSION=1024
EMBEDDING_BATCH_SIZE=64
EMBEDDING_MAX_TOKENS=512
EMBEDDING_SAFE_TOKEN_LIMIT=380

# 신규 추가
BGE_M3_SPARSE_URL=http://192.168.8.11:12801/v1/sparse
BGE_M3_HYBRID_URL=http://192.168.8.11:12801/v1/hybrid
BGE_M3_HEALTH_URL=http://192.168.8.11:12801/v1/health/ready
IR_RRF_K=60
IR_SPARSE_WEIGHT=0.4
IR_DENSE_WEIGHT=0.6
IR_PRECOMPUTE_ON_STARTUP=true
```

**config.py 추가**:
```python
# BGE-M3 IR Pipeline Settings
BGE_M3_BASE_URL: str = Field(
    default="http://192.168.8.11:12801",
    description="BGE-M3 IR server base URL"
)
IR_RRF_K: int = Field(default=60, description="RRF k parameter")
IR_SPARSE_WEIGHT: float = Field(default=0.4, description="Sparse retrieval weight")
IR_DENSE_WEIGHT: float = Field(default=0.6, description="Dense retrieval weight")
IR_PRECOMPUTE_ON_STARTUP: bool = Field(
    default=True, description="Pre-compute document embeddings on startup"
)
```

### Phase 4: Frontend/Backend 재기동

1. `.env.local` → `.env` 복사 (새 설정 반영)
2. Backend 재기동: `.\scripts\server.ps1 backend restart`
3. Frontend 재기동: `.\scripts\server.ps1 frontend restart`
4. 또는 Docker: `docker restart kms-backend-local kms-frontend-local`

### Phase 5: 테스트 및 검증

1. BGE-M3 Health Check: `curl http://192.168.8.11:12801/v1/health/ready`
2. IR Pipeline 단위 테스트: hybrid_search, RRF, rerank
3. Agentic RAG E2E 테스트: `node e2e/e2e_sentence_test.js`
4. 성능 비교: Before(NV-EmbedQA) vs After(BGE-M3 IR)

---

## 4. 수정 대상 파일

| 파일 | 변경 유형 | 내용 |
|------|----------|------|
| `app/api/services/bge_m3_ir_service.py` | **신규** | BGE-M3 IR Pipeline 서비스 |
| `app/api/services/structured_knowledge_store.py` | 수정 | IR 파이프라인 통합, model 변경 |
| `app/api/core/config.py` | 수정 | BGE-M3/IR 설정 추가 |
| `.env.local` | 수정 | Embedding → BGE-M3 설정 |
| `.env` | 수정 | 활성 설정 반영 |
| `app/api/services/agentic_rag_service.py` | 수정 (최소) | IR service import 확인 |

---

## 5. 리스크 및 대응

| 리스크 | 영향 | 대응 |
|--------|------|------|
| BGE-M3 sparse 응답 포맷 비호환 | Sparse 검색 실패 | Fallback: 기존 keyword 검색 유지 |
| 사전 임베딩 메모리 부담 | 서비스 시작 지연 | Lazy loading + batch precompute |
| 1024d vs 4096d 차원 변경 | Neo4j vector index 불일치 | SKS는 Neo4j 미사용 (인메모리) |
| 일본어 sparse tokenization | 토큰 품질 저하 | BGE-M3는 multilingual 학습됨 |
| 서비스 재기동 시 임베딩 캐시 소실 | Cold start 지연 | 디스크 캐시 옵션 추가 |

---

## 6. 성공 기준

| 지표 | 목표 |
|------|------|
| E2E Hallucination 테스트 | 현재 53% 실패 → 40% 이하 |
| 검색 Latency (p95) | < 500ms (현재 ~300ms keyword + 3s embedding) |
| IR Pipeline 가동율 | BGE-M3 실패 시 keyword fallback 100% |
| Top-3 Precision | 측정 후 10%+ 개선 목표 |

---

## 7. 의존성

| 항목 | 상태 |
|------|------|
| BGE-M3 Docker 컨테이너 | ✅ 배포 완료 (192.168.8.11:12801) |
| Dense API (/v1/embeddings) | ✅ 동작 확인 (1024 dims) |
| Sparse API (/v1/sparse) | ⚠️ 일본어 테스트 필요 |
| Hybrid API (/v1/hybrid) | ✅ 동작 확인 (dense + sparse) |
| Frontend (AgenticRAGPage) | 변경 불필요 (백엔드 투명 교체) |
