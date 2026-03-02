# Summary Quality Improvement - Design Document

> **Feature**: summary-quality-improvement
> **Version**: v1.0
> **Created**: 2026-02-03
> **Author**: Claude Opus 4.5
> **Plan Reference**: docs/01-plan/features/summary-quality-improvement.plan.md

## 1. 설계 개요

### 1.1 목적

`uploads/summaries/` 요약본 데이터의 품질을 개선하여 RAG 검색 정확도를 향상시키고 Hallucination을 방지합니다.

### 1.2 핵심 문제

| 문제 | 원인 | 영향 |
|------|------|------|
| 불완전한 설명 | "8.30. osctdlrm" (장 번호만) | LLM이 컨텍스트 부족으로 잘못된 정보 생성 |
| 중복 항목 | oscdown(3회), oscboot(3회) | 검색 결과 혼란, 일관성 저하 |
| 타입 분류 오류 | osctdlrm이 concept로 분류 | 검색 필터링 오류 |

### 1.3 해결 전략

```
Phase 1: 품질 검사 (Detection)
├── QualityChecker 클래스 구현
├── 불완전 설명, 중복, 분류 오류 탐지
└── quality_report.json 생성
    ↓
Phase 2: 데이터 보완 (Enhancement)
├── PDF 원본에서 상세 설명 재추출
├── 중복 항목 병합
└── 타입 재분류
    ↓
Phase 3: 요약본 재생성 (Regeneration)
├── commands/*.md 업데이트
├── index.json 재생성
└── learning_dataset.json 재생성
```

## 2. 컴포넌트 설계

### 2.1 QualityChecker 클래스

**파일**: `scripts/manual_processor/quality_checker.py`

```python
class QualityChecker:
    """요약본 품질 검사기

    세 가지 품질 문제를 탐지합니다:
    1. 불완전한 설명 (장 번호만 있는 항목)
    2. 중복 항목 (같은 이름의 여러 항목)
    3. 타입 분류 오류 (command 패턴이지만 concept으로 분류)
    """

    # 불완전 설명 패턴 (장 번호만)
    INCOMPLETE_PATTERNS = [
        r'^[\d.]+\s+\w+$',           # "8.30. osctdlrm"
        r'^第[\d]+章',                # "第8章"
        r'^Chapter\s+\d+',           # "Chapter 8"
        r'^\d+\.\d+\.\d+\s*$',       # "8.30.1"
    ]

    # 명령어 패턴 (concept으로 분류되면 안됨)
    COMMAND_PATTERNS = [
        r'^[a-z]+mgr$',              # tjesmgr, oscmgr
        r'^[a-z]+admin$',            # oscadmin
        r'^[a-z]+(init|rm|ctl)$',    # osctdlinit, osctdlrm
        r'^\$[A-Z]+',                # $DISPLAY, $START
        r'^tmboot|tmdown|ofboot|ofdown$',  # 시스템 명령어
    ]

    def check_all(self, summaries_dir: Path) -> QualityReport:
        """모든 품질 검사 수행"""

    def check_incomplete_descriptions(self, items: List[dict]) -> List[IncompleteItem]:
        """불완전한 설명 검출"""

    def check_duplicates(self, items: List[dict]) -> Dict[str, List[dict]]:
        """중복 항목 검출"""

    def check_type_classification(self, items: List[dict]) -> List[MisclassifiedItem]:
        """타입 분류 오류 검출"""
```

### 2.2 데이터 모델

**파일**: `scripts/manual_processor/models/quality.py`

