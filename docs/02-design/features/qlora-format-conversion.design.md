# QLoRA Format Conversion - Design Document

> **Feature**: qlora-format-conversion
> **Version**: v1.0
> **Created**: 2026-02-03
> **Author**: Claude Opus 4.5
> **Status**: Design Phase
> **Plan Reference**: `docs/01-plan/features/qlora-format-conversion.plan.md`

## 1. 아키텍처 개요

### 1.1 시스템 구성도

```
┌─────────────────────────────────────────────────────────────────┐
│                    QLoRA Format Conversion Pipeline              │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  [Input]                    [Process]                [Output]    │
│                                                                  │
│  learning_dataset.json  →  ┌──────────────┐  →  train.json      │
│  (17,431 items)            │ Converter    │      (80%)          │
│                            │              │                      │
│  question_templates.json → │ - Type분류   │  →  eval.json       │
│  (7 types × 3 langs)       │ - 템플릿적용 │      (20%)          │
│                            │ - 답변포맷팅 │                      │
│                            │ - 언어감지   │  →  stats.json      │
│                            └──────────────┘      (통계)          │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

### 1.2 데이터 흐름

```
1. Load learning_dataset.json
       ↓
2. Detect language (JA/KO/EN) per item
       ↓
3. Apply type-specific question template
       ↓
4. Format structured output (syntax, params, examples)
       ↓
5. Generate Qwen2.5 ChatML format
       ↓
6. Split train/eval (80:20)
       ↓
7. Save output files
```

## 2. 상세 설계

### 2.1 클래스 다이어그램

```python
class QLoRAConverter:
    """학습 데이터셋을 QLoRA 형식으로 변환"""

    def __init__(self, templates_path: str):
        self.templates = self._load_templates(templates_path)
        self.stats = ConversionStats()

    def convert(self, input_path: str, output_dir: str) -> ConversionResult:
        """메인 변환 로직"""
        pass

    def _detect_language(self, text: str) -> str:
        """텍스트 언어 감지 (ja/ko/en)"""
        pass

    def _apply_template(self, item: Dict, lang: str) -> Dict:
        """타입별 질문 템플릿 적용"""
        pass

    def _format_output(self, item: Dict) -> str:
        """구조화된 답변 포맷팅"""
        pass

    def _to_chatml(self, instruction: str, output: str) -> Dict:
        """Qwen2.5 ChatML 형식 변환"""
        pass


class QuestionTemplates:
    """타입별/언어별 질문 템플릿 관리"""

    TYPES = ["command", "api", "config", "concept", "procedure", "error", "term"]
    LANGUAGES = ["ja", "ko", "en"]

    def get_template(self, item_type: str, lang: str) -> str:
        pass

    def get_variations(self, item_type: str, lang: str) -> List[str]:
        """데이터 증강용 질문 변형"""
        pass


class ConversionStats:
    """변환 통계 추적"""

    total: int = 0
    converted: int = 0
    by_type: Dict[str, int]
    by_language: Dict[str, int]
    by_product: Dict[str, int]
