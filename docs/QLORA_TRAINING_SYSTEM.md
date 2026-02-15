# QLoRA 학습 시스템 분석 문서

> **작성일**: 2026-02-15
> **대상**: HybridRAG KMS - 멀티 프로덕트 QLoRA 학습 파이프라인

---

## 1. 개요

TmaxSoft 22개 제품 매뉴얼에 대해 제품별 전문 LoRA 어댑터를 학습하여, RAG 검색 시 도메인 특화 응답을 생성하는 시스템이다.

- **베이스 모델**: Qwen/Qwen2.5-7B-Instruct (7B 파라미터)
- **양자화**: 4-bit NF4 (BitsAndBytes, Double Quantization)
- **학습 방식**: QLoRA (Quantized Low-Rank Adaptation)
- **GPU**: NVIDIA A100-SXM4-40GB x 8 (학습에 GPU 4,5,6,7 사용)

---

## 2. LoRA 설정

### 2.1 LoRA Config

| 파라미터 | v9 (최신) | v4 | 비고 |
|---------|-----------|-----|------|
| Rank (r) | 64 | 64 | 도메인 지식 수용 용량 |
| Alpha (α) | 64 | 64 | Scaling = α/r = 1.0 |
| Dropout | 0.15 | 0.1 | v9에서 과적합 방지 강화 |
| Bias | none | none | 바이어스 학습 안함 |
| Task Type | CAUSAL_LM | CAUSAL_LM | 디코더 전용 |

### 2.2 Target Modules (7개)

```
q_proj, k_proj, v_proj, o_proj, gate_proj, up_proj, down_proj
```

- Attention 레이어 4개 + MLP 레이어 3개 전체 적용
- 학습 파라미터: ~7M (전체 7B의 ~0.1%)

### 2.3 양자화 설정

| 파라미터 | 값 |
|---------|-----|
| load_in_4bit | True |
| bnb_4bit_quant_type | nf4 (Normalized Float 4) |
| bnb_4bit_use_double_quant | True |
| bnb_4bit_compute_dtype | float16 (v9) / bfloat16 (v4) |

---

## 3. 학습 하이퍼파라미터

| 파라미터 | v9 (최신) | v4 | 변경 사유 |
|---------|-----------|-----|----------|
| Max Sequence Length | 1024 | 1024 | - |
| Batch Size (per device) | 2 | 2 | A100 40GB 메모리 제약 |
| Gradient Accumulation | 8 | 8 | 유효 배치 = 16 |
| Learning Rate | 1e-4 | 2e-4 | 안정성 향상 |
| Warmup Ratio | 0.05 | 0.03 | 워밍업 구간 확대 |
| Weight Decay | 0.01 | 0.001 | 정규화 강화 |
| Epochs | 5 | 3 | 소규모 데이터셋 최적화 |
| Optimizer | paged_adamw_8bit | paged_adamw_32bit | 메모리 효율화 |
| LR Scheduler | cosine | cosine | - |
| FP16 | True (v9) | False | A100 최적화 |
| BF16 | False (v9) | True | - |
| Eval Steps | 50 | 50 | - |
| Save Steps | 100 | 100 | - |
| Save Total Limit | 3 | 3 | - |
| Early Stopping Patience | 3 | 3 | - |

### v4 → v9 변경 요약

- **LR 감소** (2e-4 → 1e-4): 학습 안정성 확보
- **Dropout 증가** (0.1 → 0.15): 과적합 방지
- **Weight Decay 증가** (0.001 → 0.01): 정규화 강화
- **Epoch 증가** (3 → 5): 소규모 데이터셋에서 충분한 학습
- **Compute Dtype 변경** (BF16 → FP16): A100 GPU 최적화

---

## 4. 최종 학습 데이터셋 (multi_lora_v9)

### 4.1 데이터 포맷

ChatML 형식 (Qwen2.5 호환):

```json
{
  "text": "<|im_start|>system\n당신은 JEUS 전문 기술 어시스턴트입니다. JEUS에 관한 질문에 정확하게 답변해주세요.<|im_end|>\n<|im_start|>user\nJSP 하위 호환성을 위한 웹 컨텍스트 레벨의 옵션 설정의 개념을 알려주세요.<|im_end|>\n<|im_start|>assistant\nJEUS 4 및 5에서는 사용자의 편의성과 Servlet 2.3 이전에 개발된 애플리케이션을 위해서...\n\n**製品/Product**: JEUS\n**出典/Source**: Jeus_8.5fix0_Web-Engine-Guide.pdf<|im_end|>"
}
```

