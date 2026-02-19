# XSP Parser Faithful Wrapper - Plan

> **Feature**: xsp-parser-faithful-wrapper
> **Date**: 2026-02-19
> **Author**: Claude Code
> **Priority**: High
> **Scope**: Python fallback 파서를 OF7 C 파서와 동일하게 동작하도록 개선

---

## 1. 문제 정의

### 1.1 현재 상태

XSP JCL 파서는 두 경로로 동작:
1. **C 파서 경로** (Linux 서버): `XSPJCLCWrapper` → ctypes → `libxspjcl_kms.so` → 완전한 파싱
2. **Python 폴백 경로** (Windows/C 라이브러리 미존재): `JCLParser._extract_features()` → regex 8개 패턴

### 1.2 문제점

Python 폴백 파서가 OF7 C 파서와 **동일한 동작을 하지 않음**:

| 동작 | OF7 C 파서 | Python 폴백 |
|------|-----------|-------------|
| `\ F1 SYSTSPRT=DA` | **STMT_ERROR** + "Unknown JCL statement - F1" 에러 보고 | **무시** (아무 출력 없음) |
| `\ F2`, `\ F3` 등 | **STMT_ERROR** + 에러 보고 | **무시** |
| 기타 미인식 `\` 문 | **STMT_ERROR** + 에러 보고 | **무시** |
| `\ FD SYSTSIN=*` | `STMT_FD` → DD statement | `DD SYSTSIN` (정상) |

**핵심**: `\ F1`은 XSP JCL 규격에 없는 **원본 소스의 오류**이며, OF7 C 파서는 이를 정확히 `STMT_ERROR`로 보고한다. Python 폴백은 이러한 에러 라인을 완전히 무시하여 C 파서와 다른 결과를 산출한다.

### 1.3 OF7 C 파서의 에러 처리 (xspjcl.l:552-554)

```c
// 인식된 키워드 매칭 실패 시 (F1, F2 등 미지원 문)
sprintf(temp, "Syntax Error [Line:%s;Column: ;Keyword: ;Message:Unknown JCL statement - %s]\n",
        xspjcl_lineno_str, yytext);
