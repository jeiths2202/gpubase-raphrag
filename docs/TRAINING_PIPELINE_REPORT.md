# OpenFrame 도메인 특화 LLM 학습 파이프라인 보고서

> **프로젝트 목적**: TmaxSoft OpenFrame 제품군에 대한 도메인 특화 LLM을 구축하여, RAG 기반 KMS에서 Hallucination을 억제하고 정확한 기술 답변을 제공하는 것
>
> **최종 목표 지표**: E2E Hallucination 테스트 통과율 향상, DPO preference accuracy > 90%
>
> **베이스 모델**: Qwen/Qwen2.5-72B-Instruct
>
> **정밀도**: BF16 + QLoRA 4-bit (NF4, double quantization)
>
> **학습 일자**: 2026-02-12 ~ 2026-02-14

---

## 전체 학습 파이프라인 구조

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│  Corpus     │     │   SFT       │     │             │
│  Extract    │     │  (7B×22제품) │     │             │
│  (19 PDF)   │     │  Multi-LoRA │     │             │
└──────┬──────┘     └──────┬──────┘     │             │
       │                   │            │             │
       ▼                   ▼            │             │
┌─────────────┐     ┌─────────────┐     │             │
│   CPT       │     │  DPO Pairs  │     │   최종      │
│  (72B)      │     │  Generation │     │  Adapter    │
│  FSDP×4GPU  │     │  (2000 쌍)  │     │             │
└──────┬──────┘     └──────┬──────┘     │             │
       │                   │            │             │
       ▼                   ▼            │             │
