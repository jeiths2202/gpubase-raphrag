#!/bin/bash
# Server Management Script for KMS Portal
# Usage: ./server.sh [frontend|backend|all] [start|stop|restart]

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
FRONTEND_DIR="$PROJECT_ROOT/kms-portal-ui"
FRONTEND_PORT=3000
BACKEND_PORT=9000

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

print_status() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

get_pid_by_port() {
    local port=$1
    if [[ "$OSTYPE" == "msys" || "$OSTYPE" == "cygwin" || "$OSTYPE" == "win32" ]]; then
        # Windows (Git Bash / MSYS)
        netstat -ano 2>/dev/null | grep ":$port" | grep "LISTENING" | awk '{print $5}' | head -1
    else
        # Linux/Mac
        lsof -ti:$port 2>/dev/null
    fi
}

kill_process_by_port() {
    local port=$1
    local pid=$(get_pid_by_port $port)

    if [ -n "$pid" ]; then
        print_status "Killing process on port $port (PID: $pid)"
        if [[ "$OSTYPE" == "msys" || "$OSTYPE" == "cygwin" || "$OSTYPE" == "win32" ]]; then
            taskkill //F //PID $pid 2>/dev/null || powershell -Command "Stop-Process -Id $pid -Force" 2>/dev/null
        else
            kill -9 $pid 2>/dev/null
        fi
        sleep 1
        return 0
    else
        print_warning "No process found on port $port"
        return 1
    fi
}

start_frontend() {
    local pid=$(get_pid_by_port $FRONTEND_PORT)
    if [ -n "$pid" ]; then
        print_warning "Frontend already running on port $FRONTEND_PORT (PID: $pid)"
        return 1
    fi

    print_status "Starting frontend on port $FRONTEND_PORT..."
    cd "$FRONTEND_DIR"
    npm run dev -- --port $FRONTEND_PORT &
    sleep 3

    pid=$(get_pid_by_port $FRONTEND_PORT)
    if [ -n "$pid" ]; then
        print_status "Frontend started successfully (PID: $pid)"
        print_status "URL: http://localhost:$FRONTEND_PORT"
    else
        print_error "Failed to start frontend"
        return 1
    fi
}

stop_frontend() {
    print_status "Stopping frontend on port $FRONTEND_PORT..."
    kill_process_by_port $FRONTEND_PORT
}

start_backend() {
    local pid=$(get_pid_by_port $BACKEND_PORT)
    if [ -n "$pid" ]; then
        print_warning "Backend already running on port $BACKEND_PORT (PID: $pid)"
        return 1
    fi

    print_status "Starting backend on port $BACKEND_PORT..."
    cd "$PROJECT_ROOT"
    python -m app.api.main --mode develop --port $BACKEND_PORT &
    sleep 5

    pid=$(get_pid_by_port $BACKEND_PORT)
    if [ -n "$pid" ]; then
        print_status "Backend started successfully (PID: $pid)"
        print_status "URL: http://localhost:$BACKEND_PORT"
        print_status "Docs: http://localhost:$BACKEND_PORT/docs"
    else
        print_error "Failed to start backend"
        return 1
    fi
}

stop_backend() {
    print_status "Stopping backend on port $BACKEND_PORT..."
    kill_process_by_port $BACKEND_PORT
}

show_status() {
    echo ""
    echo "=== Server Status ==="

    local frontend_pid=$(get_pid_by_port $FRONTEND_PORT)
    if [ -n "$frontend_pid" ]; then
        echo -e "Frontend (port $FRONTEND_PORT): ${GREEN}Running${NC} (PID: $frontend_pid)"
    else
        echo -e "Frontend (port $FRONTEND_PORT): ${RED}Stopped${NC}"
    fi

    local backend_pid=$(get_pid_by_port $BACKEND_PORT)
    if [ -n "$backend_pid" ]; then
        echo -e "Backend  (port $BACKEND_PORT): ${GREEN}Running${NC} (PID: $backend_pid)"
    else
        echo -e "Backend  (port $BACKEND_PORT): ${RED}Stopped${NC}"
    fi
    echo ""
}

show_usage() {
    echo "Usage: $0 [target] [action]"
    echo ""
    echo "Targets:"
    echo "  frontend    - Frontend server (port $FRONTEND_PORT)"
    echo "  backend     - Backend API server (port $BACKEND_PORT)"
    echo "  all         - Both frontend and backend"
    echo ""
    echo "Actions:"
    echo "  start       - Start server(s)"
    echo "  stop        - Stop server(s)"
    echo "  restart     - Restart server(s)"
    echo "  status      - Show server status"
    echo ""
    echo "Examples:"
    echo "  $0 frontend start     # Start frontend only"
    echo "  $0 backend restart    # Restart backend only"
    echo "  $0 all stop           # Stop all servers"
    echo "  $0 status             # Show status of all servers"
}

# Main logic
TARGET=${1:-""}
ACTION=${2:-""}

# Handle status command without target
if [ "$TARGET" == "status" ]; then
    show_status
    exit 0
fi

if [ -z "$TARGET" ] || [ -z "$ACTION" ]; then
    show_usage
    exit 1
fi

case "$TARGET" in
    frontend)
        case "$ACTION" in
            start)   start_frontend ;;
            stop)    stop_frontend ;;
            restart) stop_frontend && sleep 2 && start_frontend ;;
            status)  show_status ;;
            *)       show_usage; exit 1 ;;
        esac
        ;;
    backend)
        case "$ACTION" in
            start)   start_backend ;;
            stop)    stop_backend ;;
            restart) stop_backend && sleep 2 && start_backend ;;
            status)  show_status ;;
            *)       show_usage; exit 1 ;;
        esac
        ;;
    all)
        case "$ACTION" in
            start)
                start_backend
                start_frontend
                ;;
            stop)
                stop_frontend
                stop_backend
                ;;
            restart)
                stop_frontend
                stop_backend
                sleep 2
                start_backend
                start_frontend
                ;;
            status)
                show_status
                ;;
            *)
                show_usage
                exit 1
                ;;
        esac
        ;;
    *)
        show_usage
        exit 1
        ;;
esac

show_status
