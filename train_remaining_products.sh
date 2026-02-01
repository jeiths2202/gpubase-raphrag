#!/bin/bash
# 나머지 제품 학습 (ofcobol, xsp_openframe, tmax)

set -e
cd /home/ofuser/workspaces/ijswork/gpubase-raphrag-new/test_0130
source /home/ofuser/workspaces/ijswork/gpubase-raphrag-new/scripts/trainning/qlora_training_20260124_093751/venv/bin/activate

export HF_HUB_OFFLINE=1
export PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True

DATA_DIR="./training_data_products"
LOG_FILE="training_remaining_products.log"

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "$LOG_FILE"
}

log "=============================================="
log "나머지 제품 학습 시작 (GPU 5)"
log "=============================================="

# 1. ofcobol
log ""
log "[1/3] OpenFrame COBOL 학습 시작"
mkdir -p ./qlora_adapters/ofcobol

python train_openframe_qlora.py \
    --data "${DATA_DIR}/ofcobol_combined.jsonl" \
    --gpu 5 \
    --epochs 3 \
    --batch_size 1 \
    --gradient_accumulation_steps 16 \
    --language ko \
    --output ./qlora_adapters/ofcobol 2>&1 | tee -a training_ofcobol.log

log "[1/3] OpenFrame COBOL 학습 완료"

# 2. xsp_openframe - combined 파일 생성
log ""
log "[2/3] XSP OpenFrame 학습 시작"
cat "${DATA_DIR}/xsp_openframe_ko.jsonl" "${DATA_DIR}/xsp_openframe_ja.jsonl" "${DATA_DIR}/xsp_openframe_en.jsonl" > "${DATA_DIR}/xsp_openframe_combined.jsonl"
mkdir -p ./qlora_adapters/xsp_openframe

python train_openframe_qlora.py \
    --data "${DATA_DIR}/xsp_openframe_combined.jsonl" \
    --gpu 5 \
    --epochs 3 \
    --batch_size 1 \
    --gradient_accumulation_steps 16 \
    --language ko \
    --output ./qlora_adapters/xsp_openframe 2>&1 | tee -a training_xsp_openframe.log

log "[2/3] XSP OpenFrame 학습 완료"

# 3. tmax - combined 파일 생성
log ""
log "[3/3] Tmax 학습 시작"
cat "${DATA_DIR}/tmax_ko.jsonl" "${DATA_DIR}/tmax_ja.jsonl" "${DATA_DIR}/tmax_en.jsonl" > "${DATA_DIR}/tmax_combined.jsonl"
mkdir -p ./qlora_adapters/tmax

python train_openframe_qlora.py \
    --data "${DATA_DIR}/tmax_combined.jsonl" \
    --gpu 5 \
    --epochs 3 \
    --batch_size 1 \
    --gradient_accumulation_steps 16 \
    --language ko \
    --output ./qlora_adapters/tmax 2>&1 | tee -a training_tmax.log

log "[3/3] Tmax 학습 완료"

log ""
log "=============================================="
log "전체 학습 완료: $(date)"
log "=============================================="
