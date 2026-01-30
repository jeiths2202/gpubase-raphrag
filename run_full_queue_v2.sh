#!/bin/bash
# =============================================================================
# 전체 학습 큐 v2 (개선된 프로세스 감지)
# =============================================================================
# 한국어 학습 완료를 정확히 감지하고 순차적으로 실행
# =============================================================================

set -e

cd /home/ofuser/workspaces/ijswork/gpubase-raphrag-new/test_0130
source /home/ofuser/workspaces/ijswork/gpubase-raphrag-new/scripts/trainning/qlora_training_20260124_093751/venv/bin/activate

export HF_HUB_OFFLINE=1
export PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True

echo "=============================================="
echo "전체 학습 큐 v2 시작"
echo "시작 시간: $(date)"
echo "=============================================="

# 한국어 학습 완료 대기 (로그 파일 기반)
wait_for_ko_completion() {
    echo "[대기] 한국어 학습 완료 대기 중..."

    while true; do
        # 프로세스 확인 (combined_ko.jsonl을 사용하는 python 프로세스)
        if pgrep -f "combined_ko.jsonl" > /dev/null 2>&1; then
            # 로그에서 진행률 확인
            PROGRESS=$(tail -100 training_ko.log 2>/dev/null | grep -oP '\d+%' | tail -1 || echo "0%")
            echo "  $(date): 한국어 학습 진행 중... ($PROGRESS)"
            sleep 120  # 2분마다 체크
        else
            # 학습 완료 또는 에러 확인
            if grep -q "Training completed" training_ko.log 2>/dev/null; then
                echo "[완료] 한국어 학습 성공적으로 완료됨"
                return 0
            elif tail -50 training_ko.log 2>/dev/null | grep -q "Error\|Exception\|failed"; then
                echo "[에러] 한국어 학습 중 에러 발생"
                return 1
            else
                echo "[완료] 한국어 학습 프로세스 종료됨"
                return 0
            fi
        fi
    done
}

# 한국어 학습 완료 대기
wait_for_ko_completion
KO_STATUS=$?

if [ $KO_STATUS -ne 0 ]; then
    echo "[경고] 한국어 학습에 문제가 있을 수 있습니다. 계속 진행합니다."
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

# 검증
python validate_all_adapters.py 2>/dev/null || echo "검증 스크립트 실행 실패"

echo ""
echo "다음 단계: python update_docker_compose.py --preview"
