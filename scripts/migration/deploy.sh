#!/bin/bash
# =============================================================================
# KMS Deployment Script
# Deploy KMS system on target Redhat Linux 64-bit GPU Environment
# =============================================================================
# Usage: ./deploy.sh [options]
# Options:
#   --skip-docker    Skip Docker services startup
#   --skip-db        Skip database initialization
#   --skip-frontend  Skip frontend build
#   --force          Force reinstall even if already deployed
# =============================================================================

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log_info() { echo -e "${GREEN}[INFO]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }
log_step() { echo -e "${BLUE}[STEP]${NC} $1"; }

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INSTALL_DIR="${INSTALL_DIR:-/opt/kms}"
KMS_USER="${KMS_USER:-kms}"
KMS_GROUP="${KMS_GROUP:-kms}"

# Parse arguments
SKIP_DOCKER=false
SKIP_DB=false
SKIP_FRONTEND=false
FORCE=false

while [[ $# -gt 0 ]]; do
    case $1 in
        --skip-docker) SKIP_DOCKER=true; shift ;;
        --skip-db) SKIP_DB=true; shift ;;
        --skip-frontend) SKIP_FRONTEND=true; shift ;;
        --force) FORCE=true; shift ;;
        *) shift ;;
    esac
done

# =============================================================================
# Pre-deployment Checks
# =============================================================================
precheck() {
    log_step "Running pre-deployment checks..."

    # Check if running as appropriate user
    if [ "$EUID" -eq 0 ]; then
        log_warn "Running as root - will switch to $KMS_USER for some operations"
    fi

    # Check if .env exists
    if [ ! -f "$INSTALL_DIR/.env" ]; then
        if [ -f "$INSTALL_DIR/.env.template" ]; then
            log_warn ".env not found - creating from template"
            cp "$INSTALL_DIR/.env.template" "$INSTALL_DIR/.env"
            log_error "Please edit $INSTALL_DIR/.env before continuing!"
            exit 1
        else
            log_error ".env file not found. Please create it first."
            exit 1
        fi
    fi

    # Load environment
    set -a
    source "$INSTALL_DIR/.env"
    set +a

    # Check required environment variables
    local required_vars=(
        "JWT_SECRET_KEY"
        "ENCRYPTION_MASTER_KEY"
        "ENCRYPTION_SALT"
        "NEO4J_PASSWORD"
        "POSTGRES_PASSWORD"
    )

    for var in "${required_vars[@]}"; do
        if [ -z "${!var}" ] || [[ "${!var}" == *"CHANGE_ME"* ]]; then
            log_error "Required variable $var is not set or has default value"
            exit 1
        fi
    done

    log_info "Pre-deployment checks passed"
}

# =============================================================================
# Copy Source Files
# =============================================================================
copy_source_files() {
    log_step "Copying source files..."

    # Copy from export directory if available
    if [ -d "$SCRIPT_DIR/source" ]; then
        log_info "Copying backend source..."
        cp -r "$SCRIPT_DIR/source/app" "$INSTALL_DIR/"

        log_info "Copying frontend source..."
        cp -r "$SCRIPT_DIR/source/kms-portal-ui" "$INSTALL_DIR/frontend"

        log_info "Copying scripts..."
        cp -r "$SCRIPT_DIR/source/scripts" "$INSTALL_DIR/"

        # Copy Docker configuration
        if [ -d "$SCRIPT_DIR/docker" ]; then
            cp -r "$SCRIPT_DIR/docker" "$INSTALL_DIR/"
        fi
    else
        log_warn "Source directory not found - assuming files already in place"
    fi

    # Set permissions
    chown -R "$KMS_USER:$KMS_GROUP" "$INSTALL_DIR"

    log_info "Source files copied"
}

