#!/bin/bash
# ============================================================
# Local Test Execution Script
# ============================================================
# Runs all local tests without requiring external dependencies
# (GPU, cloud services, databases, external APIs)
#
# Usage:
#   ./scripts/run_local_tests.sh          # Run all tests
#   ./scripts/run_local_tests.sh backend  # Run backend only
#   ./scripts/run_local_tests.sh frontend # Run frontend only
#   ./scripts/run_local_tests.sh --coverage # Run with coverage
# ============================================================

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

# Configuration
BACKEND_DIR="$PROJECT_ROOT"
FRONTEND_DIR="$PROJECT_ROOT/frontend"
ENV_FILE="$PROJECT_ROOT/.env.test"

# Results
BACKEND_RESULT=0
FRONTEND_RESULT=0
E2E_RESULT=0

# ============================================================
# Helper Functions
# ============================================================

print_header() {
    echo ""
    echo -e "${BLUE}============================================================${NC}"
    echo -e "${BLUE}$1${NC}"
    echo -e "${BLUE}============================================================${NC}"
    echo ""
}

print_success() {
    echo -e "${GREEN}✓ $1${NC}"
}

print_error() {
    echo -e "${RED}✗ $1${NC}"
}

print_warning() {
    echo -e "${YELLOW}⚠ $1${NC}"
}

print_info() {
    echo -e "${BLUE}ℹ $1${NC}"
}

# ============================================================
# Environment Setup
# ============================================================

setup_environment() {
    print_header "Setting Up Test Environment"

    # Check if .env.test exists
    if [ ! -f "$ENV_FILE" ]; then
        print_error ".env.test not found!"
        print_info "Creating default .env.test..."
        cat > "$ENV_FILE" << 'EOF'
APP_ENV=testing
DEBUG=false
JWT_SECRET_KEY=test-secret-key-minimum-32-characters-for-testing
JWT_ALGORITHM=HS256
EOF
    fi

    # Export test environment variables
    export APP_ENV=testing
    export DEBUG=false
    export JWT_SECRET_KEY="test-secret-key-minimum-32-characters-for-testing"

    print_success "Environment configured"
}

# ============================================================
# Backend Tests
# ============================================================

run_backend_tests() {
    print_header "Running Backend Tests (pytest)"

    cd "$BACKEND_DIR"

    # Check if pytest is available
    if ! command -v python &> /dev/null; then
        print_error "Python not found!"
        return 1
    fi

    # Install test dependencies if needed
    if [ "$1" == "--install" ]; then
        print_info "Installing test dependencies..."
        pip install pytest pytest-asyncio pytest-cov httpx -q
    fi

    # Run pytest with coverage option
    if [ "$1" == "--coverage" ] || [ "$2" == "--coverage" ]; then
        print_info "Running with coverage..."
        python -m pytest tests/ \
            -v \
            --tb=short \
            --cov=app/api \
            --cov-report=html:coverage_html \
            --cov-report=term-missing \
            --ignore=tests/integration/ \
            -x
        BACKEND_RESULT=$?
    else
        python -m pytest tests/ \
            -v \
            --tb=short \
            --ignore=tests/integration/ \
            -x
        BACKEND_RESULT=$?
    fi

    if [ $BACKEND_RESULT -eq 0 ]; then
        print_success "Backend tests passed!"
    else
        print_error "Backend tests failed!"
    fi

    return $BACKEND_RESULT
}

# ============================================================
# Frontend Unit Tests
# ============================================================

run_frontend_unit_tests() {
    print_header "Running Frontend Unit Tests (Vitest)"

    cd "$FRONTEND_DIR"

    # Check if npm is available
    if ! command -v npm &> /dev/null; then
        print_error "npm not found!"
        return 1
    fi

    # Check if node_modules exists
    if [ ! -d "node_modules" ]; then
        print_info "Installing frontend dependencies..."
        npm install
    fi

    # Run Vitest
    if [ "$1" == "--coverage" ]; then
        npm run test:run -- --coverage
        FRONTEND_RESULT=$?
    else
        npm run test:run
        FRONTEND_RESULT=$?
    fi

    if [ $FRONTEND_RESULT -eq 0 ]; then
        print_success "Frontend unit tests passed!"
    else
        print_error "Frontend unit tests failed!"
    fi

    return $FRONTEND_RESULT
}

