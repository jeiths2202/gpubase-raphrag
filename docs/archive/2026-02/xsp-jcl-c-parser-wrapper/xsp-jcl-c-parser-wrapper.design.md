# XSP JCL C Parser Python Wrapper Design Document

> **Summary**: OF7 XSP JCL C파서(`libxspjcl`)를 ctypes로 호출하는 Python 공통모듈 상세 설계
>
> **Project**: KMS Legacy Modernization
> **Version**: 1.0
> **Author**: Claude Code
> **Date**: 2026-02-19
> **Status**: Draft
> **Planning Doc**: [xsp-jcl-c-parser-wrapper.plan.md](../../01-plan/features/xsp-jcl-c-parser-wrapper.plan.md)

---

## 1. Overview

### 1.1 Design Goals

1. OF7 C파서 (`xspjcl_parse()`)를 Python에서 직접 호출하여 100% 동일한 파싱 결과 보장
2. 기존 `JCLParser` 클래스의 XSP dialect 처리를 C 래퍼로 대체 (어댑터 패턴)
3. C 라이브러리 미존재 시 기존 Python regex 파서로 graceful fallback
4. 41개 statement 타입 전체 지원 + 에러 감지 (`\ F1` 같은 미지원 statement 탐지)

### 1.2 Design Principles

- **원본 보존**: OF7 C 소스코드 수정 최소화 (래퍼 함수만 추가)
- **느슨한 결합**: 어댑터 패턴으로 C 래퍼와 기존 Python 파서 교체 가능
- **안전한 메모리**: ctypes 호출 후 반드시 메모리 해제, tmpfile 자동 정리
- **전역 변수 보호**: C 파서의 전역 상태(`jcl_tree`, `jcl_stream`)에 대한 thread-safe wrapper

---

## 2. Architecture

### 2.1 Component Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                    Legacy Modernization                          │
│                                                                 │
│  ┌─────────────┐    ┌──────────────────────┐                   │
│  │ JCLParser    │───▶│ XSPParserAdapter     │                   │
│  │ (jcl_parser  │    │ (adapter pattern)    │                   │
│  │  .py)        │    └──────────┬───────────┘                   │
│  └─────────────┘               │                                │
│                      ┌─────────┴─────────┐                     │
│                      ▼                   ▼                      │
│            ┌──────────────┐    ┌──────────────┐                │
│            │ XSPJCLCWrapper│    │ Python Regex │                │
│            │ (wrapper.py)  │    │ (fallback)   │                │
│            └───────┬──────┘    └──────────────┘                │
│                    │ ctypes                                      │
│            ┌───────▼──────┐                                     │
│            │libxspjcl_kms │                                     │
│            │   (.so)      │                                     │
│            └──────────────┘                                     │
└─────────────────────────────────────────────────────────────────┘
```

### 2.2 Data Flow

```
XSP JCL Source (str)
    │
    ▼
XSPParserAdapter.parse(source, file_path)
    │
    ├─ C 래퍼 사용 가능? ─── No ──▶ Python regex fallback (기존 코드)
    │
    Yes
    │
    ▼
XSPJCLCWrapper.parse(source)
    │
    ├─ 1. source → tmpfile 생성 (tempfile.NamedTemporaryFile)
    ├─ 2. kms_xspjcl_parse(tmpfile_path) 호출 [C]
    │      ├─ fopen(path) → xspjcl_parse(flags, fp) → jcl_tree 생성
    │      ├─ tree 순회 → JSON 문자열 생성
    │      └─ JSON 반환 (char*)
    ├─ 3. JSON → XSPParseResult (Python)
    ├─ 4. kms_xspjcl_free() 호출 [C] (메모리 해제)
    └─ 5. tmpfile 삭제
    │
    ▼
XSPParseResult
    │
    ▼
ResultConverter.to_parser_result(xsp_result, file_path)
    │
    ├─ XSPStatement → NormalizedFeature 변환
    ├─ XSPStatement → ASTNode 변환
    ├─ XSPError → ParseError 변환
    └─ stats 계산
    │
    ▼
ParserResult (기존 모델과 동일한 출력)
```

### 2.3 Dependencies

| Component | Depends On | Purpose |
|-----------|-----------|---------|
| `XSPJCLCWrapper` | `libxspjcl_kms.so` | C 파서 공유 라이브러리 |
| `XSPParserAdapter` | `XSPJCLCWrapper`, `JCLParser` | C/Python 전환 |
| `ResultConverter` | `base.py` models | C 결과 → Python 모델 변환 |
| `libxspjcl_kms.so` | `xspjcl_*.c`, stub headers | OF7 파서 소스 |

---

## 3. Data Model

### 3.1 C 파서 출력 구조체 (참조)

```c
// OF7/base/include/jclcom.h
struct jclcom_stmt_s {
    int type;                     // xspjcl_stmt_type_t enum
    char *name;                   // statement name
    jclcom_param_t *param_list;   // linked list of parameters
    jclcom_stmt_t *child_list;    // linked list of child statements
    link_t child_link;            // circular linked list link
    int lineno;                   // line number (1-based, 0=N/A)
    char lineno_str[513];         // for XSP macro
};

