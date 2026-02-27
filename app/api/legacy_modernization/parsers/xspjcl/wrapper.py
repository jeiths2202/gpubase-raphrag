"""OF7 XSP JCL C 파서 ctypes 래퍼.

공유 라이브러리 libxspjcl_kms.so를 ctypes로 로드하여
OF7 xspjcl C 파서의 **모든 기능**을 Python에서 직접 호출한다.

래핑 대상 C 기능 전체:
  - xspjcl_parse(): 소스 파싱 → AST + Stream + Errors
  - xspmac_parse(): 매크로 확장 (/DEFINE, /SET, SCF 변수 치환)
  - SYSIN 파일 포함 (xspjcl_sysin)
  - 43개 statement 타입 파싱
  - 파라미터 (positional/keyword + subparam 중첩)
  - Instream 데이터 (FD *, FDDS~FDDE, DATA~END)
  - Relational expression (SW/IF 조건식)
  - Line range 추적 (!!RANGE!! → first_line, last_line)
  - 21개 에러 타입 감지 + 에러 라인 추적
  - Stream 관리 (원본 소스 라인 + 에러 주석 매핑)

C 라이브러리 미존재 시 is_available=False로 graceful 처리.
"""

import ctypes
import json
import logging
import os
from pathlib import Path
from typing import Optional

from .models import XSPParseResult

logger = logging.getLogger(__name__)

# 라이브러리 검색 순서
_LIB_SEARCH_PATHS = [
    # 1. 환경변수 override
    os.environ.get("XSPJCL_LIB_PATH", ""),
    # 2. 패키지 내 lib/ 디렉토리
    str(Path(__file__).parent / "lib" / "libxspjcl_kms.so"),
    # 3. 시스템 라이브러리 경로 (LD_LIBRARY_PATH에 포함된 경우)
    "libxspjcl_kms.so",
]


