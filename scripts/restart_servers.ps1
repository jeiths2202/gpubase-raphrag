# Restart servers script
Write-Host "Stopping existing servers..."

# Kill processes on ports
foreach ($port in @(3000, 3001, 8000, 9000)) {
    $conn = Get-NetTCPConnection -LocalPort $port -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($conn) {
        Write-Host "Killing process on port $port (PID: $($conn.OwningProcess))"
        Stop-Process -Id $conn.OwningProcess -Force -ErrorAction SilentlyContinue
    }
}

Start-Sleep -Seconds 2

Write-Host "`nStarting Backend (port 9000)..."
$backendPath = "C:\Users\endur\Downloads\tmaxjapan\kms\gpubase-raphrag"
Start-Process -FilePath "python" -ArgumentList "-m", "app.api.main", "--mode", "develop", "--port", "9000" -WorkingDirectory $backendPath -WindowStyle Hidden

Start-Sleep -Seconds 5

Write-Host "Starting Frontend (port 3000)..."
$frontendPath = "C:\Users\endur\Downloads\tmaxjapan\kms\gpubase-raphrag\kms-portal-ui"
Start-Process -FilePath "cmd" -ArgumentList "/c", "npm run dev -- --port 3000" -WorkingDirectory $frontendPath -WindowStyle Hidden

Start-Sleep -Seconds 3

Write-Host "`n=== Server Status ==="
foreach ($port in @(3000, 9000)) {
    $conn = Get-NetTCPConnection -LocalPort $port -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($conn) {
        Write-Host "Port $port : Running (PID: $($conn.OwningProcess))"
    } else {
        Write-Host "Port $port : Not running"
    }
}

Write-Host "`nURLs:"
Write-Host "  Frontend: http://localhost:3000"
Write-Host "  Backend:  http://localhost:9000"
Write-Host "  API Docs: http://localhost:9000/docs"
Write-Host "  Admin:    http://localhost:3000/admin"
