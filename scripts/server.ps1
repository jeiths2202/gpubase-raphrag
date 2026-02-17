# Server Management Script for KMS Portal (Production-Grade)
# Usage: .\server.ps1 [frontend|backend|all] [start|stop|restart|status|logs] [options]
#
# Features:
# - Health Check based startup detection
# - Graceful shutdown with configurable timeout
# - Automatic retry on startup failure
# - Environment variable validation
# - Process resource monitoring (CPU/Memory)
#
# Version: 2.0.0

param(
    [Parameter(Position=0)]
    [ValidateSet("frontend", "backend", "all", "status")]
    [string]$Target = "",

    [Parameter(Position=1)]
    [ValidateSet("start", "stop", "restart", "status", "logs", "")]
    [string]$Action = "",

    [Parameter(Position=2)]
    [int]$Lines = 50,

    # Health Check timeout in seconds (default 600s to allow synchronous PDF preloading)
    [Parameter()]
    [int]$Timeout = 600,

    # Maximum retry attempts
    [Parameter()]
    [int]$MaxRetries = 3,

    # Skip environment variable validation
    [Parameter()]
    [switch]$SkipEnvCheck,

    # Graceful shutdown timeout
    [Parameter()]
    [int]$GracePeriod = 10
)

# ============================================================
# Configuration
# ============================================================

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Split-Path -Parent $ScriptDir
$FrontendDir = Join-Path $ProjectRoot "kms-portal-ui"
$LogDir = Join-Path $ProjectRoot "logs"
$PidDir = Join-Path $LogDir ".pids"
$FrontendPort = 3000
$BackendPort = 9000

# Health Check URLs (use 127.0.0.1 to avoid IPv6 localhost resolution issues)
$BackendHealthUrl = "http://127.0.0.1:$BackendPort/api/v1/health"
$FrontendHealthUrl = "https://127.0.0.1:$FrontendPort"

# Ensure TLS 1.2+ and ignore self-signed certs for health checks
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12 -bor [Net.SecurityProtocolType]::Tls13
if (-not ([System.Management.Automation.PSTypeName]'TrustAllCertsPolicy').Type) {
    Add-Type @"
using System.Net;
using System.Net.Security;
using System.Security.Cryptography.X509Certificates;
public class TrustAllCertsPolicy : ICertificatePolicy {
    public bool CheckValidationResult(ServicePoint sp, X509Certificate cert, WebRequest req, int problem) { return true; }
}
"@
}
[System.Net.ServicePointManager]::CertificatePolicy = New-Object TrustAllCertsPolicy

# Health Check settings
$HealthCheckInterval = 2

# Required environment variables for backend
$RequiredEnvVars = @(
    @{ Name = "JWT_SECRET_KEY"; MinLength = 32; Description = "JWT signing key" },
    @{ Name = "ENCRYPTION_MASTER_KEY"; MinLength = 32; Description = "Encryption key" },
    @{ Name = "NEO4J_PASSWORD"; MinLength = 1; Description = "Neo4j password" }
)

# Ensure directories exist
if (-not (Test-Path $LogDir)) {
    New-Item -ItemType Directory -Path $LogDir -Force | Out-Null
}
if (-not (Test-Path $PidDir)) {
    New-Item -ItemType Directory -Path $PidDir -Force | Out-Null
}

# ============================================================
# Utility Functions
# ============================================================

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
    $logEntry = "[$timestamp] $Message"

    $maxRetries = 3
    for ($i = 0; $i -lt $maxRetries; $i++) {
        try {
            $stream = [System.IO.File]::Open($LogFile, [System.IO.FileMode]::Append, [System.IO.FileAccess]::Write, [System.IO.FileShare]::ReadWrite)
            $writer = New-Object System.IO.StreamWriter($stream)
            $writer.WriteLine($logEntry)
            $writer.Close()
            $stream.Close()
            return
        } catch {
            if ($i -lt ($maxRetries - 1)) {
                Start-Sleep -Milliseconds 100
            }
        }
    }
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

function Write-Progress {
    param([string]$Message)
    Write-Host "`r[INFO] $Message" -NoNewline -ForegroundColor Cyan
}

# ============================================================
# PID Management Functions
# ============================================================

