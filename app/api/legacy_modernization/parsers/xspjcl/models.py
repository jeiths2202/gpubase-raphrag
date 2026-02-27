"""XSP JCL C Parser 결과 데이터 모델.

OF7 xspjcl C 파서의 JSON 출력을 Python에서 다루기 위한 Pydantic 모델.
C 파서의 모든 기능을 완전히 래핑:
  - 43개 statement 타입 (31 JCL + 11 JCM macro + STMT_ERROR)
  - 파라미터 타입: P_PARAM(positional), K_PARAM(keyword)
  - Subparam 값 타입: VAL_NULL, VAL_STR, VAL_SUBPARAMS, VAL_DATA, VAL_RELEX
  - Instream 데이터 (p_data_t)
  - Relational expression (relex_t) 트리
  - Line range 추적 (!!RANGE!! keyword)
  - Stream (원본 소스 라인 + 에러 주석)
  - 21개 에러 타입 (SCAN_ERROR_*, PARSE_ERROR_*, EXEC_ERROR_*)
  - Macro 확장 (xspmac_parse) 정보
  - SYSIN 파일 포함 정보
  - 계층 AST: JOBG → JOB → stmts (child linked list)
"""

from enum import Enum
from typing import Any, Dict, List, Optional, Union

from pydantic import BaseModel, Field


# ──────────────────── Statement Type Enum ────────────────────

class XSPStmtType(str, Enum):
    """C 파서의 xspjcl_stmt_type_t 전체 매핑 (xspmac.h).

    31 JCL statements + 11 JCM macro statements + STMT_ERROR + STMT_OTHER.
    """
    # ── JCL statements ──
    STMT_NULL = "STMT_NULL"
    STMT_JOBG = "STMT_JOBG"
    STMT_CODE = "STMT_CODE"
    STMT_JOB = "STMT_JOB"
    STMT_EX = "STMT_EX"
    STMT_PARA = "STMT_PARA"
    STMT_FD = "STMT_FD"
    STMT_SW = "STMT_SW"
    STMT_PAUSE = "STMT_PAUSE"
    STMT_MSG = "STMT_MSG"
    STMT_NOTE = "STMT_NOTE"
    STMT_JEND = "STMT_JEND"
    STMT_JGEND = "STMT_JGEND"
    STMT_FIN = "STMT_FIN"
    STMT_SYSIN = "STMT_SYSIN"
    STMT_EX_MACRO = "STMT_EX_MACRO"
    STMT_CHAM = "STMT_CHAM"
    STMT_MACRO = "STMT_MACRO"
    STMT_MEND = "STMT_MEND"
    STMT_FDR = "STMT_FDR"
    STMT_FDDS = "STMT_FDDS"
    STMT_FDDE = "STMT_FDDE"
    STMT_STACK = "STMT_STACK"
    STMT_CAT = "STMT_CAT"
    STMT_UNCAT = "STMT_UNCAT"
    STMT_DATA = "STMT_DATA"
    STMT_END = "STMT_END"
    STMT_SCAN = "STMT_SCAN"
    STMT_SCEND = "STMT_SCEND"
    STMT_USER = "STMT_USER"
    STMT_UEND = "STMT_UEND"
    STMT_NOP = "STMT_NOP"
    STMT_COMMAND = "STMT_COMMAND"
    STMT_ERROR = "STMT_ERROR"

    # ── JCM macro statements ──
    MSTMT_DEFINE = "MSTMT_DEFINE"
    MSTMT_SKIP = "MSTMT_SKIP"
    MSTMT_IF = "MSTMT_IF"
    MSTMT_IFN = "MSTMT_IFN"
    MSTMT_SET = "MSTMT_SET"
    MSTMT_MSG = "MSTMT_MSG"
    MSTMT_WTO = "MSTMT_WTO"
    MSTMT_WTOR = "MSTMT_WTOR"
    MSTMT_NOP = "MSTMT_NOP"
    MSTMT_DEXIT = "MSTMT_DEXIT"
    MSTMT_DEFEND = "MSTMT_DEFEND"

    STMT_OTHER = "STMT_OTHER"


# ──────────────────── Error Type Enum ────────────────────

