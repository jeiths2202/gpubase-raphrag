@echo off
setlocal enabledelayedexpansion

REM Server Management Script for KMS Portal
REM Usage: server.cmd [frontend|backend|all] [start|stop|restart|status|logs]

set "SCRIPT_DIR=%~dp0"
set "PROJECT_ROOT=%SCRIPT_DIR%.."
set "FRONTEND_DIR=%PROJECT_ROOT%\kms-portal-ui"
set "LOG_DIR=%PROJECT_ROOT%\logs"
set "FRONTEND_PORT=3000"
set "BACKEND_PORT=9000"

set "TARGET=%~1"
set "ACTION=%~2"
set "EXTRA=%~3"

REM Ensure log directory exists
if not exist "%LOG_DIR%" mkdir "%LOG_DIR%"

REM Get date stamp (YYYYMMDD format)
for /f "tokens=2 delims==" %%I in ('wmic os get localdatetime /value') do set "datetime=%%I"
set "DATE_STAMP=%datetime:~0,8%"

set "FRONTEND_LOG=%LOG_DIR%\frontend_%DATE_STAMP%.log"
set "BACKEND_LOG=%LOG_DIR%\backend_%DATE_STAMP%.log"

REM Handle status command without target
if /i "%TARGET%"=="status" (
    call :show_status
    goto :eof
)

if "%TARGET%"=="" goto :show_usage
if "%ACTION%"=="" goto :show_usage

if /i "%TARGET%"=="frontend" (
    if /i "%ACTION%"=="start" call :start_frontend
    if /i "%ACTION%"=="stop" call :stop_frontend
    if /i "%ACTION%"=="restart" (
        call :stop_frontend
        timeout /t 2 /nobreak >nul
        call :start_frontend
    )
    if /i "%ACTION%"=="status" call :show_status
    if /i "%ACTION%"=="logs" call :show_logs frontend
    if /i not "%ACTION%"=="logs" goto :show_final_status
    goto :eof
)

if /i "%TARGET%"=="backend" (
    if /i "%ACTION%"=="start" call :start_backend
    if /i "%ACTION%"=="stop" call :stop_backend
    if /i "%ACTION%"=="restart" (
        call :stop_backend
        timeout /t 2 /nobreak >nul
        call :start_backend
    )
    if /i "%ACTION%"=="status" call :show_status
    if /i "%ACTION%"=="logs" call :show_logs backend
    if /i not "%ACTION%"=="logs" goto :show_final_status
    goto :eof
)

if /i "%TARGET%"=="all" (
    if /i "%ACTION%"=="start" (
        call :start_backend
        call :start_frontend
    )
    if /i "%ACTION%"=="stop" (
        call :stop_frontend
        call :stop_backend
    )
    if /i "%ACTION%"=="restart" (
        call :stop_frontend
        call :stop_backend
        timeout /t 2 /nobreak >nul
        call :start_backend
        call :start_frontend
    )
    if /i "%ACTION%"=="status" call :show_status
    goto :show_final_status
)

goto :show_usage

:get_timestamp
for /f "tokens=2 delims==" %%I in ('wmic os get localdatetime /value') do set "dt=%%I"
set "TIMESTAMP=%dt:~0,4%-%dt:~4,2%-%dt:~6,2% %dt:~8,2%:%dt:~10,2%:%dt:~12,2%"
goto :eof

:log_message
REM Usage: call :log_message "log_file" "message"
call :get_timestamp
echo [%TIMESTAMP%] %~2 >> "%~1"
goto :eof

:get_pid_by_port
REM Usage: call :get_pid_by_port PORT
REM Returns PID in %PID_RESULT%
set "PID_RESULT="
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":%~1" ^| findstr "LISTENING" 2^>nul') do (
    set "PID_RESULT=%%a"
    goto :eof
)
goto :eof

:kill_by_port
REM Usage: call :kill_by_port PORT
call :get_pid_by_port %~1
if defined PID_RESULT (
    echo [INFO] Killing process on port %~1 (PID: %PID_RESULT%)
    taskkill /F /PID %PID_RESULT% >nul 2>&1
    if errorlevel 1 (
        powershell -Command "Stop-Process -Id %PID_RESULT% -Force" >nul 2>&1
    )
    timeout /t 1 /nobreak >nul
) else (
    echo [WARN] No process found on port %~1
)
goto :eof

:start_frontend
call :get_pid_by_port %FRONTEND_PORT%
if defined PID_RESULT (
    echo [WARN] Frontend already running on port %FRONTEND_PORT% (PID: %PID_RESULT%)
    goto :eof
)
echo [INFO] Starting frontend on port %FRONTEND_PORT%...
echo [INFO] Log file: %FRONTEND_LOG%

call :log_message "%FRONTEND_LOG%" "========== Frontend Server Starting =========="

cd /d "%FRONTEND_DIR%"
start "KMS Frontend" cmd /c "npm run dev -- --port %FRONTEND_PORT% >> ^"%FRONTEND_LOG%^" 2>&1"
timeout /t 3 /nobreak >nul

