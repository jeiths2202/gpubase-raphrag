# CJK Keyword Extraction Improvement Plan

## Feature: cjk-keyword-extraction
## Version: v1.0
## Created: 2026-01-31
## Status: Draft

---

## 1. Problem Statement

### 1.1 Current Issue

Summary BM25 검색에서 **일본어/한국어 키워드가 추출되지 않아** OSI 문서가 검색되지 않는 문제 발견.

**증상:**
- 사용자 쿼리: "OSIシステムを起動する方法" (OSI 시스템 기동 방법)
- 예상 결과: OSI Administrator Guide
- 실제 결과: XSP/MSP Utility Reference Guide

**근본 원인:**
```
OSI Administrator Guide의 키워드:
['AABBCC123', 'ALPHA', 'APPLCTN', 'BOOTING', 'CACHE'...]  ← 영문만!

필요한 키워드:
['起動', '終了', 'ログ', 'システム', 'OSI', '運用'...]  ← 일본어 누락
```

### 1.2 Impact Assessment

| 영향 범위 | 심각도 | 설명 |
|-----------|--------|------|
| STRUCTURES 검색 | Critical | 일본어 쿼리로 문서 검색 불가 |
| Summary BM25 | Critical | CJK 토큰화 누락으로 매칭 실패 |
| 사용자 경험 | High | 관련 없는 문서 반환으로 혼란 |
| Hallucination 위험 | High | 잘못된 문서로 답변 생성 가능 |

### 1.3 Affected Components

```
uploads/summaries/structures/index.json  ← 키워드 저장소
app/api/services/summary_bm25_service.py  ← BM25 검색 서비스
scripts/manual_processor/                 ← PDF 처리 및 키워드 추출
```

---

## 2. Goals & Objectives

### 2.1 Primary Goals

| # | Goal | Success Criteria |
|---|------|------------------|
| G1 | CJK 키워드 추출 | 일본어/한국어 키워드가 index.json에 포함 |
| G2 | BM25 CJK 토크나이저 | 일본어/한국어 쿼리 정확 토큰화 |
| G3 | OSI 검색 정확도 | "OSI起動" 쿼리로 OSI 문서 상위 반환 |

### 2.2 Non-Goals (Out of Scope)

- 중국어(간체/번체) 지원 (현재 일본어/한국어만 타겟)
- Vector Search 개선 (이미 작동 중)
- 새 문서 인덱싱 파이프라인 재구축

---

## 3. Proposed Solution

### 3.1 Solution Overview

```
[Phase 1: 키워드 추출 개선]
    │
    ├── CJK 토크나이저 추가 (fugashi/MeCab for Japanese)
    ├── 일본어 명사/동사 추출 로직
    └── index.json 재생성

[Phase 2: BM25 토크나이저 개선]
    │
    ├── summary_bm25_service.py 토큰화 개선
    ├── 쿼리 토큰화에 CJK 지원 추가
    └── 테스트 케이스 추가

[Phase 3: 검증 및 배포]
    │
    ├── OSI 검색 E2E 테스트
    ├── 성능 벤치마크
    └── 인덱스 재생성 스크립트
```

### 3.2 Technical Approach

#### Phase 1: CJK 키워드 추출

**현재 코드 (추정):**
```python
# 영문 대문자만 추출
keywords = re.findall(r'\b[A-Z][A-Z0-9]+\b', content)
```

**개선 코드:**
```python
import fugashi  # or MeCab wrapper

def extract_cjk_keywords(content: str) -> List[str]:
    keywords = []

    # 1. 기존 영문 키워드
    keywords.extend(re.findall(r'\b[A-Z][A-Z0-9]+\b', content))

    # 2. 일본어 명사 추출 (fugashi/MeCab)
    tagger = fugashi.Tagger()
    for word in tagger(content):
        if word.feature.pos1 in ['名詞', '動詞']:  # 명사, 동사
            if len(word.surface) >= 2:  # 최소 2자
                keywords.append(word.surface)

    # 3. 한국어 명사 추출 (konlpy 또는 regex)
    # 한글 연속 문자열 추출
    korean_words = re.findall(r'[가-힣]{2,}', content)
    keywords.extend(korean_words)

    return list(set(keywords))
```

#### Phase 2: BM25 토크나이저 개선

**현재 토큰화 (추정):**
```python
tokens = query.lower().split()  # 공백 기준 분리
```

**개선 토큰화:**
```python
def tokenize_cjk(text: str) -> List[str]:
    tokens = []

    # 영문: 공백 분리
    english_tokens = re.findall(r'\b[a-zA-Z]+\b', text)
    tokens.extend([t.lower() for t in english_tokens])

    # 일본어: 형태소 분석
    tagger = fugashi.Tagger()
    for word in tagger(text):
        if word.feature.pos1 in ['名詞', '動詞', '形容詞']:
            tokens.append(word.surface)

    # 한국어: 2자 이상 연속 한글
    korean_tokens = re.findall(r'[가-힣]{2,}', text)
    tokens.extend(korean_tokens)

    return tokens
```

