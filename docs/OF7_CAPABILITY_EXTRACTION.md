# OF7 소스 기반 코드레벨 지원/미지원 추출 시스템

## 1. 문제 배경

기존 Legacy Modernization 시스템의 호환성 분석은 **수동 관리되는 Capability JSON** 파일에 의존했습니다.

```
기존 상태:
- _base.json: ~25개 항목 (COBOL 7개, JCL 18개)
- 각 제품별 JSON: 2~5개 항목
- 총합: ~35개 → 대부분의 레거시 코드 기능이 "UNKNOWN"으로 분류
```

그러나 프로젝트에 **OF7 디렉토리** (OpenFrame 7 실제 소스코드)가 있었고, 여기에는 지원되는 모든 JCL 파라미터, COBOL 키워드, 유틸리티 명령어, AIM/DC 구문이 **코드 레벨에서 정확히 정의**되어 있었습니다.

```
개선 후:
- 자동 추출: 2,686개 capability 엔트리
- 에러 코드: 1,778개 (63개 모듈)
- 개선 배율: 76배 증가
```

---

## 2. 전체 아키텍처

```
OF7/ (OpenFrame 소스코드)
├── base/parser/mvsjcl/mvsjcl_keyword_table.c  ─┐
├── base/parser/cobpar/cobpar_keyword.c         │
├── batch/tool/tjesmgr/tjesmgr_lex.l            │  [추출 대상 소스]
├── batch/util/mvs/idcams/idcams.l              │
├── aim/dc/acp/acp_l.l                          │
├── batch/errcode/errcode_tjes.h                ─┘
                    │
                    ▼
    scripts/of7_extractor/              ← [Phase 1: 추출 스크립트]
    ├── keyword_table_extractor.py      C 키워드 테이블 파서
    ├── lex_extractor.py                Lex 토큰 파서 (5가지 전략)
    ├── yacc_extractor.py               Yacc 문법 파서
    ├── errcode_extractor.py            에러 코드 파서
    ├── header_extractor.py             #define 상수 파서
    └── generate_capabilities.py        오케스트레이터
                    │
                    ▼
    capabilities/ JSON                  ← [Phase 2: 자동 생성]
    ├── _base.json          (163개: COBOL 키워드 + 기본)
    ├── batch/v7_3.json     (1,929개: MVS JCL + VOS3 + 도구 + 유틸리티)
    ├── aim_msp/v7_3.json   (108개: MSP JCL)
    ├── aim_xsp/v7_3.json   (486개: XSP JCL + AIM/DC)
    └── _error_codes.json   (1,778개: 에러 코드 사전)
                    │
                    ▼
    ProductRegistry + CompatibilityEngine  ← [Phase 3: 매칭 강화]
    (다단계 패턴 매칭으로 UNKNOWN 비율 대폭 감소)
```

---

## 3. Phase 1: OF7 추출 스크립트 상세

### 3-1. keyword_table_extractor.py -- C 키워드 테이블 파서

**대상 파일**: `mvsjcl_keyword_table.c`, `mspjcl_keyword_table.c`, `vos3jcl_keyword_table.c`, `cobpar_keyword.c`

OF7의 JCL 파서는 C 소스코드에서 **구조체 배열**로 키워드를 정의합니다:

```c
// OF7/base/parser/mvsjcl/mvsjcl_keyword_table.c 원본 예시
static key_s key_dd[] = {
    {"DSN",      KW_DD_DSN,     0, NULL},
    {"DISP",     KW_DD_DISP,    0, kv_disp},
    {"RECFM",    KW_DD_RECFM,   0, kv_recfm},
    ...
};

static keyval_t kv_recfm[] = {
    {"F", 0}, {"FA", 0}, {"FM", 0}, {"FB", 0},
    {"FBA", 0}, {"V", 0}, {"VB", 0}, {"VBS", 0}, {"U", 0},
    {NULL, 0}
};
```

**추출 로직**:

```python
def extract_jcl_keywords(keyword_table_path: Path) -> Dict[str, List[Dict]]:
    """
    1단계: keyval_t 배열 파싱 → 유효값 사전 구축
       kv_recfm → ["F", "FA", "FM", "FB", ...]

    2단계: key_s 배열 파싱 → 키워드 + 유효값 연결
       key_dd[] → [{"keyword": "RECFM", "valid_values": ["F","FA",...]}, ...]

    3단계: 결과를 stmt_type별로 그룹화
       {"JOB": [...], "EXEC": [...], "DD": [...], "DCB": [...]}
    """
```

