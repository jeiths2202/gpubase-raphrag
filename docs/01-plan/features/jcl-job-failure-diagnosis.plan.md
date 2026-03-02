# Plan: JCL Job Failure Diagnosis Agent

> **Feature**: JCL Job Failure Diagnosis Agent - zip 파일 업로드로 JOB 실패 원인 자동 진단
> **Created**: 2026-02-25
> **Status**: Draft
> **Priority**: Critical (Killer Feature)
> **Level**: Enterprise

---

## 1. 현재 상태 분석 (As-Is)

### 1.1 기존 시스템이 할 수 없는 것

| 문제 | 현재 상태 | 영향 |
|------|----------|------|
| JOB 실패 진단 | 수동으로 SPOOL 파일을 하나씩 확인 | 엔지니어 1건당 30분~2시간 소요 |
| 에러코드 해석 | 매뉴얼 PDF에서 직접 검색 | OpenFrame 19개 제품, 52개 에러 모듈 |
| JCL ↔ 에러 연관 분석 | 사람의 경험에 의존 | 신입 엔지니어 미대응, 지식 단절 |
| 유사 장애 검색 | 없음 | 반복 장애에도 매번 처음부터 분석 |

### 1.2 재사용 가능한 기존 자산

| 자산 | 파일 | 활용 방법 |
|------|------|----------|
| **JCL Parser** | `app/api/legacy_modernization/parsers/jcl_parser.py` | JOB/EXEC/DD 파싱, MVS+XSP 방언 지원 |
| **JCL Expert Agent** | `app/api/legacy_modernization/agents/domain/jcl_expert.py` | STEP 분석, 프로그램 식별, 조건 분석 |
| **에러코드 DB** | `uploads/summaries/error-codes/` (52파일, ~1,200개 에러) | BATCH-9000(TJES), BASE-5000~40000 |
| **Summary Search** | `app/api/services/summary_search_service.py` | 에러코드 패턴 매칭 (<10ms) |
| **BM25 Search** | `app/api/services/summary_bm25_service.py` | 에러 메시지 전문 검색 |
| **Neo4j Vector Index** | 기존 RAG 인프라 | 유사 장애 사례 검색 |
| **Graph Search** | Knowledge Graph 에러코드 Entity | 에러 → 원인 → 해결방법 관계 탐색 |
| **File Upload** | `app/api/routers/documents.py` `/extract-text` | 파일 업로드/텍스트 추출 |
| **SSE Streaming** | `app/api/routers/agentic_rag.py` | 실시간 진단 과정 스트리밍 |
| **Agentic RAG** | Agent Executor + Tool Calling 패턴 | 멀티 에이전트 오케스트레이션 |

### 1.3 OpenFrame SPOOL 구조 (매뉴얼 기반)

사용자가 업로드하는 zip 파일은 OpenFrame TJES의 SPOOL 출력물입니다.

```
JOB 실행 시 TJES가 자동 생성하는 표준 SPOOL 데이터셋:

┌─────────────┬──────────────────────────────────────────────────┐
│ INPJCL      │ 제출된 원본 JCL (입력 복사본)                      │
│ JESJCL      │ 전개된 JCL (PROC 인라인, 심볼 해결)                │
│ JESMSG      │ 실행 메시지 (STEP 상태, I/O 통계, RC)              │
│ SYSMSG      │ 시스템 레벨 메시지 (ABEND, 에러)                   │
│ SYSPRINT    │ 프로그램 출력 (컴파일 리스트, SORT 메시지)           │
│ SYSOUT(*)   │ 사용자 정의 DD SYSOUT 출력물                      │
└─────────────┴──────────────────────────────────────────────────┘

네이밍 규칙: <catalog>.<jobname>.<job-id>.<sequence>
예시: ROOT.SORT01.JOB00040.D000004
```

**JESMSG 핵심 정보** (에러 진단의 주 소스):
- JOB 정보: JOB명, CLASS, MSGCLASS
- STEP별 실행 결과: RC=0000 (정상), RC=0008 (에러), ABEND S0C7
- 데이터셋 I/O 통계: `SYSUT1: TEST.DATASET1 R:10 W:0`
- FD 처분 메시지: `(JRN2012I) SYSPRINT FD disposed - NORMAL ok`

