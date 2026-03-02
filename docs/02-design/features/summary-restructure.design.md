# Design: 요약본 완전 재구조화 및 학습 데이터 재생성

> 작성일: 2026-02-03
> 상태: Draft
> 우선순위: Critical

## 1. 현재 문제점 분석

### 1.1 요약본 구조 문제

| 파일명 | Manager | 서브명령어 수 | 문제점 |
|--------|---------|--------------|--------|
| `OpenFrame_TJES_MVS.md` | tjesmgr | 147개 | 헤더가 `## BOOT`로 되어있어 `tjesmgr`와 연결 안됨 |
| `OpenFrame_OSC_MVS.md` | oscmgr | 633개 | 동일 |
| `OpenFrame_TACF_MVS.md` | tacfmgr | 63개 | 동일 |
| `OpenFrame_HiDB_MVS.md` | hidbmgr | 46개 | 동일 |

### 1.2 학습 데이터 문제

```
현재 상태:
- 키워드 "tjesmgr" 검색 → 요약본에서 잘못된 항목 반환
- syntax: null, parameters: [] → Learning LLM이 자체 추론 → 할루시네이션

근본 원인:
1. 요약본 헤더: "## BOOT" (tjesmgr 없음)
2. 키워드 검색: "tjesmgr" → 매칭 안됨
3. 결과: 불완전한 학습 데이터
```

### 1.3 해결해야 할 핵심 과제

1. **Manager-서브명령어 연결**: `## BOOT` → `tjesmgr BOOT` 매핑
2. **정확한 syntax 추출**: 모든 명령어에 올바른 syntax 포함
3. **키워드 완전 매핑**: 43,147개 키워드 전수 처리
4. **중복 제거**: 동일 명령어 여러 소스 병합

---

## 2. 새로운 요약본 구조 설계

### 2.1 파일명-Manager 매핑 규칙

```python
MANAGER_MAPPING = {
    # TJES (Job Entry Subsystem)
    "OpenFrame_TJES": "tjesmgr",
    "OpenFrame_Batch_MVS": "tjesmgr",
    "OpenFrame_Batch_MSP": "tjesmgr",
    "OpenFrame_Batch_XSP": "tjesmgr",
    "OpenFrame_Batch_VOS3": "tjesmgr",

    # OSC (Online System Controller)
    "OpenFrame_OSC": "oscmgr",

    # TACF (Tmax Access Control Facility)
    "OpenFrame_TACF": "tacfmgr",

    # HiDB (Hierarchical Database)
    "OpenFrame_HiDB": "hidbmgr",

    # OSI (Online System Interface)
    "OpenFrame_OSI": "osimgr",

    # Base (유틸리티 - Manager 아님)
    "OpenFrame_Base": None,  # dsmigin, dsmigout 등 독립 명령어

    # AIM
    "OpenFrame_AIM": None,  # 참조 문서
}
```

### 2.2 새로운 요약본 포맷

**기존 포맷:**
```markdown
## BOOT

TJES 노드를 초기화합니다.

**구문:**
```
tjesmgr BOOT
```
```

**새로운 포맷:**
```markdown
## tjesmgr BOOT

TJES 노드를 초기화합니다.

**명령어 정보:**
- 부모 명령어: tjesmgr
- 서브명령어: BOOT
- 타입: command
- 제품: OF_TJES

**구문:**
```
tjesmgr BOOT [nodename]
```

**파라미터:**
- `nodename`: (선택) 초기화할 노드 이름

**예시:**
```bash
$ tjesmgr BOOT
$ tjesmgr BOOT NODE1
```

- 소스: OF_Batch_MVS_7.1_TJES-Guide_v3.1.3_jp.pdf (p.21)
```

### 2.3 학습 데이터 구조

```json
{
  "name": "tjesmgr BOOT",
  "type": "command",
  "description": "TJES 노드를 초기화합니다.",
  "syntax": "tjesmgr BOOT [nodename]",
  "parameters": [
    {"name": "nodename", "required": false, "description": "초기화할 노드 이름"}
  ],
  "examples": ["tjesmgr BOOT", "tjesmgr BOOT NODE1"],
  "parent_command": "tjesmgr",
  "sub_command": "BOOT",
  "product": "OF_TJES",
  "source_file": "OF_Batch_MVS_7.1_TJES-Guide_v3.1.3_jp.pdf",
  "source_page": 21,
  "aliases": ["tjesmgr boot", "TJESMGR BOOT"]
}
```

---

## 3. 구현 아키텍처

