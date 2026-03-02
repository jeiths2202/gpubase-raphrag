# Design: JCL Job Failure Diagnosis Agent

> **Feature**: jcl-job-failure-diagnosis
> **Plan Reference**: `docs/01-plan/features/jcl-job-failure-diagnosis.plan.md`
> **Created**: 2026-02-25
> **Status**: Draft
> **Target**: OpenFrame MVS Batch (NOT XSP)

---

## 1. Architecture Overview

### 1.1 System Context

```
┌─────────────────────────────────────────────────────────────────────┐
│                        KMS Portal UI                                │
│  ┌───────────────────────────────────────────────────────────────┐  │
│  │  AgenticRAGPage.tsx  [💬 일반 질문]  [📂 JOB 진단] 탭         │  │
│  │    ↕ SSE (text/event-stream)                                  │  │
│  └───────────────────────────────────────────────────────────────┘  │
└────────────────────────────────┬────────────────────────────────────┘
                                 │ POST /api/v1/jcl-diagnosis/analyze
                                 │ (multipart/form-data: zip + message)
┌────────────────────────────────▼────────────────────────────────────┐
│                        FastAPI Backend                               │
│  ┌─────────────────────────────────────────────────────────────┐    │
│  │  jcl_diagnosis router                                        │    │
│  │  → JCLDiagnosisOrchestrator.stream_diagnosis()              │    │
│  │    ┌────────┐  ┌─────────┐  ┌──────────┐  ┌──────────┐     │    │
│  │    │  File   │→│  JCL    │→│  Error    │→│ Knowledge │     │    │
│  │    │Processor│  │Analyzer │  │Diagnosis │  │Retriever  │     │    │
│  │    └────────┘  └─────────┘  └──────────┘  └──────────┘     │    │
│  │                                   ↓                          │    │
│  │                           ┌──────────────┐                   │    │
│  │                           │    Report     │                  │    │
│  │                           │  Generator   │                   │    │
│  │                           └──────────────┘                   │    │
│  └─────────────────────────────────────────────────────────────┘    │
│           ↓                       ↓                    ↓            │
│   ┌──────────────┐  ┌──────────────────┐  ┌───────────────────┐    │
│   │  JCL Parser  │  │ SummarySearch    │  │  Neo4j            │    │
│   │  (existing)  │  │ (error-codes/)   │  │  Vector+Graph     │    │
│   └──────────────┘  └──────────────────┘  └───────────────────┘    │
└─────────────────────────────────────────────────────────────────────┘
```

### 1.2 OpenFrame MVS Batch C Source 참조

**소스 위치**: `OF7/OpenFrame7_MVS/batch/`

이 Design은 실제 C 소스에서 확인된 TJES 내부 구조를 기반으로 합니다:

| C 소스 | 역할 | Design 반영 |
|--------|------|------------|
| `include/spool.h` | SPOOL 데이터 구조체 | FileProcessor 분류 규칙 |
| `include/tjes.h` | TJES Job/Step 구조체 | JCLAnalyzer 출력 스키마 |
| `include/tjesdef.h` | Job/Step 상태 코드 정의 | ErrorDiagnosis 상태 매핑 |
| `tjes/tjclrun/executor.c` | JCL 실행 엔진 (전역변수) | ErrorDiagnosis 실패 감지 |
| `common/tjes/tjes_runner_step.c` | Step 실행 & 리포팅 | Step RC/ABEND 판별 |
| `common/tjes/tjes_jesmsg.c` | JES 메시지 출력 | JESMSG 파싱 규칙 |
| `errcode/errcode_tjes.dat` | TJES 에러코드 카탈로그 | KnowledgeRetriever 매핑 |
| `msgcode/msgcode_tjclrun.dat` | 런타임 메시지 코드 | 메시지 패턴 매칭 |

---

## 2. Data Models (Pydantic)

### 2.1 파일: `app/api/models/jcl_diagnosis.py`

```python
from pydantic import BaseModel, Field
from typing import Optional, List, Dict
from enum import Enum


# ─── Enums ────────────────────────────────────────

class SpoolFileType(str, Enum):
    """SPOOL 파일 유형 (TJES spool.h 기반)"""
    JCL = "jcl"             # INPJCL - 원본 JCL
    JESJCL = "jesjcl"       # JESJCL - 전개된 JCL
    JESMSG = "jesmsg"       # JESMSG - JES 실행 메시지
    SYSMSG = "sysmsg"       # SYSMSG - 시스템 메시지
    SYSPRINT = "sysprint"   # SYSPRINT - 프로그램 출력
    SYSOUT = "sysout"       # SYSOUT - 사용자 DD 출력
    PROC = "proc"           # PROC - 프로시저 라이브러리
    UNKNOWN = "unknown"

class StepStatus(str, Enum):
    """Step 실행 상태 (tjesdef.h step_status 기반)

    C source reference:
    'W' = WORKING, 'N' = NORMAL, 'A' = APP_ABEND,
    'S' = SYS_ABEND, 'U' = USR_ABEND
    """
    NORMAL = "normal"         # RC=0000 (exit_status='N')
    WARNING = "warning"       # RC=0004
    ERROR = "error"           # RC>=0008
    ABEND_SYSTEM = "abend_system"   # S0C7 등 (exit_status='S')
    ABEND_USER = "abend_user"       # U1234 등 (exit_status='U')
    ABEND_APP = "abend_app"         # (exit_status='A')
    SKIPPED = "skipped"       # COND 조건으로 미실행
    NOT_RUN = "not_run"       # 선행 STEP 실패로 미도달

class JobStatus(str, Enum):
    """Job 실행 상태 (tjesdef.h job_status 기반)

    C source: 'D'=DONE, 'E'=ERROR, 'T'=STOP, 'F'=FLUSH
    """
    DONE = "done"             # 정상 완료 (status='D')
    ERROR = "error"           # 비정상 완료 (status='E')
    STOPPED = "stopped"       # 운영자 중지 (status='T')
    FLUSHED = "flushed"       # 플러시 (status='F')
    UNKNOWN = "unknown"

class ErrorSeverity(str, Enum):
    CRITICAL = "critical"     # ABEND (시스템/사용자)
    HIGH = "high"             # RC >= 12
    MEDIUM = "medium"         # RC >= 8
    LOW = "low"               # RC >= 4 (경고)
    INFO = "info"             # RC = 0 or 정보 메시지

class DiagnosisEventType(str, Enum):
    """SSE 이벤트 타입"""
    FILE_EXTRACTED = "file_extracted"
    FILE_CLASSIFIED = "file_classified"
    JCL_PARSED = "jcl_parsed"
    STEP_FLOW = "step_flow"
    ERROR_FOUND = "error_found"
    SEARCHING_KNOWLEDGE = "searching_knowledge"
    SEARCH_RESULT = "search_result"
    GENERATING_REPORT = "generating_report"
    LLM_TOKEN = "llm_token"
    REPORT_COMPLETE = "report_complete"
    ERROR = "error"


# ─── File Processing Models ──────────────────────

class ClassifiedFile(BaseModel):
    """분류된 SPOOL 파일"""
    filename: str
    file_type: SpoolFileType
    size_bytes: int
    content: str = Field(default="", description="파일 텍스트 내용")
    detection_method: str = Field(
        default="filename",
        description="분류 방법: filename | content_pattern | fallback"
    )

class ClassifiedFiles(BaseModel):
    """zip에서 추출/분류된 전체 파일셋"""
    total_files: int
    files: List[ClassifiedFile]
    jcl_files: List[ClassifiedFile] = []
    proc_files: List[ClassifiedFile] = []
    jesmsg_files: List[ClassifiedFile] = []
    sysmsg_files: List[ClassifiedFile] = []
    jesjcl_files: List[ClassifiedFile] = []
    sysprint_files: List[ClassifiedFile] = []
    sysout_files: List[ClassifiedFile] = []
    unknown_files: List[ClassifiedFile] = []


# ─── JCL Analysis Models ─────────────────────────

class DDStatement(BaseModel):
    """DD 문 정보"""
    dd_name: str
    dsn: Optional[str] = None
    disp: Optional[str] = None
    unit: Optional[str] = None
    space: Optional[str] = None
    dcb: Optional[Dict[str, str]] = None
    sysout: Optional[str] = None       # SYSOUT 클래스 (A, *, etc)

class JobStep(BaseModel):
    """JCL STEP 정보 (tjes_steprpt_t 매핑)

    C struct reference:
    - step_name → step_name (8 chars)
    - pgm_name → program (16 chars)
    - proc_step → procedure
    - cond_code → return_code (TJES_EXITCODE_LEN=6)
    """
    step_number: int
    step_name: str = Field(description="STEP 이름 (//STEPNAME)")
    program: Optional[str] = Field(default=None, description="PGM= 값")
    procedure: Optional[str] = Field(default=None, description="PROC= 값")
    dd_statements: List[DDStatement] = []
    cond_parameter: Optional[str] = Field(
        default=None,
        description="COND= 파라미터 (실행 조건)"
    )
    return_code: Optional[str] = Field(
        default=None,
        description="RC 값 (0000~9999 or ABEND code)"
    )
    status: StepStatus = StepStatus.NOT_RUN
    cpu_time: Optional[str] = None
    start_time: Optional[str] = None
    end_time: Optional[str] = None

class JobAnalysis(BaseModel):
    """JCL JOB 분석 결과"""
    job_name: str
    job_class: Optional[str] = None
    msgclass: Optional[str] = None
    msglevel: Optional[str] = None
    notify: Optional[str] = None
    steps: List[JobStep] = []
    procs_referenced: List[str] = []
    datasets_used: List[str] = []
    total_steps: int = 0
    job_status: JobStatus = JobStatus.UNKNOWN
    raw_jcl: Optional[str] = None


# ─── Error Diagnosis Models ──────────────────────

class ExtractedError(BaseModel):
    """SPOOL에서 추출된 에러 정보"""
    code: str = Field(description="에러코드 (S0C7, U1234, -5212, IEF453I 등)")
    error_type: str = Field(
        description="에러 유형: abend_system|abend_user|openframe|tjes|ofcobol|cond_code|jes_msg|sort_msg|vsam_msg|batch_error"
    )
    message_line: str = Field(description="에러가 발견된 원본 라인")
    line_number: int
    context_before: List[str] = Field(default=[], description="에러 전 2줄")
    context_after: List[str] = Field(default=[], description="에러 후 2줄")
    source_file: str = Field(description="에러 출처 파일명")
    source_type: SpoolFileType

class DiagnosisResult(BaseModel):
    """에러 진단 결과"""
    failed_step: Optional[JobStep] = Field(
        default=None,
        description="실패한 STEP (특정 불가 시 None)"
    )
    primary_error: Optional[ExtractedError] = Field(
        default=None,
        description="주요 에러 (가장 심각한 것)"
    )
    all_errors: List[ExtractedError] = []
    step_results: Dict[str, str] = Field(
        default={},
        description="STEP별 RC: {'EXTRACT': '0000', 'SORT': '0000', 'CALC': 'S0C7'}"
    )
    severity: ErrorSeverity = ErrorSeverity.INFO
    summary: str = Field(default="", description="진단 요약 (1줄)")


# ─── Knowledge Retrieval Models ──────────────────

class ErrorGuide(BaseModel):
    """에러 가이드 검색 결과"""
    code: str
    name: Optional[str] = None
    module: Optional[str] = None
    description: str = ""
    cause: str = ""
    solution: str = ""
    source_file: Optional[str] = None
    source_page: Optional[str] = None
    confidence: float = 0.0

class SimilarCase(BaseModel):
    """유사 장애 사례"""
    title: str
    error_code: Optional[str] = None
    description: str = ""
    resolution: str = ""
    similarity_score: float = 0.0
    source: str = ""

class KnowledgeResult(BaseModel):
    """지식 검색 종합 결과"""
    error_guides: List[ErrorGuide] = []
    similar_cases: List[SimilarCase] = []
    related_documents: List[Dict] = []
    program_docs: List[Dict] = []


# ─── Report & API Models ─────────────────────────

class DiagnosisReport(BaseModel):
    """최종 진단 리포트"""
    diagnosis_id: str
    job_analysis: JobAnalysis
    diagnosis_result: DiagnosisResult
    knowledge_result: KnowledgeResult
    report_text: str = Field(description="LLM이 생성한 종합 리포트")
    language: str = "ja"
    created_at: str = ""

class JCLDiagnosisRequest(BaseModel):
    """API 요청 모델"""
    message: Optional[str] = Field(
        default=None,
        description="추가 질문/컨텍스트 (선택)"
    )
    language: str = Field(
        default="ja",
        description="응답 언어: ja|ko|en"
    )
    # zip 파일은 multipart/form-data로 전송 (UploadFile)
```

