#!/bin/bash
# ─────────────────────────────────────────────────────────
# Qwen3-32B v11 QLoRA Training Launch Script
# GPU 6,7 사용 (vLLM 서빙 GPU 4,5와 독립)
#
# Usage:
#   ./run_training.sh all        # 전체 파이프라인 (CPT→SFT→DPO)
#   ./run_training.sh cpt        # CPT만
#   ./run_training.sh sft        # SFT만 (CPT adapter 자동 감지)
#   ./run_training.sh dpo        # DPO만 (SFT adapter 자동 감지)
#   ./run_training.sh sft-dpo    # SFT→DPO
#   ./run_training.sh dry-run    # 설정 검증만
# ─────────────────────────────────────────────────────────
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"
PHASE="${1:-all}"

# ── 환경 변수 (루트 디스크 사용 방지) ──────────────────────
export HF_HOME="/raid/users/ofuser/.cache/huggingface"
export TRANSFORMERS_CACHE="/raid/users/ofuser/.cache/huggingface/hub"
export HF_DATASETS_CACHE="/raid/users/ofuser/.cache/huggingface/datasets"
export TMPDIR="/raid/users/ofuser/tmp"
export TOKENIZERS_PARALLELISM=false

# GPU 설정 (7번 단일 — vLLM 4,5 / BGE-M3 6 유지)
export CUDA_VISIBLE_DEVICES="7"

# Output 경로
OUTPUT_BASE="/raid/users/ofuser/qlora/outputs/v11_qwen3_32b"
ACCELERATE_CONFIG="$SCRIPT_DIR/configs/accelerate_single_gpu7.yaml"
TRAIN_SCRIPT="$SCRIPT_DIR/train_qwen3_32b.py"

echo "═══════════════════════════════════════════════════════════"
echo "  Qwen3-32B v11 QLoRA Training"
echo "  Phase: $PHASE"
echo "  Output: $OUTPUT_BASE"
echo "  GPU: $CUDA_VISIBLE_DEVICES (vLLM 4,5 + BGE-M3 6 유지)"
echo "═══════════════════════════════════════════════════════════"

# ── tmp 디렉토리 생성 ──────────────────────────────────────
mkdir -p "$TMPDIR"
mkdir -p "$OUTPUT_BASE"

# ── Dry run ────────────────────────────────────────────────
if [ "$PHASE" = "dry-run" ]; then
    echo ""
    echo "=== Dry Run (설정 검증) ==="
    cd "$PROJECT_ROOT"
    python3 "$TRAIN_SCRIPT" --phase all --dry-run
    exit 0
fi

# ── GPU 메모리 확인 ────────────────────────────────────────
echo ""
echo "GPU 메모리 상태 (학습 대상):"
nvidia-smi --query-gpu=index,memory.used,memory.free --format=csv,noheader -i 7
echo ""
echo "서빙 상태 (유지):"
nvidia-smi --query-gpu=index,memory.used,memory.free --format=csv,noheader -i 4,5,6
echo ""

# ── adapter 경로 자동 감지 ──────────────────────────────────
CPT_ADAPTER_ARG=""
SFT_ADAPTER_ARG=""

if [ "$PHASE" = "sft" ] || [ "$PHASE" = "sft-dpo" ]; then
    CPT_ADAPTER="$OUTPUT_BASE/cpt_adapter"
    if [ -d "$CPT_ADAPTER" ]; then
        echo "✓ CPT adapter 감지: $CPT_ADAPTER"
        CPT_ADAPTER_ARG="--cpt-adapter $CPT_ADAPTER"
    else
        echo "⚠️  CPT adapter 미발견. base 모델에서 SFT를 시작합니다."
    fi
fi

if [ "$PHASE" = "dpo" ]; then
    SFT_ADAPTER="$OUTPUT_BASE/sft_adapter"
    if [ -d "$SFT_ADAPTER" ]; then
        echo "✓ SFT adapter 감지: $SFT_ADAPTER"
        SFT_ADAPTER_ARG="--sft-adapter $SFT_ADAPTER"
    else
        echo "⚠️  SFT adapter 미발견. base 모델에서 DPO를 시작합니다."
    fi
fi

# ── 학습 시작 ──────────────────────────────────────────────
echo ""
echo "🚀 학습 시작: $(date '+%Y-%m-%d %H:%M:%S')"
echo ""

cd "$PROJECT_ROOT"

accelerate launch \
    --config_file "$ACCELERATE_CONFIG" \
    "$TRAIN_SCRIPT" \
    --phase "$PHASE" \
    --output-base "$OUTPUT_BASE" \
    $CPT_ADAPTER_ARG \
    $SFT_ADAPTER_ARG \
    2>&1 | tee "$OUTPUT_BASE/training_${PHASE}_$(date +%Y%m%d_%H%M%S).log"

echo ""
echo "✅ 학습 완료: $(date '+%Y-%m-%d %H:%M:%S')"
echo "   Output: $OUTPUT_BASE"
echo ""

# 학습 결과 요약
if [ -f "$OUTPUT_BASE/training_report.json" ]; then
    echo "=== Training Report ==="
    cat "$OUTPUT_BASE/training_report.json"
    echo ""
fi
