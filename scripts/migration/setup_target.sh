#!/bin/bash
# =============================================================================
# KMS Target System Setup Script
# Setup Redhat Linux 64-bit GPU Environment for KMS Deployment
# =============================================================================
# Usage: sudo ./setup_target.sh
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

# Script configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INSTALL_DIR="${INSTALL_DIR:-/opt/kms}"
KMS_USER="${KMS_USER:-kms}"
KMS_GROUP="${KMS_GROUP:-kms}"

# =============================================================================
# Check if running as root
# =============================================================================
check_root() {
    if [ "$EUID" -ne 0 ]; then
        log_error "This script must be run as root (use sudo)"
        exit 1
    fi
}

# =============================================================================
# Detect OS and Version
# =============================================================================
detect_os() {
    log_step "Detecting operating system..."

    if [ -f /etc/redhat-release ]; then
        OS_TYPE="rhel"
        OS_VERSION=$(cat /etc/redhat-release | grep -oP '\d+' | head -1)
        log_info "Detected: Red Hat Enterprise Linux $OS_VERSION"
    elif [ -f /etc/centos-release ]; then
        OS_TYPE="centos"
        OS_VERSION=$(cat /etc/centos-release | grep -oP '\d+' | head -1)
        log_info "Detected: CentOS $OS_VERSION"
    elif [ -f /etc/rocky-release ]; then
        OS_TYPE="rocky"
        OS_VERSION=$(cat /etc/rocky-release | grep -oP '\d+' | head -1)
        log_info "Detected: Rocky Linux $OS_VERSION"
    elif [ -f /etc/almalinux-release ]; then
        OS_TYPE="alma"
        OS_VERSION=$(cat /etc/almalinux-release | grep -oP '\d+' | head -1)
        log_info "Detected: AlmaLinux $OS_VERSION"
    else
        log_warn "Unknown RHEL-based distribution, proceeding anyway..."
        OS_TYPE="unknown"
        OS_VERSION="8"
    fi
}

# =============================================================================
# Install System Dependencies
# =============================================================================
install_system_deps() {
    log_step "Installing system dependencies..."

    # Enable EPEL repository
    if ! rpm -q epel-release &>/dev/null; then
        log_info "Installing EPEL repository..."
        dnf install -y epel-release
    fi

    # Enable PowerTools/CRB for additional packages
    if [ "$OS_VERSION" -ge 8 ]; then
        dnf config-manager --set-enabled powertools 2>/dev/null || \
        dnf config-manager --set-enabled crb 2>/dev/null || \
        log_warn "Could not enable powertools/crb repository"
    fi

    # Install essential packages
    log_info "Installing essential packages..."
    dnf install -y \
        gcc gcc-c++ make cmake \
        git curl wget \
        openssl openssl-devel \
        libffi-devel \
        zlib-devel bzip2-devel \
        readline-devel sqlite-devel \
        xz-devel tk-devel \
        ncurses-devel \
        tar gzip unzip \
        jq htop \
        rsync \
        policycoreutils-python-utils

    log_info "System dependencies installed"
}

# =============================================================================
# Install Python 3.10+
# =============================================================================
install_python() {
    log_step "Installing Python 3.10+..."

    # Check if Python 3.10+ is already installed
    if command -v python3.10 &>/dev/null; then
        PYTHON_VERSION=$(python3.10 --version | grep -oP '\d+\.\d+')
        log_info "Python $PYTHON_VERSION already installed"
        return
    fi

    # Install Python 3.10 from source if not available
    log_info "Installing Python 3.10 from source..."

    PYTHON_VERSION="3.10.13"
    cd /tmp
    wget -q "https://www.python.org/ftp/python/$PYTHON_VERSION/Python-$PYTHON_VERSION.tgz"
    tar -xzf "Python-$PYTHON_VERSION.tgz"
    cd "Python-$PYTHON_VERSION"

    ./configure --enable-optimizations --with-ensurepip=install
    make -j$(nproc)
    make altinstall

    # Create symlinks
    ln -sf /usr/local/bin/python3.10 /usr/local/bin/python3
    ln -sf /usr/local/bin/pip3.10 /usr/local/bin/pip3

    # Clean up
    cd /tmp
    rm -rf "Python-$PYTHON_VERSION" "Python-$PYTHON_VERSION.tgz"

    log_info "Python 3.10 installed successfully"
}

