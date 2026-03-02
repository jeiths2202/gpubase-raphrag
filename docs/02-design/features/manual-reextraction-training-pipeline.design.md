# Manual Re-extraction & Training Pipeline Design

> **Feature**: manual-reextraction-training-pipeline
> **Created**: 2026-02-20
> **Author**: Claude Opus 4.6
> **Status**: Design Phase
> **Plan Reference**: `docs/01-plan/features/manual-reextraction-training-pipeline.plan.md`

## 1. 설계 개요

기존 `scripts/manual_processor/` 패키지를 **확장(extend)** 하는 방식으로 구현합니다.
새 패키지를 별도로 만들지 않고, 기존 패키지에 모듈을 추가하여 코드 재사용을 극대화합니다.

### 1.1 설계 원칙

| 원칙 | 설명 |
|------|------|
| **기존 코드 재사용** | `manual_processor/` 패키지 확장, `config.py` 공유 |
| **단일 진입점** | `main.py`에 새 커맨드 추가 (`reextract`, `gen-training`, `validate-training`) |
| **멱등성** | 동일 입력 → 동일 출력, `--force` 없으면 기존 파일 건너뜀 |
| **점진적 실행** | Phase별 독립 실행 가능, 전체도 `run-all`로 실행 가능 |
| **검증된 로직 재사용** | `fix_error_descriptions.py`의 Format A/B 로직 통합 |

### 1.2 변경 범위

```
scripts/manual_processor/
├── main.py                          # [수정] 새 커맨드 3개 추가
├── config.py                        # [수정] 학습 데이터 경로, 제품 매핑 추가
├── parsers/
│   ├── pdf_parser.py                # [기존] PyMuPDF 텍스트 추출 (재사용)
│   ├── error_parser.py              # [대체] fix_error_descriptions.py 로직으로 교체
│   ├── comprehensive_parser.py      # [기존] 명령어/설정/API 추출 (재사용)
│   ├── content_parser.py            # [기존] 용어 추출 (재사용)
│   ├── structure_parser.py          # [기존] TOC 구조 (재사용)
│   └── strategy_aware_parser.py     # [기존] 전략 기반 추출 (재사용)
├── generators/
│   ├── markdown_generator.py        # [기존] 요약본 Markdown (재사용)
│   ├── comprehensive_generator.py   # [기존] commands/configs 생성 (재사용)
│   ├── index_generator.py           # [기존] 인덱스 생성 (재사용)
│   ├── sft_generator.py             # [신규] SFT ChatML 학습 데이터 생성
│   ├── cpt_generator.py             # [신규] CPT Plain Text 학습 데이터 생성
│   └── dpo_generator.py             # [신규] DPO Preference 학습 데이터 생성
├── validators/
│   └── training_validator.py        # [신규] 학습 데이터 품질 검증 (5개 검증 통합)
└── models/
    ├── chunk.py                     # [기존] 청크 모델 (재사용)
    └── training.py                  # [신규] SFT/DPO/CPT 데이터 모델
```

## 2. 데이터 모델

### 2.1 학습 데이터 모델 (`models/training.py`)

```python
from dataclasses import dataclass, field
from typing import List, Optional, Dict
from enum import Enum


class TrainingFormat(str, Enum):
    SFT = "sft"          # Supervised Fine-Tuning (ChatML)
    CPT = "cpt"          # Continued Pre-Training (Plain Text)
    DPO = "dpo"          # Direct Preference Optimization


class DataLanguage(str, Enum):
    JA = "ja"
    KO = "ko"
    EN = "en"


@dataclass
class SFTRecord:
    """SFT 학습 데이터 레코드 (ChatML 포맷)"""
    instruction: str        # 사용자 질문
    response: str           # 모델 응답
    system_prompt: str      # 시스템 프롬프트
    product: str            # 제품 ID (e.g., "openframe_batch_v2")
    language: DataLanguage  # 언어
    source_file: str        # 원본 PDF 파일명
    source_page: int = 0    # 원본 페이지
    item_type: str = ""     # error/command/config/api/concept

    def to_chatml(self) -> str:
        """Qwen2.5 ChatML 포맷 변환"""
        return (
            f"<|im_start|>system\n{self.system_prompt}<|im_end|>\n"
            f"<|im_start|>user\n{self.instruction}<|im_end|>\n"
            f"<|im_start|>assistant\n{self.response}<|im_end|>"
        )

    def to_jsonl(self) -> dict:
        """JSONL 출력용 dict"""
        return {
            "text": self.to_chatml(),
            "product": self.product,
            "language": self.language.value,
            "source": self.source_file,
            "type": self.item_type,
        }


@dataclass
class DPORecord:
    """DPO 학습 데이터 레코드 (Preference Pair)"""
    prompt: str             # ChatML prompt (system + user)
    chosen: str             # 선호 응답 (정답 제품 기반)
    rejected: str           # 비선호 응답 (교차 제품 / 환각)
    product: str
    language: DataLanguage
    strategy: str           # cross_product / fact_mutation / summary_cross


@dataclass
class CPTChunk:
    """CPT 학습 데이터 청크 (Plain Text)"""
    text: str               # 원문 텍스트 (최대 4096 tokens)
    product: str
    language: DataLanguage
    source_file: str
    token_count: int = 0


@dataclass
class TrainingStats:
    """학습 데이터 생성 통계"""
    total_records: int = 0
    by_format: Dict[str, int] = field(default_factory=dict)
    by_language: Dict[str, int] = field(default_factory=dict)
    by_product: Dict[str, int] = field(default_factory=dict)
    by_type: Dict[str, int] = field(default_factory=dict)
    train_count: int = 0
    eval_count: int = 0
    quality_score: float = 0.0
```

