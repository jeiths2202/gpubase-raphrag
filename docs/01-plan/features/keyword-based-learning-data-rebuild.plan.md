# Plan: 키워드 기반 학습 데이터 완전 재구성

> 작성일: 2026-02-03
> 상태: Draft
> 우선순위: Critical

## 1. 문제 정의

### 1.1 현재 문제점

| 문제 | 상세 | 영향 |
|------|------|------|
| **요약본 불완전** | syntax: null, parameters: [] | Learning LLM 할루시네이션 |
| **학습 데이터 부족** | 17,431개 중 command 94개만 | tjesmgr 등 핵심 명령어 정보 부재 |
| **JES2 할루시네이션** | TJES를 JES2로 오인 | 잘못된 응답 생성 |

### 1.2 근본 원인

```
기존 파이프라인:
PDF → 요약본 추출 (불완전) → 학습 데이터 → QLoRA 학습
         ↓
    syntax=null, parameters=[]
         ↓
    Learning LLM이 자체 추론 → 할루시네이션
```

### 1.3 해결 목표

- **43,147개 키워드** 전수 검색하여 완전한 학습 데이터 생성
- 모든 명령어에 syntax, parameters 포함
- 제품별 정확한 분류 및 출처 명시

---

## 2. 키워드 분석

### 2.1 키워드 통계 (docs/keyword.txt)

| 카테고리 | 개수 | 설명 | 예시 |
|----------|------|------|------|
| uppercase | 23,996 | 대문자 키워드 | TJES, VSAM, BOOT |
| function | 14,417 | 함수/API | DSALC_*, tpcall |
| command | 6,783 | 명령어 | tjesmgr, oscmgr |
| mixed_case | 5,666 | 혼합 케이스 | OpenFrame, TmaxSoft |
| acronym | 5,542 | 약어 | JCL, MVS, MSP |
| error_code | 2,191 | 에러 코드 | ABEND S0C7 |
| option | 933 | 옵션/플래그 | --enable-debug |
| file | 860 | 파일명 | osc.conf |
| env_var | 344 | 환경변수 | $OPENFRAME_HOME |
| jcl | 15 | JCL 키워드 | JOB, EXEC, DD |

### 2.2 우선순위 키워드 (Critical)

```
# Manager 명령어 (31개) - 최우선
tjesmgr, oscmgr, tacfmgr, hidbmgr, ndbmgr, volmgr, tconmgr,
smfmgr, cpmmgr, obmtsmgr, aimdtsmgr, hidbptrmgr, tbrmgr...

# 주요 명령어 (상위 100개)
idcams, iebgener, iebcopy, dfsort, dsmigin, dsmigout,
textrun, tjclrun, ofboot, ofdown, tmboot, tmdown...

# 설정 파일 (상위 50개)
osc.conf, tjes.conf, tacf.conf, ds.conf, ofsys.conf...

# 에러 코드 (2,191개)
ABEND S0C7, ABEND S0C4, ABEND S806, -5212, -5000...
```

---

## 3. 새로운 파이프라인 설계

### 3.1 아키텍처

