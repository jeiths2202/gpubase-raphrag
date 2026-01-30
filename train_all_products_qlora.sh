#!/bin/bash
# =============================================================================
# 7개 제품별 QLoRA 학습 스크립트
# =============================================================================
# 각 제품에 대해 별도의 QLoRA 어댑터를 생성합니다.
# 현재 OpenFrame MVS 학습이 완료된 후 실행됩니다.
#
# 제품 목록:
#   1. msp_openframe - MSP OpenFrame 7.3
#   2. vos3_openframe - VOS3 OpenFrame 2.0
#   3. tibero7 - Tibero 7
#   4. ofasm - OpenFrame ASM 4
#   5. ofcobol - OpenFrame COBOL 4
#   6. xsp_openframe - XSP OpenFrame 7.3
#   7. tmax - Tmax 6.0
# =============================================================================

set -e

cd /home/ofuser/workspaces/ijswork/gpubase-raphrag-new/test_0130
source /home/ofuser/workspaces/ijswork/gpubase-raphrag-new/scripts/trainning/qlora_training_20260124_093751/venv/bin/activate

export HF_HUB_OFFLINE=1
export PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True

TIMESTAMP=$(date +%Y%m%d_%H%M%S)
LOG_DIR="./training_logs_${TIMESTAMP}"
mkdir -p "$LOG_DIR"
mkdir -p "./qlora_adapters"

echo "=============================================="
echo "7개 제품 QLoRA 학습 시작"
echo "시작 시간: $(date)"
echo "로그 디렉토리: $LOG_DIR"
echo "=============================================="

# 제품 목록 정의
PRODUCTS=("msp_openframe" "vos3_openframe" "tibero7" "ofasm" "ofcobol" "xsp_openframe" "tmax")
PRODUCT_NAMES=("MSP OpenFrame 7.3" "VOS3 OpenFrame 2.0" "Tibero 7" "OpenFrame ASM 4" "OpenFrame COBOL 4" "XSP OpenFrame 7.3" "Tmax 6.0")

# Step 1: 학습 데이터 생성
echo ""
echo "[Step 1] 모든 제품의 학습 데이터 생성 중..."
python generate_all_products_training_data.py --product all --languages ko,ja,en --output ./training_data_products 2>&1 | tee "$LOG_DIR/data_generation.log"

# Step 2: 각 제품별 학습 (순차 실행)
PRODUCT_COUNT=0
TOTAL_PRODUCTS=${#PRODUCTS[@]}

for i in "${!PRODUCTS[@]}"; do
    PRODUCT="${PRODUCTS[$i]}"
    PRODUCT_NAME="${PRODUCT_NAMES[$i]}"
    PRODUCT_COUNT=$((PRODUCT_COUNT + 1))

    echo ""
    echo "=============================================="
    echo "[$PRODUCT_COUNT/$TOTAL_PRODUCTS] $PRODUCT_NAME 학습 시작"
    echo "시작 시간: $(date)"
    echo "=============================================="

    # 각 언어별 학습 데이터 결합
    COMBINED_FILE="./training_data_products/${PRODUCT}_combined.jsonl"

    # 결합 파일 생성
    cat ./training_data_products/${PRODUCT}_ko.jsonl \
        ./training_data_products/${PRODUCT}_ja.jsonl \
        ./training_data_products/${PRODUCT}_en.jsonl \
        > "$COMBINED_FILE" 2>/dev/null || {
            echo "Warning: 일부 언어 파일이 없을 수 있습니다."
            touch "$COMBINED_FILE"
        }

    # 데이터 수 확인
    DATA_COUNT=$(wc -l < "$COMBINED_FILE" 2>/dev/null || echo "0")
    echo "학습 데이터 수: $DATA_COUNT"

    if [ "$DATA_COUNT" -lt 10 ]; then
        echo "Warning: $PRODUCT의 학습 데이터가 부족합니다. 스킵합니다."
        continue
    fi

    # QLoRA 학습 실행
    OUTPUT_DIR="./qlora_adapters/${PRODUCT}"
    mkdir -p "$OUTPUT_DIR"

    python train_openframe_qlora.py \
        --data "$COMBINED_FILE" \
        --gpu 5,6 \
        --epochs 3 \
        --batch_size 2 \
        --language ko \
        --output "$OUTPUT_DIR" 2>&1 | tee "$LOG_DIR/${PRODUCT}_training.log"

    echo "[$PRODUCT_COUNT/$TOTAL_PRODUCTS] $PRODUCT_NAME 학습 완료: $(date)"

    # 검증
    echo "검증 중..."
    if [ -d "$OUTPUT_DIR" ]; then
        ADAPTER_FILES=$(ls -la "$OUTPUT_DIR"/ 2>/dev/null | wc -l)
        echo "어댑터 파일 수: $ADAPTER_FILES"

        if [ "$ADAPTER_FILES" -gt 2 ]; then
            echo "✓ $PRODUCT 어댑터 생성 성공"
        else
            echo "✗ $PRODUCT 어댑터 생성 실패"
        fi
    fi
done

echo ""
echo "=============================================="
echo "모든 제품 학습 완료"
echo "완료 시간: $(date)"
echo "=============================================="

# 결과 요약
echo ""
echo "생성된 어댑터 목록:"
ls -la ./qlora_adapters/

echo ""
echo "=============================================="
echo "docker-compose.yml 어댑터 등록 설정 생성 중..."
echo "=============================================="

# 어댑터 등록 설정 생성
cat > "./qlora_adapters/lora_modules_config.txt" << 'EOF'
# vLLM --lora-modules 설정
# docker-compose.yml의 learning-llm 서비스에 추가하세요:
#
# --lora-modules openframe_mvs=/opt/qlora_adapters/openframe_mvs \
#                msp_openframe=/opt/qlora_adapters/msp_openframe \
#                vos3_openframe=/opt/qlora_adapters/vos3_openframe \
#                tibero7=/opt/qlora_adapters/tibero7 \
#                ofasm=/opt/qlora_adapters/ofasm \
#                ofcobol=/opt/qlora_adapters/ofcobol \
#                xsp_openframe=/opt/qlora_adapters/xsp_openframe \
#                tmax=/opt/qlora_adapters/tmax
EOF

echo "설정 파일 생성 완료: ./qlora_adapters/lora_modules_config.txt"
echo ""
echo "다음 단계:"
echo "1. docker-compose.yml에서 learning-llm 서비스의 volumes와 command 업데이트"
echo "2. 컨테이너 재시작: docker-compose restart learning-llm"
echo "3. API 호출 시 model 파라미터에 어댑터 이름 지정"
