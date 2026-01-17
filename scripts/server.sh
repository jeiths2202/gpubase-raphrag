#!/bin/bash
# Server Management Script for KMS Portal
# Usage: ./server.sh [frontend|backend|all] [start|stop|restart]

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
FRONTEND_DIR="$PROJECT_ROOT/kms-portal-ui"
LOG_DIR="$PROJECT_ROOT/logs"
VENV_PYTHON="$PROJECT_ROOT/venv/bin/python"
FRONTEND_PORT=3000
BACKEND_PORT=9000

# Environment variables for backend
export CORS_ORIGINS='["http://localhost:3000","http://localhost:8501"]'

# Load nvm for Node.js version management
export NVM_DIR="$HOME/.nvm"
[ -s "$NVM_DIR/nvm.sh" ] && \. "$NVM_DIR/nvm.sh"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Ensure log directory exists
mkdir -p "$LOG_DIR"

get_date_stamp() {
    date +"%Y%m%d"
}

get_frontend_log() {
    echo "$LOG_DIR/frontend_$(get_date_stamp).log"
}

get_backend_log() {
    echo "$LOG_DIR/backend_$(get_date_stamp).log"
}

print_status() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

log_message() {
    local log_file=$1
    local message=$2
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $message" >> "$log_file"
}

get_pid_by_port() {
    local port=$1
    # Try multiple methods to find PID by port
    if command -v lsof &>/dev/null; then
        lsof -ti:$port 2>/dev/null
    elif command -v ss &>/dev/null; then
        ss -tlnp 2>/dev/null | grep ":$port " | grep -oP 'pid=\K[0-9]+' | head -1
    elif command -v netstat &>/dev/null; then
        netstat -tlnp 2>/dev/null | grep ":$port " | awk '{print $7}' | cut -d'/' -f1 | head -1
    else
        # Fallback: search process list
        ps aux 2>/dev/null | grep -E "(node.*$port|python.*$port)" | grep -v grep | awk '{print $2}' | head -1
    fi
}

kill_process_by_port() {
    local port=$1
    local pid=$(get_pid_by_port $port)

    if [ -n "$pid" ]; then
        print_status "Killing process on port $port (PID: $pid)"
        kill -9 $pid 2>/dev/null
        sleep 1
        return 0
    else
        # Try to find and kill by process name
        pkill -f "app.api.main.*$port" 2>/dev/null
        pkill -f "vite.*$port" 2>/dev/null
        print_warning "No process found on port $port"
        return 1
    fi
}

wait_for_port() {
    local port=$1
    local timeout=${2:-30}
    local elapsed=0

    while [ $elapsed -lt $timeout ]; do
        local pid=$(get_pid_by_port $port)
        if [ -n "$pid" ]; then
            echo "$pid"
            return 0
        fi
        sleep 2
        elapsed=$((elapsed + 2))
        echo -ne "." >&2
    done
    return 1
}

start_frontend() {
    local pid=$(get_pid_by_port $FRONTEND_PORT)
    if [ -n "$pid" ]; then
        print_warning "Frontend already running on port $FRONTEND_PORT (PID: $pid)"
        return 1
    fi

    local log_file=$(get_frontend_log)
    print_status "Starting frontend on port $FRONTEND_PORT..."
    print_status "Log file: $log_file"

    log_message "$log_file" "========== Frontend Server Starting =========="

    cd "$FRONTEND_DIR"
    nohup npm run dev -- --port $FRONTEND_PORT >> "$log_file" 2>&1 &

    print_status "Waiting for frontend to start (timeout: 30s)..."
    pid=$(wait_for_port $FRONTEND_PORT 30)
    echo ""  # newline after dots

    if [ -n "$pid" ]; then
        print_status "Frontend started successfully (PID: $pid)"
        print_status "URL: https://localhost:$FRONTEND_PORT"
        log_message "$log_file" "Frontend started successfully (PID: $pid)"
    else
        print_error "Failed to start frontend (timeout)"
        log_message "$log_file" "ERROR: Failed to start frontend (timeout after 30s)"
        return 1
    fi
}