---

## 3. Service Layer Design

### 3.1 패키지 구조

```
app/api/services/jcl_diagnosis/
├── __init__.py                     # 패키지 export
├── orchestrator.py                 # 5-Agent 파이프라인 오케스트레이터
├── file_processor.py               # ① zip 해제 + SPOOL 파일 분류
├── jcl_analyzer.py                 # ② JCL 파싱 + STEP 분석
├── error_diagnosis.py              # ③ 에러코드 추출 + 실패 STEP 특정
├── knowledge_retriever.py          # ④ Neo4j + Summary 검색
├── report_generator.py             # ⑤ LLM 리포트 생성
└── abend_code_registry.py          # ABEND 코드 카탈로그 (정적 매핑)
```

### 3.2 `__init__.py` - 패키지 Export

```python
from .orchestrator import JCLDiagnosisOrchestrator, get_jcl_diagnosis_orchestrator

__all__ = ["JCLDiagnosisOrchestrator", "get_jcl_diagnosis_orchestrator"]
```

### 3.3 `orchestrator.py` - 파이프라인 오케스트레이터

```python
"""JCL Job Failure Diagnosis Orchestrator

5-Agent sequential pipeline:
  FileProcessor → JCLAnalyzer → ErrorDiagnosis → KnowledgeRetriever → ReportGenerator

SSE 이벤트를 yield하면서 각 Agent 단계를 실행합니다.
"""
import json
import uuid
from datetime import datetime
from typing import AsyncGenerator, Dict, Optional

from app.api.models.jcl_diagnosis import (
    ClassifiedFiles, JobAnalysis, DiagnosisResult, KnowledgeResult,
    DiagnosisReport, DiagnosisEventType, JCLDiagnosisRequest
)
from .file_processor import FileProcessor
from .jcl_analyzer import JCLAnalyzer
from .error_diagnosis import ErrorDiagnosisAgent
from .knowledge_retriever import KnowledgeRetriever
from .report_generator import ReportGenerator


class JCLDiagnosisOrchestrator:
    """5-Agent 파이프라인 오케스트레이터

    각 Agent는 독립적인 서비스 클래스이며, 오케스트레이터가
    데이터 흐름을 관리하고 SSE 이벤트를 생성합니다.
    """

    def __init__(self):
        self.file_processor = FileProcessor()
        self.jcl_analyzer = JCLAnalyzer()
        self.error_diagnosis = ErrorDiagnosisAgent()
        self.knowledge_retriever = KnowledgeRetriever()
        self.report_generator = ReportGenerator()

    async def stream_diagnosis(
        self,
        zip_content: bytes,
        zip_filename: str,
        request: JCLDiagnosisRequest,
        user_id: Optional[str] = None,
    ) -> AsyncGenerator[Dict, None]:
        """전체 진단 파이프라인 실행 (SSE 스트리밍)

        Yields:
            Dict: SSE 이벤트 (type + payload)
        """
        diagnosis_id = f"diag_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"

        try:
            # ──── ① File Processor ────
            yield self._event(DiagnosisEventType.FILE_EXTRACTED, {
                "message": f"zip 파일 해제 중... ({zip_filename})",
                "diagnosis_id": diagnosis_id
            })

            classified = await self.file_processor.process(zip_content, zip_filename)

            yield self._event(DiagnosisEventType.FILE_CLASSIFIED, {
                "total_files": classified.total_files,
                "jcl": len(classified.jcl_files),
                "proc": len(classified.proc_files),
                "jesmsg": len(classified.jesmsg_files),
                "sysmsg": len(classified.sysmsg_files),
                "sysprint": len(classified.sysprint_files),
                "unknown": len(classified.unknown_files),
                "files": [f.filename for f in classified.files]
            })

            # ──── ② JCL Analyzer ────
            job_analysis = await self.jcl_analyzer.analyze(
                jcl_files=classified.jcl_files,
                proc_files=classified.proc_files,
                jesjcl_files=classified.jesjcl_files,
            )

            yield self._event(DiagnosisEventType.JCL_PARSED, {
                "job_name": job_analysis.job_name,
                "total_steps": job_analysis.total_steps,
                "steps": [
                    {"name": s.step_name, "pgm": s.program, "proc": s.procedure}
                    for s in job_analysis.steps
                ]
            })

            yield self._event(DiagnosisEventType.STEP_FLOW, {
                "steps": [
                    {
                        "step_number": s.step_number,
                        "step_name": s.step_name,
                        "program": s.program or s.procedure,
                        "status": s.status.value,
                        "return_code": s.return_code
                    }
                    for s in job_analysis.steps
                ]
            })

            # ──── ③ Error Diagnosis ────
            diagnosis = await self.error_diagnosis.diagnose(
                jesmsg_files=classified.jesmsg_files,
                sysmsg_files=classified.sysmsg_files,
                sysprint_files=classified.sysprint_files,
                job_analysis=job_analysis,
            )

            if diagnosis.primary_error:
                yield self._event(DiagnosisEventType.ERROR_FOUND, {
                    "code": diagnosis.primary_error.code,
                    "type": diagnosis.primary_error.error_type,
                    "severity": diagnosis.severity.value,
                    "failed_step": diagnosis.failed_step.step_name if diagnosis.failed_step else None,
                    "message": diagnosis.primary_error.message_line,
                    "step_results": diagnosis.step_results,
                })

            # ──── ④ Knowledge Retriever ────
            yield self._event(DiagnosisEventType.SEARCHING_KNOWLEDGE, {
                "phase": "error_guide",
                "query": diagnosis.primary_error.code if diagnosis.primary_error else "general"
            })

            knowledge = await self.knowledge_retriever.search(diagnosis)

            for guide in knowledge.error_guides:
                yield self._event(DiagnosisEventType.SEARCH_RESULT, {
                    "source": guide.source_file or guide.module,
                    "code": guide.code,
                    "confidence": guide.confidence,
                    "description": guide.description[:200],
                })

            # ──── ⑤ Report Generator ────
            yield self._event(DiagnosisEventType.GENERATING_REPORT, {
                "phase": "llm_synthesis"
            })

            async for token_event in self.report_generator.stream_report(
                job_analysis=job_analysis,
                diagnosis=diagnosis,
                knowledge=knowledge,
                user_message=request.message,
                language=request.language,
            ):
                yield token_event

            # ──── 완료 ────
            yield self._event(DiagnosisEventType.REPORT_COMPLETE, {
                "diagnosis_id": diagnosis_id,
                "job_name": job_analysis.job_name,
                "severity": diagnosis.severity.value,
                "primary_error": diagnosis.primary_error.code if diagnosis.primary_error else None,
            })

        except Exception as e:
            yield self._event(DiagnosisEventType.ERROR, {
                "message": str(e),
                "diagnosis_id": diagnosis_id,
            })

    def _event(self, event_type: DiagnosisEventType, data: Dict) -> Dict:
        """SSE 이벤트 딕셔너리 생성"""
        return {"type": event_type.value, **data}


# ─── Singleton ────────────────────────────────────

_instance: Optional[JCLDiagnosisOrchestrator] = None

def get_jcl_diagnosis_orchestrator() -> JCLDiagnosisOrchestrator:
    global _instance
    if _instance is None:
        _instance = JCLDiagnosisOrchestrator()
    return _instance
```

