#!/bin/bash
#
# Multi-LoRA LLM 서비스 관리 스크립트
#
# Usage:
#   ./manage_multi_lora.sh start    # 서비스 시작
#   ./manage_multi_lora.sh stop     # 서비스 중지
#   ./manage_multi_lora.sh restart  # 서비스 재시작
#   ./manage_multi_lora.sh status   # 상태 확인
#   ./manage_multi_lora.sh logs     # 로그 확인
#   ./manage_multi_lora.sh test     # API 테스트

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
COMPOSE_FILE="$SCRIPT_DIR/../docker/docker-compose-multi-lora.yml"
CONTAINER_NAME="multi-lora-llm"
PORT=12810

check_compose_file() {
    if [ ! -f "$COMPOSE_FILE" ]; then
        echo "❌ Compose file not found: $COMPOSE_FILE"
        exit 1
    fi
}

start_service() {
    check_compose_file
    echo "=== Starting Multi-LoRA LLM Service ==="

    # 기존 PEFT 서버 중지 (포트 충돌 방지)
    echo "Stopping existing services on port $PORT..."
    pkill -f "lora_api_server.py" 2>/dev/null || true
    fuser -k ${PORT}/tcp 2>/dev/null || true
    sleep 2

    # Docker 네트워크 확인/생성
    docker network inspect graphrag_network >/dev/null 2>&1 || \
        docker network create graphrag_network

    # 서비스 시작
    echo "Starting Docker container..."
    docker-compose -f "$COMPOSE_FILE" up -d

    echo ""
    echo "Waiting for service to be ready (may take 2-3 minutes)..."

    # 헬스체크 대기
    for i in {1..60}; do
        if curl -s http://localhost:$PORT/health >/dev/null 2>&1; then
            echo ""
            echo "✅ Service is ready!"
            show_status
            return 0
        fi
        echo -n "."
        sleep 5
    done

    echo ""
    echo "⚠️  Service not ready yet. Check logs with: $0 logs"
}

stop_service() {
    check_compose_file
    echo "=== Stopping Multi-LoRA LLM Service ==="
    docker-compose -f "$COMPOSE_FILE" down
    echo "✅ Service stopped"
}

restart_service() {
    stop_service
    sleep 2
    start_service
}

show_status() {
    echo ""
    echo "=== Service Status ==="

    # 컨테이너 상태
    docker ps --filter "name=$CONTAINER_NAME" --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"

    # API 상태
    echo ""
    if curl -s http://localhost:$PORT/health >/dev/null 2>&1; then
        echo "API: ✅ Running at http://localhost:$PORT"

        # 모델 정보
        echo ""
        echo "Loaded Models:"
        curl -s http://localhost:$PORT/v1/models 2>/dev/null | python3 -c "
import sys, json
try:
    data = json.load(sys.stdin)
    for model in data.get('data', []):
        print(f\"  - {model.get('id', 'unknown')}\")
except:
    print('  (Could not parse model info)')
" 2>/dev/null || echo "  (Models loading...)"
    else
        echo "API: ❌ Not responding"
    fi

    # GPU 사용량
    echo ""
    echo "GPU Memory (GPU 5):"
    nvidia-smi --query-gpu=index,memory.used,memory.total,utilization.gpu --format=csv,noheader | grep "^5," || echo "  (Cannot get GPU info)"
}

show_logs() {
    check_compose_file
    docker-compose -f "$COMPOSE_FILE" logs -f --tail=100
}

test_api() {
    echo "=== Testing Multi-LoRA API ==="

    # Health check
    echo ""
    echo "1. Health Check:"
    curl -s http://localhost:$PORT/health | python3 -m json.tool 2>/dev/null || echo "❌ Failed"

    # 모델 목록
    echo ""
    echo "2. Available Models:"
    curl -s http://localhost:$PORT/v1/models | python3 -m json.tool 2>/dev/null || echo "❌ Failed"

    # 각 어댑터 테스트
    ADAPTERS=("tibero7" "tmax" "openframe_mvs")
    QUERIES=(
        "Tibero 데이터베이스의 주요 특징은?"
        "Tmax의 트랜잭션 처리 방식은?"
        "tjesmgr 명령어 사용법은?"
    )

    echo ""
    echo "3. Chat Tests:"
    for i in "${!ADAPTERS[@]}"; do
        adapter="${ADAPTERS[$i]}"
        query="${QUERIES[$i]}"

        echo ""
        echo "--- Testing: $adapter ---"
        echo "Query: $query"

        response=$(curl -s -X POST http://localhost:$PORT/v1/chat/completions \
            -H "Content-Type: application/json" \
            -d "{
                \"model\": \"$adapter\",
                \"messages\": [{\"role\": \"user\", \"content\": \"$query\"}],
                \"max_tokens\": 200,
                \"temperature\": 0.7
            }" 2>/dev/null)

        if [ -n "$response" ]; then
            echo "$response" | python3 -c "
import sys, json
try:
    data = json.load(sys.stdin)
    content = data['choices'][0]['message']['content']
    print(f'Response: {content[:200]}...' if len(content) > 200 else f'Response: {content}')
except Exception as e:
    print(f'Parse error: {e}')
    print(sys.stdin.read())
" 2>/dev/null
        else
            echo "❌ No response"
        fi
    done
}

# 메인 로직
case "${1:-status}" in
    start)
        start_service
        ;;
    stop)
        stop_service
        ;;
    restart)
        restart_service
        ;;
    status)
        show_status
        ;;
    logs)
        show_logs
        ;;
    test)
        test_api
        ;;
    *)
        echo "Usage: $0 {start|stop|restart|status|logs|test}"
        exit 1
        ;;
esac