class XSPErrorCode(int, Enum):
    """C 파서의 jcl_error_t 전체 매핑 (xspjcl.h).

    21개 에러 코드: scan(0-13), parse(14-16), exec(17-21).
    """
    JCL_ERROR_OK = 0
    SCAN_ERROR = 1
    SCAN_ERROR_UNEXPECTED_INPUT = 2
    SCAN_ERROR_UNKNOWN_OPERATION_FIELD = 3
    SCAN_ERROR_MACRO_INPUT_PARAMETER_OVERFLOWED = 4
    SCAN_ERROR_MACRO_INPUT_PARAMETER_INVALID = 5
    SCAN_ERROR_SYSIN_FILE_NOT_FOUND = 6
    SCAN_ERROR_NOT_SUPPORTED_STATEMENT = 7
    SCAN_ERROR_UNKNOWN_MACRO_STATEMENT = 8
    SCAN_ERROR_MACRO_FILE_OPEN_FAIL = 9
    SCAN_ERROR_CONSOLE_DISPLAY = 10
    SCAN_ERROR_CONSOLE_ACCEPT = 11
    SCAN_ERROR_CHANGE_STREAM = 12
    SCAN_ERROR_SYSIN_PATH_GET_FAIL = 13
    PARSE_ERROR = 14
    PARSE_ERROR_NO_JOB_IN_JOBG = 15
    PARSE_ERROR_NO_STMT_IN_JOB = 16
    EXEC_ERROR = 17
    EXEC_ERROR_NO_SUCH_JOB_STREAM = 18
    EXEC_ERROR_TJES_API_JOB_START = 19
    EXEC_ERROR_TJES_API_JOB_FINISH = 20
    EXEC_ERROR_TJES_API_JOB_CURRENT = 21


# ──────────────────── Parameter Value Type Enum ────────────────────

class XSPValType(str, Enum):
    """C 파서의 jclcom_val_type_t 매핑 (jclcom.h).

    서브파라미터 값의 타입을 구분.
    """
    VAL_NULL = "VAL_NULL"
    VAL_STR = "VAL_STR"
    VAL_SUBPARAMS = "VAL_SUBPARAMS"
    VAL_DATA = "VAL_DATA"
    VAL_RELEX = "VAL_RELEX"


# ──────────────────── Relational Expression Models ────────────────────

class XSPRelexKey(BaseModel):
    """Relational expression key node (relex_key_t).

    SW/IF 문에서 사용되는 조건식의 키 또는 값.
    """
    name: Optional[str] = None
    value: int = 0


class XSPRelexComp(BaseModel):
    """Relational expression comparison node (relex_comp_t).

    비교 연산자: GT, LT, EQ, NE, GE, LE, NG, NL.
    """
    operator: str = Field(
        ..., description="비교 연산자: GT, LT, NG, NL, EQ, NE, GE, LE"
    )
    operands: List[XSPRelexKey] = Field(default_factory=list)


class XSPRelexLogic(BaseModel):
    """Relational expression logical node (relex_logic_t).

    논리 연산자: NOT, AND, OR.
    """
    operator: str = Field(..., description="논리 연산자: NOT, AND, OR")
    operands: List["XSPRelex"] = Field(default_factory=list)


class XSPRelex(BaseModel):
    """Relational expression 트리 노드 (relex_t).

    SW/IF 문의 조건식을 표현하는 트리 구조.
    type: KEY, KEY_SW, COMP, LOGIC.
    """
    type: str = Field(..., description="RELEX_KEY, RELEX_KEY_SW, RELEX_COMP, RELEX_LOGIC")
    key: Optional[XSPRelexKey] = None
    comp: Optional[XSPRelexComp] = None
    logic: Optional[XSPRelexLogic] = None


# ──────────────────── Instream Data Model ────────────────────

class XSPInstreamData(BaseModel):
    """Instream 데이터 (p_data_t).

    FD *, FDDS~FDDE, DATA~END 사이의 인라인 데이터 카드.
    """
    count: int = 0
    lines: List[str] = Field(default_factory=list)


# ──────────────────── Subparameter Model ────────────────────