### 2.2 제품 매핑 (config.py 확장)

```python
# 디렉토리명 → Multi-LoRA 제품 ID 매핑
DIRECTORY_TO_PRODUCT = {
    "MVS_Openframe 7.1_v3.1.3_JP": "openframe_common_v2",
    "MSP_Openframe 7.3_v2.1.1_JP": "openframe_common_v2",
    "XSP_Openframe 7.3_v3.2.1_JP": "openframe_common_v2",
    "VOS3_Openframe 2.0 _v2.1.1 _JP": "openframe_vos3_v2",
    "Tibero 7 FixSet01 Manual Set v2.1.1_jp": "tibero7_v2",
    "Tmax_6.0_v2.1.1_JP": "tmax_v2",
    "JEUS_8.5_v2.1.1_KR": "jeus_v2",
    "JEUS_8_v2.1.1_JP": "jeus_v2",
    "OFCOBOL_4_v3.1.2_JP": "ofcobol_v2",
    "OFAsm_4_v3.1.2_JP": "ofasm_v2",
    "OFGW_7_v2.1.3_JP": "openframe_gateway_v2",
    "OFManager_7.2_v3.1.2_JP": "ofmanager_v2",
    "OFMiner_7Fix1_v2.1.5_JP": "ofminer_v2",
    "OFPli_3_v2.1.2_JP": "ofpli_v2",
    "OFStudio_7_v2.1.1_JP": "ofstudio_v2",
    "ProSort_2SP3_v2.1.3_JP": "prosort_v2",
    "ProSync_FS01_JP": "prosync_v2",
    "ProTrieve_v2_1_JP": "protrieve_v2",
    "WebtoB_5Fix2_v2.1.3_JP": "webtob_v2",
}

# 디렉토리명 → 언어 감지
DIRECTORY_LANGUAGE = {
    "JEUS_8.5_v2.1.1_KR": "ko",
    # 나머지는 모두 "ja"
}

# 학습 데이터 출력 경로
TRAINING_OUTPUT_DIR = "uploads/training/v10"
```

## 3. 컴포넌트 상세 설계

### 3.1 Phase 1: 전체 PDF 재추출 (main.py `reextract` 커맨드)

기존 `process_all()` 메서드를 확장하여 **모든 245 PDF를 처음부터 재추출**합니다.

#### 처리 흐름

```
reextract 커맨드
│
├─ [1/4] Error Reference Guide 재추출
│   ├─ fix_error_descriptions.py 로직 통합
│   ├─ Format A/B 자동 감지
│   ├─ 40+ 모듈 매핑
│   └─ → uploads/summaries/error-codes/*.md (갱신)
│
├─ [2/4] 일반 가이드 용어 추출
│   ├─ ContentParser.parse() 사용 (기존)
│   └─ → uploads/summaries/glossary/*.md (갱신)
│
├─ [3/4] 포괄적 추출 (명령어/설정/API)
│   ├─ ComprehensiveParser.process_all_manuals() 사용 (기존)
│   └─ → uploads/summaries/commands|configs|apis/*.md (갱신)
│
└─ [4/4] 인덱스 재생성
    └─ IndexGenerator.rebuild_all() 사용 (기존)
```

#### 에러 파서 교체 설계

기존 `error_parser.py`의 regex 기반 로직을 `fix_error_descriptions.py`의 검증된 로직으로 교체합니다.