### 3.4 `file_processor.py` - ① zip 해제 + 파일 분류

```python
"""SPOOL 파일 분류 Agent

zip 파일에서 추출된 파일을 OpenFrame TJES SPOOL 데이터셋 유형으로 분류합니다.

분류 전략 (2단계):
  1. 파일명 패턴 매칭 (fast path)
  2. 콘텐츠 패턴 매칭 (fallback)

참조: OF7/OpenFrame7_MVS/batch/include/spool.h
  - SPOOL 데이터셋: INPJCL, JESMSG, SYSMSG, JESJCL, SYSPRINT, SYSOUT
  - 네이밍: <catalog>.<jobname>.<job-id>.<sequence>
"""
import io
import os
import re
import zipfile
from typing import List

from app.api.models.jcl_diagnosis import (
    ClassifiedFile, ClassifiedFiles, SpoolFileType
)


class FileProcessor:
    """zip 해제 + SPOOL 파일 유형 분류"""

    # ─── 파일명 기반 분류 패턴 ─────────────────
    FILENAME_PATTERNS = {
        SpoolFileType.JCL: [
            re.compile(r'.*\.(jcl|JCL)$'),
            re.compile(r'.*INPJCL.*', re.IGNORECASE),
        ],
        SpoolFileType.PROC: [
            re.compile(r'.*\.(proc|PROC|prc|PRC)$'),
        ],
        SpoolFileType.JESJCL: [
            re.compile(r'.*JESJCL.*', re.IGNORECASE),
        ],
        SpoolFileType.JESMSG: [
            re.compile(r'.*JES(MSG|MSGLG).*', re.IGNORECASE),
        ],
        SpoolFileType.SYSMSG: [
            re.compile(r'.*SYS(MSG|YSMSG).*', re.IGNORECASE),
            re.compile(r'.*JESYSMSG.*', re.IGNORECASE),
        ],
        SpoolFileType.SYSPRINT: [
            re.compile(r'.*SYSPRINT.*', re.IGNORECASE),
        ],
        SpoolFileType.SYSOUT: [
            re.compile(r'.*SYSOUT.*', re.IGNORECASE),
            re.compile(r'.*SPOOL.*', re.IGNORECASE),
        ],
    }

    # ─── 콘텐츠 기반 분류 패턴 (fallback) ──────
    CONTENT_PATTERNS = {
        SpoolFileType.JCL: re.compile(
            r'^//\w+\s+JOB\s', re.MULTILINE
        ),
        SpoolFileType.JESMSG: re.compile(
            r'JRN\d{4}[IWE]', re.MULTILINE
        ),
        SpoolFileType.SYSMSG: re.compile(
            r'IEF\d{3}[IWE]|IEA\d{3}[IWE]', re.MULTILINE
        ),
        SpoolFileType.SYSPRINT: re.compile(
            r'ICE\d{3}[A-Z]|IGD\d{3}[A-Z]', re.MULTILINE
        ),
    }

    # 최대 zip 해제 크기 (100MB)
    MAX_ZIP_SIZE = 100 * 1024 * 1024
    # 개별 파일 최대 읽기 크기 (10MB)
    MAX_FILE_READ = 10 * 1024 * 1024

    async def process(
        self, zip_content: bytes, zip_filename: str
    ) -> ClassifiedFiles:
        """zip 해제 → 파일 분류 → ClassifiedFiles 반환"""
        files = self._extract_zip(zip_content)
        classified = self._classify_files(files)
        return classified

    def _extract_zip(self, zip_content: bytes) -> List[dict]:
        """zip 바이너리에서 파일 추출 (in-memory)"""
        files = []
        with zipfile.ZipFile(io.BytesIO(zip_content), 'r') as zf:
            total_size = sum(info.file_size for info in zf.infolist())
            if total_size > self.MAX_ZIP_SIZE:
                raise ValueError(
                    f"zip 전체 크기 {total_size // (1024*1024)}MB가 "
                    f"제한 {self.MAX_ZIP_SIZE // (1024*1024)}MB를 초과합니다"
                )

            for info in zf.infolist():
                if info.is_dir():
                    continue
                filename = os.path.basename(info.filename)
                if not filename:
                    continue

                content_bytes = zf.read(info.filename)[:self.MAX_FILE_READ]
                # 텍스트 디코딩 시도 (UTF-8 → Shift-JIS → Latin-1)
                content = self._decode_content(content_bytes)

                files.append({
                    "filename": filename,
                    "size_bytes": info.file_size,
                    "content": content,
                })
        return files

    def _decode_content(self, content_bytes: bytes) -> str:
        """텍스트 디코딩 (멀티 인코딩 지원)"""
        for encoding in ["utf-8", "shift_jis", "euc-jp", "cp932", "latin-1"]:
            try:
                return content_bytes.decode(encoding)
            except (UnicodeDecodeError, LookupError):
                continue
        return content_bytes.decode("latin-1", errors="replace")

    def _classify_files(self, files: List[dict]) -> ClassifiedFiles:
        """2단계 분류: 파일명 → 콘텐츠 패턴"""
        classified_list = []

        for f in files:
            file_type, method = self._classify_single(f["filename"], f["content"])
            cf = ClassifiedFile(
                filename=f["filename"],
                file_type=file_type,
                size_bytes=f["size_bytes"],
                content=f["content"],
                detection_method=method,
            )
            classified_list.append(cf)

        # 유형별 그룹핑
        result = ClassifiedFiles(
            total_files=len(classified_list),
            files=classified_list,
        )
        for cf in classified_list:
            getattr(result, f"{cf.file_type.value}_files").append(cf)

        return result

    def _classify_single(self, filename: str, content: str) -> tuple:
        """단일 파일 분류 (type, method)"""
        # Stage 1: 파일명 패턴
        for ftype, patterns in self.FILENAME_PATTERNS.items():
            for pattern in patterns:
                if pattern.match(filename):
                    return ftype, "filename"

        # Stage 2: 콘텐츠 패턴 (첫 200줄)
        head = "\n".join(content.split("\n")[:200])
        for ftype, pattern in self.CONTENT_PATTERNS.items():
            if pattern.search(head):
                return ftype, "content_pattern"

        return SpoolFileType.UNKNOWN, "fallback"
```

