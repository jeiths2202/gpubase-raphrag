# Qwen3-32B Training Pipeline Guide

> 전체 학습 파이프라인: 데이터셋 생성 → GPU 학습 (CPT→SFT→DPO) → Adapter 머지 → 서빙 → 평가

---

## 1. 파이프라인 전체 흐름

```
Manual PDFs/MD/TXT (uploads/manuals/)
    │
    ▼ [Phase 0: 데이터 로딩]
ManualLoader → ManualSection 추출 (~1,000-5,000 섹션/제품)
    │
    ▼ [Phase 1: 지식 추출]
KnowledgeExtractor → 7가지 구조화 아이템 (Command, Error, Config, API, Feature, Limitation, Migration)
    │
    ▼ [Phase 2-4: 데이터셋 생성]
QAGenerator (50%) + ComparisonGenerator (30%) + ArchitectureGenerator (20%) → SFT 150K건
DPOGenerator (4 전략) → DPO 15K건
CPT Corpus → 650K+ 청크
    │
    ▼ [Phase 5: 품질 관리]
Deduplicator (cosine sim > 0.95 제거) → Scaler (부족분 증강)
    │
    ▼ [Phase 6-7: 검증 & 출력]
Validator → JSONL/TXT 파일 생성
    │
    ▼ [GPU 학습: 3-Phase]
Phase 1: CPT (도메인 사전학습) → Phase 2: SFT (Q-A 학습) → Phase 3: DPO (선호도 정렬)
    │
    ▼ [Adapter 머지]
Base + CPT + SFT + DPO → 최종 서빙 모델
    │
    ▼ [서빙 & 평가]
vLLM 컨테이너 (GPU 4,5, 포트 12810) + Perplexity/Cloze 평가
```

---

## 2. 데이터셋 생성 파이프라인 (v11)

### 2.1 디렉토리 구조

```
scripts/training/v11/
├── main.py                      # CLI 진입점 (build, validate)
├── train_qwen3_32b.py           # GPU 학습 스크립트 (CPT/SFT/DPO)
├── merge_adapters.py            # Adapter 순차 머지
├── merge_adapters_safe.py       # 안전 머지 (검증 포함)
├── toc_pipeline.py              # TOC 기반 PDF 파싱
├── serve_v11.sh                 # vLLM 서빙 스크립트
├── run_training.sh              # 단일 GPU 학습 런처
├── run_dpo_gpu67.sh             # DPO 전용 2-GPU 런처
├── configs/
│   ├── generation_config.yaml   # 데이터셋 생성 설정
│   ├── accelerate_2gpu.yaml     # GPU 4,5 DDP 설정
│   ├── accelerate_single_gpu7.yaml  # GPU 7 단일 설정
│   ├── accelerate_gpu67.yaml    # GPU 6,7 DDP 설정
│   └── accelerate_mp_gpu67.yaml # GPU 6,7 모델 병렬 설정
├── pipeline/
│   ├── config.py                # 파이프라인 설정
│   ├── models.py                # Pydantic 데이터 모델
│   ├── manual_loader.py         # PDF/MD/TXT 매뉴얼 로더
│   ├── knowledge_extractor.py   # 구조화 지식 추출
│   ├── qa_generator.py          # 단일 제품 Q-A 생성 (SFT 50%)
│   ├── comparison_generator.py  # 교차 제품 비교 Q-A (SFT 30%)
│   ├── architecture_generator.py # 아키텍처 생태계 Q-A (SFT 20%)
│   ├── dpo_generator.py         # DPO 선호도 쌍 생성
│   ├── dataset_builder.py       # 전체 오케스트레이터
│   ├── deduplicator.py          # 중복 제거 (cosine similarity)
│   ├── scaler.py                # 데이터 증강 (부족분 보충)
│   └── validator.py             # 형식/분포 검증
└── output/
    ├── sft_train.jsonl          # SFT 학습 데이터 (~120K건)
    ├── sft_eval.jsonl           # SFT 평가 데이터 (~30K건)
    ├── dpo_train.jsonl          # DPO 학습 데이터 (~10K건)
    ├── dpo_eval.jsonl           # DPO 평가 데이터 (~2.5K건)
    └── cpt_corpus.txt           # CPT 코퍼스 (~74MB)
```