struct jclcom_tree_s {
    jclcom_stmt_t *job_list;      // root: list of JOB statements
};
```

### 3.2 JSON 출력 포맷 (C → Python 전달용)

```json
{
  "success": true,
  "error_count": 0,
  "statements": [
    {
      "type": "STMT_JOB",
      "type_str": "\\ JOB",
      "name": "HAIBNFTP",
      "lineno": 3,
      "params": [
        {"keyword": "HAIBNFTP", "value": null, "position": 0}
      ],
      "children": [
        {
          "type": "STMT_EX",
          "type_str": "\\ EX",
          "name": null,
          "lineno": 5,
          "params": [
            {"keyword": null, "value": "KEQEFT01", "position": 0},
            {"keyword": "RSIZE", "value": "4096", "position": 1},
            {"keyword": "COND", "value": "10", "position": 2}
          ],
          "children": [
            {
              "type": "STMT_FD",
              "type_str": "\\ FD",
              "name": "SYSTSPRT",
              "lineno": 6,
              "params": [
                {"keyword": "SYSTSPRT", "value": "DA", "position": 0},
                {"keyword": "SOUT", "value": "A", "position": 1}
              ],
              "children": []
            }
          ]
        }
      ]
    }
  ],
  "errors": [
    {
      "lineno": 8,
      "error_code": 3,
      "message": "Unknown JCL Operation Field",
      "line_text": "\\ F1 ..."
    }
  ],
  "stream": [
    {"lineno": 1, "text": "/EXPAN DEFINE HAIBNFTP,DAY="},
    {"lineno": 2, "text": ""},
    {"lineno": 3, "text": "\\ JOB  HAIBNFTP"}
  ]
}
```

### 3.3 Python 데이터 모델

```python
# xspjcl/models.py

from typing import List, Optional
from pydantic import BaseModel, Field


class XSPParam(BaseModel):
    """XSP JCL statement 파라미터."""
    keyword: Optional[str] = None
    value: Optional[str] = None
    position: int = 0


class XSPStatement(BaseModel):
    """C 파서에서 추출한 XSP JCL statement."""
    type: str          # "STMT_JOB", "STMT_EX", "MSTMT_SET", etc.
    type_str: str      # "\\ JOB", "\\ EX", "/ SET", etc.
    name: Optional[str] = None
    lineno: int = 0
    params: List[XSPParam] = Field(default_factory=list)
    children: List["XSPStatement"] = Field(default_factory=list)


class XSPParseError(BaseModel):
    """C 파서에서 감지한 에러."""
    lineno: int
    error_code: int
    message: str
    line_text: str = ""


class XSPStreamEntry(BaseModel):
    """원본 라인 + 에러 매핑."""
    lineno: int
    text: str


class XSPParseResult(BaseModel):
    """C 파서 전체 결과."""
    success: bool
    error_count: int = 0
    statements: List[XSPStatement] = Field(default_factory=list)
    errors: List[XSPParseError] = Field(default_factory=list)
    stream: List[XSPStreamEntry] = Field(default_factory=list)
```

### 3.4 Statement Type → FeatureCategory 매핑

| C Type Enum | type_str | FeatureCategory | subcategory |
|-------------|----------|-----------------|-------------|
| STMT_JOB | `\ JOB` | JOB_CARD | JOB |
| STMT_EX | `\ EX` | EXEC_STEP / UTILITY | PGM |
| STMT_FD | `\ FD` | DD_STATEMENT / DATASET | DD |
| STMT_JEND | `\ JEND` | XSP_CONTROL | JEND |
| STMT_MSG | `\ MSG` | XSP_CONTROL | MSG |
| STMT_JOBG | `\ JOBG` | XSP_CONTROL | JOBG |
| STMT_CODE | `\ CODE` | XSP_CONTROL | CODE |
| STMT_PARA | `\ PARA` | XSP_CONTROL | PARA |
| STMT_SW | `\ SW` | XSP_CONTROL | SW |
| STMT_PAUSE | `\ PAUSE` | XSP_CONTROL | PAUSE |
| STMT_NOTE | `\ NOTE` | XSP_CONTROL | NOTE |
| STMT_JGEND | `\ JGEND` | XSP_CONTROL | JGEND |
| STMT_FIN | `\ FIN` | XSP_CONTROL | FIN |
| STMT_SYSIN | `\ SYSIN` | XSP_CONTROL | SYSIN |
| STMT_EX_MACRO | `\ EX_MACRO` | XSP_CONTROL | EX_MACRO |
| STMT_CHAM | `\ CHAM` | XSP_CONTROL | CHAM |
| STMT_MACRO | `\ MACRO` | PROCEDURE | MACRO |
| STMT_MEND | `\ MEND` | PROCEDURE | MEND |
| STMT_FDR | `\ FDR` | DD_STATEMENT | FDR |
| STMT_FDDS | `\ FDDS` | DD_STATEMENT | FDDS |
| STMT_FDDE | `\ FDDE` | DD_STATEMENT | FDDE |
| STMT_STACK | `\ STACK` | XSP_CONTROL | STACK |
| STMT_CAT | `\ CAT` | XSP_CONTROL | CAT |
| STMT_UNCAT | `\ UNCAT` | XSP_CONTROL | UNCAT |
| STMT_DATA | `\ DATA` | XSP_CONTROL | DATA |
| STMT_END | `\ END` | XSP_CONTROL | END |
| STMT_COMMAND | `\ COMMAND` | XSP_CONTROL | COMMAND |
| STMT_JALT | `\ JALT` | XSP_CONTROL | JALT |
| STMT_SCAN | `\ SCAN` | XSP_CONTROL | SCAN |
| STMT_SCEND | `\ SCEND` | XSP_CONTROL | SCEND |
| MSTMT_DEFINE | `/ DEFINE` | XSP_CONTROL | DEFINE |
| MSTMT_SKIP | `/ SKIP` | XSP_CONTROL | SKIP |
| MSTMT_IF | `/ IF` | CONDITIONAL | IF |
| MSTMT_IFN | `/ IFN` | CONDITIONAL | IFN |
| MSTMT_SET | `/ SET` | XSP_CONTROL | SET |
| MSTMT_MSG | `/ MSG` | XSP_CONTROL | MACRO_MSG |
| MSTMT_WTO | `/ WTO` | XSP_CONTROL | WTO |
| MSTMT_WTOR | `/ WTOR` | XSP_CONTROL | WTOR |
| MSTMT_NOP | `/ NOP` | XSP_CONTROL | MACRO_NOP |
| MSTMT_DEXIT | `/ DEXIT` | XSP_CONTROL | DEXIT |
| MSTMT_DEFEND | `/ DEFEND` | XSP_CONTROL | DEFEND |

---

## 4. C 래퍼 함수 설계

### 4.1 KMS 확장 C 소스 (`kms_xspjcl_wrapper.c`)

OF7 원본 소스를 수정하지 않고, 별도의 래퍼 C 파일을 추가한다.

```c
/**
 * @file    kms_xspjcl_wrapper.c
 * @brief   KMS Python용 xspjcl 래퍼 함수
 *
 * OF7 xspjcl 파서를 Python ctypes에서 호출하기 위한 C 래퍼.
 * 내부적으로 xspjcl_parse()를 호출하고 결과를 JSON으로 변환.
 */

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "jclcom.h"
#include "xspjcl.h"
#include "xspjcl_inner.h"