jcl_stream_error_add(temp);
SAVE_RETURN(K_ERROR);  // → bison에서 STMT_ERROR로 변환
```

### 1.4 영향 범위

테스트 케이스 `TESTJCL01`:
```
\ F1  SYSTSPRT=DA,SOUT=A   ← line 7: C 파서 = STMT_ERROR, Python 폴백 = 무시
```
- C 파서: 10 features + 1 error
- Python 폴백: 9 features + 0 errors
- **차이**: 에러 미보고 → 비호환성 분석에서 원본 소스 문제가 은폐됨

---

## 2. 목표

> **Python 폴백 파서를 OF7 C 파서와 동일한 동작으로 개선하여, C 라이브러리 존재 여부와 관계없이 파싱 결과가 일관되도록 한다.**

### 2.1 핵심 원칙

1. **C 파서 충실 재현**: C 파서가 에러로 보고하는 것은 Python 폴백에서도 에러로 보고
2. **에러 무시 금지**: 인식할 수 없는 XSP 문(`\` prefix)은 `STMT_ERROR`로 기록
3. **기존 인식 패턴 보존**: JOB/EX/FD/MSG/JEND/EXPAN/SET/DEFEND 등 기존 매칭은 변경 없음
4. **상위 호환**: 기존 `ParserResult` 스키마 유지, `parse_errors` 필드에 에러 추가

### 2.2 성공 기준

| 기준 | 목표 |
|------|------|
| SC-01 | `\ F1`, `\ F2` 등 미인식 XSP 문이 `parse_errors`에 에러로 보고됨 |
| SC-02 | 에러 보고 형식이 C 파서와 동일: `"Unknown JCL statement - F1"` |
| SC-03 | 에러 라인이 AST에 `STMT_ERROR` 노드로 포함됨 |
| SC-04 | `stats.error_count`가 에러 수를 반영 |
| SC-05 | 기존 정상 XSP 문 파싱 결과가 변경되지 않음 (회귀 없음) |
| SC-06 | `TESTJCL01` 파싱 결과가 C 파서와 동일한 에러를 보고 |

---

## 3. 구현 범위

### 3.1 수정 대상 파일

| # | 파일 | 변경 내용 |
|---|------|----------|
| 1 | `app/api/legacy_modernization/parsers/jcl_parser.py` | Python 폴백에서 미인식 XSP 문을 에러로 보고 |

### 3.2 변경하지 않는 파일

| 파일 | 이유 |
|------|------|
| `parsers/xspjcl/*` (C wrapper) | C 파서 래퍼는 이미 에러를 정확히 전파함 |
| `parsers/xspjcl/models.py` | `STMT_ERROR` 이미 정의됨 |
| `parsers/xspjcl/converter.py` | `STMT_ERROR` → `parse_error` 변환 이미 구현 |

---

## 4. 상세 구현 계획

### Phase 1: XSP 미인식 문 감지 로직 추가

**`jcl_parser.py`의 `_build_ast()`에 미인식 XSP 문 에러 노드 추가:**

현재 `_build_ast()`는 `\ ` prefix 라인 중 JOB/EX/FD만 매칭하고 나머지를 무시한다.

변경:
1. `\ ` prefix를 가진 라인이 JOB/EX/FD/MSG/JEND/COMMENT 어디에도 매칭되지 않으면
2. AST에 `STMT_ERROR` 노드 추가
3. `properties`에 에러 메시지 기록

```python
# 기존: JOB/EX/FD 매칭 실패 시 무시
# 변경: 미매칭 XSP 문을 STMT_ERROR로 기록

# \ prefix 라인인데 아무 패턴에도 매칭 안 됨
if _is_xsp_statement(line) and not any_matched:
    error_node = ASTNode(
        node_type="STMT_ERROR",
        source_line=line_no,
        source_end_line=line_no,
        properties={
            "error_message": f"Unknown JCL statement - {_extract_keyword(line)}",
        },
    )
    # 현재 JOB 하위 또는 최상위에 추가
```

### Phase 2: `_extract_features()`에 에러 feature 추가

미인식 XSP 문을 `NormalizedFeature`로도 기록:

```python
if _is_xsp_statement(line) and not any_matched:
    features.append(NormalizedFeature(
        feature_id=f"JCL-ERR-{counter:03d}",
        category=FeatureCategory.XSP_CONTROL,  # 또는 PARSE_ERROR
        subcategory="STMT_ERROR",
        name=f"Unknown JCL statement - {keyword}",
        ...
        complexity=ComplexityLevel.HIGH,  # 에러 = high complexity
    ))
```

### Phase 3: `parse_errors` 리스트에 에러 추가

`ParserResult.parse_errors`에 C 파서와 동일한 형식의 에러 추가:

```python
parse_errors.append(ParseError(
    line=line_no,
    column=0,
    message=f"Syntax Error [Line:{line_no};Column: ;Keyword: ;Message:Unknown JCL statement - {keyword}]",
    severity="error",
))
```

### Phase 4: `_compute_stats()` 에러 카운트 반영

```python
# error_count를 parse_errors 길이로 설정
error_count=len(parse_errors),
```

### Phase 5: 헬퍼 함수 추가

```python
def _is_xsp_statement(line: str) -> bool:
    """\ prefix로 시작하는 XSP JCL 문인지 판단 (코멘트 제외)."""
    return line.startswith("\\") and not _XSP_COMMENT_RE.match(line)

def _extract_xsp_keyword(line: str) -> str:
    """XSP 문에서 키워드 추출 (예: '\\ F1 ...' → 'F1')."""
    parts = line.lstrip("\\").strip().split()
    return parts[0] if parts else "UNKNOWN"
```

### Phase 6: 검증

`TESTJCL01` 파싱 결과 확인:

| 항목 | 기대값 |
|------|--------|
| Features | 9 (기존) + 에러 feature 포함 |
| parse_errors | 1 (`Unknown JCL statement - F1`) |
| AST | `STMT_ERROR` 노드 1개 포함 |
| error_count | 1 |

---

## 5. XSP 문 매칭 전체 목록

C 파서 lexer(`xspjcl.l:472-549`)의 인식 키워드 전체:

| 키워드 | C 토큰 | Python 폴백 매칭 | 비고 |
|--------|--------|-----------------|------|
| `JOBG` | K_JOBG | - | 미구현 (희소) |
| `CODE` | K_CODE | - | 미구현 (희소) |
| `JOB` | K_JOB | `_XSP_JOB_RE` | 정상 |
| `EX` | K_EX | `_XSP_EXEC_RE` | 정상 |
| `PARA` | K_PARA | - | 미구현 (희소) |
| `FD` | K_FD | `_XSP_FD_RE` | 정상 |
| `SW` | K_SW | - | 미구현 (희소) |
| `PAUSE` | K_PAUSE | - | 미구현 (희소) |
| `MSG` | K_MSG | `_XSP_MSG_RE` | 정상 |
| `NOTE` | K_NOTE | - | 미구현 (희소) |
| `JEND` | K_JEND | `_XSP_JEND_RE` | 정상 |
| `JGEND` | K_JGEND | - | 미구현 (희소) |
| `FIN` | K_FIN | - | 미구현 (희소) |
| `SYSIN` | K_SYSIN | - | 미구현 (희소) |
| `FDR` | K_FDR | - | 미구현 (희소) |
| `FDDS` | K_FDDS | - | 미구현 (희소) |
| `FDDE` | K_FDDE | - | 미구현 (희소) |
| `STACK` | K_STACK | - | 미구현 (희소) |
| `CAT` | K_CAT | - | 미구현 (희소) |
| `UNCAT` | K_UNCAT | - | 미구현 (희소) |
| `DATA` | K_DATA | - | 미구현 (희소) |
| `END` | K_END | - | 미구현 (희소) |
| `SCAN` | K_SCAN | - | 미구현 (희소) |
| `SCEND` | K_SCEND | - | 미구현 (희소) |
| `USER` | K_USER | - | 미구현 (희소) |
| `UEND` | K_UEND | - | 미구현 (희소) |
| `NOP` | K_NOP | - | 미구현 (희소) |
| **기타** | **K_ERROR** | **무시** | **이번 수정 대상** |

> **중요**: Python 폴백에서 미구현인 XSP 키워드(JOBG, SW, PARA 등)는 이번 범위에서 "인식 키워드로 추가"하지 않는다. C 파서에서는 이들을 정상 statement로 처리하므로, Python 폴백에서도 정상 키워드로 추가하는 것이 이상적이지만, 이번 Plan의 핵심은 **"미인식 문을 에러로 보고"**하는 것이다.
>
> 단, C 파서의 **인식 키워드 전체를 Python 폴백에도 등록**하여, C 파서와 동일하게 "인식/미인식"을 구분할 수 있도록 하는 것이 바람직하다. 이는 Phase 1에서 `_XSP_KNOWN_KEYWORDS` set으로 구현한다.

---

## 6. 구현 순서

```
Phase 1: _XSP_KNOWN_KEYWORDS set 추가 + _is_xsp_statement() + _extract_xsp_keyword()
Phase 2: _build_ast()에 STMT_ERROR 노드 추가
Phase 3: _extract_features()에 에러 feature 추가
Phase 4: parse() 메서드에서 parse_errors 수집 + stats.error_count 반영
Phase 5: TESTJCL01 검증
```

---

## 7. 리스크

| 리스크 | 영향 | 완화 |
|--------|------|------|
| `/ ` prefix 문(`/ SET`, `/ DEFEND`)도 미인식으로 잡힐 수 있음 | 오탐 | `/ ` prefix 문은 별도 regex로 이미 매칭되므로 `_is_xsp_statement()`에서 `\` prefix만 대상 |
| 기존 테스트 결과 변경 | 회귀 | 에러가 추가되는 것은 정상 변경 (기존 feature 결과는 불변) |
| C 파서와 Python 폴백의 정확한 동일성 보장 불가 | 낮음 | "에러 보고" 동작만 일치시키면 충분. 완전 동일성은 C 파서 사용으로 보장 |

---

## 8. 비기능 요구사항

| NFR | 요구사항 |
|-----|---------|
| 성능 | 추가 regex 없음 (문자열 prefix 비교만). 기존 O(n) 유지 |
| 호환성 | `ParserResult` 스키마 변경 없음. `parse_errors` 기존 필드 활용 |
| 테스트 | `TESTJCL01` 커맨드라인 검증으로 확인 |

---

## Version History

| Version | Date | Changes |
|---------|------|---------|
| 1.0 | 2026-02-19 | Initial plan |
