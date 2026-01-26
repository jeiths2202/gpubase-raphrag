#!/bin/bash
#
# Smarter RAG E2E Test Runner
# Usage: ./run_smarter_rag_tests.sh [options]
#
# Options:
#   --url URL       API base URL (default: http://localhost:9000)
#   --username USER Admin username (default: admin)
#   --password PASS Admin password
#   --help          Show this help message
#

set -e

# Default values
API_URL="http://localhost:9000"
USERNAME="admin"
PASSWORD=""

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --url)
            API_URL="$2"
            shift 2
            ;;
        --username)
            USERNAME="$2"
            shift 2
            ;;
        --password)
            PASSWORD="$2"
            shift 2
            ;;
        --help)
            head -15 "$0" | tail -13
            exit 0
            ;;
        *)
            echo "Unknown option: $1"
            exit 1
            ;;
    esac
done

# Get password from .env if not provided
if [ -z "$PASSWORD" ]; then
    if [ -f /opt/kms/.env ]; then
        PASSWORD=$(grep ADMIN_INITIAL_PASSWORD /opt/kms/.env | cut -d'=' -f2 | tr -d '"')
    fi
fi

if [ -z "$PASSWORD" ]; then
    echo "Error: Admin password required. Use --password or set ADMIN_INITIAL_PASSWORD in .env"
    exit 1
fi

echo "========================================"
echo "Smarter RAG E2E Test Suite"
echo "========================================"
echo "API URL: $API_URL"
echo "Username: $USERNAME"
echo ""

# Run the Python test suite
cd /opt/kms
python3 scripts/testing/test_smarter_rag_e2e.py \
    --url "$API_URL" \
    --username "$USERNAME" \
    --password "$PASSWORD"

exit_code=$?

echo ""
if [ $exit_code -eq 0 ]; then
    echo "✅ All tests passed!"
else
    echo "❌ Some tests failed!"
fi

exit $exit_code