```python
from dataclasses import dataclass, field
from typing import List, Dict, Optional
from enum import Enum

class QualityIssueType(Enum):
    INCOMPLETE_DESCRIPTION = "incomplete_description"
    DUPLICATE_ENTRY = "duplicate_entry"
    TYPE_MISCLASSIFICATION = "type_misclassification"

@dataclass
class IncompleteItem:
    """불완전한 설명 항목"""
    name: str
    description: str           # 현재 (불완전한) 설명
    source_file: str           # 원본 마크다운 파일
    pdf_source: Optional[str]  # 원본 PDF
    page: Optional[int]        # PDF 페이지
    suggested_fix: str = ""    # 보완 제안

@dataclass
class DuplicateGroup:
    """중복 항목 그룹"""
    name: str
    items: List[dict]          # 중복된 항목들
    best_item: Optional[dict]  # 가장 완전한 항목
    merge_strategy: str        # "keep_best" | "merge_all"

@dataclass
class MisclassifiedItem:
    """분류 오류 항목"""
    name: str
    current_type: str          # 현재 타입 (잘못된)
    suggested_type: str        # 제안 타입
    pattern_matched: str       # 매칭된 패턴
    confidence: float          # 신뢰도 (0-1)

@dataclass
class QualityReport:
    """품질 검사 리포트"""
    total_items: int
    incomplete_items: List[IncompleteItem] = field(default_factory=list)
    duplicate_groups: List[DuplicateGroup] = field(default_factory=list)
    misclassified_items: List[MisclassifiedItem] = field(default_factory=list)

    @property
    def incomplete_count(self) -> int:
        return len(self.incomplete_items)

    @property
    def duplicate_count(self) -> int:
        return sum(len(g.items) - 1 for g in self.duplicate_groups)

    @property
    def misclassified_count(self) -> int:
        return len(self.misclassified_items)

    @property
    def quality_score(self) -> float:
        """품질 점수 (0-100)"""
        if self.total_items == 0:
            return 100.0
        issues = self.incomplete_count + self.duplicate_count + self.misclassified_count
        return max(0, (1 - issues / self.total_items) * 100)

    def to_dict(self) -> dict:
        """JSON 직렬화"""
        pass
```

### 2.3 품질 개선기 (Enhancer)

**파일**: `scripts/manual_processor/quality_enhancer.py`

```python
class QualityEnhancer:
    """요약본 품질 개선기

    QualityChecker가 탐지한 문제를 수정합니다.
    """

    def __init__(self, pdf_parser: PDFParser, summaries_dir: Path):
        self.pdf_parser = pdf_parser
        self.summaries_dir = summaries_dir

    def enhance_all(self, report: QualityReport) -> EnhancementResult:
        """모든 품질 문제 수정"""

    def fix_incomplete_description(self, item: IncompleteItem) -> Optional[str]:
        """PDF에서 상세 설명 재추출

        1. 원본 PDF 로드
        2. 해당 항목이 있는 페이지 찾기
        3. 컨텍스트 윈도우 내에서 설명 추출
        4. 추출된 설명 반환
        """

    def merge_duplicates(self, group: DuplicateGroup) -> dict:
        """중복 항목 병합

        전략:
        1. 가장 완전한 설명 선택
        2. 모든 소스 파일 병합
        3. syntax 정보 병합
        4. 중복 제거된 단일 항목 반환
        """

    def reclassify_type(self, item: MisclassifiedItem) -> str:
        """타입 재분류

        command 패턴과 매칭되면 "command"로 변경
        """
```

### 2.4 설명 추출 알고리즘

