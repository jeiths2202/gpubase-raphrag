# Design: Server Script Improvement

> scripts/server.ps1 프로덕션급 개선 상세 설계

## 1. 아키텍처 개요

### 1.1 개선 전후 비교

```
[현재 구조]
Start-Process cmd.exe /c "python ..." -WindowStyle Hidden
    ↓
cmd.exe가 /c로 실행 → 명령 완료 후 종료
    ↓
Python 프로세스 부모 없이 고아 상태 또는 함께 종료

[개선 구조]
Start-Process python -PassThru -RedirectStandardOutput $log
    ↓
Python 프로세스 직접 실행 → PID 파일에 저장
    ↓
Wait-ForHealthy로 Health Check 대기
    ↓
성공 시 상태 표시 / 실패 시 재시도 (최대 3회)
```

### 1.2 함수 구조 설계

```
scripts/server.ps1 (약 550줄)
├── Configuration Section
│   ├── Parameters (Target, Action, Lines, Timeout)
│   ├── Paths (ScriptDir, ProjectRoot, LogDir)
│   ├── Ports (Frontend: 3000, Backend: 9000)
│   └── Settings (MaxRetries: 3, GracePeriod: 10s)
│
├── Utility Functions
│   ├── Get-DateStamp                    # 일자 스탬프
│   ├── Get-FrontendLog / Get-BackendLog # 로그 경로
│   ├── Write-LogMessage                 # 파일 로깅 (기존)
│   ├── Write-Status / Warn / Err        # 콘솔 출력 (기존)
│   └── Get-PidFile                      # PID 파일 경로 (신규)
│
├── Process Management Functions (신규/수정)
│   ├── Get-PidByPort                    # netstat 기반 (기존)
│   ├── Get-SavedPid                     # PID 파일에서 읽기 (신규)
│   ├── Save-Pid                         # PID 파일에 저장 (신규)
│   ├── Stop-Gracefully                  # Graceful Shutdown (신규)
│   └── Stop-ProcessByPort               # 강제 종료 (기존, 폴백)
│
├── Health Check Functions (신규)
│   ├── Wait-ForHealthy                  # HTTP Health Check 대기
│   ├── Test-PortOpen                    # 포트 오픈 확인
│   └── Get-ProcessInfo                  # CPU/메모리 정보 (신규)
│
├── Validation Functions (신규)
│   ├── Test-RequiredEnvVars             # 환경변수 검증
│   ├── Test-Dependencies                # Python/Node 버전 확인
│   └── Initialize-LogRotation           # 오래된 로그 정리
│
├── Server Control Functions (수정)
│   ├── Start-Frontend                   # 프론트엔드 시작
│   ├── Start-Backend                    # 백엔드 시작
│   ├── Stop-Frontend                    # 프론트엔드 중지
│   ├── Stop-Backend                     # 백엔드 중지
│   ├── Start-WithRetry                  # 재시도 로직 (신규)
│   └── Show-Logs                        # 로그 출력 (기존)
│
├── Display Functions
│   ├── Show-Status                      # 상태 표시 (개선)
│   └── Show-Usage                       # 도움말 (기존)
│
└── Main Section
    └── switch ($Target) { ... }
```

## 2. 상세 설계

### 2.1 Configuration 확장

```powershell
# === 신규 파라미터 ===
param(
    [Parameter(Position=0)]
    [ValidateSet("frontend", "backend", "all", "status")]
    [string]$Target = "",

    [Parameter(Position=1)]
    [ValidateSet("start", "stop", "restart", "status", "logs", "")]
    [string]$Action = "",

    [Parameter(Position=2)]
    [int]$Lines = 50,

    # 신규: Health Check 타임아웃
    [Parameter()]
    [int]$Timeout = 60,

    # 신규: 재시도 횟수
    [Parameter()]
    [int]$MaxRetries = 3,

    # 신규: 환경변수 검증 스킵
    [Parameter()]
    [switch]$SkipEnvCheck
)

# === 신규 설정 ===
$GracePeriodSeconds = 10
$HealthCheckInterval = 2
$BackendHealthUrl = "http://localhost:$BackendPort/api/v1/health"
$FrontendHealthUrl = "http://localhost:$FrontendPort"
$PidDir = Join-Path $LogDir ".pids"
```