/* JSON 버퍼 크기 */
#define KMS_JSON_BUF_INIT  (64 * 1024)   /* 64KB initial */
#define KMS_JSON_BUF_MAX   (16 * 1024 * 1024)  /* 16MB max */

/* 전역 결과 버퍼 (thread 단위 재사용) */
static char *g_json_result = NULL;
static int   g_json_result_size = 0;

/**
 * kms_xspjcl_parse - XSP JCL 소스 파일을 파싱하고 JSON 결과 반환.
 *
 * @param file_path  XSP JCL 소스 파일 경로
 * @param flags      파싱 플래그 (0=default, 1=no print, 2=always print)
 * @return           JSON 문자열 (caller가 kms_xspjcl_free()로 해제)
 *                   실패 시 에러 JSON 반환
 */
const char *kms_xspjcl_parse(const char *file_path, int flags);

/**
 * kms_xspjcl_parse_string - 문자열에서 직접 파싱.
 *
 * @param source     XSP JCL 소스 문자열
 * @param flags      파싱 플래그
 * @return           JSON 문자열
 */
const char *kms_xspjcl_parse_string(const char *source, int flags);

/**
 * kms_xspjcl_free - 파싱 결과 메모리 해제.
 */
void kms_xspjcl_free(void);

/**
 * kms_xspjcl_version - 버전 문자열 반환.
 */
const char *kms_xspjcl_version(void);
```

### 4.2 JSON 생성 로직 (C 내부)

```c
/* tree 순회 → JSON 변환 핵심 함수 */

static void stmt_to_json(char **buf, int *pos, int *size,
                         jclcom_stmt_t *stmt, int depth);
static void param_to_json(char **buf, int *pos, int *size,
                          jclcom_param_t *param);

const char *
kms_xspjcl_parse_string(const char *source, int flags)
{
    FILE *fp;
    int rc;

    /* 1. 임시 파일 생성 */
    fp = tmpfile();
    if (!fp) return "{\"success\":false,\"error_count\":1,"
                     "\"errors\":[{\"message\":\"tmpfile() failed\"}]}";
    fputs(source, fp);
    rewind(fp);

    /* 2. OF7 파서 호출 */
    rc = xspjcl_parse(flags, fp);
    fclose(fp);

    /* 3. 결과 JSON 생성 */
    /* g_json_result에 JSON 문자열 축적 */
    json_buf_init();
    json_append("{\"success\":%s,\"error_count\":%d,",
                rc == 0 ? "true" : "false",
                jcl_stream_check_error());

    /* statements */
    json_append("\"statements\":[");
    if (jcl_tree.job_list) {
        jclcom_stmt_t *job = list_first(jcl_tree.job_list, ...);
        /* 순회하며 stmt_to_json() 호출 */
    }
    json_append("],");

    /* errors */
    json_append("\"errors\":[");
    /* jcl_stream.error[] 순회 */
    json_append("],");

    /* stream */
    json_append("\"stream\":[");
    /* jcl_stream.stmt_string[] 순회 */
    json_append("]}");

    return g_json_result;
}
```

### 4.3 의존 라이브러리 Stub 설계

OF7 빌드 시스템 없이 독립 빌드하기 위해 stub을 생성한다.

| 라이브러리 | 필요 함수 | Stub 전략 |
|-----------|----------|----------|
| `libofcom` | `OFCOM_MSG_FPRINTF2` | `#define` 매크로로 stderr fprintf 대체 |
| `libjclcom` | `jclcom_param_new`, `jclcom_param_list_add`, `jclcom_print_fmt`, `list_first/next/last` | OF7 소스에서 해당 함수만 추출 |
| `libxspmac` | `xspmac_*` (매크로 확장) | 최소 stub (매크로 파싱 미지원 시 no-op) |
| `libams` | AMS catalog 관련 | 최소 stub (no-op) |