**핵심 정규식**:
- `keyval_t` 배열: `r'static\s+keyval_t\s+(\w+)\[\]\s*=\s*\{([^;]+)\};'`
- `key_s` 배열: `r'static\s+key_s\s+key_(\w+)\[\]\s*=\s*\{([^;]+)\};'`
- 메타값 필터링: `^0`, `^8`, `%class`, `%dsname` 등 내부 제어값 제외

**추출 결과**:

| JCL 변형 | JOB | EXEC | DD | DCB | OUTPUT | 합계 |
|----------|-----|------|----|-----|--------|------|
| MVS | 26 | 13 | 66 | 36 | 74 | 221 |
| MSP | - | - | - | - | - | 107 |
| VOS3 | - | - | - | - | - | 40 |
| XSP | - | - | - | - | - | 0* |

*XSP는 `_keyword.c` 형식이 다름 (향후 개선 가능)

COBOL 키워드는 별도의 `extract_cobol_keywords()` 함수로 처리:
- 방언 플래그: `L_COM` (공통), `L_MF` (Micro Focus), `L_OSVS` (OS/VS)
- 총 137개 키워드 추출

---

### 3-2. lex_extractor.py -- Lex 토큰 파서 (5가지 전략)

OF7의 `.l` (Lex) 파일들은 **다양한 패턴**으로 명령어를 정의합니다. 단일 정규식으로는 불가능하여 **5가지 추출 전략**을 구현했습니다:

#### 전략 1: CHAR_X 매크로 패턴 (tjesmgr 스타일)

```lex
TJBOOT    {CHAR_B}{CHAR_O}{CHAR_O}{CHAR_T}
TJCANCEL  {CHAR_C}{CHAR_A}{CHAR_N}{CHAR_C}{CHAR_E}{CHAR_L}
```

- 정규식: `r'^(\w+)\s+(\{CHAR_[A-Z]\}(?:\{CHAR_[A-Z]\})*)\s*$'`
- 디코딩: `{CHAR_B}{CHAR_O}{CHAR_O}{CHAR_T}` -> `BOOT`
- TJ 접두사 제거: `TJBOOT` -> 명령어 `BOOT`

#### 전략 2: 대안(|)이 있는 CHAR_X 매크로

```lex
TJCURRENTUSER  {CHAR_C}{CHAR_U}|{CHAR_C}{CHAR_U}{CHAR_R}...
```

- 약어와 전체 형태가 `|`로 연결됨
- 가장 긴 대안을 선택하여 전체 명령어명 추출

#### 전략 3: 따옴표 문자열 규칙 (IDCAMS 스타일)

```lex
"DEFINE"    { return TOKEN_DEFINE; }
"DELETE"    { return TOKEN_DELETE; }
"ALTER"     { return TOKEN_ALTER;  }
```

- 정규식: `r'"([A-Z][A-Z0-9_-]+)"\s*\{'`
- IDCAMS, IEBCOPY 등 유틸리티에서 사용

#### 전략 4: 대소문자 무시 브래킷 패턴

```lex
[Dd][Ee][Ff][Ii][Nn][Ee]    { return TOKEN_DEFINE; }
```

- 정규식: 각 `[Xx]` 쌍에서 첫 문자 추출
- `[Dd][Ee][Ff]` -> `DEF`

#### 전략 5: 인라인 규칙 키워드 (AIM/DC 스타일) -- 핵심 추가

```lex
<OPERAND>ABENDEX    { return _acptok(ABENDEX); }
<INITIAL>JOB{ws}+  { BEGIN(OPERAND); return _acptok(JOB); }
```

- 정규식: `r'<\w+>([A-Z][A-Z0-9_]{1,})\b.*?\breturn\s+\w*\(?(\w+)\)?'`
- Lex 상태(`<OPERAND>`, `<INITIAL>`) 뒤의 키워드 추출
- `INITIAL`, `OPERAND`, `COMMENT` 등 상태 이름은 필터링

**이 전략이 가장 큰 효과**: adrdssu(308개), aimcmd(380개), iebcopy, iebgener 등에서 대량 추출 성공

**추출 결과**:

| 도구/유틸리티 | 추출된 명령어 수 |
|-------------|---------------|
| tjesmgr | 146 |
| adrdssu | 308 |
| aimcmd | 380 |
| idcams | 46 |
| dfsort/icetool | ~50 |
| 기타 20+ 유틸리티 | ~590 |

---

### 3-3. yacc_extractor.py -- Yacc 문법 파서

**대상**: `.y` (Yacc/Bison) 파일의 `%token` 선언