```python
# error_parser.py 교체 핵심 변경
class ErrorCodeParser:
    """에러코드 파서 (Format A/B 자동감지)"""

    def parse_pdf_directly(self, pdf_path: Path) -> Dict[str, ErrorCodeModule]:
        """PDF에서 직접 에러코드 추출 (fix_error_descriptions.py 로직)

        기존: content = pdf_parser.parse(pdf) → error_parser.parse(content)
        신규: error_parser.parse_pdf_directly(pdf)  ← PDF 직접 열기

        이유: PyMuPDF의 페이지별 텍스트를 직접 제어해야
              Format A/B 감지가 정확함
        """
        doc = pymupdf.open(str(pdf_path))
        page_count = len(doc)
        full_text = ""
        for page_num in range(page_count):
            page = doc[page_num]
            full_text += page.get_text() + "\n"
        doc.close()

        # 1. TOC 라인 필터
        full_text = TOC_PATTERN.sub("", full_text)
        full_text = FOOTER_PATTERN.sub("", full_text)

        # 2. 모듈 섹션 분리
        sections = self._split_by_module(full_text)

        # 3. 각 섹션에서 에러코드 추출 (Format A/B 자동감지)
        modules = {}
        for module_name, section_text in sections.items():
            errors = self._extract_errors(section_text, module_name)
            if errors:
                modules[module_name] = ErrorCodeModule(
                    module_name=module_name,
                    errors=errors,
                    source_files=[pdf_path.name]
                )

        return modules
```

### 3.2 Phase 2: SFT 학습 데이터 생성 (`generators/sft_generator.py`)

#### 3.2.1 Q-A 템플릿 시스템

각 데이터 유형(error, command, config, api, concept)별로 3개 언어의 질문 템플릿을 정의합니다.

```python
# 유형별 질문 템플릿 (다변형)
QA_TEMPLATES = {
    "error": {
        "ja": [
            "エラーコード {code} ({name}) の原因と対処方法を教えてください。",
            "エラー {code} が発生しました。原因は何ですか？",
            "{name} エラーの解決方法は？",
            "OpenFrameで {code} エラーが出る場合の対処法は？",
        ],
        "ko": [
            "에러코드 {code} ({name})의 원인과 해결방법을 알려주세요.",
            "에러 {code}가 발생했습니다. 원인이 무엇인가요?",
            "{name} 에러 해결방법은?",
            "OpenFrame에서 {code} 에러가 발생할 때 대처법은?",
        ],
        "en": [
            "What causes error code {code} ({name}) and how to resolve it?",
            "Error {code} occurred. What is the cause?",
            "How to fix {name} error?",
            "How to handle error {code} in OpenFrame?",
        ],
    },
    "command": {
        "ja": [
            "{name} コマンドの使い方と主なオプションを教えてください。",
            "{name} の構文と使用例は？",
            "{name} コマンドについて説明してください。",
        ],
        "ko": [
            "{name} 명령어의 사용법과 주요 옵션을 알려주세요.",
            "{name}의 구문과 사용 예시는?",
            "{name} 명령어에 대해 설명해주세요.",
        ],
        "en": [
            "How to use the {name} command and its main options?",
            "What is the syntax and usage examples of {name}?",
            "Explain the {name} command.",
        ],
    },
    "config": {
        "ja": [
            "{name} 設定パラメータの説明と設定方法を教えてください。",
            "{name} の設定値とデフォルト値は？",
            "{name} パラメータの意味は？",
        ],
        "ko": [
            "{name} 설정 파라미터의 설명과 설정 방법을 알려주세요.",
            "{name}의 설정값과 기본값은?",
            "{name} 파라미터의 의미는?",
        ],
        "en": [
            "What does the {name} configuration parameter do and how to set it?",
            "What are the values and defaults for {name}?",
            "What does the {name} parameter mean?",
        ],
    },
    "api": {
        "ja": [
            "{name} 関数の使い方とパラメータを教えてください。",
            "{name}() のシグネチャと戻り値は？",
        ],
        "ko": [
            "{name} 함수의 사용법과 파라미터를 알려주세요.",
            "{name}()의 시그니처와 반환값은?",
        ],
        "en": [
            "How to use the {name} function and its parameters?",
            "What is the signature and return value of {name}()?",
        ],
    },
    "concept": {
        "ja": [
            "{name} とは何ですか？詳しく説明してください。",
            "{name} の概要と主な機能は？",
        ],
        "ko": [
            "{name}이란 무엇인가요? 자세히 설명해주세요.",
            "{name}의 개요와 주요 기능은?",
        ],
        "en": [
            "What is {name}? Please explain in detail.",
            "What is the overview and main features of {name}?",
        ],
    },
}
```

#### 3.2.2 응답 생성 전략

