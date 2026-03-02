# OpenFrame MVS 7.1 QLoRA 학습 최적화 방법 조사

> 작성일: 2026-02-08
> 대상 모델: Qwen/Qwen2.5-7B-Instruct
> GPU: NVIDIA A100-SXM4-40GB x 8
> 대상 데이터: OpenFrame MVS 7.1 일본어 제품 매뉴얼 (38개 PDF, 65MB)

---

## 1. 현재 상태 분석

### 1.1 원본 PDF 현황 (38개, 65MB)

| 모듈 | 파일 수 | 주요 가이드 |
|------|---------|-----------|
| OF_Base_7.1 | 3 | Base/Dataset/Installation Guide |
| OF_Batch_MVS_7.1 | 7 | Batch/JCL/Sort/TJES/TSO/IPF/Installation |
| OF_Common_MVS_7.1 | 6 | Config/Error/Getting Started/Migration/Tool/Utility |
| OF_OSC_7.1 | 6 | Admin/CTG/Developer/Installation/Mapping/Resource |
| OF_OSI_7.2 | 7 | Admin/Command/Developer/Installation/MFS/Release/System |
| OF_TACF_7.1 | 2 | Administrator/Installation |
| OF_GW_7.1 | 3 | Admin/Installation/WebTerminal |
| OF_HiDB_7.2 | 2 | HiDB/Installation |
| OF_Manager_7.1Fix1 | 2 | Installation/User Guide (10.8MB 최대) |

경로: `uploads/OpenFrame_MVS_7.1/`

### 1.2 현재 학습 데이터 (심각히 부족)

| 서브모듈 | 학습 예제 수 | 평가 |
|---------|------------|------|
| openframe_base_v2 | ~160 | 부족 |
| openframe_osc_v2 | ~100 | 부족 |
| openframe_tacf_v2 | ~187 | 부족 |
| openframe_batch_v2 | ~127 | 부족 |
| openframe_common_v2 | ~157 | 부족 |
| openframe_osi_v2 | ~94 | 부족 |
| **합계** | **~825** | **권장의 10% 수준** |

38개 PDF(65MB)에서 825개 예제만 추출된 상태. **PDF 대비 데이터 활용률이 매우 낮음.**
권장 목표: 제품당 1,000-5,000개 → 전체 6,000-20,000개.

### 1.3 현재 학습 설정 (v9)

```python
# scripts/train_qlora_v9.py
BASE_MODEL = "Qwen/Qwen2.5-7B-Instruct"
BNB_4BIT_COMPUTE_DTYPE = torch.float16   # A100에서는 bf16이 더 적합
LORA_R = 64
LORA_ALPHA = 64                          # scaling = 1.0
LORA_DROPOUT = 0.15                      # 과도한 정규화
MAX_SEQ_LENGTH = 1024                    # 기술 문서에 부족
BATCH_SIZE = 2
GRADIENT_ACCUMULATION_STEPS = 8          # effective batch = 16
LEARNING_RATE = 1e-4
NUM_EPOCHS = 5
WEIGHT_DECAY = 0.01
```

---

## 2. 최적 학습 파이프라인

### 2.1 Phase 1: PDF → 구조화된 텍스트 추출

**권장 도구: Docling (IBM Research)**

| 도구 | 복잡 테이블 정확도 | 속도 (50p) | 추천 이유 |
|------|-----------------|-----------|---------|
| **Docling** | **97.9%** | 65s | 기술 문서 테이블/계층 구조 최적 |
| LlamaParse | 낮음 (구조 오류) | ~6s | 단순 문서만 가능 |
| Unstructured | 75% | 51-141s | 단순 테이블만 |

OpenFrame 매뉴얼은 복잡한 테이블(설정 파라미터, 에러코드, 커맨드 레퍼런스)이 많아 Docling이 적합.

```bash
pip install docling
```

```python
from docling.document_converter import DocumentConverter

converter = DocumentConverter()
for pdf_path in glob("uploads/OpenFrame_MVS_7.1/*.pdf"):
    result = converter.convert(pdf_path)
    markdown = result.document.export_to_markdown()
    # 헤더 기반 청킹 (H2-H4 단위)
```

