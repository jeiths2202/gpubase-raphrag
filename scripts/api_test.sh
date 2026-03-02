#!/bin/bash
# =============================================================================
# KMS API Test Script
# =============================================================================
# Usage:
#   ./scripts/api_test.sh "쿼리 내용"
#   ./scripts/api_test.sh "tjesmgr 기능" rag
#   ./scripts/api_test.sh "에러코드 -5212" rag
# =============================================================================

API_URL="${KMS_API_URL:-http://localhost:9000}"
SCRIPT_DIR="$(dirname "$0")"

QUERY="${1:-tjesmgr 기능}"
AGENT_TYPE="${2:-rag}"

# Get token
TOKEN=$(bash "$SCRIPT_DIR/api_login.sh" 2>/dev/null)

if [ -z "$TOKEN" ]; then
    echo "Login failed"
    exit 1
fi

echo "=== Query: $QUERY ==="
echo "=== Agent: $AGENT_TYPE ==="
echo ""

# Execute query and show results
curl -s -X POST "${API_URL}/api/v1/agents/stream" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d "{\"task\": \"$QUERY\", \"agent_type\": \"$AGENT_TYPE\"}" | \
  while IFS= read -r line; do
    if [[ "$line" == data:* ]]; then
      data="${line#data: }"
      if [ "$data" != "[DONE]" ] && [ -n "$data" ]; then
        # Extract text content
        text=$(echo "$data" | python -c "import sys,json; d=json.load(sys.stdin); print(d.get('content',''),end='')" 2>/dev/null)
        if [ -n "$text" ]; then
          echo -n "$text"
        fi
      fi
    fi
  done

echo ""
echo ""
echo "=== Done ==="