┌──────────────────────────────────┐    │             │
│          DPO (72B)               │───▶│  배포/평가  │
│  FSDP×4GPU, QLoRA 4-bit         │    │             │
│  Hallucination 억제 정렬         │    │             │
└──────────────────────────────────┘    └─────────────┘
```

### 단계별 요약

| 단계 | 모델 | GPU | 소요시간 | 상태 |
|------|------|-----|---------|------|
| 1. Corpus Extract | - | CPU | ~16분 | 완료 |
| 2. SFT (Multi-LoRA) | Qwen2.5-7B-Instruct | GPU 4,5,6,7 | ~69분 | 완료 (22제품) |
| 3. CPT (72B) | Qwen2.5-72B-Instruct | GPU 4,5,6,7 | 2시간 29분 | 완료 |
| 4. DPO Pairs Gen | - | CPU | ~1분 | 완료 (2000쌍) |
| 5. DPO (72B) | Qwen2.5-72B-Instruct | GPU 4,5,6,7 | ~73분 (예상) | 진행중 |

---

## 1. 프로젝트 목적

### 1.1 배경

HybridRAG KMS 시스템에서 OpenFrame 제품에 대한 질문에 정확한 답변을 제공하기 위해, 범용 LLM을 OpenFrame 도메인에 특화시키는 것이 목적이다. 기존 E2E 테스트에서 45개 케이스 중 21개에서 Hallucination이 감지되어(통과율 53%), 이를 개선할 필요가 있었다.

### 1.2 목표

1. **도메인 지식 주입** (CPT): OpenFrame 매뉴얼, API 문서, 에러 코드 등 도메인 텍스트를 모델에 학습
2. **Hallucination 억제** (DPO): 올바른 응답(chosen)과 잘못된 응답(rejected)을 구분하여 정렬
3. **제품별 전문성** (SFT Multi-LoRA): 22개 제품 각각에 대한 전문 어댑터 제공

### 1.3 왜 RLHF 대신 DPO를 선택했는가?

| 관점 | RLHF (PPO) | DPO | 선택 이유 |
|------|-----------|-----|----------|
| Reward Model | 별도 학습 필요 | 불필요 | GPU 리소스 절약 |
| 학습 안정성 | PPO는 하이퍼파라미터 민감 | 상대적 안정 | 시행착오 최소화 |
| 구현 복잡도 | Reward + Policy + Value 3개 모델 | Policy 1개 모델 | 4GPU 제약 충족 |
| 메모리 효율 | 4개 모델 로드 | ref model은 base weight 공유 | 72B 모델에서 필수 |
| 성능 | 이론적 우수 | 실용적으로 동등 | 논문 결과 참조 |

DPO는 RLHF의 reward model과 RL 최적화를 closed-form 솔루션으로 대체하여, 동일한 preference 데이터에서 직접 policy를 최적화한다. 72B 모델을 4×A100 40GB 환경에서 학습해야 하는 제약 조건에서, reward model 없이 학습 가능한 DPO가 최적의 선택이었다.

---

## 2. 인프라 환경

### 2.1 하드웨어

| 항목 | 사양 |
|------|------|
| GPU | NVIDIA A100-SXM4-40GB × 8 |
| 학습 사용 GPU | GPU 4, 5, 6, 7 (GPU 0-3은 VLLM 서빙용) |
| GPU 메모리 | 40,960 MiB / GPU |
| 학습 중 메모리 사용 | ~30,615 MiB / GPU (DPO 기준) |
| 메모리 여유 | ~10,345 MiB / GPU |
| Storage | /raid 14TB (12TB 여유) |

### 2.2 소프트웨어 버전

| 라이브러리 | 버전 |
|-----------|------|
| PyTorch | 2.10.0+cu128 |
| CUDA | 12.8 |
| NVIDIA Driver | 550.90.07 |
| Transformers | 4.57.6 |
| PEFT | 0.18.1 |
| bitsandbytes | 0.49.1 |
| TRL | 0.27.1 |
| Accelerate | 1.12.0 |
| Python | 3.10 |

### 2.3 Git 커밋

```
Repository: gpubase-raphrag-new
Commit: e3344677101c22f15399e740a1ab392d6b9212b4
```

---

## 3. CPT (Continued Pre-Training) 상세

### 3.1 목적

72B 베이스 모델에 OpenFrame 도메인 텍스트를 사전학습하여 도메인 지식을 주입한다.

### 3.2 데이터

| 항목 | 값 |
|------|-----|
| 학습 데이터 | mixed_corpus.txt (72MB, 1,698,821줄) |
| 총 문자 수 | 49,441,025 |
| 추정 토큰 수 | 34,291,641 |
| 도메인 텍스트 비율 | 66.6% (32.9M chars) |
| 코드 데이터 비율 | 33.3% (16.5M chars) |
| 소스 PDF | 19개 제품 매뉴얼 |
| 학습 샘플 수 | 10,511 (train) / 214 (eval) |

### 3.3 파라미터

| 파라미터 | 값 | 근거 |
|---------|-----|------|
| base_model | Qwen/Qwen2.5-72B-Instruct | 최대 성능 확보 |
| lora_r | 64 | 도메인 지식 수용력 확보 (높은 rank) |
| lora_alpha | 128 | alpha/r = 2.0 (표준 비율) |
| lora_dropout | 0.05 | 과적합 방지 |
| learning_rate | 1e-5 | CPT 표준 범위 |
| epochs | 2 | corpus 크기 대비 적정 |
| max_seq_length | 2048 | 긴 문서 컨텍스트 보존 |
| batch_size | 1/GPU | 메모리 제약 |
| grad_accum | 4 | effective batch = 16 |
| target_modules | q,k,v,o,gate,up,down_proj | 전체 attention + MLP |
| quantization | NF4, double quant | 메모리 효율 |
| optimizer | paged_adamw_8bit | FSDP 호환 |
| scheduler | cosine | 표준 스케줄러 |
| precision | bf16 | A100 최적 |

### 3.4 분산 학습 설정 (FSDP)

| FSDP 파라미터 | 값 |
|-------------|-----|
| sharding_strategy | FULL_SHARD |
| auto_wrap_policy | TRANSFORMER_BASED_WRAP |
| transformer_cls | Qwen2DecoderLayer |
| backward_prefetch | BACKWARD_PRE |
| state_dict_type | SHARDED_STATE_DICT |
| sync_module_states | true |
| use_orig_params | true |
| offload_params | false |

### 3.5 결과

| 메트릭 | 값 |
|-------|-----|
| Train Loss (최종) | 0.1141 |
| Eval Loss | 0.5022 |
| Eval Perplexity | 1.6524 |
| 소요 시간 | 2시간 28분 33초 |
| 완료 시각 | 2026-02-14 05:38:29 |
| Adapter 크기 | 1.6GB (safetensors) |
| LoRA 파라미터 수 | 1,120개 |

### 3.6 CPT Loss 추이 (epoch 2 구간)

| Step | Loss | LR | Epoch |
|------|------|----|-------|
| 1010 | 0.4774 | 2.25e-6 | 1.54 |
| 1050 | 0.5180 | 1.00e-5 | 1.60 |
| 1100 | 0.4740 | 9.95e-6 | 1.67 |
| 1150 | 0.4367 | 9.82e-6 | 1.75 |
| 1200 | 0.4656 | 9.62e-6 | 1.83 |

Loss가 0.43~0.52 범위에서 안정적으로 수렴. Eval perplexity 1.65는 도메인 텍스트에 대한 양호한 적응을 의미한다.

---

## 4. SFT (Supervised Fine-Tuning) 상세

### 4.1 목적

22개 TmaxSoft 제품 각각에 대해 Multi-LoRA 어댑터를 학습하여 제품별 전문 응답을 생성한다.

### 4.2 구성

| 항목 | 값 |
|------|-----|
| 베이스 모델 | Qwen/Qwen2.5-7B-Instruct |
| 제품 수 | 22개 |
| GPU 배분 | GPU 4,5,6,7 (병렬 4개씩) |
| 총 소요 시간 | ~69분 |

### 4.3 제품별 SFT 결과 (일부)

| 제품 | Train 샘플 | Train Loss | Eval Loss | 소요시간 |
|------|-----------|-----------|----------|---------|
| jeus_v2 | 최대 | - | - | ~28분 |
| tibero7_v2 | 231 | 0.6964 | 0.6093 | 12분 47초 |
| ofcobol_v2 | 55 | 1.4947 | 0.7402 | 3분 2초 |
| webtob_v2 | - | - | - | - |

### 4.4 SFT 파라미터

| 파라미터 | 값 |
|---------|-----|
| lora_r | 64 |
| lora_alpha | 16 |
| learning_rate | 2e-4 |
| epochs | 3 |

> **Note**: SFT는 7B 모델 기반으로 NIM Multi-LoRA 서비스에서 런타임 어댑터 교체 방식으로 제공. 72B CPT/DPO와는 별도 파이프라인.

---

## 5. DPO (Direct Preference Optimization) 상세

### 5.1 목적

Hallucination을 억제하고, 정확한 답변을 선호하도록 72B 모델을 정렬한다.

### 5.2 데이터

| 항목 | 값 |
|------|-----|
| 총 DPO 쌍 | 2,000개 |
| Train / Eval | 1,800 / 200 |
| 생성 전략 | 3가지 (아래 표) |

**DPO 쌍 생성 전략별 분포:**

| 전략 | 수량 | 비율 | 설명 |
|------|------|------|------|
| factual_product_swap | 1,113 | 55.7% | 다른 제품의 답변을 rejected로 활용 |
| factual_desc_swap | 688 | 34.4% | 사실 관계가 틀린 설명을 rejected로 |
| sft_cross_match | 187 | 9.4% | SFT 모델 간 교차 비교 |
| e2e_cross_product | 12 | 0.6% | E2E 테스트 기반 교차 제품 비교 |

### 5.3 파라미터

#### A. 모델 관련

| 파라미터 | 값 | 근거 |
|---------|-----|------|
| base_model | Qwen/Qwen2.5-72B-Instruct | 최대 성능 |
| max_length | 512 | OOM 해결을 위해 2048→512 축소 |
| max_prompt_length | 128 | OOM 해결을 위해 512→128 축소 |
| gradient_checkpointing | true | 메모리 절약 (연산 재계산) |

#### B. 학습 관련

| 파라미터 | 값 | 근거 |
|---------|-----|------|
| learning_rate | 5e-6 | DPO 표준 범위. SFT보다 낮게 설정 |
| warmup_ratio | 0.1 | 학습 초기 안정화 |
| batch_size | 1/GPU | 72B 메모리 제약 |
| grad_accum | 4 | effective batch = 16 |
| epochs | 2 | DPO는 과적합 위험으로 적은 epoch |
| max_grad_norm | 1.0 | gradient clipping |
| weight_decay | 0.05 | 정규화 |
| optimizer | paged_adamw_8bit | 메모리 효율 |
| scheduler | cosine | 표준 |

#### C. DPO 특화

| 파라미터 | 값 | 근거 |
|---------|-----|------|
| beta | 0.1 | DPO 표준값. KL divergence 패널티 강도 |
| ref_model | None (base weight 공유) | PEFT에서 base weight가 reference 역할 |
| loss_type | sigmoid (기본값) | DPO 논문 원본 loss |
| precompute_ref_log_probs | false | FSDP 환경 비호환 (device mismatch) |

#### D. LoRA 관련

| 파라미터 | 값 | 근거 |
|---------|-----|------|
| lora_r | 32 | CPT(64)보다 낮음. 정렬에는 높은 rank 불필요 |
| lora_alpha | 64 | alpha/r = 2.0 |
| lora_dropout | 0.05 | 과적합 방지 |
| target_modules | q,k,v,o,gate,up,down_proj | 전체 attention + MLP |

### 5.4 학습 결과 (진행 중)

| Step | Loss | Accuracy | Margin | LR | Epoch |
|------|------|----------|--------|-----|-------|
| 10 | 0.6914 | 0.425 | 0.005 | 1.96e-6 | 0.09 |
| 20 | 0.6899 | 0.656 | 0.011 | 4.13e-6 | 0.18 |
| 30 | 0.6243 | 0.806 | 0.156 | 4.99e-6 | 0.27 |
| 40 | 0.5304 | 0.856 | 0.410 | 4.92e-6 | 0.36 |
| 50 | 0.4079 | 0.919 | 0.825 | 4.80e-6 | 0.44 |
| 60 | 0.3645 | 0.900 | 1.133 | 4.62e-6 | 0.53 |
| 70 | 0.2193 | 0.944 | 1.966 | 4.39e-6 | 0.62 |
| 80 | 0.1730 | 0.950 | 2.631 | 4.12e-6 | 0.71 |
| 90 | 0.1813 | 0.925 | 2.747 | 3.81e-6 | 0.80 |

**핵심 관찰:**
- Loss: 0.6914 → 0.1730 (75% 감소, 10 step마다 기록)
- Accuracy: 0.425 → 0.950 (chosen vs rejected 구분 능력 95%)
- Margin: 0.005 → 2.747 (chosen/rejected 간 보상 차이 확대)
- Step 90에서 accuracy 소폭 하락(0.925) → 정상적인 변동 범위

### 5.5 GPU 메모리 사용 (DPO 학습 중)

| GPU | 사용 | 총량 | 여유 |
|-----|------|------|------|
| GPU 4 | 30,615 MiB | 40,960 MiB | 10,345 MiB |
| GPU 5 | 30,615 MiB | 40,960 MiB | 10,345 MiB |
| GPU 6 | 30,615 MiB | 40,960 MiB | 10,345 MiB |
| GPU 7 | 30,615 MiB | 40,960 MiB | 10,345 MiB |

---

## 6. 파라미터 및 시행착오

### 6.1 OOM 해결 과정

DPO는 학습 중 policy 모델과 reference 모델의 forward pass를 모두 수행하므로 SFT/CPT 대비 ~2배의 GPU 메모리가 필요하다.

#### 시도 1: 원본 설정 (실패)
```
max_length=2048, max_prompt_length=512
→ Step 14에서 OOM (39.29/39.38 GiB, 128 MiB 부족)
```

#### 시도 2: precompute_ref_log_probs=True (실패)
```
Reference model의 log probability를 사전 계산하여 학습 중 메모리 절감 시도
→ RuntimeError: Expected all tensors to be on the same device
   (FSDP가 파라미터를 여러 GPU에 분산, precompute 단계에서 device 불일치)
