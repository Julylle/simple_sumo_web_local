# ==========================================
# Stop Frontend and Backend
# Windows Server 2022
# ==========================================

$PORTS = @(8000, 5173)
$logDir = Join-Path $PSScriptRoot "logs"
function Stop-BackendWatchdog {
    New-Item -ItemType Directory -Force -Path $logDir | Out-Null
    New-Item -ItemType File -Force -Path (Join-Path $logDir "backend.stop") | Out-Null
}

Write-Host "Checking Frontend and Backend..." -ForegroundColor Cyan

foreach ($PORT in $PORTS) {

    $connections = @(
        Get-NetTCPConnection `
            -LocalPort $PORT `
            -State Listen `
            -ErrorAction SilentlyContinue
    )

    if ($connections.Count -eq 0) {
        Write-Host "Port ${PORT}: Not running" -ForegroundColor Yellow
        if ($PORT -eq 8000 -and (Read-Host "Disable backend auto-restart? (Y/N)") -eq "Y") {
            Stop-BackendWatchdog
        }
        continue
    }

    $processIds = @(
        $connections |
        Select-Object -ExpandProperty OwningProcess -Unique
    )

    foreach ($processId in $processIds) {

        $process = Get-Process -Id $processId -ErrorAction SilentlyContinue

        if (-not $process) {
            continue
        }

        Write-Host ""
        Write-Host "Port: $PORT"
        Write-Host "Process: $($process.ProcessName)"
        Write-Host "PID: $processId"

        # Only allow expected process types
        if ($process.ProcessName -notin @("python", "pythonw", "node")) {
            Write-Host "Unexpected process. Skipping." -ForegroundColor Red
            continue
        }

        $answer = Read-Host "Stop this process? (Y/N)"

        if ($answer -ne "Y") {
            Write-Host "Skipped PID $processId"
            continue
        }

        try {
            if ($PORT -eq 8000) { Stop-BackendWatchdog }
            if (-not $process.HasExited) { $process.Kill() }
            Write-Host "Stopped PID $processId" -ForegroundColor Green
        }
        catch {
            Write-Host "Failed to stop PID ${processId}: $_" -ForegroundColor Red
        }
    }
}

# ==========================================
# Verify ports
# ==========================================

Start-Sleep -Seconds 2

Write-Host ""
Write-Host "Checking remaining listeners..." -ForegroundColor Cyan

$remaining = @(
    Get-NetTCPConnection `
        -LocalPort $PORTS `
        -State Listen `
        -ErrorAction SilentlyContinue
)

if ($remaining.Count -eq 0) {
    Write-Host "Both ports are now free." -ForegroundColor Green
}
else {
    $remaining |
        Select-Object LocalAddress, LocalPort, OwningProcess |
        Format-Table

    Write-Host "Some services are still running." -ForegroundColor Yellow
}