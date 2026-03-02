# Plan: Server Script Improvement

> scripts/server.ps1 프로덕션급 개선

## 1. 현황 분석

### 1.1 발견된 문제점

| 문제 | 심각도 | 상세 |
|------|--------|------|
| **Start-Process 프로세스 중단** | Critical | `cmd.exe /c`로 백그라운드 실행 시 Python 프로세스가 부모 프로세스(cmd.exe) 종료와 함께 죽음 |
| **대기 시간 하드코딩** | Medium | Backend 15초, Frontend 3초 고정 - 환경에 따라 부족하거나 낭비 |
| **Health Check 미지원** | High | 포트 오픈만 확인, 실제 서비스 Ready 상태 미확인 |
| **Graceful Shutdown 미지원** | Medium | `Stop-Process -Force`로 강제 종료 - 진행 중인 요청 손실 가능 |
| **로그 Rotation 미지원** | Low | 일별 로그만 생성, 용량 관리 없음 |
| **환경변수 검증 미흡** | Medium | .env 파일 존재 여부만 확인, 필수 변수 검증 없음 |
| **에러 복구 미지원** | High | 시작 실패 시 재시도 로직 없음 |

### 1.2 테스트 결과

```
# 테스트 시나리오
.\scripts\server.ps1 backend stop   → OK (포트 확인 후 Kill)
.\scripts\server.ps1 backend start  → FAILED (프로세스 즉시 종료)

# 원인 분석
Start-Process -FilePath "cmd.exe" -ArgumentList "/c", "python ..." -WindowStyle Hidden
→ cmd.exe가 /c 플래그로 실행되어 명령 완료 후 종료
→ Python 프로세스가 cmd.exe의 자식이므로 함께 종료될 가능성

# 직접 실행 테스트
python -m app.api.main --mode develop --port 9000 &
→ 25초 후 정상 시작 (PID: 310848)
```

### 1.3 현재 코드 구조

```
scripts/server.ps1 (360 lines)
├── Parameters: Target, Action, Lines
├── Configuration: Ports (3000, 9000), Paths
├── Functions:
│   ├── Get-DateStamp, Get-*Log        # 로그 경로
│   ├── Write-LogMessage               # 파일 로깅 (retry 로직)
│   ├── Write-Status/Warn/Err          # 콘솔 출력
│   ├── Get-PidByPort                  # netstat 기반 PID 조회
│   ├── Stop-ProcessByPort             # 강제 종료
│   ├── Start-Frontend/Backend         # 서버 시작 (문제 발생)
│   ├── Stop-Frontend/Backend          # 서버 중지
│   ├── Show-Logs                      # 로그 출력
│   └── Show-Status/Usage              # 상태/도움말
└── Main: switch ($Target) { ... }
```

## 2. 개선 목표

### 2.1 Must Have (P0)

| 항목 | 설명 | 완료 기준 |
|------|------|----------|
| 백그라운드 프로세스 안정화 | Start-Process 대신 Job 또는 nohup 방식 | `all restart` 후 5분간 서비스 유지 |
| Health Check 기반 시작 | 포트 + HTTP Health 확인 | `/api/v1/health` 200 응답 확인 |
| Graceful Shutdown | SIGTERM → 타임아웃 → Force | 종료 시 로그에 "graceful" 기록 |
| 환경변수 검증 | 필수 변수 존재 확인 | .env 누락 시 명확한 에러 메시지 |

### 2.2 Should Have (P1)

| 항목 | 설명 | 완료 기준 |
|------|------|----------|
| 시작 재시도 | 3회까지 자동 재시도 | 실패 시 에러 로그 + 재시도 카운트 |
| 타임아웃 설정 가능 | -Timeout 파라미터 | 기본 30초, 최대 120초 |
| 프로세스 상세 정보 | CPU/메모리 사용량 표시 | status 명령 시 리소스 정보 |

### 2.3 Nice to Have (P2)

| 항목 | 설명 | 완료 기준 |
|------|------|----------|
| 로그 Rotation | 7일 이상 로그 자동 삭제 | 스크립트 실행 시 cleanup |
| 의존성 체크 | Python, Node, npm 버전 확인 | start 전 버전 경고 |
| 서비스 모니터링 | watchdog 기능 | 프로세스 죽으면 자동 재시작 |

## 3. 기술 설계

### 3.1 백그라운드 프로세스 실행 방식 변경

**현재 (문제):**
```powershell
Start-Process -FilePath "cmd.exe" -ArgumentList "/c", "python ... >> log 2>&1" -WindowStyle Hidden
```

**개선안 A - PowerShell Job (권장):**
```powershell
$job = Start-Job -ScriptBlock {
    param($ProjectRoot, $LogFile, $Mode, $Port)
    Set-Location $ProjectRoot
    $env:PYTHONIOENCODING = "utf-8"
    & python -m app.api.main --mode $Mode --port $Port 2>&1 | Tee-Object -FilePath $LogFile -Append
} -ArgumentList $ProjectRoot, $logFile, $appMode, $BackendPort

# Job ID를 파일에 저장
$job.Id | Out-File -FilePath "$LogDir\.backend_job_id"
```

**개선안 B - Start-Process with -NoNewWindow:**
```powershell
$proc = Start-Process -FilePath "python" -ArgumentList "-m", "app.api.main", "--mode", $appMode, "--port", $BackendPort `
    -NoNewWindow -PassThru -RedirectStandardOutput $logFile -RedirectStandardError $errLog