# ============================================================
# Frontend E2E Tests
# ============================================================

run_frontend_e2e_tests() {
    print_header "Running Frontend E2E Tests (Playwright)"

    cd "$FRONTEND_DIR"

    # Check if Playwright is installed
    if [ ! -d "node_modules/@playwright" ]; then
        print_info "Installing Playwright..."
        npx playwright install --with-deps chromium
    fi

    # Run Playwright tests
    npx playwright test --reporter=list
    E2E_RESULT=$?

    if [ $E2E_RESULT -eq 0 ]; then
        print_success "E2E tests passed!"
    else
        print_error "E2E tests failed!"
    fi

    return $E2E_RESULT
}

# ============================================================
# Summary
# ============================================================

print_summary() {
    print_header "Test Summary"

    echo "Backend Tests:  $([ $BACKEND_RESULT -eq 0 ] && echo -e "${GREEN}PASSED${NC}" || echo -e "${RED}FAILED${NC}")"
    echo "Frontend Tests: $([ $FRONTEND_RESULT -eq 0 ] && echo -e "${GREEN}PASSED${NC}" || echo -e "${RED}FAILED${NC}")"
    echo "E2E Tests:      $([ $E2E_RESULT -eq 0 ] && echo -e "${GREEN}PASSED${NC}" || echo -e "${RED}FAILED${NC}")"
    echo ""

    TOTAL=$((BACKEND_RESULT + FRONTEND_RESULT + E2E_RESULT))

    if [ $TOTAL -eq 0 ]; then
        print_success "All tests passed!"
        return 0
    else
        print_error "Some tests failed!"
        return 1
    fi
}

# ============================================================
# Main
# ============================================================

main() {
    print_header "Local Test Execution"
    print_info "Project: GPU-Based Enterprise RAG KMS Platform"
    print_info "Date: $(date)"
    echo ""

    # Parse arguments
    COVERAGE=""
    RUN_BACKEND=true
    RUN_FRONTEND=true
    RUN_E2E=false  # E2E tests require dev server

    for arg in "$@"; do
        case $arg in
            backend)
                RUN_FRONTEND=false
                RUN_E2E=false
                ;;
            frontend)
                RUN_BACKEND=false
                ;;
            e2e)
                RUN_BACKEND=false
                RUN_FRONTEND=false
                RUN_E2E=true
                ;;
            --coverage)
                COVERAGE="--coverage"
                ;;
            --all)
                RUN_E2E=true
                ;;
            --help)
                echo "Usage: $0 [backend|frontend|e2e|--coverage|--all|--help]"
                echo ""
                echo "Options:"
                echo "  backend     Run only backend tests"
                echo "  frontend    Run only frontend unit tests"
                echo "  e2e         Run only E2E tests (requires dev server)"
                echo "  --coverage  Generate coverage reports"
                echo "  --all       Run all tests including E2E"
                echo "  --help      Show this help message"
                exit 0
                ;;
        esac
    done

    # Setup environment
    setup_environment

    # Run tests
    if [ "$RUN_BACKEND" = true ]; then
        run_backend_tests $COVERAGE || BACKEND_RESULT=$?
    fi

    if [ "$RUN_FRONTEND" = true ]; then
        run_frontend_unit_tests $COVERAGE || FRONTEND_RESULT=$?
    fi

    if [ "$RUN_E2E" = true ]; then
        run_frontend_e2e_tests || E2E_RESULT=$?
    fi

    # Print summary
    print_summary

    exit $?
}

# Run main
main "$@"