```
> **교훈**: `precompute_ref_log_probs`는 FSDP 환경에서 호환되지 않음

#### 시도 3: fsdp_offload_params=true (실패)
```
비활성 shard를 CPU로 오프로드하여 GPU 메모리 절약 시도
→ RuntimeError: All input tensors need to be on the same GPU
   (bitsandbytes paged_adamw_8bit는 CPU 텐서 미지원)
```
> **교훈**: `fsdp_offload_params`와 `paged_adamw_8bit`는 비호환

#### 시도 4: max_length 축소 (성공)
```
max_length=2048→512, max_prompt_length=512→128
→ Attention 메모리 O(n²) 특성상 4배 축소로 ~16배 메모리 절감
→ Step 14 통과, GPU 여유 ~10GB 확보
→ 이후 Step 99+ 까지 안정 학습 진행 중
```

### 6.2 CPT Adapter 형식 변환

CPT는 FSDP SHARDED_STATE_DICT로 저장하므로 PyTorch distributed checkpoint(distcp) 형식이다. 이를 PEFT 표준 형식으로 변환해야 DPO에서 로드 가능하다.

```
FSDP sharded (4 files, ~805MB each)
  → torch.distributed.checkpoint.FileSystemReader로 로드
  → LoRA 파라미터만 추출 (1,120개)
  → adapter_model.safetensors (1.6GB) + adapter_config.json
