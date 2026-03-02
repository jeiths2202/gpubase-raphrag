#!/bin/bash
# =============================================================================
# KMS API Login Script
# =============================================================================
# Usage:
#   source scripts/api_login.sh           # Set TOKEN env variable
#   ./scripts/api_login.sh                # Print token only
#   ./scripts/api_login.sh --export       # Export TOKEN
#
# After sourcing, use: $TOKEN for API calls
# =============================================================================

API_URL="${KMS_API_URL:-http://localhost:9000}"
LOGIN_FILE="$(dirname "$0")/login.json"

# Login and extract token
TOKEN=$(curl -s -X POST "${API_URL}/api/v1/auth/login" \
  -H "Content-Type: application/json" \
  -d @"$LOGIN_FILE" | python -c "import sys,json; print(json.load(sys.stdin).get('data',{}).get('access_token',''))" 2>/dev/null)

if [ -z "$TOKEN" ]; then
    echo "Login failed" >&2
    exit 1
fi

# If --export flag, export the variable
if [ "$1" = "--export" ]; then
    export TOKEN
    echo "TOKEN exported successfully"
elif [ "$0" = "$BASH_SOURCE" ]; then
    # Script executed directly - print token
    echo "$TOKEN"
else
    # Script sourced - export TOKEN
    export TOKEN
    echo "TOKEN set. Use: \$TOKEN"
fi