### 2.2 데이터 생성 설정 (generation_config.yaml)

| 파라미터 | 값 | 설명 |
|---------|-----|------|
| `target_sft_size` | 150,000 | SFT 총 샘플 수 |
| `target_dpo_size` | 15,000 | DPO 총 페어 수 |
| `sft_single_product_ratio` | 0.50 | 단일 제품 Q-A 비율 |
| `sft_comparison_ratio` | 0.30 | 교차 비교 Q-A 비율 |
| `sft_architecture_ratio` | 0.20 | 아키텍처 Q-A 비율 |
| `dpo_cross_product_ratio` | 0.30 | 제품 혼동 전략 |
| `dpo_fact_mutation_ratio` | 0.30 | 사실 변조 전략 |
| `dpo_over_claiming_ratio` | 0.20 | 과잉 주장 전략 |
| `dpo_speculative_ratio` | 0.20 | 추측성 전략 |
| `qa_variants_per_item` | 5 | 지식 항목당 질문 변형 수 |
| `dedup_threshold` | 0.95 | 중복 판단 코사인 유사도 |
| `train_eval_split` | 0.80 | 학습/평가 분할 비율 |
| `max_token_length` | 4096 | 최대 토큰 길이 |
| `primary_language` | ja | 주 언어 (일본어) |
| `secondary_languages` | [ko, en] | 부 언어 (한국어, 영어) |

### 2.3 데이터 생성 명령어

```bash
# 설정 검증만
python -m scripts.training.v11.main validate --config scripts/training/v11/configs/generation_config.yaml

# 전체 데이터셋 생성 (Dry-run)
python -m scripts.training.v11.main build --dry-run

# 전체 데이터셋 생성 (실행)
python -m scripts.training.v11.main build

# 출력 → scripts/training/v11/output/
```

### 2.4 지식 추출 항목 (7가지 유형)

| 유형 | 주요 필드 | 추출 패턴 |
|------|----------|----------|
| **CommandItem** | name, syntax, parameters, examples | `^([\w]+)\s+(?:コマンド\|command)` |
| **ErrorItem** | error_code, module, cause, resolution | `(-\d{4,5})\s*[:：]?\s*(.+)` |
| **ConfigItem** | parameter_name, default_value, config_file | `^(\w[\w.]+)\s*=\s*(.+)` |
| **APIItem** | signature, parameters, return_type | `^(\w+)\s*\(([^)]*)\)` |
| **FeatureItem** | category, related_components | 개념 섹션 제목 |
| **LimitationItem** | scope, workaround | `制限\|limitation\|제한` |
| **MigrationItem** | source, target, steps | `移行\|migration\|변환` |

### 2.5 DPO 4가지 생성 전략

| 전략 | 비율 | 방법 | 예시 |
|------|-----|------|------|
| **Cross-Product** | 30% | 다른 제품 답변으로 치환 | tjesmgr 질문에 oscmgr 답변 |
| **Fact Mutation** | 30% | 숫자/버전 정보 변조 | 에러코드, 포트번호 변경 |
| **Over-Claiming** | 20% | 가짜 기능 추가 | "AI 분석 기능 내장" 같은 거짓 |
| **Speculative** | 20% | 미검증 미래 주장 추가 | "향후 블록체인 지원 예정" |

### 2.6 출력 데이터 형식

**SFT (ChatML 형식)**:
```json
{
  "messages": [
    {"role": "system", "content": "당신은 OpenFrame 전문 기술 어시스턴트입니다..."},
    {"role": "user", "content": "tjesmgr BOOT 명령어에 대해 설명해주세요."},
    {"role": "assistant", "content": "tjesmgr BOOT는 TJES 노드를 초기화하는..."}
  ],
  "product": "openframe_tjes",
  "language": "ko",
  "category": "single_product"
}
```

**DPO (Preference Pair 형식)**:
```json
{
  "prompt": "tjesmgr とは何ですか？",
  "chosen": "TJES Manager はバッチジョブ管理コマンドで...",
  "rejected": "TACF セキュリティマネージャーで..."
}
```

---

## 3. GPU 학습 파이프라인

### 3.1 v11 학습 (4-bit 양자화 + QLoRA)

#### 3-Phase 학습 파라미터

