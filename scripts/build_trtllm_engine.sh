#!/bin/bash
#
# TensorRT-LLM 엔진 빌드 스크립트
# 병합된 QLoRA 모델을 TensorRT-LLM 최적화 엔진으로 변환
#
# Prerequisites:
#   - NVIDIA TensorRT-LLM Docker image
#   - Merged model from merge_lora_adapters.py
#
# Usage:
#   ./build_trtllm_engine.sh tibero7
#   ./build_trtllm_engine.sh all

set -e

# 설정
MERGED_MODELS_DIR="/raid/users/ofuser/qlora/merged_models"
TRTLLM_ENGINES_DIR="/raid/users/ofuser/qlora/trtllm_engines"
TRTLLM_IMAGE="nvcr.io/nvidia/tritonserver:24.08-trtllm-python-py3"
GPU_ID=5

# 사용 가능한 모델 목록
MODELS=(
    "openframe_mvs"
    "msp_openframe"
    "vos3_openframe"
    "xsp_openframe"
    "tibero7"
    "tmax"
    "ofcobol"
    "ofasm"
)

usage() {
    echo "Usage: $0 <model_name|all|list>"
    echo ""
    echo "Options:"
    echo "  <model_name>  Build TRT-LLM engine for specific model"
    echo "  all           Build engines for all models"
    echo "  list          List available models"
    echo ""
    echo "Available models:"
    for m in "${MODELS[@]}"; do
        echo "  - $m"
    done
}

check_prerequisites() {
    echo "=== Checking prerequisites ==="

    # Docker 확인
    if ! command -v docker &> /dev/null; then
        echo "❌ Docker not found"
        exit 1
    fi

    # TRT-LLM 이미지 확인
    if ! docker images | grep -q "tritonserver.*trtllm"; then
        echo "⚠️  TensorRT-LLM image not found. Pulling..."
        docker pull $TRTLLM_IMAGE
    fi

    # 출력 디렉토리 생성
    mkdir -p "$TRTLLM_ENGINES_DIR"

    echo "✅ Prerequisites OK"
}

build_engine() {
    local model_name=$1
    local model_path="$MERGED_MODELS_DIR/qwen2.5-7b-$model_name"
    local output_path="$TRTLLM_ENGINES_DIR/$model_name"
    local checkpoint_path="$TRTLLM_ENGINES_DIR/checkpoints/$model_name"

    echo ""
    echo "============================================================"
    echo "Building TRT-LLM engine: $model_name"
    echo "============================================================"
    echo "Model path: $model_path"
    echo "Output: $output_path"
    echo "GPU: $GPU_ID"

    # 모델 존재 확인
    if [ ! -d "$model_path" ]; then
        echo "❌ Model not found: $model_path"
        echo "   Run merge_lora_adapters.py first"
        return 1
    fi

    # 체크포인트 디렉토리 생성
    mkdir -p "$checkpoint_path"
    mkdir -p "$output_path"

    # 1. HuggingFace to TRT-LLM checkpoint 변환
    echo ""
    echo "Step 1: Converting HuggingFace model to TRT-LLM checkpoint..."

    docker run --rm --gpus "device=$GPU_ID" \
        -v "$model_path:/model" \
        -v "$checkpoint_path:/checkpoint" \
        -v "$MERGED_MODELS_DIR:/merged_models" \
        $TRTLLM_IMAGE \
        python3 /opt/tensorrt_llm/examples/qwen/convert_checkpoint.py \
            --model_dir /model \
            --output_dir /checkpoint \
            --dtype float16 \
            --tp_size 1 \
            --pp_size 1

    # 2. TRT-LLM 엔진 빌드
    echo ""
    echo "Step 2: Building TRT-LLM engine..."

    docker run --rm --gpus "device=$GPU_ID" \
        -v "$checkpoint_path:/checkpoint" \
        -v "$output_path:/engine" \
        $TRTLLM_IMAGE \
        trtllm-build \
            --checkpoint_dir /checkpoint \
            --output_dir /engine \
            --gemm_plugin float16 \
            --max_batch_size 8 \
            --max_input_len 4096 \
            --max_seq_len 8192 \
            --paged_kv_cache enable \
            --remove_input_padding enable \
            --use_fused_mlp enable \
            --workers 1

    # 결과 확인
    if [ -f "$output_path/rank0.engine" ] || [ -f "$output_path/config.json" ]; then
        echo ""
        echo "✅ Successfully built engine: $model_name"
        ls -lh "$output_path"
    else
        echo ""
        echo "❌ Engine build failed: $model_name"
        return 1
    fi
}

# 메인 로직
case "${1:-}" in
    "")
        usage
        ;;
    "list")
        echo "Available models:"
        for m in "${MODELS[@]}"; do
            merged="$MERGED_MODELS_DIR/qwen2.5-7b-$m"
            engine="$TRTLLM_ENGINES_DIR/$m"

            merged_status="❌"
            engine_status="❌"

            [ -d "$merged" ] && merged_status="✅"
            [ -d "$engine" ] && engine_status="✅"

            echo "  $m: merged=$merged_status engine=$engine_status"
        done
        ;;
    "all")
        check_prerequisites

        echo ""
        echo "Building engines for all models..."

        results=()
        for m in "${MODELS[@]}"; do
            if build_engine "$m"; then
                results+=("✅ $m")
            else
                results+=("❌ $m")
            fi
        done

        echo ""
        echo "============================================================"
        echo "Summary"
        echo "============================================================"
        for r in "${results[@]}"; do
            echo "  $r"
        done
        ;;
    *)
        check_prerequisites
        build_engine "$1"
        ;;
esac
