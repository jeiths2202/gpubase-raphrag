#!/bin/bash
#
# GraphRAG Services Status Script
# Shows status of all Docker containers
#

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "============================================================"
echo "  GraphRAG Services - Status"
echo "============================================================"

# Container status
echo ""
echo "Container Status:"
echo "------------------------------------------------------------"
docker ps -a --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}" | grep -E "(NAMES|graphrag|nemo|mistral)" || echo "  No GraphRAG containers found"

# Health check
echo ""
echo "Health Check:"
echo "------------------------------------------------------------"

check_health() {
    local name=$1
    local url=$2
    local container=$3

    printf "  %-20s: " "$name"

    # Check if container is running
    if ! docker ps --format '{{.Names}}' | grep -q "^${container}$"; then
        echo "STOPPED"
        return
    fi

    # Check health endpoint
    if curl -sf "$url" > /dev/null 2>&1; then
        echo "OK"
    else
        echo "UNHEALTHY"
    fi
}

check_health "Neo4j" "http://localhost:7474" "neo4j-graphrag"
check_health "Nemotron LLM" "http://localhost:12800/v1/health/ready" "nemotron-graphrag"
check_health "NeMo Embedding" "http://localhost:12801/v1/health/ready" "docker-nemo-embedding-1"
check_health "Mistral Coder" "http://localhost:12802/health" "docker-mistral-nemo-coder-1"

# GPU usage
echo ""
echo "GPU Usage:"
echo "------------------------------------------------------------"
nvidia-smi --query-gpu=index,name,memory.used,memory.total,utilization.gpu --format=csv,noheader,nounits | \
while IFS=',' read -r idx name mem_used mem_total util; do
    printf "  GPU %s: %5s/%5s MB (%3s%%) - %s\n" "$idx" "$mem_used" "$mem_total" "$util" "$name"
done

# Disk usage
echo ""
echo "Data Directory Sizes:"
echo "------------------------------------------------------------"
du -sh ../neo4j/data 2>/dev/null | awk '{printf "  Neo4j Data:         %s\n", $1}' || echo "  Neo4j Data:         N/A"
du -sh ../data/nim_llm_cache 2>/dev/null | awk '{printf "  LLM Cache:          %s\n", $1}' || echo "  LLM Cache:          N/A"
du -sh ../data/nim_embed_cache 2>/dev/null | awk '{printf "  Embedding Cache:    %s\n", $1}' || echo "  Embedding Cache:    N/A"
du -sh ../data/huggingface_cache 2>/dev/null | awk '{printf "  HuggingFace Cache:  %s\n", $1}' || echo "  HuggingFace Cache:  N/A"

echo ""
echo "============================================================"
