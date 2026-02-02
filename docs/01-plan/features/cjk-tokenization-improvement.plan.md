# PDCA Plan: CJK 토크나이징 개선

## 1. 문제 분석

### 1.1 현재 상황 (스크린샷 기반)

**snapshot.png**:
- 쿼리: "マッピング・サポート・システムのフローチャート"
- 결과: 2개 검색결과
- **잘못된 키워드**: "マッピング", "サポ", "システムのフロ", "チャ"
- **원인**: `・`(중점)이 분리자로 작동하지 않고, `の`가 다음 단어와 결합됨

**snapshot2.png**:
- 쿼리: "OSCサーバーの起動画面"
- 결과: 0개 검색결과 (심각한 검색 실패)
- **잘못된 키워드**: "oscサ", "の起動画面"
- **원인**: 영문 "OSC"와 일본어 "サーバー"가 잘못 분리됨

### 1.2 문제의 근본 원인

| 언어 | 특성 | 현재 처리 방식 | 문제점 |
|------|------|---------------|--------|
| 영어 | 공백으로 단어 분리 | ✅ 정상 | - |
| 한국어 | 공백으로 어절 분리 | ⚠️ 부분 작동 | 조사 분리 필요 |
| **일본어** | **단어 경계 없음** | ❌ **실패** | regex로 토큰화 불가능 |
| 중국어 | 단어 경계 없음 | ❌ 실패 | 동일 |

**코드 위치**: `app/api/agents/executor.py:397`
```python
# 현재 방식 (문제)
other_tokens = re.findall(r'[a-zA-Z0-9가-힣ぁ-んァ-ン一-龥]+', query.lower())
```

### 1.3 영향 범위

| 영향 | 설명 |
|------|------|
| 검색 품질 저하 | 잘못된 키워드로 인해 관련 없는 문서 검색 |
| 0 결과 발생 | "OSCサーバー" 같은 혼합 단어 검색 실패 |
| UX 저하 | 사용자에게 잘못된 키워드 표시 |
| BM25 검색 오류 | `summary_bm25_service.py`의 토크나이저도 동일 문제 |

---

## 2. 해결 방안 비교

### 방안 1: 형태소 분석기 (MeCab/Janome)
| 장점 | 단점 |
|------|------|
| 정확한 일본어 분석 | 외부 라이브러리 의존성 (MeCab 설치 복잡) |
| 오프라인 작동 | 한국어/영어/중국어 각각 다른 분석기 필요 |
| 빠른 처리 속도 | Docker 환경 설정 복잡 |

### 방안 2: LLM 기반 키워드 추출 (추천 ✅)
| 장점 | 단점 |
|------|------|
| 다국어 통합 처리 (일/한/중/영) | LLM 호출 지연 (~500ms) |
| 의미 기반 추출 (문맥 이해) | LLM 서버 의존성 |
| 설치 없음, 기존 인프라 활용 | 비용 (토큰 사용) |
| OpenFrame 도메인 지식 활용 가능 | - |

### 방안 3: 하이브리드 (LLM + 규칙)
| 장점 | 단점 |
|------|------|
| LLM 실패 시 폴백 | 구현 복잡도 증가 |
| 캐싱으로 속도 개선 | 유지보수 2배 |

**선택: 방안 2 (LLM 기반)**
- 이미 `summary_bm25_service.py`에 `_extract_keywords_llm()` 구현 존재
- 다국어 환경에서 가장 일관된 품질
- 추가 설치 없음

---

## 3. 구현 계획

### Phase 1: executor.py 키워드 추출 개선

**목표**: UI에 표시되는 "抽出されたキーワード"를 정확하게 추출

**수정 대상**: `app/api/agents/executor.py:355-432`

