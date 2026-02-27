# XSP JCL C Parser Python Wrapper Planning Document

> **Summary**: OF7 XSP JCL C파서를 Python에서 직접 호출하는 공통모듈 생성
>
> **Project**: KMS Legacy Modernization
> **Version**: 1.0
> **Author**: Claude Code
> **Date**: 2026-02-19
> **Status**: Draft

---

## 1. Overview

### 1.1 Purpose

현재 Python 기반 XSP JCL 파서(`jcl_parser.py`)는 8개 패턴만 처리하며, OF7 C파서가 지원하는 41개 statement 타입 중 33개가 누락되어 있다. Python으로 재구현하는 대신, OF7의 검증된 C파서(`libxspjcl`)를 공유 라이브러리로 빌드하고 Python ctypes를 통해 직접 호출하는 공통모듈을 생성한다.

### 1.2 Background

- OF7 XSP JCL 파서는 flex/bison 기반으로 수년간 검증된 프로덕션 파서
- Python 재구현 시 정확도 보장 불가 (특히 매크로 확장, 에러 감지 등)
- 사용자가 `\ F1` 같은 의도적 오류를 삽입하여 파서 에러 감지 기능 테스트 → C파서와 100% 동일 동작 필요
- C파서 직접 호출 시: 41개 statement 타입 완전 지원, 에러 감지 동일, 유지보수 비용 최소화

### 1.3 Related Documents

- OF7 파서 소스: `OF7/base/parser/xspjcl/` (7개 .c 파일 + flex/bison)
- OF7 헤더: `OF7/base/include/jclcom.h`, `OF7/base/include/xspjcl.h`
- 현재 Python 파서: `app/api/legacy_modernization/parsers/jcl_parser.py`
- Capability 레지스트리: `app/api/legacy_modernization/capabilities/registry.py`

---

## 2. Scope

### 2.1 In Scope

- [ ] OF7 xspjcl C 소스를 공유 라이브러리(`.so`/`.dll`)로 빌드
- [ ] Python ctypes 기반 래퍼 모듈 `xspjcl_wrapper.py` 생성
- [ ] C 파서 parse tree를 Python 데이터 구조로 변환
- [ ] `JCLParser`의 XSP dialect 처리를 C 래퍼로 대체
- [ ] 에러 감지/보고 기능 통합 (C파서의 에러 메시지 전달)
- [ ] Linux 서버 환경 빌드 스크립트 (Makefile)

### 2.2 Out of Scope

- MVS JCL 파서 변경 (기존 Python 파서 유지)
- JES2/JES3 파서 변경
- OF7 C 소스코드 수정 (원본 그대로 사용)
- Windows 네이티브 빌드 (WSL 또는 Docker 환경 사용)

---

## 3. Requirements

### 3.1 Functional Requirements

| ID | Requirement | Priority | Status |
|----|-------------|----------|--------|
| FR-01 | OF7 xspjcl C 소스를 `libxspjcl.so` 공유 라이브러리로 빌드 | High | Pending |
| FR-02 | Python ctypes 래퍼가 `xspjcl_parse()` 호출하여 파싱 수행 | High | Pending |
| FR-03 | C parse tree (`jclcom_tree_t`) → Python dict/list 변환 | High | Pending |
| FR-04 | 41개 statement 타입 전체 지원 (30 JCL + 11 JCM macro) | High | Pending |
| FR-05 | 에러 감지: 미지원 statement(`\ F1` 등) 탐지 및 보고 | High | Pending |
| FR-06 | `JCLParser.parse()` XSP dialect에서 C 래퍼 자동 호출 | Medium | Pending |
| FR-07 | C 래퍼 결과를 기존 `NormalizedFeature`/`ASTNode` 형태로 변환 | Medium | Pending |
| FR-08 | C 라이브러리 미존재 시 기존 Python 파서로 graceful fallback | Medium | Pending |

### 3.2 Non-Functional Requirements

| Category | Criteria | Measurement Method |
|----------|----------|-------------------|
| Performance | 파싱 속도 Python 대비 10x+ 향상 | 동일 입력 벤치마크 |
| Reliability | OF7 C파서와 100% 동일한 파싱 결과 | E2E 비교 테스트 |
| Portability | Linux (CentOS/Ubuntu) 서버에서 빌드/실행 | CI 빌드 검증 |
| Safety | 메모리 누수 없음, segfault 방지 | valgrind 검증 |