### 3.1 전체 파이프라인

```
┌─────────────────────────────────────────────────────────────────┐
│                    Summary Restructure Pipeline                  │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  Phase 1: 기존 요약본 분석                                       │
│  ─────────────────────────                                       │
│  uploads/summaries/commands/*.md                                │
│       ↓                                                         │
│  - 파일명에서 Manager 식별                                       │
│  - 각 "## " 헤더 파싱                                           │
│  - syntax, description 추출                                      │
│       ↓                                                         │
│  중간 결과: parsed_summaries.json                               │
│                                                                  │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  Phase 2: Manager-서브명령어 매핑                                │
│  ─────────────────────────────                                   │
│  - 파일명 → Manager 매핑 적용                                   │
│  - 서브명령어에 Manager 접두사 추가                             │
│  - syntax에 Manager가 없으면 추가                               │
│       ↓                                                         │
│  중간 결과: mapped_commands.json                                │
│                                                                  │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  Phase 3: 키워드 매칭 및 병합                                    │
│  ─────────────────────────────                                   │
│  docs/keyword.txt (43,147개)                                    │
│       ↓                                                         │
│  - 각 키워드에 대해 매핑된 명령어 찾기                          │
│  - 여러 소스의 정보 병합 (가장 완전한 정보 선택)                │
│  - 미발견 키워드는 PDF 직접 검색                                │
│       ↓                                                         │
│  중간 결과: keyword_matched.json                                │
│                                                                  │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  Phase 4: 최종 학습 데이터 생성                                  │
│  ─────────────────────────────                                   │
│  - 품질 검증 (syntax 필수, description 필수)                    │
│  - 중복 제거                                                     │
│  - QLoRA 형식 변환                                              │
│       ↓                                                         │
│  최종 결과:                                                      │
│  - restructured_learning_dataset.json                           │
│  - qlora_train.jsonl                                            │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

### 3.2 핵심 클래스 설계

```python
class SummaryRestructurer:
    """요약본 재구조화 메인 클래스"""

    MANAGER_MAPPING = {...}  # 파일명-Manager 매핑

    def parse_all_summaries(self) -> Dict[str, List[CommandInfo]]:
        """모든 요약본 파일 파싱"""
        pass

    def apply_manager_mapping(self, commands: List[CommandInfo]) -> List[CommandInfo]:
        """Manager-서브명령어 매핑 적용"""
        pass

    def merge_duplicates(self, commands: List[CommandInfo]) -> List[CommandInfo]:
        """중복 명령어 병합 (가장 완전한 정보 선택)"""
        pass


class KeywordMatcher:
    """키워드-명령어 매칭"""

    def __init__(self, commands: List[CommandInfo], keywords: List[str]):
        self.commands = commands
        self.keywords = keywords
        self.command_index = self._build_index()  # 빠른 검색을 위한 인덱스

    def match_keyword(self, keyword: str) -> Optional[CommandInfo]:
        """키워드에 매칭되는 명령어 찾기"""
        # 1. 정확히 일치
        # 2. 대소문자 무시 일치
        # 3. 서브명령어로 일치 (BOOT → tjesmgr BOOT)
        # 4. 별칭으로 일치
        pass

    def match_all(self) -> Dict[str, CommandInfo]:
        """모든 키워드 매칭"""
        pass


class LearningDataGenerator:
    """최종 학습 데이터 생성"""

    def generate(self, matched: Dict[str, CommandInfo]) -> Dict:
        """학습 데이터 생성"""
        pass

    def validate(self, item: Dict) -> bool:
        """품질 검증"""
        # syntax 필수
        # description 필수
        # 유효한 product
        pass

    def to_qlora_format(self, items: List[Dict]) -> List[Dict]:
        """QLoRA 형식 변환"""
        pass
```

---

## 4. 키워드 매칭 전략

### 4.1 매칭 우선순위

```
1. 정확히 일치 (exact match)
   - "tjesmgr BOOT" → commands["tjesmgr BOOT"]

2. 대소문자 무시 (case insensitive)
   - "Tjesmgr Boot" → commands["tjesmgr BOOT"]

3. Manager만 일치 (parent command)
   - "tjesmgr" → 모든 tjesmgr 서브명령어 반환

4. 서브명령어만 일치 (sub command)
   - "BOOT" → commands["tjesmgr BOOT"] (TJES 파일에서)

5. 별칭 일치 (aliases)
   - "TJESMGR" → commands["tjesmgr"]