class XSPSubparam(BaseModel):
    """서브파라미터 (jclcom_subparam_t).

    값 타입에 따라 다른 필드가 채워짐:
      VAL_NULL: 값 없음
      VAL_STR: str_val에 문자열
      VAL_SUBPARAMS: sub_params에 중첩 파라미터 리스트
      VAL_DATA: instream_data에 데이터 카드
      VAL_RELEX: relex에 관계식 트리
    """
    val_type: XSPValType = XSPValType.VAL_NULL
    str_val: Optional[str] = None
    sub_params: Optional[List["XSPParam"]] = None
    instream_data: Optional[XSPInstreamData] = None
    relex: Optional[XSPRelex] = None


# ──────────────────── Parameter Model ────────────────────

class XSPParam(BaseModel):
    """XSP JCL statement 파라미터 (jclcom_param_t).

    두 가지 타입:
      P_PARAM (type=0): 위치 파라미터 (position으로 구분)
      K_PARAM (type=1): 키워드 파라미터 (keyword=value)
    """
    type: str = Field("P_PARAM", description="P_PARAM 또는 K_PARAM")
    position: int = 0
    keyword: Optional[str] = None
    subparam: Optional[XSPSubparam] = None


# ──────────────────── Statement Model ────────────────────

class XSPStatement(BaseModel):
    """C 파서에서 추출한 XSP JCL statement (jclcom_stmt_t).

    계층 AST: JOBG → JOB → stmts (child_list + child_link).
    lineno_str: 매크로 확장 시 원본 라인 정보 (최대 512자).
    line_range: !!RANGE!! 파라미터에서 추출한 (first_line, last_line).
    """
    type: str = Field(..., description="C enum name: STMT_JOB, MSTMT_SET, etc.")
    type_str: Optional[str] = Field(
        None, description="xspjcl_stmt_type() 반환값: '\\\\ JOB', '/ SET'"
    )
    name: Optional[str] = None
    lineno: int = 0
    lineno_str: str = Field("", description="매크로 확장 라인 추적용 (최대 512자)")
    line_range: Optional[List[int]] = Field(
        None, description="[first_line, last_line] from !!RANGE!! param"
    )
    params: List[XSPParam] = Field(default_factory=list)
    children: List["XSPStatement"] = Field(default_factory=list)


# ──────────────────── Stream Models ────────────────────

class XSPStreamEntry(BaseModel):
    """Stream 엔트리: 원본 소스 라인 (jcl_stream.stmt_string[i])."""
    lineno: int = 0
    text: str = ""
    error: Optional[str] = Field(None, description="해당 라인의 에러 메시지")


# ──────────────────── Error Model ────────────────────

class XSPParseError(BaseModel):
    """C 파서에서 감지한 에러 (jcl_error_t + yyerror)."""
    lineno: int = 0
    error_code: int = Field(0, description="jcl_error_t enum 값")
    error_name: str = Field("", description="에러 코드 이름: SCAN_ERROR_*, etc.")
    message: str = ""
    line_text: str = Field("", description="에러 발생 라인 원문")


# ──────────────────── Macro Expansion Info ────────────────────

class XSPMacroInfo(BaseModel):
    """매크로 확장 정보 (xspmac_parse 결과).

    C 파서의 xspmac_parse()는 JCL 매크로(/ DEFINE, / SET 등)를
    확장하고 SCF 변수를 치환한 후 결과를 생성.
    """
    expanded: bool = Field(False, description="매크로 확장이 수행되었는지")
    macro_path: str = Field("", description="매크로 파일 검색 경로")
    scf_substituted: bool = Field(False, description="SCF 변수 치환 수행 여부")
    errors: List[str] = Field(default_factory=list, description="매크로 확장 에러")


# ──────────────────── Parse Result ────────────────────