**OUTPUTQ 상태**:
| 상태 | 의미 |
|------|------|
| U (Unable) | 초기 대기 |
| R (Ready) | 출력 준비 완료 |
| H (Hold) | 사용자 보류 |
| E (Error) | 출력 처리 에러 |

---

## 2. 목표 상태 (To-Be)

### 2.1 핵심 가치 제안

**"zip 파일 하나로 JOB 실패 원인 + 대처 방안을 30초 이내에 제공"**

- 다른 RAG 시스템: 질문을 입력해야 답을 얻음 (사용자가 이미 문제를 알고 있어야 함)
- **이 시스템**: 로그 파일을 업로드하면 에이전트가 자동으로 문제를 발견하고 해결방안을 제시

### 2.2 5-Agent 파이프라인

```
[사용자: JOB_ACCT001.zip 업로드]
    ↓
[① File Processor Agent]        ── zip 해제, 파일 분류 (JCL/PROC/SYSMSG/SPOOL)
    ↓
[② JCL Analyzer Agent]          ── JCL 파싱, STEP 흐름 요약, PROC 전개
    ↓
[③ Error Diagnosis Agent]       ── SYSMSG/JESMSG 에러 추출, 실패 STEP 특정
    ↓
[④ Knowledge Retrieval Agent]   ── Neo4j 에러 가이드 + Vector 유사 사례 검색
    ↓
[⑤ Report Generator Agent]     ── 종합 진단 리포트 생성 (JA/KO/EN)
    ↓
[SSE 스트리밍으로 실시간 진단 과정 표시]
```

### 2.3 대상 에러 유형

| 카테고리 | 패턴 | 예시 | 출처 |
|----------|------|------|------|
| ABEND 코드 | `S\d{3,4}` | S0C7, S0C4, S322, S806, S013 | SYSMSG/JESMSG |
| User ABEND | `U\d{4}` | U1234, U0100 | SYSMSG |
| OpenFrame 에러 | `OFR\d+[EWI]?` | OFR1234E | SYSMSG |
| TJES 에러 | `TJES\d+[EWI]?` | TJES5001E | JESMSG |
| OFCOBOL 에러 | `OFCOBOL-\d+` | OFCOBOL-1001 | SYSPRINT |
| COND CODE | `RC=\d{4}` | RC=0008, RC=0012 | JESMSG |
| JES 메시지 | `IEF\d{3}I` | IEF236I, IEF453I | JESMSG |
| SORT 메시지 | `ICE\d{3}[A-Z]` | ICE000I, ICE044A | SYSPRINT |
| VSAM 메시지 | `IGD\d{3}[A-Z]` | IGD017I, IGD100I | SYSMSG |
| 데이터셋 에러 | BATCH-9000~92000 범위 | -9001 ~ -92999 | 에러코드 DB |

### 2.4 사용자 경험 목표

```
사용자: [JOB_ACCT001_20260225.zip 업로드]
        "이 JOB이 실패했는데 원인 좀 봐주세요"

Agent:  분석 중입니다...

        📂 파일 해제 완료 (6개 파일)
        ├── ACCT001.jcl     (JCL)
        ├── ACCTPROC.proc   (PROC)
        ├── JESMSG.txt      (JES 메시지)
        ├── SYSMSG.txt      (시스템 메시지)
        ├── SYSPRINT.txt    (프로그램 출력)
        └── SYSUT2.dat      (데이터)

        📋 JOB 실행 요약
        ━━━━━━━━━━━━━━━━━
        JOB명: ACCT001  |  STEP: 4개  |  CLASS: A
        목적: 일별 회계 마감 배치 처리

        STEP1(EXTRACT) → STEP2(SORT) → STEP3(CALC) → STEP4(REPORT)
        ✅ RC=0000       ✅ RC=0000    ❌ S0C7         ⏭ SKIP

        ❌ 에러 원인 분석
        ━━━━━━━━━━━━━━━━━
        에러코드: S0C7 (Data Exception)
        실패 STEP: STEP3 (PGM=ACCTCALC)
        원인: COMPUTE 문에서 숫자 필드에 비숫자 데이터 입력

        SYSMSG:
        > IEA995I SYMPTOM DUMP OUTPUT - S0C7 IN STEP3

        🔧 대처 방안
        ━━━━━━━━━━━━
        1. STEP2 출력 데이터셋 검증 (DFSORT INCLUDE COND)
        2. ACCTCALC 프로그램의 MOVE/COMPUTE 변수 확인
        3. 입력 COPYBOOK과 실제 레코드 레이아웃 일치 확인

        📚 참고 문서
        ━━━━━━━━━━━━
        - OpenFrame S0C7 에러 가이드
        - ACCTCALC 프로그램 관련 문서 (2건)
        - 유사 장애 사례 3건
```

