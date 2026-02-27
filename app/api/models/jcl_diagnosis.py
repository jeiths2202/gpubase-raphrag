"""JCL Job Failure Diagnosis Models

OpenFrame TJES SPOOL 기반 JOB 실패 진단 데이터 모델.
C source reference: OF7/OpenFrame7_MVS/batch/include/
"""
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
    report_html: str = Field(default="", description="렌더링된 자체 포함 HTML 리포트")
    report_data: Optional[Dict] = Field(default=None, description="구조화된 리포트 JSON (report_schema 형식)")

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