```python
def extract_description_from_pdf(
    pdf_path: Path,
    item_name: str,
    page_hint: Optional[int] = None
) -> Optional[str]:
    """PDF에서 항목 설명 추출

    Algorithm:
    1. 항목 이름 위치 찾기
    2. 다음 항목 또는 섹션 시작 전까지 텍스트 추출
    3. 설명 패턴 매칭 및 정제

    Args:
        pdf_path: PDF 파일 경로
        item_name: 찾을 항목 이름
        page_hint: 힌트 페이지 번호 (optional)

    Returns:
        추출된 설명 또는 None
    """

    # 컨텍스트 윈도우 설정
    CONTEXT_BEFORE = 100   # 항목 이전 문자
    CONTEXT_AFTER = 2000   # 항목 이후 문자 (설명 추출 범위)

    # 1. PDF 로드 및 텍스트 추출
    content = pdf_parser.parse(pdf_path)
    text = content.full_text

    # 2. 항목 위치 찾기
    pattern = rf'\b{re.escape(item_name)}\b'
    matches = list(re.finditer(pattern, text, re.IGNORECASE))

    if not matches:
        return None

    # 3. 가장 적합한 매치 선택 (페이지 힌트 활용)
    best_match = select_best_match(matches, page_hint, content)

    # 4. 컨텍스트 추출
    start = best_match.end()
    end = min(len(text), start + CONTEXT_AFTER)
    context = text[start:end]

    # 5. 설명 패턴 추출
    description = extract_description_patterns(context, item_name)

    return description


def extract_description_patterns(context: str, item_name: str) -> Optional[str]:
    """컨텍스트에서 설명 패턴 추출

    패턴 우선순위:
    1. "は、〜です。" (일본어 정의)
    2. "は〜するためのツールです" (도구 설명)
    3. "を〜します" (동작 설명)
    4. 첫 번째 마침표까지
    """

    patterns = [
        # 일본어 정의 패턴
        rf'{item_name}は[、,]?([^。]+)。',
        rf'{item_name}は([^。]+ための[^。]+)です。',
        rf'{item_name}は([^。]+を[^。]+)します。',
        # 영문 정의 패턴
        rf'{item_name}\s+is\s+([^.]+)\.',
        rf'{item_name}\s+-\s+([^.]+)\.',
    ]

    for pattern in patterns:
        match = re.search(pattern, context, re.IGNORECASE)
        if match:
            description = match.group(0).strip()
            # 최대 500자로 제한
            return description[:500] if len(description) > 500 else description

    # 폴백: 첫 번째 문장
    first_sentence = re.match(r'^[^。.]+[。.]', context)
    if first_sentence:
        return first_sentence.group(0).strip()[:300]

    return None
```

## 3. 데이터 흐름

### 3.1 전체 파이프라인

```
┌─────────────────────────────────────────────────────────────────┐
│                    Quality Improvement Pipeline                  │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  uploads/summaries/          scripts/manual_processor/          │
│  ┌──────────────────┐       ┌──────────────────────────┐       │
│  │ commands/*.md    │──────▶│ QualityChecker           │       │
│  │ index.json       │       │   .check_incomplete()    │       │
│  │ learning_        │       │   .check_duplicates()    │       │
│  │   dataset.json   │       │   .check_classification()│       │
│  └──────────────────┘       └───────────┬──────────────┘       │
│                                         │                       │
│                                         ▼                       │
│                             ┌──────────────────────────┐       │
│                             │ quality_report.json      │       │
│                             │ - incomplete_items[]     │       │
│                             │ - duplicate_groups[]     │       │
│                             │ - misclassified_items[]  │       │
│                             └───────────┬──────────────┘       │
│                                         │                       │
│                                         ▼                       │
│  uploads/manuals/           ┌──────────────────────────┐       │
│  ┌──────────────────┐       │ QualityEnhancer          │       │
│  │ *.pdf (245개)    │──────▶│   .fix_incomplete()      │       │
│  └──────────────────┘       │   .merge_duplicates()    │       │
│                             │   .reclassify_type()     │       │
│                             └───────────┬──────────────┘       │
│                                         │                       │
│                                         ▼                       │
│  uploads/summaries/         ┌──────────────────────────┐       │
│  ┌──────────────────┐       │ MarkdownGenerator        │       │
│  │ commands/*.md    │◀──────│ IndexGenerator           │       │
│  │ index.json       │       │ LearningDatasetGenerator │       │
│  │ learning_        │       └──────────────────────────┘       │
│  │   dataset.json   │                                          │
│  └──────────────────┘                                          │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### 3.2 불완전 설명 수정 흐름

```
IncompleteItem                PDF 원본                    Updated Item
┌──────────────────┐         ┌─────────────────┐        ┌──────────────────┐
│ name: osctdlrm   │         │ OSC Admin Guide │        │ name: osctdlrm   │
│ desc: "8.30..."  │───▶     │ p.55:           │───▶    │ desc: "osctdlrm  │
│ source: O.md     │  찾기   │ "osctdlrmは、   │ 추출   │   は、TDL共有    │
│ pdf: OSC_*.pdf   │         │  TDL共有メモリ  │        │   メモリを完全に │
│ page: 55         │         │  を完全に..."   │        │   削除する..."   │
└──────────────────┘         └─────────────────┘        └──────────────────┘
```

### 3.3 중복 병합 흐름

```
DuplicateGroup                         Merged Item
┌────────────────────────────────┐    ┌────────────────────────────┐
│ name: oscdown                  │    │ name: oscdown              │
│ items:                         │    │ type: command              │
│   [1] type: command            │    │ syntax: oscdown [options]  │
│       desc: "リージョンを..."   │    │ desc: "リージョンを停止    │
│       source: O.md             │───▶│   するユーティリティです"   │
│   [2] type: concept            │    │ sources:                   │
│       desc: "8.25. oscdown"    │    │   - O.md                   │
│       source: OSC_MVS.md       │    │   - OSC_MVS.md            │
│   [3] type: command            │    │   - OSC_Admin.md          │
│       syntax: "oscdown..."     │    │ product: OpenFrame_OSC    │
│       source: OSC_Admin.md     │    └────────────────────────────┘
└────────────────────────────────┘
```

## 4. API 설계

### 4.1 CLI 명령어

```bash
# 품질 검사만 실행
python -m scripts.manual_processor.main quality-check
# Output: uploads/summaries/quality_report.json