| 파라미터 | CPT (Phase 1) | SFT (Phase 2) | DPO (Phase 3) |
|---------|--------------|---------------|---------------|
| **목적** | 도메인 사전학습 | Q-A 형식 학습 | 환각 감소 정렬 |
| **데이터** | cpt_corpus.txt (74MB) | sft_train/eval.jsonl | dpo_train/eval.jsonl |
| **LoRA r** | 64 | 64 | 32 |
| **LoRA alpha** | 128 | 128 | 64 |
| **Learning Rate** | 1e-5 | 2e-5 | 5e-6 |
| **Epochs** | 2 | 3 | 2 |
| **Batch Size** | 1 | 1 | 1 |
| **Grad Accum** | 8 | 8 | 4 |
| **Effective Batch** | 8 | 8 | 4 |
| **Max Seq Len** | 4096 | 2048 | 2048 |
| **Warmup Ratio** | 0.05 | 0.05 | 0.10 |
| **Weight Decay** | 0.01 | 0.01 | 0.01 |
| **DPO Beta** | - | - | 0.1 |
| **Optimizer** | paged_adamw_8bit | paged_adamw_8bit | paged_adamw_8bit |
| **Scheduler** | cosine | cosine | cosine |
| **Save Steps** | 500 | 500 | 200 |
| **modules_to_save** | embed_tokens, lm_head | - | - |

#### v11 양자화 설정 (BitsAndBytes)

```python
BitsAndBytesConfig(
    load_in_4bit=True,
    bnb_4bit_quant_type="nf4",
    bnb_4bit_use_double_quant=True,
    bnb_4bit_compute_dtype=torch.bfloat16,
)
```

#### v11 LoRA 타겟 모듈 (공통)

```python
target_modules = [
    "q_proj", "k_proj", "v_proj", "o_proj",   # Attention
    "gate_proj", "up_proj", "down_proj",       # FFN (MLP)
]
```

#### v11 학습 명령어

```bash
# 환경변수 설정 (필수!)
export HF_HOME="/raid/users/ofuser/.cache/huggingface"
export TRANSFORMERS_CACHE="/raid/users/ofuser/.cache/huggingface/hub"
export TMPDIR="/raid/users/ofuser/tmp"
export TOKENIZERS_PARALLELISM=false

# 전체 파이프라인 (CPT→SFT→DPO)
CUDA_VISIBLE_DEVICES=7 accelerate launch \
    --config_file scripts/training/v11/configs/accelerate_single_gpu7.yaml \
    scripts/training/v11/train_qwen3_32b.py --phase all

# 개별 Phase 실행
# CPT
CUDA_VISIBLE_DEVICES=7 accelerate launch \
    --config_file scripts/training/v11/configs/accelerate_single_gpu7.yaml \
    scripts/training/v11/train_qwen3_32b.py --phase cpt

# SFT (CPT adapter 로드)
CUDA_VISIBLE_DEVICES=7 accelerate launch \
    --config_file scripts/training/v11/configs/accelerate_single_gpu7.yaml \
    scripts/training/v11/train_qwen3_32b.py --phase sft \
    --cpt-adapter /raid/users/ofuser/qlora/outputs/v11_qwen3_32b/cpt_adapter

# DPO (GPU 6,7 모델 병렬 — GPU 1장 OOM 문제 회피)
CUDA_VISIBLE_DEVICES=6,7 accelerate launch \
    --config_file scripts/training/v11/configs/accelerate_mp_gpu67.yaml \
    scripts/training/v11/train_qwen3_32b.py --phase dpo \
    --sft-adapter /raid/users/ofuser/qlora/outputs/v11_qwen3_32b/sft_adapter

# 또는 스크립트 사용 (BGE-M3 자동 정지/재기동 포함)
./scripts/training/v11/run_training.sh all     # GPU 7 단일
./scripts/training/v11/run_dpo_gpu67.sh        # GPU 6,7 DPO 전용
```

#### v11 DPO OOM 문제 & 해결

| 항목 | 초기 (OOM) | 수정 후 (성공) |
|------|-----------|--------------|
| GPU | GPU 7, 1장 (40GB) | GPU 6,7, 2장 (80GB) |
| device_map | `{"": 0}` | `"auto"` (모델 병렬) |
| 원인 | DPO는 policy+ref 모델 필요 → ~50-60GB | 2장 분산으로 해결 |

