#!/bin/bash
# ─────────────────────────────────────────────────────────
# v11 Merged Model 서빙 스크립트
#
# 기존 vLLM 컨테이너를 중지하고, v11 merged model로 교체 서빙합니다.
# 머지된 모델이 없으면 자동으로 머지를 먼저 수행합니다.
#
# Usage:
#   ./serve_v11.sh cpt             # CPT만 적용
#   ./serve_v11.sh cpt-sft         # CPT+SFT 적용
#   ./serve_v11.sh cpt-sft-dpo     # CPT+SFT+DPO 전체 적용
#   ./serve_v11.sh base            # 원본 Base 모델로 복원
#
# GPU: 4,5 (TP=2), Port: 12810
# ─────────────────────────────────────────────────────────
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"

CONTAINER_NAME="vllm_qwen3_32b"
VLLM_IMAGE="vllm/vllm-openai:latest"
SERVE_PORT=12810
SERVE_GPUS="4,5"
TP_SIZE=2

BASE_MODEL_DIR="/raid/users/ofuser/models/Qwen3-32B"
MODELS_DIR="/raid/users/ofuser/models"

# 환경 변수 (머지 시 루트 디스크 사용 방지)
export HF_HOME="/raid/users/ofuser/.cache/huggingface"
export TRANSFORMERS_CACHE="/raid/users/ofuser/.cache/huggingface/hub"
export HF_DATASETS_CACHE="/raid/users/ofuser/.cache/huggingface/datasets"
export TMPDIR="/raid/users/ofuser/tmp"

# ── 사용법 ───────────────────────────────────────────────
usage() {
    echo "Usage: $0 <variant>"
    echo ""
    echo "Variants:"
    echo "  base           원본 Qwen3-32B (adapter 없음)"
    echo "  cpt            Base + CPT adapter merged"
    echo "  cpt-sft        Base + CPT + SFT adapters merged"
    echo "  cpt-sft-dpo    Base + CPT + SFT + DPO adapters merged"
    echo ""
    echo "Options:"
    echo "  --force-merge  기존 merged model 덮어쓰기"
    echo "  --merge-gpus   머지에 사용할 GPU (기본: 4,5)"
    exit 1
}

VARIANT="${1:-}"
FORCE_MERGE=false
MERGE_GPUS="4,5"

# 인자 파싱
shift || true
while [[ $# -gt 0 ]]; do
    case "$1" in
        --force-merge) FORCE_MERGE=true ;;
        --merge-gpus) MERGE_GPUS="$2"; shift ;;
        *) echo "Unknown option: $1"; usage ;;
    esac
    shift
done

if [[ -z "$VARIANT" ]]; then
    usage
fi

# variant별 모델 경로 결정
case "$VARIANT" in
    base)
        MODEL_DIR="$BASE_MODEL_DIR"
        ;;
    cpt|cpt-sft|cpt-sft-dpo)
        MODEL_DIR="$MODELS_DIR/Qwen3-32B-v11-${VARIANT}"
        ;;
    *)
        echo "❌ Unknown variant: $VARIANT"
        usage
        ;;
esac

echo "═══════════════════════════════════════════════════════════"
echo "  Qwen3-32B v11 서빙: ${VARIANT}"
echo "  Model:  $MODEL_DIR"
echo "  GPU:    $SERVE_GPUS (TP=$TP_SIZE)"
echo "  Port:   $SERVE_PORT"
echo "═══════════════════════════════════════════════════════════"

# ── Step 1: Merged model 존재 확인 / 머지 실행 ─────────────
if [[ "$VARIANT" != "base" ]]; then
    if [[ ! -f "$MODEL_DIR/config.json" ]] || [[ "$FORCE_MERGE" == "true" ]]; then
        echo ""
        echo "── Step 1: Adapter 머지 실행 ──"
        echo "  Variant: $VARIANT"
        echo "  Merge GPU: $MERGE_GPUS"

        # 기존 vLLM 중지하여 GPU 메모리 확보
        if docker ps --format '{{.Names}}' | grep -q "^${CONTAINER_NAME}$"; then
            echo "  기존 vLLM 컨테이너 중지 (GPU 메모리 확보)..."
            docker stop "$CONTAINER_NAME" && docker rm "$CONTAINER_NAME" 2>/dev/null || true
            echo "  ✅ 컨테이너 중지 완료"
            sleep 5
        fi

        FORCE_FLAG=""
        if [[ "$FORCE_MERGE" == "true" ]]; then
            FORCE_FLAG="--force"
        fi

        echo "  머지 시작..."
        CUDA_VISIBLE_DEVICES="$MERGE_GPUS" python "$SCRIPT_DIR/merge_adapters.py" \
            --variant "$VARIANT" $FORCE_FLAG

        if [[ ! -f "$MODEL_DIR/config.json" ]]; then
            echo "❌ 머지 실패: $MODEL_DIR/config.json 미발견"
            exit 1
        fi
        echo "  ✅ 머지 완료: $MODEL_DIR"
    else
        echo ""
        echo "── Step 1: Merged model 확인 ──"
        echo "  ✅ 이미 존재: $MODEL_DIR"
    fi