# =============================================================================
# Install Node.js 18 LTS
# =============================================================================
install_nodejs() {
    log_step "Installing Node.js 18 LTS..."

    # Check if Node.js 18+ is already installed
    if command -v node &>/dev/null; then
        NODE_VERSION=$(node --version | grep -oP '\d+' | head -1)
        if [ "$NODE_VERSION" -ge 18 ]; then
            log_info "Node.js $(node --version) already installed"
            return
        fi
    fi

    # Install NodeSource repository
    log_info "Adding NodeSource repository..."
    curl -fsSL https://rpm.nodesource.com/setup_18.x | bash -

    # Install Node.js
    dnf install -y nodejs

    # Verify installation
    log_info "Node.js $(node --version) installed"
    log_info "npm $(npm --version) installed"
}

# =============================================================================
# Install Docker
# =============================================================================
install_docker() {
    log_step "Installing Docker..."

    # Check if Docker is already installed
    if command -v docker &>/dev/null; then
        log_info "Docker $(docker --version | grep -oP '\d+\.\d+\.\d+' | head -1) already installed"
    else
        # Remove old Docker versions
        dnf remove -y docker docker-client docker-client-latest \
            docker-common docker-latest docker-latest-logrotate \
            docker-logrotate docker-engine 2>/dev/null || true

        # Add Docker repository
        log_info "Adding Docker repository..."
        dnf config-manager --add-repo https://download.docker.com/linux/centos/docker-ce.repo

        # Install Docker
        dnf install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

        log_info "Docker installed successfully"
    fi

    # Enable and start Docker
    systemctl enable docker
    systemctl start docker

    log_info "Docker service started"
}

# =============================================================================
# Install NVIDIA Container Toolkit
# =============================================================================
install_nvidia_container_toolkit() {
    log_step "Installing NVIDIA Container Toolkit..."

    # Check if nvidia-smi works
    if ! command -v nvidia-smi &>/dev/null; then
        log_warn "NVIDIA driver not detected. Please install NVIDIA driver first."
        log_warn "Skipping NVIDIA Container Toolkit installation."
        return
    fi

    # Add NVIDIA Container Toolkit repository
    log_info "Adding NVIDIA Container Toolkit repository..."
    curl -s -L https://nvidia.github.io/libnvidia-container/stable/rpm/nvidia-container-toolkit.repo | \
        tee /etc/yum.repos.d/nvidia-container-toolkit.repo

    # Install toolkit
    dnf install -y nvidia-container-toolkit

    # Configure Docker to use NVIDIA runtime
    nvidia-ctk runtime configure --runtime=docker

    # Restart Docker
    systemctl restart docker

    log_info "NVIDIA Container Toolkit installed"

    # Verify GPU availability in Docker
    log_info "Verifying GPU availability in Docker..."
    docker run --rm --gpus all nvidia/cuda:12.0-base nvidia-smi && \
        log_info "GPU available in Docker containers" || \
        log_warn "GPU not available in Docker - check NVIDIA driver"
}

# =============================================================================
# Install PostgreSQL Client
# =============================================================================
install_postgresql_client() {
    log_step "Installing PostgreSQL client..."

    # Add PostgreSQL repository
    dnf install -y https://download.postgresql.org/pub/repos/yum/reporpms/EL-${OS_VERSION}-x86_64/pgdg-redhat-repo-latest.noarch.rpm 2>/dev/null || true

    # Install PostgreSQL 15 client
    dnf install -y postgresql15 postgresql15-devel 2>/dev/null || \
    dnf install -y postgresql postgresql-devel

    log_info "PostgreSQL client installed"
}

# =============================================================================
# Create KMS User and Directories
# =============================================================================
create_kms_user() {
    log_step "Creating KMS user and directories..."

    # Create group if not exists
    if ! getent group "$KMS_GROUP" &>/dev/null; then
        groupadd "$KMS_GROUP"
        log_info "Created group: $KMS_GROUP"
    fi

    # Create user if not exists
    if ! id "$KMS_USER" &>/dev/null; then
        useradd -m -g "$KMS_GROUP" -s /bin/bash "$KMS_USER"
        log_info "Created user: $KMS_USER"
    fi

    # Add user to docker group
    usermod -aG docker "$KMS_USER"

    # Create installation directory
    mkdir -p "$INSTALL_DIR"/{app,frontend,logs,uploads,neo4j,backups}

    # Set ownership
    chown -R "$KMS_USER:$KMS_GROUP" "$INSTALL_DIR"

    log_info "KMS directories created at $INSTALL_DIR"
}