```
lib/stubs/
├── ofcom_stub.h      # OFCOM_MSG_FPRINTF → fprintf(stderr, ...)
├── jclcom_funcs.c    # jclcom.h 구현 중 필요 함수만 추출
├── xspmac_stub.c     # 매크로 확장 stub (no-op)
└── ams_stub.c        # AMS catalog stub (no-op)
```

---

## 5. Python ctypes 래퍼 설계

### 5.1 `wrapper.py` — C 라이브러리 로드 및 호출

```python
"""OF7 XSP JCL C 파서 ctypes 래퍼."""

import ctypes
import json
import logging
import os
import sys
import tempfile
from pathlib import Path
from typing import Optional

from .models import XSPParseResult

logger = logging.getLogger(__name__)

# 라이브러리 검색 순서
_LIB_SEARCH_PATHS = [
    # 1. 환경변수
    os.environ.get("XSPJCL_LIB_PATH", ""),
    # 2. 패키지 내 lib/
    str(Path(__file__).parent / "lib" / "libxspjcl_kms.so"),
    # 3. 시스템 경로
    "libxspjcl_kms.so",
]


class XSPJCLCWrapper:
    """OF7 xspjcl C 파서 ctypes 래퍼 (싱글턴)."""

    _instance: Optional["XSPJCLCWrapper"] = None

    def __init__(self) -> None:
        self._lib: Optional[ctypes.CDLL] = None
        self._available = False
        self._load_library()

    def _load_library(self) -> None:
        """공유 라이브러리 로드 시도."""
        for path in _LIB_SEARCH_PATHS:
            if not path:
                continue
            try:
                lib = ctypes.CDLL(path)
                self._setup_functions(lib)
                self._lib = lib
                self._available = True
                logger.info("XSP JCL C parser loaded: %s", path)
                return
            except (OSError, AttributeError) as e:
                logger.debug("Failed to load %s: %s", path, e)
                continue
        logger.warning("XSP JCL C parser not available (fallback to Python)")

    def _setup_functions(self, lib: ctypes.CDLL) -> None:
        """C 함수 시그니처 설정."""
        # const char *kms_xspjcl_parse(const char *file_path, int flags)
        lib.kms_xspjcl_parse.argtypes = [ctypes.c_char_p, ctypes.c_int]
        lib.kms_xspjcl_parse.restype = ctypes.c_char_p

        # const char *kms_xspjcl_parse_string(const char *source, int flags)
        lib.kms_xspjcl_parse_string.argtypes = [ctypes.c_char_p, ctypes.c_int]
        lib.kms_xspjcl_parse_string.restype = ctypes.c_char_p

        # void kms_xspjcl_free(void)
        lib.kms_xspjcl_free.argtypes = []
        lib.kms_xspjcl_free.restype = None

        # const char *kms_xspjcl_version(void)
        lib.kms_xspjcl_version.argtypes = []
        lib.kms_xspjcl_version.restype = ctypes.c_char_p

    @property
    def is_available(self) -> bool:
        return self._available

    def parse(self, source: str, flags: int = 0) -> XSPParseResult:
        """XSP JCL 소스를 C 파서로 파싱.

        Args:
            source: XSP JCL 소스 코드 문자열
            flags: 0=default, 1=no print, 2=always print

        Returns:
            XSPParseResult 모델

        Raises:
            RuntimeError: C 라이브러리 미로드 또는 파싱 실패
        """
        if not self._available or not self._lib:
            raise RuntimeError("XSP JCL C parser not available")

        # C 파서 호출 (문자열 직접 전달)
        source_bytes = source.encode("utf-8")
        result_ptr = self._lib.kms_xspjcl_parse_string(source_bytes, flags)

        if not result_ptr:
            raise RuntimeError("C parser returned NULL")

        try:
            result_json = result_ptr.decode("utf-8")
            data = json.loads(result_json)
            return XSPParseResult(**data)
        except (json.JSONDecodeError, UnicodeDecodeError) as e:
            raise RuntimeError(f"Failed to parse C result: {e}") from e
        finally:
            # 메모리 해제
            self._lib.kms_xspjcl_free()

    def version(self) -> str:
        """C 파서 버전 문자열."""
        if not self._available or not self._lib:
            return "unavailable"
        v = self._lib.kms_xspjcl_version()
        return v.decode("utf-8") if v else "unknown"

    @classmethod
    def get_instance(cls) -> "XSPJCLCWrapper":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance
```

### 5.2 `converter.py` — C 결과 → 기존 모델 변환

