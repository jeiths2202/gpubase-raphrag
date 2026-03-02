@echo off
echo Stopping all servers...
taskkill /F /IM python.exe 2>nul
taskkill /F /IM node.exe 2>nul
timeout /t 3 /nobreak >nul

echo Starting backend on port 9000...
cd /d C:\Users\endur\Downloads\tmaxjapan\kms\gpubase-raphrag
start "Backend" cmd /c "python -m app.api.main --mode develop --port 9000"
timeout /t 6 /nobreak >nul

echo Starting frontend on port 3000...
cd /d C:\Users\endur\Downloads\tmaxjapan\kms\gpubase-raphrag\kms-portal-ui
start "Frontend" cmd /c "npm run dev -- --port 3000"
timeout /t 3 /nobreak >nul

echo.
echo Servers started!
echo   Frontend: http://localhost:3000
echo   Backend:  http://localhost:9000
echo   Admin:    http://localhost:3000/admin
