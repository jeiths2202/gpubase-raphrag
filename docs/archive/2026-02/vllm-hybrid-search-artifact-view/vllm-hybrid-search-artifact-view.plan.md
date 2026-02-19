# Plan: vLLM Hybrid Search + Artifact View for Modernization AI

## Overview

| Item | Value |
|------|-------|
| Feature | vllm-hybrid-search-artifact-view |
| Phase | Plan |
| Priority | High |
| Scope | Backend (StructuredKnowledgeStore) + Frontend (Modernization AI artifact) |
| Estimated Files | ~8 files (3 backend, 5 frontend) |

## Problem Statement

현재 Modernization AI의 OpenFrame 검색 파이프라인에 3가지 개선 필요:

1. **키워드 기반 검색만 사용**: `StructuredKnowledgeStore.search()`가 Progressive Token + IDF 기반으로만 검색 → 의미적 유사도 기반 검색이 없어 관련 문서를 놓칠 수 있음
2. **결과 수 과다**: 기본 top_k=5로 반환 → 유사도 낮은 결과가 LLM 컨텍스트에 포함되어 반복적/중복 응답 유발
3. **긴 답변 가독성 문제**: 채팅창 내에서 긴 LLM 응답이 스크롤만으로 표시 → 마크다운 테이블 등 구조화된 응답의 가독성 저하

## Goal

1. `StructuredKnowledgeStore.search()` 마지막에 **vLLM 임베딩 기반 시맨틱 검색** 추가 (Hybrid: 키워드+IDF + vLLM semantic)
2. 최종 결과를 **유사도 순 top 3**로 제한하여 LLM 컨텍스트 품질 향상
3. Modernization AI 채팅에서 **일정 문자 수 초과 시 Artifact 뷰**로 전체 답변 표시 (마크다운 테이블 형식 필수)

## Architecture Decision

### 현재 상태 (AS-IS)

```
사용자 질문
    ↓
ProductRouterService.classify() → product_id
    ↓
BaseProductAgent.search()
    ↓
StructuredKnowledgeStore.search() [키워드+IDF만, top_k=5]
    ↓
_build_llm_context() → [5개 결과 포함]
    ↓
LearningLLMService.generate_stream() → 채팅창에 그대로 출력
```

### 목표 상태 (TO-BE)

```
사용자 질문
    ↓
ProductRouterService.classify() → product_id
    ↓
BaseProductAgent.search()
    ↓
StructuredKnowledgeStore.search()
    ├─ Phase 1: 키워드+IDF 스코어링 (기존)
    └─ Phase 2: vLLM 임베딩 시맨틱 유사도 (NEW)
    ↓
Hybrid Score = α * keyword_score + (1-α) * semantic_score
    ↓
Top 3 by hybrid_score → _build_llm_context()
    ↓
LearningLLMService.generate_stream()
    ↓
Frontend: 문자 수 판별
    ├─ ≤ THRESHOLD: 채팅 메시지 버블에 표시
    └─ > THRESHOLD: Artifact 뷰에서 markdown table 포함 전체 출력
```

## Requirements

### FR-01: vLLM Semantic Search 추가

**파일**: `app/api/services/structured_knowledge_store.py`

기존 `search()` 메서드의 키워드+IDF 스코어링 이후:
1. vLLM 임베딩 서비스(`http://192.168.8.11:12801/v1`)로 쿼리 벡터 생성
2. 상위 키워드 후보 섹션들의 content를 배치 임베딩
3. 코사인 유사도 계산하여 semantic_score 부여
4. Hybrid score 병합: `hybrid = 0.6 * normalized_keyword + 0.4 * semantic_score`

**제약 사항**:
- vLLM 임베딩 서비스 연결 실패 시 기존 키워드 점수만으로 fallback (graceful degradation)
- 임베딩 대상은 키워드 검색 상위 후보만 (전체 섹션 임베딩은 비효율)
- 비동기 처리 (`async`/`await`) + 타임아웃 3초

### FR-02: Top 3 결과 제한

**파일**: `app/api/services/structured_knowledge_store.py`

- `search()` 반환 결과를 hybrid_score 내림차순으로 정렬 후 **최대 3개**만 반환
- 호출자(`BaseProductAgent.search()`)에서 top_k 파라미터 전달 시 해당 값 존중
- `_build_llm_context()`에서도 결과 수 감소에 맞게 per_result_limit 조정

### FR-03: Artifact 뷰 (Frontend)

**파일**: `kms-portal-ui/src/components/ModernizationAI/ModernizationAIAssistant.tsx`

1. LLM 응답 완료 후 메시지 content의 문자 수 판별
2. **ARTIFACT_THRESHOLD** (예: 500문자) 초과 시:
   - 채팅 버블에는 요약/첫 부분만 표시 + "전체 보기" 버튼
   - 클릭 시 **Artifact 패널**이 채팅창 옆 또는 오버레이로 열림
   - Artifact 패널에서 **마크다운 테이블** 포함 전체 내용 렌더링
3. 마크다운 테이블 파싱: `renderMessageContent()`에 테이블 렌더링 로직 추가
   - `| col1 | col2 |` 패턴 감지 → `<table>` HTML 변환

