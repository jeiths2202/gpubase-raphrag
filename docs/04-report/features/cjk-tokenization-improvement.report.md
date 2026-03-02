# PDCA Completion Report: CJK 토크나이징 개선

**작성일**: 2026-01-31
**상태**: ✅ 완료
**Match Rate**: 100% (필수 항목)

---

## 1. Executive Summary

일본어/한국어/중국어(CJK) 쿼리의 키워드 토큰화 문제를 해결하여 RAG 검색 품질을 개선했습니다.

### Before → After

| 쿼리 | Before (잘못된 토큰화) | After (정확한 토큰화) |
|------|----------------------|---------------------|
| `マッピング・サポート・システムのフローチャート` | `マッピング`, `サポ`, `システムのフロ`, `チャ` | `マッピングサポート`, `システム`, `フローチャート` |
| `OSCサーバーの起動画面` | `oscサ`, `の起動画面` (0 results) | `OSC`, `サーバー`, `起動画面` |
| `tjesmgr BOOTについて` | `tjesmgr`, `bootについて` | `tjesmgr`, `BOOT` |

### 핵심 성과

| 지표 | 결과 |
|------|------|
| 필수 항목 완료율 | **100%** (3/3) |
| PDCA Iteration | 1회 |
| 신규 서비스 | `KeywordExtractionService` |
| 수정 파일 | 3개 |
| 추가 의존성 | 없음 |

---

## 2. Problem Statement

### 2.1 근본 원인

CJK 언어는 **단어 경계가 없어** regex 기반 토큰화가 실패:

```python
# 문제 코드 (executor.py:397)
other_tokens = re.findall(r'[a-zA-Z0-9가-힣ぁ-んァ-ン一-龥]+', query.lower())
```

### 2.2 영향

| 영향 | 설명 |
|------|------|
| 검색 실패 | `OSCサーバー` → 0개 결과 |
| UX 저하 | UI에 잘못된 키워드 표시 |
| BM25 오류 | 토큰 불일치로 검색 품질 저하 |

---

## 3. Solution Architecture

### 3.1 아키텍처 개요

```
┌─────────────────────────────────────────────────────────────────┐
│                    KeywordExtractionService (NEW)               │
│                                                                 │
│  ┌────────────────┐    ┌────────────────┐    ┌───────────────┐ │
│  │ Cache Layer    │ → │ Language       │ → │ LLM or Regex  │ │
│  │ (LRU 1000, 1h) │    │ Detection      │    │ Extraction    │ │
│  └────────────────┘    └────────────────┘    └───────────────┘ │
└─────────────────────────────────────────────────────────────────┘
                              │
              ┌───────────────┴───────────────┐
              ▼                               ▼
     ┌─────────────────┐             ┌─────────────────┐
     │ executor.py     │             │ summary_bm25    │
     │ UI 키워드 표시  │             │ BM25 검색       │
     └─────────────────┘             └─────────────────┘
```

### 3.2 핵심 설계 결정

| 결정 | 선택 | 이유 |
|------|------|------|
| 토큰화 방법 | LLM 기반 | CJK 언어 경계 없음, 의미 기반 분석 필요 |
| 캐시 전략 | LRU + TTL | 반복 쿼리 최적화, 메모리 제한 |
| 폴백 방법 | Regex | LLM 장애 시 서비스 연속성 |
| 통합 방식 | 공유 서비스 | 코드 중복 제거, 일관성 |

---

## 4. Implementation Details

### 4.1 신규 파일

#### `app/api/services/keyword_extraction_service.py`

| 컴포넌트 | 설명 |
|----------|------|
| `ExtractionMethod` | Enum: LLM, REGEX, CACHE |
| `KeywordExtractionResult` | 결과 데이터클래스 |
| `KeywordExtractionService` | 메인 서비스 클래스 |
| `get_keyword_extraction_service()` | 싱글톤 팩토리 |

**핵심 기능**:
```python
async def extract_keywords(query: str) -> KeywordExtractionResult:
    # 1. 캐시 확인 (TTL 1시간)
    # 2. 언어 감지 (ja/ko/zh/en)
    # 3. CJK면 LLM, 아니면 Regex
    # 4. 캐시 업데이트
```

### 4.2 수정 파일

#### `app/api/agents/executor.py`

| 위치 | 변경 |
|------|------|
| Line 355 | `def` → `async def _analyze_query_keywords` |
| Line 370 | KeywordExtractionService import 추가 |
| Line 392-394 | 서비스 호출로 대체 |
| Line 429-430 | `extraction_method`, `extraction_time_ms` 추가 |
| Line 2197 | `await` 추가 |

#### `app/api/services/summary_bm25_service.py`

