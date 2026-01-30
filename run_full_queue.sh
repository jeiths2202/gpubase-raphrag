#!/bin/bash
# =============================================================================
# 전체 학습 큐 (MVS + 7개 제품)
# =============================================================================
# 한국어 학습이 완료된 후 순차적으로 실행:
# 1. MVS 일본어 학습
# 2. MVS 영어 학습
# 3. 7개 제품 학습 (msp, vos3, tibero7, ofasm, ofcobol, xsp, tmax)
# =============================================================================

set -e

cd /home/ofuser/workspaces/ijswork/gpubase-raphrag-new/test_0130
source /home/ofuser/workspaces/ijswork/gpubase-raphrag-new/scripts/trainning/qlora_training_20260124_093751/venv/bin/activate

export HF_HUB_OFFLINE=1
export PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True

LOG_FILE="full_queue_$(date +%Y%m%d_%H%M%S).log"

echo "=============================================="
echo "전체 학습 큐 시작"
echo "시작 시간: $(date)"
echo "로그 파일: $LOG_FILE"
echo "=============================================="

# 한국어 학습 완료 대기 (PID 모니터링)
KO_PID=$(pgrep -f "train_openframe_qlora.py.*combined_ko" || echo "")

if [ -n "$KO_PID" ]; then
    echo "[대기] 한국어 학습 (PID: $KO_PID) 완료 대기 중..."
    while kill -0 "$KO_PID" 2>/dev/null; do
        sleep 60
        echo "  $(date): 한국어 학습 진행 중..."
    done
    echo "[완료] 한국어 학습 완료: $(date)"
fi

# =============================================================================
# Phase 1: MVS 일본어 학습
# =============================================================================
echo ""
echo "=============================================="
echo "[Phase 1/3] MVS 일본어 학습"
echo "시작 시간: $(date)"
echo "=============================================="

python train_openframe_qlora.py \
    --data training_data_multilang/combined_ja.jsonl \
    --gpu 5,6 \
    --epochs 3 \
    --batch_size 2 \
    --language ja \
    --output ./openframe_qlora_adapter 2>&1 | tee training_ja.log

echo "[Phase 1/3] MVS 일본어 학습 완료: $(date)"

# =============================================================================
# Phase 2: MVS 영어 학습
# =============================================================================
echo ""
echo "=============================================="
echo "[Phase 2/3] MVS 영어 학습"
echo "시작 시간: $(date)"
echo "=============================================="

python train_openframe_qlora.py \
    --data training_data_multilang/combined_en.jsonl \
    --gpu 5,6 \
    --epochs 3 \
    --batch_size 2 \
    --language en \
    --output ./openframe_qlora_adapter 2>&1 | tee training_en.log

echo "[Phase 2/3] MVS 영어 학습 완료: $(date)"

# =============================================================================
# Phase 3: 7개 제품 학습
# =============================================================================
echo ""
echo "=============================================="
echo "[Phase 3/3] 7개 제품 학습"
echo "시작 시간: $(date)"
echo "=============================================="

PRODUCTS=("msp_openframe" "vos3_openframe" "tibero7" "ofasm" "ofcobol" "xsp_openframe" "tmax")
PRODUCT_NAMES=("MSP OpenFrame 7.3" "VOS3 OpenFrame 2.0" "Tibero 7" "OpenFrame ASM 4" "OpenFrame COBOL 4" "XSP OpenFrame 7.3" "Tmax 6.0")

mkdir -p ./qlora_adapters

for i in "${!PRODUCTS[@]}"; do
    PRODUCT="${PRODUCTS[$i]}"
    PRODUCT_NAME="${PRODUCT_NAMES[$i]}"
    NUM=$((i + 1))

    echo ""
    echo "[$NUM/7] $PRODUCT_NAME 학습 시작: $(date)"

    # 결합 파일 생성
    DATA_DIR="./training_data_products"
    COMBINED="${DATA_DIR}/${PRODUCT}_combined.jsonl"
    rm -f "$COMBINED"

    for LANG in ko ja en; do
        [ -f "${DATA_DIR}/${PRODUCT}_${LANG}.jsonl" ] && cat "${DATA_DIR}/${PRODUCT}_${LANG}.jsonl" >> "$COMBINED"
    done

    DATA_COUNT=$(wc -l < "$COMBINED" 2>/dev/null || echo "0")
    echo "  학습 데이터: $DATA_COUNT"

    if [ "$DATA_COUNT" -lt 50 ]; then
        echo "  ⚠ 데이터 부족. 스킵."
        continue
    fi

    OUTPUT_DIR="./qlora_adapters/${PRODUCT}"
    mkdir -p "$OUTPUT_DIR"

    python train_openframe_qlora.py \
        --data "$COMBINED" \
        --gpu 5,6 \
        --epochs 3 \
        --batch_size 2 \
        --language ko \
        --output "$OUTPUT_DIR" 2>&1 | tee "training_${PRODUCT}.log"

    echo "[$NUM/7] $PRODUCT_NAME 학습 완료: $(date)"
done

echo ""
echo "=============================================="
echo "전체 학습 큐 완료"
echo "완료 시간: $(date)"
echo "=============================================="

# 검증 실행
echo ""
echo "어댑터 검증 중..."
python validate_all_adapters.py

echo ""
echo "=============================================="
echo "다음 단계: docker-compose.yml 어댑터 등록"
echo "=============================================="
echo ""
echo "  python update_docker_compose.py --preview"