```yacc
%token TOKEN_DEFINE TOKEN_DELETE TOKEN_ALTER
%token TOKEN_REPRO TOKEN_LISTCAT TOKEN_PRINT
```

- `TOKEN_` 또는 `TK_` 접두사를 제거하여 명령어명 추출
- Lex 추출 결과와 병합 (중복 제거)

---

### 3-4. errcode_extractor.py -- 에러 코드 파서

**대상**: `OF7/batch/errcode/*.h`, `OF7/base/errcode/*.h`, `OF7/aim/errcode/*.h`

```c
// errcode_tjes.h 원본 예시
#define TJES_ERR_BASE               (-9000)
#define TJES_ERR_JOB_NOT_FOUND      (TJES_ERR_BASE - 1)   // -9001
#define TJES_ERR_QUEUE_FULL         (TJES_ERR_BASE - 2)   // -9002
```

**추출 로직**:

```python
def extract_error_codes(errcode_dir: Path) -> List[Dict]:
    """
    1단계: BASE 상수 탐색
       #define TJES_ERR_BASE (-9000) -> base_value = -9000

    2단계: 오프셋 계산
       (BASE - 1) -> -9000 - 1 = -9001

    3단계: 모듈명 추론
       파일명 errcode_tjes.h -> 모듈 "TJES"

    결과: {"name": "TJES_ERR_JOB_NOT_FOUND", "code": -9001, "module": "TJES"}
    """
```

**추출 결과**: 63개 모듈, 1,778개 에러 코드
- 주요 모듈: TJES(배치), ACP(AIM), IDCAMS(유틸리티), TSO, SPOOL 등

---

### 3-5. header_extractor.py -- #define 상수/enum 파서

범용 헤더 파일 파서로, 향후 확장을 위한 기반:

- `extract_defines(path, prefix)`: `#define` 상수 추출 (10진/16진/8진 자동 판별)
- `extract_enum_values(path)`: `enum` 블록의 값 추출 (자동 카운터 증가 처리)
- `extract_dataset_types(dir)`: `DSORG_`, `RECFM_`, `VSAM_` 등 데이터셋 타입 정의 추출

---

### 3-6. generate_capabilities.py -- 오케스트레이터

모든 추출기를 조율하여 최종 JSON을 생성하는 메인 스크립트:

```bash
python -m scripts.of7_extractor.generate_capabilities \
    --of7-path OF7/ \
    --output-dir app/api/legacy_modernization/capabilities/ \
    [--dry-run]
```

**9단계 파이프라인**:

```
Step 1: COBOL 키워드      -> _base.json         (137개)
Step 2: MVS JCL 파라미터  -> batch/v7_3.json     (221개)
Step 3: MSP JCL 파라미터  -> aim_msp/v7_3.json   (107개)
Step 4: VOS3 JCL 파라미터 -> batch/v7_3.json     (40개, 카테고리=jcl_parameter_vos3)
Step 5: XSP JCL 파라미터  -> aim_xsp/v7_3.json   (0개*)
Step 6: 도구 명령어       -> batch/v7_3.json     (146개: tjesmgr 등)
Step 7: 유틸리티 명령어   -> batch/v7_3.json     (1,522개: IDCAMS, IEBGENER 등)
Step 8: AIM/DC 구문       -> aim_xsp/v7_3.json   (485개)
Step 9: 에러 코드         -> _error_codes.json   (1,778개)
```

**비파괴적 병합**: `_merge_into_json()` 함수가 기존 JSON의 엔트리를 보존하면서 새 항목만 추가 (pattern 키로 중복 방지)

---

## 4. Phase 2: CapabilityRecord 모델 확장

### registry.py 수정

```python
class CapabilityRecord(BaseModel):
    category: str
    pattern: str
    support: str              # "full", "partial", "workaround", "unsupported"
    notes: Optional[str] = None
    # === 새로 추가된 필드 ===
    parameters: Optional[List[str]] = None    # 유틸리티의 서브명령어 목록
    valid_values: Optional[List[str]] = None  # JCL 파라미터 유효값
    source_ref: Optional[str] = None          # OF7 소스 파일 참조 경로
```

**예시 데이터**:

```json
{
  "category": "jcl_parameter",
  "pattern": "JCL DD DCB RECFM",
  "support": "full",
  "notes": "JCL DD statement RECFM parameter",
  "valid_values": ["F", "FA", "FM", "FB", "FBA", "V", "VA", "VB", "VBS", "U"],
  "source_ref": "base\\parser\\mvsjcl\\mvsjcl_keyword_table.c"
}
```

