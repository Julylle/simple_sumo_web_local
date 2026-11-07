# ==========================================
# Start Frontend and Backend in Background
# Windows Server 2022
# ==========================================

param(
    [switch]$BackendOnly,
    [ValidateRange(1, 300)][int]$BackendStartupTimeoutSeconds = 60
)

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

if (-not (Test-Path -LiteralPath $CONDA -PathType Leaf)) {
    throw "Conda executable not found: $CONDA"
}
$watchdogScript = Join-Path $BACKEND_DIR "scripts\backend_watchdog.py"
if (-not (Test-Path -LiteralPath $watchdogScript -PathType Leaf)) {
    throw "Watchdog script not found: $watchdogScript"
}
$stopMarker = Join-Path $LOG_DIR "backend.stop"
if (Test-Path -LiteralPath $stopMarker) { Remove-Item -LiteralPath $stopMarker }
$launcherLog = "backend_launcher_" + [Guid]::NewGuid().ToString("N")
$backend = Start-Process `
    -FilePath $CONDA `
    -ArgumentList "run --no-capture-output -n $CONDA_ENV python -u scripts/backend_watchdog.py" `
    -WorkingDirectory $BACKEND_DIR `
    -RedirectStandardOutput "$LOG_DIR\$launcherLog.log" `
    -RedirectStandardError "$LOG_DIR\${launcherLog}_error.log" `
    -WindowStyle Hidden `
    -PassThru

Write-Host "Watchdog launcher PID: $($backend.Id). See logs\backend_watchdog.log."
Write-Host "Waiting for backend health check (up to $BackendStartupTimeoutSeconds seconds)..."
$backendReady = $false
$deadline = (Get-Date).AddSeconds($BackendStartupTimeoutSeconds)
while ((Get-Date) -lt $deadline) {
    try {
        $health = Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/health" -TimeoutSec 2 -ErrorAction Stop
        if ($health.status -eq "ok") {
            $backendReady = $true
            break
        }
    }
    catch { }
    Start-Sleep -Milliseconds 500
}
if (-not $backendReady) {
    $backend.Refresh()
    if ($backend.HasExited) {
        Write-Warning "Watchdog launcher exited with code $($backend.ExitCode)."
    }
    else {
        Write-Warning "Launcher is still running, but backend health check did not succeed."
    }
    $diagnosticLogs = @(
        (Join-Path $LOG_DIR "$launcherLog.log"),
        (Join-Path $LOG_DIR "${launcherLog}_error.log"),
        (Join-Path $LOG_DIR "backend_watchdog.log"),
        (Join-Path $LOG_DIR "backend_error.log")
    )
    foreach ($logPath in $diagnosticLogs) {
        if (Test-Path -LiteralPath $logPath) {
            Write-Host $logPath -ForegroundColor Yellow
            Get-Content -LiteralPath $logPath -Tail 25 -ErrorAction Continue
        }
    }
    throw "Backend did not become ready. See the diagnostic output above. An active watchdog will keep retrying."
}
Write-Host "Backend ready: http://127.0.0.1:8000/api/health" -ForegroundColor Green

if ($BackendOnly) { return }
if (Get-NetTCPConnection -LocalPort 5173 -State Listen -ErrorAction SilentlyContinue) {
    Write-Host "Port 5173 already has a listener; frontend launch skipped."
    return
}

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