### 3.2 v12 학습 (bf16 Full Precision — 양자화 없음)

> **v11 대비 핵심 변경**: 4-bit 양자화 제거 → bf16 full precision → 머지 시 rounding error 없음

#### v12 CPT 파라미터

| 파라미터 | 값 | v11 대비 변경 |
|---------|-----|-------------|
| **양자화** | **없음 (bf16)** | 4-bit NF4 → 제거 |
| **Optimizer** | **adamw_torch** | paged_adamw_8bit → full precision |
| **GPU** | **4,5,6,7 (4장)** | GPU 7 1장 → 4장 |
| **Batch Size** | **4** | 1 → 4 |
| **Grad Accum** | 8 | 동일 |
| **Effective Batch** | **32** | 8 → 32 |
| **Epochs** | **3** | 2 → 3 |
| **LoRA r** | 64 | 동일 |
| **LoRA alpha** | 128 | 동일 |
| **modules_to_save** | **None** | embed_tokens, lm_head → 제거 (메모리 절감) |
| **Max Seq Len** | 4096 | 동일 |
| **Learning Rate** | 1e-5 | 동일 |

#### v12 디렉토리 구조

```
scripts/training/v12/
├── train_cpt_bf16.py            # CPT 학습 (bf16 full precision)
├── run_cpt.sh                   # 서비스 정지/재기동 포함 런처
├── configs/
│   └── accelerate_mp_gpu67.yaml # 모델 병렬 설정
└── cpt_corpus_dedup.txt         # 중복 제거 코퍼스 (71MB, 1.55M행)
```

#### v12 학습 명령어

```bash
# 스크립트 사용 (권장 — vLLM/BGE-M3 자동 정지/재기동)
./scripts/training/v12/run_cpt.sh

# 수동 실행
CUDA_VISIBLE_DEVICES=4,5,6,7 accelerate launch \
    --config_file scripts/training/v12/configs/accelerate_mp_gpu67.yaml \
    scripts/training/v12/train_cpt_bf16.py

# 학습 모니터링
tail -f /raid/users/ofuser/qlora/outputs/v12_qwen3_32b/training_cpt_*.log
```

#### v12 run_cpt.sh 자동화 흐름

```
1. 서비스 정지 (GPU 해제)
   ├── docker stop vllm_qwen3_32b    (GPU 4,5 해제)
   └── docker stop bge-m3-server     (GPU 6 해제)
2. GPU 메모리 해제 대기 (10초)
3. CPT 학습 실행 (GPU 4,5,6,7)
4. 학습 완료 후 (EXIT trap):
   ├── docker start vllm_qwen3_32b
   ├── docker start bge-m3-server
   └── 헬스체크 대기 (최대 30초)
```

### 3.3 v11 vs v12 비교 요약

| 항목 | v11 | v12 |
|------|-----|-----|
| **양자화** | 4-bit NF4 (BitsAndBytes) | **없음 (bf16 full precision)** |
| **Optimizer** | paged_adamw_8bit | **adamw_torch (full precision)** |
| **GPU 수** | 1~2장 (40~80GB) | **4장 (160GB)** |
| **Effective Batch** | 8 | **32** |
| **코퍼스** | 원본 (74MB) | **중복 제거 (71MB)** |
| **Merge 품질** | rounding error 가능 | **rounding error 없음** |
| **학습 Phases** | CPT + SFT + DPO 완료 | CPT 진행 중 |

---

## 4. Adapter 머지 & 서빙

### 4.1 순차 머지 전략

```
Base Model (Qwen3-32B, bf16)
    │
    ▼ + CPT adapter (r=64) → merge_and_unload()
    │
    ▼ + SFT adapter (r=64) → merge_and_unload()
    │
    ▼ + DPO adapter (r=32) → merge_and_unload()
    │
    ▼ save_pretrained() → 최종 서빙 모델
```

### 4.2 머지 명령어

```bash
# 특정 variant 머지
CUDA_VISIBLE_DEVICES=6,7 python scripts/training/v11/merge_adapters.py --variant cpt-sft-dpo

# 모든 variant 머지
CUDA_VISIBLE_DEVICES=6,7 python scripts/training/v11/merge_adapters.py --variant all

# 안전 머지 (검증 포함)
CUDA_VISIBLE_DEVICES=6,7 python scripts/training/v11/merge_adapters_safe.py --variant cpt-sft-dpo
```