```

### 6.3 CPT Adapter + DPO 통합 이슈

4-bit 양자화된 모델에서 FSDP 다중 GPU 환경으로 LoRA adapter를 merge하면 `invalid argument to getCurrentStream` 에러가 발생한다. 이는 bitsandbytes 4-bit 역양자화가 multi-device 컨텍스트를 지원하지 않기 때문이다.

**현재 전략**: DPO 학습 후 별도 merge 단계에서 CPT + DPO adapter를 순차 통합 예정.

---

## 7. 학습 방식 비교 연구

| 방식 | 설명 | 장점 | 단점 | 채택 |
|------|------|------|------|------|
| Full Pretraining | 전체 파라미터 재학습 | 최고 성능 | 72B 비용 막대 | ❌ |
| CPT | 도메인 텍스트 사전학습 | 도메인 지식 주입 | 대규모 corpus 필요 | ✅ |
| SFT | 지시-응답 쌍으로 미세조정 | 지시 따르기 능력 | Hallucination 미해결 | ✅ (7B) |
| RLHF (PPO) | Reward 모델 + RL 최적화 | 이론적 우수 | 불안정, 4모델 필요 | ❌ |
| **DPO** | Preference 쌍으로 직접 정렬 | 안정, 효율 | 고품질 쌍 데이터 필요 | ✅ |
| IPO | DPO 변형, KL 제약 개선 | DPO 과적합 방지 | 구현 복잡 | 향후 검토 |
| KTO | Unpaired preference 학습 | 데이터 요구 낮음 | DPO 대비 성능 미검증 | 향후 검토 |
| ORPO | SFT+DPO 통합 | 단일 단계 학습 | 새로운 방식, 검증 부족 | 향후 검토 |
| **QLoRA** | 4-bit 양자화 LoRA | 메모리 극적 절약 | 풀 파인튜닝 대비 소폭 손실 | ✅ |
| **FSDP** | 모델 분산 병렬화 | 72B 분산 학습 가능 | 통신 오버헤드 | ✅ |
| ZeRO | DeepSpeed 메모리 최적화 | 유연한 메모리 관리 | FSDP와 중복 | ❌ (FSDP 채택) |
| LoRA | Low-Rank Adaptation | 효율적 미세조정 | 풀 파인튜닝 대비 제한 | ✅ (QLoRA) |

---

## 8. 실험 결과 정리

### 8.1 CPT 실험

| 실험 | LR | LoRA r | Epochs | Train Loss | Eval Loss | Perplexity | 비고 |
|------|-----|--------|--------|-----------|----------|-----------|------|
| CPT-72B | 1e-5 | 64 | 2 | 0.1141 | 0.5022 | 1.6524 | 최종 채택 |

### 8.2 DPO 실험

| 실험 | Beta | max_len | LR | Loss (최종) | Accuracy | 비고 |
|------|------|---------|-----|------------|----------|------|
| DPO-v1 (OOM) | 0.1 | 2048 | 5e-6 | - | - | Step 14 OOM |
| DPO-v2 (OOM) | 0.1 | 2048 | 5e-6 | - | - | Step 14 OOM (재시도) |
| DPO-v3 (precompute) | 0.1 | 1024 | 5e-6 | - | - | FSDP device mismatch |
| DPO-v4 (offload) | 0.1 | 512 | 5e-6 | - | - | 8bit optimizer 비호환 |
| **DPO-v5 (현재)** | 0.1 | 512 | 5e-6 | 0.1730* | 0.950* | 정상 진행 중 |

*Step 80 기준, 학습 진행 중

### 8.3 DPO Loss Curve

```
Loss
0.70 ┤ ●
0.65 ┤
0.60 ┤    ●
0.55 ┤
0.50 ┤       ●
0.45 ┤
0.40 ┤          ●
0.35 ┤             ●
0.30 ┤
0.25 ┤
0.20 ┤                ●
0.15 ┤                   ● ●
     └──────────────────────────
     10  20  30  40  50  60  70  80  90  Step