```

### 2.2 질문 템플릿 상세

```json
{
  "templates": {
    "command": {
      "ja": [
        "{name}コマンドについて説明してください。",
        "{name}コマンドの使い方を教えてください。",
        "{name}の実行方法は？"
      ],
      "ko": [
        "{name} 명령어에 대해 설명해주세요.",
        "{name} 명령어 사용법을 알려주세요.",
        "{name} 실행 방법은?"
      ],
      "en": [
        "Explain the {name} command.",
        "How do I use the {name} command?",
        "What does {name} do?"
      ]
    },
    "api": {
      "ja": [
        "{name} APIの使用方法を教えてください。",
        "{name}関数の引数と戻り値は？",
        "{name} APIの使用例を示してください。"
      ],
      "ko": [
        "{name} API 사용법을 알려주세요.",
        "{name} 함수의 인자와 반환값은?",
        "{name} API 사용 예시를 보여주세요."
      ],
      "en": [
        "How do I use the {name} API?",
        "What are the parameters and return value of {name}?",
        "Show me an example of using {name}."
      ]
    },
    "config": {
      "ja": [
        "{name}の設定方法を説明してください。",
        "{name}パラメータの設定値は？",
        "{name}の推奨設定は？"
      ],
      "ko": [
        "{name} 설정 방법을 설명해주세요.",
        "{name} 파라미터 설정값은?",
        "{name}의 권장 설정은?"
      ],
      "en": [
        "How do I configure {name}?",
        "What are the configuration options for {name}?",
        "What is the recommended setting for {name}?"
      ]
    },
    "concept": {
      "ja": [
        "{name}とは何ですか？",
        "{name}について説明してください。",
        "{name}の概念を教えてください。"
      ],
      "ko": [
        "{name}이란 무엇인가요?",
        "{name}에 대해 설명해주세요.",
        "{name}의 개념을 알려주세요."
      ],
      "en": [
        "What is {name}?",
        "Explain {name}.",
        "Describe the concept of {name}."
      ]
    },
    "procedure": {
      "ja": [
        "{name}の手順を教えてください。",
        "{name}のやり方は？",
        "{name}のステップを説明してください。"
      ],
      "ko": [
        "{name} 절차를 알려주세요.",
        "{name} 방법은?",
        "{name}의 단계를 설명해주세요."
      ],
      "en": [
        "What are the steps for {name}?",
        "How do I perform {name}?",
        "Explain the procedure for {name}."
      ]
    },
    "error": {
      "ja": [
        "エラー{name}の原因と解決方法は？",
        "{name}エラーが発生した場合の対処法は？",
        "{name}の意味と対応策を教えてください。"
      ],
      "ko": [
        "에러 {name}의 원인과 해결방법은?",
        "{name} 에러 발생 시 대처법은?",
        "{name}의 의미와 대응책을 알려주세요."
      ],
      "en": [
        "What causes error {name} and how do I fix it?",
        "How do I resolve the {name} error?",
        "What does {name} mean and how to handle it?"
      ]
    },
    "term": {
      "ja": [
        "{name}の定義を教えてください。",
        "{name}とはどういう意味ですか？",
        "{name}の用語説明をお願いします。"
      ],
      "ko": [
        "{name}의 정의를 알려주세요.",
        "{name}이란 무슨 뜻인가요?",
        "{name} 용어 설명을 부탁합니다."
      ],
      "en": [
        "Define {name}.",
        "What does {name} mean?",
        "Explain the term {name}."
      ]
    }
  },
  "system_prompts": {
    "ja": "あなたはOpenFrame KMSのアシスタントです。技術的な質問に正確に回答してください。",
    "ko": "당신은 OpenFrame KMS 어시스턴트입니다. 기술적인 질문에 정확하게 답변해주세요.",
    "en": "You are an OpenFrame KMS assistant. Answer technical questions accurately."
  }
}
```

### 2.3 출력 포맷 상세

#### 2.3.1 Qwen2.5 ChatML 형식

```python
def _to_chatml(self, instruction: str, output: str, lang: str) -> Dict:
    """
    Qwen2.5 ChatML 형식으로 변환

    Output format matches qlora_trainer.py:format_instruction()
    """
    system_prompt = self.templates["system_prompts"][lang]

    return {
        "text": f"""<|im_start|>system
{system_prompt}<|im_end|>
<|im_start|>user
{instruction}<|im_end|>
<|im_start|>assistant
{output}<|im_end|>"""
    }
```

#### 2.3.2 답변 포맷팅

```python
def _format_output(self, item: Dict) -> str:
    """
    구조화된 답변 포맷팅

    Args:
        item: 학습 데이터 항목 (name, type, description, syntax, parameters, examples)

    Returns:
        포맷팅된 답변 문자열
    """
    parts = []

    # 메인 설명
    parts.append(item["description"])

    # 구문 (command, api인 경우)
    if item.get("syntax"):
        parts.append(f"\n\n**構文/Syntax**:\n```\n{item['syntax']}\n```")

    # 파라미터
    if item.get("parameters") and len(item["parameters"]) > 0:
        params_text = "\n".join([f"- {p}" for p in item["parameters"]])
        parts.append(f"\n\n**パラメータ/Parameters**:\n{params_text}")

    # 예시
    if item.get("examples") and len(item["examples"]) > 0:
        examples_text = "\n".join([f"```\n{e}\n```" for e in item["examples"]])
        parts.append(f"\n\n**例/Example**:\n{examples_text}")

    # 관련 항목
    if item.get("related") and len(item["related"]) > 0:
        related_text = ", ".join(item["related"])
        parts.append(f"\n\n**関連/Related**: {related_text}")

    return "".join(parts)