class XSPJCLCWrapper:
    """OF7 xspjcl C 파서 ctypes 래퍼 (싱글턴).

    C 파서의 모든 기능을 JSON 직렬화하여 Python으로 전달.
    kms_xspjcl_parse_string()은 내부에서:
      1. xspmac_parse() — 매크로 확장 + SCF 변수 치환
      2. xspjcl_parse() — JCL 파싱 (AST 생성)
      3. 트리 워킹 — jcl_tree → JSON 직렬화
         (모든 param 타입, subparam, instream data, relex 포함)
      4. Stream 수집 — 원본 소스 라인 + 에러 주석
      5. 에러 수집 — error_count, jcl_errno, 에러 목록
    을 수행하고 완전한 JSON을 반환한다.

    Usage:
        wrapper = XSPJCLCWrapper.get_instance()
        if wrapper.is_available:
            result = wrapper.parse(source_code)
            # result.statements: 계층 AST
            # result.stream: 원본 소스 라인
            # result.errors: 에러 목록
            # result.macro_info: 매크로 확장 정보
    """

    _instance: Optional["XSPJCLCWrapper"] = None

    def __init__(self) -> None:
        self._lib: Optional[ctypes.CDLL] = None
        self._available = False
        self._load_library()

    def _load_library(self) -> None:
        """공유 라이브러리 로드 시도. 실패 시 _available=False."""
        for path in _LIB_SEARCH_PATHS:
            if not path:
                continue
            if path != "libxspjcl_kms.so" and not Path(path).exists():
                continue
            try:
                lib = ctypes.CDLL(path)
                self._setup_functions(lib)
                self._lib = lib
                self._available = True
                logger.info("XSP JCL C parser loaded from: %s", path)
                return
            except (OSError, AttributeError) as e:
                logger.debug("Failed to load %s: %s", path, e)
                continue
        logger.info(
            "XSP JCL C parser not available (will use Python fallback)"
        )

    def _setup_functions(self, lib: ctypes.CDLL) -> None:
        """C 래퍼 함수 시그니처 설정.

        kms_xspjcl_wrapper.c에 정의된 래퍼 함수들:
        - kms_xspjcl_parse_string: 문자열 입력 → JSON (모든 기능 포함)
        - kms_xspjcl_parse_file: 파일 입력 → JSON (모든 기능 포함)
        - kms_xspjcl_free: 마지막 결과 메모리 해제
        - kms_xspjcl_version: 파서 빌드 버전 문자열
        - kms_xspjcl_error_desc: 에러 코드 → 설명 문자열
        - kms_xspjcl_stmt_types: 지원 statement 타입 목록 JSON
        """
        # const char *kms_xspjcl_parse_string(const char *source, int flags)
        #   source: UTF-8 인코딩 XSP JCL 소스 문자열
        #   flags: 0=default, 1=no_print, 2=always_print
        #   return: JSON 결과 (모든 기능 포함) - kms_xspjcl_free()로 해제
        lib.kms_xspjcl_parse_string.argtypes = [ctypes.c_char_p, ctypes.c_int]
        lib.kms_xspjcl_parse_string.restype = ctypes.c_char_p

        # const char *kms_xspjcl_parse_file(const char *file_path, int flags)
        #   파일 경로 기반 파싱 (SYSIN 포함 시 상대경로 해석 가능)
        lib.kms_xspjcl_parse_file.argtypes = [ctypes.c_char_p, ctypes.c_int]
        lib.kms_xspjcl_parse_file.restype = ctypes.c_char_p

        # void kms_xspjcl_free(void)
        #   마지막 결과 버퍼 해제
        lib.kms_xspjcl_free.argtypes = []
        lib.kms_xspjcl_free.restype = None

        # const char *kms_xspjcl_version(void)
        lib.kms_xspjcl_version.argtypes = []
        lib.kms_xspjcl_version.restype = ctypes.c_char_p

        # const char *kms_xspjcl_error_desc(int error_code)
        #   jcl_error_t enum 값 → 설명 문자열
        lib.kms_xspjcl_error_desc.argtypes = [ctypes.c_int]
        lib.kms_xspjcl_error_desc.restype = ctypes.c_char_p

        # const char *kms_xspjcl_stmt_types(void)
        #   지원 statement 타입 JSON 배열 반환
        lib.kms_xspjcl_stmt_types.argtypes = []
        lib.kms_xspjcl_stmt_types.restype = ctypes.c_char_p

    @property
    def is_available(self) -> bool:
        """C 라이브러리 사용 가능 여부."""
        return self._available

    def parse(self, source: str, flags: int = 1) -> XSPParseResult:
        """XSP JCL 소스를 C 파서로 파싱 (모든 기능).

        내부적으로 C 래퍼가 수행하는 작업:
          1. 소스를 임시 파일/메모리 스트림으로 변환
          2. xspmac_parse() 호출 — 매크로 확장 + SCF 변수 치환
          3. xspjcl_parse() 호출 — JCL 파싱 (AST 생성)
          4. jcl_tree 재귀 워킹:
             - 모든 statement (43 타입)
             - 파라미터 (P_PARAM/K_PARAM)
             - 서브파라미터 (VAL_STR/VAL_SUBPARAMS/VAL_DATA/VAL_RELEX)
             - Instream 데이터 (p_data_t → lines 배열)
             - Relational expression (relex_t → 트리 구조)
             - Line range (!!RANGE!! → [first, last])
             - 자식 statement (child_list 재귀)
          5. Stream 수집: 원본 라인 + 에러 주석
          6. 에러 수집: error_count, jcl_errno, 에러 목록

        Args:
            source: XSP JCL 소스 코드 문자열
            flags: 0=default(에러 시 출력), 1=no print, 2=always print

        Returns:
            XSPParseResult with all parser features
        """
        if not self._available or not self._lib:
            raise RuntimeError("XSP JCL C parser not available")

        source_bytes = source.encode("utf-8")
        result_ptr = self._lib.kms_xspjcl_parse_string(source_bytes, flags)

        if not result_ptr:
            raise RuntimeError("C parser returned NULL")

        try:
            result_json = result_ptr.decode("utf-8")
            data = json.loads(result_json)
            return XSPParseResult(**data)
        except (json.JSONDecodeError, UnicodeDecodeError) as e:
            raise RuntimeError(f"Failed to parse C result JSON: {e}") from e
        finally:
            self._lib.kms_xspjcl_free()

    def parse_file(self, file_path: str, flags: int = 1) -> XSPParseResult:
        """XSP JCL 파일을 C 파서로 파싱 (모든 기능).

        파일 기반 파싱은 SYSIN 포함 시 상대경로 해석이 가능하므로,
        SYSIN 문이 포함된 JCL 파싱 시에는 이 메서드를 사용할 것.

        Args:
            file_path: XSP JCL 소스 파일 경로
            flags: 파싱 플래그

        Returns:
            XSPParseResult with all parser features
        """
        if not self._available or not self._lib:
            raise RuntimeError("XSP JCL C parser not available")

        path_bytes = file_path.encode("utf-8")
        result_ptr = self._lib.kms_xspjcl_parse_file(path_bytes, flags)

        if not result_ptr:
            raise RuntimeError("C parser returned NULL")

        try:
            result_json = result_ptr.decode("utf-8")
            data = json.loads(result_json)
            return XSPParseResult(**data)
        except (json.JSONDecodeError, UnicodeDecodeError) as e:
            raise RuntimeError(f"Failed to parse C result JSON: {e}") from e
        finally:
            self._lib.kms_xspjcl_free()

    def version(self) -> str:
        """C 파서 버전 문자열."""
        if not self._available or not self._lib:
            return "unavailable"
        v = self._lib.kms_xspjcl_version()
        return v.decode("utf-8") if v else "unknown"

    def get_error_description(self, error_code: int) -> str:
        """에러 코드에 대한 설명 문자열 (jcl_strerr 래핑)."""
        if not self._available or not self._lib:
            from .models import ERROR_DESCRIPTIONS
            return ERROR_DESCRIPTIONS.get(error_code, f"Unknown error ({error_code})")
        desc = self._lib.kms_xspjcl_error_desc(error_code)
        return desc.decode("utf-8") if desc else f"Unknown error ({error_code})"

    def get_supported_stmt_types(self) -> list:
        """지원하는 statement 타입 목록 (JSON 배열)."""
        if not self._available or not self._lib:
            from .models import STMT_TYPE_DISPLAY
            return list(STMT_TYPE_DISPLAY.keys())
        raw = self._lib.kms_xspjcl_stmt_types()
        if not raw:
            return []
        try:
            return json.loads(raw.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            return []

    @classmethod
    def get_instance(cls) -> "XSPJCLCWrapper":
        """싱글턴 인스턴스 반환."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance
