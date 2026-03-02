# Plan: JCL Diagnosis Fix - ZIP SPOOL 파싱 실패 및 할루시네이션 근절

> **Feature**: jcl-diagnosis-fix
> **Created**: 2026-02-27
> **Status**: Plan
> **Priority**: HIGH (기능 장애 - 진단 결과가 할루시네이션)

---

## 1. 문제 정의

### 1.1 핵심 증상
JCL Diagnosis 기능에서 `temp\JOB02235.zip` 업로드 시:
1. **phaseReport 할루시네이션**: `"JOBは「UNKNOWN」という名称で実行され、「done」ステータスとして終了しています。ただし、STEP数はゼロであり..."` → 실제 JOB 정보와 무관한 허위 보고서 생성
2. **404 에러**: `GET https://localhost:3000/api/v1/api/v1/support/sessions` → URL prefix 중복

### 1.2 영향 범위
- JCL Diagnosis 기능의 신뢰성 완전 상실 (UNKNOWN + 0 STEP → 무의미한 보고서)
- Premium Support 세션 목록 로드 실패 (404)

---

## 2. 근본 원인 분석 (Root Cause Analysis)

### Bug #1: SPOOL 파일 분류 실패 → UNKNOWN JOB

**원인 체인:**
```
JOB02235.zip 해제
  → 파일명 패턴 불일치 (TJES SPOOL 네이밍 미지원)
  → 콘텐츠 패턴도 fallback 실패
  → 모든 파일 UNKNOWN 분류
  → jcl_files = [], jesjcl_files = []
  → _select_best_jcl() → None
  → job_name="UNKNOWN", total_steps=0
  → LLM 프롬프트에 빈 데이터 전달
  → LLM이 "UNKNOWN" 기반 할루시네이션 생성
```

**상세 원인:**

| # | 원인 | 위치 | 설명 |
|---|------|------|------|
| 1 | **파일명 패턴 부족** | `file_processor.py:28-53` | TJES SPOOL 네이밍 `<catalog>.<jobname>.<jobid>.<seq>` 미지원. 실제 SPOOL 파일은 `SYSOUT.JOB02235.JOB00001.001` 같은 이름이지만 `INPJCL`, `JESMSG` 같은 키워드 부재 가능 |
| 2 | **콘텐츠 패턴 한계** | `file_processor.py:56-69` | JCL 감지가 `^//\w+\s+JOB\s`만 사용. JESJCL(전개된 JCL)은 `XX`로 시작하는 continuation이나 `++` prefix 등 다른 패턴 가능. JESMSG 감지도 `JRN\d{4}[IWE]`만 사용하여 OF 메시지 패턴 미포함 |
| 3 | **JCL 없을 때 JESMSG 미활용** | `jcl_analyzer.py:52-54` | JCL이 없으면 즉시 `UNKNOWN` 반환. JESMSG에서 JOB명, STEP 정보 추출 시도 없음 |
| 4 | **LLM에 검증 없이 전달** | `report_generator.py:86-143` | `job_name="UNKNOWN"`, `total_steps=0`일 때도 그대로 LLM에 전달 → 할루시네이션 유발 |
| 5 | **폴백 보고서 미사용** | `report_generator.py:51-65` | `llm_service.is_available`이면 무조건 LLM 사용. UNKNOWN 상태에서 폴백 템플릿이 더 정확함 |

### Bug #2: Premium Support 404

**원인:**
```
constants.ts:13  → API_BASE_URL = '/api/v1'
client.ts:96-97  → axios.create({ baseURL: API_BASE_URL })  // = '/api/v1'
premium-support.api.ts:7  → BASE_URL = '/api/v1/support'  // ← '/api/v1' 중복!
premium-support.api.ts:60 → client.get(`${BASE_URL}/sessions`)
                           → axios가 baseURL + URL = '/api/v1' + '/api/v1/support/sessions'
                           → 최종: '/api/v1/api/v1/support/sessions' → 404
```

---

## 3. 수정 방안

### Fix #1: SPOOL 파일 분류 강화 (`file_processor.py`)

**3.1a. TJES SPOOL 네이밍 패턴 추가**
```python
# 추가할 패턴: TJES SPOOL 데이터셋 네이밍
# 형식: *.INPJCL, *.JESJCL, *.JESMSGLG, *.JESYSMSG, *.SYSPRINT, etc.
FILENAME_PATTERNS[SpoolFileType.JCL].append(
    re.compile(r'.*\.INPJCL$', re.IGNORECASE)
)
FILENAME_PATTERNS[SpoolFileType.JESJCL].append(
    re.compile(r'.*\.JESJCL$', re.IGNORECASE)
)
FILENAME_PATTERNS[SpoolFileType.JESMSG].append(
    re.compile(r'.*\.JESMSGLG$', re.IGNORECASE)
)
```

**3.1b. 콘텐츠 패턴 확장**
```python
# JESMSG 추가 패턴 (OpenFrame TJES 메시지)
SpoolFileType.JESMSG: re.compile(
    r'JRN\d{4}[IWE]|IEF\d{3}[IWE]|HASP\d{3,4}|J\s+ES\s+M', re.MULTILINE
),
# JCL 추가 패턴 (JESJCL 전개 형태)
SpoolFileType.JCL: re.compile(
    r'^//\w+\s+JOB\s|^XX\w*\s+EXEC\s|^//\w+\s+EXEC\s', re.MULTILINE
),
# SYSMSG 추가 패턴
SpoolFileType.SYSMSG: re.compile(
    r'IEF\d{3}[IWE]|IEA\d{3}[IWE]|IOS\d{3}[A-Z]|IGD\d{3}[A-Z]', re.MULTILINE
),
```

**3.1c. 3단계 분류: 파일명 → 콘텐츠 → SPOOL 순서 추론**
```python
# 새로운 Stage 3: ZIP 내 파일 순서 기반 추론
# TJES SPOOL 출력 순서: INPJCL → JESJCL → JESMSG → JESYSMSG → SYSPRINT...
# 순서 번호가 있는 경우 활용
```

### Fix #2: JESMSG에서 JOB 정보 복원 (`jcl_analyzer.py`)

JCL 파일이 없어도 JESMSG/SYSMSG에서 JOB명과 STEP 정보를 추출:

```python
async def analyze_from_jesmsg(
    self, jesmsg_files: List[ClassifiedFile], sysmsg_files: List[ClassifiedFile]
) -> JobAnalysis:
    """JCL이 없을 때 JESMSG에서 JOB 정보 복원

    JESMSG에 포함된 정보:
    - JOB명: "JOB02235  JOBNAME  STARTED" 또는 "IEF403I JOBNAME - STARTED"
    - STEP 실행: "STEP01   RC=0000" 또는 "IEF142I STEP01 PGM=IEFBR14 COND CODE 0000"
    - ABEND: "STEP03   S0C7"
    """
```

### Fix #3: UNKNOWN 상태 검증 + 폴백 경로 (`orchestrator.py`, `report_generator.py`)

**3.3a. Orchestrator에서 분류 결과 검증**
```python
# orchestrator.py: JCL Analyzer 이후 검증 추가
if job_analysis.job_name == "UNKNOWN" and job_analysis.total_steps == 0:
    # JESMSG/SYSMSG에서 복원 시도
    job_analysis = await self.jcl_analyzer.analyze_from_jesmsg(
        jesmsg_files=classified.jesmsg_files,
        sysmsg_files=classified.sysmsg_files,
    )
```

**3.3b. ReportGenerator에서 UNKNOWN 가드**
```python
# report_generator.py: LLM 프롬프트에 경고 추가
if job_analysis.job_name == "UNKNOWN":
    # 폴백 템플릿 사용 (LLM 대신)
    # 또는 프롬프트에 "UNKNOWN은 JOB이름이 아닙니다" 명시
```

### Fix #4: Premium Support 404 수정 (`premium-support.api.ts`)