---

## 4. Implementation Plan

### 4.1 Phase Breakdown

| Phase | Task | Priority | Effort |
|-------|------|----------|--------|
| 1.1 | fugashi/MeCab 의존성 추가 | High | 2h |
| 1.2 | 키워드 추출 함수 구현 | High | 4h |
| 1.3 | index.json 재생성 스크립트 | High | 2h |
| 2.1 | BM25 토크나이저 개선 | High | 3h |
| 2.2 | 기존 테스트 호환성 확인 | Medium | 2h |
| 3.1 | OSI 검색 E2E 테스트 | High | 2h |
| 3.2 | 성능 벤치마크 | Low | 1h |

### 4.2 Files to Modify

| File | Change |
|------|--------|
| `requirements-api.txt` | fugashi 의존성 추가 |
| `scripts/manual_processor/extractors/keyword_extractor.py` | CJK 키워드 추출 |
| `app/api/services/summary_bm25_service.py` | CJK 토크나이저 |
| `uploads/summaries/structures/index.json` | 재생성 (output) |
| `e2e/e2e_sentence_test.js` | OSI 검색 테스트 추가 |

### 4.3 New Files

| File | Purpose |
|------|---------|
| `app/api/services/cjk_tokenizer.py` | CJK 토크나이저 서비스 |
| `scripts/rebuild_structure_index.py` | 인덱스 재생성 스크립트 |

---

## 5. Dependencies

### 5.1 External Libraries

| Library | Purpose | Installation |
|---------|---------|--------------|
| fugashi | 일본어 형태소 분석 | `pip install fugashi[unidic-lite]` |
| unidic-lite | 일본어 사전 | fugashi와 함께 설치 |
| konlpy (optional) | 한국어 형태소 분석 | `pip install konlpy` |

### 5.2 Internal Dependencies

- `summary_bm25_service.py` - 기존 BM25 서비스
- `manual_processor/` - PDF 처리 스크립트
- `scoring_config_service.py` - 스코어링 설정

---

## 6. Risks & Mitigations

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|------------|
| fugashi 설치 실패 (C++ 의존성) | Medium | High | Docker에서 사전 빌드된 wheel 사용 |
| 인덱스 재생성 시간 | Low | Medium | 병렬 처리 적용 |
| 기존 검색 회귀 | Medium | High | 기존 테스트 케이스 유지 |
| 메모리 사용량 증가 | Low | Low | 토크나이저 캐싱 적용 |

---

## 7. Success Metrics

| Metric | Current | Target |
|--------|---------|--------|
| OSI 검색 정확도 | 0% (미검색) | 100% (상위 3위 이내) |
| CJK 키워드 추출률 | 0% | 90%+ |
| BM25 검색 응답 시간 | <50ms | <100ms (증가 허용) |
| E2E 테스트 통과율 | - | 100% |

---

## 8. Testing Strategy

### 8.1 Unit Tests

```python
def test_extract_japanese_keywords():
    content = "OSIシステムを起動する方法"
    keywords = extract_cjk_keywords(content)
    assert "起動" in keywords
    assert "システム" in keywords
    assert "OSI" in keywords

def test_tokenize_japanese_query():
    query = "OSIシステムの起動方法"
    tokens = tokenize_cjk(query)
    assert "osi" in tokens or "OSI" in tokens
    assert "起動" in tokens
    assert "方法" in tokens
```

### 8.2 E2E Tests

```javascript
// e2e/e2e_sentence_test.js에 추가
const CJK_KEYWORD_TESTS = [
    {
        query: "OSIシステムを起動する方法",
        expected: ["OSI", "Administrator-Guide"],
        notExpected: ["XSP", "MSP"]
    },
    {
        query: "ログファイルの管理方法",
        expected: ["ログ", "管理"],
        notExpected: []
    }
];
```

---

## 9. Rollback Plan

1. `requirements-api.txt`에서 fugashi 제거
2. `summary_bm25_service.py` 이전 버전 복원
3. `index.json` 백업본 복원
4. Docker 이미지 재빌드

---

## 10. Timeline

| Day | Milestone |
|-----|-----------|
| Day 1 | Phase 1 완료 (키워드 추출 개선) |
| Day 2 | Phase 2 완료 (BM25 토크나이저) |
| Day 3 | Phase 3 완료 (검증 및 배포) |

---

## Appendix A: Related Issues

- 스크린샷 분석에서 발견된 OSI 검색 실패
- STRUCTURES 카테고리에서 XSP/MSP 반환 문제
- Vector Search는 정상 작동 (OSI 0.77 score)

## Appendix B: Reference Documents

- `docs/archive/2026-01/cjk-tokenization-improvement/` - 이전 CJK 토큰화 개선 작업
- `app/api/services/summary_bm25_service.py` - 현재 BM25 구현
- `uploads/summaries/structures/index.json` - 키워드 인덱스