```

### 8.4 DPO Preference Accuracy Curve

```
Accuracy
1.00 ┤
0.95 ┤                   ●  ●  ●
0.90 ┤             ●  ●
0.85 ┤          ●
0.80 ┤       ●
0.70 ┤
0.65 ┤    ●
0.50 ┤
0.40 ┤ ●
     └──────────────────────────
     10  20  30  40  50  60  70  80  90  Step
```

---

## 9. 사용 소스 및 스크립트 정리

### 9.1 핵심 스크립트

| 스크립트 | 용도 |
|---------|------|
| `scripts/training/run_cpt_70b_fsdp.py` | CPT 72B FSDP 학습 |
| `scripts/training/run_dpo_70b_fsdp.py` | DPO 72B FSDP 학습 |
| `scripts/training/fsdp_qlora_config.yaml` | FSDP+QLoRA 설정 |
| `scripts/training/run_full_pipeline.py` | 전체 파이프라인 자동화 |
| `scripts/training/generate_dpo_data.py` | DPO 쌍 생성 |
| `scripts/training/sft_product_worker.py` | 제품별 SFT 학습 |

### 9.2 실행 스크립트

| 스크립트 | 용도 |
|---------|------|
| `parallel_pipeline/run_cpt_resume_then_dpo.sh` | CPT resume → DPO 연계 |
| `parallel_pipeline/run_dpo_only.sh` | DPO 단독 실행 (OOM 수정판) |
| `parallel_pipeline/resume_cpt_70b.sh` | CPT 중단 복구 |

### 9.3 데이터 경로

| 파일 | 크기 | 설명 |
|------|------|------|
| `parallel_pipeline/mixed_corpus.txt` | 72MB | CPT 학습 corpus |
| `parallel_pipeline/dpo_pairs.json` | 1.1MB | DPO preference 쌍 2000개 |
| `parallel_pipeline/cpt_70b_adapter/` | 1.6GB | CPT adapter (PEFT 형식) |
| `parallel_pipeline/dpo_70b_adapter/` | - | DPO adapter (학습 중) |
| `parallel_pipeline/sft_adapters/` | - | 22개 제품 SFT adapter |

---

## 10. 향후 전략

### 10.1 기술적 개선

| 항목 | 설명 | 우선순위 |
|------|------|---------|
| CPT+DPO Adapter Merge | 학습 후 단일 GPU에서 순차 merge | 즉시 |
| ORPO 실험 | SFT+DPO 통합 학습으로 단계 축소 | 중기 |
| Curriculum DPO | 쉬운 쌍 → 어려운 쌍 순서로 학습 | 중기 |
| Adaptive Beta | 학습 진행에 따라 beta 값 조정 | 장기 |
| Reference-free DPO | base weight 공유 대신 별도 reference 제거 | 장기 |

### 10.2 데이터 전략

| 항목 | 설명 | 우선순위 |
|------|------|---------|
| Hard Negative Mining | E2E 테스트 실패 케이스로 DPO 쌍 생성 | 즉시 |
| Preference 데이터 정제 | 저품질 쌍 필터링 및 재생성 | 중기 |
| Synthetic Preference | LLM-as-judge로 자동 preference 생성 | 중기 |
| Cross-lingual DPO | 한국어/일본어 혼합 preference 쌍 | 장기 |

### 10.3 인프라 개선

| 항목 | 설명 | 우선순위 |
|------|------|---------|
| 8 GPU Scaling | VLLM 서빙과 학습 GPU 분리 시 전체 8GPU 활용 | 중기 |
| Checkpoint 안정화 | FSDP sharded → PEFT 자동 변환 파이프라인 | 즉시 |
| max_length 복원 | GPU 메모리 확보 후 512→1024 이상 복원 | 중기 |
| Evaluation Pipeline | 학습 후 자동 E2E Hallucination 테스트 | 즉시 |

### 10.4 모델 구조 검토

| 항목 | 설명 | 우선순위 |
|------|------|---------|
| Long Context 확장 | RoPE scaling으로 4096+ 토큰 지원 | 장기 |
| Multi-LoRA 72B | 7B뿐 아니라 72B에도 제품별 adapter | 장기 |
| Speculative Decoding | 작은 모델로 초안 생성, 72B로 검증 | 장기 |

---

## 부록 A: 전략적 질문

> **우리는 "instruction model"을 만드는가? 아니면 "alignment 특화 모델"을 만드는가?**

현재 접근: **도메인 특화 + alignment 하이브리드**

- CPT로 OpenFrame 도메인 지식을 주입하여 "도메인 전문가"를 만들고
- DPO로 Hallucination 억제와 정확성 정렬을 수행하여 "신뢰할 수 있는 전문가"로 만든다
- 최종 목표는 RAG 파이프라인의 생성 모듈로 사용되므로, 검색된 문맥에 충실하게 답변하는 "grounded generation" 모델이 핵심이다

이 모델은 단독 사용이 아닌 RAG 시스템의 컴포넌트로서, 검색 결과를 기반으로 정확한 답변을 생성하되 모르는 것은 모른다고 답하는 정렬이 가장 중요하다.

---

## 부록 B: 환경 변수 설정 (필수)

```bash
# 모든 학습 스크립트에 반드시 포함
export HF_HOME="/raid/users/ofuser/.cache/huggingface"
export TRANSFORMERS_CACHE="/raid/users/ofuser/.cache/huggingface/hub"
export HF_DATASETS_CACHE="/raid/users/ofuser/.cache/huggingface/datasets"
export TMPDIR="/raid/users/ofuser/tmp"
export CUDA_VISIBLE_DEVICES=4,5,6,7
export PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True
```

> **주의**: 루트 `/` 디스크 여유 29GB. 모델 다운로드/캐시는 반드시 `/raid` 사용.