---

## 4. Success Criteria

### 4.1 Definition of Done

- [ ] `libxspjcl.so` 빌드 성공 (의존 라이브러리 포함)
- [ ] Python에서 ctypes로 `xspjcl_parse()` 호출 성공
- [ ] 41개 statement 타입 파싱 결과가 C 직접 실행과 동일
- [ ] `\ F1` 등 에러 케이스에서 에러 감지 동작
- [ ] `JCLParser`에서 XSP 입력 시 자동으로 C 래퍼 사용
- [ ] 기존 Incompatibility Report 파이프라인과 통합 완료

### 4.2 Quality Criteria

- [ ] 테스트 파일 5개 이상으로 파싱 검증
- [ ] C 래퍼 초기화/종료 시 메모리 누수 없음
- [ ] C 라이브러리 로드 실패 시 Python fallback 정상 동작

---

## 5. Risks and Mitigation

| Risk | Impact | Likelihood | Mitigation |
|------|--------|------------|------------|
| C 의존 라이브러리 (libams, libofcom, libjclcom, libxspmac) 빌드 복잡 | High | High | stub 라이브러리 생성 또는 필요 함수만 추출하여 단독 빌드 |
| C 구조체 레이아웃 (padding, alignment) 불일치 | Medium | Medium | `ctypes.Structure` 정확한 매핑 + sizeof 검증 |
| flex/bison 생성 코드 의존성 (yylex, yyparse) | Medium | Medium | 이미 생성된 `xspjcl_scanner.c`, `xspjcl_grammar.c` 사용 |
| 전역 변수 사용 (`jcl_tree`, `jcl_stream`) → 스레드 안전성 | Medium | Medium | Python GIL 보호 또는 mutex wrapper 추가 |
| Windows 개발 환경에서 빌드 불가 | Low | High | Docker/WSL 빌드 스크립트 제공, 서버에서만 빌드 |

---

## 6. Architecture Considerations

### 6.1 Project Level Selection

| Level | Characteristics | Recommended For | Selected |
|-------|-----------------|-----------------|:--------:|
| **Starter** | Simple structure | Static sites | ☐ |
| **Dynamic** | Feature-based modules | Web apps with backend | ☐ |
| **Enterprise** | Strict layer separation, DI | Complex architectures | ☑ |

### 6.2 Key Architectural Decisions

| Decision | Options | Selected | Rationale |
|----------|---------|----------|-----------|
| C 호출 방식 | ctypes / cffi / pybind11 / subprocess | **ctypes** | 표준 라이브러리, 추가 의존성 없음, C ABI 직접 호출 |
| 빌드 방식 | OF7 Makefile / 독립 Makefile / CMake | **독립 Makefile** | OF7 빌드 시스템 의존 제거, 필요 소스만 추출 |
| 의존 라이브러리 | 전체 OF7 라이브러리 / stub 생성 | **stub 생성** | 최소 의존, 독립 빌드 가능 |
| Parse tree 전달 | 직접 구조체 순회 / JSON 출력 / callback | **JSON 출력 wrapper** | Python 측 구조체 매핑 복잡도 회피 |
| 통합 방식 | JCLParser 내부 / 독립 서비스 / 어댑터 | **어댑터 패턴** | 기존 코드 최소 변경, fallback 용이 |

### 6.3 모듈 구조

```
app/api/legacy_modernization/parsers/
├── jcl_parser.py              # 기존 (MVS JCL은 유지, XSP는 C 래퍼로 위임)
├── xspjcl/                    # 새로 생성하는 C 래퍼 패키지
│   ├── __init__.py            # XSPJCLParser 클래스 export
│   ├── wrapper.py             # ctypes 래퍼 (C 라이브러리 로드/호출)
│   ├── models.py              # Python 데이터 모델 (ParsedStatement, ParseTree)
│   ├── converter.py           # C 출력 → NormalizedFeature 변환
│   └── lib/                   # 빌드된 공유 라이브러리
│       ├── build.sh           # 빌드 스크립트
│       ├── Makefile            # 독립 Makefile
│       └── libxspjcl_kms.so   # 빌드 산출물 (git에는 미포함)
```

