#!/bin/bash
# ============================================================================
# Generate self-signed SSL certificates for KMS Frontend (HTTPS)
# ============================================================================
# Run once before first deployment:
#   bash scripts/generate-ssl-certs.sh
#
# Certificates are generated in docker/ssl/ directory.
# Valid for 365 days. Re-run to regenerate after expiry.
# ============================================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
SSL_DIR="$PROJECT_DIR/docker/ssl"

mkdir -p "$SSL_DIR"

if [ -f "$SSL_DIR/server.crt" ] && [ -f "$SSL_DIR/server.key" ]; then
    echo "SSL certificates already exist in $SSL_DIR"
    echo "  Certificate: $SSL_DIR/server.crt"
    echo "  Private Key: $SSL_DIR/server.key"
    echo ""
    echo "To regenerate, delete them first:"
    echo "  rm $SSL_DIR/server.crt $SSL_DIR/server.key"
    exit 0
fi

echo "Generating self-signed SSL certificate for 192.168.8.11..."
echo ""

openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
    -keyout "$SSL_DIR/server.key" \
    -out "$SSL_DIR/server.crt" \
    -subj "/CN=192.168.8.11/O=TmaxSoft KMS/C=JP/ST=Tokyo/L=Tokyo" \
    -addext "subjectAltName=IP:192.168.8.11,DNS:localhost,IP:127.0.0.1"

chmod 644 "$SSL_DIR/server.crt"
chmod 600 "$SSL_DIR/server.key"

echo "SSL certificates generated successfully!"
echo "  Certificate: $SSL_DIR/server.crt"
echo "  Private Key: $SSL_DIR/server.key"
echo "  Valid for:   365 days"
echo ""
echo "Next steps:"
echo "  docker compose -f kms.docker-compose.yml build kms-backend kms-frontend"
echo "  docker compose -f kms.docker-compose.yml up -d kms-backend kms-frontend kms-redis"
