#!/bin/bash
#
# GraphRAG Services Start Script
# Starts all Docker containers for the GraphRAG system
#

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

echo "============================================================"
echo "  GraphRAG Services - Starting"
echo "============================================================"

# Create data directories if they don't exist
echo ""
echo "[1/4] Creating data directories..."
mkdir -p ../neo4j/data ../neo4j/logs ../neo4j/plugins
mkdir -p ../data/nim_llm_cache ../data/nim_embed_cache ../data/huggingface_cache
echo "  Done."

# Check if .env file exists
if [ ! -f .env ]; then
    echo ""
    echo "[WARNING] .env file not found. Please create it with NGC_API_KEY."
    exit 1
fi

# Start services (using docker compose v2)
echo ""
echo "[2/4] Starting Docker services..."
docker compose up -d

# Wait for services to be healthy
echo ""
echo "[3/4] Waiting for services to be healthy..."
echo "  (This may take 2-5 minutes for GPU models to load)"
echo ""

# Check each service
check_service() {
    local container="$1"
    local port="$2"
    local name="$3"

    printf "  %-20s: " "$name"

    # Wait up to 5 minutes for container to be healthy
    max_wait=300
    waited=0
    while [ $waited -lt $max_wait ]; do
        status=$(docker inspect --format='{{.State.Health.Status}}' "$container" 2>/dev/null || echo "starting")

        if [ "$status" = "healthy" ]; then
            echo "OK (port $port)"
            return 0
        elif [ "$status" = "unhealthy" ]; then
            echo "UNHEALTHY"
            return 1
        fi

        sleep 5
        waited=$((waited + 5))
        printf "."
    done

    echo "TIMEOUT"
    return 1
}

check_service "neo4j-graphrag" "7474" "Neo4j"
check_service "nemotron-graphrag" "12800" "Nemotron LLM"
check_service "docker-nemo-embedding-1" "12801" "NeMo Embedding"
check_service "docker-mistral-nemo-coder-1" "12802" "Mistral Coder"

# Show final status
echo ""
echo "[4/4] Service Status:"
echo "------------------------------------------------------------"
docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}" | grep -E "(NAMES|graphrag|nemo|mistral)"

echo ""
echo "============================================================"
echo "  GraphRAG Services Started"
echo ""
echo "  Endpoints:"
echo "    Neo4j Browser:    http://localhost:7474"
echo "    Nemotron LLM:     http://localhost:12800"
echo "    NeMo Embedding:   http://localhost:12801"
echo "    Mistral Coder:    http://localhost:12802"
echo ""
echo "  Data Persistence:"
echo "    Neo4j:            ../neo4j/data"
echo "    LLM Cache:        ../data/nim_llm_cache"
echo "    Embedding Cache:  ../data/nim_embed_cache"
echo "    HuggingFace:      ../data/huggingface_cache"
echo "============================================================"
