@echo off
REM KMS AI Agent CLI Launcher
REM Usage: agent.cmd [options]

set "SCRIPT_DIR=%~dp0"
set "PROJECT_ROOT=%SCRIPT_DIR%.."

cd /d "%PROJECT_ROOT%"

python -m cli.agent %*