| 소스 | 응답 생성 방법 | 예상 비율 |
|------|---------------|----------|
| 에러코드 요약본 | `설명` + `대처방법` + `참고` 직접 사용 | 30% |
| 명령어 요약본 | `구문` + `설명` + `옵션` + `사용예` 조합 | 25% |
| 설정 요약본 | `설명` + `기본값` + `범위` 조합 | 15% |
| 용어 요약본 | `full_name` + `description` + `features` 조합 | 15% |
| PDF 원문 청크 | TOC 섹션 기반 텍스트 청크에서 Q-A 추출 | 15% |

#### 3.2.3 SFT Generator 핵심 로직

```python
class SFTGenerator:
    """SFT ChatML 학습 데이터 생성"""

    def __init__(self, summaries_dir: Path, output_dir: Path):
        self.summaries_dir = summaries_dir
        self.output_dir = output_dir
        self.records: List[SFTRecord] = []

    def generate_all(self, languages: List[str] = ["ja", "ko", "en"]) -> TrainingStats:
        """전체 SFT 데이터 생성"""
        stats = TrainingStats()

        # 1. 에러코드에서 Q-A 생성
        self._generate_from_error_codes(languages)

        # 2. 명령어에서 Q-A 생성
        self._generate_from_commands(languages)

        # 3. 설정에서 Q-A 생성
        self._generate_from_configs(languages)

        # 4. API에서 Q-A 생성
        self._generate_from_apis(languages)

        # 5. 용어/개념에서 Q-A 생성
        self._generate_from_glossary(languages)

        # 6. Train/Eval 분할 (80:20, stratified by product)
        train, eval_ = self._stratified_split(self.records, ratio=0.8)

        # 7. 출력
        self._write_jsonl(train, self.output_dir / "sft" / "train_all.jsonl")
        self._write_jsonl(eval_, self.output_dir / "sft" / "eval_all.jsonl")

        # 8. 제품별 분할 출력
        self._write_by_product(train, eval_)

        return stats

    def _generate_from_error_codes(self, languages: List[str]):
        """에러코드 요약본에서 Q-A 생성"""
        error_dir = self.summaries_dir / "error-codes"
        for md_file in error_dir.glob("*.md"):
            entries = self._parse_error_md(md_file)
            for entry in entries:
                for lang in languages:
                    templates = QA_TEMPLATES["error"][lang]
                    template = random.choice(templates)

                    instruction = template.format(
                        code=entry["code"],
                        name=entry["name"],
                    )
                    response = self._build_error_response(entry, lang)
                    product = self._detect_product_from_error(entry)
                    system_prompt = self._get_system_prompt(product, lang)

                    self.records.append(SFTRecord(
                        instruction=instruction,
                        response=response,
                        system_prompt=system_prompt,
                        product=product,
                        language=DataLanguage(lang),
                        source_file=md_file.name,
                        item_type="error",
                    ))
```

### 3.3 Phase 3: CPT 학습 데이터 생성 (`generators/cpt_generator.py`)

```python
class CPTGenerator:
    """CPT Plain Text 학습 데이터 생성"""

    MAX_CHUNK_TOKENS = 4096
    SEPARATOR = "<|endoftext|>"

    def generate_all(self, manuals_dir: Path, output_dir: Path,
                     languages: List[str] = ["ja", "ko", "en"]) -> TrainingStats:
        """전체 CPT 코퍼스 생성"""
        stats = TrainingStats()

        for lang in languages:
            chunks = []

            for product_dir in sorted(manuals_dir.iterdir()):
                if not product_dir.is_dir():
                    continue

                dir_lang = DIRECTORY_LANGUAGE.get(product_dir.name, "ja")
                if dir_lang != lang:
                    continue

                for pdf_path in sorted(product_dir.glob("*.pdf")):
                    text = self._extract_text(pdf_path)
                    pdf_chunks = self._chunk_text(text, pdf_path.name)
                    chunks.extend(pdf_chunks)

            # 코퍼스 파일 작성
            corpus_path = output_dir / "cpt" / f"corpus_{lang}.txt"
            self._write_corpus(chunks, corpus_path)

            stats.by_language[lang] = len(chunks)

        return stats

    def _chunk_text(self, text: str, source: str) -> List[CPTChunk]:
        """텍스트를 4096 토큰 이하 청크로 분할"""
        # TOC 제거, 헤더/푸터 제거
        text = self._clean_text(text)

        # 섹션 경계(제목 패턴)에서 우선 분할
        sections = re.split(r'\n(?=第?\d+[章節]|[A-Z]\.\d+|\d+\.\d+\.)', text)

        chunks = []
        current = ""
        for section in sections:
            if self._count_tokens(current + section) > self.MAX_CHUNK_TOKENS:
                if current:
                    chunks.append(CPTChunk(
                        text=current.strip(),
                        source_file=source,
                        token_count=self._count_tokens(current),
                    ))
                current = section
            else:
                current += section

        if current.strip():
            chunks.append(CPTChunk(
                text=current.strip(),
                source_file=source,
                token_count=self._count_tokens(current),
            ))

        return chunks
```