### 3.5 `jcl_analyzer.py` - ② JCL 파싱 + STEP 분석

```python
"""JCL Analyzer Agent

기존 JCL Parser (legacy_modernization/parsers/jcl_parser.py)를 래핑하여
Job Failure Diagnosis에 필요한 STEP 흐름 분석을 수행합니다.

주요 역할:
  - JCL Parser 호출 → features 추출
  - STEP 순서 + 프로그램 + DD 매핑
  - PROC 참조 확인
  - JESMSG에서 STEP별 RC 추출 (파싱 보완)
"""
import re
from typing import List, Optional

from app.api.models.jcl_diagnosis import (
    ClassifiedFile, JobAnalysis, JobStep, DDStatement, StepStatus, JobStatus
)


class JCLAnalyzer:
    """JCL 파싱 + STEP 흐름 분석"""

    # STEP RC 추출 패턴 (JESMSG에서)
    # 예: "STEP01   RC=0000", "CALC     S0C7"
    _RC_PATTERN = re.compile(
        r'(\w+)\s+(?:RC=(\d{4})|COND\s+CODE\s*=?\s*(\d{4})|(S[0-9A-F]{3,4})|(U\d{4}))'
    )

    # JOB 카드 패턴
    _JOB_PATTERN = re.compile(
        r'^//(\w+)\s+JOB\s+(.*)', re.MULTILINE
    )

    # EXEC 문 패턴
    _EXEC_PATTERN = re.compile(
        r'^//(\w*)\s+EXEC\s+(.*)', re.MULTILINE
    )

    # DD 문 패턴
    _DD_PATTERN = re.compile(
        r'^//(\w+)\s+DD\s+(.*)', re.MULTILINE
    )

    async def analyze(
        self,
        jcl_files: List[ClassifiedFile],
        proc_files: List[ClassifiedFile],
        jesjcl_files: List[ClassifiedFile],
    ) -> JobAnalysis:
        """JCL 파싱 → JobAnalysis 생성

        우선순위: JESJCL (전개済) > JCL (원본) > PROC
        """
        # 가장 좋은 JCL 소스 선택
        jcl_content = self._select_best_jcl(jcl_files, jesjcl_files)
        if not jcl_content:
            return JobAnalysis(job_name="UNKNOWN", total_steps=0)

        # JOB 카드 파싱
        job_name, job_params = self._parse_job_card(jcl_content)

        # STEP 파싱
        steps = self._parse_steps(jcl_content)

        # PROC 참조 수집
        procs = [s.procedure for s in steps if s.procedure]

        # 데이터셋 수집
        datasets = self._extract_datasets(jcl_content)

        return JobAnalysis(
            job_name=job_name,
            job_class=job_params.get("CLASS"),
            msgclass=job_params.get("MSGCLASS"),
            msglevel=job_params.get("MSGLEVEL"),
            notify=job_params.get("NOTIFY"),
            steps=steps,
            procs_referenced=list(set(procs)),
            datasets_used=datasets,
            total_steps=len(steps),
            raw_jcl=jcl_content,
        )

    def _select_best_jcl(
        self,
        jcl_files: List[ClassifiedFile],
        jesjcl_files: List[ClassifiedFile],
    ) -> Optional[str]:
        """전개된 JESJCL 우선, 없으면 원본 JCL"""
        if jesjcl_files:
            return jesjcl_files[0].content
        if jcl_files:
            return jcl_files[0].content
        return None

    def _parse_job_card(self, jcl: str) -> tuple:
        """JOB 문 파싱 → (job_name, params_dict)"""
        match = self._JOB_PATTERN.search(jcl)
        if not match:
            return "UNKNOWN", {}

        job_name = match.group(1)
        params_str = match.group(2)
        params = self._parse_keyword_params(params_str)
        return job_name, params

    def _parse_steps(self, jcl: str) -> List[JobStep]:
        """EXEC 문 기준 STEP 파싱"""
        steps = []
        step_num = 0

        for match in self._EXEC_PATTERN.finditer(jcl):
            step_num += 1
            step_name = match.group(1) or f"STEP{step_num:02d}"
            exec_params = match.group(2).strip()

            program = None
            procedure = None

            if exec_params.startswith("PGM="):
                program = exec_params.split("PGM=")[1].split(",")[0].split()[0]
            elif exec_params.startswith("PROC="):
                procedure = exec_params.split("PROC=")[1].split(",")[0].split()[0]
            else:
                # EXEC procname (PROC= 생략 형태)
                procedure = exec_params.split(",")[0].split()[0]

            # COND 파라미터 추출
            cond = None
            params = self._parse_keyword_params(exec_params)
            if "COND" in params:
                cond = params["COND"]

            # 해당 STEP의 DD 문 수집
            dd_stmts = self._extract_dd_for_step(jcl, step_name)

            steps.append(JobStep(
                step_number=step_num,
                step_name=step_name,
                program=program,
                procedure=procedure,
                dd_statements=dd_stmts,
                cond_parameter=cond,
            ))

        return steps

    def update_step_results_from_jesmsg(
        self,
        job_analysis: JobAnalysis,
        jesmsg_content: str,
    ) -> JobAnalysis:
        """JESMSG에서 STEP별 RC를 추출하여 JobAnalysis에 반영

        JESMSG 포맷 (tjes_runner_step.c 참조):
        - 정상: "STEP01  RC=0000"
        - ABEND: "STEP03  S0C7"
        """
        rc_map = {}
        for match in self._RC_PATTERN.finditer(jesmsg_content):
            step_name = match.group(1)
            rc = match.group(2) or match.group(3)  # RC= or COND CODE=
            abend_s = match.group(4)  # System ABEND
            abend_u = match.group(5)  # User ABEND

            if rc:
                rc_map[step_name] = rc
            elif abend_s:
                rc_map[step_name] = abend_s
            elif abend_u:
                rc_map[step_name] = abend_u

        # STEP에 RC 반영
        found_failure = False
        for step in job_analysis.steps:
            rc_value = rc_map.get(step.step_name)
            if rc_value:
                step.return_code = rc_value
                step.status = self._rc_to_status(rc_value)
                if step.status in (StepStatus.ABEND_SYSTEM, StepStatus.ABEND_USER, StepStatus.ERROR):
                    found_failure = True
            elif found_failure:
                step.status = StepStatus.NOT_RUN

        # Job 전체 상태
        job_analysis.job_status = (
            JobStatus.ERROR if found_failure else JobStatus.DONE
        )
        return job_analysis

    def _rc_to_status(self, rc: str) -> StepStatus:
        """RC 값 → StepStatus 변환 (tjesdef.h 매핑)"""
        if rc.startswith("S"):
            return StepStatus.ABEND_SYSTEM
        if rc.startswith("U"):
            return StepStatus.ABEND_USER
        try:
            code = int(rc)
            if code == 0:
                return StepStatus.NORMAL
            elif code <= 4:
                return StepStatus.WARNING
            else:
                return StepStatus.ERROR
        except ValueError:
            return StepStatus.ERROR

    def _parse_keyword_params(self, params_str: str) -> dict:
        """JCL 키워드 파라미터 파싱 (KEY=VALUE 형식)"""
        result = {}
        # 괄호 내부는 쉼표 분리 제외
        parts = re.split(r',(?![^()]*\))', params_str)
        for part in parts:
            part = part.strip()
            if "=" in part:
                key, _, value = part.partition("=")
                result[key.strip()] = value.strip()
        return result

    def _extract_dd_for_step(self, jcl: str, step_name: str) -> List[DDStatement]:
        """특정 STEP에 속하는 DD 문 추출"""
        # 간략화: 다음 EXEC 문 전까지의 DD 문 수집
        dd_stmts = []
        in_step = False
        for line in jcl.split("\n"):
            if re.match(rf'^//{step_name}\s+EXEC\s', line):
                in_step = True
                continue
            if in_step and re.match(r'^//\w+\s+EXEC\s', line):
                break
            if in_step:
                dd_match = self._DD_PATTERN.match(line)
                if dd_match:
                    dd_name = dd_match.group(1)
                    dd_params = self._parse_keyword_params(dd_match.group(2))
                    dd_stmts.append(DDStatement(
                        dd_name=dd_name,
                        dsn=dd_params.get("DSN"),
                        disp=dd_params.get("DISP"),
                        sysout=dd_params.get("SYSOUT"),
                    ))
        return dd_stmts

    def _extract_datasets(self, jcl: str) -> List[str]:
        """JCL 전체에서 DSN= 값 추출"""
        return list(set(re.findall(r'DSN=([A-Z0-9.&()]+)', jcl, re.IGNORECASE)))
```

### 3.6 `error_diagnosis.py` - ③ 에러 추출 + 실패 STEP 특정