$proc.Id | Out-File -FilePath "$LogDir\.backend_pid"
```

### 3.2 Health Check 기반 시작 완료 감지

```powershell
function Wait-ForHealthy {
    param(
        [string]$Url,
        [int]$TimeoutSeconds = 60,
        [int]$IntervalSeconds = 2
    )

    $stopwatch = [System.Diagnostics.Stopwatch]::StartNew()
    while ($stopwatch.Elapsed.TotalSeconds -lt $TimeoutSeconds) {
        try {
            $response = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 5
            if ($response.StatusCode -eq 200) {
                return $true
            }
        } catch {
            # 연결 실패 - 계속 대기
        }
        Start-Sleep -Seconds $IntervalSeconds
    }
    return $false
}

# 사용
$healthy = Wait-ForHealthy -Url "http://localhost:$BackendPort/api/v1/health" -TimeoutSeconds 60
if ($healthy) {
    Write-Status "Backend is healthy and ready"
} else {
    Write-Err "Backend health check failed after 60 seconds"
}
```

### 3.3 Graceful Shutdown

```powershell
function Stop-Gracefully {
    param(
        [int]$ProcessId,
        [int]$GracePeriodSeconds = 10
    )

    try {
        # 1. SIGTERM 신호 (Ctrl+C 시뮬레이션)
        $proc = Get-Process -Id $ProcessId -ErrorAction Stop

        # Windows에서는 GenerateConsoleCtrlEvent 사용 불가하므로
        # WM_CLOSE 메시지 전송 시도
        $proc.CloseMainWindow() | Out-Null

        # 2. Grace period 동안 대기
        $waited = 0
        while (!$proc.HasExited -and $waited -lt $GracePeriodSeconds) {
            Start-Sleep -Seconds 1
            $waited++
        }

        # 3. 여전히 실행 중이면 강제 종료
        if (!$proc.HasExited) {
            Write-Warn "Graceful shutdown timeout, forcing..."
            Stop-Process -Id $ProcessId -Force
        } else {
            Write-Status "Process exited gracefully"
        }
        return $true
    } catch {
        Write-Err "Failed to stop process: $_"
        return $false
    }
}
```

### 3.4 환경변수 검증

```powershell
function Test-RequiredEnvVars {
    $required = @(
        "JWT_SECRET_KEY",
        "ENCRYPTION_MASTER_KEY",
        "NEO4J_PASSWORD"
    )

    $missing = @()
    $envFile = Join-Path $ProjectRoot ".env"

    if (-not (Test-Path $envFile)) {
        Write-Err ".env file not found: $envFile"
        return $false
    }

    $envContent = Get-Content $envFile
    foreach ($var in $required) {
        $found = $envContent | Where-Object { $_ -match "^$var=" }
        if (-not $found) {
            $missing += $var
        }
    }

    if ($missing.Count -gt 0) {
        Write-Err "Missing required environment variables:"
        $missing | ForEach-Object { Write-Err "  - $_" }
        return $false
    }

    return $true
}
```

## 4. 구현 순서

| 순서 | 작업 | 예상 라인 | 우선순위 |
|------|------|----------|----------|
| 1 | Start-Process 방식 변경 (Job 기반) | +50 | P0 |
| 2 | Health Check 함수 추가 | +30 | P0 |
| 3 | Wait-ForHealthy 로직 적용 | +20 | P0 |
| 4 | Graceful Shutdown 구현 | +40 | P0 |
| 5 | 환경변수 검증 함수 추가 | +30 | P0 |
| 6 | 재시도 로직 추가 | +25 | P1 |
| 7 | 프로세스 상세 정보 (CPU/Mem) | +20 | P1 |
| 8 | 로그 Rotation | +15 | P2 |

**예상 총 변경:** 기존 360줄 → 약 550줄 (+190줄)

## 5. 테스트 시나리오

| 시나리오 | 검증 항목 |
|----------|----------|
| `all start` | Backend → Frontend 순차 시작, Health Check 통과 |
| `all stop` | Graceful shutdown, 로그에 종료 기록 |
| `all restart` | 기존 프로세스 정리 → 새로 시작 → 5분 유지 |
| `.env 누락` | 명확한 에러 메시지 출력 |
| `Backend 시작 실패` | 3회 재시도 후 최종 실패 보고 |
| `status` | PID, Port, CPU%, Mem 표시 |

## 6. 위험 요소

| 위험 | 대응 |
|------|------|
| Job 기반 실행이 Windows 정책에 의해 차단될 수 있음 | ExecutionPolicy 체크 + 안내 메시지 |
| Health Check URL이 인증 필요 시 실패 | `/api/v1/health`는 인증 불필요 확인 필요 |
| 긴 startup 시간으로 timeout 발생 | 기본 60초, 환경변수로 조정 가능 |

## 7. 성공 기준

- [ ] `.\server.ps1 all restart` 실행 후 5분간 서비스 정상 운영
- [ ] Backend Health Check (`/api/v1/health`) 200 응답 확인
- [ ] Graceful Shutdown 시 로그에 "graceful" 또는 "clean" 기록
- [ ] .env 필수 변수 누락 시 명확한 에러 출력
- [ ] 시작 실패 시 자동 재시도 (최대 3회)

---

**생성일:** 2026-02-03
**작성자:** Claude (PDCA Plan)
**상태:** Plan 완료, Design 대기