### 3.4 Phase 4: DPO 학습 데이터 생성 (`generators/dpo_generator.py`)

#### 3.4.1 3가지 생성 전략

```python
class DPOGenerator:
    """DPO Preference Pairs 생성"""

    STRATEGIES = {
        "cross_product": 0.40,     # 교차 제품 (다른 제품 정보로 응답)
        "fact_mutation": 0.35,     # 사실 변이 (숫자/이름 변경)
        "summary_cross": 0.25,    # 요약본 교차 (관련없는 요약 사용)
    }

    def generate_all(self, sft_records: List[SFTRecord],
                     target_count: int = 2000) -> List[DPORecord]:
        """SFT 레코드에서 DPO 쌍 생성"""
        dpo_records = []

        for strategy, ratio in self.STRATEGIES.items():
            count = int(target_count * ratio)
            samples = random.sample(sft_records, min(count, len(sft_records)))

            for record in samples:
                if strategy == "cross_product":
                    rejected = self._generate_cross_product(record, sft_records)
                elif strategy == "fact_mutation":
                    rejected = self._mutate_facts(record)
                else:
                    rejected = self._cross_summary(record, sft_records)

                if rejected:
                    dpo_records.append(DPORecord(
                        prompt=self._build_prompt(record),
                        chosen=record.response,
                        rejected=rejected,
                        product=record.product,
                        language=record.language,
                        strategy=strategy,
                    ))

        return dpo_records

    def _generate_cross_product(self, record: SFTRecord,
                                 all_records: List[SFTRecord]) -> Optional[str]:
        """다른 제품의 응답을 rejected로 사용 (RAFT Distractor)"""
        other_products = [r for r in all_records
                         if r.product != record.product
                         and r.item_type == record.item_type
                         and r.language == record.language]
        if not other_products:
            return None
        return random.choice(other_products).response

    def _mutate_facts(self, record: SFTRecord) -> str:
        """응답의 사실 정보를 변형 (에러코드, 포트번호 등 변경)"""
        mutated = record.response
        # 숫자 변형
        numbers = re.findall(r'-?\d{4,5}', mutated)
        for num in numbers[:2]:
            new_num = str(int(num) + random.randint(100, 999))
            mutated = mutated.replace(num, new_num, 1)
        return mutated
```

### 3.5 Phase 5: 품질 검증 (`validators/training_validator.py`)