```
┌─────────────────────────────────────────────────────────────┐
│                    Keyword-Based Pipeline                    │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  1. 키워드 로드                                              │
│     docs/keyword.txt (43,147개)                             │
│              ↓                                               │
│  2. 키워드별 PDF 검색                                        │
│     uploads/manuals/**/*.pdf (245개)                        │
│     - 키워드 포함 페이지 추출                                │
│     - 주변 컨텍스트 (±5줄) 함께 추출                         │
│              ↓                                               │
│  3. 구조화된 정보 추출                                       │
│     - name: 키워드명                                         │
│     - description: 설명 (전후 문맥에서)                      │
│     - syntax: 구문 (코드 블록 또는 $ 시작 줄)                │
│     - parameters: 파라미터 (<>, [], KEY=)                    │
│     - examples: 예시 코드                                    │
│     - source: PDF명 + 페이지                                 │
│     - product: 제품명 (파일명에서)                           │
│              ↓                                               │
│  4. 중복 제거 및 병합                                        │
│     - 동일 키워드의 여러 소스 병합                           │
│     - 가장 완전한 정보 선택                                  │
│              ↓                                               │
│  5. QLoRA 형식 변환                                          │
│     - ChatML 형식                                            │
│     - 다국어 질문 템플릿 (ja, ko, en)                        │
│              ↓                                               │
│  6. 학습 실행                                                │
│     - GPU 서버 전송                                          │
│     - QLoRA 파인튜닝                                         │
│     - 어댑터 배포                                            │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

### 3.2 핵심 개선사항

| 기존 방식 | 새 방식 | 개선점 |
|-----------|---------|--------|
| 요약본 재활용 | 키워드별 직접 검색 | 누락 없음 |
| syntax=null 허용 | syntax 필수 추출 | 완전한 정보 |
| 단일 출처 | 다중 출처 병합 | 정확도 향상 |
| 제품 미분류 | 파일명 기반 분류 | 정확한 제품 매핑 |

---

## 4. 구현 계획

### 4.1 Phase 1: 키워드 검색 엔진 구현

**파일**: `scripts/training/keyword_pdf_searcher.py`

```python
# 핵심 기능
class KeywordPDFSearcher:
    def search_keyword(self, keyword: str) -> List[SearchResult]:
        """키워드를 모든 PDF에서 검색"""
        pass

    def extract_context(self, page, keyword, context_lines=5) -> str:
        """키워드 주변 컨텍스트 추출"""
        pass

    def extract_syntax(self, context: str) -> Optional[str]:
        """구문 정보 추출"""
        # $ 시작 줄, ``` 블록, 구문: 다음 줄
        pass

    def extract_parameters(self, syntax: str) -> List[str]:
        """파라미터 추출"""
        # <param>, [option], KEY=value
        pass
```

**예상 출력**:
```json
{
  "keyword": "tjesmgr",
  "occurrences": [
    {
      "pdf": "OF_Batch_MVS_7.1_TJES-Guide_v3.1.3_jp.pdf",
      "page": 21,
      "context": "tjesmgrのBOOTコマンドは...",
      "syntax": "tjesmgr BOOT [nodename]",
      "parameters": ["nodename"]
    },
    {
      "pdf": "OF_Batch_MVS_7.1_TJES-Guide_v3.1.3_jp.pdf",
      "page": 91,
      "context": "tjesmgr CANCELは...",
      "syntax": "tjesmgr CANCEL {<job-ID>|N=<job-name>}",
      "parameters": ["job-ID", "job-name"]
    }
  ]
}
```

### 4.2 Phase 2: 학습 데이터 생성기

**파일**: `scripts/training/keyword_learning_generator.py`

```python
class KeywordLearningGenerator:
    def generate_item(self, keyword: str, occurrences: List) -> LearningItem:
        """검색 결과를 학습 항목으로 변환"""
        # 가장 완전한 정보 선택
        # syntax, parameters 필수 포함
        pass

    def merge_occurrences(self, occurrences: List) -> Dict:
        """여러 출처의 정보 병합"""
        # 가장 긴 description 선택
        # 모든 syntax 수집
        # parameters 합집합
        pass

    def detect_type(self, keyword: str, context: str) -> str:
        """항목 타입 결정"""
        # command, config, api, error, concept
        pass
```

### 4.3 Phase 3: QLoRA 변환 및 학습

**기존 스크립트 활용**:
- `scripts/training/convert_to_qlora.py` - 형식 변환
- `scripts/training/qlora_trainer.py` - 학습 실행

---

## 5. 품질 보증

### 5.1 검증 체크리스트

- [ ] 43,147개 키워드 전수 검색 완료
- [ ] Manager 명령어 31개 모두 syntax 포함
- [ ] 에러 코드 2,191개 모두 설명 포함
- [ ] 설정 파일 860개 모두 파라미터 포함
- [ ] 중복 제거 후 유효 항목 수 확인

### 5.2 검증 테스트

```bash
# 1. tjesmgr 검증
grep -A5 '"name": "tjesmgr"' learning_dataset.json
# syntax가 null이 아닌지 확인