### 2.2 Phase 2: 청크 → QA 쌍 생성 (LLM 활용)

```
PDF 1개당 평균 페이지: ~50-100페이지
목표 청크 수: 20-50개/PDF
목표 QA 쌍: 5개/청크
38개 PDF × 35청크 × 5QA = 약 6,650개 QA 쌍
```

**QA 생성 프롬프트 (포트 12800 Qwen2.5-7B 활용):**
```python
prompt = f"""다음 {product_name} 기술 문서 내용을 바탕으로 5개의 다양한 질문-답변 쌍을 생성하세요.

질문 유형:
1. How-to (설치/설정 절차)
2. Troubleshooting (에러 해결)
3. 개념 설명 (기능/아키텍처)
4. 설정 파라미터 참조
5. Best Practice / 권장사항

규칙:
- 답변은 제공된 텍스트에서 확인 가능해야 함
- 구체적 파라미터명, 명령어, 코드 예시 포함
- 기초~고급 난이도 혼합

문서 내용:
{chunk_text}
"""
```

### 2.3 Phase 3: 품질 필터링

```python
# 검증 LLM으로 생성된 QA 쌍 품질 검사
validation_prompt = f"""
다음 QA 쌍이 기술적으로 정확한지 평가하세요 (1-5점):
Q: {question}
A: {answer}
원본 문서: {source_chunk}
"""
# 4점 이상만 학습 데이터에 포함
```

### 2.4 Phase 4: 다국어 증강

```
원본 (JA): 6,650개
번역 (KO): 6,650개
번역 (EN): 6,650개
패러프레이즈: 3,000개 추가
──────────────────────
목표 합계: ~23,000개 (제품당 ~3,000개)
```

기존 `scripts/augment_multilingual_v9.py` 활용하되, **역번역 검증** 추가:
- JA→KO 번역 후, KO→JA 역번역하여 원본과 비교
- 의미 왜곡된 쌍 제거

---

## 3. v9 → v10 설정 변경사항

### 3.1 즉시 변경 (High Priority)

| 항목 | 현재 v9 | **권장 v10** | 이유 |
|------|---------|------------|------|
| `compute_dtype` | fp16 | **bf16** | A100 네이티브 bf16 지원, fp16은 NaN 위험 |
| `max_seq_length` | 1024 | **2048** | 기술 문서 응답이 1024 토큰 초과 빈번 |
| `lora_dropout` | 0.15 | **0.05** | 0.15는 과도한 정규화, 학습 저해 |
| `use_rslora` | 미사용 | **True** | rank 64에서 그래디언트 안정성 향상 |
| `max_grad_norm` | 1.0 | **0.3** | 학습 안정성 크게 개선 |
| `lr_scheduler` | default | **cosine** | 수렴 품질 향상 |
| `batch_size` | 2 | **4** | bf16 + gradient checkpointing으로 VRAM 여유 |
| `grad_accum` | 8 | **4** | effective batch 16 유지 (4x4=16) |

### 3.2 v10 전체 권장 설정

```python
# === LoRA Config (v10) ===
from peft import LoraConfig

lora_config = LoraConfig(
    r=64,
    lora_alpha=64,
    target_modules=["q_proj", "k_proj", "v_proj", "o_proj",
                     "gate_proj", "up_proj", "down_proj"],
    lora_dropout=0.05,        # 0.15 → 0.05
    bias="none",
    task_type="CAUSAL_LM",
    use_rslora=True,           # NEW: rank-stabilized scaling
)

# === BitsAndBytes Config ===
bnb_config = BitsAndBytesConfig(
    load_in_4bit=True,
    bnb_4bit_compute_dtype=torch.bfloat16,  # fp16 → bf16
    bnb_4bit_quant_type="nf4",
    bnb_4bit_use_double_quant=True,
)

# === Training Arguments ===
training_args = TrainingArguments(
    per_device_train_batch_size=4,           # 2 → 4
    gradient_accumulation_steps=4,            # 8 → 4 (effective batch 16)
    learning_rate=1e-4,
    num_train_epochs=3,                       # 데이터 충분하면 3, 부족하면 5
    warmup_ratio=0.05,
    weight_decay=0.01,
    max_grad_norm=0.3,                        # NEW
    lr_scheduler_type="cosine",               # NEW
    bf16=True,                                # fp16 → bf16
    fp16=False,
    optim="paged_adamw_8bit",
    gradient_checkpointing=True,
    dataloader_num_workers=4,                 # NEW
    save_total_limit=3,
)

# === SFTTrainer ===
trainer = SFTTrainer(
    max_seq_length=2048,                      # 1024 → 2048
    packing=True,                             # NEW: 짧은 예제 패킹
)
```