# =============================================================================
# Configure Firewall
# =============================================================================
configure_firewall() {
    log_step "Configuring firewall..."

    # Check if firewalld is running
    if ! systemctl is-active --quiet firewalld; then
        log_warn "Firewalld is not running - skipping firewall configuration"
        return
    fi

    # Add ports
    local ports=(3000 9000 5432 7474 7687 12800 12801 12802)

    for port in "${ports[@]}"; do
        firewall-cmd --permanent --add-port=${port}/tcp 2>/dev/null || true
    done

    # Reload firewall
    firewall-cmd --reload

    log_info "Firewall configured for KMS ports"
}

# =============================================================================
# Configure SELinux
# =============================================================================
configure_selinux() {
    log_step "Configuring SELinux..."

    # Check if SELinux is enabled
    if ! command -v getenforce &>/dev/null || [ "$(getenforce)" == "Disabled" ]; then
        log_warn "SELinux is disabled - skipping SELinux configuration"
        return
    fi

    # Allow Docker and required ports
    setsebool -P container_manage_cgroup on 2>/dev/null || true

    log_info "SELinux configured"
}

# =============================================================================
# Setup Systemd Services
# =============================================================================
setup_systemd_services() {
    log_step "Setting up systemd services..."

    # Backend service
    cat > /etc/systemd/system/kms-backend.service << EOF
[Unit]
Description=KMS Backend API Service
After=network.target docker.service postgresql.service
Wants=docker.service

[Service]
Type=simple
User=$KMS_USER
Group=$KMS_GROUP
WorkingDirectory=$INSTALL_DIR/app
Environment="PATH=/usr/local/bin:/usr/bin:/bin"
EnvironmentFile=$INSTALL_DIR/.env
ExecStart=/usr/local/bin/python3.10 -m uvicorn app.api.main:app --host 0.0.0.0 --port 9000
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

    # Frontend service
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

    # Docker services
    cat > /etc/systemd/system/kms-docker.service << EOF
[Unit]
Description=KMS Docker Services (GPU LLM, Neo4j, PostgreSQL)
After=docker.service
Requires=docker.service

[Service]
Type=oneshot
RemainAfterExit=yes
User=$KMS_USER
Group=$KMS_GROUP
WorkingDirectory=$INSTALL_DIR/docker
ExecStart=/usr/bin/docker compose up -d
ExecStop=/usr/bin/docker compose down

[Install]
WantedBy=multi-user.target
EOF

    # Reload systemd
    systemctl daemon-reload

    log_info "Systemd services configured"
}

