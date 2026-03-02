#!/bin/bash
# ─────────────────────────────────────────────────────────
# v11 DPO 재학습 스크립트 (GPU 6,7 사용)
#
# 1) bge-m3-server 컨테이너 일시 중지 (GPU 6 해제)
# 2) GPU 6,7 모델 병렬(device_map=auto)로 DPO 학습 실행
# 3) 학습 완료 후 bge-m3-server 재기동
#
# Note: DDP(데이터 병렬)가 아닌 모델 병렬 사용.
#       32B 모델을 2장에 분산 적재하여 OOM 방지.
#
# Usage:
#   ./run_dpo_gpu67.sh
# ─────────────────────────────────────────────────────────
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"

BGE_CONTAINER="bge-m3-server"
OUTPUT_BASE="/raid/users/ofuser/qlora/outputs/v11_qwen3_32b"
SFT_ADAPTER="$OUTPUT_BASE/sft_adapter"
DPO_OUTPUT="$OUTPUT_BASE/dpo_adapter"
# 모델 병렬 모드: 단일 프로세스 + device_map="auto"로 GPU 2장에 분산
ACCELERATE_CONFIG="$SCRIPT_DIR/configs/accelerate_mp_gpu67.yaml"
TRAIN_SCRIPT="$SCRIPT_DIR/train_qwen3_32b.py"
LOG_FILE="$OUTPUT_BASE/training_dpo_gpu67_$(date +%Y%m%d_%H%M%S).log"

# 환경 변수 (루트 디스크 사용 방지)
export HF_HOME="/raid/users/ofuser/.cache/huggingface"
export TRANSFORMERS_CACHE="/raid/users/ofuser/.cache/huggingface/hub"
export HF_DATASETS_CACHE="/raid/users/ofuser/.cache/huggingface/datasets"
export TMPDIR="/raid/users/ofuser/tmp"
export TOKENIZERS_PARALLELISM=false
export CUDA_VISIBLE_DEVICES="6,7"
# OOM 방지: PyTorch 메모리 단편화 완화
export PYTORCH_CUDA_ALLOC_CONF="expandable_segments:True"

mkdir -p "$TMPDIR"

# ── cleanup: 스크립트 종료 시 bge-m3-server 반드시 재기동 ──
cleanup() {
    local exit_code=$?
    echo ""
    echo "═══════════════════════════════════════════════════════════"
    echo "  BGE-M3 서버 재기동 중..."
    echo "═══════════════════════════════════════════════════════════"
    docker start "$BGE_CONTAINER"

    # 헬스체크 대기 (최대 120초)
    echo "  헬스체크 대기 중..."
    for i in $(seq 1 24); do
        STATUS=$(docker inspect --format='{{.State.Health.Status}}' "$BGE_CONTAINER" 2>/dev/null || echo "unknown")
        if [ "$STATUS" = "healthy" ]; then
            echo "  ✅ $BGE_CONTAINER 정상 기동 확인 (healthy)"
            break
        fi
        echo "    [$i/24] 상태: $STATUS (5초 대기...)"
        sleep 5
    done

    STATUS=$(docker inspect --format='{{.State.Health.Status}}' "$BGE_CONTAINER" 2>/dev/null || echo "unknown")
    if [ "$STATUS" != "healthy" ]; then
        echo "  ⚠️  $BGE_CONTAINER 헬스체크 타임아웃. 수동 확인 필요."
        echo "     docker logs $BGE_CONTAINER --tail 20"
    fi

    echo ""
    echo "  GPU 상태:"
    nvidia-smi --query-gpu=index,memory.used,memory.free --format=csv,noheader -i 6,7
    echo ""

    if [ $exit_code -eq 0 ]; then
        echo "  ✅ DPO 학습 정상 완료 + BGE-M3 재기동 완료"
    else
        echo "  ❌ DPO 학습 실패 (exit code: $exit_code) + BGE-M3 재기동 완료"
    fi
    echo "═══════════════════════════════════════════════════════════"
    exit $exit_code
}
trap cleanup EXIT

# ── 사전 검증 ────────────────────────────────────────────
echo "═══════════════════════════════════════════════════════════"
echo "  Qwen3-32B v11 DPO 재학습 (GPU 6,7 모델 병렬)"
echo "  SFT adapter: $SFT_ADAPTER"
echo "  Output:      $DPO_OUTPUT"
echo "  Log:         $LOG_FILE"
echo "═══════════════════════════════════════════════════════════"

# SFT adapter 존재 확인
if [ ! -d "$SFT_ADAPTER" ]; then
    echo "❌ SFT adapter 미발견: $SFT_ADAPTER"
    echo "   CPT→SFT 학습을 먼저 완료해야 합니다."
    exit 1
fi
echo "✓ SFT adapter 확인: $(du -sh "$SFT_ADAPTER" | cut -f1)"

# 이전 실패한 DPO 출력 정리
if [ -d "$DPO_OUTPUT" ]; then
    if [ -z "$(ls -A "$DPO_OUTPUT" 2>/dev/null)" ]; then
        echo "✓ 이전 빈 DPO 디렉토리 제거"
        rm -rf "$DPO_OUTPUT"
    else
        BACKUP="$OUTPUT_BASE/dpo_adapter_backup_$(date +%Y%m%d_%H%M%S)"
        echo "⚠️  이전 DPO 출력 백업: $BACKUP"
        mv "$DPO_OUTPUT" "$BACKUP"
    fi
fi

# ── Step 1: BGE-M3 컨테이너 일시 중지 ────────────────────
echo ""
echo "── Step 1: $BGE_CONTAINER 일시 중지 ──"
if docker ps --format '{{.Names}}' | grep -q "^${BGE_CONTAINER}$"; then
    docker stop "$BGE_CONTAINER"
    echo "  ✅ $BGE_CONTAINER 중지 완료"
else
    echo "  ⚠️  $BGE_CONTAINER 이미 중지 상태"
fi

# GPU 메모리 해제 대기
echo "  GPU 메모리 해제 대기 (10초)..."
sleep 10

echo ""
echo "  GPU 메모리 상태 (학습 대상):"
nvidia-smi --query-gpu=index,memory.used,memory.free --format=csv,noheader -i 6,7
echo ""

# ── Step 2: DPO 학습 실행 ────────────────────────────────
echo "── Step 2: DPO 학습 시작 ──"
echo "  시작: $(date '+%Y-%m-%d %H:%M:%S')"
echo ""

cd "$PROJECT_ROOT"

accelerate launch \
    --config_file "$ACCELERATE_CONFIG" \
    "$TRAIN_SCRIPT" \
    --phase dpo \
    --output-base "$OUTPUT_BASE" \
    --sft-adapter "$SFT_ADAPTER" \
    2>&1 | tee "$LOG_FILE"

echo ""
echo "  ✅ DPO 학습 완료: $(date '+%Y-%m-%d %H:%M:%S')"
echo "  Output: $DPO_OUTPUT"

# 학습 결과 확인
if [ -d "$DPO_OUTPUT" ] && [ -f "$DPO_OUTPUT/adapter_config.json" ]; then
    echo "  Adapter 크기: $(du -sh "$DPO_OUTPUT" | cut -f1)"
    echo ""
    echo "=== DPO Adapter 파일 ==="
    ls -lh "$DPO_OUTPUT"/adapter_*.safetensors 2>/dev/null || echo "  (safetensors 파일 없음)"
else
    echo "  ❌ DPO adapter 파일이 생성되지 않았습니다."
    exit 1
fi

# Step 3 (BGE-M3 재기동)는 cleanup trap에서 자동 실행