### 3.3 A100-40GB 메모리 예산 (v10 기준)

```
Base model (4-bit):         ~4 GB
LoRA adapters (rank 64):    ~0.2 GB
Optimizer states (8-bit):   ~0.4 GB
Gradients:                  ~0.2 GB
Activations (checkpointing): ~5-15 GB
CUDA overhead:              ~2 GB
──────────────────────────────────
예상 합계:                  ~12-22 GB
가용 여유:                  ~18-28 GB
```

---

## 4. 고급 최적화 옵션

### 4.1 Option A: Unsloth 도입 (강력 권장)

| 항목 | 현재 (HF TRL) | Unsloth |
|------|-------------|---------|
| 학습 속도 | Baseline | **2배 빠름** |
| VRAM 사용 | ~22GB | **~8GB** |
| 최대 컨텍스트 | 제한적 | **8배 확장** |
| 코드 변경 | - | **최소** (패치 방식) |

```python
from unsloth import FastLanguageModel

model, tokenizer = FastLanguageModel.from_pretrained(
    model_name="Qwen/Qwen2.5-7B-Instruct",
    max_seq_length=2048,
    load_in_4bit=True,
)
model = FastLanguageModel.get_peft_model(
    model, r=64, lora_alpha=64,
    target_modules=["q_proj","k_proj","v_proj","o_proj",
                     "gate_proj","up_proj","down_proj"],
    lora_dropout=0.05,
    use_rslora=True,
)
# 이후 SFTTrainer 코드 동일
```

### 4.2 Option B: DoRA (Weight-Decomposed LoRA)

ICML 2024에서 발표. rank 32로 현재 rank 64 수준의 성능 달성 가능:

```python
LoraConfig(
    r=32,              # 64의 절반
    lora_alpha=32,
    use_dora=True,     # DoRA 활성화
    lora_dropout=0.05,
    ...
)
```

- 학습 시간 ~10-15% 증가
- learning rate를 약간 낮춤 (5e-5)

### 4.3 Option C: rsLoRA + High Rank

최대 품질을 원할 경우:

```python
LoraConfig(
    r=256,             # 고랭크
    lora_alpha=256,
    use_rslora=True,   # 필수: 고랭크 안정화
    ...
)
```

rsLoRA는 scaling을 `alpha/r` → `alpha/sqrt(r)`로 변경하여 고랭크에서 안정적.

---

## 5. 학습 데이터 포맷

### 5.1 ChatML (현재 포맷 유지)

Qwen2.5-Instruct의 네이티브 포맷으로 적합:

```
<|im_start|>system
{system_prompt}<|im_end|>
<|im_start|>user
{question}<|im_end|>
<|im_start|>assistant
{answer}<|im_end|>
```

### 5.2 시스템 프롬프트 다양화 (과적합 방지)

```json
[
  "あなたはOpenFrame MVS 7.1の技術サポートアシスタントです。",
  "OpenFrame MVS 기술 전문가로서 정확한 기술 지원을 제공합니다.",
  "You are an OpenFrame MVS 7.1 technical support specialist.",
  "TmaxSoft OpenFrame MVS에 대한 기술적 질문에 답변해주세요."
]
```

### 5.3 멀티턴 대화 포함 (전체의 20-30%)

```
<|im_start|>user
OpenFrame Batch의 JCL 작업 실행 방법은?<|im_end|>
<|im_start|>assistant
[답변]<|im_end|>
<|im_start|>user
TJES에서 작업이 실패했을 때 에러 로그는 어디서 확인하나요?<|im_end|>
<|im_start|>assistant
[후속 답변]<|im_end|>
```