```python
class TrainingValidator:
    """학습 데이터 품질 검증 (5가지 검증 통합)"""

    # 검증 기준
    MIN_INSTRUCTION_LEN = 10     # 최소 질문 길이 (chars)
    MIN_RESPONSE_LEN = 20        # 최소 응답 길이 (chars)
    MAX_RESPONSE_TOKENS = 4096   # 최대 응답 토큰
    DUPLICATE_THRESHOLD = 0.95   # 중복 판정 코사인 유사도
    COHERENCE_THRESHOLD = 0.30   # Q-A 키워드 겹침 최소 비율
    MIN_PRODUCT_COUNT = 20       # 제품당 최소 레코드 수

    def validate_all(self, records: List[SFTRecord]) -> Dict:
        """전체 검증 실행"""
        report = {
            "total": len(records),
            "passed": 0,
            "failed": 0,
            "checks": {},
        }

        # 1. 길이 검증
        report["checks"]["length"] = self._check_length(records)

        # 2. 중복 검출
        report["checks"]["duplicates"] = self._check_duplicates(records)

        # 3. Q-A 일치도
        report["checks"]["coherence"] = self._check_coherence(records)

        # 4. 언어 균형
        report["checks"]["language_balance"] = self._check_language_balance(records)

        # 5. ChatML 포맷
        report["checks"]["format"] = self._check_format(records)

        # 종합 점수
        total_issues = sum(c.get("failed", 0) for c in report["checks"].values())
        report["passed"] = len(records) - total_issues
        report["failed"] = total_issues
        report["quality_score"] = (report["passed"] / max(1, len(records))) * 100

        return report

    def _check_length(self, records: List[SFTRecord]) -> Dict:
        """길이 검증"""
        too_short_q = [r for r in records if len(r.instruction) < self.MIN_INSTRUCTION_LEN]
        too_short_a = [r for r in records if len(r.response) < self.MIN_RESPONSE_LEN]
        return {
            "passed": len(records) - len(too_short_q) - len(too_short_a),
            "failed": len(too_short_q) + len(too_short_a),
            "short_questions": len(too_short_q),
            "short_answers": len(too_short_a),
        }

    def _check_duplicates(self, records: List[SFTRecord]) -> Dict:
        """코사인 유사도 기반 중복 검출"""
        # TF-IDF + cosine similarity
        from sklearn.feature_extraction.text import TfidfVectorizer
        from sklearn.metrics.pairwise import cosine_similarity

        texts = [r.instruction + " " + r.response for r in records]

        # 제품별로 중복 검출 (전체 비교는 O(n²) 비용 과다)
        duplicates = set()
        products = set(r.product for r in records)
        for product in products:
            indices = [i for i, r in enumerate(records) if r.product == product]
            if len(indices) < 2:
                continue
            product_texts = [texts[i] for i in indices]
            vectorizer = TfidfVectorizer(max_features=5000)
            tfidf = vectorizer.fit_transform(product_texts)
            sim = cosine_similarity(tfidf)
            for i in range(len(indices)):
                for j in range(i + 1, len(indices)):
                    if sim[i][j] >= self.DUPLICATE_THRESHOLD:
                        duplicates.add(indices[j])

        return {
            "passed": len(records) - len(duplicates),
            "failed": len(duplicates),
            "duplicate_indices": list(duplicates),
        }

    def _check_coherence(self, records: List[SFTRecord]) -> Dict:
        """Q-A 키워드 겹침 검증"""
        incoherent = []
        for i, r in enumerate(records):
            q_words = set(re.findall(r'[a-zA-Z_]{3,}|[ぁ-んァ-ヶ一-龥]{2,}', r.instruction))
            a_words = set(re.findall(r'[a-zA-Z_]{3,}|[ぁ-んァ-ヶ一-龥]{2,}', r.response))
            if not q_words:
                continue
            overlap = len(q_words & a_words) / len(q_words)
            if overlap < self.COHERENCE_THRESHOLD:
                incoherent.append(i)

        return {
            "passed": len(records) - len(incoherent),
            "failed": len(incoherent),
        }

    def _check_language_balance(self, records: List[SFTRecord]) -> Dict:
        """언어 균형 검증"""
        lang_counts = {}
        for r in records:
            lang_counts[r.language.value] = lang_counts.get(r.language.value, 0) + 1

        total = len(records)
        balance = {}
        for lang, count in lang_counts.items():
            balance[lang] = {
                "count": count,
                "ratio": count / max(1, total),
            }

        return {
            "passed": len(records),
            "failed": 0,
            "balance": balance,
        }

    def _check_format(self, records: List[SFTRecord]) -> Dict:
        """ChatML 포맷 검증"""
        invalid = []
        for i, r in enumerate(records):
            chatml = r.to_chatml()
            if "<|im_start|>" not in chatml or "<|im_end|>" not in chatml:
                invalid.append(i)
            if chatml.count("<|im_start|>") != 3:  # system + user + assistant
                invalid.append(i)

        return {
            "passed": len(records) - len(invalid),
            "failed": len(invalid),
        }
```

## 4. CLI 인터페이스 설계

### 4.1 main.py 커맨드 추가

```python
# main.py에 추가할 3개 커맨드

# 1. reextract - 전체 재추출
reextract_parser = subparsers.add_parser(
    "reextract",
    help="전체 매뉴얼 재추출 (에러코드 + 용어 + 명령어/설정/API)"
)
reextract_parser.add_argument("--product", type=str, help="특정 제품만 처리")
reextract_parser.add_argument("--force", action="store_true", help="기존 파일 덮어쓰기")

# 2. gen-training - 학습 데이터 생성
training_parser = subparsers.add_parser(
    "gen-training",
    help="학습 데이터 생성 (SFT + CPT + DPO)"
)
training_parser.add_argument(
    "--format", choices=["all", "sft", "cpt", "dpo"], default="all"
)
training_parser.add_argument(
    "--lang", type=str, default="ja,ko,en",
    help="생성 언어 (콤마 구분, 기본: ja,ko,en)"
)
training_parser.add_argument(
    "--output", "-o", type=Path, default=None,
    help="출력 디렉토리 (기본: uploads/training/v10)"
)
training_parser.add_argument(
    "--dpo-count", type=int, default=2000,
    help="DPO 쌍 수 (기본: 2000)"
)

# 3. validate-training - 품질 검증
validate_parser = subparsers.add_parser(
    "validate-training",
    help="학습 데이터 품질 검증"
)
validate_parser.add_argument(
    "--input", "-i", type=Path, required=True,
    help="학습 데이터 디렉토리 또는 JSONL 파일"
)
validate_parser.add_argument(
    "--report", "-r", type=Path, default=None,
    help="품질 보고서 출력 경로"
)
```

