#!/bin/bash
# =============================================================================
# 남은 학습 실행 (영어 + 7개 제품) - GPU 5 전용
# =============================================================================

set -e

cd /home/ofuser/workspaces/ijswork/gpubase-raphrag-new/test_0130
source /home/ofuser/workspaces/ijswork/gpubase-raphrag-new/scripts/trainning/qlora_training_20260124_093751/venv/bin/activate

export HF_HUB_OFFLINE=1
export PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True

LOG_FILE="training_remaining.log"

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "$LOG_FILE"
}

log "=============================================="
log "남은 학습 시작 (GPU 5)"
log "=============================================="

# =============================================================================
# Phase 1: MVS 영어 학습
# =============================================================================
log ""
log "[1/8] MVS 영어 학습 시작"

python train_openframe_qlora.py \
    --data training_data_multilang/combined_en.jsonl \
    --gpu 5 \
    --epochs 3 \
    --batch_size 1 \
    --gradient_accumulation_steps 16 \
    --language en \
    --output ./openframe_qlora_adapter 2>&1 | tee -a training_en_gpu5.log

log "[1/8] MVS 영어 학습 완료"

# =============================================================================
# Phase 2: 7개 제품 학습
# =============================================================================
PRODUCTS=("msp_openframe" "vos3_openframe" "tibero7" "ofasm" "ofcobol" "xsp_openframe" "tmax")
PRODUCT_NAMES=("MSP OpenFrame 7.3" "VOS3 OpenFrame 2.0" "Tibero 7" "OpenFrame ASM 4" "OpenFrame COBOL 4" "XSP OpenFrame 7.3" "Tmax 6.0")

mkdir -p ./qlora_adapters

for i in "${!PRODUCTS[@]}"; do
    PRODUCT="${PRODUCTS[$i]}"
    PRODUCT_NAME="${PRODUCT_NAMES[$i]}"
    NUM=$((i + 2))  # 2부터 시작 (영어가 1번)

    log ""
    log "[$NUM/8] $PRODUCT_NAME 학습 시작"

    # 결합 파일 생성
    DATA_DIR="./training_data_products"
    COMBINED="${DATA_DIR}/${PRODUCT}_combined.jsonl"
    rm -f "$COMBINED"

    for LANG in ko ja en; do
        [ -f "${DATA_DIR}/${PRODUCT}_${LANG}.jsonl" ] && cat "${DATA_DIR}/${PRODUCT}_${LANG}.jsonl" >> "$COMBINED"
    done

    DATA_COUNT=$(wc -l < "$COMBINED" 2>/dev/null || echo "0")
    log "  데이터 수: $DATA_COUNT"

    if [ "$DATA_COUNT" -lt 50 ]; then
        log "  ⚠ 데이터 부족. 스킵."
        continue
    fi

    OUTPUT_DIR="./qlora_adapters/${PRODUCT}"
    mkdir -p "$OUTPUT_DIR"

    python train_openframe_qlora.py \
        --data "$COMBINED" \
        --gpu 5 \
        --epochs 3 \
        --batch_size 1 \
        --gradient_accumulation_steps 16 \
        --language ko \
        --output "$OUTPUT_DIR" 2>&1 | tee -a "training_${PRODUCT}.log"

    log "[$NUM/8] $PRODUCT_NAME 학습 완료"
done

log ""
log "=============================================="
log "전체 학습 완료: $(date)"
log "=============================================="

# 어댑터 목록 출력
log ""
log "생성된 어댑터:"
ls -la ./openframe_qlora_adapter/ 2>/dev/null | tail -5
ls -la ./qlora_adapters/ 2>/dev/null