```json
{
  "category": "utility",
  "pattern": "PGM=IDCAMS",
  "support": "full",
  "notes": "MVS utility program IDCAMS",
  "parameters": ["ALTER", "BLDINDEX", "DEFINE", "DELETE", "LISTCAT", "PRINT", "REPRO"],
  "source_ref": "batch/util/mvs/idcams/"
}
```

---

## 5. Phase 3: CompatibilityEngine 매칭 강화

### lookup_capability() -- 4단계 매칭

기존에는 **정확 일치(exact match)** 만 지원했습니다. 이제 4단계 매칭으로 확장:

```python
def lookup_capability(self, product, version, pattern):
    resolved = self.resolve_capabilities(product, version)
    caps = resolved.capabilities

    # 1. 정확 일치
    #    "JCL JOB REGION" == "JCL JOB REGION" -> 매칭
    if pattern in caps:
        return caps[pattern]

    # 2. 접두사 매칭
    #    "JCL DD DCB" -> "JCL DD DCB RECFM" (짧은 쿼리가 긴 패턴에 매칭)
    #    "JCL DD DCB RECFM FB" -> "JCL DD DCB RECFM" (긴 쿼리가 짧은 패턴에 매칭)
    for cap_pattern, cap in caps.items():
        if cap_pattern.startswith(pattern + " ") or pattern.startswith(cap_pattern + " "):
            return cap

    # 3. 유틸리티 프로그램 매칭
    #    "PGM=IDCAMS" -> caps["PGM=IDCAMS"] 조회
    if pattern.startswith("PGM="):
        pgm_name = pattern.split("=", 1)[1].upper()
        if f"PGM={pgm_name}" in caps:
            return caps[f"PGM={pgm_name}"]

    # 4. 파라미터=값 매칭 (유효값 검증)
    #    "JCL DD DCB RECFM=FB" -> "JCL DD DCB RECFM" 찾고,
    #    valid_values에 "FB"가 있는지 검증
    if "=" in pattern:
        base, value = pattern.rsplit("=", 1)
        for cap_pattern, cap in caps.items():
            if cap_pattern == base or ...:
                if cap.valid_values and value.upper() in [...]:
                    return cap
```

### _match_with_registry() -- 3가지 전략

CompatibilityEngine의 `_match_with_registry()`도 강화:

```python
def _match_with_registry(self, feature, target_product, target_version, evidence):
    registry = get_product_registry()

    # 전략 1: 직접 조회 (위의 4단계 매칭 활용)
    cap = registry.lookup_capability(target_product, target_version, feature.name)

    # 전략 2: 유틸리티 프로그램 매칭
    #   feature.metadata = {"pgm": "IDCAMS"} -> "PGM=IDCAMS"로 조회
    if cap is None and feature.metadata:
        pgm = feature.metadata.get("pgm")
        if pgm:
            cap = registry.lookup_capability(..., f"PGM={pgm.upper()}")

    # 전략 3: JCL 파라미터+값 매칭
    #   feature.metadata = {"param": "RECFM", "value": "FB"}
    #   -> "JCL DD RECFM=FB"로 조회
    if cap is None and feature.metadata:
        param = feature.metadata.get("param")
        value = feature.metadata.get("value")
        if param and value:
            cap = registry.lookup_capability(..., f"{feature.name}={value}")
```

---

## 6. 상속 체인과 버전별 해결

ProductRegistry의 상속 체인이 새로운 데이터와 함께 작동합니다:

```
_base.json (163개: COBOL + 기본)
    ↓ 상속
batch/v7_0.json (기존 2개)
    ↓ 상속
batch/v7_1.json (기존 3개)
    ↓ 상속 (여기서는 v7_3 직접)
batch/v7_3.json (1,929개 추가!)
```

**결과**:
- `batch/7.1` 해결 시: 189개 capabilities (기존 + _base)
- `batch/7.3` 해결 시: 2,118개 capabilities (기존 + _base + **1,929개 신규**)

이 구조 덕분에 **v7.0, v7.1에서는 기존 데이터만** 반환되고, **v7.3에서만 새로운 대량 데이터**가 추가됩니다. 향후 v8.0에서 제거된 기능은 `removed` 배열로 처리 가능합니다.

---

## 7. 카테고리별 최종 분포

