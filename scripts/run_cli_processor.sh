#!/bin/bash
# ============================================================================
# KMS CLI Document Processor - GPU Server Execution Script
# ============================================================================
#
# Usage:
#   ./run_cli_processor.sh <input_file_or_dir> [options]
#
# Examples:
#   ./run_cli_processor.sh /data/manuals/OpenFrame_TJES.pdf -l ko
#   ./run_cli_processor.sh /data/manuals/ -l ja --enable-vlm
#   ./run_cli_processor.sh /data/manuals/Base_Guide.pdf -l en --enable-vlm --save-db
#
# ============================================================================

set -e

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROCESSOR_SCRIPT="${SCRIPT_DIR}/cli_document_processor.py"

# GPU Server API Endpoints
export EMBEDDING_URL="${EMBEDDING_URL:-http://192.168.8.11:12801/v1}"
export VISION_URL="${VISION_URL:-http://192.168.8.11:12803/v1}"

# Database credentials (set these in environment or here)
# export POSTGRES_PASSWORD="your_password"
# export NEO4J_PASSWORD="your_password"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

print_banner() {
    echo -e "${BLUE}"
    echo "╔══════════════════════════════════════════════════════════════╗"
    echo "║           KMS Document Processor - GPU Server                ║"
    echo "╠══════════════════════════════════════════════════════════════╣"
    echo "║  Embedding Model : nvidia/nv-embedqa-mistral-7b-v2 (12801)   ║"
    echo "║  Vision Model    : Qwen/Qwen2-VL-2B-Instruct (12803)         ║"
    echo "╚══════════════════════════════════════════════════════════════╝"
    echo -e "${NC}"
}

check_dependencies() {
    echo -e "${YELLOW}Checking dependencies...${NC}"

    # Check Python
    if ! command -v python3 &> /dev/null; then
        echo -e "${RED}Error: Python 3 not found${NC}"
        exit 1
    fi

    # Check required Python packages
    python3 -c "import aiohttp" 2>/dev/null || {
        echo -e "${YELLOW}Installing aiohttp...${NC}"
        pip3 install aiohttp
    }

    python3 -c "import fitz" 2>/dev/null || python3 -c "import pypdf" 2>/dev/null || {
        echo -e "${YELLOW}Installing PDF libraries...${NC}"
        pip3 install PyMuPDF pypdf
    }

    echo -e "${GREEN}✓ Dependencies OK${NC}"
}

check_services() {
    echo -e "${YELLOW}Checking GPU services...${NC}"

    # Check Embedding API
    if curl -s --connect-timeout 5 "${EMBEDDING_URL}/models" > /dev/null 2>&1; then
        echo -e "${GREEN}✓ Embedding API (${EMBEDDING_URL}) - OK${NC}"
    else
        echo -e "${RED}✗ Embedding API (${EMBEDDING_URL}) - UNREACHABLE${NC}"
        echo -e "${YELLOW}  Make sure nemo-embedding-graphrag container is running${NC}"
        exit 1
    fi

    # Check Vision API (optional)
    if curl -s --connect-timeout 5 "${VISION_URL}/models" > /dev/null 2>&1; then
        echo -e "${GREEN}✓ Vision API (${VISION_URL}) - OK${NC}"
    else
        echo -e "${YELLOW}⚠ Vision API (${VISION_URL}) - UNREACHABLE (VLM disabled)${NC}"
    fi
}

show_help() {
    echo "Usage: $0 <input_file_or_dir> [options]"
    echo ""
    echo "Arguments:"
    echo "  input              Input file (.pdf, .txt, .md) or directory"
    echo ""
    echo "Options:"
    echo "  -l, --language     Document language: ko, ja, en (default: ko)"
    echo "  -t, --tags         Comma-separated tags (default: manual)"
    echo "  --enable-vlm       Enable VLM analysis for images/charts/tables"
    echo "  --save-db          Save results to PostgreSQL and Neo4j"
    echo "  -o, --output       Output directory for results JSON"
    echo "  --chunk-size       Chunk size in characters (default: 1000)"
    echo "  --chunk-overlap    Chunk overlap in characters (default: 200)"
    echo "  --batch-size       Embedding batch size (default: 32)"
    echo "  -v, --verbose      Enable verbose logging"
    echo "  -h, --help         Show this help message"
    echo ""
    echo "Examples:"
    echo "  # Process single PDF in Korean"
    echo "  $0 /data/manual.pdf -l ko"
    echo ""
    echo "  # Process directory with VLM enabled"
    echo "  $0 /data/manuals/ -l ja --enable-vlm"
    echo ""
    echo "  # Full processing with database save"
    echo "  $0 /data/file.pdf -l en --enable-vlm --save-db"
    echo ""
    echo "Environment Variables:"
    echo "  EMBEDDING_URL      Embedding API URL (default: http://192.168.8.11:12801/v1)"
    echo "  VISION_URL         Vision API URL (default: http://192.168.8.11:12803/v1)"
    echo "  POSTGRES_PASSWORD  PostgreSQL password (for --save-db)"
    echo "  NEO4J_PASSWORD     Neo4j password (for --save-db)"
}

# Main
main() {
    # Check for help flag
    if [[ "$1" == "-h" ]] || [[ "$1" == "--help" ]] || [[ -z "$1" ]]; then
        show_help
        exit 0
    fi

    print_banner
    check_dependencies
    check_services

    echo ""
    echo -e "${BLUE}Starting document processing...${NC}"
    echo ""

    # Run the processor
    python3 "${PROCESSOR_SCRIPT}" "$@"

    exit_code=$?

    if [ $exit_code -eq 0 ]; then
        echo ""
        echo -e "${GREEN}✓ Processing completed successfully${NC}"
    else
        echo ""
        echo -e "${RED}✗ Processing completed with errors${NC}"
    fi

    exit $exit_code
}

main "$@"