# =============================================================================
# Install Python Dependencies
# =============================================================================
install_python_deps() {
    log_step "Installing Python dependencies..."

    cd "$INSTALL_DIR/app"

    # Create virtual environment if not exists
    if [ ! -d "$INSTALL_DIR/venv" ]; then
        log_info "Creating Python virtual environment..."
        python3.10 -m venv "$INSTALL_DIR/venv"
    fi

    # Activate virtual environment
    source "$INSTALL_DIR/venv/bin/activate"

    # Upgrade pip
    pip install --upgrade pip wheel setuptools

    # Install requirements
    if [ -f "$SCRIPT_DIR/config/requirements-api.txt" ]; then
        pip install -r "$SCRIPT_DIR/config/requirements-api.txt"
    elif [ -f "$INSTALL_DIR/app/requirements-api.txt" ]; then
        pip install -r "$INSTALL_DIR/app/requirements-api.txt"
    else
        log_error "requirements-api.txt not found"
        exit 1
    fi

    # Install additional GPU-related packages
    pip install nvidia-ml-py3 2>/dev/null || true

    deactivate

    log_info "Python dependencies installed"
}

# =============================================================================
# Build Frontend
# =============================================================================
build_frontend() {
    if [ "$SKIP_FRONTEND" = true ]; then
        log_info "Skipping frontend build (--skip-frontend)"
        return
    fi

    log_step "Building frontend..."

    cd "$INSTALL_DIR/frontend"

    # Install npm dependencies
    log_info "Installing npm dependencies..."
    npm ci --legacy-peer-deps 2>/dev/null || npm install

    # Build production version
    log_info "Building production bundle..."
    npm run build

    log_info "Frontend build completed"
}

# =============================================================================
# Start Docker Services
# =============================================================================
start_docker_services() {
    if [ "$SKIP_DOCKER" = true ]; then
        log_info "Skipping Docker services (--skip-docker)"
        return
    fi

    log_step "Starting Docker services..."

    cd "$INSTALL_DIR/docker"

    # Create .env file for docker-compose if not exists
    if [ ! -f "$INSTALL_DIR/docker/.env" ]; then
        cat > "$INSTALL_DIR/docker/.env" << EOF
NEO4J_PASSWORD=${NEO4J_PASSWORD}
POSTGRES_DB=${POSTGRES_DB:-ragdb}
POSTGRES_USER=${POSTGRES_USER:-raguser}
POSTGRES_PASSWORD=${POSTGRES_PASSWORD}
NGC_API_KEY=${NGC_API_KEY:-}
HUGGING_FACE_HUB_TOKEN=${HUGGING_FACE_HUB_TOKEN:-}
EOF
    fi

    # Stop existing containers
    docker compose down 2>/dev/null || true

    # Start services
    log_info "Starting Docker containers..."
    docker compose up -d

    # Wait for services to be healthy
    log_info "Waiting for services to be ready..."

    # Wait for PostgreSQL
    log_info "Waiting for PostgreSQL..."
    local max_attempts=30
    local attempt=0
    while [ $attempt -lt $max_attempts ]; do
        if docker exec postgres-graphrag pg_isready -U "${POSTGRES_USER:-raguser}" &>/dev/null; then
            log_info "PostgreSQL is ready"
            break
        fi
        attempt=$((attempt + 1))
        sleep 2
    done

    # Wait for Neo4j
    log_info "Waiting for Neo4j..."
    attempt=0
    while [ $attempt -lt $max_attempts ]; do
        if curl -s http://localhost:7474 &>/dev/null; then
            log_info "Neo4j is ready"
            break
        fi
        attempt=$((attempt + 1))
        sleep 2
    done

    log_info "Docker services started"
}