else
    echo ""
    echo "── Step 1: Base model 사용 ──"
    echo "  ✅ $MODEL_DIR"
fi

# ── Step 2: 기존 컨테이너 중지 ─────────────────────────────
echo ""
echo "── Step 2: 기존 vLLM 컨테이너 정리 ──"
if docker ps -a --format '{{.Names}}' | grep -q "^${CONTAINER_NAME}$"; then
    docker stop "$CONTAINER_NAME" 2>/dev/null || true
    docker rm "$CONTAINER_NAME" 2>/dev/null || true
    echo "  ✅ 기존 컨테이너 제거 완료"
    sleep 3
else
    echo "  (기존 컨테이너 없음)"
fi

# ── Step 3: 새 컨테이너 시작 ───────────────────────────────
echo ""
echo "── Step 3: vLLM 컨테이너 시작 ──"
echo "  Image:  $VLLM_IMAGE"
echo "  Model:  $MODEL_DIR → /opt/models/qwen3-32b"
echo "  GPU:    $SERVE_GPUS (TP=$TP_SIZE)"

docker run -d \
    --name "$CONTAINER_NAME" \
    --runtime nvidia \
    --restart unless-stopped \
    -p "${SERVE_PORT}:8000" \
    -e "NVIDIA_VISIBLE_DEVICES=${SERVE_GPUS}" \
    -e "VLLM_LOGGING_LEVEL=INFO" \
    --shm-size 16gb \
    -v "${MODEL_DIR}:/opt/models/qwen3-32b:ro" \
    "$VLLM_IMAGE" \
    --model /opt/models/qwen3-32b \
    --tensor-parallel-size "$TP_SIZE" \
    --max-model-len 8192 \
    --gpu-memory-utilization 0.90 \
    --dtype bfloat16 \
    --trust-remote-code \
    --enable-auto-tool-choice \
    --tool-call-parser hermes

echo "  ✅ 컨테이너 시작됨"

# ── Step 4: 헬스체크 대기 ──────────────────────────────────
echo ""
echo "── Step 4: 헬스체크 대기 (최대 10분) ──"
MAX_WAIT=120  # 5초 * 120 = 600초 = 10분
for i in $(seq 1 $MAX_WAIT); do
    HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" "http://localhost:${SERVE_PORT}/health" 2>/dev/null || echo "000")
    if [[ "$HTTP_CODE" == "200" ]]; then
        echo "  ✅ 서버 정상 기동 (${i}회 체크, $((i*5))초 소요)"
        break
    fi
    if (( i % 12 == 0 )); then
        echo "  [$((i*5/60))분 경과] HTTP $HTTP_CODE - 대기 중..."
    fi
    sleep 5
done

# 최종 확인
HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" "http://localhost:${SERVE_PORT}/health" 2>/dev/null || echo "000")
if [[ "$HTTP_CODE" != "200" ]]; then
    echo "  ⚠️  헬스체크 타임아웃 (HTTP $HTTP_CODE)"
    echo "     로그 확인: docker logs $CONTAINER_NAME --tail 30"
    exit 1
fi

# ── 결과 출력 ──────────────────────────────────────────────
echo ""
echo "═══════════════════════════════════════════════════════════"
echo "  ✅ Qwen3-32B v11 서빙 완료"
echo ""
echo "  Variant:   $VARIANT"
echo "  Model:     $MODEL_DIR"
echo "  Endpoint:  http://localhost:${SERVE_PORT}"
echo "  GPU:       $SERVE_GPUS (TP=$TP_SIZE)"
echo ""
echo "  테스트:"
echo "    curl http://localhost:${SERVE_PORT}/v1/models"
echo "    curl http://localhost:${SERVE_PORT}/health"
echo ""
echo "  다른 variant로 전환:"
echo "    ./serve_v11.sh base          # 원본"
echo "    ./serve_v11.sh cpt           # CPT only"
echo "    ./serve_v11.sh cpt-sft       # CPT+SFT"
echo "    ./serve_v11.sh cpt-sft-dpo   # CPT+SFT+DPO"
echo "═══════════════════════════════════════════════════════════"

# GPU 상태 출력
echo ""
echo "  GPU 상태:"
nvidia-smi --query-gpu=index,memory.used,memory.total --format=csv,noheader -i ${SERVE_GPUS//,/ -i }
