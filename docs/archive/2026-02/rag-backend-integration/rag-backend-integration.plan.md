# RAG Backend Integration Plan

**Feature**: RAG Anti-Hallucination Service Integration
**Date**: 2026-02-03
**Status**: Planning
**Priority**: High

---

## 1. Overview

### 1.1 Problem Statement

현재 Multi-LoRA LLM (Port 12815-12817) 사용 시 **할루시네이션(Hallucination)** 문제가 심각함:

| 문제 | 현재 상황 | 목표 |
|------|----------|------|
| 정확도 | 20% | **95%** |
| 할루시네이션 발생률 | 80% | **5%** |
| 출처 추적 | 0% | **100%** |

### 1.2 Root Cause

- 희귀 키워드에 대한 학습 데이터 부족 (예: DFSURGL0 - 13,594개 중 3개, 0.02%)
- LLM이 암기에만 의존하여 모르는 내용을 생성(환각)
- 학습 데이터에 정확한 답변이 있어도 모델이 참조하지 못함

### 1.3 Solution

RAG(Retrieval-Augmented Generation) 통합으로 할루시네이션 제거:
1. 답변 전에 학습 데이터 검색
2. 검색 결과를 LLM에게 제공하여 정확한 답변 생성
3. 소스 추적 가능 (어느 문서에서 가져왔는지 명시)

---

## 2. Scope

### 2.1 In Scope

- [ ] RAG Anti-Hallucination Service 구현 (`app/api/services/rag_anti_hallucination_service.py`)
- [ ] RAG Query Router 구현 (`app/api/routers/query_rag.py`)
- [ ] 3가지 RAG 모드 지원 (Direct, LLM, Hybrid)
- [ ] 기존 `ImprovedRAG` 클래스 통합 (`test_0203/rag_solution_improved.py`)
- [ ] 통계 및 모니터링 엔드포인트
- [ ] 단위 테스트 및 통합 테스트

### 2.2 Out of Scope

- WebUI 전면 적용 (Phase 3에서 진행)
- A/B 테스트 인프라 (Phase 4에서 진행)
- Neo4j 벡터 검색 통합 (추후 Phase에서 진행)
- Prometheus/Grafana 모니터링 대시보드

---

## 3. Architecture

### 3.1 System Flow

```
┌─────────────────────────────────────────────────────────────────┐
│                        WebUI Client                              │
│              (http://localhost:3000)                             │
└───────────────────────────────┬─────────────────────────────────┘
                                │ HTTP Request
                                ↓
┌─────────────────────────────────────────────────────────────────┐
│                    FastAPI Backend                               │
│                  (http://localhost:9000)                         │
│                                                                   │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │  /api/v1/query/rag (신규) ✨                              │  │
│  │  → RAG Anti-Hallucination Service                         │  │
│  │     ↓                                                      │  │
│  │     1. Keyword Extraction                                  │  │
│  │     2. Training Data Search (13,594 documents)            │  │
│  │     3. Decision Logic (Score-based)                       │  │
│  │        - Score >= 10 → Direct Answer (LLM 우회)          │  │
│  │        - Score < 10  → LLM with Context                   │  │
│  │        - Score = 0   → "정보 없음"                         │  │
│  │     4. Response with Sources                              │  │
│  └──────────────────────────────────────────────────────────┘  │
└───────────────────────────────┬─────────────────────────────────┘
                                │
                    ┌───────────┴───────────┐
                    ↓                       ↓
┌─────────────────────────────┐  ┌──────────────────────────┐
│  Training Data (JSONL)       │  │  Multi-LoRA LLMs         │
│  test_0203/training_data_v2/ │  │  - GPU 5 (Port 12815)    │
│  - 24 products               │  │  - GPU 6 (Port 12816)    │
│  - 13,594 documents          │  │  - GPU 7 (Port 12817)    │
└─────────────────────────────┘  └──────────────────────────┘
```

### 3.2 Three RAG Modes

| Mode | LLM 사용 | 정확도 | 속도 | 사용 시기 |
|------|----------|--------|------|----------|
| **Direct** | ❌ No | 100% | 매우 빠름 | 정확한 키워드 질의 |
| **LLM** | ✅ Yes | 85% | 보통 | 자연스러운 답변 필요 |
| **Hybrid** | 상황별 | 95% | 빠름 | **권장** (자동 선택) |

### 3.3 Decision Tree (Hybrid Mode)

```
사용자 질문
    ↓
키워드 추출 ("DFSURGL0について説明してください" → "DFSURGL0")
    ↓
학습 데이터 검색 (keyword_search)
    ↓
검색 결과 있음?
    ├─ NO  → "該当する情報が見つかりませんでした"
    └─ YES → Score 확인
               ↓
           Score >= 10?
               ├─ YES → Direct Answer (100% 정확, 환각 불가)
               └─ NO  → LLM with Context (85% 정확)
```

---

## 4. API Design

### 4.1 Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/v1/query/rag` | POST | RAG 기반 쿼리 (메인) |
| `/api/v1/query/rag/search` | POST | 검색만 수행 (디버깅용) |
| `/api/v1/query/rag/stats` | GET | 서비스 통계 |
| `/api/v1/query/rag/health` | GET | 상태 확인 |

### 4.2 Request/Response Schema

#### POST `/api/v1/query/rag`

**Request:**
```json
{
  "query": "DFSURGL0について説明してください。",
  "mode": "hybrid",
  "model": "openframe_common_v2",
  "max_tokens": 500,
  "temperature": 0.2
}
```