**구성 요소**:
- `system`: 제품별 전문 어시스턴트 지시문
- `user`: 기술 문서 기반 질문/지시
- `assistant`: 매뉴얼에서 추출한 상세 답변 + 출처 메타데이터

### 4.2 제품별 데이터 분포

| 제품 | Train | Eval | 합계 | 주요 언어 |
|------|-------|------|------|----------|
| jeus_v2 | 980 | 210 | 1,190 | 한국어 |
| tibero7_v2 | 231 | 12 | 243 | 한국어 |
| ofpli_v2 | 74 | 20 | 94 | 일본어 |
| openframe_aim_v2 | 72 | 22 | 94 | 일본어 |
| prosync_v2 | 72 | 22 | 94 | 한국어 |
| protrieve_v2 | 67 | 22 | 89 | 한국어 |
| openframe_hidb_v2 | 64 | 21 | 85 | 일본어 |
| openframe_tacf_v2 | 62 | 22 | 84 | 한국어/일본어 |
| openframe_vos3_v2 | 57 | 25 | 82 | 일본어 |
| ofmanager_v2 | 59 | 17 | 76 | 한국어 |
| openframe_base_v2 | 53 | 17 | 70 | 일본어 |
| ofcobol_v2 | 55 | 14 | 69 | 한국어 |
| openframe_common_v2 | 52 | 3 | 55 | 일본어 |
| webtob_v2 | 50 | 0 | 50 | 한국어 |
| openframe_batch_v2 | 42 | 5 | 47 | 일본어 |
| prosort_v2 | 25 | 15 | 40 | 한국어 |
| openframe_osc_v2 | 33 | 4 | 37 | 일본어 |
| ofstudio_v2 | 26 | 9 | 35 | 한국어 |
| openframe_osi_v2 | 31 | 2 | 33 | 일본어 |
| tmax_v2 | 30 | 3 | 33 | 한국어 |
| ofminer_v2 | 22 | 4 | 26 | 한국어 |
| openframe_gateway_v2 | 16 | 5 | 21 | 일본어 |
| **합계** | **2,173** | **474** | **2,647** | |

### 4.3 언어 분포

| 언어 | 샘플 수 | 비율 |
|------|---------|------|
| 한국어 | ~1,200+ | ~45% |
| 일본어 | ~1,100+ | ~42% |
| 영어 | ~340+ | ~13% |

### 4.4 저장 경로

```
uploads/summaries/multi_lora_v9/
├── jeus_v2/
│   ├── train.json
│   └── eval.json
├── tibero7_v2/
│   ├── train.json
│   └── eval.json
├── ... (22개 제품 폴더)
├── train_all.json          # 전체 통합 학습 데이터
└── eval_all.json           # 전체 통합 평가 데이터
```

---

## 5. 데이터 파이프라인

### 5.1 전체 흐름

```
[Phase 0] PDF 매뉴얼 추출
    38개 PDF → 헤더 기반 청킹 → 구조화된 텍스트 청크
    ↓ (~1,330 청크)

[Phase 1] Q&A 쌍 생성
    LLM 기반 (Qwen2.5, port 12800)
    청크당 ~5개 Q&A 쌍 생성
    ↓ (~6,650 raw pairs)

[Phase 2] 품질 필터링
    - P0: 빈 필드, placeholder 패턴, 답변 25자 미만 제거
    - P1: Q&A 일관성 검증
    - P2: 문맥 의존 질문, 짧은 답변 보강
    ↓ (~33% 탈락)

[Phase 3] 데이터 밸런싱
    - 대규모 제품 (JEUS): 80% train / 20% eval
    - 소규모 제품 (<100): 75% train / 25% eval
    - 초소규모 (<30): 수동 증강
    ↓

[Phase 4] 다국어 증강 (선택적)
    - 원본 → 한/일/영 번역
    - 역번역으로 의미 왜곡 검증 (cosine > 0.85)
    - 고가치 쌍 패러프레이징
    ↓ (1 → 3~4배 증강)

[최종] 2,173 train + 474 eval = 2,647 샘플
```