### 2.2 PID 관리 함수

```powershell
function Get-PidFile {
    param([string]$Service)
    return Join-Path $PidDir "$Service.pid"
}

function Save-Pid {
    param(
        [string]$Service,
        [int]$ProcessId
    )
    if (-not (Test-Path $PidDir)) {
        New-Item -ItemType Directory -Path $PidDir -Force | Out-Null
    }
    $ProcessId | Out-File -FilePath (Get-PidFile -Service $Service) -NoNewline
}

function Get-SavedPid {
    param([string]$Service)
    $pidFile = Get-PidFile -Service $Service
    if (Test-Path $pidFile) {
        $pid = Get-Content $pidFile -Raw
        if ($pid -match '^\d+$') {
            return [int]$pid
        }
    }
    return $null
}

function Remove-PidFile {
    param([string]$Service)
    $pidFile = Get-PidFile -Service $Service
    if (Test-Path $pidFile) {
        Remove-Item $pidFile -Force
    }
}
```

### 2.3 Health Check 함수

```powershell
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
            $tcpClient.EndConnect($asyncResult)
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
        [switch]$RequireHealthy  # true면 status=healthy 필요, false면 200 응답만
    )

    $stopwatch = [System.Diagnostics.Stopwatch]::StartNew()
    $lastError = ""

    while ($stopwatch.Elapsed.TotalSeconds -lt $TimeoutSeconds) {
        try {
            $response = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 5 -ErrorAction Stop
            if ($response.StatusCode -eq 200) {
                if ($RequireHealthy) {
                    $json = $response.Content | ConvertFrom-Json
                    if ($json.status -eq "healthy" -or $json.services.api.status -eq "healthy") {
                        return @{ Success = $true; ElapsedSeconds = $stopwatch.Elapsed.TotalSeconds }
                    }
                    # API는 떴지만 완전히 healthy가 아닌 경우도 성공으로 처리
                    # (Neo4j, LLM 등 외부 서비스 장애는 별개)
                    if ($json.services -and $json.services.api.status -eq "healthy") {
                        return @{ Success = $true; ElapsedSeconds = $stopwatch.Elapsed.TotalSeconds }
                    }
                } else {
                    return @{ Success = $true; ElapsedSeconds = $stopwatch.Elapsed.TotalSeconds }
                }
            }
        } catch {
            $lastError = $_.Exception.Message
        }

        # 진행 상황 표시
        $elapsed = [math]::Round($stopwatch.Elapsed.TotalSeconds, 0)
        Write-Host "`r[INFO] Waiting for service... ($elapsed/$TimeoutSeconds sec)" -NoNewline -ForegroundColor Cyan

        Start-Sleep -Seconds $IntervalSeconds
    }

    Write-Host ""  # 줄바꿈
    return @{ Success = $false; ElapsedSeconds = $TimeoutSeconds; Error = $lastError }
}
```

### 2.4 Graceful Shutdown 함수

```powershell
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

    # 1단계: WM_CLOSE 메시지 전송 시도
    $closed = $proc.CloseMainWindow()
    if ($closed) {
        Write-Status "Sent close signal to $ServiceName"
    }

    # 2단계: Grace period 동안 대기
    $waited = 0
    while (-not $proc.HasExited -and $waited -lt $GracePeriodSeconds) {
        Start-Sleep -Seconds 1
        $waited++
        Write-Host "`r[INFO] Waiting for graceful exit... ($waited/$GracePeriodSeconds sec)" -NoNewline -ForegroundColor Cyan
    }
    Write-Host ""

    # 3단계: 여전히 실행 중이면 강제 종료
    if (-not $proc.HasExited) {
        Write-Warn "Graceful shutdown timeout, forcing termination..."
        try {
            Stop-Process -Id $ProcessId -Force -ErrorAction Stop
            Start-Sleep -Milliseconds 500
            Write-Status "$ServiceName terminated forcefully"
        } catch {
            Write-Err "Failed to terminate $ServiceName : $_"
            return $false
        }
    } else {
        Write-Status "$ServiceName exited gracefully"
    }

    return $true
}
```

### 2.5 환경변수 검증 함수

```powershell
function Test-RequiredEnvVars {
    $required = @(
        @{ Name = "JWT_SECRET_KEY"; MinLength = 32; Description = "JWT signing key" },
        @{ Name = "ENCRYPTION_MASTER_KEY"; MinLength = 32; Description = "Encryption key" },
        @{ Name = "NEO4J_PASSWORD"; MinLength = 1; Description = "Neo4j password" }
    )

    $envFile = Join-Path $ProjectRoot ".env"

    if (-not (Test-Path $envFile)) {
        Write-Err ".env file not found: $envFile"
        Write-Err "Please copy .env.local or .env.docker to .env"
        return $false
    }

    $envContent = Get-Content $envFile
    $errors = @()

    foreach ($var in $required) {
        $line = $envContent | Where-Object { $_ -match "^$($var.Name)=" }
        if (-not $line) {
            $errors += "Missing: $($var.Name) - $($var.Description)"
        } else {
            $value = ($line -split "=", 2)[1].Trim()
            if ($value.Length -lt $var.MinLength) {
                $errors += "Too short: $($var.Name) (min $($var.MinLength) chars)"
            }
        }
    }

    if ($errors.Count -gt 0) {
        Write-Err "Environment validation failed:"
        $errors | ForEach-Object { Write-Err "  - $_" }
        return $false
    }

    Write-Status "Environment validation passed"
    return $true
}
```

### 2.6 Start-Backend 개선

```powershell
function Start-Backend {
    param(
        [int]$RetryCount = 0
    )

    # 이미 실행 중인지 확인
    $existingPid = Get-PidByPort -Port $BackendPort
    if ($existingPid) {
        Write-Warn "Backend already running on port $BackendPort (PID: $existingPid)"
        return $true
    }

    # 환경변수 검증 (스킵 옵션 없으면)
    if (-not $SkipEnvCheck) {
        if (-not (Test-RequiredEnvVars)) {
            Write-Err "Environment validation failed. Use -SkipEnvCheck to bypass."
            return $false
        }
    }

    $logFile = Get-BackendLog
    $errLog = Join-Path $LogDir "backend_$(Get-DateStamp)_error.log"

    Write-Status "Starting backend on port $BackendPort (attempt $($RetryCount + 1)/$MaxRetries)..."
    Write-Status "Log file: $logFile"
    Write-LogMessage -LogFile $logFile -Message "========== Backend Server Starting =========="

    # APP_MODE 읽기
    $appMode = "develop"
    $envFile = Join-Path $ProjectRoot ".env"
    if (Test-Path $envFile) {
        $modeMatch = Get-Content $envFile | Where-Object { $_ -match "^APP_MODE=" }
        if ($modeMatch) {
            $appMode = ($modeMatch -split "=")[1].Trim()
        }
    }

    # Python 프로세스 직접 시작 (cmd.exe 우회)
    Push-Location $ProjectRoot
    try {
        $env:PYTHONIOENCODING = "utf-8"

        $proc = Start-Process -FilePath "python" `
            -ArgumentList "-m", "app.api.main", "--mode", $appMode, "--port", $BackendPort `
            -NoNewWindow -PassThru `
            -RedirectStandardOutput $logFile `
            -RedirectStandardError $errLog

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

    # Health Check 대기
    Write-Status "Waiting for backend to become healthy..."
    $healthResult = Wait-ForHealthy -Url $BackendHealthUrl -TimeoutSeconds $Timeout -RequireHealthy

    if ($healthResult.Success) {
        Write-Status "Backend started successfully in $([math]::Round($healthResult.ElapsedSeconds, 1)) seconds"
        Write-Status "URL: http://localhost:$BackendPort"
        Write-Status "Docs: http://localhost:$BackendPort/docs"
        Write-LogMessage -LogFile $logFile -Message "Backend healthy after $($healthResult.ElapsedSeconds)s"
        return $true
    } else {
        Write-Err "Backend health check failed after $Timeout seconds"
        Write-LogMessage -LogFile $logFile -Message "ERROR: Health check failed - $($healthResult.Error)"

        # 재시도
        if ($RetryCount -lt ($MaxRetries - 1)) {
            Write-Warn "Retrying... ($(($RetryCount + 2))/$MaxRetries)"
            # 실패한 프로세스 정리
            $savedPid = Get-SavedPid -Service "backend"
            if ($savedPid) {
                Stop-Gracefully -ProcessId $savedPid -ServiceName "Backend" -GracePeriodSeconds 5
                Remove-PidFile -Service "backend"
            }
            Start-Sleep -Seconds 2
            return Start-Backend -RetryCount ($RetryCount + 1)
        }

        return $false
    }
}
```

### 2.7 Stop-Backend 개선

```powershell
function Stop-Backend {
    $logFile = Get-BackendLog
    Write-LogMessage -LogFile $logFile -Message "========== Backend Server Stopping =========="

    # 저장된 PID 먼저 확인
    $savedPid = Get-SavedPid -Service "backend"
    $portPid = Get-PidByPort -Port $BackendPort

    $targetPid = $null
    if ($savedPid -and (Get-Process -Id $savedPid -ErrorAction SilentlyContinue)) {
        $targetPid = $savedPid
    } elseif ($portPid) {
        $targetPid = [int]$portPid
    }

    if ($targetPid) {
        $result = Stop-Gracefully -ProcessId $targetPid -ServiceName "Backend" -GracePeriodSeconds $GracePeriodSeconds
        Remove-PidFile -Service "backend"
        Write-LogMessage -LogFile $logFile -Message "Backend stopped (graceful: $result)"
        return $result
    } else {
        Write-Warn "No backend process found"
        Remove-PidFile -Service "backend"
        return $true
    }
}
```

### 2.8 Show-Status 개선

```powershell
function Get-ProcessInfo {
    param([int]$ProcessId)
    try {
        $proc = Get-Process -Id $ProcessId -ErrorAction Stop
        $cpu = [math]::Round($proc.CPU, 2)
        $memMB = [math]::Round($proc.WorkingSet64 / 1MB, 1)
        return @{
            CPU = $cpu
            MemoryMB = $memMB
            StartTime = $proc.StartTime
        }
    } catch {
        return $null
    }
}

function Show-Status {
    Write-Host ""
    Write-Host "=== Server Status ===" -ForegroundColor Cyan

    # Frontend
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

    # Backend
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

        # Health Check 상태
        try {
            $health = Invoke-WebRequest -Uri $BackendHealthUrl -UseBasicParsing -TimeoutSec 3 -ErrorAction Stop
            $json = $health.Content | ConvertFrom-Json
            $apiStatus = $json.services.api.status
            Write-Host "         Health: " -NoNewline
            if ($apiStatus -eq "healthy") {
                Write-Host "Healthy" -ForegroundColor Green
            } else {
                Write-Host "Degraded" -ForegroundColor Yellow
            }
        } catch {
            Write-Host "         Health: " -NoNewline
            Write-Host "Unknown" -ForegroundColor DarkGray
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
```

### 2.9 로그 Rotation (P2)

```powershell
function Initialize-LogRotation {
    param([int]$RetainDays = 7)

    $cutoffDate = (Get-Date).AddDays(-$RetainDays)
    $oldLogs = Get-ChildItem -Path $LogDir -Filter "*.log" | Where-Object {
        $_.LastWriteTime -lt $cutoffDate
    }

    if ($oldLogs.Count -gt 0) {
        Write-Status "Cleaning up $($oldLogs.Count) old log files..."
        $oldLogs | Remove-Item -Force
    }
}
```

## 3. 구현 순서

| 순서 | 함수/영역 | 설명 | 예상 라인 |
|------|----------|------|----------|
| 1 | Parameters | Timeout, MaxRetries, SkipEnvCheck 추가 | +10 |
| 2 | Configuration | PidDir, HealthUrl, Settings | +10 |
| 3 | PID Management | Save-Pid, Get-SavedPid, Remove-PidFile | +30 |
| 4 | Health Check | Test-PortOpen, Wait-ForHealthy | +50 |
| 5 | Graceful Shutdown | Stop-Gracefully | +40 |
| 6 | Env Validation | Test-RequiredEnvVars | +35 |
| 7 | Start-Backend | 전면 재작성 | +60 (기존 대체) |
| 8 | Stop-Backend | Graceful 적용 | +20 (기존 대체) |
| 9 | Start-Frontend | 동일 패턴 적용 | +40 (기존 대체) |
| 10 | Stop-Frontend | Graceful 적용 | +15 (기존 대체) |
| 11 | Get-ProcessInfo | CPU/Mem 정보 | +15 |
| 12 | Show-Status | 정보 표시 개선 | +30 (기존 대체) |
| 13 | Log Rotation | Initialize-LogRotation | +15 |

**총 예상:** 기존 360줄 → 약 550줄 (+190줄)

## 4. 테스트 체크리스트

### 4.1 P0 테스트 (필수)

| # | 시나리오 | 명령어 | 기대 결과 |
|---|----------|--------|----------|
| 1 | Backend 시작 | `.\server.ps1 backend start` | Health Check 통과, PID 저장됨 |
| 2 | Backend 중지 | `.\server.ps1 backend stop` | Graceful 종료, PID 파일 삭제 |
| 3 | Backend 재시작 | `.\server.ps1 backend restart` | 중지 → 시작, 5분 유지 |
| 4 | Frontend 시작 | `.\server.ps1 frontend start` | 포트 오픈 확인 |
| 5 | 전체 시작 | `.\server.ps1 all start` | Backend → Frontend 순차 |
| 6 | 전체 중지 | `.\server.ps1 all stop` | Frontend → Backend 순차 |
| 7 | .env 누락 | .env 없이 start | 명확한 에러 메시지 |
| 8 | 상태 확인 | `.\server.ps1 status` | PID, CPU, Mem, Health 표시 |

### 4.2 P1 테스트 (권장)

| # | 시나리오 | 명령어 | 기대 결과 |
|---|----------|--------|----------|
| 9 | 시작 실패 재시도 | 잘못된 PORT로 시작 | 3회 재시도 후 실패 |
| 10 | 타임아웃 조정 | `-Timeout 120` | 120초까지 대기 |
| 11 | Env 검증 스킵 | `-SkipEnvCheck` | 검증 없이 시작 시도 |

## 5. 롤백 계획

문제 발생 시 원본 스크립트로 복원:

```powershell
# 백업
Copy-Item scripts/server.ps1 scripts/server.ps1.bak

# 롤백
Copy-Item scripts/server.ps1.bak scripts/server.ps1
```

## 6. 의존성

- PowerShell 5.1+ (Windows 10 기본)
- .NET Framework 4.5+ (TcpClient 사용)
- Python 3.10+ (Backend)
- Node.js 18+ (Frontend)

---

**생성일:** 2026-02-03
**작성자:** Claude (PDCA Design)
**상태:** Design 완료, Do 대기
**Plan 참조:** docs/01-plan/features/server-script-improvement.plan.md
