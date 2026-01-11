# Server Management Script for KMS Portal
# Usage: .\server.ps1 [frontend|backend|all] [start|stop|restart|status]

param(
    [Parameter(Position=0)]
    [ValidateSet("frontend", "backend", "all", "status")]
    [string]$Target = "",

    [Parameter(Position=1)]
    [ValidateSet("start", "stop", "restart", "status", "")]
    [string]$Action = ""
)

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Split-Path -Parent $ScriptDir
$FrontendDir = Join-Path $ProjectRoot "kms-portal-ui"
$FrontendPort = 3000
$BackendPort = 9000

function Write-Status {
    param([string]$Message)
    Write-Host "[INFO] $Message" -ForegroundColor Green
}

function Write-Warn {
    param([string]$Message)
    Write-Host "[WARN] $Message" -ForegroundColor Yellow
}

function Write-Err {
    param([string]$Message)
    Write-Host "[ERROR] $Message" -ForegroundColor Red
}

function Get-PidByPort {
    param([int]$Port)
    $result = netstat -ano | Select-String ":$Port" | Select-String "LISTENING"
    if ($result) {
        $line = $result[0].ToString().Trim()
        $parts = $line -split '\s+'
        return $parts[-1]
    }
    return $null
}

function Stop-ProcessByPort {
    param([int]$Port)
    $pid = Get-PidByPort -Port $Port
    if ($pid) {
        Write-Status "Killing process on port $Port (PID: $pid)"
        try {
            Stop-Process -Id $pid -Force -ErrorAction Stop
            Start-Sleep -Seconds 1
            return $true
        } catch {
            Write-Err "Failed to kill process: $_"
            return $false
        }
    } else {
        Write-Warn "No process found on port $Port"
        return $false
    }
}

function Start-Frontend {
    $pid = Get-PidByPort -Port $FrontendPort
    if ($pid) {
        Write-Warn "Frontend already running on port $FrontendPort (PID: $pid)"
        return
    }

    Write-Status "Starting frontend on port $FrontendPort..."
    Push-Location $FrontendDir
    Start-Process -FilePath "cmd.exe" -ArgumentList "/c", "npm run dev -- --port $FrontendPort" -WindowStyle Normal
    Pop-Location

    Start-Sleep -Seconds 3
    $pid = Get-PidByPort -Port $FrontendPort
    if ($pid) {
        Write-Status "Frontend started successfully (PID: $pid)"
        Write-Status "URL: http://localhost:$FrontendPort"
    } else {
        Write-Err "Failed to start frontend"
    }
}

function Stop-Frontend {
    Write-Status "Stopping frontend on port $FrontendPort..."
    Stop-ProcessByPort -Port $FrontendPort
}

function Start-Backend {
    $pid = Get-PidByPort -Port $BackendPort
    if ($pid) {
        Write-Warn "Backend already running on port $BackendPort (PID: $pid)"
        return
    }

    Write-Status "Starting backend on port $BackendPort..."
    Push-Location $ProjectRoot
    Start-Process -FilePath "cmd.exe" -ArgumentList "/c", "python -m app.api.main --mode develop --port $BackendPort" -WindowStyle Normal
    Pop-Location

    Start-Sleep -Seconds 5
    $pid = Get-PidByPort -Port $BackendPort
    if ($pid) {
        Write-Status "Backend started successfully (PID: $pid)"
        Write-Status "URL: http://localhost:$BackendPort"
        Write-Status "Docs: http://localhost:$BackendPort/docs"
    } else {
        Write-Err "Failed to start backend"
    }
}

function Stop-Backend {
    Write-Status "Stopping backend on port $BackendPort..."
    Stop-ProcessByPort -Port $BackendPort
}

function Show-Status {
    Write-Host ""
    Write-Host "=== Server Status ===" -ForegroundColor Cyan

    $frontendPid = Get-PidByPort -Port $FrontendPort
    if ($frontendPid) {
        Write-Host "Frontend (port $FrontendPort): " -NoNewline
        Write-Host "Running" -ForegroundColor Green -NoNewline
        Write-Host " (PID: $frontendPid)"
    } else {
        Write-Host "Frontend (port $FrontendPort): " -NoNewline
        Write-Host "Stopped" -ForegroundColor Red
    }

    $backendPid = Get-PidByPort -Port $BackendPort
    if ($backendPid) {
        Write-Host "Backend  (port $BackendPort): " -NoNewline
        Write-Host "Running" -ForegroundColor Green -NoNewline
        Write-Host " (PID: $backendPid)"
    } else {
        Write-Host "Backend  (port $BackendPort): " -NoNewline
        Write-Host "Stopped" -ForegroundColor Red
    }
    Write-Host ""
}

function Show-Usage {
    Write-Host "Usage: .\server.ps1 [target] [action]"
    Write-Host ""
    Write-Host "Targets:"
    Write-Host "  frontend    - Frontend server (port $FrontendPort)"
    Write-Host "  backend     - Backend API server (port $BackendPort)"
    Write-Host "  all         - Both frontend and backend"
    Write-Host ""
    Write-Host "Actions:"
    Write-Host "  start       - Start server(s)"
    Write-Host "  stop        - Stop server(s)"
    Write-Host "  restart     - Restart server(s)"
    Write-Host "  status      - Show server status"
    Write-Host ""
    Write-Host "Examples:"
    Write-Host "  .\server.ps1 frontend start     # Start frontend only"
    Write-Host "  .\server.ps1 backend restart    # Restart backend only"
    Write-Host "  .\server.ps1 all stop           # Stop all servers"
    Write-Host "  .\server.ps1 status             # Show status of all servers"
}

# Handle status command without action
if ($Target -eq "status") {
    Show-Status
    exit 0
}

if (-not $Target -or -not $Action) {
    Show-Usage
    exit 1
}

switch ($Target) {
    "frontend" {
        switch ($Action) {
            "start" { Start-Frontend }
            "stop" { Stop-Frontend }
            "restart" {
                Stop-Frontend
                Start-Sleep -Seconds 2
                Start-Frontend
            }
            "status" { Show-Status }
        }
    }
    "backend" {
        switch ($Action) {
            "start" { Start-Backend }
            "stop" { Stop-Backend }
            "restart" {
                Stop-Backend
                Start-Sleep -Seconds 2
                Start-Backend
            }
            "status" { Show-Status }
        }
    }
    "all" {
        switch ($Action) {
            "start" {
                Start-Backend
                Start-Frontend
            }
            "stop" {
                Stop-Frontend
                Stop-Backend
            }
            "restart" {
                Stop-Frontend
                Stop-Backend
                Start-Sleep -Seconds 2
                Start-Backend
                Start-Frontend
            }
            "status" { Show-Status }
        }
    }
}

Show-Status
