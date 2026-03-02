---
description: QLoRA 학습 파이프라인을 관리합니다. Verified Knowledge 기반 Learning LLM 학습, 어댑터 관리, 학습 상태 확인을 수행합니다.
---

# KMS Learning Pipeline Skill

Smarter RAG의 QLoRA 학습 파이프라인을 관리하는 스킬입니다.

## 사용법

```
/kms-learn status      # 학습 상태 확인
/kms-learn train       # 수동 학습 실행
/kms-learn adapters    # 사용 가능한 어댑터 목록
```

## Smarter RAG 아키텍처

```
사용자 질문
    │
    ▼
┌─────────────────────────────────────────────┐
│ 1단계: Verified Knowledge (similarity≥0.85) │ → 즉시 반환
└─────────────────────────────────────────────┘
    │ 없음
    ▼
┌─────────────────────────────────────────────┐
│ 2단계: Learning LLM (QLoRA) (0.5~0.85)      │ → 학습된 패턴
└─────────────────────────────────────────────┘
    │ 낮은 신뢰도
    ▼
┌─────────────────────────────────────────────┐
│ 3단계: General RAG (문서 검색)               │ → 문서 기반
└─────────────────────────────────────────────┘
```

## QLoRA 학습 실행

### 자동 배치 생성 및 학습
```bash
python scripts/training/qlora_trainer.py --auto
```

### 특정 배치 학습
```bash
python scripts/training/qlora_trainer.py --batch_id batch_20240125_001
```

### 옵션
```bash
python scripts/training/qlora_trainer.py \
    --auto \
    --min_score 0.8 \        # 최소 피드백 점수
    --min_thumbs_up 1 \      # 최소 추천 수
    --limit 1000             # 최대 샘플 수
```

## 학습 설정 (TrainingConfig)

| 항목 | 값 |
|------|-----|
| Base Model | `Qwen/Qwen2.5-7B-Instruct` |
| 양자화 | 4-bit NF4, Double Quant |
| LoRA r | 64 |
| LoRA alpha | 16 |
| Max Seq Length | 2048 |
| VRAM 요구량 | ~8GB |

## 학습 대상 모듈

```python
LORA_TARGET_MODULES = [
    "q_proj", "k_proj", "v_proj", "o_proj",
    "gate_proj", "up_proj", "down_proj"
]
```

## 학습 데이터 소스

Verified Knowledge Store에서 고품질 Q&A 추출:
- `feedback_score >= 0.8`
- `thumbs_up_count >= 1`
- `status = 'active'`
- `is_trained = FALSE`

## 어댑터 경로

```
/opt/kms/models/qlora_adapters/
├── qlora_batch_20240125_001/
├── qlora_batch_20240126_001/
└── ...
```

## vLLM 서버 연동

Learning LLM은 vLLM 서버 또는 로컬 어댑터로 실행:

```python
# vLLM 모드 (권장)
LEARNING_LLM_URL=http://learning-llm-graphrag:8000/v1
LEARNING_LLM_MODEL=learning

# 로컬 모드
use_vllm=False
```

## Unlearning (잘못된 지식 제거)

잘못된 지식 발견 시:
```sql
UPDATE verified_knowledge
SET status = 'unlearn_required'
WHERE id = '잘못된_지식_ID';
```

다음 학습에서 자동 제거됨.