### 6.4 C 래퍼 API 설계

```python
# wrapper.py - 핵심 인터페이스

class XSPJCLCWrapper:
    """OF7 xspjcl C 파서를 ctypes로 호출하는 래퍼."""

    def __init__(self, lib_path: Optional[str] = None):
        """공유 라이브러리 로드. 실패 시 RuntimeError."""
        self._lib = ctypes.CDLL(lib_path or self._find_library())
        self._setup_functions()

    def parse(self, source: str) -> XSPParseResult:
        """XSP JCL 소스 파싱.

        내부적으로:
        1. source → 임시 파일 생성
        2. xspjcl_parse(flags, fp) 호출
        3. jcl_tree + jcl_stream 순회하여 결과 추출
        4. 임시 파일 정리
        """
        ...

    def get_errors(self) -> List[XSPParseError]:
        """마지막 파싱의 에러 목록 반환."""
        ...

    @staticmethod
    def is_available() -> bool:
        """C 라이브러리 사용 가능 여부."""
        ...
```

### 6.5 C 파서 Entry Point와 데이터 흐름

```
Python (wrapper.py)
    │
    ├─ source → tmpfile 생성
    ├─ ctypes.CDLL("libxspjcl_kms.so")
    │
    ▼
C 파서 호출:
    xspjcl_parse(flags=0, fp=tmpfile)
    │
    ├─ flex lexer (xspjcl_scanner.c) → 토큰화
    ├─ bison parser (xspjcl_grammar.c) → AST 생성
    ├─ jcl_tree.job_list → 파싱된 statement 트리
    └─ jcl_stream → 원문+에러 스트림
    │
    ▼
Python 결과 추출:
    ├─ xspjcl_stmt_list_print() → stdout 캡처 → JSON 파싱
    ├─ jcl_stream_error_print() → 에러 목록 추출
    └─ 또는 kms_xspjcl_to_json() 래퍼 함수 (C에 추가)
    │
    ▼
Python 변환 (converter.py):
    XSPParseResult → List[NormalizedFeature]
    → JCLParser.parse() 결과와 동일한 형태
```

### 6.6 C 파서 지원 Statement 전체 목록 (41개)

#### JCL Statements (30개, `\` prefix)
| # | Statement | Type Enum | 카테고리 |
|---|-----------|-----------|----------|
| 1 | `\ JOBG` | STMT_JOBG | Job Group |
| 2 | `\ CODE` | STMT_CODE | Code Block |
| 3 | `\ JOB` | STMT_JOB | Job 정의 |
| 4 | `\ EX` | STMT_EX | 프로그램 실행 |
| 5 | `\ PARA` | STMT_PARA | Parameter |
| 6 | `\ FD` | STMT_FD | File Definition |
| 7 | `\ SW` | STMT_SW | Switch |
| 8 | `\ PAUSE` | STMT_PAUSE | Pause |
| 9 | `\ MSG` | STMT_MSG | Message |
| 10 | `\ NOTE` | STMT_NOTE | Comment |
| 11 | `\ JEND` | STMT_JEND | Job End |
| 12 | `\ JGEND` | STMT_JGEND | Job Group End |
| 13 | `\ FIN` | STMT_FIN | Finish |
| 14 | `\ SYSIN` | STMT_SYSIN | Sysin Data |
| 15 | `\ EX_MACRO` | STMT_EX_MACRO | Macro Execution |
| 16 | `\ CHAM` | STMT_CHAM | Chain Module |
| 17 | `\ MACRO` | STMT_MACRO | Macro Definition |
| 18 | `\ MEND` | STMT_MEND | Macro End |
| 19 | `\ FDR` | STMT_FDR | FD Redirect |
| 20 | `\ FDDS` | STMT_FDDS | FD DS |
| 21 | `\ FDDE` | STMT_FDDE | FD DE |
| 22 | `\ STACK` | STMT_STACK | Stack |
| 23 | `\ CAT` | STMT_CAT | Catalog |
| 24 | `\ UNCAT` | STMT_UNCAT | Uncatalog |
| 25 | `\ DATA` | STMT_DATA | Data |
| 26 | `\ END` | STMT_END | End |
| 27 | `\ COMMAND` | STMT_COMMAND | Command |
| 28 | `\ JALT` | STMT_JALT | Job Alternate |
| 29 | `\ SCAN` | STMT_SCAN | Scan |
| 30 | `\ SCEND` | STMT_SCEND | Scan End |