---

## 6. 평가 파이프라인

### 6.1 자동 메트릭 (매 학습 실행)

| 메트릭 | 측정 대상 | 도구 |
|--------|---------|------|
| Training Loss | 수렴 품질 | Trainer logs |
| Eval Loss | 과적합 탐지 | Hold-out eval set |
| Perplexity | 언어 모델 품질 | `math.exp(eval_loss)` |

### 6.2 도메인 QA 평가 (주간)

| 메트릭 | 측정 대상 | 구현 |
|--------|---------|------|
| Domain QA 정확도 | 사실 정확성 | LLM-as-Judge (100+ 테스트 QA) |
| ROUGE-L | 응답 완전성 | 참조 답변 대비 비교 |
| 용어 정확도 | 제품 용어 사용 | 용어 사전 대비 키워드 매칭 |
| 다국어 일관성 | KO/JA/EN 품질 편차 | 언어별 동일 질문 비교 |

### 6.3 A/B 비교 평가

```python
# 테스트 질문마다:
# 1. Base model 응답 (Qwen2.5-7B, 어댑터 없음)
# 2. Fine-tuned 모델 응답 (Qwen2.5-7B + LoRA)
# 3. Judge LLM으로 정확도/완전성/도움 정도 평가 (1-5)
# 4. Fine-tuned vs Base 승률 계산
```

**평가 테스트셋**: 학습에 포함되지 않은 50-100개 QA 쌍을 제품별로 별도 유지

---

## 7. 실행 우선순위

### 1순위 - 데이터 (가장 큰 임팩트)

1. **Docling으로 38개 PDF 재추출** → 구조화된 Markdown
2. **LLM으로 QA 쌍 대량 생성** → 제품당 1,000-5,000개 목표
3. **품질 필터링** → 정확도 4점 이상만 유지
4. **다국어 증강** (KO/EN 번역 + 역번역 검증)

### 2순위 - 학습 설정 개선

5. **bf16으로 전환** (fp16에서)
6. **max_seq_length 2048** 확장
7. **rsLoRA 활성화** + dropout 0.05 + cosine scheduler
8. **Unsloth 도입**으로 학습 속도 2배 향상

### 3순위 - 품질 관리

9. 평가 파이프라인 구축
10. 시스템 프롬프트 다양화 + 멀티턴 대화 추가
11. TensorBoard 실험 추적 설정

---

## 8. 성능 비교 기준선

### Multi-LoRA vLLM vs TRT-LLM NIM

| 항목 | Multi-LoRA vLLM (Port 12810) | TRT-LLM NIM (Port 12820) |
|------|---------------------------|------------------------|
| 모델 로딩 | 즉시 (동시) | Lazy (요청시 ~28초) |
| 추론 속도 | ~25 tok/s | ~32 tok/s |
| 메모리 사용 | 38GB (전체) | 15GB (모델당) |
| 최적화 | vLLM | TensorRT-LLM |

### 어댑터 크기

- LoRA 어댑터: ~309 MB/개
- TRT-LLM 엔진: ~15 GB/개 (최적화 후)
- 현재 총 어댑터: 17GB (MVS) + 19GB (8개 제품)

---

## 참고 자료

- rsLoRA Paper: https://arxiv.org/abs/2312.03732
- DoRA (ICML 2024): https://arxiv.org/abs/2402.09353
- QLoRA Original: https://arxiv.org/abs/2305.14314
- Unsloth: https://github.com/unslothai/unsloth
- Qwen + LLaMA-Factory: https://qwen.readthedocs.io/en/latest/training/llama_factory.html
- Qwen + Unsloth: https://qwen.readthedocs.io/en/latest/training/unsloth.html
- Docling (IBM): https://github.com/DS4SD/docling
- PDF Extraction Benchmark 2025: Docling vs LlamaParse vs Unstructured
- Unsloth LoRA Hyperparameters Guide: https://unsloth.ai/docs/get-started/fine-tuning-llms-guide/lora-hyperparameters-guide