### FR-04: LLM 응답 마크다운 테이블 형식 유도

**파일**: `app/api/services/agentic_rag_service.py` (`_stream_llm` 또는 system prompt)

- LLM system prompt에 "検索結果はmarkdown table形式で出力してください" 지시 추가
- 검색 결과가 3건일 때 테이블 포맷으로 정리하도록 유도:
  ```
  | No | 項目 | 内容 | ソース |
  |----|------|------|--------|
  | 1  | ...  | ...  | ...    |
  ```

## Implementation Plan

### Phase 1: Backend - vLLM Semantic Search (FR-01, FR-02)

| Step | File | Description |
|------|------|-------------|
| 1 | `structured_knowledge_store.py` | `_embed_query()` 메서드 추가 - vLLM 임베딩 API 호출 |
| 2 | `structured_knowledge_store.py` | `_embed_batch()` 메서드 추가 - 후보 섹션 배치 임베딩 |
| 3 | `structured_knowledge_store.py` | `_cosine_similarity()` 유틸 추가 |
| 4 | `structured_knowledge_store.py` | `search()` 마지막에 semantic scoring + hybrid merge 추가 |
| 5 | `structured_knowledge_store.py` | 최종 결과를 top 3으로 제한 |
| 6 | `agentic_rag_service.py` | `_build_llm_context()`의 결과 수 조정 반영 |

### Phase 2: Backend - LLM 테이블 포맷 유도 (FR-04)

| Step | File | Description |
|------|------|-------------|
| 7 | `learning_llm_service.py` 또는 `agentic_rag_service.py` | system prompt에 markdown table 출력 지시 추가 |

### Phase 3: Frontend - Artifact 뷰 (FR-03)

| Step | File | Description |
|------|------|-------------|
| 8 | `ModernizationAIAssistant.tsx` | `renderMessageContent()`에 마크다운 테이블 파싱 추가 |
| 9 | `ModernizationAIAssistant.tsx` | Artifact 뷰 컴포넌트 추가 (오버레이/패널) |
| 10 | `ModernizationAIAssistant.tsx` | 문자 수 초과 시 "전체 보기" 버튼 + Artifact 연동 |
| 11 | `ModernizationAIAssistant.css` | Artifact 뷰 스타일링 (테이블, 패널, 오버레이) |
| 12 | `i18n/locales/{en,ko,ja}/legacy.json` | Artifact 관련 번역 키 추가 |

## Key Files

| File | Role |
|------|------|
| `app/api/services/structured_knowledge_store.py` | 핵심 수정 - vLLM semantic search + top 3 제한 |
| `app/api/services/agentic_rag_service.py` | LLM 컨텍스트 빌딩 조정 + 테이블 포맷 유도 |
| `app/api/services/learning_llm_service.py` | system prompt 테이블 형식 지시 (옵션) |
| `kms-portal-ui/src/components/ModernizationAI/ModernizationAIAssistant.tsx` | Artifact 뷰 + 테이블 렌더링 |
| `kms-portal-ui/src/components/ModernizationAI/ModernizationAIAssistant.css` | Artifact 스타일링 |
| `kms-portal-ui/src/i18n/locales/*/legacy.json` | 번역 (en, ko, ja) |

## Configuration

| Config | Value | Description |
|--------|-------|-------------|
| `EMBEDDING_URL` | `http://192.168.8.11:12801/v1` | NV-EmbedQA 임베딩 서비스 URL |
| `HYBRID_ALPHA` | `0.6` | 키워드 점수 가중치 (1-α = semantic 가중치) |
| `EMBED_TIMEOUT` | `3.0` | 임베딩 API 타임아웃 (초) |
| `EMBED_TOP_N` | `20` | 시맨틱 검색 대상 키워드 후보 수 |
| `SEARCH_TOP_K` | `3` | 최종 반환 결과 수 |
| `ARTIFACT_THRESHOLD` | `500` | Artifact 뷰 전환 문자 수 임계값 |

## Risk & Mitigation

| Risk | Impact | Mitigation |
|------|--------|------------|
| 임베딩 서비스 다운 | 시맨틱 검색 불가 | try/except fallback → 키워드 점수만 사용 |
| 임베딩 지연 | 검색 속도 저하 | 상위 20개 후보만 임베딩 + 3초 타임아웃 |
| 테이블 렌더링 오류 | UI 깨짐 | regex 파싱 + fallback to plain text |
| LLM이 테이블 형식 미준수 | 출력 형식 불일치 | system prompt 강화 + 후처리 포맷터 |

## Success Criteria

- [ ] `StructuredKnowledgeStore.search()` 호출 시 vLLM 시맨틱 유사도 반영된 결과 반환
- [ ] 최종 결과가 최대 3개로 제한
- [ ] 임베딩 서비스 다운 시 기존 키워드 검색으로 graceful fallback
- [ ] Modernization AI에서 500문자 초과 응답 시 Artifact 뷰로 전환
- [ ] Artifact 뷰에서 마크다운 테이블이 올바르게 렌더링
- [ ] 3개 언어(en, ko, ja) 번역 완료