### 5.2 품질 필터 상세 (quality_filter.py)

| 우선순위 | 필터 | 제거 대상 |
|---------|------|----------|
| P0 | Empty fields | 빈 name/description |
| P0 | Placeholder patterns | 제네릭 템플릿 |
| P0 | Min answer length | 답변 25자 미만 |
| P0 | Page numbers only | 페이지 번호만 있는 항목 |
| P1 | Q&A consistency | 질문-답변 불일치 |
| P2 | Context-dependent | 문맥 의존 불완전 질문 |
| P2 | Short answer enrichment | 50자 미만 답변 보강 |

---

## 6. 멀티 프로덕트 학습 전략

### 6.1 3가지 학습 방식

| 방식 | 스크립트 | GPU | 용도 |
|------|---------|-----|------|
| 개별 학습 | `train_qlora_v9.py` | 1 GPU | 제품별 전문 어댑터 (운영용) |
| 병렬 학습 | `multi_product_trainer_v3.py` | 4 GPU | 대규모 일괄 학습 |
| 통합 학습 | `simple_qlora_trainer.py` | 1 GPU | 빠른 프로토타이핑 |

### 6.2 개별 학습 (운영 권장)

```bash
python scripts/train_qlora_v9.py \
  --data uploads/summaries/multi_lora_v9/jeus_v2/train.json \
  --output /raid/users/ofuser/qlora/outputs/jeus_v2 \
  --epochs 5 \
  --batch_size 2 \
  --learning_rate 1e-4
```

### 6.3 병렬 학습 (4 GPU)

```bash
python scripts/training/multi_product_trainer_v3.py \
  --gpu-id 4 \
  --products jeus_v2 tibero7_v2 openframe_base_v2 \
  --base-dir uploads/summaries/multi_lora_v9 \
  --output models/multi_lora_v3
```

### 6.4 통합 학습

```bash
python scripts/training/simple_qlora_trainer.py \
  --dataset uploads/summaries/multi_lora_v9/train_all.json \
  --eval-dataset uploads/summaries/multi_lora_v9/eval_all.json \
  --output models/combined_v9 \
  --gpu-id 4
```

---

## 7. 멀티 페이즈 학습 파이프라인

전체 학습은 3단계로 구성된다:

### Phase 1: CPT (Continued Pre-Training)

| 항목 | 값 |
|------|-----|
| 목적 | 도메인 지식 주입 |
| 모델 | Qwen2.5-72B |
| GPU | GPU 4 (단일) |
| 데이터 | 통합 코퍼스 (72MB, 49M chars) |
| LoRA Rank | 128 |
| Learning Rate | 1e-5 |
| Epochs | 2 |
| Max Seq Length | 2048 |

### Phase 2: SFT (Supervised Fine-Tuning)

| 항목 | 값 |
|------|-----|
| 목적 | Q&A 능력 학습 |
| 모델 | Qwen2.5-7B-Instruct |
| GPU | GPU 4,5,6,7 (병렬) |
| 데이터 | 22개 제품, 2,173 train 샘플 |
| LoRA Rank | 64 |
| Learning Rate | 2e-4 (v4) / 1e-4 (v9) |
| Epochs | 3 (v4) / 5 (v9) |
| Max Seq Length | 1024 |

### Phase 3: DPO (Direct Preference Optimization)

| 항목 | 값 |
|------|-----|
| 목적 | 환각(Hallucination) 억제 |
| 모델 | Qwen2.5-72B |
| GPU | GPU 4 (단일) |
| 데이터 | 2,000 preference pairs (chosen vs rejected) |
| LoRA Rank | 32 |
| Learning Rate | 5e-6 |
| Beta | 0.1 |
| Epochs | 2 |

---

## 8. 어댑터 저장 및 추론

### 8.1 어댑터 저장 구조

```
/raid/users/ofuser/qlora/outputs/
├── jeus_v2_adapter/
│   ├── adapter_model.bin          # LoRA 가중치 (8-10 MB)
│   ├── adapter_config.json        # LoRA 설정
│   └── training_metadata.json     # 학습 메타데이터
├── tibero7_v2_adapter/
├── openframe_base_v2_adapter/
└── ... (22개 제품)
```

### 8.2 추론 코드

