#!/bin/bash
# OpenFrame QLoRA Training - All Languages (Sequential)
# GPU 5,6 사용, 한국어 -> 일본어 -> 영어 순서

cd /home/ofuser/workspaces/ijswork/gpubase-raphrag-new/test_0130
source /home/ofuser/workspaces/ijswork/gpubase-raphrag-new/scripts/trainning/qlora_training_20260124_093751/venv/bin/activate

export HF_HUB_OFFLINE=1
export PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True

echo "=============================================="
echo "OpenFrame QLoRA Training - All Languages"
echo "Started at: $(date)"
echo "=============================================="

# 1. Korean Training (Already running separately)
# echo "[1/3] Starting Korean training..."
# python train_openframe_qlora.py \
#     --data training_data_multilang/combined_ko.jsonl \
#     --gpu 5,6 \
#     --epochs 3 \
#     --batch_size 2 \
#     --language ko \
#     --output ./openframe_qlora_adapter 2>&1 | tee training_ko.log
# echo "[1/3] Korean training completed at: $(date)"

# 2. Japanese Training
echo ""
echo "[2/3] Starting Japanese training..."
echo "Started at: $(date)"
python train_openframe_qlora.py \
    --data training_data_multilang/combined_ja.jsonl \
    --gpu 5,6 \
    --epochs 3 \
    --batch_size 2 \
    --language ja \
    --output ./openframe_qlora_adapter 2>&1 | tee training_ja.log
echo "[2/3] Japanese training completed at: $(date)"

# 3. English Training
echo ""
echo "[3/3] Starting English training..."
echo "Started at: $(date)"
python train_openframe_qlora.py \
    --data training_data_multilang/combined_en.jsonl \
    --gpu 5,6 \
    --epochs 3 \
    --batch_size 2 \
    --language en \
    --output ./openframe_qlora_adapter 2>&1 | tee training_en.log
echo "[3/3] English training completed at: $(date)"

echo ""
echo "=============================================="
echo "All training completed at: $(date)"
echo "=============================================="
echo ""
echo "Adapter locations:"
ls -la openframe_qlora_adapter/