```python
"""XSPParseResult → ParserResult 변환기."""

from typing import List, Optional

from ..base import (
    ASTNode, NormalizedFeature, ParseError, ParseStats,
    ParserResult, SourceReference, TraceEvidence,
)
from ..models.enums import AssetType, ComplexityLevel, FeatureCategory
from .models import XSPParseResult, XSPStatement


# Statement type → (FeatureCategory, subcategory, complexity) 매핑
_STMT_FEATURE_MAP = {
    "STMT_JOB":    (FeatureCategory.JOB_CARD,     "JOB",      ComplexityLevel.LOW),
    "STMT_EX":     (FeatureCategory.EXEC_STEP,     "PGM",      ComplexityLevel.MEDIUM),
    "STMT_FD":     (FeatureCategory.DD_STATEMENT,   "DD",       ComplexityLevel.LOW),
    "STMT_JEND":   (FeatureCategory.XSP_CONTROL,   "JEND",     ComplexityLevel.LOW),
    "STMT_MSG":    (FeatureCategory.XSP_CONTROL,   "MSG",      ComplexityLevel.MEDIUM),
    "STMT_JOBG":   (FeatureCategory.XSP_CONTROL,   "JOBG",     ComplexityLevel.MEDIUM),
    "STMT_CODE":   (FeatureCategory.XSP_CONTROL,   "CODE",     ComplexityLevel.MEDIUM),
    "STMT_PARA":   (FeatureCategory.XSP_CONTROL,   "PARA",     ComplexityLevel.LOW),
    "STMT_SW":     (FeatureCategory.XSP_CONTROL,   "SW",       ComplexityLevel.MEDIUM),
    "STMT_PAUSE":  (FeatureCategory.XSP_CONTROL,   "PAUSE",    ComplexityLevel.LOW),
    "STMT_NOTE":   (FeatureCategory.XSP_CONTROL,   "NOTE",     ComplexityLevel.LOW),
    "STMT_JGEND":  (FeatureCategory.XSP_CONTROL,   "JGEND",    ComplexityLevel.LOW),
    "STMT_FIN":    (FeatureCategory.XSP_CONTROL,   "FIN",      ComplexityLevel.LOW),
    "STMT_SYSIN":  (FeatureCategory.XSP_CONTROL,   "SYSIN",    ComplexityLevel.MEDIUM),
    "STMT_EX_MACRO": (FeatureCategory.XSP_CONTROL, "EX_MACRO", ComplexityLevel.HIGH),
    "STMT_CHAM":   (FeatureCategory.XSP_CONTROL,   "CHAM",     ComplexityLevel.HIGH),
    "STMT_MACRO":  (FeatureCategory.PROCEDURE,     "MACRO",    ComplexityLevel.HIGH),
    "STMT_MEND":   (FeatureCategory.PROCEDURE,     "MEND",     ComplexityLevel.LOW),
    "STMT_FDR":    (FeatureCategory.DD_STATEMENT,   "FDR",      ComplexityLevel.MEDIUM),
    "STMT_FDDS":   (FeatureCategory.DD_STATEMENT,   "FDDS",     ComplexityLevel.MEDIUM),
    "STMT_FDDE":   (FeatureCategory.DD_STATEMENT,   "FDDE",     ComplexityLevel.MEDIUM),
    "STMT_STACK":  (FeatureCategory.XSP_CONTROL,   "STACK",    ComplexityLevel.MEDIUM),
    "STMT_CAT":    (FeatureCategory.XSP_CONTROL,   "CAT",      ComplexityLevel.MEDIUM),
    "STMT_UNCAT":  (FeatureCategory.XSP_CONTROL,   "UNCAT",    ComplexityLevel.MEDIUM),
    "STMT_DATA":   (FeatureCategory.XSP_CONTROL,   "DATA",     ComplexityLevel.LOW),
    "STMT_END":    (FeatureCategory.XSP_CONTROL,   "END",      ComplexityLevel.LOW),
    "STMT_COMMAND":(FeatureCategory.XSP_CONTROL,   "COMMAND",  ComplexityLevel.HIGH),
    "STMT_JALT":   (FeatureCategory.XSP_CONTROL,   "JALT",     ComplexityLevel.HIGH),
    "STMT_SCAN":   (FeatureCategory.XSP_CONTROL,   "SCAN",     ComplexityLevel.MEDIUM),
    "STMT_SCEND":  (FeatureCategory.XSP_CONTROL,   "SCEND",    ComplexityLevel.LOW),
    # JCM macro statements
    "MSTMT_DEFINE":(FeatureCategory.XSP_CONTROL,   "DEFINE",   ComplexityLevel.MEDIUM),
    "MSTMT_SKIP":  (FeatureCategory.XSP_CONTROL,   "SKIP",     ComplexityLevel.LOW),
    "MSTMT_IF":    (FeatureCategory.CONDITIONAL,   "IF",       ComplexityLevel.MEDIUM),
    "MSTMT_IFN":   (FeatureCategory.CONDITIONAL,   "IFN",      ComplexityLevel.MEDIUM),
    "MSTMT_SET":   (FeatureCategory.XSP_CONTROL,   "SET",      ComplexityLevel.LOW),
    "MSTMT_MSG":   (FeatureCategory.XSP_CONTROL,   "MACRO_MSG",ComplexityLevel.LOW),
    "MSTMT_WTO":   (FeatureCategory.XSP_CONTROL,   "WTO",      ComplexityLevel.MEDIUM),
    "MSTMT_WTOR":  (FeatureCategory.XSP_CONTROL,   "WTOR",     ComplexityLevel.MEDIUM),
    "MSTMT_NOP":   (FeatureCategory.XSP_CONTROL,   "MACRO_NOP",ComplexityLevel.LOW),
    "MSTMT_DEXIT": (FeatureCategory.XSP_CONTROL,   "DEXIT",    ComplexityLevel.MEDIUM),
    "MSTMT_DEFEND":(FeatureCategory.XSP_CONTROL,   "DEFEND",   ComplexityLevel.LOW),
}

UTILITY_PROGRAMS = {
    "IDCAMS", "IEBGENER", "IEBCOPY", "IEFBR14", "DFSORT", "SORT",
    "ICETOOL", "IKJEFT01", "IRXJCL", "IEFPROC", "ADRDSSU",
    "DSMIGIN", "DSMIGOUT", "KEQEFT01",
}


class ResultConverter:
    """XSPParseResult → ParserResult 변환."""

    def to_parser_result(
        self, xsp_result: XSPParseResult, source: str, file_path: str,
    ) -> ParserResult:
        features = []
        counter = 0
        for stmt in xsp_result.statements:
            counter = self._extract_features(stmt, file_path, features, counter)

        ast = self._build_ast(xsp_result.statements, file_path, source)
        evidence = self._build_evidence(features, source, file_path)
        errors = [
            ParseError(
                line=e.lineno, column=0,
                message=e.message, severity="error",
            )
            for e in xsp_result.errors
        ]

        lines = source.splitlines()
        stats = ParseStats(
            total_lines=len(lines),
            code_lines=sum(1 for l in lines if l.strip() and not l.strip().startswith("\\*")),
            comment_lines=sum(1 for l in lines if l.strip().startswith("\\*")),
            blank_lines=sum(1 for l in lines if not l.strip()),
            feature_count=len(features),
            dialect="xsp",
        )

        return ParserResult(
            asset_type=AssetType.JCL,
            dialect="xsp",
            ast=ast,
            features=features,
            trace_evidence=evidence,
            parse_errors=errors,
            stats=stats,
        )

    def _extract_features(
        self, stmt: XSPStatement, file_path: str,
        features: list, counter: int,
    ) -> int:
        """단일 statement를 NormalizedFeature로 변환 (재귀)."""
        mapping = _STMT_FEATURE_MAP.get(stmt.type)
        if mapping:
            counter += 1
            category, subcategory, complexity = mapping

            # EX statement: PGM 이름 추출, utility 판별
            name = stmt.type_str
            if stmt.type == "STMT_EX" and stmt.params:
                pgm_name = stmt.params[0].value or stmt.name or ""
                pgm_upper = pgm_name.upper()
                if pgm_upper in UTILITY_PROGRAMS:
                    category = FeatureCategory.UTILITY
                name = f"PGM={pgm_upper}" if pgm_upper else stmt.type_str

            # FD statement: DD name 추출
            elif stmt.type == "STMT_FD":
                dd_name = stmt.name or (stmt.params[0].keyword if stmt.params else "")
                name = f"DD {dd_name}" if dd_name else stmt.type_str

            # JOB statement
            elif stmt.type == "STMT_JOB":
                job_name = stmt.name or "UNNAMED"
                name = f"JOB {job_name}"

            else:
                name = stmt.type_str
                if stmt.name:
                    name = f"{stmt.type_str} {stmt.name}"

            features.append(NormalizedFeature(
                feature_id=f"JCL-XSP-{counter:03d}",
                category=category,
                subcategory=subcategory,
                name=name,
                source_reference=SourceReference(
                    file_path=file_path,
                    line_start=stmt.lineno,
                    line_end=stmt.lineno,
                ),
                complexity=complexity,
            ))

        # 재귀: 자식 statements
        for child in stmt.children:
            counter = self._extract_features(child, file_path, features, counter)

        return counter

    def _build_ast(
        self, statements: list, file_path: str, source: str,
    ) -> ASTNode:
        """XSPStatement 리스트 → ASTNode 트리."""
        children = [self._stmt_to_ast(s) for s in statements]
        lines = source.splitlines()
        return ASTNode(
            node_type="JCL_FILE",
            name=file_path,
            source_line=1,
            source_end_line=len(lines),
            children=children,
        )

    def _stmt_to_ast(self, stmt: XSPStatement) -> ASTNode:
        """단일 XSPStatement → ASTNode (재귀)."""
        return ASTNode(
            node_type=stmt.type_str.replace("\\ ", "").replace("/ ", ""),
            name=stmt.name,
            source_line=stmt.lineno,
            source_end_line=stmt.lineno,
            children=[self._stmt_to_ast(c) for c in stmt.children],
            properties={
                "params": [
                    {"keyword": p.keyword, "value": p.value}
                    for p in stmt.params
                ],
            },
        )

    def _build_evidence(
        self, features: list, source: str, file_path: str,
    ) -> list:
        lines = source.splitlines()
        evidence = []
        for feat in features:
            idx = feat.source_reference.line_start - 1
            raw = lines[idx] if 0 <= idx < len(lines) else ""
            evidence.append(TraceEvidence(
                ast_node_path=f"/JCL/{feat.category.value}/{feat.feature_id}",
                source_file=file_path,
                source_lines=(feat.source_reference.line_start,
                             feat.source_reference.line_end),
                raw_source=raw.rstrip(),
                confidence=1.0,  # C parser = high confidence
            ))
        return evidence
```