stop_frontend() {
    local log_file=$(get_frontend_log)
    print_status "Stopping frontend on port $FRONTEND_PORT..."
    log_message "$log_file" "========== Frontend Server Stopping =========="
    kill_process_by_port $FRONTEND_PORT
    log_message "$log_file" "Frontend stopped"
}

start_backend() {
    local pid=$(get_pid_by_port $BACKEND_PORT)
    if [ -n "$pid" ]; then
        print_warning "Backend already running on port $BACKEND_PORT (PID: $pid)"
        return 1
    fi

    local log_file=$(get_backend_log)
    print_status "Starting backend on port $BACKEND_PORT..."
    print_status "Log file: $log_file"

    log_message "$log_file" "========== Backend Server Starting =========="

    cd "$PROJECT_ROOT"
    nohup "$VENV_PYTHON" -m app.api.main --mode develop --port $BACKEND_PORT >> "$log_file" 2>&1 &

    print_status "Waiting for backend to start (timeout: 30s)..."
    pid=$(wait_for_port $BACKEND_PORT 30)
    echo ""  # newline after dots

    if [ -n "$pid" ]; then
        print_status "Backend started successfully (PID: $pid)"
        print_status "URL: http://localhost:$BACKEND_PORT"
        print_status "Docs: http://localhost:$BACKEND_PORT/docs"
        log_message "$log_file" "Backend started successfully (PID: $pid)"
    else
        print_error "Failed to start backend (timeout)"
        log_message "$log_file" "ERROR: Failed to start backend (timeout after 30s)"
        return 1
    fi
}

stop_backend() {
    local log_file=$(get_backend_log)
    print_status "Stopping backend on port $BACKEND_PORT..."
    log_message "$log_file" "========== Backend Server Stopping =========="
    kill_process_by_port $BACKEND_PORT
    log_message "$log_file" "Backend stopped"
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
    echo "=== Log Files ==="
    echo "Frontend: $(get_frontend_log)"
    echo "Backend:  $(get_backend_log)"
    echo ""
}

show_logs() {
    local target=$1
    local lines=${2:-50}

    case "$target" in
        frontend)
            local log_file=$(get_frontend_log)
            if [ -f "$log_file" ]; then
                print_status "Showing last $lines lines of $log_file"
                tail -n $lines "$log_file"
            else
                print_warning "Log file not found: $log_file"
            fi
            ;;
        backend)
            local log_file=$(get_backend_log)
            if [ -f "$log_file" ]; then
                print_status "Showing last $lines lines of $log_file"
                tail -n $lines "$log_file"
            else
                print_warning "Log file not found: $log_file"
            fi
            ;;
        *)
            print_error "Invalid target for logs: $target"
            ;;
    esac
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
    echo "  logs [N]    - Show last N lines of log (default: 50)"
    echo ""
    echo "Log files are saved to: $LOG_DIR"
    echo "  - frontend_YYYYMMDD.log"
    echo "  - backend_YYYYMMDD.log"
    echo ""
    echo "Examples:"
    echo "  $0 frontend start     # Start frontend only"
    echo "  $0 backend restart    # Restart backend only"
    echo "  $0 all stop           # Stop all servers"
    echo "  $0 status             # Show status of all servers"
    echo "  $0 frontend logs 100  # Show last 100 lines of frontend log"
}

# Main logic
TARGET=${1:-""}
ACTION=${2:-""}
EXTRA=${3:-""}

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
            logs)    show_logs frontend ${EXTRA:-50} ;;
            *)       show_usage; exit 1 ;;
        esac
        ;;
    backend)
        case "$ACTION" in
            start)   start_backend ;;
            stop)    stop_backend ;;
            restart) stop_backend && sleep 2 && start_backend ;;
            status)  show_status ;;
            logs)    show_logs backend ${EXTRA:-50} ;;
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

if [ "$ACTION" != "logs" ]; then
    show_status
fi
