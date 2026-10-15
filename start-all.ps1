# =============================================================================
# Kubernetes Serverless FaaS Platform - One-Click Launcher
# Usage: .\start-all.ps1 [-Tunnel]
# =============================================================================

param (
    [switch]$Tunnel = $false,
    [string]$NgrokDomain = ""
)

Write-Host "==============================================================" -ForegroundColor Cyan
Write-Host "  Launching Kubernetes FaaS Platform (Full Stack)" -ForegroundColor Cyan
Write-Host "==============================================================" -ForegroundColor Cyan

$WorkspaceRoot = $PSScriptRoot

# 1. Environment Config
if (-not (Test-Path "$WorkspaceRoot\.env")) {
    Write-Host "[1/6] Initializing .env from .env.example..." -ForegroundColor Yellow
    Copy-Item "$WorkspaceRoot\.env.example" "$WorkspaceRoot\.env"
} else {
    Write-Host "[1/6] Configuration file .env found." -ForegroundColor Green
}

# Read NGROK settings from .env if not passed
if (-not $NgrokDomain) {
    Get-Content "$WorkspaceRoot\.env" | ForEach-Object {
        if ($_ -match "^NGROK_DOMAIN=(.+)$") {
            $NgrokDomain = $matches[1].Trim()
        }
    }
}

# 2. Check Docker
Write-Host "[2/6] Checking Docker status..." -ForegroundColor Yellow
try {
    $dockerCheck = docker info 2>&1
    if ($LASTEXITCODE -ne 0) {
        Write-Host "ERROR: Docker Desktop is not running. Please start Docker Desktop and retry." -ForegroundColor Red
        exit 1
    }
    Write-Host "  -> Docker daemon is healthy." -ForegroundColor Green
} catch {
    Write-Host "ERROR: Could not communicate with Docker." -ForegroundColor Red
    exit 1
}

# 3. Start PostgreSQL and Docker Registry
Write-Host "[3/6] Starting supporting infrastructure (Postgres + Registry)..." -ForegroundColor Yellow
docker compose up -d
if ($LASTEXITCODE -ne 0) {
    Write-Host "ERROR: docker compose failed to start containers." -ForegroundColor Red
    exit 1
}
Write-Host "  -> Supporting containers running." -ForegroundColor Green

# 4. Backend Dependencies & Launcher
Write-Host "[4/6] Starting FastAPI Backend on http://localhost:8000..." -ForegroundColor Yellow
$PythonCmd = "python"
if (Test-Path "$WorkspaceRoot\venv\Scripts\python.exe") {
    $PythonCmd = "$WorkspaceRoot\venv\Scripts\python.exe"
}

# Start backend in new background window
Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd '$WorkspaceRoot'; Write-Host '--- FaaS FastAPI Backend ---' -ForegroundColor Green; & '$PythonCmd' -m uvicorn backend.app.main:app --host 0.0.0.0 --port 8000 --reload"

# 5. Frontend Dependencies & Launcher
Write-Host "[5/6] Starting Vite Frontend on http://localhost:5173..." -ForegroundColor Yellow
if (-not (Test-Path "$WorkspaceRoot\frontend\node_modules")) {
    Write-Host "  -> First-time setup: installing npm packages..." -ForegroundColor Yellow
    Start-Process powershell -Wait -ArgumentList "-Command", "cd '$WorkspaceRoot\frontend'; npm install"
}

# Start frontend in new background window
Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd '$WorkspaceRoot\frontend'; Write-Host '--- FaaS Vite Frontend ---' -ForegroundColor Cyan; npm run dev"

# 6. Public Tunneling (Optional / Automatic if configured)
if ($Tunnel -or $NgrokDomain) {
    Write-Host "[6/6] Launching Ngrok tunnel..." -ForegroundColor Yellow
    if ($NgrokDomain) {
        Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd '$WorkspaceRoot'; Write-Host '--- Ngrok Public Tunnel ---' -ForegroundColor Magenta; ngrok http 5173 --domain=$NgrokDomain"
        $PublicUrl = "https://$NgrokDomain"
    } else {
        Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd '$WorkspaceRoot'; Write-Host '--- Ngrok Public Tunnel ---' -ForegroundColor Magenta; ngrok http 5173"
        $PublicUrl = "Active (Check Ngrok window for URL)"
    }
} else {
    Write-Host "[6/6] Skipping public tunnel (pass -Tunnel or set NGROK_DOMAIN in .env to enable)." -ForegroundColor Gray
    $PublicUrl = "None (Run: ngrok http 5173 to expose)"
}

Write-Host ""
Write-Host "==============================================================" -ForegroundColor Green
Write-Host "  Platform Successfully Started!" -ForegroundColor Green
Write-Host "==============================================================" -ForegroundColor Green
Write-Host "  - Local Dashboard:     http://localhost:5173" -ForegroundColor White
Write-Host "  - Backend API & Docs:  http://localhost:8000/docs" -ForegroundColor White
Write-Host "  - Prometheus Exporter: http://localhost:8000/api/v1/metrics" -ForegroundColor White
if ($PublicUrl -ne "None (Run: ngrok http 5173 to expose)") {
    Write-Host "  - Public Domain:       $PublicUrl" -ForegroundColor Cyan
}
Write-Host "==============================================================" -ForegroundColor Green