```
_base.json (163개)
├── cobol_keyword: 137개     <- PERFORM, COPY, DIVISION, SECTION...
├── file_io: 7개             <- READ, WRITE, OPEN, CLOSE...
├── flow_control: 7개        <- IF, EVALUATE, GO TO...
├── arithmetic: 5개          <- ADD, SUBTRACT, MULTIPLY...
├── data_definition: 3개
├── string_op: 3개
└── copybook: 1개

batch/v7_3.json (1,929개)
├── utility_command: 1,493개 <- IDCAMS DEFINE, IEBGENER GENERATE...
├── jcl_parameter: 221개    <- JCL JOB REGION, JCL DD DISP...
├── tool_command: 146개      <- tjesmgr BOOT, tjesmgr CANCEL...
├── jcl_parameter_vos3: 40개 <- VOS3 전용 JCL 파라미터
└── utility: 29개            <- PGM=IDCAMS, PGM=IEBGENER...

aim_xsp/v7_3.json (486개)
├── aim_dc: 485개            <- AIM ACP ABENDEX, AIM PSAM...
└── cics: 1개                <- 기존

aim_msp/v7_3.json (108개)
├── jcl_parameter: 107개     <- MSP JCL 파라미터
└── ims: 1개                 <- 기존

_error_codes.json (1,778개, 63모듈)
├── TJES: ~200개             <- 배치 처리 에러
├── ACP: ~150개              <- AIM/DC 에러
├── IDCAMS: ~100개           <- 유틸리티 에러
└── ... 60개 모듈
```

---

## 8. 실행 방법

```bash
# 드라이런 (파일 미변경, 추출 수만 확인)
python -m scripts.of7_extractor.generate_capabilities \
    --of7-path OF7/ \
    --output-dir app/api/legacy_modernization/capabilities/ \
    --dry-run

# 실제 실행 (JSON 파일 업데이트)
python -m scripts.of7_extractor.generate_capabilities \
    --of7-path OF7/ \
    --output-dir app/api/legacy_modernization/capabilities/
```

**멱등성 보장**: 동일 스크립트를 여러 번 실행해도 `pattern` 키 기준으로 중복이 방지되므로 안전합니다.

---

## 9. 설계 원칙

| 원칙 | 설명 |
|------|------|
| **No LLM** | CompatibilityEngine은 100% 결정론적 조회 -- LLM 호출 없음 |
| **비파괴적 병합** | 기존 JSON 항목 보존, 새 항목만 추가 |
| **소스 추적** | 모든 엔트리에 `source_ref` 기록 (감사 추적 가능) |
| **상속 호환** | 기존 `_base.json -> product/vX_Y.json` 상속 체인 100% 유지 |
| **하위 호환** | 새 필드 (`parameters`, `valid_values`, `source_ref`)는 모두 Optional |
| **멱등성** | 스크립트 반복 실행 시 중복 생성 없음 |

---

## 10. 관련 파일 목록

### 추출 스크립트 (신규)

| 파일 | 역할 |
|------|------|
| `scripts/of7_extractor/__init__.py` | 패키지 초기화 |
| `scripts/of7_extractor/keyword_table_extractor.py` | C 키워드 테이블 파서 |
| `scripts/of7_extractor/lex_extractor.py` | Lex 토큰 파서 (5가지 전략) |
| `scripts/of7_extractor/yacc_extractor.py` | Yacc 문법 파서 |
| `scripts/of7_extractor/errcode_extractor.py` | 에러 코드 파서 |
| `scripts/of7_extractor/header_extractor.py` | #define 상수/enum 파서 |
| `scripts/of7_extractor/generate_capabilities.py` | 오케스트레이터 (CLI) |

### Capability JSON (자동 생성으로 보강)

| 파일 | 엔트리 수 | 내용 |
|------|-----------|------|
| `capabilities/_base.json` | 163 | COBOL 키워드 + 기본 capabilities |
| `capabilities/batch/v7_3.json` | 1,929 | MVS JCL + VOS3 JCL + 도구 + 유틸리티 |
| `capabilities/aim_msp/v7_3.json` | 108 | MSP JCL 파라미터 |
| `capabilities/aim_xsp/v7_3.json` | 486 | XSP JCL + AIM/DC capabilities |
| `capabilities/_error_codes.json` | 1,778 | 에러 코드 사전 (63 모듈) |

### 수정된 엔진 파일

| 파일 | 변경 내용 |
|------|----------|
| `capabilities/registry.py` | CapabilityRecord에 `parameters`, `valid_values`, `source_ref` 필드 추가; `lookup_capability()` 4단계 매칭 |
| `models/capability_model.py` | `_match_with_registry()` 3가지 전략 (직접, 유틸리티, 파라미터+값) |