```

### 4.2 특수 케이스 처리

| 케이스 | 예시 | 처리 방법 |
|--------|------|-----------|
| Manager만 | `tjesmgr` | 대표 설명 + 서브명령어 목록 |
| 옵션 플래그 | `-h`, `-v` | `tjesmgr -h`, `oscmgr -h` 등으로 확장 |
| 에러 코드 | `ABEND S0C7` | error-codes 폴더에서 검색 |
| 설정 파일 | `tjes.conf` | configs 폴더에서 검색 |
| API 함수 | `DSALC_*` | apis 폴더에서 검색 |

---

## 5. 품질 보증

### 5.1 필수 검증 항목

```python
VALIDATION_RULES = {
    "command": {
        "syntax": "required",      # 반드시 있어야 함
        "description": "required",  # 반드시 있어야 함
        "product": "required",      # 반드시 있어야 함
    },
    "config": {
        "syntax": "optional",       # 선택
        "description": "required",
        "parameters": "required",   # 설정 파라미터 목록
    },
    "error": {
        "code": "required",         # 에러 코드
        "description": "required",
        "cause": "optional",        # 원인
        "solution": "optional",     # 해결방법
    },
}
```

### 5.2 최종 검증 체크리스트

- [ ] tjesmgr: syntax 있음, TJES 설명 포함, JES2 언급 없음
- [ ] oscmgr: syntax 있음, OSC 설명 포함
- [ ] tacfmgr: syntax 있음, TACF 설명 포함
- [ ] hidbmgr: syntax 있음, HiDB 설명 포함
- [ ] 모든 Manager 서브명령어: Manager 접두사 포함
- [ ] 에러 코드 2,191개: 설명 포함
- [ ] 설정 파일: 파라미터 목록 포함

---

## 6. 구현 계획

### 6.1 파일 구조

```
scripts/training/
├── restructure_summaries.py      # 메인 실행 파일
├── parsers/
│   ├── __init__.py
│   ├── summary_parser.py         # 요약본 파싱
│   ├── manager_mapper.py         # Manager 매핑
│   └── keyword_matcher.py        # 키워드 매칭
├── generators/
│   ├── __init__.py
│   ├── learning_data.py          # 학습 데이터 생성
│   └── qlora_converter.py        # QLoRA 변환
└── validators/
    ├── __init__.py
    └── quality_checker.py        # 품질 검증
```

### 6.2 실행 순서

```bash
# 1. 요약본 재구조화 (약 1분)
python scripts/training/restructure_summaries.py parse

# 2. Manager 매핑 적용 (약 30초)
python scripts/training/restructure_summaries.py map

# 3. 키워드 매칭 (약 2분)
python scripts/training/restructure_summaries.py match

# 4. 학습 데이터 생성 (약 1분)
python scripts/training/restructure_summaries.py generate

# 5. 품질 검증
python scripts/training/restructure_summaries.py validate

# 또는 전체 실행
python scripts/training/restructure_summaries.py all
```

---

## 7. 예상 결과물

### 7.1 출력 파일

| 파일 | 내용 | 예상 크기 |
|------|------|-----------|
| `parsed_summaries.json` | 파싱된 요약본 | ~5MB |
| `mapped_commands.json` | Manager 매핑된 명령어 | ~6MB |
| `keyword_matched.json` | 키워드 매칭 결과 | ~15MB |
| `restructured_learning_dataset.json` | 최종 학습 데이터 | ~20MB |
| `qlora_train.jsonl` | QLoRA 학습 데이터 | ~30MB |

### 7.2 품질 목표

| 항목 | 목표 | 측정 방법 |
|------|------|-----------|
| Manager 명령어 syntax 완성도 | 100% | syntax != null |
| 키워드 매칭률 | ≥ 80% | 매칭된 키워드 / 전체 키워드 |
| 할루시네이션 | 0개 | E2E 테스트 |
| 중복 항목 | 0개 | 고유 name 수 |

---

## 8. 승인 요청

### 8.1 구현 전 확인

1. 기존 요약본 백업 필요 여부
2. GPU 서버 학습 일정
3. 예상 소요 시간: 구현 2시간 + 실행 30분 + 학습 3시간

### 8.2 리스크

| 리스크 | 영향 | 대응 |
|--------|------|------|
| 요약본 포맷 불일치 | 파싱 실패 | 예외 처리 + 로그 |
| 메모리 부족 | 프로세스 중단 | 청크 단위 처리 |
| 키워드 미매칭 | 학습 데이터 부족 | PDF 직접 검색 폴백 |