# =============================================================================
# Initialize Database
# =============================================================================
init_database() {
    if [ "$SKIP_DB" = true ]; then
        log_info "Skipping database initialization (--skip-db)"
        return
    fi

    log_step "Initializing database..."

    # Wait a bit more for database to be fully ready
    sleep 5

    # Run PostgreSQL migrations
    log_info "Running PostgreSQL migrations..."

    local PG_HOST="${POSTGRES_HOST:-localhost}"
    local PG_PORT="${POSTGRES_PORT:-5432}"
    local PG_USER="${POSTGRES_USER:-raguser}"
    local PG_DB="${POSTGRES_DB:-ragdb}"
    local PG_PASSWORD="${POSTGRES_PASSWORD}"

    # Find migration files
    local MIGRATION_DIR=""
    if [ -d "$SCRIPT_DIR/database" ]; then
        MIGRATION_DIR="$SCRIPT_DIR/database"
    elif [ -d "$INSTALL_DIR/app/migrations" ]; then
        MIGRATION_DIR="$INSTALL_DIR/app/migrations"
    fi

    if [ -n "$MIGRATION_DIR" ] && [ -d "$MIGRATION_DIR" ]; then
        # Sort and apply migrations
        for sql_file in $(ls "$MIGRATION_DIR"/*.sql 2>/dev/null | sort); do
            log_info "Applying migration: $(basename $sql_file)"
            PGPASSWORD="$PG_PASSWORD" psql \
                -h "$PG_HOST" \
                -p "$PG_PORT" \
                -U "$PG_USER" \
                -d "$PG_DB" \
                -f "$sql_file" 2>/dev/null || {
                    log_warn "Migration $(basename $sql_file) may have already been applied"
                }
        done
    else
        log_warn "Migration directory not found - skipping"
    fi

    # Restore data if available
    if [ -f "$SCRIPT_DIR/database/data.sql" ]; then
        log_info "Restoring data..."
        PGPASSWORD="$PG_PASSWORD" psql \
            -h "$PG_HOST" \
            -p "$PG_PORT" \
            -U "$PG_USER" \
            -d "$PG_DB" \
            -f "$SCRIPT_DIR/database/data.sql" 2>/dev/null || {
                log_warn "Data restore may have failed - check manually"
            }
    fi

    log_info "Database initialization completed"
}

# =============================================================================
# Update Systemd Service Files
# =============================================================================
update_systemd_services() {
    log_step "Updating systemd service files..."

    # Update backend service to use virtual environment
    cat > /etc/systemd/system/kms-backend.service << EOF
[Unit]
Description=KMS Backend API Service
After=network.target docker.service
Wants=docker.service kms-docker.service

[Service]
Type=simple
User=$KMS_USER
Group=$KMS_GROUP
WorkingDirectory=$INSTALL_DIR/app
Environment="PATH=$INSTALL_DIR/venv/bin:/usr/local/bin:/usr/bin:/bin"
EnvironmentFile=$INSTALL_DIR/.env
ExecStart=$INSTALL_DIR/venv/bin/python -m uvicorn app.api.main:app --host 0.0.0.0 --port 9000
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

    # Update frontend service
    cat > /etc/systemd/system/kms-frontend.service << EOF
[Unit]
Description=KMS Frontend UI Service
After=network.target kms-backend.service

[Service]
Type=simple
User=$KMS_USER
Group=$KMS_GROUP
WorkingDirectory=$INSTALL_DIR/frontend
Environment="PATH=/usr/local/bin:/usr/bin:/bin"
Environment="NODE_ENV=production"
ExecStart=/usr/bin/npm run preview -- --host 0.0.0.0 --port 3000
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

    # Reload systemd
    systemctl daemon-reload

    log_info "Systemd services updated"
}

# =============================================================================
# Start Services
# =============================================================================
start_services() {
    log_step "Starting KMS services..."

    # Enable and start services
    systemctl enable kms-docker kms-backend kms-frontend

    # Start backend
    log_info "Starting backend service..."
    systemctl start kms-backend

    # Wait for backend
    sleep 5

    # Check backend health
    local max_attempts=30
    local attempt=0
    while [ $attempt -lt $max_attempts ]; do
        if curl -s http://localhost:9000/docs &>/dev/null; then
            log_info "Backend is healthy"
            break
        fi
        attempt=$((attempt + 1))
        sleep 2
    done

    # Start frontend
    log_info "Starting frontend service..."
    systemctl start kms-frontend

    log_info "Services started"
}

# =============================================================================
# Verify Deployment
# =============================================================================
verify_deployment() {
    log_step "Verifying deployment..."

    local errors=0

    # Check PostgreSQL
    if docker exec postgres-graphrag pg_isready -U "${POSTGRES_USER:-raguser}" &>/dev/null; then
        log_info "PostgreSQL: OK"
    else
        log_error "PostgreSQL: FAILED"
        errors=$((errors + 1))
    fi

    # Check Neo4j
    if curl -s http://localhost:7474 &>/dev/null; then
        log_info "Neo4j: OK"
    else
        log_error "Neo4j: FAILED"
        errors=$((errors + 1))
    fi

    # Check Backend API
    if curl -s http://localhost:9000/docs &>/dev/null; then
        log_info "Backend API: OK"
    else
        log_error "Backend API: FAILED"
        errors=$((errors + 1))
    fi

    # Check Frontend
    if curl -s http://localhost:3000 &>/dev/null; then
        log_info "Frontend: OK"
    else
        log_warn "Frontend: May need more time to start"
    fi

    # Check GPU services (if configured)
    if [ -n "$NGC_API_KEY" ]; then
        if curl -s http://localhost:12800/v1/health/ready &>/dev/null; then
            log_info "Nemotron LLM: OK"
        else
            log_warn "Nemotron LLM: May need more time to start (GPU models take longer)"
        fi

        if curl -s http://localhost:12801/v1/health/ready &>/dev/null; then
            log_info "NeMo Embedding: OK"
        else
            log_warn "NeMo Embedding: May need more time to start"
        fi
    fi

    if [ $errors -gt 0 ]; then
        log_error "Deployment verification found $errors error(s)"
        return 1
    fi

    log_info "Deployment verification completed successfully"
}

# =============================================================================
# Print Deployment Summary
# =============================================================================
print_summary() {
    echo ""
    echo "=============================================="
    log_info "KMS Deployment Completed!"
    echo "=============================================="
    echo ""
    echo "Service URLs:"
    echo "  Frontend:    http://$(hostname -I | awk '{print $1}'):3000"
    echo "  Backend API: http://$(hostname -I | awk '{print $1}'):9000"
    echo "  API Docs:    http://$(hostname -I | awk '{print $1}'):9000/docs"
    echo "  Neo4j:       http://$(hostname -I | awk '{print $1}'):7474"
    echo ""
    echo "Service Management:"
    echo "  systemctl status kms-backend     # Check backend status"
    echo "  systemctl status kms-frontend    # Check frontend status"
    echo "  systemctl status kms-docker      # Check Docker services"
    echo ""
    echo "  systemctl restart kms-backend    # Restart backend"
    echo "  systemctl restart kms-frontend   # Restart frontend"
    echo ""
    echo "Logs:"
    echo "  journalctl -u kms-backend -f     # Backend logs"
    echo "  journalctl -u kms-frontend -f    # Frontend logs"
    echo "  docker logs nemotron-graphrag    # LLM logs"
    echo ""
    echo "Configuration:"
    echo "  Environment: $INSTALL_DIR/.env"
    echo "  Docker:      $INSTALL_DIR/docker/docker-compose.yml"
    echo ""
}

# =============================================================================
# Main Execution
# =============================================================================
main() {
    echo "=============================================="
    echo " KMS System Deployment"
    echo " Target: Redhat Linux 64-bit GPU Environment"
    echo "=============================================="
    echo ""

    precheck
    copy_source_files
    install_python_deps
    build_frontend
    start_docker_services
    init_database
    update_systemd_services
    start_services
    verify_deployment
    print_summary
}

main "$@"