# 2. 주요 명령어 검증
for cmd in tjesmgr oscmgr tacfmgr hidbmgr; do
  echo "=== $cmd ==="
  grep -c "\"$cmd\"" learning_dataset.json
done

# 3. E2E 테스트
cd e2e && node e2e_sentence_test.js
# Hallucination 0개 목표
```

### 5.3 품질 기준

| 항목 | 기준 | 측정 방법 |
|------|------|----------|
| 키워드 커버리지 | ≥ 95% | 검색된 키워드 / 전체 키워드 |
| syntax 완성도 | ≥ 90% | syntax 있는 항목 / command 타입 항목 |
| 할루시네이션 | 0개 | E2E 테스트 결과 |
| 학습 손실 | < 0.5 | QLoRA 학습 로그 |

---

## 6. 일정 및 리소스

### 6.1 예상 일정

| Phase | 작업 | 예상 시간 |
|-------|------|----------|
| 1 | 키워드 검색 엔진 구현 | 1시간 |
| 2 | 43,147개 키워드 검색 (245 PDF) | 2-3시간 |
| 3 | 학습 데이터 생성 | 30분 |
| 4 | QLoRA 변환 | 10분 |
| 5 | QLoRA 학습 (GPU 서버) | 2-4시간 |
| 6 | 검증 및 배포 | 1시간 |
| **Total** | | **7-10시간** |

### 6.2 리소스 요구사항

| 리소스 | 요구량 | 용도 |
|--------|--------|------|
| 로컬 메모리 | 8GB+ | PDF 파싱 |
| 디스크 | 5GB+ | 중간 결과 저장 |
| GPU (원격) | A100 40GB | QLoRA 학습 |

---

## 7. 위험 요소 및 대응

| 위험 | 영향 | 대응 방안 |
|------|------|----------|
| PDF 파싱 실패 | 일부 키워드 누락 | 실패 로그 기록, 수동 처리 |
| 메모리 부족 | 프로세스 중단 | 배치 처리 (1000개씩) |
| 잘못된 syntax 추출 | 학습 품질 저하 | 정규식 패턴 검증 |
| 학습 시간 초과 | 일정 지연 | GPU 증설 또는 배치 분할 |

---

## 8. 승인 요청

### 8.1 구현 시작 전 확인 사항

1. **키워드 파일 확인**: `docs/keyword.txt` 43,147개
2. **PDF 파일 확인**: `uploads/manuals/**/*.pdf` 245개
3. **GPU 서버 접근**: 192.168.8.11 학습 환경 준비

### 8.2 예상 결과물

| 파일 | 설명 |
|------|------|
| `keyword_search_results.json` | 키워드별 검색 결과 |
| `keyword_learning_dataset.json` | 새 학습 데이터 |
| `keyword_qlora_train.jsonl` | QLoRA 학습 데이터 |
| `qlora_keyword_v1/` | 학습된 어댑터 |

---

## Appendix: 주요 키워드 목록

### A. Manager 명령어 (31개)

```
aimdtsmgr, cpmmgr, GTJESMGR, h_mgr, hidbmgr, hidbptrmgr,
HIDBPTRMGR, lmgr, mgr, MGR, ndbmgr, NMGR, obmtsmgr,
OFRUISVRVOLMGR, oscmgr, OSCMGR, OSIMPPSVRMGR, prs_mgr,
QMGR, rmgr, RMGR, RQMGR, SECURITYMGR, sle_mgr, smfmgr,
tacfmgr, TACFMGR, tbrmgr, tconmgr, TCONMGR, tjesmgr,
TJESMGR, tmgr, TSOMGR, TXRQMGR, volmgr
```

### B. 핵심 JCL 명령어

```
JOB, EXEC, DD, PROC, PEND, IF, THEN, ELSE, ENDIF,
SET, INCLUDE, JCLLIB, OUTPUT, CNTL, ENDCNTL
```

### C. 주요 에러 코드 패턴

```
ABEND S0C7, ABEND S0C4, ABEND S806, ABEND S013
-5000 ~ -5999 (DSALC 모듈)
-9000 ~ -9999 (TJES 모듈)
-18000 ~ -18999 (TACF 모듈)
```