```python
"""Error Diagnosis Agent

SYSMSG/JESMSG에서 에러코드를 추출하고 실패 STEP을 특정합니다.

에러 패턴 레지스트리는 OF7 C 소스를 기반으로 작성:
  - tjesdef.h: Step status codes (N/A/S/U)
  - executor.c: ABEND flag (_run_abend, _run_step_abend)
  - errcode_tjes.dat: TJES error code ranges (-1 ~ -951)
  - msgcode_tjclrun.dat: JRN prefix messages
"""
import re
from typing import List, Optional, Tuple

from app.api.models.jcl_diagnosis import (
    ClassifiedFile, JobAnalysis, DiagnosisResult, ExtractedError,
    SpoolFileType, StepStatus, ErrorSeverity, JobStep
)
from .abend_code_registry import ABEND_REGISTRY


class ErrorDiagnosisAgent:
    """SPOOL 로그에서 에러 추출 + 진단"""

    # ─── 에러 패턴 레지스트리 (우선순위 순) ─────
    ERROR_PATTERNS: List[Tuple[str, re.Pattern]] = [
        # System ABEND (최고 우선순위)
        ("abend_system", re.compile(r'(?:ABEND\s+)?(S[0-9A-F]{3,4})\b')),
        # User ABEND
        ("abend_user", re.compile(r'(?:ABEND\s+)?(U\d{4})\b')),
        # OpenFrame 고유 에러코드
        ("openframe", re.compile(r'\b(OFR\d+[EWI]?)\b')),
        # TJES 에러코드
        ("tjes", re.compile(r'\b(TJES\d+[EWI]?)\b')),
        # OFCOBOL 에러
        ("ofcobol", re.compile(r'\b(OFCOBOL-\d+)\b')),
        # Condition Code (RC)
        ("cond_code", re.compile(r'(?:COND\s+CODE|RC)\s*=?\s*(\d{4})')),
        # JES 시스템 메시지 (IEF)
        ("jes_msg", re.compile(r'\b(IEF\d{3}[IWE])\b')),
        # SORT 메시지 (ICE)
        ("sort_msg", re.compile(r'\b(ICE\d{3}[A-Z])\b')),
        # VSAM/SMS 메시지 (IGD)
        ("vsam_msg", re.compile(r'\b(IGD\d{3}[A-Z])\b')),
        # OpenFrame 에러코드 (음수)
        ("batch_error", re.compile(r'\b(-\d{4,5})\b')),
    ]

    async def diagnose(
        self,
        jesmsg_files: List[ClassifiedFile],
        sysmsg_files: List[ClassifiedFile],
        sysprint_files: List[ClassifiedFile],
        job_analysis: JobAnalysis,
    ) -> DiagnosisResult:
        """에러 진단 실행

        1. 모든 SPOOL 파일에서 에러 패턴 추출
        2. 실패 STEP 특정 (에러 메시지 ↔ STEP 이름 교차 매칭)
        3. 심각도 분류 (ABEND > RC>=12 > RC>=8 > RC>=4)
        """
        all_errors: List[ExtractedError] = []

        # 파일 유형별 에러 추출 (우선순위: SYSMSG > JESMSG > SYSPRINT)
        for files, ftype in [
            (sysmsg_files, SpoolFileType.SYSMSG),
            (jesmsg_files, SpoolFileType.JESMSG),
            (sysprint_files, SpoolFileType.SYSPRINT),
        ]:
            for f in files:
                errors = self._extract_errors(f.content, f.filename, ftype)
                all_errors.extend(errors)

        if not all_errors:
            return DiagnosisResult(summary="에러가 감지되지 않았습니다.")

        # 중복 제거 (같은 코드는 최초 발견만 유지)
        unique_errors = self._deduplicate(all_errors)

        # 주요 에러 선택 (ABEND 우선)
        primary = self._select_primary_error(unique_errors)

        # 실패 STEP 특정
        failed_step = self._identify_failed_step(
            unique_errors, job_analysis.steps
        )

        # STEP별 RC 매핑
        step_results = self._build_step_results(unique_errors, job_analysis.steps)

        # 심각도 판정
        severity = self._assess_severity(primary)

        return DiagnosisResult(
            failed_step=failed_step,
            primary_error=primary,
            all_errors=unique_errors,
            step_results=step_results,
            severity=severity,
            summary=self._build_summary(primary, failed_step),
        )

    def _extract_errors(
        self, content: str, filename: str, source_type: SpoolFileType
    ) -> List[ExtractedError]:
        """단일 파일에서 에러 패턴 추출"""
        errors = []
        lines = content.split("\n")

        for i, line in enumerate(lines):
            for error_type, pattern in self.ERROR_PATTERNS:
                for match in pattern.finditer(line):
                    code = match.group(1)

                    # RC=0000은 에러가 아님
                    if error_type == "cond_code" and code == "0000":
                        continue

                    errors.append(ExtractedError(
                        code=code,
                        error_type=error_type,
                        message_line=line.strip(),
                        line_number=i + 1,
                        context_before=[
                            lines[j].strip()
                            for j in range(max(0, i - 2), i)
                        ],
                        context_after=[
                            lines[j].strip()
                            for j in range(i + 1, min(len(lines), i + 3))
                        ],
                        source_file=filename,
                        source_type=source_type,
                    ))

        return errors

    def _deduplicate(self, errors: List[ExtractedError]) -> List[ExtractedError]:
        """같은 에러코드는 최초 발견만 유지"""
        seen = set()
        result = []
        for e in errors:
            key = (e.code, e.error_type)
            if key not in seen:
                seen.add(key)
                result.append(e)
        return result

    def _select_primary_error(
        self, errors: List[ExtractedError]
    ) -> Optional[ExtractedError]:
        """심각도 순서로 주요 에러 선택"""
        priority = [
            "abend_system", "abend_user", "abend_app",
            "openframe", "tjes", "ofcobol",
            "cond_code", "batch_error",
            "jes_msg", "sort_msg", "vsam_msg",
        ]
        for ptype in priority:
            for e in errors:
                if e.error_type == ptype:
                    # cond_code는 RC>=8만 primary로 선택
                    if ptype == "cond_code":
                        try:
                            if int(e.code) < 8:
                                continue
                        except ValueError:
                            pass
                    return e
        return errors[0] if errors else None

    def _identify_failed_step(
        self,
        errors: List[ExtractedError],
        steps: List[JobStep],
    ) -> Optional[JobStep]:
        """에러 메시지에서 실패 STEP 특정

        전략: 에러 라인에 STEP 이름이 포함되어 있으면 매칭
        """
        step_names = {s.step_name: s for s in steps}

        for error in errors:
            if error.error_type in ("abend_system", "abend_user", "openframe", "tjes"):
                # 에러 메시지 + 전후 컨텍스트에서 STEP 이름 검색
                search_text = (
                    error.message_line + " " +
                    " ".join(error.context_before) + " " +
                    " ".join(error.context_after)
                )
                for sname, step in step_names.items():
                    if sname in search_text:
                        return step

        # 폴백: ABEND 에러가 있으면 마지막 실행된 STEP
        for step in reversed(steps):
            if step.status in (
                StepStatus.ABEND_SYSTEM, StepStatus.ABEND_USER, StepStatus.ERROR
            ):
                return step

        return None

    def _build_step_results(
        self,
        errors: List[ExtractedError],
        steps: List[JobStep],
    ) -> dict:
        """STEP별 RC 딕셔너리 생성"""
        results = {}
        for step in steps:
            if step.return_code:
                results[step.step_name] = step.return_code
            else:
                results[step.step_name] = step.status.value
        return results

    def _assess_severity(self, primary: Optional[ExtractedError]) -> ErrorSeverity:
        """주요 에러의 심각도 판정"""
        if not primary:
            return ErrorSeverity.INFO

        if primary.error_type in ("abend_system", "abend_user", "abend_app"):
            return ErrorSeverity.CRITICAL

        if primary.error_type == "cond_code":
            try:
                rc = int(primary.code)
                if rc >= 12:
                    return ErrorSeverity.HIGH
                if rc >= 8:
                    return ErrorSeverity.MEDIUM
                return ErrorSeverity.LOW
            except ValueError:
                return ErrorSeverity.MEDIUM

        if primary.error_type in ("openframe", "tjes", "ofcobol"):
            return ErrorSeverity.HIGH

        return ErrorSeverity.MEDIUM

    def _build_summary(
        self,
        primary: Optional[ExtractedError],
        failed_step: Optional[JobStep],
    ) -> str:
        """진단 1줄 요약"""
        if not primary:
            return "에러가 감지되지 않았습니다."

        # ABEND 코드 레지스트리에서 설명 조회
        desc = ABEND_REGISTRY.get(primary.code, {}).get("description", "")

        step_info = ""
        if failed_step:
            pgm = failed_step.program or failed_step.procedure or ""
            step_info = f" (STEP: {failed_step.step_name}, PGM: {pgm})"

        return f"{primary.code}{' - ' + desc if desc else ''}{step_info}"
```