```python
from peft import AutoPeftModelForCausalLM
from transformers import AutoTokenizer

# 베이스 모델 + 어댑터 로드
model = AutoPeftModelForCausalLM.from_pretrained(
    "Qwen/Qwen2.5-7B-Instruct",
    adapter_name="jeus_v2",
    torch_dtype=torch.float16,
    device_map="auto",
    load_in_4bit=True
)

# 프롬프트 (학습 시 포맷과 동일해야 함)
prompt = """<|im_start|>system
당신은 JEUS 전문 기술 어시스턴트입니다.<|im_end|>
<|im_start|>user
JEUS 설정 방법을 알려주세요.<|im_end|>
<|im_start|>assistant"""

output = model.generate(tokenizer(prompt).input_ids, max_new_tokens=512)
```

---

## 9. 주요 스크립트 목록

### 학습 스크립트

| 스크립트 | 역할 |
|---------|------|
| `scripts/train_qlora_v9.py` | v9 단일 제품 학습 (FP16 최적화, 최신) |
| `scripts/train_qlora_v4.py` | v4 단일 제품 학습 |
| `scripts/training/multi_product_trainer_v3.py` | 멀티 제품 병렬 학습 (4 GPU) |
| `scripts/training/simple_qlora_trainer.py` | 간소화 학습기 (eval 지원) |
| `scripts/training/qlora_parallel_trainer.py` | 데이터 병렬 학습 |
| `scripts/training/merge_adapter.py` | 어댑터 병합 |

### 데이터 전처리 스크립트

| 스크립트 | 역할 |
|---------|------|
| `scripts/training/quality_filter.py` | 품질 필터링 |
| `scripts/training/semantic_clean_dataset.py` | 의미적 정제 |
| `scripts/training/improve_v9_dataset.py` | v9 데이터셋 개선 |
| `scripts/training/generate_qa_dataset.py` | 매뉴얼 요약본 기반 Q&A 생성 |
| `scripts/augment_multilingual_v9.py` | 다국어 증강 |
| `scripts/training/paraphrase_augment.py` | 패러프레이징 증강 |

### 실행 스크립트

| 스크립트 | 역할 |
|---------|------|
| `scripts/train_parallel_v9.sh` | v9 병렬 학습 실행 |
| `scripts/training/run_multi_lora_v3.sh` | 멀티 LoRA v3 실행 |
| `scripts/training/run_parallel_training_v3.sh` | v3 병렬 학습 실행 |
| `scripts/training/accelerate_config_4gpu.yaml` | 4 GPU Accelerate 설정 |

---

## 10. 데이터셋 버전 이력

| 버전 | 위치 | 변경 사항 |
|------|------|----------|
| v3 | `multi_lora_v3/` | 기본 QLoRA 구성 |
| v4 | `multi_lora_v4_cleaned/` | Alpha 증가 (16→64), 데이터 정제 |
| v5 | `multi_lora_v5_augmented/` | 증강 적용, 의미적 정제 |
| v6 | `multi_lora_v6_final/` | 최종 정제 |
| v7 | `multi_lora_v7_clean/` | 대규모 정제 |
| v8 | `multi_lora_v8_final/` | 멀티 제품 통합, 균형 분할 |
| **v9** | **`multi_lora_v9/`** | **FP16, dropout/weight decay 조정 (최신)** |

---

## 11. 핵심 설계 결정 사항

### Scaling = 1.0 (α = r = 64)

기본값(α=16, r=64, scaling=0.25)보다 4배 강한 어댑터 영향력을 적용한다. 범용 LLM에 TmaxSoft 도메인 전문 지식을 강하게 주입하기 위한 의도적 선택이다.

### 제품별 개별 어댑터

통합 어댑터 대신 22개 개별 어댑터를 학습한다. 제품 간 지식 간섭을 방지하고, 추론 시 제품 키워드 기반으로 적절한 어댑터를 동적 로드한다.

### 품질 우선 전략

원본 ~6,650개 Q&A 쌍에서 ~33%만 통과시켜 2,173개 고품질 데이터만 학습에 사용한다. 소규모 고품질 > 대규모 저품질 전략이다.

### 3-Phase 파이프라인

CPT(도메인 지식) → SFT(Q&A 능력) → DPO(환각 억제)로 단계적으로 모델 능력을 구축한다.
