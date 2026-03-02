# QLoRA Format Conversion Plan

> **Feature**: qlora-format-conversion
> **Created**: 2026-02-03
> **Author**: Claude Opus 4.5
> **Status**: Plan Phase

## 1. 배경 및 목적

### 1.1 현재 상황
- **학습 데이터셋**: `uploads/summaries/learning_dataset.json` (17,431개 항목)
- **형식**: 구조화된 지식 데이터 (name, type, description, syntax, parameters, examples...)
- **품질**: 100% (모든 25개 제품)

### 1.2 문제점
기존 학습 데이터셋은 **Instruction-Response 형식**이 아니라 QLoRA 학습에 직접 사용 불가:

| 현재 형식 | QLoRA 필요 형식 |
|-----------|----------------|
| `name`, `description` | `instruction`, `input`, `output` |
| 단일 텍스트 블록 | 질문-답변 쌍 |
| 메타데이터 포함 | 순수 텍스트 프롬프트 |

### 1.3 목표
1. 학습 데이터셋을 QLoRA Trainer 호환 형식으로 자동 변환
2. 타입별 질문 템플릿 적용으로 다양한 질문-답변 쌍 생성
3. 데이터 증강을 통한 학습 효과 극대화

## 2. 요구사항

### 2.1 기능 요구사항

| ID | 요구사항 | 우선순위 |
|----|----------|----------|
| FR-01 | learning_dataset.json → QLoRA 형식 변환 | P0 |
| FR-02 | 타입별(command, api, concept 등) 질문 템플릿 | P0 |
| FR-03 | 다국어 지원 (일본어/한국어/영어) | P1 |
| FR-04 | 학습/검증 세트 자동 분할 (80:20) | P1 |
| FR-05 | 데이터 증강 (질문 변형) | P2 |

### 2.2 비기능 요구사항

| ID | 요구사항 | 기준 |
|----|----------|------|
| NFR-01 | 변환 속도 | 17,431개 → 5분 이내 |
| NFR-02 | 출력 파일 크기 | 원본 대비 150% 이내 |
| NFR-03 | Qwen2.5 chat template 호환 | 100% |

## 3. 솔루션 설계

### 3.1 변환 로직

```python
# 현재 형식
{
    "name": "tjesmgr BOOT",
    "type": "command",
    "description": "TJESノードを初期化します...",
    "syntax": "tjesmgr BOOT [node_name]",
    "parameters": [...],
    "examples": [...],
    "product": "OF_TJES"
}

# 변환 후 (QLoRA 형식)
{
    "instruction": "tjesmgr BOOTコマンドについて説明してください。",
    "input": "",
    "output": "tjesmgr BOOTはTJESノードを初期化するコマンドです。\n\n**構文**: tjesmgr BOOT [node_name]\n\n**パラメータ**:\n- node_name: 対象ノード名\n\n**例**:\n```\ntjesmgr BOOT node1\n```"
}
```

### 3.2 타입별 질문 템플릿

| Type | 질문 템플릿 (JA) | 질문 템플릿 (KO) |
|------|------------------|------------------|
| command | `{name}コマンドについて説明してください。` | `{name} 명령어에 대해 설명해주세요.` |
| api | `{name} APIの使用方法を教えてください。` | `{name} API 사용법을 알려주세요.` |
| config | `{name}の設定方法を説明してください。` | `{name} 설정 방법을 설명해주세요.` |
| concept | `{name}とは何ですか？` | `{name}이란 무엇인가요?` |
| procedure | `{name}の手順を教えてください。` | `{name} 절차를 알려주세요.` |
| error | `エラー{name}の原因と解決方法は？` | `에러 {name}의 원인과 해결방법은?` |
| term | `{name}の定義を教えてください。` | `{name}의 정의를 알려주세요.` |

### 3.3 출력 구조

```python
# Output format (Qwen2.5 ChatML compatible)
{
    "conversations": [
        {
            "role": "system",
            "content": "You are a helpful KMS assistant..."
        },
        {
            "role": "user",
            "content": "{instruction}"
        },
        {
            "role": "assistant",
            "content": "{output}"
        }
    ]
}
```

### 3.4 데이터 증강 전략

1. **질문 변형**: 동일 지식에 대해 2-3개 질문 패턴 생성
2. **언어 혼합**: 일본어/한국어 질문 모두 생성 (Korean JEUS 데이터)
3. **컨텍스트 추가**: 관련 항목을 input으로 제공

## 4. 구현 계획

### 4.1 파일 구조

```
scripts/training/
├── qlora_trainer.py           # 기존 학습 스크립트 (변경 없음)
├── convert_to_qlora.py        # NEW: 형식 변환 스크립트
└── templates/
    └── question_templates.json # NEW: 타입별 질문 템플릿
```

### 4.2 구현 단계

| 단계 | 작업 | 산출물 |
|------|------|--------|
| 1 | 변환 스크립트 작성 | `convert_to_qlora.py` |
| 2 | 질문 템플릿 정의 | `question_templates.json` |
| 3 | 데이터셋 변환 실행 | `qlora_training_data.json` |
| 4 | 학습/검증 분할 | `train.json`, `eval.json` |
| 5 | 통계 및 검증 | 변환 결과 리포트 |

### 4.3 예상 출력

| 항목 | 값 |
|------|-----|
| 입력 | 17,431개 (learning_dataset.json) |
| 출력 (기본) | ~17,431개 (1:1 변환) |
| 출력 (증강 시) | ~35,000개 (2x 질문 변형) |
| 학습 세트 | 80% (~14,000개) |
| 검증 세트 | 20% (~3,400개) |

## 5. 위험 요소 및 대응

| 위험 | 영향 | 대응 |
|------|------|------|
| 긴 description truncation | 정보 손실 | MAX_SEQ_LENGTH=2048 내 자르기 |
| 메모리 부족 | 변환 실패 | 청크 단위 처리 |
| 템플릿 불일치 | 학습 품질 저하 | 샘플 검토 후 조정 |

## 6. 성공 기준

| 기준 | 목표 |
|------|------|
| 변환 완료율 | 100% |
| QLoRA Trainer 호환 | 오류 없이 로드 |
| 학습 시작 | GPU 메모리 8GB 이내 |

## 7. 다음 단계

1. `/pdca design qlora-format-conversion` - 상세 설계
2. 구현 및 테스트
3. GPU 학습 실행

---

**참조 파일**:
- `uploads/summaries/learning_dataset.json` - 입력 데이터
- `scripts/training/qlora_trainer.py` - 기존 학습 스크립트
- `temp/dataset_analysis.json` - 데이터셋 분석 결과
