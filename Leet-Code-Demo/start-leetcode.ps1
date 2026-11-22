# =============================================================================
# CodeArena (LeetCode Demo) - One-Click Launcher
# =============================================================================

$WorkspaceRoot = $PSScriptRoot

Write-Host "==============================================================" -ForegroundColor Cyan
Write-Host "  Launching CodeArena (LeetCode Demo Platform)" -ForegroundColor Cyan
Write-Host "==============================================================" -ForegroundColor Cyan

# 1. Environment Config Check
$BackendEnv = "$WorkspaceRoot\backend\.env"
if (-not (Test-Path $BackendEnv)) {
    Write-Host "[1/4] Initializing backend\.env from backend\.env.example..." -ForegroundColor Yellow
    Copy-Item "$WorkspaceRoot\backend\.env.example" $BackendEnv
} else {
    Write-Host "[1/4] Found backend\.env configuration." -ForegroundColor Green
}

# Check if credentials are set
$FaasPublicId = ""
$FaasApiKey = ""
$FaasBaseUrl = "http://127.0.0.1:8000"

Get-Content $BackendEnv | ForEach-Object {
    if ($_ -match "^\s*FAAS_PUBLIC_ID\s*=\s*(.+)$") { $FaasPublicId = $matches[1].Trim() }
    if ($_ -match "^\s*FAAS_API_KEY\s*=\s*(.+)$") { $FaasApiKey = $matches[1].Trim() }
    if ($_ -match "^\s*FAAS_BASE_URL\s*=\s*(.+)$") { $FaasBaseUrl = $matches[1].Trim() }
}

if (-not $FaasPublicId -or -not $FaasApiKey) {
    Write-Host ""
    Write-Host "[!] NOTE: FAAS_PUBLIC_ID and FAAS_API_KEY are not configured in backend\.env yet." -ForegroundColor Yellow
    Write-Host "    Open $BackendEnv and paste your FaaS credentials" -ForegroundColor Yellow
    Write-Host "    (obtained from your FaaS Dashboard -> Invocation Console -> API Access panel)." -ForegroundColor Yellow
    Write-Host ""
} else {
    Write-Host "  -> MicroFaaS Target: $FaasBaseUrl" -ForegroundColor Green
    Write-Host "  -> Target Function:  $FaasPublicId" -ForegroundColor Green
}

# 2. Locate Python executable
Write-Host "[2/4] Locating Python runtime..." -ForegroundColor Yellow
$PythonCmd = "python"
if (Test-Path "$WorkspaceRoot\backend\.venv\Scripts\python.exe") {
    $PythonCmd = "$WorkspaceRoot\backend\.venv\Scripts\python.exe"
} elseif (Test-Path "$WorkspaceRoot\..\.venv\Scripts\python.exe") {
    $PythonCmd = "$WorkspaceRoot\..\.venv\Scripts\python.exe"
} elseif (Test-Path "$WorkspaceRoot\..\venv\Scripts\python.exe") {
    $PythonCmd = "$WorkspaceRoot\..\venv\Scripts\python.exe"
}
Write-Host "  -> Using Python: $PythonCmd" -ForegroundColor Green

# 3. Start Backend on port 8001
Write-Host "[3/4] Starting CodeArena Backend on http://localhost:8001..." -ForegroundColor Yellow
Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd '$WorkspaceRoot\backend'; Write-Host '--- CodeArena FastAPI Backend (Port 8001) ---' -ForegroundColor Green; & '$PythonCmd' -m uvicorn app.main:app --host 0.0.0.0 --port 8001 --reload"

# 4. Start Frontend on port 5174
Write-Host "[4/4] Starting CodeArena Frontend on http://localhost:5174..." -ForegroundColor Yellow
if (-not (Test-Path "$WorkspaceRoot\frontend\node_modules")) {
    Write-Host "  -> Installing npm dependencies for frontend..." -ForegroundColor Yellow
    Start-Process powershell -Wait -ArgumentList "-Command", "cd '$WorkspaceRoot\frontend'; npm install"
}
Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd '$WorkspaceRoot\frontend'; Write-Host '--- CodeArena Vite Frontend (Port 5174) ---' -ForegroundColor Cyan; npm run dev"

Write-Host ""
Write-Host "==============================================================" -ForegroundColor Green
Write-Host "  CodeArena Demo Successfully Started!" -ForegroundColor Green
Write-Host "==============================================================" -ForegroundColor Green
Write-Host "  - LeetCode Web UI:      http://localhost:5174" -ForegroundColor White
Write-Host "  - LeetCode Backend API: http://localhost:8001/docs" -ForegroundColor White
Write-Host "  - Connected FaaS:       $FaasBaseUrl" -ForegroundColor White
Write-Host "==============================================================" -ForegroundColor Green