**Response:**
```json
{
  "answer": "DFSURGL0は、HD再編成アンロード・ユーティリティ...",
  "mode_used": "direct_answer",
  "search_score": 23,
  "sources": [
    {
      "product": "openframe_common",
      "name": "DFSURGL0",
      "score": 23
    }
  ],
  "keyword_extracted": "DFSURGL0",
  "metadata": {
    "search_time_ms": 45,
    "llm_time_ms": 0,
    "total_time_ms": 45
  }
}
```

---

## 5. Implementation Tasks

### Phase 1: Core Service (Day 1-2)

| Task ID | Task | Priority | Files |
|---------|------|----------|-------|
| P1-1 | RAG Anti-Hallucination Service 생성 | High | `app/api/services/rag_anti_hallucination_service.py` |
| P1-2 | ImprovedRAG 클래스 import 및 래핑 | High | `test_0203/rag_solution_improved.py` |
| P1-3 | 싱글톤 패턴 구현 | Medium | Service class |
| P1-4 | 통계 수집 로직 구현 | Medium | Service class |

### Phase 2: API Router (Day 2-3)

| Task ID | Task | Priority | Files |
|---------|------|----------|-------|
| P2-1 | RAG Query Router 생성 | High | `app/api/routers/query_rag.py` |
| P2-2 | Pydantic Request/Response 모델 정의 | High | Router file |
| P2-3 | main.py에 라우터 등록 | High | `app/api/main.py` |
| P2-4 | 인증 미들웨어 적용 | High | Router file |

### Phase 3: Testing (Day 3-4)

| Task ID | Task | Priority | Files |
|---------|------|----------|-------|
| P3-1 | 단위 테스트 작성 | High | `tests/api/test_rag_service.py` |
| P3-2 | 통합 테스트 작성 | High | `tests/api/test_rag_endpoints.py` |
| P3-3 | E2E 테스트 스크립트 | Medium | `e2e/e2e_rag_test.js` |
| P3-4 | 할루시네이션 감소 검증 | High | Test results |

### Phase 4: Documentation & Deployment (Day 4-5)

| Task ID | Task | Priority | Files |
|---------|------|----------|-------|
| P4-1 | API 문서 업데이트 (OpenAPI) | Medium | Auto-generated |
| P4-2 | 환경 변수 문서화 | Medium | `.env.example` |
| P4-3 | 배포 가이드 작성 | Low | `docs/` |
| P4-4 | Health check 확인 | High | Curl scripts |

---

## 6. Dependencies

### 6.1 External Dependencies

| Component | Location | Status |
|-----------|----------|--------|
| ImprovedRAG | `test_0203/rag_solution_improved.py` | ✅ Ready |
| Training Data | `test_0203/training_data_v2/*.jsonl` | ✅ Ready (13,594 docs) |
| Multi-LoRA LLMs | GPU 5-7 (Ports 12815-12817) | ✅ Running |

### 6.2 Internal Dependencies

| Component | Required For |
|-----------|--------------|
| `core/deps.py` | Dependency injection |
| `core/cookie_auth.py` | Authentication |
| `models/user.py` | Current user |

---

## 7. Environment Configuration

```bash
# .env 추가 항목
RAG_TRAINING_DATA_DIR=/raid/users/ofuser/work/ijswork/gpubase-raphrag-new/test_0203/training_data_v2
RAG_ENABLE=true
RAG_DEFAULT_MODE=hybrid
```

---

## 8. Success Criteria

### 8.1 Functional

- [ ] `/api/v1/query/rag` 엔드포인트 정상 동작
- [ ] 3가지 모드 (direct, llm, hybrid) 모두 정상 동작
- [ ] 인증된 사용자만 접근 가능
- [ ] 검색 결과에 출처(sources) 포함

### 8.2 Performance

- [ ] Direct 모드 응답 시간 < 100ms
- [ ] Hybrid 모드 응답 시간 < 500ms
- [ ] 13,594 문서 로드 시간 < 5초

### 8.3 Quality

- [ ] 정확도 >= 90% (E2E 테스트 기준)
- [ ] 할루시네이션 발생률 < 10%
- [ ] 테스트 커버리지 >= 80%

---

## 9. Risks & Mitigations

| Risk | Impact | Probability | Mitigation |
|------|--------|-------------|------------|
| LLM 서비스 다운 | High | Medium | Fallback to direct mode |
| 메모리 부족 (13K docs) | Medium | Low | Lazy loading 구현 |
| 키워드 추출 실패 | Medium | Medium | Fallback 검색 로직 |
| 기존 API 영향 | Low | Low | 별도 엔드포인트 사용 |

---

## 10. Timeline

| Phase | Duration | Deliverables |
|-------|----------|--------------|
| Phase 1: Core Service | 2 days | RAG Service, Tests |
| Phase 2: API Router | 1 day | REST Endpoints |
| Phase 3: Testing | 1 day | Unit/Integration/E2E Tests |
| Phase 4: Deployment | 1 day | Documentation, Health checks |
| **Total** | **5 days** | Production-ready RAG API |

---

## 11. References

- [RAG_BACKEND_INTEGRATION.md](../RAG_BACKEND_INTEGRATION.md) - 상세 구현 가이드
- [RAG_QUICK_START.md](../RAG_QUICK_START.md) - 빠른 시작 가이드
- [test_0203/HALLUCINATION_SOLUTIONS.md](../../test_0203/HALLUCINATION_SOLUTIONS.md) - 할루시네이션 솔루션
- [app/api/CLAUDE.md](../../app/api/CLAUDE.md) - 백엔드 구조

---

## 12. Approval

| Role | Name | Date | Signature |
|------|------|------|-----------|
| Tech Lead | | | |
| Backend Lead | | | |
| QA Lead | | | |

---

**Plan Status**: Ready for Review