**구현 내용**:
1. `_analyze_query_keywords_llm()` 비동기 함수 추가
2. LLM 기반 키워드 추출 (기존 `_extract_keywords_llm` 재사용)
3. 캐시 레이어 추가 (동일 쿼리 재요청 방지)
4. 폴백: LLM 실패 시 기존 regex 방식 사용

**API 호출 형식**:
```python
prompt = """Extract the technical keywords from this query.
Query: {query}

Rules:
1. Keep compound words together (e.g., "マッピング・サポート" → one keyword)
2. Separate by Japanese particles like の、を、が、は
3. Keep alphanumeric terms (e.g., "OSC", "BMS", "-5212")
4. Return JSON: {"keywords": ["keyword1", "keyword2", ...]}

Output ONLY valid JSON:"""
```

### Phase 2: summary_bm25_service.py 토크나이저 개선

**목표**: BM25 검색의 토큰화 개선

**수정 대상**: `app/api/services/summary_bm25_service.py:199-236`

**구현 내용**:
1. `_tokenize()` 함수에 LLM 토큰화 옵션 추가
2. CJK 쿼리 감지 시 LLM 토큰화 사용
3. 캐시 적용 (query hash → tokens)

### Phase 3: 성능 최적화

**목표**: LLM 호출 지연 최소화

**구현 내용**:
1. 키워드 캐시 (TTL: 1시간)
2. 병렬 처리: 키워드 추출과 검색을 동시 시작
3. Timeout 설정: 3초 (초과 시 regex 폴백)

---

## 4. 예상 쿼리 처리 결과

### Before (현재)
| 쿼리 | 추출된 키워드 |
|------|--------------|
| マッピング・サポート・システムのフローチャート | マッピング, サポ, システムのフロ, チャ |
| OSCサーバーの起動画面 | oscサ, の起動画面 |
| tjesmgr BOOTについて | tjesmgr, bootについて |

### After (개선 후)
| 쿼리 | 추출된 키워드 |
|------|--------------|
| マッピング・サポート・システムのフローチャート | マッピングサポート, システム, フローチャート |
| OSCサーバーの起動画面 | OSC, サーバー, 起動画面 |
| tjesmgr BOOTについて | tjesmgr, BOOT |

---

## 5. 성공 기준

| 기준 | 측정 방법 |
|------|----------|
| 키워드 정확도 | "OSCサーバー" → ["OSC", "サーバー"] 분리 성공 |
| 검색 결과 | "OSCサーバーの起動画面" 쿼리 시 0개 → 2개 이상 |
| 응답 지연 | 키워드 추출 < 500ms (캐시 미스 시) |
| 캐시 히트율 | 반복 쿼리 시 < 10ms |

---

## 6. 리스크 및 대응

| 리스크 | 영향 | 대응 |
|--------|------|------|
| LLM 서버 불가용 | 키워드 추출 실패 | regex 폴백 (기존 방식) |
| LLM 응답 지연 | UX 저하 | 3초 타임아웃 + 캐시 |
| 잘못된 LLM 응답 | 키워드 품질 저하 | JSON 파싱 검증 + 폴백 |
| 메모리 사용량 | 캐시 증가 | LRU 캐시 (최대 1000개) |

---

## 7. 파일 수정 목록

| 파일 | 변경 내용 | 복잡도 |
|------|----------|--------|
| `app/api/agents/executor.py` | `_analyze_query_keywords_llm()` 추가 | 중 |
| `app/api/services/summary_bm25_service.py` | `_tokenize()` LLM 옵션 추가 | 중 |
| (선택) `app/api/services/keyword_extraction_service.py` | 공통 키워드 추출 서비스 | 저 |

---

## 8. 다음 단계

1. `/pdca design cjk-tokenization-improvement` - 상세 설계 문서 작성
2. Phase 1 구현 (executor.py)
3. Phase 2 구현 (summary_bm25_service.py)
4. Phase 3 구현 (캐싱/최적화)
5. `/pdca analyze cjk-tokenization-improvement` - Gap 분석 및 검증