class XSPParseResult(BaseModel):
    """C 파서 전체 결과.

    xspjcl_parse() + xspmac_parse()의 완전한 출력:
      - success: 파싱 성공 여부 (에러 카운트 0이면 true)
      - error_count: jcl_stream.error_count
      - jcl_errno: 최종 jcl_errno 값
      - statements: AST 루트 노드들 (jcl_tree.job_list)
      - errors: 감지된 에러 목록
      - stream: 원본 소스 라인 + 에러 주석
      - macro_info: 매크로 확장 정보
      - parser_version: C 파서 빌드 버전
      - flags: 파싱 시 사용된 플래그
    """
    success: bool = True
    error_count: int = 0
    jcl_errno: int = Field(0, description="최종 jcl_error_t 값")
    jcl_errno_name: str = Field("JCL_ERROR_OK", description="에러 코드 이름")
    jcl_errno_desc: str = Field("", description="에러 코드 설명")
    flags: int = Field(1, description="파싱 플래그: 0=default, 1=no_print, 2=always")
    statements: List[XSPStatement] = Field(default_factory=list)
    errors: List[XSPParseError] = Field(default_factory=list)
    stream: List[XSPStreamEntry] = Field(default_factory=list)
    macro_info: Optional[XSPMacroInfo] = None
    parser_version: str = Field("", description="C 파서 빌드 버전")
    total_lines: int = Field(0, description="전체 소스 라인 수")
    stmt_count: int = Field(0, description="파싱된 statement 총 수")


# ──────────────────── Enum 참조 테이블 ────────────────────

# xspjcl_stmt_type() 반환값 매핑 (xspjcl_util.c 기반)
STMT_TYPE_DISPLAY: Dict[str, str] = {
    "STMT_JOBG": "\\ JOBG",
    "STMT_CODE": "\\ CODE",
    "STMT_JOB": "\\ JOB",
    "STMT_EX": "\\ EX",
    "STMT_PARA": "\\ PARA",
    "STMT_FD": "\\ FD",
    "STMT_SW": "\\ SW",
    "STMT_PAUSE": "\\ PAUSE",
    "STMT_MSG": "\\ MSG",
    "STMT_NOTE": "\\ NOTE",
    "STMT_JEND": "\\ JEND",
    "STMT_JGEND": "\\ JGEND",
    "STMT_FIN": "\\ FIN",
    "STMT_SYSIN": "\\ SYSIN",
    "STMT_EX_MACRO": "\\ EX_MACRO",
    "STMT_CHAM": "\\ CHAM",
    "STMT_MACRO": "\\ MACRO",
    "STMT_MEND": "\\ MEND",
    "STMT_FDR": "\\ FDR",
    "STMT_FDDS": "\\ FDDS",
    "STMT_FDDE": "\\ FDDE",
    "STMT_STACK": "\\ STACK",
    "STMT_CAT": "\\ CAT",
    "STMT_UNCAT": "\\ UNCAT",
    "STMT_DATA": "\\ DATA",
    "STMT_END": "\\ END",
    "STMT_COMMAND": "\\ COMMAND",
    "STMT_SCAN": "\\ SCAN",
    "STMT_SCEND": "\\ SCEND",
    "STMT_USER": "\\ USER",
    "STMT_UEND": "\\ UEND",
    "STMT_NOP": "\\ NOP",
    "STMT_ERROR": "ERROR",
    "MSTMT_DEFINE": "/ DEFINE",
    "MSTMT_SKIP": "/ SKIP",
    "MSTMT_IF": "/ IF",
    "MSTMT_IFN": "/ IFN",
    "MSTMT_SET": "/ SET",
    "MSTMT_MSG": "/ MSG",
    "MSTMT_WTO": "/ WTO",
    "MSTMT_WTOR": "/ WTOR",
    "MSTMT_NOP": "/ NOP",
    "MSTMT_DEXIT": "/ DEXIT",
    "MSTMT_DEFEND": "/ DEFEND",
}

# jcl_error_t 에러 설명 매핑 (xspjcl_error.c 기반)
ERROR_DESCRIPTIONS: Dict[int, str] = {
    0: "No error",
    1: "Scan error",
    2: "Unexpected JCL input characters are found",
    3: "Unknown JCL Operation Field",
    4: "MACRO input parameter is overflowed",
    5: "MACRO input parameter is invalid (key and position parameter cannot mixed)",
    6: "SYSIN file not found",
    7: "Not supported statement",
    8: "Unknown MACRO statement",
    9: "MACRO file open fail",
    10: "Send message to console fail",
    11: "Receive message from console fail",
    12: "Change JCL stream for input parameter fail",
    13: "SYSIN path get fail",
    14: "Parse error",
    15: "there is no JOB in JOBG",
    16: "there is no statement in JOB",
    17: "Exec error",
    18: "No such job stream (.jcl file) not found",
    19: "tjes_api_job_start() error",
    20: "tjes_api_job_finish() error",
    21: "tjes_api_job_current() error",
}