### 4.3 머지 출력 경로

| Variant | 경로 | 크기 |
|---------|------|------|
| CPT only | `/raid/users/ofuser/models/Qwen3-32B-v11-cpt` | ~65GB |
| CPT+SFT | `/raid/users/ofuser/models/Qwen3-32B-v11-cpt-sft` | ~65GB |
| CPT+SFT+DPO | `/raid/users/ofuser/models/Qwen3-32B-v11-cpt-sft-dpo` | ~65GB |

### 4.4 Adapter 경로 & 크기

| Phase | 경로 | 크기 | LoRA |
|-------|------|------|------|
| CPT | `/raid/users/ofuser/qlora/outputs/v11_qwen3_32b/cpt_adapter` | 3.9GB | r=64, alpha=128 |
| SFT | `/raid/users/ofuser/qlora/outputs/v11_qwen3_32b/sft_adapter` | 2.1GB | r=64, alpha=128 |
| DPO | `/raid/users/ofuser/qlora/outputs/v11_qwen3_32b/dpo_adapter` | 1.1GB | r=32, alpha=64 |

### 4.5 vLLM 서빙

```bash
# 서빙 스크립트 (variant 선택)
./scripts/training/v11/serve_v11.sh cpt-sft-dpo    # 전체 학습 모델
./scripts/training/v11/serve_v11.sh cpt-sft         # DPO 제외
./scripts/training/v11/serve_v11.sh cpt              # CPT만
./scripts/training/v11/serve_v11.sh base             # 원본 모델
```

#### vLLM 컨테이너 설정

```bash
docker run -d --name vllm_qwen3_32b \
    --runtime nvidia -e NVIDIA_VISIBLE_DEVICES=4,5 \
    --shm-size 16g -p 12810:8000 \
    --restart unless-stopped \
    -v /raid/users/ofuser/models/Qwen3-32B-v11-cpt-sft-dpo:/opt/models/qwen3-32b:ro \
    vllm/vllm-openai:latest \
    --model /opt/models/qwen3-32b \
    --tensor-parallel-size 2 \
    --max-model-len 8192 \
    --gpu-memory-utilization 0.90 \
    --dtype bfloat16 \
    --trust-remote-code \
    --enable-auto-tool-choice \
    --tool-call-parser hermes
```

| 설정 | 값 |
|------|-----|
| GPU | 4, 5 (A100 40GB x 2) |
| Tensor Parallel | TP=2 |
| Max Context | 8192 tokens |
| GPU Memory Utilization | 90% |
| Precision | bfloat16 |
| Port | 12810 |

---

## 5. 평가 & 검증

### 5.1 Perplexity 평가

```bash
# 단일 모델 평가
python scripts/training/evaluate_perplexity.py \
    --model /raid/users/ofuser/models/Qwen3-32B-v11-cpt-sft-dpo \
    --eval-data scripts/training/v11/output/sft_eval.jsonl

# 다중 모델 비교 (base vs CPT vs SFT vs DPO)
python scripts/training/evaluate_perplexity.py \
    --models \
        /raid/users/ofuser/models/Qwen3-32B \
        /raid/users/ofuser/models/Qwen3-32B-v11-cpt \
        /raid/users/ofuser/models/Qwen3-32B-v11-cpt-sft \
        /raid/users/ofuser/models/Qwen3-32B-v11-cpt-sft-dpo \
    --eval-data scripts/training/v11/output/sft_eval.jsonl
```

**평가 항목**:
- **Perplexity**: 홀드아웃 도메인 텍스트에 대한 토큰 예측 loss
- **Cloze Test**: 30개 OpenFrame 도메인 용어 빈칸 채우기 정확도

### 5.2 E2E Hallucination 테스트

```bash
cd e2e
node e2e_sentence_test.js    # 45개 문장 기반 환각 감지
```

### 5.3 API 테스트

```bash
# 서빙 헬스체크
curl -s http://localhost:12810/v1/models | python3 -m json.tool

# RAG 파이프라인 테스트
TOKEN=$(curl -s -X POST http://localhost:9000/api/v1/auth/login \
    -H "Content-Type: application/json" \
    -d @scripts/login.json | python -c "import sys,json; print(json.load(sys.stdin)['data']['access_token'])")

curl -s -X POST http://localhost:9000/api/v1/agents/stream \
    -H "Content-Type: application/json" \
    -H "Authorization: Bearer $TOKEN" \
    -d '{"task": "tjesmgr BOOT 명령어 설명", "agent_type": "rag"}'
```