---

## 3. 기술 설계 개요

### 3.1 Agent 시스템 통합

기존 Agentic RAG 아키텍처를 확장하여 구현합니다.

```
기존:  AgenticRAGService → ProductAgent → [검색 + LLM 생성]
신규:  AgenticRAGService → JCLDiagnosisOrchestrator → [5개 Sub-Agent 파이프라인]
```

**진입점 결정**: `agent_mode` 파라미터 확장

| 모드 | 동작 |
|------|------|
| `rag` (기존) | 제품별 RAG 검색 + 응답 생성 |
| `jcl_diagnosis` (신규) | zip 업로드 → 5-Agent 진단 파이프라인 |

### 3.2 신규 파일 구조

```
app/api/
├── services/
│   └── jcl_diagnosis/                    # 신규 패키지
│       ├── __init__.py
│       ├── orchestrator.py               # 5-Agent 파이프라인 오케스트레이터
│       ├── file_processor.py             # ① zip 해제 + 파일 분류
│       ├── jcl_analyzer.py               # ② JCL 파싱 + STEP 분석
│       ├── error_diagnosis.py            # ③ 에러코드 추출 + 실패 STEP 특정
│       ├── knowledge_retriever.py        # ④ Neo4j + Vector 검색
│       └── report_generator.py           # ⑤ 리포트 생성
├── routers/
│   └── jcl_diagnosis.py                  # REST API 엔드포인트
└── models/
    └── jcl_diagnosis.py                  # Pydantic 스키마

kms-portal-ui/src/
├── pages/
│   └── AgenticRAGPage.tsx                # zip 업로드 UI 추가 (기존 확장)
├── api/
│   └── jcl-diagnosis.api.ts              # API 클라이언트
└── components/
    └── JCLDiagnosis/
        ├── JobFlowDiagram.tsx             # STEP 흐름 시각화
        ├── ErrorHighlight.tsx             # 에러 하이라이트
        └── DiagnosisReport.tsx            # 리포트 렌더링
```

### 3.3 각 Agent 상세

#### ① File Processor Agent

**역할**: zip 파일 해제 + SPOOL 파일 유형 분류

**입력**: zip 파일 바이너리
**출력**: `ClassifiedFiles` (JCL, PROC, SYSMSG, JESMSG, SYSPRINT, SYSOUT, unknown)

**파일 분류 규칙** (OpenFrame SPOOL 규칙 기반):

| 파일 유형 | 판별 패턴 | SPOOL 출처 |
|----------|----------|-----------|
| JCL | `*.jcl`, `*.JCL`, INPJCL 내용 패턴 | INPJCL 데이터셋 |
| PROC | `*.proc`, `*.PROC`, `*.prc` | 라이브러리 참조 |
| JESMSG | `JESMSG*`, `JESMSGLG*`, JRN 패턴 | JESMSG 데이터셋 |
| SYSMSG | `SYSMSG*`, `JESYSMSG*`, IEF/IEA 패턴 | SYSMSG 데이터셋 |
| JESJCL | `JESJCL*`, 전개된 JCL 패턴 | JESJCL 데이터셋 |
| SYSPRINT | `SYSPRINT*`, SORT/COBOL 출력 패턴 | SYSOUT DD |
| SYSOUT | 기타 SYSOUT 출력 | 사용자 DD |