# 품질 검사 + 자동 수정
python -m scripts.manual_processor.main quality-improve
# Output: 수정된 요약본 파일들

# 특정 카테고리만 검사
python -m scripts.manual_processor.main quality-check --category commands
python -m scripts.manual_processor.main quality-check --category configs

# dry-run (변경 없이 미리보기)
python -m scripts.manual_processor.main quality-improve --dry-run

# 특정 항목만 수정
python -m scripts.manual_processor.main quality-fix osctdlrm
```

### 4.2 CLI 인터페이스 추가 (main.py)

```python
# quality-check 명령
check_parser = subparsers.add_parser(
    "quality-check",
    help="요약본 품질 검사"
)
check_parser.add_argument(
    "--category", "-c",
    choices=["all", "commands", "configs", "apis", "concepts"],
    default="all",
    help="검사할 카테고리 (기본: all)"
)
check_parser.add_argument(
    "--output", "-o",
    type=Path,
    default=None,
    help="리포트 출력 경로 (기본: summaries/quality_report.json)"
)

# quality-improve 명령
improve_parser = subparsers.add_parser(
    "quality-improve",
    help="요약본 품질 개선 (검사 + 자동 수정)"
)
improve_parser.add_argument(
    "--dry-run",
    action="store_true",
    help="변경 없이 미리보기"
)
improve_parser.add_argument(
    "--skip-pdf-extraction",
    action="store_true",
    help="PDF 재추출 건너뛰기 (빠른 실행)"
)
```

## 5. 파일 구조

### 5.1 새로 생성할 파일

```
scripts/manual_processor/
├── quality_checker.py         # 품질 검사기 (NEW)
├── quality_enhancer.py        # 품질 개선기 (NEW)
├── models/
│   └── quality.py             # 품질 관련 데이터 모델 (NEW)
└── main.py                    # CLI 명령어 추가 (MODIFY)