### 5.3 `__init__.py` — XSPParserAdapter (진입점)

```python
"""XSP JCL C Parser Python wrapper package."""

from typing import Optional

from ..base import ParserResult
from .wrapper import XSPJCLCWrapper
from .converter import ResultConverter
from .models import XSPParseResult


class XSPParserAdapter:
    """XSP JCL 파서 어댑터.

    C 래퍼 사용 가능 시 C 파서 호출, 불가 시 Python fallback.
    """

    def __init__(self) -> None:
        self._c_wrapper = XSPJCLCWrapper.get_instance()
        self._converter = ResultConverter()

    @property
    def using_c_parser(self) -> bool:
        return self._c_wrapper.is_available

    async def parse(self, source: str, file_path: str) -> ParserResult:
        """XSP JCL 소스 파싱.

        C 파서 사용 가능 시 C 호출, 불가 시 None 반환 (caller가 fallback).
        """
        if not self._c_wrapper.is_available:
            return None  # caller가 Python fallback 수행

        try:
            xsp_result = self._c_wrapper.parse(source, flags=1)  # no print
            return self._converter.to_parser_result(xsp_result, source, file_path)
        except RuntimeError as e:
            import logging
            logging.getLogger(__name__).warning(
                "C parser failed, falling back: %s", e
            )
            return None  # fallback


def get_xsp_parser_adapter() -> XSPParserAdapter:
    """싱글턴 어댑터 인스턴스."""
    return XSPParserAdapter()
```