### 3.7 `abend_code_registry.py` - ABEND 코드 정적 매핑

```python
"""ABEND 코드 레지스트리

주요 System ABEND 코드의 설명/원인/대처 방안 매핑.
이 레지스트리는 LLM을 거치지 않는 즉시 참조용입니다.

참조: IBM System Codes + OpenFrame 호환 코드
"""

ABEND_REGISTRY: dict = {
    # ─── Data Exceptions ──────────────────────
    "S0C1": {
        "description": "Operation Exception",
        "cause": "유효하지 않은 기계어 명령 실행 시도",
        "common_causes": [
            "잘못된 프로그램 진입점",
            "모듈이 올바르게 링크되지 않음",
            "CSECT 이름 불일치"
        ],
    },
    "S0C4": {
        "description": "Protection Exception (Storage Violation)",
        "cause": "할당되지 않은 메모리 영역 접근",
        "common_causes": [
            "배열 인덱스 초과 (COBOL OCCURS)",
            "WORKING-STORAGE 초기화 누락",
            "GETMAIN/FREEMAIN 불일치",
            "잘못된 포인터 사용"
        ],
    },
    "S0C7": {
        "description": "Data Exception",
        "cause": "숫자 연산 시 비숫자 데이터 사용",
        "common_causes": [
            "MOVE/COMPUTE에 SPACE가 포함된 변수",
            "파일 레이아웃과 COPYBOOK 불일치",
            "초기화되지 않은 숫자 변수",
            "EBCDIC/ASCII 변환 오류"
        ],
    },
    "S013": {
        "description": "Conflicting DCB Parameters",
        "cause": "DD 문의 DCB 파라미터와 프로그램의 DCB가 불일치",
        "common_causes": [
            "LRECL/BLKSIZE 불일치",
            "RECFM 불일치 (F vs V)",
            "데이터셋 존재하지 않음"
        ],
    },
    "S0CB": {
        "description": "Floating Point Division by Zero",
        "cause": "부동소수점 0으로 나누기",
        "common_causes": ["COMPUTE 문에서 0으로 나누기"],
    },
    "S222": {
        "description": "Job Cancelled by Operator",
        "cause": "운영자가 JOB을 CANCEL 명령으로 취소",
        "common_causes": ["무한 루프 감지", "리소스 과다 사용"],
    },
    "S322": {
        "description": "Time Limit Exceeded",
        "cause": "JOB/STEP TIME 파라미터 초과",
        "common_causes": [
            "무한 루프",
            "대용량 데이터 처리 시 TIME 부족",
            "TIME=1440 지정 필요"
        ],
    },
    "S806": {
        "description": "Module Not Found",
        "cause": "EXEC PGM= 또는 CALL 대상 모듈이 라이브러리에 없음",
        "common_causes": [
            "프로그램명 오타",
            "STEPLIB/JOBLIB DD 누락",
            "라이브러리 연결 누락 (LKED 실패)"
        ],
    },
    "S837": {
        "description": "End of Volume / Dataset Full",
        "cause": "데이터셋에 할당된 공간 초과",
        "common_causes": [
            "SPACE 파라미터 부족",
            "2차 할당 미지정",
            "SMS 스토리지 그룹 Full"
        ],
    },
    "S913": {
        "description": "Security Authorization Failure",
        "cause": "RACF/TACF 보안 인증 실패",
        "common_causes": [
            "데이터셋 접근 권한 없음",
            "TACF 프로파일 미등록",
            "USER ID 권한 불일치"
        ],
    },
    "SB37": {
        "description": "Dataset Space Exhausted (End of Volume)",
        "cause": "데이터셋 공간 부족 (볼륨 끝)",
        "common_causes": [
            "SPACE 1차/2차 할당 부족",
            "볼륨에 여유 공간 없음"
        ],
    },
    "SD37": {
        "description": "Dataset Space Exhausted (No Secondary)",
        "cause": "2차 할당 미지정 상태에서 공간 부족",
        "common_causes": ["SPACE 2차 할당 추가 필요"],
    },
    "SE37": {
        "description": "Dataset Space Exhausted (Max Extents)",
        "cause": "최대 Extent 수 초과",
        "common_causes": [
            "Extent 수 제한 도달 (최대 16)",
            "데이터셋 재구성 필요"
        ],
    },
}
```

### 3.8 `knowledge_retriever.py` - ④ 지식 검색

```python
"""Knowledge Retrieval Agent

진단 결과를 바탕으로 기존 Knowledge Base에서 에러 가이드 + 유사 사례를 검색합니다.

3단계 검색:
  1. SummarySearchService → error-codes/*.md (정확 매칭, <10ms)
  2. SummaryBM25Service → 에러 메시지 전문 검색 (BM25)
  3. Neo4j Vector Index → 유사 장애 사례 (벡터 검색)
"""
from typing import Optional

from app.api.models.jcl_diagnosis import (
    DiagnosisResult, KnowledgeResult, ErrorGuide, SimilarCase
)
from app.api.services.summary_search_service import get_summary_search_service
from app.api.services.summary_bm25_service import get_summary_bm25_service
from .abend_code_registry import ABEND_REGISTRY


class KnowledgeRetriever:
    """에러 가이드 + 유사 사례 검색"""

    async def search(self, diagnosis: DiagnosisResult) -> KnowledgeResult:
        """진단 결과 기반 지식 검색"""
        result = KnowledgeResult()

        if not diagnosis.primary_error:
            return result

        # ──── Stage 1: ABEND 레지스트리 즉시 조회 ────
        abend_info = ABEND_REGISTRY.get(diagnosis.primary_error.code)
        if abend_info:
            result.error_guides.append(ErrorGuide(
                code=diagnosis.primary_error.code,
                description=abend_info.get("description", ""),
                cause=abend_info.get("cause", ""),
                solution="\n".join(abend_info.get("common_causes", [])),
                source_file="abend_code_registry (built-in)",
                confidence=1.0,
            ))

        # ──── Stage 2: Summary Search (에러코드 정확 매칭) ────
        summary_svc = get_summary_search_service()
        for error in diagnosis.all_errors[:5]:  # 상위 5개 에러만
            try:
                summary_result = await summary_svc.search_error_code(error.code)
                if summary_result:
                    result.error_guides.append(ErrorGuide(
                        code=error.code,
                        name=summary_result.get("name"),
                        module=summary_result.get("module"),
                        description=summary_result.get("description", ""),
                        cause=summary_result.get("cause", ""),
                        solution=summary_result.get("solution", ""),
                        source_file=summary_result.get("source_file"),
                        confidence=0.95,
                    ))
            except Exception:
                pass

        # ──── Stage 3: BM25 전문 검색 (에러 메시지 기반) ────
        bm25_svc = get_summary_bm25_service()
        error_text = diagnosis.primary_error.message_line
        try:
            bm25_results = await bm25_svc.search(
                query=error_text,
                top_k=3,
            )
            for r in bm25_results:
                if r.get("score", 0) > 0.3:
                    result.similar_cases.append(SimilarCase(
                        title=r.get("title", ""),
                        description=r.get("content", "")[:500],
                        similarity_score=r.get("score", 0),
                        source=r.get("source", ""),
                    ))
        except Exception:
            pass

        # ──── Stage 4: Neo4j Vector Search (유사 사례) ────
        # TODO: Phase 2에서 구현
        # - 에러 메시지를 임베딩하여 벡터 검색
        # - ErrorCode → Guide → Resolution 그래프 탐색

        return result
```

### 3.9 `report_generator.py` - ⑤ LLM 리포트 생성

```python
"""Report Generator Agent

수집된 모든 정보를 종합하여 LLM 기반 진단 리포트를 생성합니다.
SSE llm_token 이벤트로 스트리밍합니다.

LLM: vLLM (Qwen 2.5 + QLoRA OpenFrame 어댑터)
"""
import json
from typing import AsyncGenerator, Dict, Optional

from app.api.models.jcl_diagnosis import (
    JobAnalysis, DiagnosisResult, KnowledgeResult,
    DiagnosisEventType, StepStatus
)
from app.api.services.learning_llm_service import get_learning_llm_service


class ReportGenerator:
    """LLM 기반 진단 리포트 생성 (스트리밍)"""

    SYSTEM_PROMPT = """あなたはOpenFrame TJES バッチジョブ障害診断の専門エンジニアです。
JCL JOBの実行ログを分析し、障害原因と対処方法を提供します。

重要な規則:
- 提供された情報のみに基づいて回答してください
- 推測ではなく、ログから確認できる事実を報告してください
- エラーコードの説明は、提供されたエラーガイドを引用してください
- 対処方法は具体的なステップで提示してください"""

    async def stream_report(
        self,
        job_analysis: JobAnalysis,
        diagnosis: DiagnosisResult,
        knowledge: KnowledgeResult,
        user_message: Optional[str] = None,
        language: str = "ja",
    ) -> AsyncGenerator[Dict, None]:
        """LLM 리포트를 토큰 단위로 스트리밍

        Yields:
            Dict: {"type": "llm_token", "token": "..."} 형태
        """
        prompt = self._build_prompt(
            job_analysis, diagnosis, knowledge, user_message, language
        )

        llm_service = get_learning_llm_service()

        try:
            async for token in llm_service.stream_generate(
                prompt=prompt,
                system_prompt=self.SYSTEM_PROMPT,
                max_tokens=2048,
                temperature=0.3,  # 정확도 중시
            ):
                yield {
                    "type": DiagnosisEventType.LLM_TOKEN.value,
                    "token": token,
                }
        except Exception as e:
            # LLM 실패 시 템플릿 기반 폴백 리포트
            fallback = self._generate_fallback_report(
                job_analysis, diagnosis, knowledge, language
            )
            yield {
                "type": DiagnosisEventType.LLM_TOKEN.value,
                "token": fallback,
            }

    def _build_prompt(
        self,
        job_analysis: JobAnalysis,
        diagnosis: DiagnosisResult,
        knowledge: KnowledgeResult,
        user_message: Optional[str],
        language: str,
    ) -> str:
        """LLM 프롬프트 조합"""
        # STEP 흐름 요약
        step_summary = self._format_step_flow(job_analysis)

        # 에러 가이드 컨텍스트
        guides_text = "\n".join([
            f"- {g.code}: {g.description}\n  原因: {g.cause}\n  対処: {g.solution}"
            for g in knowledge.error_guides
        ]) or "エラーガイドなし"

        # 유사 사례
        cases_text = "\n".join([
            f"- {c.title} (類似度: {c.similarity_score:.0%})\n  {c.description[:200]}"
            for c in knowledge.similar_cases[:3]
        ]) or "類似事例なし"

        lang_instruction = {
            "ja": "日本語で回答してください。",
            "ko": "한국어로 답변해 주세요.",
            "en": "Please respond in English.",
        }.get(language, "日本語で回答してください。")

        return f"""{lang_instruction}

## JOB情報
- JOB名: {job_analysis.job_name}
- JOBステータス: {job_analysis.job_status.value}
- STEP数: {job_analysis.total_steps}

## STEP実行フロー
{step_summary}

## エラー診断
- 障害STEP: {diagnosis.failed_step.step_name if diagnosis.failed_step else 'N/A'}
- プログラム: {diagnosis.failed_step.program if diagnosis.failed_step else 'N/A'}
- 主要エラー: {diagnosis.primary_error.code if diagnosis.primary_error else 'N/A'}
- 重大度: {diagnosis.severity.value}
- エラーメッセージ: {diagnosis.primary_error.message_line if diagnosis.primary_error else 'N/A'}

## エラーガイド（参照情報）
{guides_text}

## 類似障害事例
{cases_text}

{f"## ユーザー追加質問: {user_message}" if user_message else ""}

上記情報を基に、以下の構成で障害分析レポートを作成してください:
1. JOB実行サマリー（STEPフローの概要）
2. エラー原因分析（コード・メッセージ・発生箇所）
3. 対処方法（具体的なステップ）
4. 参考資料（エラーガイド・類似事例の引用）
5. 追加確認事項（再発防止・潜在リスク）"""

    def _format_step_flow(self, job: JobAnalysis) -> str:
        """STEP 흐름을 텍스트로 포맷"""
        lines = []
        for s in job.steps:
            icon = {
                StepStatus.NORMAL: "OK",
                StepStatus.WARNING: "WARN",
                StepStatus.ERROR: "ERR",
                StepStatus.ABEND_SYSTEM: "ABEND",
                StepStatus.ABEND_USER: "ABEND",
                StepStatus.SKIPPED: "SKIP",
                StepStatus.NOT_RUN: "---",
            }.get(s.status, "?")
            pgm = s.program or s.procedure or "?"
            rc = s.return_code or s.status.value
            lines.append(f"  STEP{s.step_number}({s.step_name}) PGM={pgm} → [{icon}] {rc}")
        return "\n".join(lines) or "  (STEP情報なし)"

    def _generate_fallback_report(
        self,
        job_analysis: JobAnalysis,
        diagnosis: DiagnosisResult,
        knowledge: KnowledgeResult,
        language: str,
    ) -> str:
        """LLM 실패 시 템플릿 폴백 리포트"""
        step_flow = self._format_step_flow(job_analysis)
        primary = diagnosis.primary_error

        guides = "\n".join([
            f"- {g.code}: {g.description}"
            for g in knowledge.error_guides
        ]) or "- (参考情報なし)"

        return f"""## JOB実行サマリー
JOB名: {job_analysis.job_name}
STEP数: {job_analysis.total_steps}
{step_flow}

## エラー原因
コード: {primary.code if primary else 'N/A'}
メッセージ: {primary.message_line if primary else 'N/A'}
障害STEP: {diagnosis.failed_step.step_name if diagnosis.failed_step else 'N/A'}
重大度: {diagnosis.severity.value}

## 参考エラーガイド
{guides}

(注: LLM応答が利用できなかったため、テンプレートレポートを表示しています)
"""
```

---

## 4. Router Design

### 4.1 파일: `app/api/routers/jcl_diagnosis.py`

```python
"""JCL Job Failure Diagnosis Router

Endpoints:
  POST /api/v1/jcl-diagnosis/analyze   - zip 업로드 → SSE 스트리밍 진단
  POST /api/v1/jcl-diagnosis/analyze-text - 텍스트 직접 입력 → SSE 진단
"""
import json
from fastapi import APIRouter, Depends, UploadFile, File, Form
from fastapi.responses import StreamingResponse

from app.api.core.deps import get_current_user
from app.api.models.jcl_diagnosis import JCLDiagnosisRequest
from app.api.services.jcl_diagnosis import get_jcl_diagnosis_orchestrator


router = APIRouter(prefix="/jcl-diagnosis", tags=["JCL Diagnosis"])


@router.post("/analyze")
async def analyze_job_failure(
    file: UploadFile = File(..., description="JOB 출력 zip 파일"),
    message: str = Form(default=None, description="추가 질문"),
    language: str = Form(default="ja", description="응답 언어"),
    current_user: dict = Depends(get_current_user),
):
    """zip 파일 업로드 → JOB 실패 진단 (SSE 스트리밍)

    multipart/form-data:
      - file: zip 파일 (필수)
      - message: 추가 질문/컨텍스트 (선택)
      - language: ja|ko|en (기본: ja)
    """
    zip_content = await file.read()
    request = JCLDiagnosisRequest(message=message, language=language)
    orchestrator = get_jcl_diagnosis_orchestrator()

    async def generate():
        async for event in orchestrator.stream_diagnosis(
            zip_content=zip_content,
            zip_filename=file.filename or "unknown.zip",
            request=request,
            user_id=current_user.get("user_id"),
        ):
            yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/analyze-text")
async def analyze_job_failure_text(
    request: JCLDiagnosisRequest,
    current_user: dict = Depends(get_current_user),
):
    """텍스트 직접 입력 → 진단 (Phase 2에서 구현)

    사용자가 SPOOL 텍스트를 직접 붙여넣기하는 경우
    """
    # TODO: Phase 2
    pass
```

### 4.2 main.py 라우터 등록

```python
# app/api/main.py에 추가
from app.api.routers import jcl_diagnosis
app.include_router(jcl_diagnosis.router, prefix=API_PREFIX)
```

---

## 5. Frontend Design

### 5.1 AgenticRAGPage 탭 확장

기존 `AgenticRAGPage.tsx`에 "JOB 진단" 탭을 추가합니다.

```
┌──── AgenticRAGPage.tsx ─────────────────────────────┐
│                                                      │
│  [💬 일반 질문]  [📂 JOB 진단]                       │
│                  ^^^^^^^^^^^ (신규 탭)                │
│                                                      │
│  ┌── JOB 진단 모드 ──────────────────────────────┐   │
│  │                                                │   │
│  │  📂 zip 파일을 드래그 또는 클릭               │   │
│  │     (JOB SPOOL 출력 파일)                     │   │
│  │                                                │   │
│  │  [추가 질문 입력...]             [📤 분석 시작] │   │
│  │                                                │   │
│  └────────────────────────────────────────────────┘   │
│                                                      │
│  ── 진단 결과 (SSE 스트리밍) ──────────────────      │
│                                                      │
│  📂 파일 분류 → file_classified 이벤트              │
│  📋 STEP 흐름 → step_flow 이벤트                    │
│  ❌ 에러 발견 → error_found 이벤트                   │
│  🔍 지식 검색 → search_result 이벤트                │
│  📝 리포트   → llm_token 이벤트 (스트리밍)          │
│                                                      │
└──────────────────────────────────────────────────────┘
```

