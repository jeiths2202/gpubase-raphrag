#!/bin/bash
# ============================================
# vLLM 서버 시작 - Merged CPT 72B Model
# GPU 4,5,6,7 전용 (tensor-parallel-size=4)
# ============================================
set -eo pipefail

CONTAINER_NAME="vllm-chat-cpt"
PORT=8800
IMAGE="vllm/vllm-openai:v0.15.0"

# Merged 모델 경로
MERGED_MODEL="/raid/users/ofuser/qlora/outputs/merged_cpt_72b"
HF_CACHE="/raid/users/ofuser/.cache/huggingface"

echo "============================================"
echo " vLLM Chat Server (Qwen2.5-72B + CPT Merged)"
echo " GPU: 4,5,6,7 | Port: ${PORT}"
echo "============================================"

# Merged 모델 존재 확인
if [ ! -f "${MERGED_MODEL}/config.json" ]; then
    echo "ERROR: Merged model not found: ${MERGED_MODEL}"
    echo "먼저 merge를 실행하세요:"
    echo "  python3 scripts/chat_service/merge_adapter.py"
    exit 1
fi

# 기존 컨테이너 정리
if docker ps -a --format '{{.Names}}' | grep -q "^${CONTAINER_NAME}$"; then
    echo "기존 컨테이너 정리 중..."
    docker rm -f "${CONTAINER_NAME}" 2>/dev/null
fi

echo "Starting vLLM server..."

docker run -d \
    --name "${CONTAINER_NAME}" \
    --runtime nvidia \
    -e NVIDIA_VISIBLE_DEVICES=4,5,6,7 \
    -e HF_HOME=/root/.cache/huggingface \
    -p "${PORT}:8000" \
    -v "${MERGED_MODEL}:/opt/model" \
    -v "${HF_CACHE}:/root/.cache/huggingface" \
    --shm-size 16g \
    "${IMAGE}" \
    --model /opt/model \
    --served-model-name openframe-cpt-72b \
    --tensor-parallel-size 4 \
    --max-model-len 2048 \
    --max-num-seqs 16 \
    --gpu-memory-utilization 0.95 \
    --dtype bfloat16 \
    --trust-remote-code \
    --enforce-eager \
    --port 8000

echo ""
echo "컨테이너 시작됨: ${CONTAINER_NAME}"
echo "모델 로딩 중... (약 2-3분 소요)"
echo ""
echo "상태 확인:  docker logs -f ${CONTAINER_NAME}"
echo "헬스 체크:  curl http://localhost:${PORT}/health"
echo "모델 확인:  curl http://localhost:${PORT}/v1/models"
echo "채팅 시작:  python3 scripts/chat_service/chat.py"
echo "서버 중지:  docker rm -f ${CONTAINER_NAME}"