function Get-PidFile {
    param([string]$Service)
    return Join-Path $PidDir "$Service.pid"
}

function Save-Pid {
    param(
        [string]$Service,
        [int]$ProcessId
    )
    $ProcessId | Out-File -FilePath (Get-PidFile -Service $Service) -NoNewline -Force
}

function Get-SavedPid {
    param([string]$Service)
    $pidFile = Get-PidFile -Service $Service
    if (Test-Path $pidFile) {
        $pidContent = Get-Content $pidFile -Raw -ErrorAction SilentlyContinue
        if ($pidContent -match '^\d+$') {
            return [int]$pidContent.Trim()
        }
    }
    return $null
}

function Remove-PidFile {
    param([string]$Service)
    $pidFile = Get-PidFile -Service $Service
    if (Test-Path $pidFile) {
        Remove-Item $pidFile -Force -ErrorAction SilentlyContinue
    }
}

function Get-PidByPort {
    param([int]$Port)
    $result = netstat -ano 2>$null | Select-String ":$Port\s" | Select-String "LISTENING"
    if ($result) {
        $line = $result[0].ToString().Trim()
        $parts = $line -split '\s+'
        return $parts[-1]
    }
    return $null
}

# ============================================================
# Health Check Functions
# ============================================================

function Test-PortOpen {
    param(
        [int]$Port,
        [int]$TimeoutMs = 1000
    )
    try {
        $tcpClient = New-Object System.Net.Sockets.TcpClient
        $asyncResult = $tcpClient.BeginConnect("localhost", $Port, $null, $null)
        $waitResult = $asyncResult.AsyncWaitHandle.WaitOne($TimeoutMs, $false)
        if ($waitResult) {
            try { $tcpClient.EndConnect($asyncResult) } catch { }
            $tcpClient.Close()
            return $true
        }
        $tcpClient.Close()
        return $false
    } catch {
        return $false
    }
}

function Wait-ForHealthy {
    param(
        [string]$Url,
        [int]$TimeoutSeconds = 60,
        [int]$IntervalSeconds = 2,
        [switch]$CheckApiHealth
    )

    $stopwatch = [System.Diagnostics.Stopwatch]::StartNew()
    $lastError = ""

    while ($stopwatch.Elapsed.TotalSeconds -lt $TimeoutSeconds) {
        try {
            # Use Invoke-WebRequest (more reliable on Windows than HttpWebRequest)
            $response = $null
            $responseBody = ""
            $statusCode = 0

            try {
                $response = Invoke-WebRequest -Uri $Url -Method GET -TimeoutSec 10 -UseBasicParsing -ErrorAction Stop
                $statusCode = [int]$response.StatusCode
                $responseBody = $response.Content
            } catch [System.Net.WebException] {
                # Invoke-WebRequest throws on non-2xx (e.g. 503 degraded)
                # Response body is in ErrorDetails.Message
                if ($_.ErrorDetails -and $_.ErrorDetails.Message) {
                    $responseBody = $_.ErrorDetails.Message
                    $statusCode = [int]$_.Exception.Response.StatusCode
                } elseif ($_.Exception.Response) {
                    $statusCode = [int]$_.Exception.Response.StatusCode
                    $responseBody = ""
                } else {
                    throw
                }
            }

            # Accept both 200 (healthy) and 503 (degraded) as valid responses
            if ($statusCode -eq 200 -or $statusCode -eq 503) {
                if ($CheckApiHealth) {
                    $json = $responseBody | ConvertFrom-Json
                    # API service healthy is sufficient (external LLM services may be unavailable)
                    if ($json.services -and $json.services.api -and $json.services.api.status -eq "healthy") {
                        Write-Host ""
                        $statusMsg = if ($statusCode -eq 503) { " (degraded - some LLM services unavailable)" } else { "" }
                        Write-Status "Backend API is healthy$statusMsg"
                        return @{ Success = $true; ElapsedSeconds = [math]::Round($stopwatch.Elapsed.TotalSeconds, 1); Degraded = ($statusCode -eq 503) }
                    }
                } else {
                    Write-Host ""
                    return @{ Success = $true; ElapsedSeconds = [math]::Round($stopwatch.Elapsed.TotalSeconds, 1) }
                }
            }
        } catch {
            $lastError = $_.Exception.Message
        }

        $elapsed = [math]::Round($stopwatch.Elapsed.TotalSeconds, 0)
        Write-Progress "Waiting for service... ($elapsed/$TimeoutSeconds sec)"
        Start-Sleep -Seconds $IntervalSeconds
    }

    Write-Host ""
    return @{ Success = $false; ElapsedSeconds = $TimeoutSeconds; Error = $lastError }
}

