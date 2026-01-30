#!/bin/bash
# =============================================================================
# 전체 QLoRA 학습 파이프라인
# =============================================================================
# 1. OpenFrame MVS 7.1 (ko/ja/en) - 현재 진행 중
# 2. 7개 추가 제품 학습 (msp, vos3, tibero7, ofasm, ofcobol, xsp, tmax)
#
# 현재 학습이 완료된 후 이 스크립트를 실행하거나,
# 큐에 추가하여 자동으로 이어서 실행할 수 있습니다.
# =============================================================================

set -e

cd /home/ofuser/workspaces/ijswork/gpubase-raphrag-new/test_0130
source /home/ofuser/workspaces/ijswork/gpubase-raphrag-new/scripts/trainning/qlora_training_20260124_093751/venv/bin/activate

export HF_HUB_OFFLINE=1
export PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True

TIMESTAMP=$(date +%Y%m%d_%H%M%S)
LOG_FILE="training_products_${TIMESTAMP}.log"

echo "=============================================="
echo "7개 제품 QLoRA 학습 파이프라인 시작"
echo "시작 시간: $(date)"
echo "로그 파일: $LOG_FILE"
echo "=============================================="

# 제품 목록
PRODUCTS=("msp_openframe" "vos3_openframe" "tibero7" "ofasm" "ofcobol" "xsp_openframe" "tmax")
PRODUCT_NAMES=("MSP OpenFrame 7.3" "VOS3 OpenFrame 2.0" "Tibero 7" "OpenFrame ASM 4" "OpenFrame COBOL 4" "XSP OpenFrame 7.3" "Tmax 6.0")

TOTAL_PRODUCTS=${#PRODUCTS[@]}
COMPLETED=0
FAILED=0

# 어댑터 출력 디렉토리
mkdir -p ./qlora_adapters

for i in "${!PRODUCTS[@]}"; do
    PRODUCT="${PRODUCTS[$i]}"
    PRODUCT_NAME="${PRODUCT_NAMES[$i]}"
    PRODUCT_NUM=$((i + 1))

    echo ""
    echo "=============================================="
    echo "[$PRODUCT_NUM/$TOTAL_PRODUCTS] $PRODUCT_NAME 학습"
    echo "시작 시간: $(date)"
    echo "=============================================="

    # 학습 데이터 파일 결합 (ko + ja + en)
    DATA_DIR="./training_data_products"
    COMBINED_FILE="${DATA_DIR}/${PRODUCT}_combined.jsonl"

    # 기존 결합 파일 삭제 후 새로 생성
    rm -f "$COMBINED_FILE"

    # 각 언어별 파일 결합
    for LANG in ko ja en; do
        LANG_FILE="${DATA_DIR}/${PRODUCT}_${LANG}.jsonl"
        if [ -f "$LANG_FILE" ]; then
            cat "$LANG_FILE" >> "$COMBINED_FILE"
            echo "  추가: $LANG_FILE ($(wc -l < "$LANG_FILE") lines)"
        fi
    done

    # 데이터 수 확인
    if [ -f "$COMBINED_FILE" ]; then
        DATA_COUNT=$(wc -l < "$COMBINED_FILE")
    else
        DATA_COUNT=0
    fi

    echo "  총 학습 데이터: $DATA_COUNT"

    # 데이터가 충분하지 않으면 스킵
    if [ "$DATA_COUNT" -lt 50 ]; then
        echo "  ⚠ 데이터 부족 ($DATA_COUNT < 50). 스킵합니다."
        FAILED=$((FAILED + 1))
        continue
    fi

    # QLoRA 학습 실행
    OUTPUT_DIR="./qlora_adapters/${PRODUCT}"
    mkdir -p "$OUTPUT_DIR"

    echo "  학습 시작..."
    python train_openframe_qlora.py \
        --data "$COMBINED_FILE" \
        --gpu 5,6 \
        --epochs 3 \
        --batch_size 2 \
        --language ko \
        --output "$OUTPUT_DIR" 2>&1 | tee -a "$LOG_FILE"

    # 결과 확인
    ADAPTER_COUNT=$(find "$OUTPUT_DIR" -name "adapter_config.json" 2>/dev/null | wc -l)
    if [ "$ADAPTER_COUNT" -gt 0 ]; then
        echo "  ✓ $PRODUCT_NAME 학습 완료"
        COMPLETED=$((COMPLETED + 1))

        # 최신 어댑터 경로 출력
        LATEST_ADAPTER=$(ls -td "$OUTPUT_DIR"/*/ 2>/dev/null | head -1)
        echo "  어댑터 경로: $LATEST_ADAPTER"
    else
        echo "  ✗ $PRODUCT_NAME 학습 실패"
        FAILED=$((FAILED + 1))
    fi

    echo "[$PRODUCT_NUM/$TOTAL_PRODUCTS] 완료 시간: $(date)"
done

echo ""
echo "=============================================="
echo "학습 파이프라인 완료"
echo "완료 시간: $(date)"
echo "=============================================="
echo ""
echo "결과 요약:"
echo "  성공: $COMPLETED / $TOTAL_PRODUCTS"
echo "  실패: $FAILED / $TOTAL_PRODUCTS"
echo ""

# 어댑터 목록
echo "생성된 어댑터:"
for PRODUCT in "${PRODUCTS[@]}"; do
    ADAPTER_DIR="./qlora_adapters/${PRODUCT}"
    if [ -d "$ADAPTER_DIR" ]; then
        LATEST=$(ls -td "$ADAPTER_DIR"/*/ 2>/dev/null | head -1)
        if [ -n "$LATEST" ]; then
            echo "  $PRODUCT: $LATEST"
        fi
    fi
done

echo ""
echo "=============================================="
echo "docker-compose.yml 업데이트 안내"
echo "=============================================="
echo ""
echo "다음 명령을 실행하여 어댑터 등록 설정을 확인하세요:"
echo "  python update_docker_compose.py --preview"
echo ""
echo "컨테이너에 적용하려면:"
echo "  python update_docker_compose.py --apply"
echo "  cd /home/ofuser/workspaces/ijswork/gpubase-raphrag-new/docker"
echo "  docker-compose restart learning-llm"