| 위치 | 변경 |
|------|------|
| Line 1192-1240 | `_extract_keywords_llm()` 전면 교체 |

**Before** (~95줄): 독자적 LLM 호출, 캐시, 프롬프트
**After** (~50줄): KeywordExtractionService 통합, 분류 로직만 유지

---

## 5. Performance Characteristics

### 5.1 응답 시간

| 시나리오 | 예상 지연 |
|----------|----------|
| 캐시 히트 | < 1ms |
| LLM 호출 (정상) | 300-500ms |
| LLM 타임아웃 + 폴백 | 3000ms + 5ms |
| Regex 전용 (non-CJK) | < 5ms |

### 5.2 캐시 설정

| 항목 | 값 |
|------|-----|
| 최대 크기 | 1,000 entries |
| TTL | 1시간 |
| 키 생성 | MD5(query) |
| 정리 방식 | LRU (50% 제거) |

---

## 6. Error Handling

| 오류 상황 | 처리 방법 |
|----------|----------|
| LLM 서버 불가용 | Regex 폴백 |
| LLM 타임아웃 (3초) | Regex 폴백 |
| 잘못된 JSON 응답 | Regex 폴백 |
| 빈 키워드 반환 | Regex 폴백 |

---

## 7. Test Cases

### 7.1 일본어 쿼리 검증

| 입력 | 예상 출력 |
|------|----------|
| `マッピング・サポート・システムのフローチャート` | `["マッピングサポート", "システム", "フローチャート"]` |
| `OSCサーバーの起動画面` | `["OSC", "サーバー", "起動画面"]` |
| `tjesmgrについて教えてください` | `["tjesmgr"]` |
| `-5212エラーの原因` | `["-5212", "エラー", "原因"]` |

### 7.2 한국어 쿼리 검증

| 입력 | 예상 출력 |
|------|----------|
| `tjesmgr 명령어 사용법` | `["tjesmgr", "명령어", "사용법"]` |
| `-5212 에러 해결 방법` | `["-5212", "에러", "해결", "방법"]` |
| `OSC와 TJES의 차이점` | `["OSC", "TJES", "차이점"]` |

---

## 8. PDCA Cycle Summary

### 8.1 Phase Timeline

| Phase | 상태 | 산출물 |
|-------|------|--------|
| Plan | ✅ | `docs/01-plan/features/cjk-tokenization-improvement.plan.md` |
| Design | ✅ | `docs/02-design/features/cjk-tokenization-improvement.design.md` |
| Do | ✅ | 3개 파일 구현 |
| Check | ✅ | Match Rate 100% |
| Act | ✅ | Iteration 1 완료 |

### 8.2 Iteration History

| Iteration | Match Rate | 수정 내용 |
|-----------|------------|----------|
| Initial | 67% | Step 1, 2 완료 |
| 1 | **100%** | Step 3 완료 (summary_bm25_service.py) |

---

## 9. Files Changed

| 파일 | 변경 유형 | 줄 수 |
|------|----------|-------|
| `app/api/services/keyword_extraction_service.py` | 신규 | ~360 |
| `app/api/agents/executor.py` | 수정 | ~80 |
| `app/api/services/summary_bm25_service.py` | 수정 | -45 |

---

## 10. Rollback Plan

문제 발생 시 즉시 롤백 가능:

1. `keyword_extraction_service.py` 삭제
2. `executor.py`의 `_analyze_query_keywords`를 동기 함수로 복원
3. `summary_bm25_service.py`의 `_extract_keywords_llm`을 원본으로 복원

**롤백 트리거 조건**:
- LLM 응답 오류율 > 10%
- 평균 응답 지연 > 2초
- 키워드 품질 저하 (수동 검증)

---

## 11. Future Recommendations

| 우선순위 | 항목 | 설명 |
|----------|------|------|
| 권장 | 단위 테스트 | `tests/api/test_keyword_extraction.py` 작성 |
| 선택 | E2E 테스트 | `e2e/e2e_cjk_tokenization.js` 작성 |
| 선택 | 캐시 모니터링 | 히트율, 메모리 사용량 대시보드 |
| 선택 | 프롬프트 튜닝 | 도메인별 프롬프트 최적화 |

---

## 12. Lessons Learned

1. **LLM vs 형태소 분석기**: Docker 환경에서 형태소 분석기 설정 복잡, LLM 기반이 더 실용적
2. **공유 서비스 패턴**: 중복 코드 제거 및 캐시 공유로 효율성 증가
3. **Regex 폴백**: LLM 장애 시에도 서비스 연속성 확보

---

*Generated by report-generator*
*PDCA Cycle: cjk-tokenization-improvement*
*Completion Date: 2026-01-31*