function Get-ProcessInfo {
    param([int]$ProcessId)
    try {
        $proc = Get-Process -Id $ProcessId -ErrorAction Stop
        return @{
            CPU = [math]::Round($proc.CPU, 2)
            MemoryMB = [math]::Round($proc.WorkingSet64 / 1MB, 1)
            StartTime = $proc.StartTime
            Running = (-not $proc.HasExited)
        }
    } catch {
        return $null
    }
}

# ============================================================
# Validation Functions
# ============================================================

function Test-RequiredEnvVars {
    $envFile = Join-Path $ProjectRoot ".env"

    if (-not (Test-Path $envFile)) {
        Write-Err ".env file not found: $envFile"
        Write-Err "Please copy .env.local or .env.docker to .env"
        return $false
    }

    $envContent = Get-Content $envFile -ErrorAction SilentlyContinue
    $errors = @()

    foreach ($var in $RequiredEnvVars) {
        $line = $envContent | Where-Object { $_ -match "^$($var.Name)=" }
        if (-not $line) {
            $errors += "Missing: $($var.Name) - $($var.Description)"
        } else {
            $value = ($line -split "=", 2)[1].Trim().Trim('"').Trim("'")
            if ($value.Length -lt $var.MinLength) {
                $errors += "Too short: $($var.Name) (need $($var.MinLength)+ chars, got $($value.Length))"
            }
        }
    }

    if ($errors.Count -gt 0) {
        Write-Err "Environment validation failed:"
        $errors | ForEach-Object { Write-Err "  - $_" }
        return $false
    }

    return $true
}

function Initialize-LogRotation {
    param([int]$RetainDays = 7)

    $cutoffDate = (Get-Date).AddDays(-$RetainDays)
    $oldLogs = Get-ChildItem -Path $LogDir -Filter "*.log" -ErrorAction SilentlyContinue | Where-Object {
        $_.LastWriteTime -lt $cutoffDate
    }

    if ($oldLogs -and $oldLogs.Count -gt 0) {
        Write-Status "Cleaning up $($oldLogs.Count) old log files (older than $RetainDays days)..."
        $oldLogs | Remove-Item -Force -ErrorAction SilentlyContinue
    }
}

# ============================================================
# Graceful Shutdown Function
# ============================================================

function Stop-Gracefully {
    param(
        [int]$ProcessId,
        [int]$GracePeriodSeconds = 10,
        [string]$ServiceName = "Process"
    )

    try {
        $proc = Get-Process -Id $ProcessId -ErrorAction Stop
    } catch {
        Write-Warn "$ServiceName (PID: $ProcessId) is not running"
        return $true
    }

    Write-Status "Stopping $ServiceName (PID: $ProcessId) gracefully..."

    # Step 1: Try to close gracefully
    try {
        $closed = $proc.CloseMainWindow()
        if ($closed) {
            Write-Status "Sent close signal to $ServiceName"
        }
    } catch { }

    # Step 2: Wait for graceful exit
    $waited = 0
    while ($waited -lt $GracePeriodSeconds) {
        try {
            $proc.Refresh()
            if ($proc.HasExited) {
                Write-Status "$ServiceName exited gracefully"
                return $true
            }
        } catch {
            # Process no longer exists
            Write-Status "$ServiceName exited gracefully"
            return $true
        }
        Start-Sleep -Seconds 1
        $waited++
        Write-Progress "Waiting for graceful exit... ($waited/$GracePeriodSeconds sec)"
    }
    Write-Host ""

    # Step 3: Force kill if still running
    try {
        $proc.Refresh()
        if (-not $proc.HasExited) {
            Write-Warn "Graceful shutdown timeout, forcing termination..."
            Stop-Process -Id $ProcessId -Force -ErrorAction Stop
            Start-Sleep -Milliseconds 500
            Write-Status "$ServiceName terminated forcefully"
        }
    } catch {
        Write-Status "$ServiceName terminated"
    }

    return $true
}