### 4.2 사용 예시

```bash
# 전체 재추출 (Phase 1-2)
python -m scripts.manual_processor.main reextract

# 특정 제품만 재추출
python -m scripts.manual_processor.main reextract --product MVS_Openframe

# 학습 데이터 생성 (Phase 3)
python -m scripts.manual_processor.main gen-training --format all --lang ja,ko,en

# SFT만 생성
python -m scripts.manual_processor.main gen-training --format sft --lang ja

# 품질 검증 (Phase 4)
python -m scripts.manual_processor.main validate-training -i uploads/training/v10

# 전체 파이프라인 (권장)
python -m scripts.manual_processor.main reextract && \
python -m scripts.manual_processor.main gen-training && \
python -m scripts.manual_processor.main validate-training -i uploads/training/v10
```

## 5. 다국어 처리 설계

### 5.1 언어별 소스

| 언어 | 소스 | 처리 방법 |
|------|------|----------|
| JA (일본어) | 18개 제품 원문 PDF (242 PDFs) | 직접 추출 |
| KO (한국어) | JEUS 8.5 KR 매뉴얼 (24 PDFs) | 직접 추출 |
| EN (영어) | 없음 | 템플릿 기반 생성 |

### 5.2 영어 데이터 생성 전략

영어 PDF가 없으므로 **템플릿 기반 규칙 변환**으로 생성합니다 (LLM 번역 아님):

```python
# 룰 기반 변환 예시
def translate_error_response(entry: dict, target_lang: str) -> str:
    """에러코드 응답을 룰 기반으로 변환"""
    if target_lang == "en":
        return (
            f"Error {entry['code']} ({entry['name']}) occurs when "
            f"{entry['description_en']}.\n\n"
            f"Resolution: {entry['solution_en']}"
        )
    elif target_lang == "ko":
        return (
            f"에러 {entry['code']} ({entry['name']})는 "
            f"{entry['description_ko']} 발생합니다.\n\n"
            f"해결방법: {entry['solution_ko']}"
        )
```

### 5.3 에러코드/명령어 용어 번역 매핑

```python
# 기술 용어는 번역하지 않음 (영문 유지)
NO_TRANSLATE = {
    "tjesmgr", "tacfmgr", "hidbmgr", "oscmgr", "osimgr",
    "TJES", "TACF", "OSC", "OSI", "HiDB", "NDB",
    "VSAM", "KSDS", "ESDS", "GDG", "PDS",
    "JCL", "JOB", "EXEC", "DD",
}

# 공통 표현 번역 테이블
PHRASE_TABLE = {
    "ja": {
        "場合に発生します": {"ko": "경우 발생합니다", "en": "occurs when"},
        "お問い合わせください": {"ko": "문의하시기 바랍니다", "en": "please contact"},
        "再実行します": {"ko": "다시 실행합니다", "en": "retry the operation"},
        "確認してください": {"ko": "확인하시기 바랍니다", "en": "please verify"},
    }
}
```

## 6. 출력 구조 및 포맷

### 6.1 디렉토리 구조

```
uploads/training/v10/
├── sft/
│   ├── train_all.jsonl          # 전체 학습셋 (ChatML)
│   ├── eval_all.jsonl           # 전체 평가셋
│   ├── openframe_common_v2/
│   │   ├── train.jsonl
│   │   └── eval.jsonl
│   ├── tibero7_v2/
│   │   ├── train.jsonl
│   │   └── eval.jsonl
│   └── ... (24개 제품)
├── cpt/
│   ├── corpus_ja.txt            # 일본어 코퍼스
│   ├── corpus_ko.txt            # 한국어 코퍼스 (JEUS KR)
│   └── corpus_en.txt            # 영어 코퍼스 (템플릿 생성)
├── dpo/
│   ├── preferences.jsonl        # DPO 쌍
│   └── stats.json               # DPO 통계
├── quality_report.json          # 품질 보고서
└── generation_stats.json        # 생성 통계
```

### 6.2 JSONL 레코드 포맷

