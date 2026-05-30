# ── TALVEX Local Service Orchestration Script ──────────────────────────
# Usage: .\run_local.ps1
#
# This script orchestrates and launches all local components of the TALVEX
# platform in separate interactive terminal windows for easy log monitoring.
# Runs 100% locally with Node/NPM, Python, PostgreSQL, and Redis.
# No Docker required.

$ErrorActionPreference = "Stop"

# Clear host and print a premium banner
Clear-Host
Write-Host "──────────────────────────────────────────────────────────" -ForegroundColor Cyan
Write-Host "                TALVEX LOCAL LAUNCHER                     " -ForegroundColor Green -Bold
Write-Host "         The AI-Powered Job Application pipeline            " -ForegroundColor Gray
Write-Host "──────────────────────────────────────────────────────────" -ForegroundColor Cyan

# ── 1. Check Prerequisites ──────────────────────────────────────────
Write-Host "`n[1/6] Checking prerequisites..." -ForegroundColor Yellow

# Node.js Check
$node = Get-Command "node" -ErrorAction SilentlyContinue
if (-not $node) {
    Write-Error "Node.js is NOT installed! Please install Node.js 18+ first."
}
$nodeVersion = & node -v
Write-Host "  [OK] Node.js: Active ($nodeVersion)" -ForegroundColor Green

# NPM Check
$npm = Get-Command "npm" -ErrorAction SilentlyContinue
if (-not $npm) {
    Write-Error "NPM is NOT installed! Please install NPM."
}
Write-Host "  [OK] NPM: Active" -ForegroundColor Green

# Python Check
$python = Get-Command "python" -ErrorAction SilentlyContinue
if (-not $python) {
    Write-Error "Python is NOT installed! Please install Python 3.10+ and add it to your PATH."
}
$pyVersion = & python --version
Write-Host "  [OK] Python: Active ($pyVersion)" -ForegroundColor Green

# ── 2. Check & Configure Environment ─────────────────────────────────
Write-Host "`n[2/6] Checking environment configuration..." -ForegroundColor Yellow

$envFile = Join-Path $PSScriptRoot ".env"
$exampleFile = Join-Path $PSScriptRoot ".env.example"

if (-not (Test-Path $envFile)) {
    if (Test-Path $exampleFile) {
        Write-Host "  [WARN] .env file is missing! Copying from .env.example..." -ForegroundColor Cyan
        Copy-Item $exampleFile $envFile
        Write-Host "  [OK] .env file created. Please open '.env' and fill in your API keys!" -ForegroundColor Yellow
    } else {
        Write-Error "Both .env and .env.example are missing! Local startup halted."
    }
} else {
    Write-Host "  [OK] .env file: Detected" -ForegroundColor Green
}

# ── 3. Check PostgreSQL (Mandatory — SQLite fallback removed) ─────────
Write-Host "`n[3/6] Checking PostgreSQL instance (Port 5439)..." -ForegroundColor Yellow
$pgTest = Test-NetConnection -ComputerName "localhost" -Port 5439 -WarningAction SilentlyContinue

if ($pgTest.TcpTestSucceeded) {
    Write-Host "  [OK] PostgreSQL: Detected and responding on port 5439!" -ForegroundColor Green
} else {
    Write-Host "  [FAIL] PostgreSQL is NOT running on localhost:5439!" -ForegroundColor Red -Bold
    Write-Host "         SQLite fallback has been REMOVED for production safety." -ForegroundColor Yellow
    Write-Host "         Start PostgreSQL locally or via Docker:" -ForegroundColor Gray
    Write-Host '         docker run -d --name talvex-pg -p 5439:5432 -e POSTGRES_USER=talvex -e POSTGRES_PASSWORD=t4lv3x_s3cur3 -e POSTGRES_DB=talvex postgres:16-alpine' -ForegroundColor DarkGray
    $continue = Read-Host "         Continue anyway? (y/N)"
    if ($continue -ne "y") {
        Write-Host "  Aborted. Start PostgreSQL and try again." -ForegroundColor Red
        exit 1
    }
}

# ── 4. Check Redis Instance (Mandatory for ARQ) ──────────────────────
Write-Host "`n[4/6] Checking Redis instance (Port 6379)..." -ForegroundColor Yellow
$redisTest = Test-NetConnection -ComputerName "localhost" -Port 6379 -WarningAction SilentlyContinue

if ($redisTest.TcpTestSucceeded) {
    Write-Host "  [OK] Redis: Detected and responding on port 6379!" -ForegroundColor Green
} else {
    Write-Host "  [FAIL] Redis is NOT running on localhost:6379!" -ForegroundColor Red -Bold
    Write-Host "         ARQ background workers and stateful auth require Redis." -ForegroundColor Yellow
    Write-Host "         Start Redis locally (redis-server or memurai) or via Docker:" -ForegroundColor Gray
    Write-Host '         docker run -d --name talvex-redis -p 6379:6379 redis:7-alpine' -ForegroundColor DarkGray
    $continue = Read-Host "         Continue anyway? (y/N)"
    if ($continue -ne "y") {
        Write-Host "  Aborted. Start Redis and try again." -ForegroundColor Red
        exit 1
    }
}

