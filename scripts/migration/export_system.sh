#!/bin/bash
# =============================================================================
# KMS System Export Script for Migration
# Export all components for migration to Redhat Linux 64-bit GPU environment
# =============================================================================
# Usage: ./export_system.sh [output_dir]
# =============================================================================

set -e

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
OUTPUT_DIR="${1:-$PROJECT_ROOT/migration_export_$TIMESTAMP}"
ARCHIVE_NAME="kms_migration_$TIMESTAMP.tar.gz"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

log_info() { echo -e "${GREEN}[INFO]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }
log_step() { echo -e "${BLUE}[STEP]${NC} $1"; }

# =============================================================================
# Pre-flight checks
# =============================================================================
preflight_check() {
    log_step "Running pre-flight checks..."

    # Check required tools
    local required_tools=("pg_dump" "git" "tar")
    for tool in "${required_tools[@]}"; do
        if ! command -v "$tool" &> /dev/null; then
            log_warn "$tool not found - some exports may fail"
        fi
    done

    # Load environment variables
    if [ -f "$PROJECT_ROOT/.env" ]; then
        set -a
        source "$PROJECT_ROOT/.env"
        set +a
        log_info "Loaded environment from .env"
    else
        log_warn "No .env file found - using defaults"
    fi
}

# =============================================================================
# Create export directory structure
# =============================================================================
setup_export_dir() {
    log_step "Creating export directory structure..."

    mkdir -p "$OUTPUT_DIR"/{database,source,config,docker,neo4j,logs}

    log_info "Export directory: $OUTPUT_DIR"
}

# =============================================================================
# Export PostgreSQL Database
# =============================================================================
export_postgresql() {
    log_step "Exporting PostgreSQL database..."

    local PG_HOST="${POSTGRES_HOST:-localhost}"
    local PG_PORT="${POSTGRES_PORT:-5432}"
    local PG_USER="${POSTGRES_USER:-raguser}"
    local PG_DB="${POSTGRES_DB:-ragdb}"
    local PG_PASSWORD="${POSTGRES_PASSWORD:-ragpassword}"

    # Export schema only
    log_info "Exporting PostgreSQL schema..."
    PGPASSWORD="$PG_PASSWORD" pg_dump \
        -h "$PG_HOST" \
        -p "$PG_PORT" \
        -U "$PG_USER" \
        -d "$PG_DB" \
        --schema-only \
        --no-owner \
        --no-privileges \
        -f "$OUTPUT_DIR/database/schema.sql" 2>/dev/null || {
            log_warn "pg_dump failed - copying migration files instead"
            cp -r "$PROJECT_ROOT/migrations" "$OUTPUT_DIR/database/"
        }

    # Export full data dump
    log_info "Exporting PostgreSQL data..."
    PGPASSWORD="$PG_PASSWORD" pg_dump \
        -h "$PG_HOST" \
        -p "$PG_PORT" \
        -U "$PG_USER" \
        -d "$PG_DB" \
        --data-only \
        --no-owner \
        --no-privileges \
        -f "$OUTPUT_DIR/database/data.sql" 2>/dev/null || {
            log_warn "Data export failed - will use migration scripts"
        }

    # Export complete dump (schema + data)
    log_info "Creating complete database dump..."
    PGPASSWORD="$PG_PASSWORD" pg_dump \
        -h "$PG_HOST" \
        -p "$PG_PORT" \
        -U "$PG_USER" \
        -d "$PG_DB" \
        --no-owner \
        --no-privileges \
        -Fc \
        -f "$OUTPUT_DIR/database/full_dump.pgdump" 2>/dev/null || {
            log_warn "Full dump failed"
        }

    # Always copy migration SQL files
    log_info "Copying migration SQL files..."
    cp -r "$PROJECT_ROOT/migrations"/*.sql "$OUTPUT_DIR/database/" 2>/dev/null || true

    log_info "PostgreSQL export completed"
}

# =============================================================================
# Export Neo4j Data
# =============================================================================
export_neo4j() {
    log_step "Exporting Neo4j data..."

    local NEO4J_DATA_DIR="$PROJECT_ROOT/neo4j/data"

    if [ -d "$NEO4J_DATA_DIR" ]; then
        log_info "Copying Neo4j data directory..."
        cp -r "$NEO4J_DATA_DIR" "$OUTPUT_DIR/neo4j/" 2>/dev/null || {
            log_warn "Neo4j data copy failed - may need manual export"
        }
    else
        log_warn "Neo4j data directory not found at $NEO4J_DATA_DIR"
    fi

    # Copy Neo4j plugins if exist
    if [ -d "$PROJECT_ROOT/neo4j/plugins" ]; then
        cp -r "$PROJECT_ROOT/neo4j/plugins" "$OUTPUT_DIR/neo4j/"
    fi

    log_info "Neo4j export completed"
}

# =============================================================================
# Export Source Code
# =============================================================================
export_source() {
    log_step "Exporting source code..."

    # Export backend
    log_info "Exporting backend source..."
    mkdir -p "$OUTPUT_DIR/source/app"
    cp -r "$PROJECT_ROOT/app" "$OUTPUT_DIR/source/"

    # Export frontend
    log_info "Exporting frontend source..."
    mkdir -p "$OUTPUT_DIR/source/kms-portal-ui"
    rsync -av --exclude='node_modules' --exclude='.git' --exclude='dist' \
        "$PROJECT_ROOT/kms-portal-ui/" "$OUTPUT_DIR/source/kms-portal-ui/" 2>/dev/null || {
        # Fallback if rsync not available
        cp -r "$PROJECT_ROOT/kms-portal-ui" "$OUTPUT_DIR/source/"
        rm -rf "$OUTPUT_DIR/source/kms-portal-ui/node_modules" 2>/dev/null || true
        rm -rf "$OUTPUT_DIR/source/kms-portal-ui/dist" 2>/dev/null || true
    }

    # Export scripts
    log_info "Exporting utility scripts..."
    cp -r "$PROJECT_ROOT/scripts" "$OUTPUT_DIR/source/"

    # Export tests
    log_info "Exporting test files..."
    cp -r "$PROJECT_ROOT/tests" "$OUTPUT_DIR/source/" 2>/dev/null || true

    # Export docs
    if [ -d "$PROJECT_ROOT/docs" ]; then
        cp -r "$PROJECT_ROOT/docs" "$OUTPUT_DIR/source/"
    fi

    log_info "Source code export completed"
}

# =============================================================================
# Export Configuration Files
# =============================================================================
export_config() {
    log_step "Exporting configuration files..."

    # Copy environment example
    cp "$PROJECT_ROOT/.env.example" "$OUTPUT_DIR/config/" 2>/dev/null || true

    # Copy requirements
    cp "$PROJECT_ROOT/requirements-api.txt" "$OUTPUT_DIR/config/"
    cp "$PROJECT_ROOT/app/requirements.txt" "$OUTPUT_DIR/config/" 2>/dev/null || true

    # Copy package.json for frontend
    cp "$PROJECT_ROOT/kms-portal-ui/package.json" "$OUTPUT_DIR/config/frontend-package.json"
    cp "$PROJECT_ROOT/kms-portal-ui/package-lock.json" "$OUTPUT_DIR/config/frontend-package-lock.json" 2>/dev/null || true

    # Copy Docker configuration
    cp -r "$PROJECT_ROOT/docker" "$OUTPUT_DIR/docker/"

    # Copy CLAUDE.md files for reference
    cp "$PROJECT_ROOT/CLAUDE.md" "$OUTPUT_DIR/config/" 2>/dev/null || true
    cp "$PROJECT_ROOT/app/api/CLAUDE.md" "$OUTPUT_DIR/config/api-CLAUDE.md" 2>/dev/null || true
    cp "$PROJECT_ROOT/kms-portal-ui/CLAUDE.md" "$OUTPUT_DIR/config/ui-CLAUDE.md" 2>/dev/null || true

    # Generate pip freeze
    log_info "Generating Python dependency list..."
    pip freeze > "$OUTPUT_DIR/config/pip_freeze.txt" 2>/dev/null || {
        log_warn "pip freeze failed - using requirements file"
    }

    log_info "Configuration export completed"
}

# =============================================================================
# Generate Installation Scripts for Target
# =============================================================================
generate_install_scripts() {
    log_step "Generating installation scripts for target system..."

    # Copy setup and deploy scripts
    cp "$SCRIPT_DIR/setup_target.sh" "$OUTPUT_DIR/" 2>/dev/null || true
    cp "$SCRIPT_DIR/deploy.sh" "$OUTPUT_DIR/" 2>/dev/null || true

    log_info "Installation scripts generated"
}

# =============================================================================
# Create Migration Archive
# =============================================================================
create_archive() {
    log_step "Creating migration archive..."

    cd "$(dirname "$OUTPUT_DIR")"
    tar -czvf "$ARCHIVE_NAME" "$(basename "$OUTPUT_DIR")"

    log_info "Archive created: $(dirname "$OUTPUT_DIR")/$ARCHIVE_NAME"

    # Calculate checksum
    if command -v sha256sum &> /dev/null; then
        sha256sum "$ARCHIVE_NAME" > "$ARCHIVE_NAME.sha256"
        log_info "Checksum created: $ARCHIVE_NAME.sha256"
    fi
}

# =============================================================================
# Generate Migration Report
# =============================================================================
generate_report() {
    log_step "Generating migration report..."

    local REPORT_FILE="$OUTPUT_DIR/MIGRATION_REPORT.md"

    cat > "$REPORT_FILE" << EOF
# KMS System Migration Report

**Generated:** $(date '+%Y-%m-%d %H:%M:%S')
**Source System:** $(uname -a)

## Exported Components

### 1. Database
- PostgreSQL schema: \`database/schema.sql\`
- PostgreSQL data: \`database/data.sql\`
- Full dump: \`database/full_dump.pgdump\`
- Migration scripts: \`database/*.sql\`

### 2. Source Code
- Backend API: \`source/app/\`
- Frontend UI: \`source/kms-portal-ui/\`
- Scripts: \`source/scripts/\`
- Tests: \`source/tests/\`

### 3. Configuration
- Environment template: \`config/.env.example\`
- Python requirements: \`config/requirements-api.txt\`
- Frontend packages: \`config/frontend-package.json\`
- Docker compose: \`docker/docker-compose.yml\`

### 4. Neo4j Data
- Data directory: \`neo4j/data/\`
- Plugins: \`neo4j/plugins/\`

## Target System Requirements

### Hardware
- CPU: 8+ cores recommended
- RAM: 64GB+ recommended
- GPU: NVIDIA A100 or equivalent (8x for full deployment)
- Storage: 500GB+ SSD

### Software
- OS: Red Hat Enterprise Linux 8/9 (64-bit)
- Python: 3.10+
- Node.js: 18+ LTS
- Docker: 24.0+
- NVIDIA Driver: 535+
- CUDA: 12.0+

## Installation Instructions

1. Transfer archive to target system
2. Extract: \`tar -xzvf $ARCHIVE_NAME\`
3. Run setup: \`./setup_target.sh\`
4. Configure: Edit \`.env\` file
5. Deploy: \`./deploy.sh\`

## Port Allocations

| Port  | Service              |
|-------|----------------------|
| 3000  | React Frontend       |
| 9000  | FastAPI Backend      |
| 5432  | PostgreSQL           |
| 7474  | Neo4j HTTP           |
| 7687  | Neo4j Bolt           |
| 12800 | Nemotron LLM         |
| 12801 | NeMo Embedding       |
| 12802 | Mistral Code LLM     |

## Post-Installation Checklist

- [ ] Generate new JWT_SECRET_KEY
- [ ] Generate new ENCRYPTION_MASTER_KEY
- [ ] Generate new ENCRYPTION_SALT
- [ ] Set NEO4J_PASSWORD
- [ ] Set POSTGRES_PASSWORD
- [ ] Configure NGC_API_KEY for NVIDIA NIMs
- [ ] Verify GPU availability with \`nvidia-smi\`
- [ ] Run database migrations
- [ ] Test all services
EOF

    log_info "Migration report generated: $REPORT_FILE"
}

# =============================================================================
# Main Execution
# =============================================================================
main() {
    echo "=============================================="
    echo " KMS System Export for Migration"
    echo " Target: Redhat Linux 64-bit GPU Environment"
    echo "=============================================="
    echo ""

    preflight_check
    setup_export_dir
    export_postgresql
    export_neo4j
    export_source
    export_config
    generate_install_scripts
    generate_report
    create_archive

    echo ""
    echo "=============================================="
    log_info "Export completed successfully!"
    echo "=============================================="
    echo ""
    echo "Export directory: $OUTPUT_DIR"
    echo "Archive file: $(dirname "$OUTPUT_DIR")/$ARCHIVE_NAME"
    echo ""
    echo "Next steps:"
    echo "1. Transfer the archive to the target RHEL system"
    echo "2. Extract: tar -xzvf $ARCHIVE_NAME"
    echo "3. Run: ./setup_target.sh"
    echo "4. Configure .env file"
    echo "5. Run: ./deploy.sh"
    echo ""
}

main "$@"