---

## 6. JCLParser 통합 설계

### 6.1 `jcl_parser.py` 수정 포인트

```python
# jcl_parser.py 상단에 추가
from .xspjcl import XSPParserAdapter

class JCLParser(BaseParser):

    def __init__(self):
        self._xsp_adapter = XSPParserAdapter()

    async def parse(self, source: str, file_path: str) -> ParserResult:
        # dialect 감지
        dialect = await self.detect_dialect(source)

        # XSP dialect + C 래퍼 사용 가능 → C 파서 위임
        if dialect == "xsp" and self._xsp_adapter.using_c_parser:
            result = await self._xsp_adapter.parse(source, file_path)
            if result is not None:
                return result
            # C 파서 실패 시 아래 Python fallback으로 진행

        # 기존 Python 파서 로직 (MVS/JES2/JES3 + XSP fallback)
        lines = self._preprocess_continuation(source)
        ast = self._build_ast(lines, file_path)
        features = self._extract_features(lines, file_path)
        evidence = self._build_trace_evidence(features, source, file_path)
        stats = self._compute_stats(source.splitlines(), features, dialect)

        return ParserResult(
            asset_type=AssetType.JCL,
            dialect=dialect,
            ast=ast,
            features=features,
            trace_evidence=evidence,
            stats=stats,
        )
```

---

## 7. 빌드 시스템 설계

### 7.1 독립 Makefile

```makefile
# app/api/legacy_modernization/parsers/xspjcl/lib/Makefile

CC = gcc
CFLAGS = -fPIC -shared -O2 -Wall
INCLUDES = -I$(OF7_SRC)/base/include \
           -I$(OF7_SRC)/base/jcl/include \
           -Istubs

# OF7 소스 (읽기 전용 참조)
OF7_SRC ?= $(CURDIR)/../../../../../../../OF7

# 소스 파일
SOURCES = \
    $(OF7_SRC)/base/parser/xspjcl/xspjcl_grammar.c \
    $(OF7_SRC)/base/parser/xspjcl/xspjcl_scanner.c \
    $(OF7_SRC)/base/parser/xspjcl/xspjcl_error.c \
    $(OF7_SRC)/base/parser/xspjcl/xspjcl_util.c \
    $(OF7_SRC)/base/parser/xspjcl/xspjcl_stream.c \
    $(OF7_SRC)/base/parser/xspjcl/xspjcl_keyword.c \
    $(OF7_SRC)/base/parser/xspjcl/xspjcl_version.c \
    stubs/jclcom_funcs.c \
    stubs/ofcom_stub.c \
    stubs/xspmac_stub.c \
    stubs/ams_stub.c \
    kms_xspjcl_wrapper.c

TARGET = libxspjcl_kms.so

DEFINES = -D_XSPJCL_MODULE -DXSP_TJES -D_XSP_VERSION -DKMS_STANDALONE

.PHONY: all clean

all: $(TARGET)

$(TARGET): $(SOURCES)
	$(CC) $(CFLAGS) $(DEFINES) $(INCLUDES) -o $@ $^

clean:
	rm -f $(TARGET)
```

### 7.2 빌드 스크립트 (`build.sh`)

```bash
#!/bin/bash
# app/api/legacy_modernization/parsers/xspjcl/lib/build.sh
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
OF7_SRC="${SCRIPT_DIR}/../../../../../../../OF7"

echo "=== Building libxspjcl_kms.so ==="
echo "OF7 source: ${OF7_SRC}"

# 의존성 확인
for cmd in gcc flex bison; do
    if ! command -v $cmd &>/dev/null; then
        echo "ERROR: $cmd not found. Install with: sudo yum install $cmd"
        exit 1
    fi
done

# 빌드
cd "$SCRIPT_DIR"
make OF7_SRC="$OF7_SRC"

echo "=== Build complete: $(pwd)/libxspjcl_kms.so ==="
ls -la libxspjcl_kms.so
```