# ============================================================
# Server Control Functions
# ============================================================

function Start-Backend {
    param([int]$RetryCount = 0)

    # Check if already running
    $existingPid = Get-PidByPort -Port $BackendPort
    if ($existingPid) {
        Write-Warn "Backend already running on port $BackendPort (PID: $existingPid)"
        return $true
    }

    # Validate environment (unless skipped)
    if (-not $SkipEnvCheck) {
        if (-not (Test-RequiredEnvVars)) {
            Write-Err "Environment validation failed. Use -SkipEnvCheck to bypass."
            return $false
        }
    }

    $logFile = Get-BackendLog
    $attempt = $RetryCount + 1

    Write-Status "Starting backend on port $BackendPort (attempt $attempt/$MaxRetries)..."
    Write-Status "Log file: $logFile"
    Write-LogMessage -LogFile $logFile -Message "========== Backend Server Starting (attempt $attempt) =========="

    # Read APP_MODE from .env
    $appMode = "develop"
    $envFile = Join-Path $ProjectRoot ".env"
    if (Test-Path $envFile) {
        $modeMatch = Get-Content $envFile | Where-Object { $_ -match "^APP_MODE=" }
        if ($modeMatch) {
            $appMode = ($modeMatch -split "=", 2)[1].Trim().Trim('"').Trim("'")
        }
    }

    # Start Python process directly (not via cmd.exe)
    Push-Location $ProjectRoot
    try {
        $env:PYTHONIOENCODING = "utf-8"

        # Use Start-Process with direct python execution
        $proc = Start-Process -FilePath "python" `
            -ArgumentList "-u", "-m", "app.api.main", "--mode", $appMode, "--port", $BackendPort `
            -NoNewWindow -PassThru `
            -RedirectStandardOutput $logFile `
            -RedirectStandardError (Join-Path $LogDir "backend_$(Get-DateStamp)_error.log")

        if ($proc -and $proc.Id) {
            Save-Pid -Service "backend" -ProcessId $proc.Id
            Write-Status "Backend process started (PID: $($proc.Id))"
        } else {
            Write-Err "Failed to start backend process"
            Pop-Location
            return $false
        }
    } catch {
        Write-Err "Error starting backend: $_"
        Pop-Location
        return $false
    }
    Pop-Location

    # Wait for health check
    Write-Status "Waiting for backend to become healthy (timeout: $Timeout sec)..."
    $healthResult = Wait-ForHealthy -Url $BackendHealthUrl -TimeoutSeconds $Timeout -CheckApiHealth

    if ($healthResult.Success) {
        Write-Status "Backend started successfully in $($healthResult.ElapsedSeconds) seconds"
        Write-Status "URL: http://localhost:$BackendPort"
        Write-Status "Docs: http://localhost:$BackendPort/docs"
        Write-LogMessage -LogFile $logFile -Message "Backend healthy after $($healthResult.ElapsedSeconds)s"
        return $true
    } else {
        Write-Err "Backend health check failed after $Timeout seconds"
        if ($healthResult.Error) {
            Write-Err "Last error: $($healthResult.Error)"
        }
        Write-LogMessage -LogFile $logFile -Message "ERROR: Health check failed - $($healthResult.Error)"

        # Retry logic
        if ($RetryCount -lt ($MaxRetries - 1)) {
            Write-Warn "Retrying... ($($RetryCount + 2)/$MaxRetries)"

            # Cleanup failed process
            $savedPid = Get-SavedPid -Service "backend"
            if ($savedPid) {
                Stop-Gracefully -ProcessId $savedPid -ServiceName "Backend" -GracePeriodSeconds 5 | Out-Null
            }
            Remove-PidFile -Service "backend"
            Start-Sleep -Seconds 3

            return Start-Backend -RetryCount ($RetryCount + 1)
        }

        return $false
    }
}

function Stop-Backend {
    $logFile = Get-BackendLog
    Write-LogMessage -LogFile $logFile -Message "========== Backend Server Stopping =========="

    # Try saved PID first, then port-based detection
    $savedPid = Get-SavedPid -Service "backend"
    $portPid = Get-PidByPort -Port $BackendPort

    $targetPid = $null
    if ($savedPid) {
        $info = Get-ProcessInfo -ProcessId $savedPid
        if ($info -and $info.Running) {
            $targetPid = $savedPid
        }
    }
    if (-not $targetPid -and $portPid) {
        $targetPid = [int]$portPid
    }

    if ($targetPid) {
        $result = Stop-Gracefully -ProcessId $targetPid -ServiceName "Backend" -GracePeriodSeconds $GracePeriod
        Remove-PidFile -Service "backend"
        Write-LogMessage -LogFile $logFile -Message "Backend stopped (graceful: $result)"
        return $result
    } else {
        Write-Warn "No backend process found"
        Remove-PidFile -Service "backend"
        return $true
    }
}

function Start-Frontend {
    param([int]$RetryCount = 0)

    # Check if already running
    $existingPid = Get-PidByPort -Port $FrontendPort
    if ($existingPid) {
        Write-Warn "Frontend already running on port $FrontendPort (PID: $existingPid)"
        return $true
    }

    $logFile = Get-FrontendLog
    $attempt = $RetryCount + 1

    Write-Status "Starting frontend on port $FrontendPort (attempt $attempt/$MaxRetries)..."
    Write-Status "Log file: $logFile"
    Write-LogMessage -LogFile $logFile -Message "========== Frontend Server Starting (attempt $attempt) =========="

    # Start npm process via cmd.exe (npm is a batch file, not an executable)
    Push-Location $FrontendDir
    try {
        $errorLog = Join-Path $LogDir "frontend_$(Get-DateStamp)_error.log"
        $cmdArgs = "/c npm run dev -- --port $FrontendPort > `"$logFile`" 2> `"$errorLog`""

        $proc = Start-Process -FilePath "cmd.exe" `
            -ArgumentList $cmdArgs `
            -NoNewWindow -PassThru `
            -WorkingDirectory $FrontendDir

        if ($proc -and $proc.Id) {
            # Give npm a moment to spawn the actual node process
            Start-Sleep -Seconds 2

            # Find the node process that's actually listening on the port
            Save-Pid -Service "frontend" -ProcessId $proc.Id
            Write-Status "Frontend process started (PID: $($proc.Id))"
        } else {
            Write-Err "Failed to start frontend process"
            Pop-Location
            return $false
        }
    } catch {
        Write-Err "Error starting frontend: $_"
        Pop-Location
        return $false
    }
    Pop-Location

    # Wait for port to open (frontend doesn't have health endpoint like backend)
    Write-Status "Waiting for frontend to become available (timeout: 30 sec)..."
    $frontendTimeout = [math]::Min($Timeout, 30)
    $healthResult = Wait-ForHealthy -Url $FrontendHealthUrl -TimeoutSeconds $frontendTimeout

    if ($healthResult.Success) {
        Write-Status "Frontend started successfully in $($healthResult.ElapsedSeconds) seconds"
        Write-Status "URL: http://localhost:$FrontendPort"
        Write-LogMessage -LogFile $logFile -Message "Frontend ready after $($healthResult.ElapsedSeconds)s"
        return $true
    } else {
        # For frontend, check if port is at least open
        if (Test-PortOpen -Port $FrontendPort) {
            Write-Status "Frontend port is open (may still be initializing)"
            Write-Status "URL: http://localhost:$FrontendPort"
            return $true
        }

        Write-Err "Frontend startup failed after $frontendTimeout seconds"
        Write-LogMessage -LogFile $logFile -Message "ERROR: Startup failed"

        # Retry logic
        if ($RetryCount -lt ($MaxRetries - 1)) {
            Write-Warn "Retrying... ($($RetryCount + 2)/$MaxRetries)"
            $savedPid = Get-SavedPid -Service "frontend"
            if ($savedPid) {
                Stop-Gracefully -ProcessId $savedPid -ServiceName "Frontend" -GracePeriodSeconds 5 | Out-Null
            }
            Remove-PidFile -Service "frontend"
            Start-Sleep -Seconds 2
            return Start-Frontend -RetryCount ($RetryCount + 1)
        }

        return $false
    }
}

function Stop-Frontend {
    $logFile = Get-FrontendLog
    Write-LogMessage -LogFile $logFile -Message "========== Frontend Server Stopping =========="

    $savedPid = Get-SavedPid -Service "frontend"
    $portPid = Get-PidByPort -Port $FrontendPort

    $targetPid = $null
    if ($savedPid) {
        $info = Get-ProcessInfo -ProcessId $savedPid
        if ($info -and $info.Running) {
            $targetPid = $savedPid
        }
    }
    if (-not $targetPid -and $portPid) {
        $targetPid = [int]$portPid
    }

    if ($targetPid) {
        $result = Stop-Gracefully -ProcessId $targetPid -ServiceName "Frontend" -GracePeriodSeconds $GracePeriod
        Remove-PidFile -Service "frontend"
        Write-LogMessage -LogFile $logFile -Message "Frontend stopped (graceful: $result)"
        return $result
    } else {
        Write-Warn "No frontend process found"
        Remove-PidFile -Service "frontend"
        return $true
    }
}

# ============================================================
# Display Functions
# ============================================================

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

    # Frontend status
    $frontendPid = Get-PidByPort -Port $FrontendPort
    Write-Host "Frontend (port $FrontendPort): " -NoNewline
    if ($frontendPid) {
        Write-Host "Running" -ForegroundColor Green -NoNewline
        Write-Host " (PID: $frontendPid)" -NoNewline
        $info = Get-ProcessInfo -ProcessId $frontendPid
        if ($info) {
            Write-Host " | CPU: $($info.CPU)s | Mem: $($info.MemoryMB)MB" -ForegroundColor DarkGray
        } else {
            Write-Host ""
        }
    } else {
        Write-Host "Stopped" -ForegroundColor Red
    }

    # Backend status
    $backendPid = Get-PidByPort -Port $BackendPort
    Write-Host "Backend  (port $BackendPort): " -NoNewline
    if ($backendPid) {
        Write-Host "Running" -ForegroundColor Green -NoNewline
        Write-Host " (PID: $backendPid)" -NoNewline
        $info = Get-ProcessInfo -ProcessId $backendPid
        if ($info) {
            Write-Host " | CPU: $($info.CPU)s | Mem: $($info.MemoryMB)MB" -ForegroundColor DarkGray
        } else {
            Write-Host ""
        }

        # Health check status (handle both 200 and 503 responses)
        $healthBody = ""
        $healthCode = 0

        try {
            $healthResp = Invoke-WebRequest -Uri $BackendHealthUrl -Method GET -TimeoutSec 15 -UseBasicParsing -ErrorAction Stop
            $healthCode = [int]$healthResp.StatusCode
            $healthBody = $healthResp.Content
        } catch [System.Net.WebException] {
            if ($_.ErrorDetails -and $_.ErrorDetails.Message) {
                $healthBody = $_.ErrorDetails.Message
                $healthCode = [int]$_.Exception.Response.StatusCode
            } elseif ($_.Exception.Response) {
                $healthCode = [int]$_.Exception.Response.StatusCode
                $healthBody = ""
            }
        } catch {
            $healthBody = ""
        }

        if ($healthBody) {
            try {
                $healthJson = $healthBody | ConvertFrom-Json
                $overallStatus = $healthJson.status
                $apiStatus = if ($healthJson.services -and $healthJson.services.api) { $healthJson.services.api.status } else { "unknown" }

                Write-Host "         Health: " -NoNewline
                if ($overallStatus -eq "healthy") {
                    Write-Host "Healthy" -ForegroundColor Green
                } elseif ($overallStatus -eq "degraded" -and $apiStatus -eq "healthy") {
                    Write-Host "Degraded" -ForegroundColor Yellow -NoNewline
                    Write-Host " (API OK, some LLM services unavailable)" -ForegroundColor DarkGray
                } elseif ($apiStatus -eq "unhealthy") {
                    Write-Host "Unhealthy" -ForegroundColor Red
                } else {
                    Write-Host "Unknown ($overallStatus)" -ForegroundColor DarkGray
                }
            } catch {
                Write-Host "         Health: " -NoNewline
                Write-Host "Parse Error" -ForegroundColor Red
            }
        } else {
            Write-Host "         Health: " -NoNewline
            Write-Host "Unreachable" -ForegroundColor Red
        }
    } else {
        Write-Host "Stopped" -ForegroundColor Red
    }

    Write-Host ""
    Write-Host "=== Log Files ===" -ForegroundColor Cyan
    Write-Host "Frontend: $(Get-FrontendLog)"
    Write-Host "Backend:  $(Get-BackendLog)"
    Write-Host ""
}

function Show-Usage {
    Write-Host "Server Management Script for KMS Portal (v2.0)" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "Usage: .\server.ps1 [target] [action] [options]"
    Write-Host ""
    Write-Host "Targets:" -ForegroundColor Yellow
    Write-Host "  frontend    - Frontend server (port $FrontendPort)"
    Write-Host "  backend     - Backend API server (port $BackendPort)"
    Write-Host "  all         - Both frontend and backend"
    Write-Host "  status      - Show server status (shortcut)"
    Write-Host ""
    Write-Host "Actions:" -ForegroundColor Yellow
    Write-Host "  start       - Start server(s) with health check"
    Write-Host "  stop        - Stop server(s) gracefully"
    Write-Host "  restart     - Restart server(s)"
    Write-Host "  status      - Show server status"
    Write-Host "  logs [N]    - Show last N lines of log (default: 50)"
    Write-Host ""
    Write-Host "Options:" -ForegroundColor Yellow
    Write-Host "  -Timeout N      - Health check timeout in seconds (default: 600)"
    Write-Host "  -MaxRetries N   - Max retry attempts on failure (default: 3)"
    Write-Host "  -GracePeriod N  - Graceful shutdown timeout (default: 10)"
    Write-Host "  -SkipEnvCheck   - Skip environment variable validation"
    Write-Host ""
    Write-Host "Log files: $LogDir" -ForegroundColor DarkGray
    Write-Host "  - frontend_YYYYMMDD.log"
    Write-Host "  - backend_YYYYMMDD.log"
    Write-Host ""
    Write-Host "Examples:" -ForegroundColor Yellow
    Write-Host "  .\server.ps1 backend start              # Start backend with health check"
    Write-Host "  .\server.ps1 all restart                # Restart all servers"
    Write-Host "  .\server.ps1 backend start -Timeout 120 # Extended timeout"
    Write-Host "  .\server.ps1 all start -SkipEnvCheck    # Skip env validation"
    Write-Host "  .\server.ps1 status                     # Show status"
    Write-Host "  .\server.ps1 backend logs 100           # Show last 100 log lines"
}

# ============================================================
# Main Execution
# ============================================================

# Cleanup old logs on startup
Initialize-LogRotation -RetainDays 7

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
$exitCode = 0

switch ($Target) {
    "frontend" {
        switch ($Action) {
            "start" {
                $result = Start-Frontend
                if (-not $result) { $exitCode = 1 }
            }
            "stop" {
                Stop-Frontend | Out-Null
            }
            "restart" {
                Stop-Frontend | Out-Null
                Start-Sleep -Seconds 2
                $result = Start-Frontend
                if (-not $result) { $exitCode = 1 }
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
            "start" {
                $result = Start-Backend
                if (-not $result) { $exitCode = 1 }
            }
            "stop" {
                Stop-Backend | Out-Null
            }
            "restart" {
                Stop-Backend | Out-Null
                Start-Sleep -Seconds 2
                $result = Start-Backend
                if (-not $result) { $exitCode = 1 }
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
                $backendResult = Start-Backend
                if ($backendResult) {
                    $frontendResult = Start-Frontend
                    if (-not $frontendResult) { $exitCode = 1 }
                } else {
                    $exitCode = 1
                    Write-Err "Skipping frontend start due to backend failure"
                }
            }
            "stop" {
                Stop-Frontend | Out-Null
                Stop-Backend | Out-Null
            }
            "restart" {
                Stop-Frontend | Out-Null
                Stop-Backend | Out-Null
                Start-Sleep -Seconds 2
                $backendResult = Start-Backend
                if ($backendResult) {
                    $frontendResult = Start-Frontend
                    if (-not $frontendResult) { $exitCode = 1 }
                } else {
                    $exitCode = 1
                }
            }
            "status" { Show-Status }
        }
    }
}

if ($showFinalStatus) {
    Show-Status
}

exit $exitCode