### 5.4 롤백 절차 (품질 저하 시)

```bash
# 1. 현재 컨테이너 정지
docker stop vllm_qwen3_32b && docker rm vllm_qwen3_32b

# 2. 이전 variant로 서빙 전환
./scripts/training/v11/serve_v11.sh cpt-sft    # DPO 제외
# 또는
./scripts/training/v11/serve_v11.sh base       # 원본으로 복원

# 3. 헬스체크
curl -s http://localhost:12810/v1/models | python3 -m json.tool
```

---

## 6. GPU 할당 맵

| GPU | 서빙 시 | v11 학습 시 | v12 학습 시 |
|-----|---------|------------|------------|
| 0 | Mistral NeMo Code (12802) | 유지 | 유지 |
| 1-3 | vLLM Workers (기타) | 유지 | 유지 |
| 4 | **Qwen3-32B TP0 (12810)** | 유지 | **CPT 학습** (정지 후) |
| 5 | **Qwen3-32B TP1 (12810)** | 유지 | **CPT 학습** (정지 후) |
| 6 | **BGE-M3 Embedding (12801)** | DPO 학습 (정지 후) | **CPT 학습** (정지 후) |
| 7 | **Nemotron Nano 9B (12800)** | CPT/SFT 학습 | **CPT 학습** |

---

## 7. 필수 환경변수

```bash
# 디스크 경로 (루트 디스크 사용 금지!)
export HF_HOME="/raid/users/ofuser/.cache/huggingface"
export TRANSFORMERS_CACHE="/raid/users/ofuser/.cache/huggingface/hub"
export HF_DATASETS_CACHE="/raid/users/ofuser/.cache/huggingface/datasets"
export TMPDIR="/raid/users/ofuser/tmp"
export TOKENIZERS_PARALLELISM=false

# OOM 방지 (DPO 학습 시)
export PYTORCH_CUDA_ALLOC_CONF="expandable_segments:True"
```

---

## 8. Accelerate 설정 비교

### 단일 GPU (GPU 7)
```yaml
# configs/accelerate_single_gpu7.yaml
compute_environment: LOCAL_MACHINE
distributed_type: "NO"
gpu_ids: "7"
mixed_precision: bf16
num_processes: 1
```

### 2-GPU DDP (GPU 4,5)
```yaml
# configs/accelerate_2gpu.yaml
compute_environment: LOCAL_MACHINE
distributed_type: MULTI_GPU
gpu_ids: "4,5"
mixed_precision: bf16
num_processes: 2
```

### 2-GPU 모델 병렬 (GPU 6,7)
```yaml
# configs/accelerate_mp_gpu67.yaml
compute_environment: LOCAL_MACHINE
distributed_type: "NO"
mixed_precision: bf16
num_processes: 1           # 단일 프로세스 + device_map="auto"
```

> **Note**: 모델 병렬은 `num_processes: 1`이지만, 코드 내 `device_map="auto"`로 여러 GPU에 분산.

---

## 9. 전체 실행 체크리스트

### 데이터셋 생성 → 학습 → 서빙 전체 흐름

```bash
# ── Step 1: 데이터셋 생성 ──
python -m scripts.training.v11.main build

# ── Step 2: 학습 (순차 실행) ──
# CPT (GPU 7, ~4시간)
./scripts/training/v11/run_training.sh cpt

# SFT (GPU 7, ~6시간)
./scripts/training/v11/run_training.sh sft

# DPO (GPU 6,7, ~2시간)
./scripts/training/v11/run_dpo_gpu67.sh

# ── Step 3: Adapter 머지 ──
CUDA_VISIBLE_DEVICES=6,7 python scripts/training/v11/merge_adapters.py --variant cpt-sft-dpo

# ── Step 4: 서빙 시작 ──
./scripts/training/v11/serve_v11.sh cpt-sft-dpo

# ── Step 5: 검증 ──
curl -s http://localhost:12810/v1/models | python3 -m json.tool
cd e2e && node e2e_sentence_test.js
```