---

## 8. Error Handling

### 8.1 C 파서 에러 코드

| Code | Enum | Message | Python 처리 |
|------|------|---------|------------|
| 0 | JCL_ERROR_OK | No error | success=true |
| 1 | SCAN_ERROR | Scan error | ParseError 생성 |
| 2 | SCAN_ERROR_UNEXPECTED_INPUT | Unexpected JCL input | ParseError 생성 |
| 3 | SCAN_ERROR_UNKNOWN_OPERATION_FIELD | Unknown JCL Operation Field | ParseError + `\ F1` 등 감지 |
| 7 | SCAN_ERROR_NOT_SUPPORTED_STATEMENT | Not supported statement | ParseError 생성 |
| 8 | SCAN_ERROR_UNKNOWN_MACRO_STATEMENT | Unknown MACRO statement | ParseError 생성 |
| 14 | PARSE_ERROR | Parse error | ParseError 생성 |
| 15 | PARSE_ERROR_NO_JOB_IN_JOBG | No JOB in JOBG | ParseError 생성 |
| 16 | PARSE_ERROR_NO_STMT_IN_JOB | No statement in JOB | ParseError 생성 |

### 8.2 Python 측 에러 처리

```python
# 에러 분류 및 처리 전략
class XSPErrorClassifier:
    @staticmethod
    def classify(error: XSPParseError) -> str:
        """에러 심각도 분류."""
        if error.error_code <= 0:
            return "info"
        elif error.error_code < 14:  # SCAN errors
            return "warning"
        else:  # PARSE/EXEC errors
            return "error"
```

---

## 9. Test Plan

### 9.1 Test Scope

| Type | Target | Tool |
|------|--------|------|
| Unit Test | `ResultConverter` 변환 로직 | pytest |
| Integration Test | C 래퍼 → Python 변환 전체 | pytest + libxspjcl_kms.so |
| Comparison Test | C 파서 vs Python 파서 결과 동일성 | pytest |
| Error Test | `\ F1` 등 에러 케이스 감지 | pytest |

### 9.2 Test Cases

- [ ] Happy path: TESTJCL00 파싱 → 8개 feature 추출, 0 에러
- [ ] Error case: TESTJCL01 (`\ F1`) 파싱 → ParseError 포함, error_code=3
- [ ] All statements: 41개 statement 타입 각각 포함한 테스트 파일 파싱
- [ ] Fallback: C 라이브러리 없을 때 Python regex 파서로 자동 전환
- [ ] Memory: 대용량 XSP JCL (1000줄+) 파싱 후 메모리 누수 없음
- [ ] Thread safety: 동시 파싱 요청 시 결과 혼선 없음

### 9.3 Test 데이터

| 파일 | 목적 | 기대 결과 |
|------|------|----------|
| `temp/assets/XSP/src/TESTJCL00` | 정상 XSP JCL | 7 FULL + 1 PARTIAL |
| `temp/assets/XSP/src/TESTJCL01` | `\ F1` 에러 포함 | ParseError(code=3) |
| (신규) `test_all_statements.xsp` | 41개 statement 전체 | 41 features |

---

## 10. Implementation Order

### 10.1 Phase 순서

```
Phase 1: C 빌드 인프라 (2일)
├── 1.1 stub 헤더/소스 생성
├── 1.2 kms_xspjcl_wrapper.c 작성
├── 1.3 Makefile + build.sh 작성
└── 1.4 서버에서 빌드 검증

Phase 2: Python 래퍼 모듈 (1일)
├── 2.1 xspjcl/models.py
├── 2.2 xspjcl/wrapper.py
├── 2.3 xspjcl/converter.py
└── 2.4 xspjcl/__init__.py (XSPParserAdapter)

Phase 3: JCLParser 통합 (0.5일)
├── 3.1 jcl_parser.py 수정 (XSP → C 래퍼 위임)
└── 3.2 기존 Python fallback 유지

Phase 4: 테스트 (1일)
├── 4.1 단위 테스트 (converter, models)
├── 4.2 통합 테스트 (C 래퍼 ↔ Python)
├── 4.3 비교 테스트 (C vs Python 결과)
└── 4.4 에러 케이스 테스트
```

### 10.2 파일 생성/수정 목록

| Action | File | Description |
|--------|------|-------------|
| CREATE | `parsers/xspjcl/__init__.py` | XSPParserAdapter export |
| CREATE | `parsers/xspjcl/wrapper.py` | ctypes C 라이브러리 래퍼 |
| CREATE | `parsers/xspjcl/models.py` | XSPParseResult 등 Pydantic 모델 |
| CREATE | `parsers/xspjcl/converter.py` | C 결과 → NormalizedFeature 변환 |
| CREATE | `parsers/xspjcl/lib/kms_xspjcl_wrapper.c` | C 래퍼 함수 |
| CREATE | `parsers/xspjcl/lib/Makefile` | 독립 빌드 |
| CREATE | `parsers/xspjcl/lib/build.sh` | 빌드 스크립트 |
| CREATE | `parsers/xspjcl/lib/stubs/` | 의존 라이브러리 stub |
| MODIFY | `parsers/jcl_parser.py` | XSP dialect → C 래퍼 위임 |

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-02-19 | Initial draft | Claude Code |
