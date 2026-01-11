# Server Management Script for KMS Portal
# Usage: .\server.ps1 [frontend|backend|all] [start|stop|restart|status|logs]

param(
    [Parameter(Position=0)]
    [ValidateSet("frontend", "backend", "all", "status")]
    [string]$Target = "",

    [Parameter(Position=1)]
    [ValidateSet("start", "stop", "restart", "status", "logs", "")]
    [string]$Action = "",

    [Parameter(Position=2)]
    [int]$Lines = 50
)

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Split-Path -Parent $ScriptDir
$FrontendDir = Join-Path $ProjectRoot "kms-portal-ui"
$LogDir = Join-Path $ProjectRoot "logs"
$FrontendPort = 3000
$BackendPort = 9000

# Ensure log directory exists
if (-not (Test-Path $LogDir)) {
    New-Item -ItemType Directory -Path $LogDir -Force | Out-Null
}

function Get-DateStamp {
    return Get-Date -Format "yyyyMMdd"
}

function Get-FrontendLog {
    return Join-Path $LogDir "frontend_$(Get-DateStamp).log"
}

function Get-BackendLog {
    return Join-Path $LogDir "backend_$(Get-DateStamp).log"
}

function Write-LogMessage {
    param(
        [string]$LogFile,
        [string]$Message
    )
    $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    Add-Content -Path $LogFile -Value "[$timestamp] $Message"
}

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
    $procId = Get-PidByPort -Port $Port
    if ($procId) {
        Write-Status "Killing process on port $Port (PID: $procId)"
        try {
            Stop-Process -Id $procId -Force -ErrorAction Stop
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
    $procId = Get-PidByPort -Port $FrontendPort
    if ($procId) {
        Write-Warn "Frontend already running on port $FrontendPort (PID: $procId)"
        return
    }

    $logFile = Get-FrontendLog
    Write-Status "Starting frontend on port $FrontendPort..."
    Write-Status "Log file: $logFile"

    Write-LogMessage -LogFile $logFile -Message "========== Frontend Server Starting =========="

    Push-Location $FrontendDir
    $command = "npm run dev -- --port $FrontendPort *>> `"$logFile`" 2>&1"
    Start-Process -FilePath "cmd.exe" -ArgumentList "/c", $command -WindowStyle Hidden
    Pop-Location

    Start-Sleep -Seconds 3
    $procId = Get-PidByPort -Port $FrontendPort
    if ($procId) {
        Write-Status "Frontend started successfully (PID: $procId)"
        Write-Status "URL: http://localhost:$FrontendPort"
        Write-LogMessage -LogFile $logFile -Message "Frontend started successfully (PID: $procId)"
    } else {
        Write-Err "Failed to start frontend"
        Write-LogMessage -LogFile $logFile -Message "ERROR: Failed to start frontend"
    }
}

function Stop-Frontend {
    $logFile = Get-FrontendLog
    Write-Status "Stopping frontend on port $FrontendPort..."
    Write-LogMessage -LogFile $logFile -Message "========== Frontend Server Stopping =========="
    Stop-ProcessByPort -Port $FrontendPort
    Write-LogMessage -LogFile $logFile -Message "Frontend stopped"
}

function Start-Backend {
    $procId = Get-PidByPort -Port $BackendPort
    if ($procId) {
        Write-Warn "Backend already running on port $BackendPort (PID: $procId)"
        return
    }

    $logFile = Get-BackendLog
    Write-Status "Starting backend on port $BackendPort..."
    Write-Status "Log file: $logFile"

    Write-LogMessage -LogFile $logFile -Message "========== Backend Server Starting =========="

    Push-Location $ProjectRoot
    $command = "python -m app.api.main --mode develop --port $BackendPort *>> `"$logFile`" 2>&1"
    Start-Process -FilePath "cmd.exe" -ArgumentList "/c", $command -WindowStyle Hidden
    Pop-Location

    Start-Sleep -Seconds 5
    $procId = Get-PidByPort -Port $BackendPort
    if ($procId) {
        Write-Status "Backend started successfully (PID: $procId)"
        Write-Status "URL: http://localhost:$BackendPort"
        Write-Status "Docs: http://localhost:$BackendPort/docs"
        Write-LogMessage -LogFile $logFile -Message "Backend started successfully (PID: $procId)"
    } else {
        Write-Err "Failed to start backend"
        Write-LogMessage -LogFile $logFile -Message "ERROR: Failed to start backend"
    }
}

function Stop-Backend {
    $logFile = Get-BackendLog
    Write-Status "Stopping backend on port $BackendPort..."
    Write-LogMessage -LogFile $logFile -Message "========== Backend Server Stopping =========="
    Stop-ProcessByPort -Port $BackendPort
    Write-LogMessage -LogFile $logFile -Message "Backend stopped"
}

function Show-Logs {
    param(
        [string]$LogTarget,
        [int]$TailLines = 50
    )

    switch ($LogTarget) {
        "frontend" {
            $logFile = Get-FrontendLog
            if (Test-Path $logFile) {
                Write-Status "Showing last $TailLines lines of $logFile"
                Get-Content $logFile -Tail $TailLines
            } else {
                Write-Warn "Log file not found: $logFile"
            }
        }
        "backend" {
            $logFile = Get-BackendLog
            if (Test-Path $logFile) {
                Write-Status "Showing last $TailLines lines of $logFile"
                Get-Content $logFile -Tail $TailLines
            } else {
                Write-Warn "Log file not found: $logFile"
            }
        }
    }
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
    Write-Host "=== Log Files ===" -ForegroundColor Cyan
    Write-Host "Frontend: $(Get-FrontendLog)"
    Write-Host "Backend:  $(Get-BackendLog)"
    Write-Host ""
}

function Show-Usage {
    Write-Host "Usage: .\server.ps1 [target] [action] [lines]"
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
    Write-Host "  logs [N]    - Show last N lines of log (default: 50)"
    Write-Host ""
    Write-Host "Log files are saved to: $LogDir"
    Write-Host "  - frontend_YYYYMMDD.log"
    Write-Host "  - backend_YYYYMMDD.log"
    Write-Host ""
    Write-Host "Examples:"
    Write-Host "  .\server.ps1 frontend start     # Start frontend only"
    Write-Host "  .\server.ps1 backend restart    # Restart backend only"
    Write-Host "  .\server.ps1 all stop           # Stop all servers"
    Write-Host "  .\server.ps1 status             # Show status of all servers"
    Write-Host "  .\server.ps1 frontend logs 100  # Show last 100 lines of frontend log"
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

$showFinalStatus = $true

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
            "logs" {
                Show-Logs -LogTarget "frontend" -TailLines $Lines
                $showFinalStatus = $false
            }
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
            "logs" {
                Show-Logs -LogTarget "backend" -TailLines $Lines
                $showFinalStatus = $false
            }
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

if ($showFinalStatus) {
    Show-Status
}