#### SFT (train_all.jsonl)
```json
{"text":"<|im_start|>system\nあなたはOpenFrame Batch専門のテクニカルアシスタントです。<|im_end|>\n<|im_start|>user\ntjesmgrコマンドの使い方と主なオプションを教えてください。<|im_end|>\n<|im_start|>assistant\ntjesmgrはTJES (Tmax Job Entry Subsystem) の管理コマンドです。\n\n主なサブコマンド:\n- BOOT: TJESノードを初期化\n- SHUTDOWN: TJESノードを停止\n- STATUS: 現在の状態を表示\n\n構文: tjesmgr [サブコマンド] [オプション]<|im_end|>","product":"openframe_batch_v2","language":"ja","source":"OF_Batch_MVS_7.1_TJES-Guide_v3.1.3_JP.pdf","type":"command"}
```

#### DPO (preferences.jsonl)
```json
{"prompt":"<|im_start|>system\nあなたはOpenFrame Batch専門のテクニカルアシスタントです。<|im_end|>\n<|im_start|>user\ntjesmgrコマンドについて説明してください。<|im_end|>\n","chosen":"<|im_start|>assistant\ntjesmgrはTJES管理コマンドで...<|im_end|>","rejected":"<|im_start|>assistant\ntjesmgrはOSCトランザクション管理で...<|im_end|>","product":"openframe_batch_v2","language":"ja","strategy":"cross_product"}
```

## 7. 品質 보고서 포맷

```json
{
  "version": "v10",
  "generated": "2026-02-20T12:00:00Z",
  "pipeline": "manual-reextraction-training-pipeline",
  "extraction": {
    "pdfs_processed": 245,
    "products": 19,
    "error_codes_extracted": 1824,
    "commands_extracted": 500,
    "configs_extracted": 200,
    "apis_extracted": 100,
    "glossary_terms": 2500
  },
  "training_data": {
    "sft": {
      "total": 0,
      "train": 0,
      "eval": 0,
      "by_language": {"ja": 0, "ko": 0, "en": 0},
      "by_product": {},
      "by_type": {"error": 0, "command": 0, "config": 0, "api": 0, "concept": 0}
    },
    "cpt": {
      "corpus_ja_size_mb": 0,
      "corpus_ko_size_mb": 0,
      "corpus_en_size_mb": 0,
      "total_chunks": 0,
      "total_tokens": 0
    },
    "dpo": {
      "total_pairs": 0,
      "by_strategy": {"cross_product": 0, "fact_mutation": 0, "summary_cross": 0}
    }
  },
  "quality": {
    "overall_score": 0.0,
    "length_check": {"passed": 0, "failed": 0},
    "duplicate_check": {"passed": 0, "failed": 0},
    "coherence_check": {"passed": 0, "failed": 0},
    "language_balance": {"ja": 0.0, "ko": 0.0, "en": 0.0},
    "format_check": {"passed": 0, "failed": 0}
  },
  "comparison_v9": {
    "v9_records": 2647,
    "v10_records": 0,
    "change_pct": "+0%",
    "new_languages": ["ko", "en"],
    "new_types": [],
    "quality_delta": "+0%"
  }
}
```

## 8. 구현 순서

| 순서 | 파일 | 작업 | 의존성 |
|------|------|------|--------|
| 1 | `models/training.py` | 데이터 모델 정의 | 없음 |
| 2 | `config.py` | 제품 매핑, 학습 경로 추가 | 없음 |
| 3 | `parsers/error_parser.py` | Format A/B 로직 교체 | 1 |
| 4 | `generators/sft_generator.py` | SFT ChatML 생성 | 1, 2 |
| 5 | `generators/cpt_generator.py` | CPT Plain Text 생성 | 1, 2 |
| 6 | `generators/dpo_generator.py` | DPO Preference 생성 | 1, 2, 4 |
| 7 | `validators/training_validator.py` | 품질 검증 | 1 |
| 8 | `main.py` | 3개 커맨드 추가 | 3, 4, 5, 6, 7 |
| 9 | 실행 및 검증 | 전체 파이프라인 테스트 | 8 |

## 9. 성공 기준 (Design 기준)

| 항목 | 목표 | 검증 방법 |
|------|------|----------|
| 에러코드 빈 항목 | ≤1% | `quality_report.json` |
| SFT 레코드 수 | ≥5,000 | `train_all.jsonl` 라인 수 |
| 3개 언어 존재 | JA+KO+EN | `by_language` 필드 |
| DPO 쌍 수 | ≥2,000 | `preferences.jsonl` 라인 수 |
| CPT 코퍼스 | ≥70MB | `corpus_*.txt` 합산 |
| 품질 점수 | ≥95% | `quality_report.json` |
| ChatML 호환 | 100% | `format_check.passed == total` |
| 신규 파일 수 | 6개 | 위 구현 순서 참조 |
| 기존 파일 수정 | 2개 | `main.py`, `config.py` |
