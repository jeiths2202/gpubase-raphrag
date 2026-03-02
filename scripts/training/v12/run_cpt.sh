#!/bin/bash
# ─────────────────────────────────────────────────────────
# v12 CPT Training — Full bf16 (NO quantization)
#
# 1) vllm_qwen3_32b + bge-m3-server 일시 중지 (GPU 4,5,6 해제)
# 2) GPU 4,5,6,7 모델 병렬로 CPT 학습
# 3) 학습 완료 후 vllm_qwen3_32b + bge-m3-server 재기동
#
# Usage:
#   ./run_cpt.sh
#   ./run_cpt.sh dry-run
# ─────────────────────────────────────────────────────────
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
PHASE="${1:-train}"

BGE_CONTAINER="bge-m3-server"
VLLM_CONTAINER="vllm_qwen3_32b"
OUTPUT_BASE="/raid/users/ofuser/qlora/outputs/v12_qwen3_32b"
ACCELERATE_CONFIG="$SCRIPT_DIR/configs/accelerate_mp_gpu67.yaml"
TRAIN_SCRIPT="$SCRIPT_DIR/train_cpt_bf16.py"
LOG_FILE="$OUTPUT_BASE/training_cpt_$(date +%Y%m%d_%H%M%S).log"

# 환경 변수 (루트 디스크 사용 방지)
export HF_HOME="/raid/users/ofuser/.cache/huggingface"
export TRANSFORMERS_CACHE="/raid/users/ofuser/.cache/huggingface/hub"
export HF_DATASETS_CACHE="/raid/users/ofuser/.cache/huggingface/datasets"
export TMPDIR="/raid/users/ofuser/tmp"
export TOKENIZERS_PARALLELISM=false
export CUDA_VISIBLE_DEVICES="4,5,6,7"
export PYTORCH_CUDA_ALLOC_CONF="expandable_segments:True"

mkdir -p "$TMPDIR"
mkdir -p "$OUTPUT_BASE"

echo "═══════════════════════════════════════════════════════════"
echo "  Qwen3-32B v12 CPT — Full bf16 (NO quantization)"
echo "  GPU: $CUDA_VISIBLE_DEVICES"
echo "  Output: $OUTPUT_BASE"
echo "  Log: $LOG_FILE"
echo "═══════════════════════════════════════════════════════════"

# ── dry-run ──────────────────────────────────────────────
if [ "$PHASE" = "dry-run" ]; then
    cd "$PROJECT_ROOT"
    python3 "$TRAIN_SCRIPT" --dry-run
    exit 0
fi

# ── cleanup: 종료 시 서비스 재기동 ─────────────────────────
cleanup() {
    local exit_code=$?
    echo ""
    echo "═══════════════════════════════════════════════════════════"
    echo "  서비스 재기동 중 (vLLM + BGE-M3)..."
    echo "═══════════════════════════════════════════════════════════"

    # vLLM 재기동 (GPU 4,5)
    echo "  [1/2] $VLLM_CONTAINER 재기동..."
    docker start "$VLLM_CONTAINER"
    sleep 5

    # BGE-M3 재기동 (GPU 6)
    echo "  [2/2] $BGE_CONTAINER 재기동..."
    docker start "$BGE_CONTAINER"

    echo "  헬스체크 대기 중..."
    for i in $(seq 1 30); do
        VLLM_STATUS=$(docker inspect --format='{{.State.Status}}' "$VLLM_CONTAINER" 2>/dev/null || echo "unknown")
        BGE_STATUS=$(docker inspect --format='{{.State.Health.Status}}' "$BGE_CONTAINER" 2>/dev/null || echo "unknown")

        if [ "$VLLM_STATUS" = "running" ] && [ "$BGE_STATUS" = "healthy" ]; then
            echo "  ✅ 모든 서비스 정상 기동 확인"
            break
        fi
        echo "    [$i/30] vLLM=$VLLM_STATUS, BGE=$BGE_STATUS (5초 대기...)"
        sleep 5
    done

    nvidia-smi --query-gpu=index,memory.used,memory.free --format=csv,noheader -i 4,5,6,7
    echo ""

    if [ $exit_code -eq 0 ]; then
        echo "  ✅ CPT 학습 정상 완료 + 서비스 재기동 완료"
    else
        echo "  ❌ CPT 학습 실패 (exit code: $exit_code) + 서비스 재기동 완료"
    fi
    echo "═══════════════════════════════════════════════════════════"
    exit $exit_code
}
trap cleanup EXIT

# ── Step 1: 서비스 일시 중지 (GPU 4,5,6 해제) ─────────────
echo ""
echo "── Step 1: 서비스 일시 중지 ──"

for CONTAINER in "$VLLM_CONTAINER" "$BGE_CONTAINER"; do
    if docker ps --format '{{.Names}}' | grep -q "^${CONTAINER}$"; then
        docker stop "$CONTAINER"
        echo "  ✅ $CONTAINER 중지 완료"
    else
        echo "  ⚠️  $CONTAINER 이미 중지 상태"
    fi
done

echo "  GPU 메모리 해제 대기 (10초)..."
sleep 10

echo ""
echo "  GPU 메모리 상태:"
nvidia-smi --query-gpu=index,memory.used,memory.free --format=csv,noheader -i 4,5,6,7
echo ""

# ── Step 2: CPT 학습 ────────────────────────────────────
echo "── Step 2: CPT 학습 시작 ──"
echo "  시작: $(date '+%Y-%m-%d %H:%M:%S')"
echo ""

cd "$PROJECT_ROOT"

accelerate launch \
    --config_file "$ACCELERATE_CONFIG" \
    "$TRAIN_SCRIPT" \
    2>&1 | tee "$LOG_FILE"

echo ""
echo "  ✅ CPT 학습 완료: $(date '+%Y-%m-%d %H:%M:%S')"
echo "  Output: $OUTPUT_BASE"
