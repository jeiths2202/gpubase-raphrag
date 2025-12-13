#!/bin/bash
#
# GraphRAG Services Stop Script
# Stops all Docker containers for the GraphRAG system
# Data is preserved in bind-mounted directories
#

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "============================================================"
echo "  GraphRAG Services - Stopping"
echo "============================================================"

# Show current status
echo ""
echo "[1/2] Current running containers:"
docker ps --format "table {{.Names}}\t{{.Status}}" | grep -E "(NAMES|graphrag|nemo|mistral)" || echo "  No GraphRAG containers running"

# Stop services
echo ""
echo "[2/2] Stopping Docker services..."
docker-compose down

echo ""
echo "============================================================"
echo "  GraphRAG Services Stopped"
echo ""
echo "  Data is preserved in:"
echo "    Neo4j:            ../neo4j/data"
echo "    LLM Cache:        ../data/nim_llm_cache"
echo "    Embedding Cache:  ../data/nim_embed_cache"
echo "    HuggingFace:      ../data/huggingface_cache"
echo ""
echo "  To restart: ./start-services.sh"
echo "============================================================"