```

### 2.4 언어 감지 로직

```python
def _detect_language(self, text: str) -> str:
    """
    텍스트에서 주요 언어 감지

    Detection rules:
    1. 히라가나/가타카나 포함 → ja
    2. 한글 포함 → ko
    3. 그 외 → en
    """
    import re

    # 한글 범위: AC00-D7AF (완성형), 1100-11FF (자모)
    korean_pattern = r'[\uAC00-\uD7AF\u1100-\u11FF]'

    # 히라가나: 3040-309F, 가타카나: 30A0-30FF
    japanese_pattern = r'[\u3040-\u309F\u30A0-\u30FF]'

    korean_count = len(re.findall(korean_pattern, text))
    japanese_count = len(re.findall(japanese_pattern, text))

    # 한글이 더 많으면 한국어
    if korean_count > japanese_count and korean_count > 10:
        return "ko"
    # 일본어 문자가 있으면 일본어
    elif japanese_count > 0:
        return "ja"
    # 기본값 영어
    else:
        return "en"
```

## 3. 구현 순서

### 3.1 파일 생성 순서

| 순서 | 파일 | 설명 |
|------|------|------|
| 1 | `scripts/training/templates/question_templates.json` | 질문 템플릿 정의 |
| 2 | `scripts/training/convert_to_qlora.py` | 메인 변환 스크립트 |
| 3 | 실행 및 검증 | `train.json`, `eval.json` 생성 |

### 3.2 CLI 인터페이스

```bash
# 기본 변환 (1:1)
python scripts/training/convert_to_qlora.py \
    --input uploads/summaries/learning_dataset.json \
    --output /opt/kms/data/training/

# 데이터 증강 포함 (질문 변형)
python scripts/training/convert_to_qlora.py \
    --input uploads/summaries/learning_dataset.json \
    --output /opt/kms/data/training/ \
    --augment

# 커스텀 분할 비율
python scripts/training/convert_to_qlora.py \
    --input uploads/summaries/learning_dataset.json \
    --output /opt/kms/data/training/ \
    --train-ratio 0.9
```

### 3.3 출력 파일 구조

```
/opt/kms/data/training/
├── train.json           # 학습 세트 (80%)
├── eval.json            # 검증 세트 (20%)
├── full_dataset.json    # 전체 변환 데이터
└── conversion_stats.json # 변환 통계
```

## 4. 테스트 계획

### 4.1 단위 테스트

| 테스트 | 검증 항목 |
|--------|----------|
| test_language_detection | 한글/일본어/영어 정확 감지 |
| test_template_application | 타입별 템플릿 적용 |
| test_output_formatting | 답변 포맷팅 정확성 |
| test_chatml_format | Qwen2.5 ChatML 호환성 |

### 4.2 통합 테스트

```python
def test_full_conversion():
    """전체 변환 파이프라인 테스트"""
    converter = QLoRAConverter("templates/question_templates.json")
    result = converter.convert(
        "uploads/summaries/learning_dataset.json",
        "/tmp/test_output"
    )

    assert result.total == 17431
    assert result.converted == result.total
    assert os.path.exists("/tmp/test_output/train.json")
    assert os.path.exists("/tmp/test_output/eval.json")
```

### 4.3 QLoRA Trainer 호환성 테스트

```python
def test_qlora_trainer_compatibility():
    """qlora_trainer.py와의 호환성 테스트"""
    from scripts.training.qlora_trainer import prepare_dataset

    with open("/opt/kms/data/training/train.json") as f:
        data = json.load(f)

    # prepare_dataset이 오류 없이 실행되어야 함
    dataset = prepare_dataset(data, tokenizer, max_length=2048)
    assert len(dataset) > 0
```

## 5. 성공 기준 체크리스트

| ID | 기준 | 목표 |
|----|------|------|
| SC-01 | 변환 완료율 | 100% (17,431개) |
| SC-02 | ChatML 형식 호환 | qlora_trainer.py 로드 성공 |
| SC-03 | 타입별 템플릿 적용 | 7개 타입 모두 커버 |
| SC-04 | 언어별 템플릿 | JA/KO/EN 3개 언어 |
| SC-05 | Train/Eval 분할 | 80:20 비율 |
| SC-06 | 변환 시간 | 5분 이내 |

## 6. 참조

### 6.1 관련 파일
- `scripts/training/qlora_trainer.py` - 기존 QLoRA 학습 스크립트
- `uploads/summaries/learning_dataset.json` - 입력 데이터
- `temp/dataset_analysis.json` - 데이터셋 분석 결과

### 6.2 Plan 문서
- `docs/01-plan/features/qlora-format-conversion.plan.md`

---

**다음 단계**: `/pdca do qlora-format-conversion` 또는 직접 구현 시작
