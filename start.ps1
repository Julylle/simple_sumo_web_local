# ==========================================
# Start Frontend and Backend in Background
# Windows Server 2022
# ==========================================

$PROJECT_DIR = $PSScriptRoot

$BACKEND_DIR = Join-Path $PROJECT_DIR "backend"
$FRONTEND_DIR = Join-Path $PROJECT_DIR "frontend"

# Load database settings before launching processes so the backend inherits them.
. (Join-Path $BACKEND_DIR "scripts\load-database-env.ps1")

# Conda environment
$CONDA_ENV = "sumo_web"

# Conda executable
$CONDA = "C:\ProgramData\miniconda3\Scripts\conda.exe"

# Log directory
$LOG_DIR = Join-Path $PROJECT_DIR "logs"
New-Item -ItemType Directory -Force -Path $LOG_DIR | Out-Null

# ==========================================
# Start Backend
# ==========================================

Write-Host "Starting Backend..." -ForegroundColor Green

$backend = Start-Process `
    -FilePath $CONDA `
    -ArgumentList "run --no-capture-output -n $CONDA_ENV python -m uvicorn main:app --host 127.0.0.1 --port 8000" `
    -WorkingDirectory $BACKEND_DIR `
    -RedirectStandardOutput "$LOG_DIR\backend.log" `
    -RedirectStandardError "$LOG_DIR\backend_error.log" `
    -WindowStyle Hidden `
    -PassThru

Write-Host "Backend launcher PID: $($backend.Id)"

# ==========================================
# Start Frontend
# ==========================================

Write-Host "Starting Frontend..." -ForegroundColor Green

$frontend = Start-Process `
    -FilePath "cmd.exe" `
    -ArgumentList "/c npm run dev -- --host 127.0.0.1 --port 5173 --strictPort" `
    -WorkingDirectory $FRONTEND_DIR `
    -RedirectStandardOutput "$LOG_DIR\frontend.log" `
    -RedirectStandardError "$LOG_DIR\frontend_error.log" `
    -WindowStyle Hidden `
    -PassThru

Write-Host "Frontend launcher PID: $($frontend.Id)"

Write-Host ""
Write-Host "======================================"
Write-Host "Services launched in background"
Write-Host "Frontend: http://127.0.0.1:5173"
Write-Host "Backend:  http://127.0.0.1:8000"
Write-Host "Logs:     $LOG_DIR"
Write-Host "======================================"