call :get_pid_by_port %FRONTEND_PORT%
if defined PID_RESULT (
    echo [INFO] Frontend started successfully (PID: %PID_RESULT%)
    echo [INFO] URL: http://localhost:%FRONTEND_PORT%
    call :log_message "%FRONTEND_LOG%" "Frontend started successfully (PID: %PID_RESULT%)"
) else (
    echo [ERROR] Failed to start frontend
    call :log_message "%FRONTEND_LOG%" "ERROR: Failed to start frontend"
)
goto :eof

:stop_frontend
echo [INFO] Stopping frontend on port %FRONTEND_PORT%...
call :log_message "%FRONTEND_LOG%" "========== Frontend Server Stopping =========="
call :kill_by_port %FRONTEND_PORT%
call :log_message "%FRONTEND_LOG%" "Frontend stopped"
goto :eof

:start_backend
call :get_pid_by_port %BACKEND_PORT%
if defined PID_RESULT (
    echo [WARN] Backend already running on port %BACKEND_PORT% (PID: %PID_RESULT%)
    goto :eof
)
echo [INFO] Starting backend on port %BACKEND_PORT%...
echo [INFO] Log file: %BACKEND_LOG%

call :log_message "%BACKEND_LOG%" "========== Backend Server Starting =========="

cd /d "%PROJECT_ROOT%"
start "KMS Backend" cmd /c "python -m app.api.main --mode develop --port %BACKEND_PORT% >> ^"%BACKEND_LOG%^" 2>&1"
timeout /t 5 /nobreak >nul

call :get_pid_by_port %BACKEND_PORT%
if defined PID_RESULT (
    echo [INFO] Backend started successfully (PID: %PID_RESULT%)
    echo [INFO] URL: http://localhost:%BACKEND_PORT%
    echo [INFO] Docs: http://localhost:%BACKEND_PORT%/docs
    call :log_message "%BACKEND_LOG%" "Backend started successfully (PID: %PID_RESULT%)"
) else (
    echo [ERROR] Failed to start backend
    call :log_message "%BACKEND_LOG%" "ERROR: Failed to start backend"
)
goto :eof

:stop_backend
echo [INFO] Stopping backend on port %BACKEND_PORT%...
call :log_message "%BACKEND_LOG%" "========== Backend Server Stopping =========="
call :kill_by_port %BACKEND_PORT%
call :log_message "%BACKEND_LOG%" "Backend stopped"
goto :eof

:show_logs
REM Usage: call :show_logs [frontend|backend]
set "LOG_TARGET=%~1"
set "LOG_LINES=%EXTRA%"
if "%LOG_LINES%"=="" set "LOG_LINES=50"

if /i "%LOG_TARGET%"=="frontend" (
    if exist "%FRONTEND_LOG%" (
        echo [INFO] Showing last %LOG_LINES% lines of %FRONTEND_LOG%
        powershell -Command "Get-Content '%FRONTEND_LOG%' -Tail %LOG_LINES%"
    ) else (
        echo [WARN] Log file not found: %FRONTEND_LOG%
    )
)
if /i "%LOG_TARGET%"=="backend" (
    if exist "%BACKEND_LOG%" (
        echo [INFO] Showing last %LOG_LINES% lines of %BACKEND_LOG%
        powershell -Command "Get-Content '%BACKEND_LOG%' -Tail %LOG_LINES%"
    ) else (
        echo [WARN] Log file not found: %BACKEND_LOG%
    )
)
goto :eof

:show_status
echo.
echo === Server Status ===
call :get_pid_by_port %FRONTEND_PORT%
if defined PID_RESULT (
    echo Frontend (port %FRONTEND_PORT%): Running (PID: %PID_RESULT%)
) else (
    echo Frontend (port %FRONTEND_PORT%): Stopped
)
call :get_pid_by_port %BACKEND_PORT%
if defined PID_RESULT (
    echo Backend  (port %BACKEND_PORT%): Running (PID: %PID_RESULT%)
) else (
    echo Backend  (port %BACKEND_PORT%): Stopped
)
echo.
echo === Log Files ===
echo Frontend: %FRONTEND_LOG%
echo Backend:  %BACKEND_LOG%
echo.
goto :eof

:show_final_status
call :show_status
goto :eof

:show_usage
echo Usage: %~nx0 [target] [action]
echo.
echo Targets:
echo   frontend    - Frontend server (port %FRONTEND_PORT%)
echo   backend     - Backend API server (port %BACKEND_PORT%)
echo   all         - Both frontend and backend
echo.
echo Actions:
echo   start       - Start server(s)
echo   stop        - Stop server(s)
echo   restart     - Restart server(s)
echo   status      - Show server status
echo   logs [N]    - Show last N lines of log (default: 50)
echo.
echo Log files are saved to: %LOG_DIR%
echo   - frontend_YYYYMMDD.log
echo   - backend_YYYYMMDD.log
echo.
echo Examples:
echo   %~nx0 frontend start     # Start frontend only
echo   %~nx0 backend restart    # Restart backend only
echo   %~nx0 all stop           # Stop all servers
echo   %~nx0 status             # Show status of all servers
echo   %~nx0 frontend logs 100  # Show last 100 lines of frontend log
goto :eof