**콘텐츠 기반 분류** (파일명만으로 판별 불가 시):
```python
CONTENT_PATTERNS = {
    'jcl': r'^//\w+\s+JOB\s',          # JOB 카드로 시작
    'jesmsg': r'JRN\d{4}[IWE]',        # TJES 메시지 패턴
    'sysmsg': r'IEF\d{3}[IWE]|IEA\d{3}[IWE]',  # JES 시스템 메시지
    'sysprint': r'ICE\d{3}[A-Z]|IGD\d{3}[A-Z]', # SORT/VSAM 메시지
}
```

#### ② JCL Analyzer Agent

**역할**: JCL 파싱 + STEP 흐름 분석 + PROC 인라인 전개

**기존 JCL Parser 재사용**: `legacy_modernization/parsers/jcl_parser.py`
- MVS JCL (`//` prefix) + XSP JCL (`\` prefix) 모두 지원
- JOB_CARD, EXEC_STEP, DD_STATEMENT, PROCEDURE, UTILITY 추출
- COND 파라미터, IF/THEN/ELSE 조건문 분석
- GDG, VSAM, IDCAMS 명령 인식

**출력**: `JobAnalysis`
```python
{
    "job_name": "ACCT001",
    "job_class": "A",
    "steps": [
        {
            "step_name": "EXTRACT",
            "step_number": 1,
            "program": "IEBGENER",
            "procedure": null,
            "dd_statements": [...],
            "cond": null
        },
        {
            "step_name": "SORT",
            "step_number": 2,
            "program": "DFSORT",
            "procedure": null,
            "dd_statements": [...],
            "cond": "(4,LT,EXTRACT)"
        }
    ],
    "datasets_used": [...],
    "procs_referenced": ["ACCTPROC"],
    "expanded_procs": {...}
}
```

#### ③ Error Diagnosis Agent (핵심)

**역할**: SYSMSG/JESMSG에서 에러코드 추출 + 실패 STEP 특정 + 심각도 분류

**에러 패턴 레지스트리**:

```python
ERROR_PATTERNS = {
    'abend_system': r'(?:ABEND\s+)?(S[0-9A-F]{3,4})',
    'abend_user': r'(?:ABEND\s+)?(U\d{4})',
    'openframe': r'(OFR\d+[EWI]?)',
    'tjes': r'(TJES\d+[EWI]?)',
    'ofcobol': r'(OFCOBOL-\d+)',
    'cond_code': r'(?:COND\s+CODE|RC)\s*=?\s*(\d{4})',
    'jes_msg': r'(IEF\d{3}[IWE])',
    'sort_msg': r'(ICE\d{3}[A-Z])',
    'vsam_msg': r'(IGD\d{3}[A-Z])',
    'batch_error': r'(-\d{4,5})',  # OpenFrame 에러코드
}
```

**진단 로직**:
1. 모든 에러/경고 패턴 추출 (위치 + 전후 컨텍스트 포함)
2. STEP 이름과 에러 메시지 교차 매칭 → 실패 STEP 특정
3. ABEND > COND_CODE > WARNING 순서로 심각도 분류
4. Return Code 해석: 0=정상, 4=경고, 8=에러, 12=심각, 16=치명

**출력**: `DiagnosisResult`
```python
{
    "failed_step": {"step_name": "CALC", "step_number": 3, "program": "ACCTCALC"},
    "primary_error": {"code": "S0C7", "type": "abend_system", "category": "Data Exception"},
    "all_errors": [...],
    "cond_codes": {"EXTRACT": 0, "SORT": 0, "CALC": "S0C7"},
    "error_context": "IEA995I SYMPTOM DUMP OUTPUT - S0C7 IN STEP3\n...",
    "severity": "CRITICAL"
}
```

#### ④ Knowledge Retrieval Agent

**역할**: 에러코드 → 기존 Knowledge Base에서 가이드 + 유사 사례 검색

**3단계 검색 전략**:

| 단계 | 방법 | 소스 | 속도 |
|------|------|------|------|
| 1. 정확 매칭 | `SummarySearchService.search_error_code()` | error-codes/*.md | <10ms |
| 2. Graph 탐색 | Neo4j Cypher: ErrorCode → Guide → Resolution | Knowledge Graph | <100ms |
| 3. Vector 유사 검색 | 에러 메시지 임베딩 → 유사 청크 검색 | Neo4j Vector Index | <500ms |

**검색 쿼리 보강**:
```
원본: "S0C7 에러"
보강: "S0C7 에러 Data Exception ABEND
      [에러코드 S0C7: 숫자 필드 비숫자 데이터, COBOL COMPUTE/MOVE]
      [관련: DSALC, 데이터셋 할당, 레코드 레이아웃]"
```

#### ⑤ Report Generator Agent

**역할**: 전체 진단 결과를 구조화된 리포트로 종합

**리포트 섹션**:
1. JOB 실행 요약 (STEP 흐름 다이어그램)
2. 에러 원인 분석 (코드 + 설명 + 발생 위치)
3. 대처 방안 (단계별 가이드, 우선순위 포함)
4. 참고 문서 (에러 가이드 링크, 매뉴얼 페이지)
5. 추가 확인 사항 (잠재 위험, 재발 방지)

**LLM 활용**: vLLM (Qwen 32B + QLoRA) → OpenFrame 도메인 특화 응답
**언어 지원**: ja (일본어), ko (한국어), en (영어) → `language` 파라미터

---

## 4. API 설계

### 4.1 엔드포인트

```
POST /api/v1/jcl-diagnosis/analyze          # zip 업로드 → 진단 시작 (SSE)
POST /api/v1/jcl-diagnosis/analyze-text     # 텍스트 직접 입력 → 진단
GET  /api/v1/jcl-diagnosis/history          # 진단 이력 조회
GET  /api/v1/jcl-diagnosis/history/{id}     # 특정 진단 상세
```

### 4.2 요청/응답 스키마

```python
# 요청
class JCLDiagnosisRequest(BaseModel):
    language: str = "ja"                   # 응답 언어
    message: Optional[str] = None          # 추가 질문/컨텍스트
    # zip 파일은 multipart/form-data로 별도 전송

# SSE 이벤트 타입
class DiagnosisEventType(str, Enum):
    FILE_EXTRACTED = "file_extracted"       # 파일 해제 완료
    FILE_CLASSIFIED = "file_classified"     # 파일 분류 완료
    JCL_PARSED = "jcl_parsed"             # JCL 파싱 완료
    STEP_FLOW = "step_flow"               # STEP 흐름 분석
    ERROR_FOUND = "error_found"           # 에러 발견
    SEARCHING = "searching"               # 지식베이스 검색 중
    SEARCH_RESULT = "search_result"       # 검색 결과
    GENERATING = "generating"             # 리포트 생성 중
    LLM_TOKEN = "llm_token"              # LLM 토큰 스트리밍
    REPORT_COMPLETE = "report_complete"   # 리포트 완성
    ERROR = "error"                       # 처리 에러
```

### 4.3 SSE 이벤트 스트림 예시

```json
{"type": "file_extracted", "files_count": 6, "files": ["ACCT001.jcl", ...]}
{"type": "file_classified", "jcl": 1, "proc": 1, "jesmsg": 1, "sysmsg": 1, "sysprint": 1}
{"type": "jcl_parsed", "job_name": "ACCT001", "steps_count": 4}
{"type": "step_flow", "steps": [{"name": "EXTRACT", "pgm": "IEBGENER"}, ...]}
{"type": "error_found", "code": "S0C7", "type": "abend", "step": "CALC", "severity": "CRITICAL"}
{"type": "searching", "phase": "error_guide", "query": "S0C7"}
{"type": "search_result", "source": "error-codes/BASE-5000.md", "score": 0.98}
{"type": "generating", "phase": "report"}
{"type": "llm_token", "token": "에러코드"}
{"type": "llm_token", "token": " S0C7은"}
{"type": "report_complete", "diagnosis_id": "diag_20260225_001"}
```

---

## 5. Frontend UI 설계

### 5.1 Agentic RAG 페이지 확장

기존 `AgenticRAGPage.tsx`에 zip 업로드 모드 추가:

```
┌──────────────────────────────────────────────────┐
│  🤖 Agentic RAG                                  │
│                                                  │
│  [💬 일반 질문]  [📂 JOB 진단]  ← 탭 전환        │
│                                                  │
│  ┌──────────────────────────────────────┐        │
│  │                                      │        │
│  │  📂 zip 파일을 드래그하거나 클릭       │        │
│  │     JOB 출력 파일 (SPOOL)             │        │
│  │                                      │        │
│  └──────────────────────────────────────┘        │
│                                                  │
│  [추가 질문 입력...]                    [분석 시작] │
│                                                  │
│  ── 진단 결과 ──────────────────────────          │
│                                                  │
│  📂 파일 분류                                     │
│  ├── JCL: ACCT001.jcl                            │
│  ├── PROC: ACCTPROC.proc                         │
│  ├── JESMSG: jesmsg.txt                          │
│  └── SYSMSG: sysmsg.txt                          │
│                                                  │
│  📋 STEP 흐름                                     │
│  [EXTRACT] → [SORT] → [CALC ❌] → [REPORT ⏭]    │
│   RC=0000    RC=0000   S0C7       SKIP            │
│                                                  │
│  ❌ S0C7: Data Exception                          │
│  실패 STEP: CALC (PGM=ACCTCALC)                  │
│  원인: 숫자 필드에 비숫자 데이터...                  │
│                                                  │
│  🔧 대처 방안                                     │
│  1. STEP2 출력 데이터셋 검증...                    │
│  2. ACCTCALC COMPUTE 변수 확인...                 │
│                                                  │
│  📚 참고 문서 [3건]                               │
└──────────────────────────────────────────────────┘
```

### 5.2 STEP 흐름 시각화 컴포넌트

```
[EXTRACT]  →  [SORT]  →  [CALC]  →  [REPORT]
   ✅          ✅         ❌          ⏭
  RC=0       RC=0       S0C7       SKIP
 IEBGENER   DFSORT    ACCTCALC   RPTRPT01
```

색상 코드:
- 녹색: RC=0000 (정상)
- 노란색: RC=0004 (경고)
- 빨간색: ABEND 또는 RC>=0008 (에러)
- 회색: SKIP (미실행)

---

## 6. 구현 로드맵

### Phase 1: 핵심 진단 엔진 (1주)

| 순서 | 작업 | 파일 | 난이도 |
|------|------|------|--------|
| 1-1 | File Processor: zip 해제 + 파일 분류 | `services/jcl_diagnosis/file_processor.py` | Low |
| 1-2 | Error Diagnosis: 에러 패턴 추출 | `services/jcl_diagnosis/error_diagnosis.py` | Medium |
| 1-3 | JCL Analyzer: 기존 JCL Parser 래핑 | `services/jcl_diagnosis/jcl_analyzer.py` | Medium |
| 1-4 | Pydantic 모델 정의 | `models/jcl_diagnosis.py` | Low |

### Phase 2: 지식 검색 연동 (3일)

| 순서 | 작업 | 파일 | 난이도 |
|------|------|------|--------|
| 2-1 | Knowledge Retriever: Summary + Neo4j 검색 | `services/jcl_diagnosis/knowledge_retriever.py` | Medium |
| 2-2 | 에러코드 DB 보강 (ABEND 코드 매핑) | `uploads/summaries/error-codes/ABEND-*.md` | Medium |
| 2-3 | Graph 스키마 확장 (ErrorCode → Resolution) | Neo4j Cypher | High |

### Phase 3: 리포트 생성 + API (3일)

| 순서 | 작업 | 파일 | 난이도 |
|------|------|------|--------|
| 3-1 | Report Generator: LLM 리포트 생성 | `services/jcl_diagnosis/report_generator.py` | Medium |
| 3-2 | Orchestrator: 5-Agent 파이프라인 | `services/jcl_diagnosis/orchestrator.py` | High |
| 3-3 | REST API + SSE 스트리밍 | `routers/jcl_diagnosis.py` | Medium |
| 3-4 | main.py 라우터 등록 | `app/api/main.py` | Low |

### Phase 4: Frontend UI (3일)

| 순서 | 작업 | 파일 | 난이도 |
|------|------|------|--------|
| 4-1 | zip 업로드 UI (기존 페이지 탭 추가) | `AgenticRAGPage.tsx` | Medium |
| 4-2 | SSE 이벤트 소비 + 렌더링 | `jcl-diagnosis.api.ts` | Medium |
| 4-3 | STEP 흐름 시각화 | `JobFlowDiagram.tsx` | Medium |
| 4-4 | 진단 리포트 렌더링 | `DiagnosisReport.tsx` | Low |
| 4-5 | i18n (ja, ko, en) | `locales/*.json` | Low |

### Phase 5: 품질 향상 (2일)

| 순서 | 작업 | 난이도 |
|------|------|--------|
| 5-1 | E2E 테스트 (샘플 JOB 출력) | Medium |
| 5-2 | 에러 가이드 DB 확충 (주요 ABEND 30종) | Medium |
| 5-3 | 진단 이력 저장 + 유사 사례 학습 | High |

---

## 7. 성공 지표

| 지표 | 목표 | 측정 방법 |
|------|------|----------|
| 에러코드 인식률 | >= 95% | 테스트 JOB 출력 50건 |
| 실패 STEP 특정 정확도 | >= 90% | 에러 메시지-STEP 매칭 |
| 진단 소요 시간 | < 30초 | 업로드~리포트 완성 |
| 대처 방안 적합도 | >= 80% | 전문가 리뷰 |
| 지원 에러 유형 | >= 30종 | ABEND + OpenFrame 에러 |

---

## 8. 리스크 및 대응

| 리스크 | 영향 | 대응 |
|--------|------|------|
| zip 내 파일 형식 비표준 | 파일 분류 실패 | 콘텐츠 기반 2차 분류 + unknown 폴백 |
| 에러코드 DB 미등록 | 가이드 미제공 | Vector 유사 검색 폴백 + "미등록 에러" 표시 |
| 대용량 SPOOL (>100MB) | 처리 지연 | 파일 크기 제한 + 점진적 처리 |
| JCL 방언 차이 (MVS/XSP) | 파싱 실패 | 기존 JCL Parser가 양 방언 지원 |
| LLM 환각 (잘못된 대처 방안) | 신뢰도 저하 | 에러코드 DB 기반 검증 + 출처 표시 필수 |

---

## 9. 의존성 및 전제조건

| 항목 | 상태 | 비고 |
|------|------|------|
| JCL Parser | ✅ 존재 | `legacy_modernization/parsers/jcl_parser.py` |
| 에러코드 DB | ✅ 존재 (52파일) | ABEND 코드 매핑 추가 필요 |
| Neo4j | ✅ 운용 중 | Vector Index + Knowledge Graph |
| vLLM (LLM) | ✅ 운용 중 | Qwen + QLoRA 어댑터 |
| SSE 스트리밍 | ✅ 패턴 확립 | Agentic RAG에서 검증됨 |
| 파일 업로드 | ✅ 존재 | documents router의 extract-text |
| SPOOL 구조 이해 | ✅ 조사 완료 | TJES 매뉴얼 第4章 スプール 참조 |
| Frontend 탭 UI | ⚠️ 신규 | AgenticRAGPage 확장 |
| ABEND 코드 매핑 | ⚠️ 신규 | S0C7, S0C4 등 30종 추가 필요 |

---

## 10. 차별화 포인트 (타 RAG 시스템 대비)

| 기능 | 일반 RAG | JCL Diagnosis Agent |
|------|---------|---------------------|
| 입력 방식 | 텍스트 질문만 | zip 파일 업로드 (자동 분석) |
| 에러 이해 | 사용자가 에러를 설명해야 함 | 로그에서 에러 자동 추출 |
| JCL 분석 | 불가 | STEP 흐름 + 실패 지점 시각화 |
| 도메인 지식 | 범용 | OpenFrame 19제품 특화 (에러코드 1,200개) |
| 대처 방안 | 일반적 조언 | 에러코드별 구체적 가이드 (출처 명시) |
| 유사 사례 | 불가 | Graph+Vector 유사 장애 검색 |
| 학습 | 정적 | QLoRA 어댑터 + 장애 사례 축적 |

---

*이 기능은 OpenFrame 마이그레이션/운영 고객에게 즉시 가치를 전달할 수 있는 킬러 기능입니다.*
*"에러가 나면 로그를 zip으로 묶어서 올리세요" — 이것만으로 전문 엔지니어 수준의 진단을 제공합니다.*