#### JCM Macro Statements (11개, `/` prefix)
| # | Statement | Type Enum | 카테고리 |
|---|-----------|-----------|----------|
| 31 | `/ DEFINE` | MSTMT_DEFINE | Macro Define |
| 32 | `/ SKIP` | MSTMT_SKIP | Skip |
| 33 | `/ IF` | MSTMT_IF | Conditional |
| 34 | `/ IFN` | MSTMT_IFN | Negative Conditional |
| 35 | `/ SET` | MSTMT_SET | Variable Set |
| 36 | `/ MSG` | MSTMT_MSG | Message |
| 37 | `/ WTO` | MSTMT_WTO | Write To Operator |
| 38 | `/ WTOR` | MSTMT_WTOR | Write To Operator with Reply |
| 39 | `/ NOP` | MSTMT_NOP | No Operation |
| 40 | `/ DEXIT` | MSTMT_DEXIT | Define Exit |
| 41 | `/ DEFEND` | MSTMT_DEFEND | Define End |

---

## 7. Convention Prerequisites

### 7.1 Existing Project Conventions

- [x] `CLAUDE.md` has coding conventions section
- [x] Backend: Router → Service → Repository 패턴
- [x] Service 싱글턴: `_instance` + `get_X()` 패턴
- [x] Python type hints 필수

### 7.2 Conventions to Define/Verify

| Category | Current State | To Define | Priority |
|----------|---------------|-----------|:--------:|
| **C 빌드** | 없음 | Makefile, 빌드 스크립트 규칙 | High |
| **ctypes 래퍼** | 없음 | 에러 처리, 메모리 관리 패턴 | High |
| **Fallback** | 없음 | C 라이브러리 미존재 시 동작 | Medium |

### 7.3 Environment Variables Needed

| Variable | Purpose | Scope | To Be Created |
|----------|---------|-------|:-------------:|
| `XSPJCL_LIB_PATH` | C 라이브러리 경로 override | Server | ☑ |

---

## 8. Implementation Plan

### Phase 1: C 라이브러리 독립 빌드 (빌드 환경 구축)

1. OF7 소스에서 필요한 파일만 추출
2. 의존 라이브러리 stub 생성 (ofcom, jclcom, xspmac, ams)
3. 독립 Makefile 작성
4. `libxspjcl_kms.so` 빌드 검증

### Phase 2: JSON 출력 래퍼 함수 (C 측 확장)

1. `kms_xspjcl_parse_to_json()` 함수 작성 (C)
   - 입력: `const char *source` (문자열)
   - 출력: `char *json_result` (JSON 문자열)
   - 내부: tmpfile → xspjcl_parse → tree 순회 → JSON 생성
2. `kms_xspjcl_free()` 메모리 해제 함수

### Phase 3: Python ctypes 래퍼 모듈

1. `xspjcl/wrapper.py` - C 라이브러리 로드 및 함수 호출
2. `xspjcl/models.py` - ParsedStatement, XSPParseResult 모델
3. `xspjcl/converter.py` - C 결과 → NormalizedFeature 변환

### Phase 4: JCLParser 통합

1. `jcl_parser.py`에서 XSP dialect 감지 시 C 래퍼로 위임
2. C 래퍼 실패 시 기존 Python regex fallback
3. 에러 보고 통합

### Phase 5: 테스트 및 검증

1. TESTJCL00, TESTJCL01 등 기존 테스트 파일로 검증
2. C 직접 실행 vs Python 래퍼 결과 비교
3. 에러 케이스 (`\ F1` 등) 검증

---

## 9. Next Steps

1. [ ] Write design document (`xsp-jcl-c-parser-wrapper.design.md`)
2. [ ] OF7 빌드 환경 확인 (서버에 gcc, flex, bison 설치 여부)
3. [ ] 의존 라이브러리 헤더 분석 → stub 범위 확정
4. [ ] Start implementation

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-02-19 | Initial draft | Claude Code |