```typescript
// Before (bug):
const BASE_URL = '/api/v1/support';
// → axios baseURL='/api/v1' + '/api/v1/support/sessions' = '/api/v1/api/v1/...'

// After (fix):
const BASE_URL = '/support';
// → axios baseURL='/api/v1' + '/support/sessions' = '/api/v1/support/sessions'
```

---

## 4. 구현 순서 (Implementation Order)

| # | 작업 | 파일 | 우선도 | 예상 복잡도 |
|---|------|------|--------|------------|
| 1 | SPOOL 파일명 패턴 확장 | `file_processor.py` | P0 | Low |
| 2 | 콘텐츠 패턴 확장 | `file_processor.py` | P0 | Low |
| 3 | JESMSG 기반 JOB 정보 복원 | `jcl_analyzer.py` | P0 | Medium |
| 4 | Orchestrator 분류 실패 복원 경로 | `orchestrator.py` | P0 | Low |
| 5 | ReportGenerator UNKNOWN 가드 | `report_generator.py` | P0 | Low |
| 6 | Premium Support URL 수정 | `premium-support.api.ts` | P1 | Trivial |
| 7 | 테스트 검증 | 수동 + E2E | P0 | Medium |

---

## 5. 테스트 계획

### 5.1 검증 항목
- [ ] JOB02235.zip 업로드 → 파일 분류가 UNKNOWN이 아닌 올바른 유형으로 분류
- [ ] JOB명이 "UNKNOWN"이 아닌 실제 JOB 이름으로 표시
- [ ] STEP 수가 0이 아닌 실제 STEP 개수로 표시
- [ ] 보고서가 실제 JOB 내용을 기반으로 생성 (할루시네이션 제거)
- [ ] Premium Support 세션 목록이 정상 로드 (404 해결)

### 5.2 테스트 방법
```bash
# Backend 단위 테스트
python -m pytest tests/unit/test_file_processor.py -v
python -m pytest tests/unit/test_jcl_analyzer.py -v

# API 통합 테스트
curl -X POST http://localhost:9000/api/v1/jcl-diagnosis/analyze \
  -F "file=@temp/JOB02235.zip" -F "language=ja"

# Premium Support 404 확인
curl http://localhost:9000/api/v1/support/sessions
```

---

## 6. 리스크 및 고려사항

| 리스크 | 대응 |
|--------|------|
| SPOOL 파일 네이밍이 사이트마다 다름 | 다단계 분류(파일명→콘텐츠→순서)로 커버리지 최대화 |
| JESMSG 복원 정확도 | 복원 결과에 `(recovered_from_jesmsg)` 표시로 사용자에게 알림 |
| LLM 폴백 시 정보 부족 | 템플릿 보고서도 에러코드/RC 정보는 포함하도록 설계 |
| 실제 ZIP 파일 미확인 | 구현 시 JOB02235.zip 내부 파일명/콘텐츠 로그 출력으로 디버그 |

---

## 7. 참조 파일

| 파일 | 역할 |
|------|------|
| `app/api/services/jcl_diagnosis/file_processor.py` | SPOOL 파일 분류 (버그 위치) |
| `app/api/services/jcl_diagnosis/jcl_analyzer.py` | JCL 파싱 (UNKNOWN 반환 위치) |
| `app/api/services/jcl_diagnosis/orchestrator.py` | 파이프라인 오케스트레이터 |
| `app/api/services/jcl_diagnosis/report_generator.py` | LLM 리포트 생성 (할루시네이션 위치) |
| `app/api/services/jcl_diagnosis/error_diagnosis.py` | 에러 추출 |
| `kms-portal-ui/src/pages/JCLDiagnosisPage.tsx` | 프론트엔드 진단 페이지 |
| `kms-portal-ui/src/api/premium-support.api.ts` | 404 버그 위치 |
| `kms-portal-ui/src/api/client.ts` | axios baseURL 설정 |
| `kms-portal-ui/src/config/constants.ts` | API_BASE_URL 정의 |