# =============================================================================
# Generate Environment Template
# =============================================================================
generate_env_template() {
    log_step "Generating environment template..."

    cat > "$INSTALL_DIR/.env.template" << 'EOF'
# =============================================================================
# KMS Environment Configuration - RHEL GPU Server
# =============================================================================
# IMPORTANT: Copy this to .env and update ALL required values
# Generate secrets with: openssl rand -base64 32
# =============================================================================

# ==================== Application ====================
APP_ENV=production
DEBUG=false
APP_NAME="KMS API"
APP_VERSION="1.0.0"

# ==================== Server ====================
HOST=0.0.0.0
PORT=9000
WORKERS=4

# ==================== CORS Origins ====================
CORS_ORIGINS=http://localhost:3000

# ==================== REQUIRED SECRETS ====================

# JWT Authentication (generate with: openssl rand -base64 32)
JWT_SECRET_KEY=CHANGE_ME_GENERATE_NEW_SECRET
JWT_ALGORITHM=HS256
JWT_ACCESS_TOKEN_EXPIRE_MINUTES=60
JWT_REFRESH_TOKEN_EXPIRE_DAYS=7

# Encryption Keys (generate with: openssl rand -base64 32)
ENCRYPTION_MASTER_KEY=CHANGE_ME_GENERATE_NEW_SECRET
ENCRYPTION_SALT=CHANGE_ME_GENERATE_SALT

# ==================== Database ====================

# Neo4j Graph Database
NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=CHANGE_ME_SET_NEO4J_PASSWORD

# PostgreSQL Database
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_DB=ragdb
POSTGRES_USER=raguser
POSTGRES_PASSWORD=CHANGE_ME_SET_POSTGRES_PASSWORD
POSTGRES_POOL_SIZE=10
POSTGRES_MAX_OVERFLOW=20

# ==================== Admin User ====================
ADMIN_INITIAL_PASSWORD=CHANGE_ME_SET_ADMIN_PASSWORD
ADMIN_EMAIL=admin@localhost

# ==================== LLM Configuration ====================

# Main LLM (Nemotron)
LLM_API_URL=http://localhost:12800/v1/chat/completions
LLM_MODEL=nvidia/nvidia-nemotron-nano-9b-v2

# Code LLM (Mistral NeMo)
CODE_LLM_API_URL=http://localhost:12802/v1/chat/completions
CODE_LLM_MODEL=mistralai/Mistral-Nemo-Instruct-2407
CODE_LLM_TEMPERATURE=0.1
CODE_LLM_MAX_TOKENS=2048

# Embedding Model
EMBEDDING_API_URL=http://localhost:12801/v1
EMBEDDING_MODEL=nvidia/nv-embedqa-mistral-7b-v2
EMBEDDING_DIMENSION=4096
EMBEDDING_BATCH_SIZE=32

# ==================== NVIDIA NGC API Key ====================
# Required for NVIDIA NIM containers
NGC_API_KEY=CHANGE_ME_SET_NGC_API_KEY

# HuggingFace Token (optional, for Mistral model)
HUGGING_FACE_HUB_TOKEN=

# ==================== RAG Configuration ====================
VECTOR_INDEX_NAME=chunk_embedding
VECTOR_SIMILARITY_FUNCTION=cosine
CHUNK_SIZE=1000
CHUNK_OVERLAP=200
DEFAULT_RAG_STRATEGY=auto
VECTOR_WEIGHT=0.5
TOP_K_RESULTS=5

# ==================== File Upload ====================
MAX_UPLOAD_SIZE_MB=50
UPLOAD_DIR=/opt/kms/uploads

# ==================== Rate Limiting ====================
RATE_LIMIT_QUERY=60
RATE_LIMIT_UPLOAD=10
RATE_LIMIT_DEFAULT=120
EOF

    chown "$KMS_USER:$KMS_GROUP" "$INSTALL_DIR/.env.template"

    log_info "Environment template created at $INSTALL_DIR/.env.template"
}

# =============================================================================
# Print Summary
# =============================================================================
print_summary() {
    echo ""
    echo "=============================================="
    log_info "Target system setup completed!"
    echo "=============================================="
    echo ""
    echo "Installed components:"
    echo "  - Python 3.10+"
    echo "  - Node.js 18 LTS"
    echo "  - Docker with NVIDIA Container Toolkit"
    echo "  - PostgreSQL client"
    echo ""
    echo "Created:"
    echo "  - User: $KMS_USER"
    echo "  - Install directory: $INSTALL_DIR"
    echo "  - Systemd services: kms-backend, kms-frontend, kms-docker"
    echo ""
    echo "Next steps:"
    echo "  1. Copy source files to $INSTALL_DIR"
    echo "  2. Copy .env.template to .env and configure"
    echo "  3. Run: ./deploy.sh"
    echo ""
    echo "Important configuration items:"
    echo "  - Set JWT_SECRET_KEY (openssl rand -base64 32)"
    echo "  - Set ENCRYPTION_MASTER_KEY (openssl rand -base64 32)"
    echo "  - Set ENCRYPTION_SALT (openssl rand -base64 16)"
    echo "  - Set database passwords"
    echo "  - Set NGC_API_KEY for NVIDIA NIMs"
    echo ""
}

# =============================================================================
# Main Execution
# =============================================================================
main() {
    echo "=============================================="
    echo " KMS Target System Setup"
    echo " Redhat Linux 64-bit GPU Environment"
    echo "=============================================="
    echo ""

    check_root
    detect_os
    install_system_deps
    install_python
    install_nodejs
    install_docker
    install_nvidia_container_toolkit
    install_postgresql_client
    create_kms_user
    configure_firewall
    configure_selinux
    setup_systemd_services
    generate_env_template
    print_summary
}

main "$@"