uploads/summaries/
└── quality_report.json        # 품질 검사 리포트 (NEW)
```

### 5.2 수정할 파일

| 파일 | 수정 내용 |
|------|----------|
| `main.py` | quality-check, quality-improve CLI 명령 추가 |
| `commands/*.md` | 불완전 설명 보완, 중복 제거 |
| `index.json` | 업데이트된 메타데이터 반영 |
| `learning_dataset.json` | 개선된 데이터로 재생성 |

## 6. 테스트 전략

### 6.1 단위 테스트

```python
# tests/unit/test_quality_checker.py

def test_detect_incomplete_description():
    """불완전 설명 탐지 테스트"""
    items = [
        {"name": "osctdlrm", "description": "8.30. osctdlrm"},  # 불완전
        {"name": "oscboot", "description": "リージョンを起動します"},  # 완전
    ]

    checker = QualityChecker()
    incomplete = checker.check_incomplete_descriptions(items)

    assert len(incomplete) == 1
    assert incomplete[0].name == "osctdlrm"

def test_detect_duplicates():
    """중복 항목 탐지 테스트"""
    items = [
        {"name": "oscdown", "source": "O.md"},
        {"name": "oscdown", "source": "OSC_MVS.md"},
        {"name": "oscdown", "source": "OSC_Admin.md"},
        {"name": "tjesmgr", "source": "TJES.md"},  # 유일
    ]

    checker = QualityChecker()
    duplicates = checker.check_duplicates(items)

    assert "oscdown" in duplicates
    assert len(duplicates["oscdown"]) == 3
    assert "tjesmgr" not in duplicates

def test_detect_type_misclassification():
    """타입 분류 오류 탐지 테스트"""
    items = [
        {"name": "osctdlrm", "type": "concept"},   # 오류: command여야 함
        {"name": "tjesmgr", "type": "concept"},    # 오류: command여야 함
        {"name": "TJES", "type": "concept"},       # 정상
    ]

    checker = QualityChecker()
    misclassified = checker.check_type_classification(items)

    assert len(misclassified) == 2
    assert all(m.suggested_type == "command" for m in misclassified)
```

### 6.2 통합 테스트

```python
# tests/integration/test_quality_pipeline.py

async def test_full_quality_improvement_pipeline():
    """전체 품질 개선 파이프라인 테스트"""

    # 1. 품질 검사
    checker = QualityChecker()
    report = checker.check_all(Path("uploads/summaries"))

    initial_score = report.quality_score

    # 2. 품질 개선
    enhancer = QualityEnhancer(pdf_parser, summaries_dir)
    result = enhancer.enhance_all(report)

    # 3. 재검사
    final_report = checker.check_all(Path("uploads/summaries"))
    final_score = final_report.quality_score

    # 4. 검증
    assert final_score > initial_score
    assert final_report.incomplete_count < report.incomplete_count

async def test_osctdlrm_hallucination_resolved():
    """osctdlrm Hallucination 해결 검증"""

    # 개선 후 RAG 쿼리 테스트
    response = await rag_query("osctdlrmについて説明してください")

    # 올바른 정보 포함 확인
    assert "osctdlrm" in response.lower()
    assert "TDL" in response or "共有メモリ" in response

    # Hallucination 없음 확인
    assert "oscadmin osctdlrm" not in response  # 이 조합은 존재하지 않음
```

## 7. 성공 기준

| 기준 | 목표 | 측정 방법 |
|------|------|----------|
| 불완전 설명 비율 | 0% | `quality_report.incomplete_count == 0` |
| 중복 항목 수 | 0개 | `quality_report.duplicate_count == 0` |
| 타입 분류 정확도 | 100% | `quality_report.misclassified_count == 0` |
| 품질 점수 | 95+ | `quality_report.quality_score >= 95` |
| osctdlrm Hallucination | 해결 | E2E 테스트 통과 |
| 처리 시간 | < 30분 | 전체 파이프라인 실행 시간 |

## 8. 위험 요소 및 대응

| 위험 | 영향 | 대응 |
|------|------|------|
| PDF 파싱 실패 | 일부 설명 추출 불가 | 수동 보완 플래그 + fallback |
| 자동 병합 오류 | 잘못된 정보 병합 | dry-run 모드로 사전 검증 |
| 대량 변경 부작용 | 기존 학습 데이터 영향 | 백업 후 진행 + 버전 관리 |

## 9. 구현 순서

```
Day 1 (Phase 1):
├── [1.1] quality.py 데이터 모델 구현
├── [1.2] QualityChecker 클래스 구현
├── [1.3] quality-check CLI 명령 추가
└── [1.4] quality_report.json 생성 테스트

Day 2 (Phase 2):
├── [2.1] QualityEnhancer 클래스 구현
├── [2.2] PDF 설명 재추출 로직 구현
├── [2.3] 중복 병합 로직 구현
└── [2.4] 타입 재분류 로직 구현

Day 3 (Phase 3):
├── [3.1] quality-improve CLI 명령 추가
├── [3.2] 요약본 파일 업데이트 로직 구현
├── [3.3] learning_dataset.json 재생성
└── [3.4] 전체 파이프라인 테스트

Day 4 (Phase 4):
├── [4.1] E2E osctdlrm Hallucination 테스트
├── [4.2] 품질 점수 검증
└── [4.3] 최종 리포트 생성
```

---

**참조 파일**:
- Plan: `docs/01-plan/features/summary-quality-improvement.plan.md`
- 기존 파서: `scripts/manual_processor/parsers/content_parser.py`
- 요약본 위치: `uploads/summaries/`
- 원본 PDF: `uploads/manuals/`
