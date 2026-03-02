#!/bin/bash
# ============================================================================
# Pack KMS Desktop Deployment into a zip file
# ============================================================================
# Creates kms-desktop-deploy.zip with all files needed to run
# backend + frontend in Docker on any desktop machine.
# GPU and DB services connect to remote server (192.168.8.11).
#
# Usage: bash scripts/pack-desktop-deploy.sh
# ============================================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
OUTPUT="$PROJECT_DIR/kms-desktop-deploy.zip"

cd "$PROJECT_DIR"

# Remove old zip if exists
rm -f "$OUTPUT"

echo "Packing KMS Desktop Deployment..."
echo ""

zip -r "$OUTPUT" \
  docker-compose.desktop.yml \
  .env.desktop \
  Dockerfile.local \
  docker-entrypoint.sh \
  requirements-pinned.txt \
  scripts/generate-ssl-certs.sh \
  docker/ssl/.gitkeep \
  kms-portal-ui/Dockerfile \
  kms-portal-ui/nginx-ssl.conf \
  kms-portal-ui/nginx.conf \
  kms-portal-ui/package.json \
  kms-portal-ui/package-lock.json \
  kms-portal-ui/tsconfig.json \
  kms-portal-ui/tsconfig.node.json \
  kms-portal-ui/vite.config.ts \
  kms-portal-ui/index.html \
  kms-portal-ui/src/ \
  kms-portal-ui/public/ \
  app/api/ \
  uploads/summaries/ \
  -x "**/__pycache__/*" \
  -x "**/.pytest_cache/*" \
  -x "**/node_modules/*" \
  -x "**/*.pyc" \
  -x "**/.DS_Store"

echo ""
echo "Created: $OUTPUT"
echo "Size: $(du -h "$OUTPUT" | cut -f1)"
echo ""
echo "=== Deployment Instructions ==="
echo "1. Unzip on target desktop"
echo "2. bash scripts/generate-ssl-certs.sh"
echo "3. docker compose -f docker-compose.desktop.yml build"
echo "4. docker compose -f docker-compose.desktop.yml up -d"
echo "5. Open https://localhost:3000"