# ── 5. Set Up Dependencies & Database Migrations ─────────────────────
Write-Host "`n[5/6] Aligning dependencies and database..." -ForegroundColor Yellow

# Create python venv if not exists
$venvDir = Join-Path $PSScriptRoot "backend\venv"
if (-not (Test-Path $venvDir)) {
    Write-Host "  Venv not found. Initializing virtual environment at $venvDir..." -ForegroundColor Cyan
    & python -m venv $venvDir
    Write-Host "  [OK] Virtual environment initialized!" -ForegroundColor Green
} else {
    Write-Host "  [OK] Python Virtual Environment: Active" -ForegroundColor Green
}

# Determine correct pip path inside venv
$pipPath = Join-Path $venvDir "Scripts\pip.exe"
$pythonExec = Join-Path $venvDir "Scripts\python.exe"

# Install backend dependencies (verbose — no --quiet)
Write-Host "  Installing backend Python dependencies..." -ForegroundColor Cyan
& $pipPath install -r (Join-Path $PSScriptRoot "backend\requirements.txt")
if ($LASTEXITCODE -ne 0) {
    Write-Host "  [FAIL] pip install failed! Check the errors above." -ForegroundColor Red
    $continue = Read-Host "         Continue anyway? (y/N)"
    if ($continue -ne "y") { exit 1 }
} else {
    Write-Host "  [OK] Backend dependencies: Synchronized" -ForegroundColor Green
}

# Install frontend dependencies
Write-Host "  Installing frontend Node dependencies..." -ForegroundColor Cyan
& npm install --no-audit --no-fund
if ($LASTEXITCODE -ne 0) {
    Write-Host "  [FAIL] npm install failed! Check the errors above." -ForegroundColor Red
    $continue = Read-Host "         Continue anyway? (y/N)"
    if ($continue -ne "y") { exit 1 }
} else {
    Write-Host "  [OK] Frontend dependencies: Synchronized" -ForegroundColor Green
}

# Alembic DB Migration Check (LOUD failures — halt on error)
Write-Host "  Applying latest database migrations (Alembic)..." -ForegroundColor Cyan
try {
    $prevDir = Get-Location
    Set-Location (Join-Path $PSScriptRoot "backend")
    $migrationOutput = & $pythonExec -m alembic upgrade head 2>&1
    if ($LASTEXITCODE -ne 0) {
        Write-Host "  [FAIL] Alembic migration FAILED with output:" -ForegroundColor Red -Bold
        Write-Host $migrationOutput -ForegroundColor Red
        Write-Host "  This usually means DATABASE_URL in .env is wrong or PostgreSQL is not running." -ForegroundColor Yellow
        $continue = Read-Host "         Continue anyway? (y/N)"
        if ($continue -ne "y") {
            Set-Location $prevDir
            exit 1
        }
    } else {
        Write-Host "  [OK] Database migrations: Up-to-date!" -ForegroundColor Green
    }
    Set-Location $prevDir
} catch {
    Write-Host "  [FAIL] Alembic migration CRASHED:" -ForegroundColor Red -Bold
    Write-Host $_.Exception.Message -ForegroundColor Red
    $continue = Read-Host "         Continue anyway? (y/N)"
    if ($continue -ne "y") { exit 1 }
}

# ── 6. Launch Orchestrator ──────────────────────────────────────────
Write-Host "`n[6/6] Launching TALVEX services in separate shell windows..." -ForegroundColor Yellow

# Launch FastAPI Backend
Write-Host "  Starting FastAPI Backend (Port 8000)..." -ForegroundColor Green
Start-Process powershell.exe -ArgumentList "-NoExit", "-Command", "cd '$PSScriptRoot\backend'; .\venv\Scripts\python.exe -m uvicorn main:app --reload --port 8000" -WindowStyle Normal

# Launch ARQ Worker
Write-Host "  Starting ARQ Background Task Worker..." -ForegroundColor Green
Start-Process powershell.exe -ArgumentList "-NoExit", "-Command", "cd '$PSScriptRoot\backend'; .\venv\Scripts\python.exe -m arq worker.WorkerSettings" -WindowStyle Normal

# Launch Next.js Frontend
Write-Host "  Starting Next.js Frontend (Port 3000)..." -ForegroundColor Green
Start-Process powershell.exe -ArgumentList "-NoExit", "-Command", "cd '$PSScriptRoot'; npm run dev" -WindowStyle Normal

Write-Host "`n──────────────────────────────────────────────────────────" -ForegroundColor Cyan
Write-Host "   SUCCESS: All TALVEX services have been booted!" -ForegroundColor Green -Bold
Write-Host "   FastAPI API:  http://localhost:8000/docs" -ForegroundColor Gray
Write-Host "   Frontend:     http://localhost:3000" -ForegroundColor Gray
Write-Host "──────────────────────────────────────────────────────────" -ForegroundColor Cyan
Write-Host "Opening frontend in your browser now..." -ForegroundColor Cyan

Start-Sleep -Seconds 3
Start-Process "http://localhost:3000"