### 5.2 SSE 이벤트 → UI 매핑

| SSE Event | UI Component | 표시 내용 |
|-----------|-------------|----------|
| `file_extracted` | ProgressBar | "zip 해제 중..." |
| `file_classified` | FileTree | 파일 목록 + 유형 아이콘 |
| `jcl_parsed` | Badge | "JOB: ACCT001 (4 STEPS)" |
| `step_flow` | **JobFlowDiagram** | STEP 흐름 시각화 |
| `error_found` | AlertBanner (red) | "S0C7 - STEP3(CALC)" |
| `searching_knowledge` | Spinner | "지식 검색 중..." |
| `search_result` | SourceCard | 에러 가이드 카드 |
| `generating_report` | Spinner | "리포트 생성 중..." |
| `llm_token` | MarkdownRenderer | 스트리밍 텍스트 |
| `report_complete` | CompleteBadge | "진단 완료" |

### 5.3 JobFlowDiagram 컴포넌트

```
STEP 흐름 시각화:

┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐
│ EXTRACT  │ →  │  SORT    │ →  │  CALC    │ →  │ REPORT   │
│ IEBGENER │    │ DFSORT   │    │ ACCTCALC │    │ RPTRPT01 │
│ ✅ 0000  │    │ ✅ 0000  │    │ ❌ S0C7  │    │ ⏭ SKIP  │
└──────────┘    └──────────┘    └──────────┘    └──────────┘
```

색상 규칙:
- `StepStatus.NORMAL` → green (`bg-green-100 border-green-500`)
- `StepStatus.WARNING` → yellow (`bg-yellow-100 border-yellow-500`)
- `StepStatus.ERROR/ABEND_*` → red (`bg-red-100 border-red-500`)
- `StepStatus.SKIPPED/NOT_RUN` → gray (`bg-gray-100 border-gray-300`)

### 5.4 i18n 키

```json
// locales/ja/common.json 추가분
{
  "jclDiagnosis": {
    "title": "JOB障害診断",
    "tabLabel": "JOB診断",
    "uploadPrompt": "JOB出力のzipファイルをドラッグまたはクリック",
    "additionalQuestion": "追加の質問を入力...",
    "analyzeButton": "分析開始",
    "fileClassified": "ファイル分類完了",
    "stepFlow": "STEPフロー",
    "errorFound": "エラー検出",
    "searchingKnowledge": "ナレッジ検索中...",
    "generatingReport": "レポート生成中...",
    "reportComplete": "診断完了",
    "severity": {
      "critical": "致命的",
      "high": "高",
      "medium": "中",
      "low": "低"
    }
  }
}
```

---

## 6. 구현 순서 (Build Sequence)

```
Phase 1: Backend 핵심 (순서 엄수)
──────────────────────────────────
  ① models/jcl_diagnosis.py          ← 모든 서비스가 참조 (최우선)
  ② services/jcl_diagnosis/__init__.py
  ③ services/jcl_diagnosis/abend_code_registry.py  ← 정적, 의존성 없음
  ④ services/jcl_diagnosis/file_processor.py       ← 의존성: models만
  ⑤ services/jcl_diagnosis/jcl_analyzer.py         ← 의존성: models만
  ⑥ services/jcl_diagnosis/error_diagnosis.py      ← 의존성: models + abend_registry
  ⑦ services/jcl_diagnosis/knowledge_retriever.py  ← 의존성: models + summary_search
  ⑧ services/jcl_diagnosis/report_generator.py     ← 의존성: models + learning_llm
  ⑨ services/jcl_diagnosis/orchestrator.py         ← 의존성: 모든 서비스
  ⑩ routers/jcl_diagnosis.py                       ← 의존성: orchestrator + deps
  ⑪ main.py 라우터 등록

Phase 2: Frontend (Phase 1 완료 후)
──────────────────────────────────
  ⑫ api/jcl-diagnosis.api.ts         ← API 클라이언트
  ⑬ components/JCLDiagnosis/JobFlowDiagram.tsx
  ⑭ AgenticRAGPage.tsx 탭 추가
  ⑮ i18n 3개 로케일 (ja, ko, en)

Phase 3: 품질 향상 (Phase 2 완료 후)
──────────────────────────────────
  ⑯ E2E 테스트 (샘플 JOB zip)
  ⑰ ABEND 코드 확충 (30종 → 50종)
  ⑱ Neo4j Vector 유사 사례 검색
```

---

## 7. OpenFrame MVS Batch 전문가 Agent 생성

### 7.1 Claude Code Agent 정의

`.claude/agents/openframe-batch-expert.md`는 이미 존재하나 JOB Failure Diagnosis에 특화된 지식을 보강해야 합니다.

**보강 내용** (기존 agent에 추가):

```markdown
### JOB Failure Diagnosis

#### SPOOL 데이터셋 구조 (C source: OF7/OpenFrame7_MVS/batch/include/spool.h)
- `spool_t.jesmsg_fd` → JESMSG 파일 디스크립터
- `spool_t.sysmsg_fd` → SYSMSG 파일 디스크립터
- `spool_t.jesjcl_fd` → JESJCL 파일 디스크립터
- `spool_jesq_t.status` → N=new, D=delete, C=change, P=print

#### Step 상태 코드 (C source: OF7/OpenFrame7_MVS/batch/include/tjesdef.h)
| 코드 | 의미 | exit_status |
|------|------|-------------|
| W | 실행 중 | WORKING |
| N | 정상 종료 | NORMAL (RC=0000) |
| A | 어플리케이션 ABEND | APP_ABEND |
| S | 시스템 ABEND | SYS_ABEND |
| U | 사용자 ABEND | USR_ABEND |

#### Job 상태 전이 (C source: executor.c)
READY(R) → START(S) → WORKING(W) → DONE(D) or ERROR(E)

#### 에러코드 범위 (C source: errcode/errcode_tjes.dat)
| 범위 | 분류 |
|------|------|
| -1 ~ -14 | 공통 프레임워크 |
| -100 ~ -111 | 잘못된 파라미터 |
| -200 ~ -213 | Job/Runner 에러 |
| -300 ~ -307 | 큐/리소스 에러 |
| -800 ~ -801 | JCL 경로/문법 에러 |
| -900 ~ -903 | 보안/SAF 에러 |
```

---

## 8. 데이터 흐름 다이어그램

```
zip_content (bytes)
    │
    ▼
FileProcessor.process()
    │ → ClassifiedFiles
    │     .jcl_files[]
    │     .jesmsg_files[]
    │     .sysmsg_files[]
    │
    ├──────────────────────────────────┐
    ▼                                  ▼
JCLAnalyzer.analyze()        ErrorDiagnosisAgent.diagnose()
    │ → JobAnalysis                │ → DiagnosisResult
    │     .job_name                │     .primary_error
    │     .steps[]                 │     .failed_step
    │     .total_steps             │     .severity
    │                              │
    └──────────┬───────────────────┘
               │
               ▼
    JCLAnalyzer.update_step_results_from_jesmsg()
    (JESMSG의 RC를 JobAnalysis.steps에 반영)
               │
               ▼
    KnowledgeRetriever.search(diagnosis)
               │ → KnowledgeResult
               │     .error_guides[]
               │     .similar_cases[]
               │
               ▼
    ReportGenerator.stream_report(
        job_analysis, diagnosis, knowledge
    )
               │ → SSE: llm_token 스트리밍
               │
               ▼
    DiagnosisReport (최종)
```

---

## 9. 보안 및 제약사항

| 항목 | 제약 | 대응 |
|------|------|------|
| zip 크기 | 최대 100MB | `FileProcessor.MAX_ZIP_SIZE` |
| 개별 파일 | 최대 10MB 읽기 | `FileProcessor.MAX_FILE_READ` |
| 인코딩 | UTF-8/Shift-JIS/EUC-JP/CP932 | 다중 디코딩 시도 |
| zip bomb | 해제 후 총 크기 검증 | `total_size` 사전 확인 |
| 인증 | `get_current_user` 의존성 | 기존 JWT 인증 재사용 |
| LLM 실패 | vLLM 타임아웃/에러 | 템플릿 폴백 리포트 |
| 임시 파일 | in-memory 처리 | 디스크 미사용 (io.BytesIO) |

---

*이 Design은 OF7/OpenFrame7_MVS/batch C 소스의 실제 구조체와 상태 코드를 기반으로 작성되었습니다.*
